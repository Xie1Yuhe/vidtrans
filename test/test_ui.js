// 用最小 DOM 桩执行 index.html 里的脚本，验证：
//   1) window 上确实注册了 drop 监听（拖文件不会再被浏览器直接打开）
//   2) 语言下拉框在没有网络的情况下也有选项（不会「点了没反应」）
//   3) boot() 即使连不上后端也不抛异常（交互仍可用）
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(path.join(__dirname, "..", "vidtrans", "web", "index.html"), "utf8");
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error("找不到 script"); process.exit(2); }
const code = m[1];

const listeners = { window: {}, el: {} };

function mkEl(id) {
  const el = {
    id: id || "",
    _listeners: {},
    innerHTML: "",
    textContent: "",
    value: "",
    className: "",
    style: {},
    files: null,
    classList: {
      add: (c) => { el.className += " " + c; },
      remove: (c) => { el.className = el.className.replace(c, "").trim(); },
      contains: (c) => el.className.includes(c),
    },
    addEventListener: (t, fn) => {
      (el._listeners[t] = el._listeners[t] || []).push(fn);
      listeners.el[id + "|" + t] = (listeners.el[id + "|" + t] || 0) + 1;
    },
    appendChild: () => {},
    click: () => {},
    querySelector: () => mkEl(),
    querySelectorAll: () => [],
    scrollTop: 0,
    scrollHeight: 0,
  };
  return el;
}

const byId = {};
const ids = ["ver", "badges", "log", "banner", "stages", "drop", "file", "fileinfo",
  "start", "cancel", "savecfg", "cfgtip", "src_lang", "dst_lang", "asr_model",
  "asr_prompt", "concurrency", "chunk_size", "burn", "glossary", "extra_rules",
  "base_url", "model_name", "api_key", "resultcard", "downloads", "restip"];
ids.forEach((i) => { byId[i] = mkEl(i); });

const documentStub = {
  readyState: "complete",
  getElementById: (id) => byId[id] || null,
  querySelector: (sel) => {
    if (sel.startsWith("#")) return byId[sel.slice(1)] || mkEl();
    return mkEl();
  },
  querySelectorAll: () => [],
  createElement: () => mkEl(),
  addEventListener: (t, fn) => {
    (listeners.window["document:" + t] = listeners.window["document:" + t] || []).push(fn);
  },
};

const windowStub = {
  addEventListener: (t, fn) => {
    (listeners.window[t] = listeners.window[t] || []).push(fn);
  },
  location: { protocol: "http:", href: "http://127.0.0.1:8765/" },
};

const fetchReject = () => Promise.reject(new Error("模拟后端不可用"));

const sandbox = {
  window: windowStub,
  document: documentStub,
  location: windowStub.location,
  fetch: fetchReject,
  EventSource: function () { this.close = () => {}; },
  XMLHttpRequest: function () {
    this.open = () => {};
    this.setRequestHeader = () => {};
    this.send = () => {};
  },
  setTimeout: (fn) => 0,
  console,
  encodeURIComponent,
  JSON,
};

const vm = require("vm");
const ctx = vm.createContext(sandbox);
// 让脚本里的 window.addEventListener / document.* 指向桩
vm.runInContext("var window=this.window, document=this.document, location=this.location;", ctx);

let failed = 0;
function check(name, cond, extra) {
  console.log((cond ? "  PASS  " : "  FAIL  ") + name + (extra ? "  " + extra : ""));
  if (!cond) failed++;
}

try {
  vm.runInContext(code, ctx, { filename: "index.html<script>" });
} catch (e) {
  console.error("脚本执行抛异常：", e.message);
  failed++;
}

// 1) 拖拽监听
const dropCount = (listeners.window["drop"] || []).length;
check("window 注册了 drop 监听", dropCount >= 1, `count=${dropCount}`);
const overCount = (listeners.window["dragover"] || []).length;
check("window 注册了 dragover 监听", overCount >= 1, `count=${overCount}`);

// 2) 语言下拉有选项（内置兜底表）
["src_lang", "dst_lang"].forEach((id) => {
  const el = byId[id];
  const ok = el.innerHTML.includes("<option") && el.innerHTML.includes("日语");
  check(`#${id} 有语言选项`, ok, `len=${el.innerHTML.length}`);
});

// 3) 交互已绑定
check("#start 已绑定 click", (listeners.el["start|click"] || 0) >= 1);
check("#savecfg 已绑定 click", (listeners.el["savecfg|click"] || 0) >= 1);
check("#drop 已绑定 click", (listeners.el["drop|click"] || 0) >= 1);

// 4) 连不上后端时给出横幅提示（异步，等一个事件循环再断言）
setTimeout(() => {
  const b = byId["banner"];
  check("后端不可用时显示提示横幅",
        b.innerHTML.length > 0 && !b.className.includes("hidden"),
        `len=${b.innerHTML.length}`);
  console.log("\nRESULT:", failed === 0 ? "PASS" : `FAIL(${failed})`);
  process.exit(failed === 0 ? 0 : 1);
}, 30);
