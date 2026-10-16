# 发布清单（推送到 GitHub / skills.sh）

> 仓库已在本地初始化并完成首次提交（分支 `main`，commit `1e6ead0`）。
> **推送需要你的 GitHub 凭证，所以最后一步留给你执行。** 本机没装 `gh`，
> 全局 git 也没配 author，因此下面有几种走法，挑一种即可。

仓库位置（同时也是已生效的技能目录）：
```
C:\Users\Lucas\.dsh\skills\liepin-boss-apply
```

---

## 方式 A：用 GitHub CLI（最省事，需先安装）

```powershell
# 1) 安装（任选）
winget install --id GitHub.cli
# 或 scoop install gh

# 2) 登录（会开浏览器授权）
gh auth login

# 3) 建仓库并推送（public；想私有改成 --private）
cd "$env:USERPROFILE\.dsh\skills\liepin-boss-apply"
gh repo create liepin-boss-apply --public --source=. --remote=origin --push
```

## 方式 B：已在 GitHub 网页建好空仓库

```powershell
cd "$env:USERPROFILE\.dsh\skills\liepin-boss-apply"
git remote add origin https://github.com/lucasleong2007514133-art/liepin-boss-apply.git
git push -u origin main
```

推送时会提示输入用户名与 **Personal Access Token**（GitHub 已不接受密码，
在 Settings → Developer settings → Personal access tokens 生成，勾 `repo` 即可）。

## 方式 C：SSH

```powershell
# 先生成密钥并添加到 GitHub → Settings → SSH and GPG keys
ssh-keygen -t ed25519 -C "your@email.com"
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"   # 复制到 GitHub

cd "$env:USERPROFILE\.dsh\skills\liepin-boss-apply"
git remote add origin git@github.com:lucasleong2007514133-art/liepin-boss-apply.git
git push -u origin main
```

---

## 推送前建议改两处

### 1) 把提交作者改成你自己
当前是本地占位身份（`liepin-boss-apply <noreply@localhost>`，因为本机没配全局 author）：

```powershell
cd "$env:USERPROFILE\.dsh\skills\liepin-boss-apply"
git config user.name  "<你的名字>"
git config user.email "<你的邮箱>"
git commit --amend --reset-author --no-edit
```

### 2) 把 README 里的 `lucasleong2007514133-art` 换成你的用户名
```powershell
(Get-Content README.md -Raw) -replace 'lucasleong2007514133-art', 'lucasleong2007514133-art' | Set-Content README.md -Encoding UTF8
git add README.md; git commit -m "docs: 填入仓库地址"
```

---

## 推上去之后：发布到 skills.sh 生态

`skills.sh` 是**聚合 GitHub 仓库的索引**，不需要单独上传 —— 只要仓库公开、
且根目录有合法的 `SKILL.md`（本仓库已满足），它就能被搜索到：

```powershell
npx -y skills@latest find "resume apply"        # 或 boss / liepin / job
npx -y skills@latest add lucasleong2007514133-art/liepin-boss-apply   # 别人这样安装
```

> 提示：技能本体已放在 `~/.dsh/skills/liepin-boss-apply`，**DSH 当前已识别并加载**
> （会话技能目录里已出现 `liepin-boss-apply`）。所以即使暂不推送，你也能立刻用。
> 推送只是为了让别人也能装、以及可被 skills.sh 检索到。

---

## 首次使用前要做的准备（与推送无关，但别忘）

1. **换掉示例事实库**：把 `references/facts.example.json` 里的 `<你的名字>` 等占位符
   改成你的真实履历（数字要能被追问）。否则生成的话术会带占位符。
   用 `jobauto.py draft --facts 你的facts.json` 传入。
2. **改 `messages.py` 的 `PATTERNS` 表**（可选）：让 JD 关键词更贴合你的岗位方向。
3. **登录一次**：`jobauto.py launch` 后在新窗口登录 BOSS直聘 / 猎聘，登录态会持久化。
4. **猎聘首次使用务必先 `probe`**：登录后的沟通 UI 选择器未实测，需按真实 DOM 校准。
