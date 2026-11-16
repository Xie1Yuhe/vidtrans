## 这个 PR 做了什么

<!-- 一两句话说明 -->

## 关联 issue

<!-- 例如：closes #12 -->

## 改动类型

- [ ] 修 bug
- [ ] 新功能
- [ ] 重构 / 性能
- [ ] 文档
- [ ] 界面 / 样式

## 自测情况

- [ ] `python -m compileall -q vidtrans app.py` 通过
- [ ] `node test/test_ui.js` 输出 `RESULT: PASS`
- [ ] 改了后端接口 → `python test/test_server.py` 通过
- [ ] 改了 `vidtrans/web/index.html` → 同步更新了 `test/test_ui.js` 的断言

## 两个必须注意的坑

- [ ] 如果动了 `run.bat`：保持 **纯 ASCII + CRLF**，里面不要写中文
      （cmd 用系统码页解析，UTF-8/LF 会把命令行截断）
- [ ] 如果新增了下载接口：文件名要按 RFC 5987 编码，不能直接塞中文进
      `Content-Disposition`

## 截图（改界面时）

<!-- 拖一张前后对比图进来 -->
