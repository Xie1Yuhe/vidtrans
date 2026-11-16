// 用最小 DOM 桩执行 vidtrans/web/index.html 里的脚本，验证：
//   1) window 上注册了 drop/dragover 监听（拖文件不会被浏览器直接打开）
//   2) 语言下拉在内置兜底表下也有选项（不会「点了没反应」）
//   3) 关键按钮都绑定了事件（开始 / 保存 / 安装 ffmpeg / 测试 API / 拖拽区）
//   4) 连不上后端时给出横幅提示
// 不需要浏览器、不需要网络。
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(
  path.join(__dirname, "..", "vidtrans", "web", "index.html"), "utf8");
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error("找不到 script"); process.exit(2); }
const code = m[1];

const winListeners = {};
const idListeners = {};
let failed = 0;

function check(name, cond, extra) {
  console.log((cond ? "  PASS  " : "  FAIL  ") + name + (extra ? "  " + extra : ""));
  if (!cond) failed++;
}

function mkEl(id) {
  const el = {
    id: id || "",
    innerHTML: "",
    textContent: "",
    value: "",
    className: "",
    style: {},
    files: null,
    options: [],
    selectedIndex: 0,
    checked: true,
    disabled: false,
    scrollTop: 0,
    scrollHeight: 0,
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); el.className = [...this._s].join(" "); },
      remove(c) { this._s.delete(c); el.className = [...this._s].join(" "); },
      contains(c) { return this._s.has(c); },
      toggle(c, on) { if (on === undefined) on = !this._s.has(c); on ? this.add(c) : this.remove(c); },
    },
    addEventListener(t, fn) {
      (idListeners[(id || "") + "|" + t] = idListeners[(id || "") + "|" + t] || []).push(fn);
    },
    appendChild() {},
    click() {},
    focus() {},
    scrollIntoView() {},
    querySelector() { return mkEl(); },
    querySelectorAll() { return []; },
  };
  return el;
}

const els = {};
function byId(id) {
  if (!els[id]) els[id] = mkEl(id);
  return els[id];
}

// 从真实 HTML 里预置初始状态（class / disabled / checked / value），
// 否则桩测的是桩本身，而不是页面真实初始态。
(function seedFromHtml() {
  const tagRe = /<([a-zA-Z][\w-]*)([^>]*)>/g;
  let mm;
  while ((mm = tagRe.exec(html))) {
    const attrs = mm[2] || "";
    const idm = attrs.match(/\bid="([^"]+)"/);
    if (!idm) continue;
    const e = byId(idm[1]);
    const cm = attrs.match(/\bclass="([^"]*)"/);
    if (cm) cm[1].split(/\s+/).filter(Boolean).forEach((c) => e.classList.add(c));
    if (/(^|\s)disabled(\s|=|$)/.test(attrs)) e.disabled = true;
    if (/(^|\s)checked(\s|=|$)/.test(attrs)) e.checked = true;
    const vm2 = attrs.match(/\bvalue="([^"]*)"/);
    if (vm2) e.value = vm2[1];
  }
})();

const documentStub = {
  readyState: "complete",
  getElementById: byId,
  querySelector(sel) {
    if (sel && sel[0] === "#") return byId(sel.slice(1));
    return mkEl();
  },
  querySelectorAll() { return []; },
  createElement() { return mkEl(); },
  addEventListener(t, fn) {
    (winListeners["document:" + t] = winListeners["document:" + t] || []).push(fn);
  },
};

const windowStub = {
  addEventListener(t, fn) { (winListeners[t] = winListeners[t] || []).push(fn); },
  location: { protocol: "http:", href: "http://127.0.0.1:8765/" },
};

const localStorageStub = {
  _d: {},
  getItem(k) { return k in this._d ? this._d[k] : null; },
  setItem(k, v) { this._d[k] = String(v); },
};

const sandbox = {
  window: windowStub,
  document: documentStub,
  location: windowStub.location,
  localStorage: localStorageStub,
  fetch: () => Promise.reject(new Error("模拟后端不可用")),
  EventSource: function () { this.close = () => {}; },
  XMLHttpRequest: function () {
    this.open = () => {};
    this.setRequestHeader = () => {};
    this.send = () => {};
  },
  setTimeout: (fn) => 0,
  clearTimeout: () => {},
  Image: function () { this.src = ""; },
  console,
  encodeURIComponent,
  JSON,
};

const vm = require("vm");
const ctx = vm.createContext(sandbox);
vm.runInContext(
  "var window=this.window, document=this.document, location=this.location," +
  " localStorage=this.localStorage, Image=this.Image;", ctx);

try {
  vm.runInContext(code, ctx, { filename: "vidtrans/web/index.html<script>" });
} catch (e) {
  console.error("脚本执行抛异常：", e.message);
  failed++;
}

// 1) 拖拽拦截
check("window 注册了 drop 监听", (winListeners["drop"] || []).length >= 1,
      "count=" + (winListeners["drop"] || []).length);
check("window 注册了 dragover 监听", (winListeners["dragover"] || []).length >= 1);
check("window 注册了 dragenter 监听", (winListeners["dragenter"] || []).length >= 1);

// 2) 语言下拉有兜底选项
["src_lang", "dst_lang"].forEach((id) => {
  const h = byId(id).innerHTML;
  check("#" + id + " 有语言选项", h.indexOf("<option") >= 0 && h.indexOf("日语") >= 0,
        "len=" + h.length);
});

// 3) 关键交互已绑定
[
  ["start", "click"], ["savecfg", "click"], ["drop", "click"],
  ["cancel", "click"], ["btnToggle", "click"], ["btnSwap", "click"],
  ["btnTestApi", "click"], ["btnInstallFf", "click"], ["btnReset", "click"],
  ["autoStart", "change"], ["file", "change"],
].forEach(([id, t]) => {
  check("#" + id + " 绑定 " + t, (idListeners[id + "|" + t] || []).length >= 1);
});

// 4) 初始状态
check("设置面板默认收起", byId("settingsBody").classList.contains("hidden"));
check("进度阶段已渲染", byId("stages").innerHTML.indexOf("stage") >= 0);
check("服务商预设已填充", byId("preset").innerHTML.indexOf("<option") >= 0);
check("开始按钮初始禁用", byId("start").disabled !== false);

// 5) 连不上后端时要给提示（异步）
setTimeout(() => {
  const b = byId("banner");
  check("后端不可用时显示提示横幅",
        b.innerHTML.length > 0 && !b.classList.contains("hidden"),
        "len=" + b.innerHTML.length);
  console.log("\nRESULT:", failed === 0 ? "PASS" : "FAIL(" + failed + ")");
  process.exit(failed === 0 ? 0 : 1);
}, 30);
