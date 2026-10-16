# 故障速查表

> 全部为实测现象。排查顺序：先 `doctor`，再 `tabs`，再给页面 JS 包 try/catch。

## 一、连不上 / 起不来

| 现象 | 原因 | 解法 |
|---|---|---|
| `连接调试端口 9222 失败` | 端口没起 / 被常驻服务吞参数 | 完全退出 ChromeCore（含托盘）后重跑 `launch` |
| `doctor` 报 `hijackers_running: ChromeCoreSvr.exe` | 常驻服务会吞掉 `--remote-debugging-port` | **不要 Stop-Process**（Access denied），让用户托盘右键「退出」 |
| `端口 9222 被别的程序占用` | 有别的进程占了端口 | 换 `--port 9223` |
| 找不到浏览器 | 路径不在候选表里 | `--browser "<路径>"` 或设 `JOBAUTO_BROWSER` |
| 启动后标签页是空的 | 新 profile 首次启动 | 正常，`launch` 之后用 `login` / `goto` 开页 |

## 二、抓不到数据（最高频，且最容易误判）

| 现象 | 原因 | 解法 |
|---|---|---|
| `js` 返回 `None`（无任何报错） | **页面 JS 抛了异常，错误只在 stderr** | 给 JS 包 `try{...}catch(e){return 'ERR:'+e.message}`，别猜选择器 |
| 抓取脚本返回 `None` / `{__js_error__:...}` | 同上 | 看 `__js_error__` 里的异常摘要 |
| `[...new Set(arr)]` 那行之后全崩 | **Chrome 101 上 `Set` 不可用** | 换「数组 + `indexOf`」；`for...of` 同理 |
| `SyntaxError: Unexpected token 'const'` | `js` 是**函数体**语义，却被包成了表达式 | 确认脚本以 `(` / `async` 开头才需要包 `return (...)` |
| 列表解析失败但页面明显有内容 | 选择器随站点改版 | 按 `references/selectors.md` 第三节重新探 DOM |
| 公司/地点字段全空 | 用错选择器（BOSS 列表页是 `.boss-name` / `.company-location`） | 见 selectors.md |
| 薪资显示空白或方框 | BOSS直聘 字体混淆 | 用 `decode` 命令 / `fontmap.decode_salary()` |
| 只抓到 150 条里的一半 | 卡片有重复（同一岗位多卡片） | 按 `jid` 去重（`platforms.search` 已做） |

## 三、发送相关

| 现象 | 原因 | 解法 |
|---|---|---|
| `fill` 超时 / 找不到 `textarea` | **该页面本来就没弹窗**（对方已是「继续沟通」状态） | 先 `probe` 看 `state`；`has_history` 会直接跳聊天页 |
| 点了沟通按钮既没弹窗也没跳页 | 按钮文案变了 / 选择器失效 | `probe` 打印 `chat_btn_labels` 人工看 |
| 填入成功但发送后输入框还有内容 | 发送按钮被 disable / 点错按钮 | 回读 `input_left`，非 0 就人工确认后再发 |
| 发送动作执行了但没校验到 | 可能是假成功 | 去 `inbox` 看会话列表末条消息，**别信页面提示** |
| 担心重复发送 | 兜底链在未校验时继续尝试下一档 | `send_message` 已改为「未校验即收手并如实上报」，不会自动重发 |

## 四、稳定性 / 进程

| 现象 | 原因 | 解法 |
|---|---|---|
| 标签页变成 `about:blank` | 同页面连续操作 ~20 次后浏览器崩 | `nav <目标页> --index N` 恢复；**每批 10–20 条** |
| 用户日常浏览器被影响 | 用了日常 profile | **必须**用独立 user-data-dir（`launch` 已强制） |
| 误杀用户浏览器 | 用「最近 N 分钟启动」判断进程 | 只杀命令行含 `remote-debugging-port=<自己端口>` 且不含 `--type=` 的进程 |

## 五、编码

| 现象 | 原因 | 解法 |
|---|---|---|
| `UnicodeEncodeError: 'gbk' codec can't encode '\ue033'` | Windows 控制台默认 GBK，PUA 字符打不出 | `sys.stdout.reconfigure(encoding="utf-8")` + `PYTHONIOENCODING=utf-8` |
| 中文乱码 | 同上 | 同上；`.bat` 里加 `chcp 65001` |

## 六、Playwright 相关（本技能不用，但会撞上）

| 现象 | 原因 | 解法 |
|---|---|---|
| `element.checkVisibility is not a function` | 用了新版 Playwright，内核只有 Chrome 101 | 改用原生 CDP（本技能首选路径） |
| `goto` 在 ChromeCore 上超时 | Playwright 导航在该内核不稳 | 用 `nav`（原生 CDP） |
| `click`/`fill` 在重度 SPA 上频繁超时 | actionability 检查依赖 Chrome 105+ | 同上 |
