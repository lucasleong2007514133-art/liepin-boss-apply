# 真实 DOM 选择器速查

> 全部来自 **2026-10-15 本机 Chrome 101 (ChromeCore) 实测**，不是抄的。
> 站点改版时，只改 `scripts/jobauto/` 里的对应 JS，然后跑 `probe` / `scan` 复核。

## 一、BOSS直聘

### 1.1 搜索页（列表）

URL：
```
https://www.zhipin.com/web/geek/jobs?query=<URL编码关键词>&city=<城市码>
  &experience=&degree=&industry=&scale=&stage=&position=&jobType=&salary=
  &multiBusinessDistrict=&multiSubway=&page=1&pageSize=30
```

**城市码**（实测）：东莞 `101281600`、广州 `101280100`、深圳 `101280600`、
佛山 `101280800`、江门 `101281100`、全国 `100010000`。

**卡片结构与实测选择器**：

```html
<li class="job-card-box">
  <div class="job-info">
    <div class="job-title clearfix">
      <a class="job-name" href="/job_detail/<JID>.html">多多买菜城市经理</a>
      <span class="job-salary">16-20K</span>      <!-- 字体混淆，需解码 -->
    </div>
    <ul class="tag-list"><li>3-5年</li><li>学历不限</li></ul>
  </div>
  <div class="job-card-footer">
    <a class="boss-info" href="/gongsi/...">
      <div class="boss-logo"><img ...></div>
      <span class="boss-name">拼多多集团-PDD</span>   <!-- ← 公司名在这 -->
    </a>
    <span class="company-location"> 东莞·虎门镇·北栅 </span> <!-- ← 地点，前后有空格 -->
  </div>
</li>
```

| 字段 | 选择器 | 备注 |
|---|---|---|
| 岗位名 | `a.job-name` | |
| 详情 URL | `a.job-name[href]` | jid 用 `job_detail/([^.]+)\.html` 提取 |
| 薪资 | `span.job-salary` | **必须 `decode_salary()`** |
| 公司 | `.boss-name` | ⚠️ 不要用 `.company-name`（不存在） |
| 地点 | `.company-location` | ⚠️ 不要用 `.job-area`（不存在）；要 `strip()` |
| 标签 | `ul.tag-list li` | |

**实测产出**：1 页 150 个卡片元素 → 去重后 **75 个唯一岗位**，`company`/`area`/`salary`/`tags`
**空缺 0/75**。

### 1.2 详情页

URL：`https://www.zhipin.com/job_detail/<JID>.html`

| 字段 | 选择器 | 实测值示例 |
|---|---|---|
| 岗位名 | `h1[title]` | `多多买菜城市经理` |
| 公司 | `.boss-info-attr` → 按 `·` 切第一段 | `拼多多集团-PDD·城市经理` |
| 公司（备选） | `.boss-info .boss-name`、`a[href*="/gongsi/"]` | |
| 薪资 | `.salary` | `16-20K` |
| 沟通按钮 | `a.btn-startchat, .btn-startchat` | 见下方文案规则 |
| JD 全文 | `document.body.innerText` 从「职位描述」/「岗位职责」起截 2000 字 | 实测 2000 字 |

> ⚠️ `.company-info` 在详情页是**岗位卡片**（含 `div.name` = 岗位名 + `span.badge` = 薪资），
> **不是公司**。别拿它当公司名。

### 1.3 沟通按钮文案规则（★ 关键）

| 文案 | 含义 | 点击后行为 |
|---|---|---|
| **立即沟通** | 无沟通记录 | 弹 modal：`textarea.input-area` + `.send-message` |
| **继续沟通** | 已有沟通记录 | **不弹窗**，跳 `/web/geek/chat?id=xxx` |

### 1.4 聊天页

URL：`https://www.zhipin.com/web/geek/chat`

| 元素 | 选择器 |
|---|---|
| 输入框（contenteditable） | `#chat-input` 或 `div.chat-input[contenteditable="true"]` |
| 发送按钮 | `.btn-send` |
| 消息气泡 | `.im-ui-txt`、`.dialog-con` |
| 会话列表项 | `li` + `.name-text`（HR 名）/ `.last-msg-text`（末条）/ `.message-status`（`[送达]`/`[已读]`） |

**打开会话必须派发完整鼠标事件序列**（Vue 列表不响应单纯 `.click()`）：
`pointerover → mouseover → pointerdown → mousedown → pointerup → mouseup → click`。
`driver/acts.py` 的 `cmd_click` 已实现。

### 1.5 薪资字体映射

PUA `U+E031..U+E03A` → `0..9`（`code - 0xE031 == 数字`）。

---

## 二、猎聘

> ⚠️ **只有公开页面（免登录）实测过。登录后的沟通 UI 未实测**，
> `chatui.py` 里 `LIEPIN` 表的选择器是**待验证的假设**，首次使用必须先 `probe`。

### 2.1 公开 SEO 列表页（免登录可抓）

URL 形态：`https://www.liepin.com/city-<城市slug>/zp<关键词slug>/`

**城市 slug**：东莞 `dongguan`、广州 `gz`、深圳 `shenzhen`、佛山 `foshan`、江门 `jiangmen`。
**关键词 slug**：城市经理 `chengshijingli`、配送经理 `peisongjingli`、
配送运营经理 `peisongyunyingjingli`、物流运营经理 `wuliuyunyingjingli`、
区域经理 `quyujingli`、即时配送 `jishipeisong`、运营经理 `yunyingjingli`。

卡片选择器：`.job-card-pc-container`（也可能 `li[class*="job-card"]`）

| 字段 | 选择器 |
|---|---|
| 详情链接 | `a[data-nick="job-detail-job-info"][data-jobid]` → `/job/<id>.shtml` |
| 岗位名 | `.job-title-box div[title]` |
| 薪资 | `span.job-salary` |
| 公司 | `span.company-name` |
| 城市 | `.job-dq-box span.ellipsis-1` |
| 标签 | `span.labels-tag` |

**免浏览器兜底通道**：`jobauto.py liepin-http --kw 城市经理 --city 东莞`
（走 `requests` + 轻量正则，无 requests 时会如实报缺口）。

### 2.2 详情页

`https://www.liepin.com/job/<id>.shtml`，JD 从「职位描述」/「职位介绍」起截。

---

## 三、改选择器的正确姿势

1. **先拿到真实 DOM**，不要猜：
   ```
   python "$S\jobauto.py" detail --site boss --url "<职位页URL>"
   ```
   或用 `driver.eval` / `driver.js` 打印 `outerHTML.slice(0, 1200)` 与元素 class 清单。
2. **改完立刻用真实页面复核**，看到实际条数与字段空缺率：
   ```
   python "$S\jobauto.py" scan --site boss --kw "城市经理" --city 东莞 -o jobs.json
   ```
3. **页面 JS 一律包 try/catch**（异常会被驱动吞掉，只表现为没有数据）：
   ```js
   try { /* 逻辑 */ } catch (e) { return JSON.stringify({__err: e.message}); }
   ```
4. **禁用 `Set` 与 `for...of`**（Chrome 101 上必抛异常），用数组 + `indexOf`。
