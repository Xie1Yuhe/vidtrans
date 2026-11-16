# -*- coding: utf-8 -*-
"""本地假 OpenAI 接口，用来在不花钱的情况下验证翻译 HTTP 路径。

    python test/mock_api.py 8899

收到 /v1/chat/completions，解析 user 消息里的 JSON 数组，
按 id 回一个「[译]原文前若干字」的数组。
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace")
        try:
            req = json.loads(raw)
        except Exception:
            req = {}
        msgs = req.get("messages") or []
        user = msgs[-1]["content"] if msgs else ""
        a = user.find("[")
        items = []
        try:
            items = json.loads(user[a:]) if a >= 0 else []
        except Exception:
            items = []
        out = []
        for it in items:
            src = (it.get("src") or "").strip()
            out.append({"id": it.get("id"), "text": "【译】" + src[:18]})
        content = json.dumps(out, ensure_ascii=False)
        body = json.dumps({
            "id": "mock",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant",
                                                "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": len(user) // 3,
                      "completion_tokens": len(content) // 3,
                      "total_tokens": (len(user) + len(content)) // 3},
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"mock api on http://127.0.0.1:{port}/v1/chat/completions", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
