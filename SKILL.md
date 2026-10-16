---
name: liepin-boss-apply
description: 在 BOSS直聘 / 猎聘 上自动搜岗、按 JD 生成定制招呼话术、发起沟通与投递，并回消息中心核实送达。用原生 CDP 接管独立浏览器实例（零依赖、不动日常浏览器）。当用户说「帮我投简历」「在 BOSS直聘/猎聘 上发招呼语」「批量给 HR 发话术」「自动投递岗位」「抓招聘网站岗位并定制话术」时使用。含 9 条本机实测踩坑记录（含一次覆盖用户简历的事故复盘）。
whenToUse: 用户要求在 BOSS直聘 或 猎聘 上搜索岗位、生成并发送打招呼话术、批量投递、核实投递/送达状态；或需要抓取这两站的岗位数据（含 BOSS直聘 薪资字体反混淆）。仅查岗位信息、不涉及投递时也可用 scan 子命令。
metadata:
  version: 1.0.0
  verifiedOn: 2026-10-15
  engine: 原生 CDP（零第三方依赖，纯 Python 标准库）
  verifiedScope:
    boss: 登录后全流程实测通过（搜岗 / 详情 / 沟通状态探测 / 发话术 / 送达核实）
    liepin: 仅公开列表页与详情页只读抓取实测通过；登录后沟通 UI 未实测
  license: MIT
---

# 招聘平台投递与话术自动化（BOSS直聘 · 猎聘）

> **每一节都来自本机真实测试，包含 9 条踩坑记录和 1 次把用户简历页覆盖成空白的事故复盘。**
> **动手前先读第二节「硬约束」和第五节「协作纪律」。**

## 一、能做什么 / 不能做什么（别把没测过的说成能用）

| 能力 | BOSS直聘 | 猎聘 |
|---|---|---|
| 免登录抓岗位列表 | ✅ 实测 75 条/页，字段 0 空缺 | ✅ 公开 SEO 页（`requests` 通道） |
| 抓岗位详情 + JD 全文 | ✅ 实测 2000 字 JD | ✅ 公开详情页 |
| 薪资读取 | ✅ **已解字体反混淆**（`22-35K·16薪`） | ✅ 页面明文 |
| 探测「首次沟通 / 已有沟通」状态 | ✅ 实测可判别 | ⚠️ 选择器待实测 |
| 发起沟通 + 发定制话术 | ✅ **实测送达** | ⚠️ 未实测 |
| 回消息中心核实送达 | ✅ 实测读到 `[送达]`/`[已读]` | ⚠️ 未实测 |
| 上传/替换在线简历 | ✅ `upload` 命令可用（API 层） | ⚠️ 未实测 |

**缺口如实声明**：猎聘登录后的沟通 UI 选择器未在本机实测过，集中在 `chatui.py` 的
`LIEPIN` 表里。首次用猎聘投递前**必须先跑 `probe`** 看真实 DOM，再据此改选择器——
不要因为「BOSS 能跑」就假设猎聘也能跑。

## 二、★ 九条硬约束（每条都真踩过）

### 1. ★★★ 绝不用用户日常 profile 起调试实例
**事故**：曾用用户日常 profile + 调试端口启动，导致**用户正在编辑的猎聘简历页被覆盖成空白**。
**正确做法**：只用**独立 user-data-dir**（默认 `~/.jobauto/profile`），代价是首次要在新窗口
登录一次目标站点（登录态持久化），换来的是完全不动用户的日常浏览器。本技能的
`launch` 已强制走独立 profile。

### 2. ★★★ Chrome 101 上 `Set` 完全不可用（最容易静默失败）
本机浏览器内核是 **Chrome 101**。实测结果：

| 写法 | 结果 |
|---|---|
| `[...new Set(arr)]` | ❌ 抛异常 |
| `Array.from(new Set())` | ❌ 抛异常 |
| `new Set().forEach(...)` | ❌ 抛异常 |
| `for (const x of set)` | ❌ 抛异常 |
| `for (const x of nodeList)` | ❌ 抛异常 |
| `[...nodeList]` | ✅ 可用 |
| `Array.from(nodeList)` | ✅ 可用 |
| `Array.prototype.slice.call(nodeList)` | ✅ 可用 |

**纪律：页面 JS 里一律禁用 `Set` 和 `for...of`**，去重用「数组 + `indexOf`」。
本技能的 `platforms.py` / `chatui.py` / `verify.py` 已全部改掉。

### 3. ★★ `webctl2.py js` 是「函数体」语义，不是表达式
`acts.cmd_js` → `CDP.eval_async`，等价于 `new AsyncFunction(body)`。
- 传 IIFE 表达式 → 只求值成函数对象 → **输出恒为 `None`**
- 传函数体（含 `return`）→ 正常

`driver.py` 的 `js()` 已做兼容，但**判定必须保守**：
只有当脚本**以 `(` / `async` / `!function` 开头**时才包 `return (...)`。
绝不能因为「文本里没有 `return` 字样」就去包裹 —— 函数体若有前置语句
（`const a=[1]; return ...`），会变成 `return (const a=[1]; return ...)`，
**直接 SyntaxError**，而 webctl2 只把异常打到 stderr，调用方看到的是 `None`，极难排查。

### 4. ★★ 页面 JS 异常会被「静默吞掉」，返回值只会是 `None`
webctl2 遇到页面 JS 异常时：**打 stderr + exit 1**，stdout 为空。
驱动把 `null`/`undefined` 打成字符串 `"None"`。若不处理，上层会拿到一个**真值字符串
`"None"`**，走进「假成功」分支。`driver._try_json()` 已把 `"None"`/`"null"`/`"undefined"`
显式转成 Python `None`，`js()` 也已把 stderr 里的异常摘要带回（`{"__js_error__": ...}`）。
**排查思路：页面数据抓不到时，先给 JS 包 `try { ... } catch (e) { return 'ERR:'+e.message; }`，
不要靠猜选择器。**

### 5. ★★ 沟通按钮文案随「沟通状态」变化 —— 必须每次先探测
| 按钮文案 | 触发条件 | 实际行为 |
|---|---|---|
| **立即沟通** | 与该招聘方**无**沟通记录 | 弹出 modal（`textarea.input-area` + `.send-message`） |
| **继续沟通** | 已有沟通记录 | **不弹窗**，直接跳 `/web/geek/chat?id=xxx` |

**事故**：曾以为「弹窗会自动关闭」，实际是对方已是「继续沟通」状态、**根本没有弹窗**，
我却在等 `textarea` → 必然超时。
**纪律**：动手前先 `probe` 拿 `state`（`first_contact` / `has_history` / `in_chat_page` / …），
按状态分支。`chatui.apply_via_detail()` 已实现这个状态机。

### 6. ★ BOSS直聘 薪资是字体混淆的 —— 需解码
薪资数字被映射到自定义字体的私用区（PUA）字符，直接读是空白/方框。
**已解出的映射（U+E031..U+E03A → 0..9）**：
```
\ue031=0  \ue032=1  \ue033=2  \ue034=3  \ue035=4
\ue036=5  \ue037=6  \ue038=7  \ue039=8  \ue03a=9
```
即 `code - 0xE031 == 数字`。
**重建映射的方法**（字体换了要用）：从 `performance.getEntriesByType('resource')` 拿字体
URL → 下载 → `fontTools` 取 cmap → `PIL` 把每个字形渲染成图片 → 与 Arial 的 0-9
**逐个像素比对**（不能靠顺序猜）。

### 7. ★ Windows 控制台默认 GBK，打印 PUA 字符会崩
`UnicodeEncodeError: 'gbk' codec can't encode character '\ue033'`。
**解法**：脚本启动时 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，
并设 `PYTHONIOENCODING=utf-8`。本技能 CLI 已内置。

### 8. ★ 长流程会让浏览器崩成 about:blank
同一页面连续操作约 **20 次**后标签页会跳 `about:blank`。
**纪律**：**每批 10–20 条**，每批发完落盘一次（`sender.py` 已实现断点续传）；
崩了执行 `nav <目标页> --index N` 即可恢复，已保存数据不受影响。

### 9. ★ 常驻服务会吞掉启动参数 + 进程清理纪律
- `ChromeCoreSvr.exe` 常驻时会吞掉 `--remote-debugging-port` 参数 → 端口起不来。
  该进程**权限高，`Stop-Process` 会 `Access is denied`** → **不要硬杀**，让用户从托盘
  右键「退出」。
- **清理进程只能用自己记录的 PID + 命令行核验**：只杀命令行含
  `remote-debugging-port=<自己的端口>` 且**不含 `--type=`** 的主进程。
  **禁止**用「最近 N 分钟启动」这类时间窗口判断（曾误杀用户浏览器）。

## 三、快速开始

```powershell
$S = "$env:USERPROFILE\.dsh\skills\liepin-boss-apply\scripts"
$env:PYTHONIOENCODING = "utf-8"

# 0) 环境自检（先看能不能干活）
python "$S\jobauto.py" doctor

# 1) 启动独立可控制浏览器（首次要在新窗口登录一次 BOSS直聘 / 猎聘）
python "$S\jobauto.py" launch
python "$S\jobauto.py" login --site boss

# 2) 看清标签页，再决定动哪个 index
python "$S\jobauto.py" tabs

# 3) 抓岗位（只读）
python "$S\jobauto.py" scan --site boss --kw "城市经理" --city 东莞 --pages 2 -o jobs.json

# 4) 准备自己的「事实库」（必须换掉示例占位符，否则话术里会出现 <你的名字>）
python "$S\jobauto.py" draft --jobs jobs.json --facts my_facts.json -o messages.json

# 5) 先 dry-run 看清要发什么（默认就是 dry-run）
python "$S\jobauto.py" send --site boss --messages messages.json --batch 15

# 6) 确认无误后真发（必须显式 --execute）
python "$S\jobauto.py" send --site boss --messages messages.json --batch 15 --execute --verify-each

# 7) 回消息中心独立核实
python "$S\jobauto.py" inbox --site boss -o inbox.json
```

### 命令表

| 命令 | 作用 | 是否改动线上 |
|---|---|---|
| `doctor` | 环境自检（端口 / 浏览器 / 常驻服务） | 只读 |
| `launch` | 启动独立 profile 的可控制浏览器 | 只读 |
| `tabs` | 列标签页（index/title/url）**第一步永远先跑** | 只读 |
| `login` | 打开登录页 | 只读 |
| `probe` | 探测当前页状态（按钮文案 / 输入框 / 沟通状态） | 只读 |
| `scan` | 搜岗抓列表（含薪资解码） | 只读 |
| `detail` | 抓岗位详情 + JD 全文 + 可见按钮 | 只读 |
| `decode` | 薪资 PUA 字符解码 | 只读 |
| `draft` | 由 jobs + 事实库生成发送清单 | 只写本地 |
| `apply` | 在单个岗位页发起沟通并发送 | **默认 dry-run** |
| `send` | 批量发送（分批 + 落盘 + 可选逐条核实） | **默认 dry-run** |
| `inbox` | 拉会话列表（HR / 末条消息 / 送达状态） | 只读 |
| `verify` | 按清单逐条核实送达 | 只读 |
| `liepin-http` | 不走浏览器的猎聘公开页抓取 | 只读 |

> **所有发送类命令默认 dry-run，必须显式加 `--execute`。** 这是有意为之：
> 投递/发消息是不可逆动作。

## 四、话术怎么写才有效（实测）

一条**成功送达且被 HR 回复**的 BOSS直聘 话术结构（实测 289 字）：

```
<称呼>您好，我是<名字>，<年限>年<行业>经验。看到贵司在招<岗位名>，我的匹配点：
1）<JD 里的关键词>：<我的可验证事实，带数字>
2）...
3）...
4）...
<收尾一句：我在本地 / 期待详聊>
```

**四条纪律**：
1. **必须定制**：HR 每天收到大量模板招呼，「15年经验求关注」等于没写。
   话术里要出现**该 JD 的关键词**，形成「我认真看过」的信号。
2. **带数字**：`单均成本由 6.2 元降至 5.3 元（-14.5%）` 远胜「擅长成本控制」。
3. **3–4 条对应点**最好（`messages.py` 默认上限 4 条）：超过 4 条像刷屏，少于 3 条像海投。
4. **有短板就主动说明**，别硬吹。示例里有一句
   「我直接管理的是 7 名城市经理 + 1700 名骑手的运力体系…与贵岗要求的 50 人以上
   前端团队规模相当但组织形态不同，这点我们可以沟通」——**坦诚反而更容易拿到回复**。

`messages.py` 的 `PATTERNS` 表把 JD 关键词映射到事实库字段（成本/骑手/团队/多城市/
数据/代理商/0-1/现场）。**记得按自己的履历改这张表和事实库**。

事实库格式（`--facts my_facts.json`）：
```json
{
  "name": "张三",
  "years": "8年城市配送管理经验",
  "current": "现任某体系区域经理",
  "scope": "直管5个城市",
  "scale": "管理1200+骑手、覆盖30+站点",
  "team": "直接管理城市经理7人，培养出2名城市经理",
  "cost": "主导单均成本由6.2元降至5.3元（-14.5%）",
  "rescue": "两个清退预警城市进驻3个月做到商评第一",
  "data": "用时段/商圈/运力线多维数据定位问题出改善方案",
  "proxy": "负责代理商准入、考核与结算",
  "zero2one": "项目华南负责人，一年做到深圳85点/广州50点",
  "site": "直营网点现场运营与营运质量管控"
}
```
> 没提供真实事实库时，生成的话术会带 `<你的名字>` 这类占位符，且清单里
> `facts_is_example: true` 会如实标记 —— **不要带着占位符发送**。

## 五、★ 协作纪律（AI 执行时必须遵守）

1. **不可逆动作先确认**：投递、发消息、提交表单、删除 —— 动手前讲清楚并拿到明确同意。
   本技能默认 dry-run 就是为了强制这一步。
2. **先只读**：`text` / `count` / `cards` / `read` / `probe` 看清页面，再决定操作。
3. **先探测状态再动手**：按钮文案、登录态、是否已有沟通记录（见硬约束 5）。
4. **一次一步、回读校验**：填完 `eval` 回读，再点提交；发送后去**消息中心**核实，
   **不要靠页面提示判断真假**（实测靠这一步抓到过假成功）。
5. **改线上资料先找试验田**（如新建测试简历），别直接改正在用的简历。
6. **分批**：每批 10–20 条，不要一口气 50 条（浏览器会崩）。
7. **限速做人**：不要把频率拉到真人不可能达到的水平。平台风控、账号封禁风险自负，
   请遵守各平台用户协议。
8. **本机网络**：github.com 可达；npm 用镜像 `https://registry.npmmirror.com`。

## 六、目录结构

```
~/.dsh/skills/liepin-boss-apply/
├── SKILL.md                   # 本文件
├── references/
│   ├── selectors.md           # 真实 DOM 选择器速查（含实测依据）
│   ├── troubleshooting.md     # 故障速查表
│   └── facts.example.json     # 事实库示例
└── scripts/
    ├── jobauto.py             # ★ CLI 入口（所有命令）
    ├── 启动_可控制浏览器.bat    # 手动启动（等价于 jobauto.py launch）
    ├── driver/                # 原生 CDP 驱动（纯标准库，零依赖）
    │   ├── cdp.py             # 手写 WebSocket + CDP 客户端
    │   ├── acts.py            # CDP 动作库（JS 直操 DOM + 完整鼠标事件序列）
    │   └── webctl2.py         # 底层 CLI
    └── jobauto/
        ├── launcher.py        # 启动/自检独立浏览器
        ├── driver.py          # webctl2 封装（js 语义兼容 + 异常带回）
        ├── chatui.py          # 沟通状态机 + 发送三重兜底 + 回读校验
        ├── platforms.py       # 搜岗 / 列表 / 详情（Chrome 101 兼容）
        ├── fontmap.py         # BOSS直聘 薪资字体反混淆
        ├── messages.py        # 话术引擎（JD → 定制招呼语）
        ├── sender.py          # 分批发送 + 断点续传
        └── verify.py          # 送达核实 + 收件箱盘点
```

## 七、为什么不用 Playwright

Playwright 的 `click/fill` 走 **actionability 检查**（可见性+稳定性），依赖
`element.checkVisibility()`（**Chrome 105+**）。本机内核是 101 → 直接 `TypeError` → 超时。
原生 CDP 用 `Runtime.evaluate` 执行 JS，**不经过任何 actionability 检查**，从根本上绕开。
实测对比：同一套 BOSS直聘 发话术流程，**原生 CDP 一次成功；Playwright 失败 4 次**。

## 八、合规与免责

- 本技能是**效率工具**，不改变平台规则。使用者须自行遵守 BOSS直聘 / 猎聘 的
  用户协议、robots 与投放频率限制。
- 自动化操作存在**账号受限风险**，请自行评估并控制频率。
- 话术中的经历与数字**必须真实**，编造经历可能导致录用后被解除劳动关系。
- 本工具只读抓取公开页面 + 在你已登录的浏览器里代你操作，**不绕过任何登录或验证码**；
  遇到验证码请人工处理，不要试图规避。
- MIT License。
