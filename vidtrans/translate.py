# -*- coding: utf-8 -*-
"""翻译：OpenAI 兼容接口的分块并行翻译。

设计要点（都是这次长视频踩出来的）：
  * 一行一条、id 严格对齐，避免模型自由发挥导致时间轴错位
  * 分块 + 并发，失败块单独重试
  * 缺 id / JSON 坏掉时，只针对缺失部分补问一次
  * 术语表与额外规则注入 system prompt
  * MockTranslator 供离线自测
"""
import json
import random
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

LANG_LABEL = {
    "zh": "简体中文", "zh-tw": "繁体中文", "ja": "日语", "en": "英语",
    "ko": "韩语", "ru": "俄语", "fr": "法语", "de": "德语", "es": "西班牙语",
    "pt": "葡萄牙语", "it": "意大利语", "th": "泰语", "vi": "越南语",
}


class TranslateError(RuntimeError):
    pass


def label(lang):
    return LANG_LABEL.get((lang or "").lower(), lang or "目标语言")


SYSTEM_TEMPLATE = """你是专业的字幕翻译，把{src}视频字幕翻译成{dst}。

## 输出格式（必须严格遵守）
输入是一个 JSON 数组，元素形如 {{"id": 12, "src": "原文"}}。
输出必须是**同样长度、同样 id、同样顺序**的 JSON 数组，元素只含 id 与 text：
[{{"id": 12, "text": "译文"}}, {{"id": 13, "text": "译文"}}]

- 一个 id 只输出一行译文，不要合并、拆分、新增或删除 id。
- 译文控制在 {max_chars} 字以内；原文信息过多时只保留核心意思，宁短勿长。
- 只输出 JSON 数组本身，不要任何解释、注释或代码块围栏。

## 翻译风格
- 口语化、自然，像本地语言的字幕，不要翻译腔。
- 数字用阿拉伯数字。
- 语气词、感叹保留情绪。
- 语音识别可能有错字，按上下文合理修正，不要编造原文没有的内容。

{glossary_block}{rules_block}"""

GLOSSARY_BLOCK = """## 术语表（必须使用下列译法，优先级最高）
{body}

"""

RULES_BLOCK = """## 额外要求
{body}
"""


def _extract_json(text):
    """从模型输出里尽量抠出 JSON 数组。"""
    if not text:
        return None
    t = text.strip()
    # 去代码块围栏
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    a, b = t.find("["), t.rfind("]")
    if a >= 0 and b > a:
        try:
            return json.loads(t[a:b + 1])
        except Exception:
            pass
    # 逐条抠 {"id": N, "text": "..."}
    items = []
    for m in re.finditer(r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"text"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}', t):
        try:
            items.append({"id": int(m.group(1)),
                          "text": json.loads('"' + m.group(2) + '"')})
        except Exception:
            continue
    return items or None


class Translator:
    """OpenAI 兼容 /chat/completions。"""

    def __init__(self, cfg, src_lang="ja", dst_lang="zh", glossary="",
                 extra_rules="", log=print, progress=None, cancel=None):
        p = cfg.get("provider") or {}
        self.base_url = (p.get("base_url") or "").rstrip("/")
        self.model = p.get("model") or "gpt-4o-mini"
        self.api_key = p.get("api_key") or ""
        self.temperature = float(p.get("temperature") or 0.3)
        self.max_tokens = int(p.get("max_tokens") or 4096)
        self.timeout = int(p.get("timeout") or 180)
        self.max_retry = int(cfg.get("max_retry") or 4)
        self.concurrency = max(1, int(cfg.get("concurrency") or 4))
        self.max_chars = int(cfg.get("max_line_chars") or 24)

        self.src_lang = src_lang
        self.dst_lang = dst_lang
        self.log = log
        self.progress = progress
        self.cancel = cancel
        self.usage = {"prompt": 0, "completion": 0, "calls": 0}
        self._lock = threading.Lock()

        gl = GLOSSARY_BLOCK.format(body=glossary.strip()) if (glossary or "").strip() else ""
        ru = RULES_BLOCK.format(body=extra_rules.strip()) if (extra_rules or "").strip() else ""
        self.system = SYSTEM_TEMPLATE.format(
            src=label(src_lang), dst=label(dst_lang),
            max_chars=self.max_chars,
            glossary_block=gl, rules_block=ru,
        )

    # ---------- HTTP ----------
    def _post(self, messages):
        if not self.api_key:
            raise TranslateError("没有配置 API Key，请在设置里填写")
        if not self.base_url:
            raise TranslateError("没有配置 API 地址 base_url")
        url = self.base_url + "/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + self.api_key)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        if "error" in data and data["error"]:
            raise TranslateError(str(data["error"])[:500])
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        with self._lock:
            self.usage["prompt"] += int(usage.get("prompt_tokens") or 0)
            self.usage["completion"] += int(usage.get("completion_tokens") or 0)
            self.usage["calls"] += 1
        return content

    def _chat(self, cues, ctx=None):
        payload = [{"id": c["id"], "src": c["src"]} for c in cues]
        user = ""
        if ctx:
            user += "前文（仅供理解上下文，不要翻译）：\n" + \
                    "\n".join(c["src"] for c in ctx) + "\n\n"
        user += "请翻译下面这个 JSON 数组，返回等长 JSON 数组：\n" + \
                json.dumps(payload, ensure_ascii=False)
        last_err = None
        for attempt in range(self.max_retry):
            try:
                content = self._post([
                    {"role": "system", "content": self.system},
                    {"role": "user", "content": user},
                ])
                data = _extract_json(content)
                if not isinstance(data, list):
                    raise TranslateError("返回不是 JSON 数组")
                return {int(x["id"]): (x.get("text") or "").strip()
                        for x in data if isinstance(x, dict) and "id" in x}
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                    json.JSONDecodeError, TranslateError, KeyError, TypeError) as e:
                last_err = e
                wait = min(30, (2 ** attempt) + random.random() * 1.5)
                if isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403):
                    raise TranslateError(f"API 拒绝（{e.code}）："
                                         f"{e.read().decode('utf-8', 'replace')[:300]}")
                self.log(f"  重试 {attempt + 1}/{self.max_retry}：{type(e).__name__} {e}")
                time.sleep(wait)
        raise TranslateError(f"多次重试仍失败：{last_err}")

    # ---------- 对外 ----------
    def translate_chunk(self, chunk):
        want = [c["id"] for c in chunk["cues"]]
        got = self._chat(chunk["cues"], chunk.get("ctx"))
        missing = [i for i in want if i not in got or not got[i]]
        if missing:
            self.log(f"  第 {chunk['index'] + 1} 块缺 {len(missing)} 条，补问一次")
            sub = [c for c in chunk["cues"] if c["id"] in missing]
            got2 = self._chat(sub, chunk.get("ctx"))
            for k, v in got2.items():
                if v:
                    got[k] = v
        return {i: got.get(i, "") for i in want}

    def translate_all(self, chunks):
        """并发翻译所有分块，返回 {id: text}。"""
        total = len(chunks)
        result = {}
        done = 0
        errors = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
            futs = {ex.submit(self.translate_chunk, ch): ch for ch in chunks}
            for fut in as_completed(futs):
                ch = futs[fut]
                if self.cancel is not None and self.cancel.is_set():
                    for f in futs:
                        f.cancel()
                    raise TranslateError("已取消")
                try:
                    part = fut.result()
                    with self._lock:
                        result.update(part)
                except Exception as e:
                    errors.append((ch["index"], str(e)[:200]))
                    self.log(f"  第 {ch['index'] + 1} 块失败：{e}")
                done += 1
                if self.progress:
                    self.progress.fraction(
                        "translate", done / total,
                        f"翻译中 {done}/{total} 块（{len(result)} 条）")
        if errors and len(errors) == total:
            raise TranslateError("所有分块都失败了：" + errors[0][1])
        if errors:
            self.log(f"有 {len(errors)} 个分块失败，对应字幕将留空")
        cost = self.usage["prompt"] * 0.0000005 + self.usage["completion"] * 0.0000015
        self.log(f"翻译完成：{len(result)} 条，API 调用 {self.usage['calls']} 次，"
                 f"tokens {self.usage['prompt']}/{self.usage['completion']}，"
                 f"粗估费用 ≈ {cost:.3f} 元")
        return result


class MockTranslator(Translator):
    """离线自测用：不联网，译文 = [目标语言] + 原文。"""

    def __init__(self, cfg, *a, **kw):
        super().__init__(cfg, *a, **kw)
        self.api_key = self.api_key or "mock"

    def _post(self, messages):
        user = messages[-1]["content"]
        a = user.find("[")
        payload = json.loads(user[a:])
        out = []
        for it in payload:
            src = it.get("src") or ""
            out.append({"id": it["id"], "text": f"[{self.dst_lang}]{src[:self.max_chars]}"})
        time.sleep(0.02)
        with self._lock:
            self.usage["calls"] += 1
        return json.dumps(out, ensure_ascii=False)
