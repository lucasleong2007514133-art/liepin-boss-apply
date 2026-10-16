# 简历投递话术自动化 · BOSS直聘 / 猎聘

一个 **DSH / Claude 风格的 Agent Skill**：在 BOSS直聘、猎聘上自动**搜岗 → 读 JD →
生成定制招呼话术 → 发起沟通 → 回消息中心核实送达**。

用**原生 CDP** 接管一个**独立 profile** 的浏览器实例 —— 纯 Python 标准库，**零第三方依赖**，
**完全不碰你日常在用的浏览器**。

> 这不是"群发助手"。它是把「一份简历 + 一条 JD → 一条让 HR 愿意回的招呼语」这件事
> 做成可复用流程，并强制你在发送前确认、发送后核实。

---

## 为什么值得用：这些都是实测踩出来的

写这个技能花了整整一轮真实调试，**每个坑都留下了记录**。如果你自己写浏览器自动化，
下面这几条大概率正在等着你（尤其第一条）：

| # | 坑 | 后果 |
|---|---|---|
| 1 | **Chrome 101 上 `Set` 完全不可用** —— `[...new Set()]`、`Array.from(new Set())`、`for...of Set`、`Set.forEach` 全部抛异常 | 抓取静默返回空，**没有任何报错**，你会去怀疑选择器，方向全错 |
| 2 | 页面 JS 异常被驱动**吞掉**，返回值只有 `None`（而且串成了字符串 `"None"`，是**真值**） | 走进"假成功"分支；不包 `try/catch` 根本查不出来 |
| 3 | `webctl2.py js` 是**函数体**语义（`new AsyncFunction(body)`），不是表达式 | 传 IIFE 进去 → 输出**恒为 `None`** |
| 4 | 沟通按钮文案随状态变：**「立即沟通」弹窗 / 「继续沟通」不弹窗直接跳聊天页** | 死等 `textarea` → **必然超时**（曾误判成"弹窗自动关闭"） |
| 5 | BOSS直聘 薪资是**字体私用区字符混淆**的 | 薪资读出来是空白/方框 |
| 6 | 用**日常 profile** 起调试实例 | ⚠️ **把用户正在编辑的猎聘简历页覆盖成了空白**——本技能用独立 profile 从根上避免 |
| 7 | 同一页面连续操作 ~20 次后浏览器崩成 `about:blank` | 长流程跑一半全废；必须分批 + 落盘 |
| 8 | Windows 控制台默认 GBK，打印 PUA 字符直接 `UnicodeEncodeError` | 脚本崩在输出上，而不是逻辑上 |
| 9 | 常驻服务吞掉 `--remote-debugging-port`，且该进程**杀不掉**（Access denied） | 端口永远起不来；正确做法是让用户从托盘退出 |

**实测战绩**：BOSS直聘 完整流程（搜岗 75 条 / 详情 2000 字 JD / 沟通状态判别 / 发话术 /
送达核实 28 个会话）**全部跑通**。同一套发话术流程，**原生 CDP 一次成功，Playwright 失败 4 次**
（因为 `click/fill` 的 actionability 检查依赖 `element.checkVisibility()`，需要 Chrome 105+）。

---

## 能力与边界（不吹）

| 能力 | BOSS直聘 | 猎聘 |
|---|---|---|
| 免登录抓岗位列表 | ✅ 实测 75 条/页，字段空缺 0/75 | ✅ 公开 SEO 页 |
| 抓详情 + JD 全文 | ✅ 实测 2000 字 | ✅ 公开详情页 |
| 薪资读取 | ✅ **已解字体混淆**（`22-35K·16薪`） | ✅ 明文 |
| 判别「首次沟通 / 已有沟通」 | ✅ | ⚠️ 选择器待实测 |
| 发起沟通 + 发定制话术 | ✅ **实测送达** | ⚠️ **未实测** |
| 回消息中心核实送达 | ✅ 实测读到 `[送达]`/`[已读]` | ⚠️ 未实测 |

**猎聘登录后的沟通 UI 我没有实测过**，选择器作为待验证假设放在 `chatui.py` 的 `LIEPIN` 表里。
首次用猎聘投递前必须先 `probe` 看真实 DOM。诚实比好看重要。

---

## 安装

作为 Agent Skill 使用（DSH / Claude Code 等）：

```bash
git clone https://github.com/lucasleong2007514133-art/liepin-boss-apply.git \
  ~/.dsh/skills/liepin-boss-apply
```

或通过 skills.sh 生态（仓库公开后）：

```bash
npx -y skills@latest add lucasleong2007514133-art/liepin-boss-apply
```

无需 `pip install` / `npm install` —— **纯标准库**。

## 快速开始

```powershell
$S = "$env:USERPROFILE\.dsh\skills\liepin-boss-apply\scripts"
$env:PYTHONIOENCODING = "utf-8"

python "$S\jobauto.py" doctor          # 1) 环境自检
python "$S\jobauto.py" launch          # 2) 起独立浏览器（首次登录一次即可）
python "$S\jobauto.py" tabs            # 3) 先看清标签页

python "$S\jobauto.py" scan  --site boss --kw "城市经理" --city 东莞 -o jobs.json
python "$S\jobauto.py" draft --jobs jobs.json --facts references\facts.example.json -o messages.json
python "$S\jobauto.py" send  --site boss --messages messages.json --batch 15              # dry-run
python "$S\jobauto.py" send  --site boss --messages messages.json --batch 15 --execute --verify-each
python "$S\jobauto.py" inbox --site boss -o inbox.json                                    # 独立核实
```

**所有发送命令默认 dry-run，必须显式 `--execute`。** 投递是人的事，工具只负责省时间。

## 命令表

> 想把仓库推上 GitHub / 发布到 skills.sh，见 [PUSH.md](PUSH.md)（含三种推送方式）。

| 命令 | 作用 | 触碰线上 |
|---|---|---|
| `doctor` / `launch` / `tabs` / `login` | 环境与浏览器 | 只读 |
| `probe` | 探测页面状态（按钮文案/输入框/沟通状态） | 只读 |
| `scan` / `detail` / `decode` | 搜岗、详情、薪资解码 | 只读 |
| `draft` | 生成发送清单 | 只写本地 |
| `apply` / `send` | 发起沟通、批量发送 | **默认 dry-run** |
| `inbox` / `verify` | 送达核实 | 只读 |
| `liepin-http` | 免浏览器抓猎聘公开页 | 只读 |

## 话术引擎

一条**成功送达且被 HR 回复**的话术结构（实测 289 字）：

```
<称呼>您好，我是<名字>，<年限>年<行业>经验。看到贵司在招<岗位名>，我的匹配点：
1）<JD 关键词>：<可验证事实，带数字>
2）… 3）… 4）…
<收尾>
```

四条纪律：**必须按 JD 定制**（出现 JD 关键词）、**必须带数字**、**3–4 条对应点**、
**短板主动说明别硬吹**。`messages.py` 的 `PATTERNS` 表把 JD 关键词映射到事实库字段，
按自己的履历改它和 `references/facts.example.json` 即可。

## 目录

```
SKILL.md                       # Agent 指令主体（9 条硬约束 + 5 条协作纪律）
references/
  selectors.md                 # 真实 DOM 选择器（含实测依据与 HTML 结构）
  troubleshooting.md           # 故障速查表
  facts.example.json           # 事实库模板
scripts/
  jobauto.py                   # CLI 入口
  driver/                      # 原生 CDP 驱动（cdp.py / acts.py / webctl2.py）
  jobauto/                     # launcher / driver / chatui / platforms
                               # fontmap / messages / sender / verify
```

## 合规与免责

本工具是**效率工具，不改变平台规则**。请遵守 BOSS直聘 / 猎聘 的用户协议与投放频率限制；
自动化操作存在**账号受限风险**，请自行评估。工具**只读抓取公开页面**，
并在**你已登录的浏览器**里代你操作，**不绕过任何登录或验证码** —— 遇到验证码请人工处理。
话术中的经历与数字**必须真实**。

## License

MIT
