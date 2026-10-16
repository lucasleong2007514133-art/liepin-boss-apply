# 发布清单（已发布 ✅）

## 当前状态

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/lucasleong2007514133-art/liepin-boss-apply |
| 可见性 | **Public** ✅（已匿名校验可读） |
| 默认分支 | `main` |
| 最后提交 | `044074e`（本地 HEAD == origin/main，完全同步） |
| 文件数 | 22（远端 blob SHA 与本地逐文件一致，0 差异） |
| 安装验证 | ✅ 实测 `npx skills add lucasleong2007514133-art/liepin-boss-apply -g -y` 成功装到 `~\.agents\skills\` |

别人这样安装：

```powershell
npx -y skills@latest add lucasleong2007514133-art/liepin-boss-apply -g -y
```

`skills.sh` **搜索索引**（`npx skills find`）目前还查不到本仓库 —— 该索引按安装量/热度
聚合，新仓库需要时间和安装量积累，**没有人工提交入口**。直接按上面命令安装
（或直接给仓库链接）始终可用，不依赖索引。

---

## ★ 这台机器上的一个硬约束：`github.com:443` 不可靠

实测结果：

| 端点 | 状态 |
|---|---|
| `github.com:443` | ❌ **经常超时**（解析到 `20.205.243.166`） |
| `api.github.com` | ✅ 稳定 200 |
| `codeload.github.com` / `objects.githubusercontent.com` | ✅ 通（发布包能下载） |

**后果**：`gh auth login`（设备码流程最后要 POST `github.com/login/oauth/access_token`）
**必然失败**；`git push` 时通时断。

**所以本次发布走的是 Git Data API**（只依赖 `api.github.com`）：
`blob → tree → commit → ref`，等价于一次完整推送，但完全绕开 `github.com`。
工具在 `_tools/ghpub.py`（`publish` / `verify` 两个子命令，token 只从环境变量读、不落盘）。

```powershell
$env:GH_TOKEN = "<你的 PAT>"
python "_tools\ghpub.py" publish lucasleong2007514133-art liepin-boss-apply
python "_tools\ghpub.py" verify  lucasleong2007514133-art liepin-boss-apply
```

### 踩到的两个 API 坑（已修进脚本）

1. **空仓库不能用 Git Data API**：对没有任何提交的仓库创建 blob 或 tree，
   GitHub 一律返回 `409 Git Repository is empty`。
   → 出口是用 **Contents API**（`PUT /contents/<path>`）先创建第一个文件，
   它会顺带产生首个提交，之后 Git Data API 才可用。脚本用 `README.md` 作首个文件。
2. **中文文件名**：`git ls-files` 默认把 `scripts/启动_可控制浏览器.bat`
   输出成八进制转义（`"scripts/\345\220\257..."`），拿它去 `git show` 必然失败。
   → 必须用 `git -c core.quotepath=false ls-files -z`（NUL 分隔且不转义）。

---

## 以后要更新技能内容

```powershell
cd "$env:USERPROFILE\.dsh\skills\liepin-boss-apply"
# 改完文件后
git add -A; git commit -m "feat: ..."

# 方式一（github.com 通的时候）
git push origin main

# 方式二（github.com 不通时走 API —— 推荐，稳定）
$env:GH_TOKEN = "<你的 PAT>"
python "D:\安装软件\deepseek harness\工作文件夹\_tools\ghpub.py" publish lucasleong2007514133-art liepin-boss-apply
python "D:\安装软件\deepseek harness\工作文件夹\_tools\ghpub.py" verify  lucasleong2007514133-art liepin-boss-apply
```

> 方式二会上传**当前 `HEAD` 的完整内容**。本地与远端历史已合并统一
> （远端含一个 `chore: 初始化仓库` 的引导提交），正常快进即可。

---

## ⚠️ 安全：请吊销本次使用的 token

发布用的 PAT 是在对话里明文传递的，**建议立即吊销**：

👉 https://github.com/settings/tokens

已确认无残留：技能目录与工具目录全盘扫描无命中、git remote URL 不含凭证、
无 `.git-credentials`、无 credential helper 持久化。但对话记录本身可能留存，
**吊销是唯一彻底的做法**。以后需要更新时再生成新 token（`public_repo` 即可）。
