# 零基础搭建与使用手册

这份手册手把手带你从一台只装了 Windows 的电脑开始，搭建一个“AI 写草稿、人工审阅后发布”的静态博客，并教你日常怎么使用。不需要编程基础，只要按顺序照做。

- 首次搭建大约需要 2～3 小时，大部分时间花在注册账号和填写配置上。
- 需要准备：一台 Windows 10/11 电脑、一个常用邮箱、一张能在线支付的银行卡（给 AI 模型充值，几美元起）、能正常访问 GitHub、Cloudflare、OpenRouter 的网络。
- 每一章结尾都有“检查点”。检查点没通过就先别往下做，去第 15 章找原因。

## 阅读约定

| 写法 | 含义 |
| --- | --- |
| `这样的文字` | 需要原样输入或点击的内容 |
| `<尖括号>` | 替换成你自己的内容，替换时连尖括号一起删掉。例如 `<用户名>` 写成 `zhangsan` |
| A → B → C | 依次点击菜单 A、B、C |
| “PowerShell 中执行” | 把命令复制到 PowerShell 窗口，按回车 |

网站界面偶尔会改版。如果按钮名字和手册略有不同，找意思相近的按钮即可。

---

## 目录

1. 先了解几个概念
2. 费用与前提条件
3. 安装软件
4. 注册三个账号
5. 把代码放到你自己的 GitHub 仓库
6. 在本机试运行（推荐）
7. 配置 Cloudflare Pages（网站托管）
8. 配置 GitHub 仓库
9. 第一次部署：让空网站上线
10. 保护 main 分支
11. 完整演练：生成并发布第一篇文章
12. 日常使用
13. 手写文章
14. 进阶设置
15. 故障排查
16. 安全与合规须知
17. 附录：配置总表与常用命令

---

## 1. 先了解几个概念

不用死记，遇到不懂的词回来查。

| 名词 | 通俗解释 |
| --- | --- |
| Git | 装在电脑上的“版本记录”软件，记录文件的每一次修改 |
| GitHub | 存放 Git 项目的网站，还能自动运行任务 |
| 仓库（Repository） | 一个项目的全部文件和修改历史，相当于项目文件夹 |
| 分支（Branch） | 仓库的一条“平行版本线”。`main` 是正式版本，网站就用它发布；AI 草稿放在 `draft/...` 分支，互不影响 |
| 提交（Commit） | 保存一次修改，并附上一句说明 |
| 推送（Push） | 把电脑上的提交上传到 GitHub |
| Pull Request（PR） | “请把这个分支的修改合并到 main”的申请单，审阅就在这里进行 |
| 合并（Merge） | 批准 PR 后，把修改正式并入 `main` |
| GitHub Actions / 工作流 | GitHub 上的自动化任务。本项目有 3 个：生成草稿、审阅检查、部署网站 |
| Secret | 存在 GitHub 里的保密信息（如密钥），任何人都看不到它的值 |
| Variable | 存在 GitHub 里的普通配置（如模型名称） |
| Environment | GitHub 里的“部署环境”，可以单独存放只给部署用的 Secret |
| Markdown | 一种用符号排版的纯文本格式，如 `## 标题`、`- 列表` |
| front-matter | 文章文件开头两行 `---` 之间的信息区，写标题、日期、是否草稿等 |
| OpenRouter | AI 模型的中转服务，一个账号就能调用多家模型，按用量付费 |
| API Key / Token | 程序访问某个服务时用的“密码” |
| Cloudflare Pages | 免费托管静态网站的服务，网站地址形如 `https://xxx.pages.dev` |
| 静态网站 | 由现成 HTML 文件组成的网站，没有数据库和后台，便宜且安全 |

整个系统是这样运转的：

```text
① 你在 GitHub 上点按钮，填写选题
        │
        ▼
② “生成草稿”工作流调用 AI，把草稿放到 draft/<一串字符> 分支
        │
        ▼
③ 你为草稿创建 PR，逐项审阅、修改，确认后手动改为“可发布”
        │
        ▼
④ “审阅检查”工作流确认审阅记录齐全 → 合并 PR 到 main
        │
        ▼
⑤ “部署”工作流自动构建网站，上传到 Cloudflare Pages，文章上线
```

AI 永远只能写草稿。发布一定要经过人工审阅和人工合并，这是本项目的核心规则。

---

## 2. 费用与前提条件

### 2.1 费用

| 服务 | 费用 |
| --- | --- |
| GitHub | 公开仓库免费（含 Actions 运行时间） |
| Cloudflare Pages | 有免费计划，个人博客通常够用 |
| OpenRouter | 按用量付费，需要先充值。一篇文章通常只花不到 1 美分（取决于模型和长度） |
| 域名 | 可选。不买也能用 `xxx.pages.dev` 免费地址 |

以上是写作时的情况，价格和免费额度以各服务官网为准。

### 2.2 仓库必须是公开的（或者你有 GitHub Pro）

本项目依赖 GitHub 的两个功能：Environments（保存部署密钥）和分支保护（防止跳过审阅）。按 [GitHub 官方文档](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)，免费账号只能在公开仓库中使用这两个功能。

所以你有两个选择：

- 使用公开仓库（推荐新手）。代码和草稿别人都能看到，但 Secret 中的密钥不会公开。
- 使用私有仓库，并升级到 GitHub Pro 等付费计划。

### 2.3 一个人还是两个人

GitHub 不允许你批准自己创建的 PR。本项目的合规清单要求“至少一位人工批准”，因此最理想的是两个人：一个人负责审阅编辑，另一个人批准合并。

只有你一个人也能用，第 10.3 节会说明单人设置方式及其代价。

---

## 3. 安装软件

需要安装 3 个软件：Git、Node.js（22.12 或更高版本）、Python（3.11 或更高版本）。

### 3.1 打开 PowerShell

按键盘上的 Windows 键，输入 `PowerShell`，点击“Windows PowerShell”。会出现一个蓝色或黑色的命令窗口，后面所有“PowerShell 中执行”的命令都在这里输入。

小技巧：在 PowerShell 中，右键单击即可粘贴。

### 3.2 用 winget 一键安装（推荐）

先检查电脑是否有 winget：

```powershell
winget --version
```

显示版本号（如 `v1.9.xxxx`）就可以继续。如果提示“无法识别”，跳到 3.3 手动安装。

依次执行下面 3 条命令，每条都等它显示“已成功安装”再执行下一条。过程中如果弹出“是否允许此应用更改设备”，点“是”。

```powershell
winget install --id Git.Git -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Python.Python.3.12 -e
```

第一次使用 winget 时可能询问是否同意条款，输入 `Y` 回车。

### 3.3 手动安装（winget 不可用时）

- Git：打开 <https://git-scm.com/download/win>，下载安装包，所有选项保持默认，一路 Next。
- Node.js：打开 <https://nodejs.org/>，下载标着 LTS 的版本，一路 Next。
- Python：打开 <https://www.python.org/downloads/windows/>，下载 3.12 或更新版本。安装第一页务必勾选底部的 `Add python.exe to PATH`，再点 Install Now。

### 3.4 验证安装

关闭所有 PowerShell 窗口，重新打开一个（这一步很重要，否则新软件不生效）。依次执行：

```powershell
git --version
node -v
npm -v
python --version
```

| 命令 | 正常结果示例 | 要求 |
| --- | --- | --- |
| `git --version` | `git version 2.xx.x.windows.1` | 有版本号即可 |
| `node -v` | `v24.12.0` | 不低于 `v22.12.0` |
| `npm -v` | `11.x.x` | 有版本号即可 |
| `python --version` | `Python 3.12.x` | 不低于 3.11 |

如果输入 `python` 后弹出了微软应用商店：打开 Windows 设置 → 应用 → 高级应用设置 → 应用执行别名，关闭 `python.exe` 和 `python3.exe` 两项，再重新打开 PowerShell。

### 3.5 设置 Git 身份

Git 的每次提交都会记录作者。PowerShell 中执行（换成你自己的信息）：

```powershell
git config --global user.name "<你的名字或昵称>"
git config --global user.email "<你注册 GitHub 用的邮箱>"
```

### 3.6 （可选）安装代码编辑器

推荐安装 [Visual Studio Code](https://code.visualstudio.com/) 或 Kiro，用来查看和编辑项目文件。不装也行，本手册的大部分操作在 GitHub 网页上就能完成。

检查点：3.4 中四条命令都能显示合格的版本号。

---

## 4. 注册三个账号

### 4.1 GitHub

1. 打开 <https://github.com/signup>，按提示填写邮箱、密码、用户名，完成邮箱验证。
2. 记住你的用户名，后面会反复用到。
3. 强烈建议开启两步验证：右上角头像 → Settings → Password and authentication → Enable two-factor authentication。

### 4.2 OpenRouter（AI 模型）

1. 打开 <https://openrouter.ai/>，点右上角 Sign Up 注册并登录。
2. 充值：打开 <https://openrouter.ai/settings/credits>，点 Add Credits，按页面提示付款。第一次建议只充最低金额，够写很多篇文章。
3. 查看模型价格：打开 <https://openrouter.ai/openai/gpt-4o-mini>，记下两个价格：
   - Input（输入），每百万 token 多少美元；
   - Output（输出），每百万 token 多少美元。

   写作时分别约为 0.15 和 0.60 美元，请以页面实际显示为准。第 8 章要填这两个数字。
4. 创建 API Key：打开 <https://openrouter.ai/settings/keys>，点 Create Key：
   - Name：填 `content-farm`；
   - Credit limit（如有此项）：建议填一个上限，如 `2`，防止意外超支；
   - 点 Create。
5. 页面会显示一串以 `sk-or-` 开头的密钥。立刻复制，保存到安全的地方（如密码管理器）。它只显示这一次。

密钥就像银行卡密码：不要发到聊天群、不要截图、不要写进任何项目文件。泄露了就回到 Keys 页面删除它，再建一个新的。

### 4.3 Cloudflare（网站托管）

1. 打开 <https://dash.cloudflare.com/sign-up>，用邮箱注册，完成邮箱验证。
2. 不需要购买域名，也不需要添加网站。登录能看到控制台就行。

检查点：三个账号都能登录；手里有一个 OpenRouter API Key 和两个模型价格数字。

---

## 5. 把代码放到你自己的 GitHub 仓库

根据你的情况，选择 5.2、5.3、5.4 中的一种。

### 5.1 在 GitHub 上新建一个空仓库

（5.4 的情况跳过这一步）

1. 登录 GitHub，点右上角 `+` → New repository。
2. Repository name：填一个名字，如 `my-blog`，只用英文、数字和连字符。
3. 选择 Public（原因见 2.2）。
4. 下面的 Add a README file、.gitignore、license 都不要勾选，保持空仓库。
5. 点 Create repository。

仓库地址是 `https://github.com/<用户名>/<仓库名>`。

### 5.2 情况 A：你手里有项目文件夹

先在 PowerShell 中进入项目文件夹。路径里有空格时要加双引号：

```powershell
cd "F:\project_code\content farm"
```

（换成你自己的项目路径。可以在文件资源管理器中打开项目文件夹，点击顶部地址栏复制路径。）

检查这个文件夹是否已经是 Git 仓库：

```powershell
git status
```

- 如果提示 `not a git repository`，先执行 `git init`。
- 其他情况直接继续。

把分支命名为 `main`，并关联到你刚建的仓库：

```powershell
git branch -M main
git remote -v
```

- 如果 `git remote -v` 没有任何输出，执行：

  ```powershell
  git remote add origin https://github.com/<用户名>/<仓库名>.git
  ```

- 如果已经显示了一个 `origin` 地址，但不是你的仓库，执行：

  ```powershell
  git remote set-url origin https://github.com/<用户名>/<仓库名>.git
  ```

上传前，先看看会上传哪些文件：

```powershell
git add .
git status
```

逐行检查绿色的文件列表，确认没有私人文件，比如 PDF 电子书、`.env`、写有密钥的文本文件。发现了就执行 `git reset`，把这些文件移出项目文件夹后重新 `git add .`。确认无误后提交并上传：

```powershell
git commit -m "初始化项目"
git push -u origin main
```

第一次推送会弹出 GitHub 登录窗口，选 Sign in with your browser，在浏览器里点授权即可。

### 5.3 情况 B：从别人的 GitHub 仓库获取代码

```powershell
cd "$env:USERPROFILE\Documents"
git clone https://github.com/<原作者>/<原仓库名>.git my-blog
cd my-blog
git remote set-url origin https://github.com/<你的用户名>/<你的仓库名>.git
git branch -M main
git push -u origin main
```

这样代码就放进了你自己的仓库，Actions 默认启用。不建议使用 GitHub 的 Fork 按钮，Fork 仓库默认禁用 Actions，设置更麻烦。

### 5.4 情况 C：代码已在 GitHub 上，但默认分支叫 `master`

部署工作流只在 `main` 分支有新提交时运行，所以必须改名为 `main`。

1. 打开仓库页面 → Settings → General。
2. 在 Default branch 一栏，点分支名旁边的铅笔图标（Rename branch）。
3. 输入 `main`，点 Rename branch。

然后在本机项目文件夹中执行，让本地也同步改名：

```powershell
git branch -m master main
git fetch origin
git branch -u origin/main main
git remote set-head origin -a
```

检查点：打开 `https://github.com/<用户名>/<仓库名>`，能看到 `src`、`content_pipeline`、`docs` 等文件夹；页面左上方的分支按钮显示 `main`。

---

## 6. 在本机试运行（推荐）

这一步不是必须的，但能确认代码完好，也能让你提前在本机看到网站的样子。

### 6.1 安装项目依赖

在 PowerShell 中进入项目文件夹（`cd "<项目路径>"`），依次执行：

```powershell
npm ci
```

这一步会下载网站依赖，需要几分钟，最后显示 `added xxx packages` 就成功了。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

第一条会在项目里创建独立的 Python 环境 `.venv`，第二条激活它。激活成功后，命令行开头会出现 `(.venv)`。

如果第二条报错“在此系统上禁止运行脚本”，执行下面这条，输入 `Y` 回车，再重新执行激活命令：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

安装 Python 依赖：

```powershell
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

以后每次新开 PowerShell 窗口，都要先执行 `.\.venv\Scripts\Activate.ps1`，再运行 Python 相关命令。

### 6.2 运行测试

```powershell
npm run test:all
```

依次运行两组测试。结尾分别出现类似下面的内容就说明全部通过（具体数量会随项目更新而变化）：

```text
Test Files  5 passed (5)
     Tests  45 passed (45)
...
383 passed in 4.44s
```

出现 `failed` 字样说明有问题，先不要继续，把错误信息记下来排查。

### 6.3 本地预览网站

```powershell
npm run dev
```

看到 `Local http://localhost:4321/` 后，用浏览器打开这个地址。你会看到标题为 “Content Pipeline”、“最新文章”下写着“暂无文章。”的首页，这是正常的，因为还没有发布任何文章。

预览完成后，回到 PowerShell 按 `Ctrl + C` 停止。

检查点：测试全部通过，浏览器能打开本地首页。

---

## 7. 配置 Cloudflare Pages（网站托管）

需要完成三件事：创建 Pages 项目、找到账号 ID、创建 API Token。

### 7.1 创建 Pages 项目

这一步用命令行完成，因为命令行可以明确指定“生产分支为 main”。在网页上创建的直接上传项目，之后无法在界面修改生产分支。

先想好项目名：只用小写英文、数字和连字符，如 `my-blog`。它会成为网址的一部分：`https://my-blog.pages.dev`。

PowerShell 中执行（第一次会下载 wrangler 工具，询问时输入 `y` 回车）：

```powershell
npx wrangler@4.141.0 login
```

浏览器会打开 Cloudflare 授权页，点 Allow。看到 “Successfully logged in” 后回到 PowerShell，创建项目：

```powershell
npx wrangler@4.141.0 pages project create <项目名> --production-branch=main
```

成功后会显示项目的访问地址。确认一下：

```powershell
npx wrangler@4.141.0 pages project list
```

列表中应该有你的项目。如果项目名已被别人占用，地址可能会带随机后缀，例如 `my-blog-abc.pages.dev`。请以实际显示的地址为准，第 8 章要用。

此时网址还打不开或显示错误页，这是正常的，第 9 章部署后才有内容。

### 7.2 找到账号 ID（Account ID）

1. 打开 <https://dash.cloudflare.com/>，左侧菜单点 Workers & Pages（在“计算”或 Compute 分组下）。
2. 在页面右侧找到 Account Details，点 Account ID 旁边的复制按钮。

找不到时，也可以在控制台任意页面按 `Ctrl + K`，输入 `Copy account ID`，选中结果即可复制（参考 [Cloudflare 文档](https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/)）。

把它临时保存起来。账号 ID 是一串 32 位的字母数字。

### 7.3 创建 API Token

这个 Token 只允许 GitHub 往你的 Pages 项目上传网站，权限越小越安全。

1. Cloudflare 控制台右上角头像 → My Profile → 左侧 API Tokens。
2. 点 Create Token，拉到下方 Custom token，点 Get started。
3. 按下表填写：

   | 项目 | 填写 |
   | --- | --- |
   | Token name | `github-deploy` |
   | Permissions | 三个下拉框依次选 `Account`、`Cloudflare Pages`、`Edit` |
   | Account Resources | `Include`、选择你的账号 |
   | 其他 | 保持默认 |

4. 点 Continue to summary → Create Token。
5. 复制显示的 Token，保存到安全的地方。它同样只显示这一次。

### 7.4 退出命令行登录（可选）

```powershell
npx wrangler@4.141.0 logout
```

之后部署由 GitHub 使用 7.3 的 Token 完成，本机不再需要保持登录。

检查点：你现在有 Pages 项目名、网站地址（`https://<项目名>.pages.dev`）、账号 ID、API Token。

---

## 8. 配置 GitHub 仓库

以下操作都在浏览器中打开你的仓库页面，点顶部的 Settings（设置）后进行。名字必须和手册完全一致，包括大小写和下划线，建议直接复制。

### 8.1 Actions 权限

Settings → 左侧 Actions → General：

1. Actions permissions：保持 `Allow all actions and reusable workflows`。
2. 拉到页面下方 Workflow permissions：
   - 选择 `Read repository contents and packages permissions`；
   - 取消勾选 `Allow GitHub Actions to create and approve pull requests`；
   - 点 Save。

这样能防止自动化程序自己批准 PR。

### 8.2 添加模型密钥（Secret）

Settings → 左侧 Secrets and variables → Actions → Secrets 标签页 → New repository secret：

| Name | Secret |
| --- | --- |
| `MODEL_GATEWAY_API_KEY` | 粘贴 4.2 中复制的 OpenRouter API Key |

点 Add secret。保存后页面只显示名字，不显示值，这是正常的。

### 8.3 添加配置变量（Variables）

同一页面切换到 Variables 标签页，点 New repository variable，逐个添加下面 10 个变量（每添加一个点一次 Add variable）：

| Name | Value（示例） | 说明 |
| --- | --- | --- |
| `MODEL_GATEWAY` | `openrouter` | 固定填这个 |
| `MODEL_ID` | `openai/gpt-4o-mini` | 固定填这个（更换模型见 14.3） |
| `BUDGET_INPUT_PRICE_PER_MTOK` | `0.15` | 4.2 记下的 Input 价格 |
| `BUDGET_OUTPUT_PRICE_PER_MTOK` | `0.60` | 4.2 记下的 Output 价格 |
| `BUDGET_MAX_INPUT_TOKENS` | `4000` | 输入 token 上限，用于估算费用 |
| `BUDGET_MAX_OUTPUT_TOKENS` | `4000` | AI 最多输出多少 token |
| `BUDGET_MAX_COST_PER_ARTICLE` | `0.01` | 单篇费用上限（美元） |
| `BUDGET_MAX_COST_PER_RUN` | `0.02` | 单次运行费用上限（美元） |
| `SITE_URL` | `https://<项目名>.pages.dev` | 7.1 中显示的网站地址，必须以 `https://` 开头 |
| `CLOUDFLARE_PAGES_PROJECT` | `<项目名>` | 7.1 中创建的项目名 |

填写数字时的注意事项：

- 只写普通数字，如 `0.6`。不要写 `$`、空格、负数或 `1e-3` 这类写法。
- 两个 token 上限只能是整数。

预算是怎么算的？每次调用 AI 之前，程序会先估算最坏情况下的费用：

```text
预估费用 = (输入上限 × 输入单价 + 输出上限 × 输出单价) ÷ 1,000,000
         = (4000 × 0.15 + 4000 × 0.60) ÷ 1,000,000
         = 0.003 美元
```

- 预估费用超过单篇上限（0.01），直接停止，不调用 AI。
- 网络出错时程序会自动重试 1 次，重试也要预留一份费用。所以单次上限（0.02）至少要是预估费用的 2 倍，才能保证重试有额度。

`BUDGET_MAX_OUTPUT_TOKENS` 同时也是 AI 回答的最大长度。设得太小，文章会被截断，导致生成失败。4000 一般够写一篇中等长度的文章；想要更长的文章可以调大，同时相应调高两个费用上限。

### 8.4 创建部署环境 production

Settings → 左侧 Environments → New environment：

1. Name 填 `production`，点 Configure environment。
2. 找到 Deployment branches and tags，下拉选择 `Selected branches and tags`，点 Add deployment branch or tag rule，输入 `main`，点 Add rule。
3. 找到 Environment secrets，点 Add environment secret，添加两个：

   | Name | Value |
   | --- | --- |
   | `CLOUDFLARE_API_TOKEN` | 7.3 中复制的 Token |
   | `CLOUDFLARE_ACCOUNT_ID` | 7.2 中复制的账号 ID |

这两个必须添加在 production 环境里，不要加到 8.2 的仓库 Secret 中。这样只有部署步骤能读取它们，生成草稿的程序读不到。

检查点：

- [ ] Actions → General 中已取消勾选 “Allow GitHub Actions to create and approve pull requests”；
- [ ] 仓库 Secret 有 1 个：`MODEL_GATEWAY_API_KEY`；
- [ ] 仓库 Variable 有 10 个，名字与 8.3 表格完全一致；
- [ ] Environments 中有 `production`，限制为 `main` 分支，并有 2 个 Secret。

---

## 9. 第一次部署：让空网站上线

部署工作流只在 `main` 分支收到新提交时运行。现在还没有设置分支保护，可以直接在 `main` 上做一次小修改来触发它。

### 9.1 触发部署

1. 打开仓库首页，点击文件列表中的 `README.md`。
2. 点右上角的铅笔图标（Edit this file）。
3. 在文件最末尾另起一行，随便写一句话，如 `站点已完成首次部署。`
4. 点右上角绿色的 Commit changes...，在弹窗中选择 `Commit directly to the main branch`，再点 Commit changes。

### 9.2 查看部署进度

1. 点仓库顶部的 Actions 标签页。
2. 列表最上方会出现一条 “Deploy static site” 运行记录，黄色圆圈表示正在运行。
3. 点进去可以看到两个任务：`Build static site (no secrets)` 和 `Deploy to static hosting`。两个都变成绿色对勾即成功，通常需要 2～5 分钟。

### 9.3 访问网站

浏览器打开 `https://<项目名>.pages.dev`，看到和 6.3 本地预览一样的首页（“暂无文章。”）就成功了。刚部署完如果打不开，等一两分钟再刷新。

如果任务出现红色叉号，点进去找到红色的步骤，展开查看以 `Error` 或 `::error::` 开头的行，然后到第 15.3 节对照处理。

检查点：`https://<项目名>.pages.dev` 能打开首页。

---

## 10. 保护 main 分支

生成草稿的程序有写仓库的权限。分支保护规则可以确保任何修改都必须通过 PR、经过检查才能进入 `main`，是防止跳过人工审阅的最后一道防线。

### 10.1 创建规则

Settings → 左侧 Rules → Rulesets → New ruleset → New branch ruleset：

| 设置项 | 填写 |
| --- | --- |
| Ruleset Name | `protect-main` |
| Enforcement status | `Active` |
| Bypass list | 保持为空，不添加任何人或应用 |
| Target branches | 点 Add target → `Include default branch` |

在下方 Rules 区域：

- 保持勾选 `Restrict deletions` 和 `Block force pushes`；
- 勾选 `Require a pull request before merging`，展开后把 `Required approvals` 设为 `1`（单人运营见 10.3）；
- `Require status checks to pass` 先不勾，第 11.4 节再回来添加。

拉到底部点 Create。

如果你的界面没有 Rulesets，也可以用 Settings → Branches → Add classic branch protection rule，Branch name pattern 填 `main`，勾选相同的选项。

### 10.2 验证规则生效

按 9.1 的方法再编辑一次 `README.md`，这次弹窗中应该只能选择 `Create a new branch for this commit and start a pull request`，不能直接提交到 main。看到这个选项说明保护已生效，点 Cancel 取消即可。

### 10.3 单人运营怎么办

GitHub 不允许批准自己创建的 PR，所以 `Required approvals` 为 1 时，一个人永远无法合并。有两种做法：

方案一（推荐，符合合规清单）：邀请一位协作者

1. Settings → Collaborators → Add people，输入对方的 GitHub 用户名或邮箱。
2. 对方在邮件中接受邀请后，就可以批准你的 PR。

方案二（单人）：把 `Required approvals` 改为 `0`

- 仍然要求所有修改走 PR，并且要通过 review-gate 审阅检查。
- 代价是少了第二个人把关。这与 `docs/compliance.md` 中“要求至少一位人工批准”的规定不一致，请自行评估。条件允许时，建议尽快改用方案一。

检查点：编辑 main 上的文件时，只能选择“新建分支并创建 PR”。

---

## 11. 完整演练：生成并发布第一篇文章

### 11.1 触发生成

1. 仓库顶部 Actions → 左侧列表点 `Generate draft (manual)`。
2. 右侧点 Run workflow 下拉按钮。
3. `Use workflow from` 保持 `Branch: main`（选其他分支会直接失败）。
4. 填写 5 个输入：

   | 输入框 | 含义 | 示例 |
   | --- | --- | --- |
   | 选题 `topic` | 写什么，最多 160 字 | `如何为个人博客选择静态托管` |
   | 读者画像 `audience` | 写给谁看，最多 160 字 | `第一次搭建博客、不懂编程的新手` |
   | 关键词 `keywords` | 相关关键词，最多 300 字 | `静态网站, Cloudflare Pages, 免费托管` |
   | Prompt 名称 `prompt_name` | 写作指令的名字 | `article-draft` |
   | Prompt 版本 `prompt_version` | 写作指令的版本 | `1.0.0` |

5. 点绿色的 Run workflow。

几秒后刷新页面，列表出现新的运行记录。点进去可以看到两个任务：

- `Generate and validate draft (read-only)`：调用 AI 并检查文章格式；
- `Create or update draft/<stable-key> for review`：把草稿保存到草稿分支。

两个都变绿就完成了，通常需要 1～5 分钟。

写好输入的建议：

- 选题越具体越好。“个人博客静态托管怎么选”比“博客”好得多。
- 读者画像写清楚对方的水平和目的，AI 会据此调整深浅。
- 关键词只写真正相关的几个，不要堆砌。

同一时间只能运行一个生成任务，运行中再次触发的会排队。

### 11.2 找到草稿

在这次运行的页面，点左侧的 Summary，页面下方会显示“草稿已就绪，等待人工审阅”，里面有：

- 草稿分支：`draft/` 加 64 位字符；
- 文章文件：`src/content/articles/<英文短名>-<12位字符>.md`；
- 创建 Pull Request 的链接。

### 11.3 创建 PR

1. 点击 Summary 中第 1 步的链接，打开 “Comparing changes” 页面。
2. 确认顶部显示 `base: main` ← `compare: draft/...`。
3. 标题默认是 `draft: generate ...`，建议改成文章的主题，方便以后查找。
4. 描述框已经自动填好了审阅模板，先不用改。
5. 点 Create pull request。

### 11.4 添加必需检查 review-gate

PR 创建后，页面下方会出现 `review-gate` 检查，并很快显示红色失败。这是正常的：审阅记录还没填，文章也还是草稿。

现在它已经运行过一次，可以把它设为合并的必要条件了：

1. Settings → Rules → Rulesets → 点 `protect-main`。
2. 勾选 `Require status checks to pass`，点 Add checks，输入 `review-gate`，在搜索结果中选中它。
3. 页面底部点 Save changes。

以后所有 PR 都必须通过 review-gate 才能合并。这一步只需做一次。

### 11.5 阅读草稿

在 PR 页面点 Files changed 标签页，可以看到 AI 生成的完整文章。点文件右上角的 `⋯` → View file，可以看到排版后的效果。

文章开头 `---` 之间是 front-matter，例如：

```yaml
---
title: "文章标题"
description: "一两句话的摘要"
pubDate: "2026-09-26T08:00:00Z"
tags: ["静态网站", "部署"]
slug: "static-hosting-guide"
draft: true
ai_assisted: true
model: "openai/gpt-4o-mini"
prompt_version: "1.0.0"
sources: []
---
```

`slug` 决定文章网址：`https://<项目名>.pages.dev/articles/<slug>/`。`draft: true` 表示这还是草稿，不会出现在网站上。

### 11.6 逐项审阅

AI 可能编造数据、引用和链接，必须逐项认真检查：

| 审阅项 | 要检查什么 |
| --- | --- |
| 事实与来源 | 文中的数据、结论是否正确？`sources` 里的每个链接都要亲手打开，确认真实存在并且支持文中说法 |
| 读者价值 | 对目标读者有没有实际帮助？有没有空话、套话、重复堆砌关键词 |
| 语气 | 是否客观、友好、符合网站风格？有没有夸大宣传 |
| 链接 | 正文里的每个链接都能打开，指向正确的页面 |
| 标题 | 标题是否准确反映内容，没有夸张或误导 |

### 11.7 在网页上修改文章

发现需要修改的地方：

1. Files changed 中，点文件右上角 `⋯` → Edit file。
2. 直接修改文字。
3. 点右上角 Commit changes...，确认选中 `Commit directly to the draft/... branch`，点 Commit changes。

修改时注意保持格式：

- 不要删除 front-matter 前后的 `---` 行；
- 日期必须加双引号，格式 `"YYYY-MM-DDTHH:mm:ssZ"`；
- 正文链接必须是 `https://` 开头的完整网址，或以 `/` 开头的站内地址；
- 不要写 HTML 代码，尤其是 `<script>`。

更多字段规则见 13.3。

### 11.8 填写审阅记录

1. 回到 PR 的 Conversation 标签页。
2. 在最上方的描述框右上角点 `⋯` → Edit。
3. 找到五行审阅清单，把每行的 `[ ]` 改为 `[x]`，并在冒号后写下你检查了什么、结论是什么。
4. 点 Update comment。

填写示例：

```markdown
- [x] 事实与来源 `facts_and_sources`：核对了 3 处数据和 2 个来源链接，删除 1 处无法证实的说法
- [x] 读者价值 `reader_value`：补充了具体操作步骤，适合新手
- [x] 语气 `tone`：去掉两处夸张用语
- [x] 链接 `links`：5 个链接都能打开，替换了 1 个失效链接
- [x] 标题 `title`：改为更具体的“个人博客静态托管的三种选择”
```

必须遵守的规则（否则 review-gate 不通过）：

- 5 项都要勾选 `[x]`，每项只能出现一次；
- 冒号后必须写内容，不能留空，也不能只写 `TODO`、`TBD`、`待填写`、`待定`、`-`、`...`；
- 不要删除行中反引号括起来的英文名，如 `` `tone` ``，检查程序靠它识别每一项；
- 写在 `<!--` 和 `-->` 之间的内容是注释，不会被计入。

### 11.9 改为可发布

五项审阅全部完成后，按 11.7 的方法编辑文章，把 front-matter 中的

```yaml
draft: true
```

改为

```yaml
draft: false
```

然后提交到草稿分支。

这一步必须由你本人的 GitHub 账号完成。在网页上编辑就自动满足这个要求。由自动化账号（名字以 `[bot]` 结尾）做的这一改动会被 review-gate 拒绝。

### 11.10 合并发布

1. 回到 Conversation 标签页，等待 review-gate 变成绿色对勾。修改描述或推送新提交后，它会自动重新运行。
2. 请协作者批准：对方打开 PR → Files changed → 右上角 Review changes → 选 Approve → Submit review。单人方案二可跳过这一步。
3. 点绿色的 Merge pull request → Confirm merge。
4. 可以点 Delete branch 删除草稿分支，保持仓库整洁。

合并后，Actions 中会自动出现新的 “Deploy static site” 运行。等它变绿，打开网站首页，就能看到你的第一篇文章了。

检查点：网站首页出现文章，点击能打开 `/articles/<slug>/` 页面。

恭喜，搭建全部完成。

---

## 12. 日常使用

### 12.1 发布一篇新文章（速查）

1. Actions → Generate draft (manual) → Run workflow → 分支选 `main` → 填 5 项 → Run。
2. 运行完成后打开 Summary 中的链接 → Create pull request。
3. Files changed 中阅读并修改文章。
4. 编辑 PR 描述，完成五项 `[x]` 审阅记录。
5. 编辑文章，`draft: true` 改为 `draft: false`。
6. review-gate 通过 → 协作者批准 → Merge pull request。
7. 等 Deploy static site 完成，文章上线。

### 12.2 放弃一篇草稿

草稿不满意、不想发布：

- 已经创建了 PR：在 PR 页面底部点 Close pull request，再点 Delete branch。
- 还没创建 PR：仓库首页点分支按钮 → View all branches，找到对应的 `draft/...` 分支，点右侧垃圾桶图标。

草稿永远不会出现在网站上，放着不管也没有影响。

### 12.3 重新生成的注意事项

- 用完全相同的 5 个输入重新生成，会写入同一个分支、同一个文件。如果编辑已经在修改这篇草稿，重新生成会覆盖掉这些修改，并把 `draft` 恢复为 `true`。所以审阅开始后，不要用相同输入重新生成。
- 想要一个不同的版本，请改一下选题或关键词。
- 更换了 Prompt 版本或模型，会生成一个全新的草稿分支。

### 12.4 修改已发布的文章

1. 在仓库文件列表中打开 `src/content/articles/` 下要改的文章。
2. 点铅笔图标编辑。保持 `draft: false`，建议在 front-matter 中加一行更新时间：

   ```yaml
   updatedDate: "2026-10-01T08:00:00Z"
   ```

3. Commit changes，选择 `Create a new branch for this commit and start a pull request`，点 Propose changes → Create pull request。
4. PR 描述同样要完成五项审阅记录，review-gate 通过后合并。

不要随意修改 `slug`，否则文章网址会变，旧链接失效。

### 12.5 下线一篇文章

1. 打开文章文件，点右上角 `⋯` → Delete file。
2. 选择 `Create a new branch for this commit and start a pull request` → Propose changes → Create pull request。
3. 只删除文章的 PR 不需要填写审阅记录，review-gate 会显示“不适用”并通过。合并后文章从网站消失。

不要用把 `draft` 改回 `true` 的方式下线。review-gate 要求 PR 中修改过的文章最终必须是 `draft: false`，这种 PR 无法通过检查。

### 12.6 怎么看花了多少钱

- 每次生成运行的日志中会输出预估费用和调用次数：Actions → 某次运行 → `Generate and validate draft` 任务 → 展开 `Generate draft bundle` 步骤。
- 实际扣费以 OpenRouter 的 <https://openrouter.ai/activity> 页面为准。

---

## 13. 手写文章

不用 AI，也可以自己写文章发布。

### 13.1 在网页上新建文章

1. 仓库首页 → Add file → Create new file。
2. 文件名输入框中填 `src/content/articles/<文件名>.md`。输入 `/` 时会自动变成文件夹层级。
3. 把 13.2 的模板粘贴进去，修改内容，并保持 `draft: true`。
4. Commit changes，选择 `Create a new branch for this commit and start a pull request` → Propose changes → Create pull request。
5. 按 11.6～11.10 审阅：填写五项记录，再单独提交一次把 `draft` 改为 `false`，然后合并。

为什么要先写 `draft: true` 再改？review-gate 要求 PR 历史中能看到“先是草稿，后由人工改为可发布”的过程。第一次提交就写 `draft: false`，检查会报 `no draft: true -> false transition found`。

文件名规则：只用小写英文、数字和连字符，以 `.md` 结尾，如 `static-hosting-guide.md`，直接放在 `src/content/articles/` 下，不要建子文件夹。

### 13.2 文章模板

```markdown
---
title: "个人博客静态托管的三种选择"
description: "比较三种常见静态托管方式的部署流程与限制。"
pubDate: "2026-09-26T08:00:00Z"
tags: ["静态网站", "部署"]
slug: "static-hosting-choices"
draft: true
ai_assisted: false
model: "none"
prompt_version: "none"
sources:
  - title: "Astro 部署指南"
    url: "https://docs.astro.build/en/guides/deploy/"
    accessedDate: "2026-09-26T08:00:00Z"
---

## 为什么选择静态托管

这里开始写正文，使用 Markdown 格式。

## 第二个小标题

- 列表项一
- 列表项二

[站内链接示例](/tags/)
```

### 13.3 字段说明

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `title` | 是 | 标题，不能为空 |
| `description` | 是 | 摘要，一两句话，不能为空 |
| `pubDate` | 是 | 发布时间，UTC 时间，格式 `"YYYY-MM-DDTHH:mm:ssZ"`，必须带双引号。北京时间减 8 小时就是 UTC 时间，如北京时间 16:00 写成 `08:00:00Z` |
| `updatedDate` | 否 | 更新时间，格式同上 |
| `tags` | 是 | 标签列表，如 `["部署", "教程"]`；没有标签写 `[]` |
| `slug` | 是 | 网址名，只用小写英文、数字和单个连字符，最长 80 个字符，不能和其他已发布文章重复 |
| `draft` | 是 | `true` 草稿，`false` 可发布 |
| `ai_assisted` | 是 | 是否用了 AI，`true` 或 `false` |
| `model` | 是 | 使用的模型，手写文章填 `"none"` |
| `prompt_version` | 是 | Prompt 版本，手写文章填 `"none"` |
| `sources` | 是 | 参考来源列表，没有写 `[]`。每项要有 `title`、`url`（`https://` 开头）、`accessedDate`（访问时间，格式同 `pubDate`） |

正文规则：

- 不能为空，最长 10 万字符；
- 不能包含 `<script>`，建议完全不写 HTML；
- 链接只能是 `https://` 开头的完整网址，或 `/` 开头的站内地址；`http://` 链接会导致文章被排除。

注意：格式不合规的文章不会报错，而是悄悄不显示在网站上。合并后文章没出现，先对照这张表检查。

---

## 14. 进阶设置

### 14.1 修改网站名称和简介

编辑 `src/lib/site-meta.ts`：

```ts
export const SITE_TITLE = 'Content Pipeline';            // 网站名称
export const SITE_DESCRIPTION = '人工审阅后发布的静态内容博客。'; // 首页简介
```

改引号里的文字，通过 PR 合并即可。只修改代码、不涉及文章的 PR 不需要填写审阅记录。

### 14.2 修改 AI 写作指令（Prompt）

写作指令在 `prompts/article-draft.md`，开头是名称和版本：

```markdown
---
name: article-draft
version: 1.0.0
description: 为人工审阅生成一篇面向读者的博客文章草稿。
---
这里是给 AI 的写作要求……
```

修改方法：

1. 不要直接改已经用过的版本。新建一个文件，如 `prompts/article-draft-v1-1.md`，复制原内容，把 `version` 改为 `1.1.0`，再修改写作要求。
2. 规则：`name` 只用小写英文、数字和连字符；`version` 是“数字.数字.数字”；正文不能为空；任意两个文件的 name 和 version 不能完全相同。
3. 通过 PR 合并到 main 后，生成时在 `prompt_version` 中填 `1.1.0` 即可使用。

`prompts/` 下只要有一个文件格式错误，所有生成都会失败，修改时要仔细检查。

### 14.3 更换 AI 模型

需要同时改两处，缺一不可：

1. 通过 PR 修改 `docs/compliance.md` 开头的 `model`，并同步修改下方正文第 1 节中的模型名称。
2. 在 GitHub Variables 中修改 `MODEL_ID` 为相同的值，并按新模型价格更新两个单价变量。

如需改用 LiteLLM 或其他网关地址，还要修改 `docs/compliance.md` 中的 `gateway`、`model_endpoint` 和 `allowed_endpoints`，并更新 `MODEL_GATEWAY` 和密钥。`compliance.md` 中的禁止项只能增加，不能删除，否则生成会失败。

### 14.4 绑定自己的域名

1. Cloudflare 控制台 → Workers & Pages → 点你的项目 → Custom domains → Set up a custom domain，按提示添加域名并完成 DNS 设置。
2. 生效后，把 GitHub Variable `SITE_URL` 改为 `https://<你的域名>`。
3. 下一次部署后，RSS、sitemap 等中的网址就会使用新域名。

### 14.5 在本机检查审阅记录

提交前想先确认审阅记录格式是否正确，可以在本机运行检查（需完成第 6 章）：

1. 把 PR 描述全文复制到一个文本文件，如 `C:\Users\<用户名>\Desktop\pr-body.md`（不要放在项目文件夹里）。
2. 本机切换到 PR 的分支后执行：

   ```powershell
   .\.venv\Scripts\Activate.ps1
   git fetch origin
   python -m content_pipeline.review_gate --base origin/main --head HEAD --body-file "$env:USERPROFILE\Desktop\pr-body.md"
   ```

显示 `passed` 或 `not applicable` 表示通过；否则会逐条列出问题，对照 15.2 处理。

---

## 15. 故障排查

### 15.0 怎么看错误信息

1. 仓库顶部 Actions，点红色叉号的运行记录。
2. 点红色叉号的任务。
3. 展开红色叉号的步骤，找以 `error:`、`::error::`、`review gate:` 开头的行。

错误信息只显示出错的字段名或配置名，不会显示密钥内容，可以放心截图求助（截图前仍请确认画面中没有密钥）。

### 15.1 生成草稿失败

| 错误信息或现象 | 原因与解决 |
| --- | --- |
| `Run this workflow from the default branch` | 触发时没有选 `main` 分支，重新触发并选择 `main` |
| 提到 `topic`、`audience`、`keywords`、`prompt_name`、`prompt_version` | 该输入为空、超长或格式不对，按 11.1 表格修改 |
| `prompt not found: 名称@版本` | Prompt 名称或版本填错，或新版本还没合并到 main |
| `invalid prompt file` 或 `duplicate prompt` | `prompts/` 下有格式错误或版本重复的文件，见 14.2 |
| 列出 `MODEL_GATEWAY`、`MODEL_ID`、`MODEL_GATEWAY_API_KEY` 等名称 | 对应的 Secret 或 Variable 没添加、名字拼错，或与 `docs/compliance.md` 不一致。对照 8.2、8.3 逐个核对 |
| 列出 `BUDGET_...` 名称 | 预算变量缺失或格式不对（写了 `$`、空格或非数字） |
| 提到 `BUDGET_MAX_COST_PER_ARTICLE` 或 `BUDGET_MAX_COST_PER_RUN` 超限 | 预估费用超过上限。调低 token 上限或调高费用上限，按 8.3 公式重算 |
| HTTP 401 | OpenRouter API Key 错误或已删除，重新创建并更新 Secret |
| HTTP 402 | OpenRouter 余额不足或超过 Key 的额度上限，去充值或调高 Key 的 Credit limit |
| HTTP 404 或提示没有可用的服务商 | 模型名写错，或 OpenRouter 账号的隐私设置屏蔽了该模型的服务商，到 <https://openrouter.ai/settings/privacy> 检查 |
| HTTP 429、5xx 或超时，重试后仍失败 | 服务暂时繁忙，程序已自动重试 1 次。过几分钟再运行 |
| 文章格式校验错误（提到 `body`、`slug`、`title` 等） | AI 输出不合格，常见原因是 `BUDGET_MAX_OUTPUT_TOKENS` 太小导致截断。调大后重新运行 |
| `Generated draft is identical to the Default_Branch` | 生成的文章与 main 上已有文件完全相同，无需审阅 |
| 运行一直显示排队 | 前一个生成任务还没结束，等待即可 |

### 15.2 审阅检查 review-gate 不通过

| 错误信息 | 解决 |
| --- | --- |
| `review.xxx: review record is missing` | 描述中缺少该项，或删掉了行中反引号括起的英文名。从 `.github/pull_request_template.md` 复制原始清单重新填写 |
| `review record must appear exactly once` | 同一项写了两次，删掉多余的一行 |
| `review item must be checked [x]` | 该项还是 `[ ]`，改为 `[x]` |
| `review record text must not be empty` | 冒号后为空或只写了占位词，写上实际的检查记录 |
| `draft: is still true` | 审阅完成后按 11.9 把 `draft` 改为 `false` |
| `no draft: true -> false transition found` | PR 历史中没有“先 true 后 false”的过程，见 13.1 |
| `committed by automation` | 改为 `false` 的那次提交不是你本人做的。在网页上把它改回 `true` 提交，再改为 `false` 提交一次 |
| 提到 `pubDate`、`slug`、`sources` 等字段 | front-matter 格式错误，对照 13.3 修改 |

### 15.3 部署失败

| 错误信息或现象 | 原因与解决 |
| --- | --- |
| 合并后 Actions 中没有出现 Deploy static site | 默认分支不是 `main`，按 5.4 改名 |
| `SITE_URL must be set` | Variable `SITE_URL` 没填，或不是 `https://` 开头 |
| `CLOUDFLARE_PAGES_PROJECT is missing` | Variable 没填，或项目名含大写字母、空格 |
| `Project not found` | Pages 项目没创建，或名字与 Variable 不一致。按 7.1 用 `pages project list` 核对 |
| `Authentication error` 或 `code: 10000` | Token 权限不对或 Account ID 错误。检查 7.3 的权限设置，重新创建 Token 并更新 production 环境中的两个 Secret |
| Deploy 任务提示环境不允许部署 | production 环境的部署分支规则不是 `main`，见 8.4 |
| `Duplicate published slug` | 两篇已发布文章的 `slug` 相同，修改其中一篇 |
| `Tags ... share slug` | 两个写法不同的标签生成了相同的网址，统一标签写法 |
| `npm test` 失败 | 有人修改了代码导致测试不通过，在本机运行 `npm test` 查看详情 |
| 部署成功但文章没出现 | 检查 `draft` 是否为 `false`、日期是否带双引号并符合格式、链接是否都是 `https://`。格式不对的文章会被悄悄排除。可在本机合并后的 main 上运行 `npm run dev` 检查 |
| 网站显示旧内容 | 浏览器缓存，按 `Ctrl + F5` 强制刷新 |

部署失败时不会影响线上网站，线上会继续显示上一次成功部署的内容。

### 15.4 本机操作问题

| 现象 | 解决 |
| --- | --- |
| 命令提示“无法识别” | 安装后没重开 PowerShell，或安装时没加入 PATH。重开窗口，仍不行就重新安装（Python 注意勾选 `Add python.exe to PATH`） |
| `npm ci` 报 `Unsupported engine` | Node.js 版本低于 22.12，重新安装 LTS 版本 |
| 激活 `.venv` 时提示禁止运行脚本 | 执行 6.1 中的 `Set-ExecutionPolicy` 命令 |
| 运行 Python 命令提示 `No module named ...` | 没有激活 `.venv`，先执行 `.\.venv\Scripts\Activate.ps1` |
| `git push` 被拒绝，提示 `protected branch` | main 已受保护，这是正常的。新建分支推送后创建 PR |
| `git push` 反复要求登录 | 在弹窗中选择浏览器登录；或打开 Windows“凭据管理器”删除旧的 github.com 凭据后重试 |
| `cd` 进入路径失败 | 路径中有空格或中文时，用英文双引号把路径括起来 |

### 15.5 撤销一次发布

最稳妥的方式：打开当初合并的 PR，点页面下方的 Revert 按钮，会自动生成一个撤销 PR，按正常流程合并即可。

Cloudflare 控制台的项目页面也能回滚到之前的部署，但这样线上内容和仓库不一致，下次部署时会被覆盖，只适合应急。

---

## 16. 安全与合规须知

- 密钥只存放在 GitHub Secrets 中。不要写进代码、文章、PR 描述、聊天记录或截图。怀疑泄露时立即到 OpenRouter 或 Cloudflare 删除旧密钥，创建新密钥并更新 GitHub。
- 不要关闭分支保护，不要把任何人或应用加入 Bypass list，不要开启 “Allow GitHub Actions to create and approve pull requests”。
- 所有 AI 生成的内容都必须经过五项人工审阅才能发布，不要为了省事批量跳过审阅。
- 本项目明确禁止：规避 AI 检测或用 “humanizer” 改写、绕过平台限流、多账号、分散 IP、违反第三方服务条款的自动化操作、未经审阅的大规模分发、自动发布到其他平台。
- 不要给项目添加数据库、Redis、任务队列、VPS、Docker、Ollama 等依赖。
- 内容以读者价值和准确性为目标。AI 会编造数据和引用，事实类内容务必逐条核实。

完整规则以 [docs/compliance.md](compliance.md) 为准，修改它必须经过 PR 审阅。技术细节可参考 [README](../README.md)。

---

## 17. 附录：配置总表与常用命令

### 17.1 配置总表

| 名称 | 类型 | 在哪里设置 | 值从哪里来 |
| --- | --- | --- | --- |
| `MODEL_GATEWAY_API_KEY` | 仓库 Secret | Settings → Secrets and variables → Actions → Secrets | OpenRouter Keys 页面（4.2） |
| `MODEL_GATEWAY` | 仓库 Variable | 同上 → Variables | 固定 `openrouter` |
| `MODEL_ID` | 仓库 Variable | 同上 | 与 `docs/compliance.md` 的 `model` 一致 |
| `BUDGET_INPUT_PRICE_PER_MTOK` | 仓库 Variable | 同上 | OpenRouter 模型页 Input 价格 |
| `BUDGET_OUTPUT_PRICE_PER_MTOK` | 仓库 Variable | 同上 | OpenRouter 模型页 Output 价格 |
| `BUDGET_MAX_INPUT_TOKENS` | 仓库 Variable | 同上 | 建议 `4000` |
| `BUDGET_MAX_OUTPUT_TOKENS` | 仓库 Variable | 同上 | 建议 `4000` |
| `BUDGET_MAX_COST_PER_ARTICLE` | 仓库 Variable | 同上 | 建议 `0.01` |
| `BUDGET_MAX_COST_PER_RUN` | 仓库 Variable | 同上 | 建议 `0.02`，至少为预估费用的 2 倍 |
| `SITE_URL` | 仓库 Variable | 同上 | `https://<项目名>.pages.dev` 或自有域名 |
| `CLOUDFLARE_PAGES_PROJECT` | 仓库 Variable | 同上 | 7.1 创建的项目名 |
| `CLOUDFLARE_API_TOKEN` | production 环境 Secret | Settings → Environments → production | Cloudflare API Tokens（7.3） |
| `CLOUDFLARE_ACCOUNT_ID` | production 环境 Secret | 同上 | Cloudflare Workers & Pages 页面（7.2） |

### 17.2 常用命令

| 命令 | 作用 |
| --- | --- |
| `cd "<项目路径>"` | 进入项目文件夹 |
| `.\.venv\Scripts\Activate.ps1` | 激活 Python 环境（每个新窗口执行一次） |
| `git status` | 查看哪些文件被修改 |
| `git pull` | 把 GitHub 上的最新内容同步到本机 |
| `git switch <分支名>` | 切换到某个分支，如 `git switch main` |
| `npm run dev` | 本地预览网站，`Ctrl + C` 停止 |
| `npm run build` | 构建网站到 `dist` 文件夹 |
| `npm run test:all` | 运行全部测试 |
