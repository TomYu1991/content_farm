# 零基础搭建与使用手册

这份手册手把手带你从一台只装了 Windows 的电脑开始，搭建一个“AI 写草稿、人工审阅后发布”的静态网站，并教你日常怎么使用。网站同时是个人手作作品集（照片、视频、材料清单）和博客（教程、随笔）。不需要编程基础，只要按顺序照做。

- 首次搭建大约需要 2～3 小时，大部分时间花在注册账号和填写配置上。
- 需要准备：一台 Windows 10/11 电脑、一个常用邮箱、一种能给 AI 模型服务商充值的付款方式（如 DeepSeek 等，金额很小）、能正常访问 GitHub、Cloudflare 和你所选模型服务商的网络。
- 每一章结尾都有“检查点”。检查点没通过就先别往下做，去第 16 章找原因。

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
14. 作品集：发布一件手作作品
15. 进阶设置
16. 故障排查
17. 安全与合规须知
18. 附录：配置总表与常用命令

---

## 1. 先了解几个概念

不用死记，遇到不懂的词回来查。

| 名词 | 通俗解释 |
| --- | --- |
| Git | 装在电脑上的“版本记录”软件，记录文件的每一次修改 |
| GitHub | 存放 Git 项目的网站，还能自动运行任务 |
| 仓库（Repository） | 一个项目的全部文件和修改历史，相当于项目文件夹 |
| 分支（Branch） | 仓库的一条“平行版本线”。`main` 是正式版本，网站就用它发布；AI 文章草稿放在 `draft/...` 分支，作品放在 `work/<作品名>` 分支，互不影响 |
| 提交（Commit） | 保存一次修改，并附上一句说明 |
| 推送（Push） | 把电脑上的提交上传到 GitHub |
| Pull Request（PR） | “请把这个分支的修改合并到 main”的申请单，审阅就在这里进行 |
| 合并（Merge） | 批准 PR 后，把修改正式并入 `main` |
| GitHub Actions / 工作流 | GitHub 上的自动化任务。本项目有 4 个：生成文章草稿、起草作品文字、审阅检查、部署网站 |
| 作品（Work） | 作品集里的一件手作：照片、材料工具、制作过程，可附视频。网址形如 `/works/<作品名>/` |
| 替代文本（alt） | 给每张照片写的一句文字描述，读屏软件会朗读它，图片加载失败时也会显示 |
| EXIF / GPS | 手机照片里隐藏的拍摄信息，可能包含拍摄地点坐标。发布前必须去掉，本项目的导入命令会自动去掉 |
| Secret | 存在 GitHub 里的保密信息（如密钥），任何人都看不到它的值 |
| Variable | 存在 GitHub 里的普通配置（如模型名称） |
| Environment | GitHub 里的“部署环境”，可以单独存放只给部署用的 Secret |
| Markdown | 一种用符号排版的纯文本格式，如 `## 标题`、`- 列表` |
| front-matter | 文章文件开头两行 `---` 之间的信息区，写标题、日期、是否草稿等 |
| 模型服务商 | 提供 AI 大模型接口的公司，如 DeepSeek、智谱、硅基流动，按用量付费 |
| OpenAI 兼容接口 | 大多数模型服务商都支持的一种通用调用格式，只要填 base_url、api_key、model 三项就能接入 |
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

作品走的是另一条相似的路：你在本机导入照片、写制作笔记，推送到 `work/<作品名>` 分支；可选地让 AI 根据笔记起草作品文字；之后同样是 PR、人工审阅（多一项“图片与视频”）、人工合并、自动部署。详见第 14 章。

AI 永远只能写草稿，而且看不到你的照片。发布一定要经过人工审阅和人工合并，这是本项目的核心规则。

---

## 2. 费用与前提条件

### 2.1 费用

| 服务 | 费用 |
| --- | --- |
| GitHub | 公开仓库免费（含 Actions 运行时间） |
| Cloudflare Pages | 有免费计划，个人博客通常够用 |
| 模型服务商（如 DeepSeek） | 按用量付费，需要先充值。一篇文章通常只花几分钱人民币（取决于模型和长度） |
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

需要安装 3 个软件：Git、Node.js（22.19 或更高版本，推荐 24 LTS）、Python（3.11 或更高版本）。

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
| `node -v` | `v24.12.0` | 不低于 `v22.19.0` |
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

### 4.2 AI 模型服务商

本项目可以接入任何提供 “OpenAI 兼容接口” 的模型服务商。你只需要从服务商那里拿到三样东西：

| 名称 | 含义 | 以 DeepSeek 为例 |
| --- | --- | --- |
| base_url | 服务商的接口地址 | `https://api.deepseek.com` |
| api_key | 你的密钥 | `sk-` 开头的一串字符 |
| model | 模型名称 | `deepseek-flash` |

另外还要记下模型的两个价格（输入、输出每百万 token 的价格），第 8 章设置费用上限时要用。

常见服务商的 base_url（写作时的信息，以各家官方文档为准）：

| 服务商 | base_url | model 在哪里找 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | [模型与价格页](https://api-docs.deepseek.com/quick_start/pricing)，如 `deepseek-flash` |
| 智谱 BigModel | `https://open.bigmodel.cn/api/paas/v4` | 控制台的模型列表 |
| 硅基流动 SiliconFlow | `https://api.siliconflow.cn/v1` | 模型广场，复制完整模型名（如 `厂商/模型名`） |
| 阿里云百炼 | 控制台中 “OpenAI 兼容” 的地址（以 `/compatible-mode/v1` 结尾） | 模型广场 |
| OpenRouter | `https://openrouter.ai/api/v1` | 模型页，如 `openai/gpt-4o-mini` |

下面以 DeepSeek 为例，其他服务商的步骤类似。

1. 打开 <https://platform.deepseek.com/>，注册并登录。
2. 充值：在左侧菜单找到“充值”，按页面支持的付款方式充值。第一次建议只充最低金额，够写很多篇文章。
3. 查看价格：打开 [模型与价格页](https://api-docs.deepseek.com/quick_start/pricing)，找到 `deepseek-flash` 这一列，记下两个数字：
   - 每百万输入 token 的价格（选 “缓存未命中 / CACHE MISS” 那行，按高峰价 PEAK 记）；
   - 每百万输出 token 的价格（按高峰价记）。

   写作时英文页面的高峰价分别约为 0.3 和 1.2 美元。按高峰价记是为了让估算宁高勿低。中文页面可能显示人民币价格，用哪种货币都可以，但第 8 章的费用上限要用同一种货币。
4. 创建 API Key：在左侧菜单找到 “API keys”，点“创建 API key”，名称填 `content-farm`，点创建。
5. 页面会显示一串以 `sk-` 开头的密钥。立刻复制，保存到安全的地方（如密码管理器）。它只显示这一次。

密钥就像银行卡密码：不要发到聊天群、不要截图、不要写进任何项目文件。泄露了就回到 API keys 页面删除它，再建一个新的。

关于“思考模式”：DeepSeek 等一些模型默认会先“思考”再回答，思考内容也会占用输出长度。所以第 8 章建议把输出上限设得宽松一些（8000）。如果生成时出现文章被截断的错误，再调大。

### 4.3 Cloudflare（网站托管）

1. 打开 <https://dash.cloudflare.com/sign-up>，用邮箱注册，完成邮箱验证。
2. 不需要购买域名，也不需要添加网站。登录能看到控制台就行。

检查点：三个账号都能登录；手里有模型服务商的 base_url、api_key、model 和两个价格数字。

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
Test Files  6 passed (6)
     Tests  60 passed (60)
...
456 passed in 7.00s
```

出现 `failed` 字样说明有问题，先不要继续，把错误信息记下来排查。

### 6.3 本地预览网站

```powershell
npm run dev
```

看到 `Local http://localhost:4321/` 后，用浏览器打开这个地址。你会看到标题为 “DIY Maker Hub”、“最新作品”下写着“暂无作品。”的首页，这是正常的，因为还没有发布任何作品或文章。顶部导航有“首页 / 作品 / 分类 / 文章 / 标签 / 关于”，都可以点开看看。网站名称和简介的改法见 15.1。

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
| `MODEL_GATEWAY_API_KEY` | 粘贴 4.2 中复制的 api_key |

点 Add secret。保存后页面只显示名字，不显示值，这是正常的。

### 8.3 添加配置变量（Variables）

同一页面切换到 Variables 标签页，点 New repository variable，逐个添加下面 11 个变量（每添加一个点一次 Add variable）。另有一个可选变量 `CF_ANALYTICS_TOKEN`（免 Cookie 统计），现在可以先不加，见 15.8。示例值以 DeepSeek 为例，用其他服务商时换成你在 4.2 拿到的值：

| Name | Value（示例） | 说明 |
| --- | --- | --- |
| `MODEL_GATEWAY` | `openai_compatible` | 固定填这个（表示 OpenAI 兼容接口） |
| `MODEL_BASE_URL` | `https://api.deepseek.com` | 4.2 中的 base_url |
| `MODEL_ID` | `deepseek-flash` | 4.2 中的 model |
| `BUDGET_INPUT_PRICE_PER_MTOK` | `0.3` | 4.2 记下的输入价格 |
| `BUDGET_OUTPUT_PRICE_PER_MTOK` | `1.2` | 4.2 记下的输出价格 |
| `BUDGET_MAX_INPUT_TOKENS` | `4000` | 输入 token 上限，用于估算费用 |
| `BUDGET_MAX_OUTPUT_TOKENS` | `8000` | AI 最多输出多少 token（含思考过程） |
| `BUDGET_MAX_COST_PER_ARTICLE` | `0.02` | 单篇费用上限（与价格同一货币） |
| `BUDGET_MAX_COST_PER_RUN` | `0.04` | 单次运行费用上限（与价格同一货币） |
| `SITE_URL` | `https://<项目名>.pages.dev` | 7.1 中显示的网站地址，必须以 `https://` 开头 |
| `CLOUDFLARE_PAGES_PROJECT` | `<项目名>` | 7.1 中创建的项目名 |

填写数字时的注意事项：

- 只写普通数字，如 `0.6`。不要写 `$`、`元`、空格、负数或 `1e-3` 这类写法。
- 两个 token 上限只能是整数。
- `MODEL_BASE_URL` 直接粘贴服务商给的地址，必须以 `https://` 开头，末尾有没有 `/` 都可以。服务商给的如果是以 `/chat/completions` 结尾的完整地址，也可以直接填。

预算是怎么算的？每次调用 AI 之前，程序会先估算最坏情况下的费用：

```text
预估费用 = (输入上限 × 输入单价 + 输出上限 × 输出单价) ÷ 1,000,000
         = (4000 × 0.3 + 8000 × 1.2) ÷ 1,000,000
         = 0.0108 美元
```

- 预估费用超过单篇上限（0.02），直接停止，不调用 AI。
- 网络出错时程序会自动重试 1 次，重试也要预留一份费用。所以单次上限（0.04）至少要是预估费用的 2 倍，才能保证重试有额度。
- 如果你的价格是人民币（例如每百万 token 2 元和 8 元），费用上限也要按人民币填，例如单篇 `0.2`、单次 `0.4`，先用公式算一遍再填。

`BUDGET_MAX_OUTPUT_TOKENS` 同时也是 AI 回答的最大长度。设得太小，文章会被截断，导致生成失败。8000 一般够写一篇中等长度的文章并留出思考空间；想要更长的文章可以调大，同时按公式调高两个费用上限。

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

### 8.5 在合规清单中登记模型地址

为了安全，程序只会访问 `docs/compliance.md` 中登记过的地址和模型。只填 GitHub 变量还不够，这里要登记一次，而且登记的内容必须和 8.3 中填的完全一致，否则生成会在调用 AI 之前失败。

如果打开文件后发现开头已经是你的服务商地址和模型（比如别人已经改好），核对一致后直接跳到检查点。

现在还没有设置分支保护（第 10 章），可以直接在网页上修改 main。如果已经设置了，就按 12.7 的方法新建分支、走 PR：

1. 在仓库文件列表中依次打开 `docs` → `compliance.md`，点右上角铅笔图标编辑。
2. 修改文件开头 `---` 之间的 4 处（以 DeepSeek 为例）：

   修改前：

   ```yaml
   gateway: openrouter
   model_endpoint: https://openrouter.ai/api/v1/chat/completions
   allowed_endpoints:
     - https://openrouter.ai/api/v1/chat/completions
   model: openai/gpt-4o-mini
   ```

   修改后：

   ```yaml
   gateway: openai_compatible
   model_endpoint: https://api.deepseek.com/chat/completions
   allowed_endpoints:
     - https://api.deepseek.com/chat/completions
   model: deepseek-flash
   ```

   规则：`model_endpoint` = 你的 base_url 末尾去掉 `/` 后加上 `/chat/completions`；`allowed_endpoints` 下写同一个地址；`model` 与 `MODEL_ID` 相同。例如硅基流动的 base_url 是 `https://api.siliconflow.cn/v1`，这里就写 `https://api.siliconflow.cn/v1/chat/completions`。

3. 往下找到 “## 1. 模型网关与允许网络端点” 这一节，把其中的 3 行同步改掉，让说明文字和上面一致：

   ```markdown
   - 网关：`openai_compatible`（`litellm`、`openrouter`、`openai_compatible` 中恰好一个；`openai_compatible` 表示任意提供 OpenAI 兼容 Chat Completions 接口的服务商）。
   - Allowed_Network_Endpoint（仅 HTTPS）：
     - `https://api.deepseek.com/chat/completions`（模型调用端点）
   - 指定模型标识：`deepseek-flash`
   ```

4. 不要改动文件中的其他内容，特别是“禁止”相关的列表，删掉任何一项都会导致生成失败。
5. 点 Commit changes...，选择 `Commit directly to the main branch`，点 Commit changes。

这次提交会自动触发一次网站部署，第 9 章会用到。

检查点：

- [ ] Actions → General 中已取消勾选 “Allow GitHub Actions to create and approve pull requests”；
- [ ] 仓库 Secret 有 1 个：`MODEL_GATEWAY_API_KEY`；
- [ ] 仓库 Variable 有 11 个，名字与 8.3 表格完全一致；
- [ ] Environments 中有 `production`，限制为 `main` 分支，并有 2 个 Secret；
- [ ] `docs/compliance.md` 中的地址和模型与 `MODEL_BASE_URL`、`MODEL_ID` 对应一致。

---

## 9. 第一次部署：让空网站上线

部署工作流只在 `main` 分支收到新提交时运行。现在还没有设置分支保护，可以直接在 `main` 上做一次小修改来触发它。

### 9.1 触发部署

8.5 中修改 `compliance.md` 的那次提交已经触发了部署，直接看 9.2 即可。如果那次部署因为配置问题失败了，修好配置后按下面的方法再触发一次：

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

如果任务出现红色叉号，点进去找到红色的步骤，展开查看以 `Error` 或 `::error::` 开头的行，然后到第 16.3 节对照处理。

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

注意：完成 11.4 之前，review-gate 检查即使是红色失败，PR 也照样能合并。这段时间里看到红色检查一定不要点合并，否则未审阅的草稿会进入 main（见 16.6）。

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

从这里开始，请严格按顺序操作，合并一定是最后一步：

```text
11.4 设必需检查 → 11.5–11.7 阅读、审阅、修改 → 11.8 填审阅记录
→ 11.9 本人把 draft 改为 false → review-gate 变绿 → 11.10 合并
```

PR 一旦合并就结束了。合并之后再往草稿分支提交任何修改（包括把 `draft` 改为 `false`），都不会进入 main，文章也不会上线。

### 11.4 添加必需检查 review-gate

PR 创建后，页面下方会出现 `review-gate` 检查，并很快显示红色失败。这是正常的：审阅记录还没填，文章也还是草稿。

现在它已经运行过一次，可以把它设为合并的必要条件了：

1. Settings → Rules → Rulesets → 点 `protect-main`。
2. 勾选 `Require status checks to pass`，点 Add checks，输入 `review-gate`，在搜索结果中选中它。
3. 页面底部点 Save changes。

以后所有 PR 都必须通过 review-gate 才能合并。这一步只需做一次，但千万不要跳过：不设置的话，检查失败的 PR 也能合并。

验证方法：回到这个 PR 页面刷新，合并按钮应变成灰色，并提示 `Required statuses must pass before merging` 之类的文字。看到这个提示说明设置生效了。

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
model: "deepseek-flash"
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
| 链接 | 正文里的每个链接都能打开，指向正确的页面。推广链接只推荐你真正用过或核实过的商品，不要让 AI 编造商品链接；用的联盟平台不在 `AFFILIATE_HOSTS` 里时先加进去（15.8），否则页面不会显示披露提示 |
| 标题 | 标题是否准确反映内容，没有夸张或误导 |

AI 草稿里常见、需要重点检查的问题：

- 来源的访问日期是编的：`sources` 里每项的 `accessedDate` 常被 AI 写成一个过去的日期，而实际上没人在那天访问过。你亲自打开核对后，把它改成核对当天的日期，如 `"2026-09-28T00:00:00Z"`。
- 正文第一行重复了标题：页面会自动把 `title` 显示为大标题。如果正文开头还有一行 `# 标题`，页面上会出现两个相同的大标题，删掉正文里那一行即可。
- 平台价格、免费额度、命令写法：这类信息变化快，要对照官方文档逐条核对，不确定的删掉或改成“以官方为准”。
- 编造的数据和引用：找不到出处的数字、原话，一律删除。

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
3. 找到审阅清单，把前五行的 `[ ]` 改为 `[x]`，并在冒号后写下你检查了什么、结论是什么。第六行“图片与视频 `media`”只用于作品和作品照片（见 14.8），只发文章时保持原样即可。
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
- 冒号后必须写内容，不能留空，也不能只写 `TODO`、`TBD`、`待填写`、`待定`、`-`、`...`。只勾 `[x]` 不写内容是最常见的失败原因；
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

然后提交到草稿分支。如果你在 11.7 还有别的修改，可以和这一改动放在同一次提交里。

这一步必须由你本人的 GitHub 账号完成。在网页上编辑就自动满足这个要求。由自动化账号（名字以 `[bot]` 结尾）做的这一改动会被 review-gate 拒绝。

### 11.10 合并发布

1. 回到 Conversation 标签页，等待 review-gate 变成绿色对勾。修改描述或推送新提交后，它会自动重新运行。review-gate 不是绿色时，不要想办法绕过，按 16.2 修好再合并。
2. 合并前最后确认一遍：Files changed 里文章的 `draft` 是 `false`。
3. 请协作者批准：对方打开 PR → Files changed → 右上角 Review changes → 选 Approve → Submit review。单人方案二可跳过这一步。
4. 点绿色 Merge pull request 按钮旁的小箭头，选 `Create a merge commit`，再点 Merge pull request → Confirm merge。不要选 Squash and merge 或 Rebase and merge，否则本地仓库之后同步时容易出现冲突。
5. 可以点 Delete branch 删除草稿分支，保持仓库整洁。

合并后，Actions 中会自动出现新的 “Deploy static site” 运行。等它变绿，打开网站首页，就能看到你的第一篇文章了。如果部署成功但文章没出现，见 16.6。

检查点：网站首页出现文章，点击能打开 `/articles/<slug>/` 页面。

恭喜，搭建全部完成。

---

## 12. 日常使用

### 12.1 发布一篇新文章（速查）

发布作品的速查见 14.11。

1. Actions → Generate draft (manual) → Run workflow → 分支选 `main` → 填 5 项 → Run。
2. 运行完成后打开 Summary 中的链接 → Create pull request。
3. Files changed 中阅读并修改文章（重点看 11.6 列出的常见问题）。
4. 编辑 PR 描述，完成五项 `[x]` 审阅记录，冒号后都要写内容。
5. 编辑文章，`draft: true` 改为 `draft: false`。
6. review-gate 变绿 → 协作者批准 → Merge pull request（选 Create a merge commit）。
7. 等 Deploy static site 完成，文章上线。

第 6 步之前的任何一步没完成，都不要合并。

### 12.2 放弃一篇草稿

草稿不满意、不想发布：

- 已经创建了 PR：在 PR 页面底部点 Close pull request，再点 Delete branch。
- 还没创建 PR：仓库首页点分支按钮 → View all branches，找到对应的 `draft/...` 分支，点右侧垃圾桶图标。

草稿永远不会出现在网站上，放着不管也没有影响。

### 12.3 重新生成的注意事项

- 用完全相同的 5 个输入重新生成，会写入同一个分支、同一个文件。如果编辑已经在修改这篇草稿，重新生成会用全新的内容覆盖掉这些修改，并把 `draft` 恢复为 `true`。所以审阅开始后，不要用相同输入重新生成。
- 如果已经重新生成了，之前的审阅作废：要把新内容从头审一遍，重新改 `draft: false`。
- 重新生成后，PR 页面上的 review-gate 不会自动重跑（自动化程序的推送不会触发检查），显示的还是旧结果，不代表当前内容。编辑一下 PR 描述或推送一次你自己的修改，它就会重新检查。
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

下线作品见 14.10。

不要用把 `draft` 改回 `true` 的方式下线。review-gate 要求 PR 中修改过的文章最终必须是 `draft: false`，这种 PR 无法通过检查。

### 12.6 怎么看花了多少钱

- 每次生成运行的日志中会输出预估费用和调用次数：Actions → 某次运行 → `Generate and validate draft` 任务 → 展开 `Generate draft bundle` 步骤。作品起草在 `Generate and validate work draft` 任务的 `Generate work bundle` 步骤。
- 实际扣费以模型服务商控制台的用量或账单页面为准（DeepSeek 在 <https://platform.deepseek.com/> 的用量信息中查看）。

### 12.7 修改代码或配置文件（新建分支 + PR）

设置分支保护后，任何修改都不能直接推送到 main。直接推送会被拒绝，报错类似：

```text
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - Changes must be made through a pull request.
! [remote rejected] main -> main (push declined due to repository rule violations)
```

这是保护规则在正常工作，不是故障。本地改了代码（比如更新了工作流、Prompt、`compliance.md`）后，按下面的步骤提交：

1. 在 PowerShell 或编辑器的终端里新建一个分支，名字自己取，如 `fix/update-config`：

   ```powershell
   git switch -c fix/update-config
   ```

   已经在 main 上提交过也没关系，新分支会带上这些提交。

2. 推送这个分支（不是 main）：

   ```powershell
   git push -u origin fix/update-config
   ```

3. 打开仓库页面，顶部会出现黄色提示条 “fix/update-config had recent pushes”，点 Compare & pull request → Create pull request。
4. 只改代码、没改文章、作品或作品照片的 PR，review-gate 会显示“不适用”并通过，描述里的审阅清单不用填。
5. 按 11.10 第 4 步选 `Create a merge commit` 合并。
6. 回到本地，同步 main 并删掉用完的分支：

   ```powershell
   git switch main
   git pull
   git branch -d fix/update-config
   ```

只改一两个文件时，也可以直接在 GitHub 网页上编辑，提交时选 `Create a new branch for this commit and start a pull request`，效果相同。

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

## 14. 作品集：发布一件手作作品

一件作品 = 你拍的照片 + 材料工具等信息 + 制作过程文字，可附一段视频。照片和事实都由你提供；AI 只能根据你的制作笔记起草文字（可选），而且看不到照片。

```text
① 本机：npm run ingest 导入照片（自动旋转、压缩、去除 GPS 等信息），生成作品文件和笔记模板
        │
② 本机：写制作笔记、填材料工具和每张照片的替代文本 → 推送到 work/<作品名> 分支
        │
③ （可选）GitHub：运行 “Generate work draft (manual)”，AI 根据笔记写简介、标签和正文
        │
④ 创建 PR → 六项审阅（多一项“图片与视频”）→ 本人改 draft: false → review-gate 变绿 → 合并
        │
⑤ 自动部署，作品出现在 /works/<作品名>/
```

本章需要第 6 章的本机环境（`npm ci` 已完成）。

### 14.1 准备照片和视频

- 选 3～10 张照片，第一张（或你指定的一张）做封面。封面最好是成品全貌，光线均匀、背景干净。
- 支持 JPEG、PNG、WebP、TIFF。iPhone 的 HEIC 格式不支持：先在“照片”App 里导出为 JPEG，或把相机设置为“兼容性最佳”。
- 把这件作品的照片单独放进一个文件夹，如 `D:\photos\tote-bag`。文件名决定顺序（`1.jpg`、`2.jpg`……按数字排序）。
- 原图不要放进项目文件夹，也不要提交到 GitHub。
- 视频不放进仓库：先上传到哔哩哔哩或 YouTube，记下视频编号。B 站是网址里 `BV` 开头的 12 位编号，如 `BV1xx411c7mD`；YouTube 是网址 `watch?v=` 后面的 11 位编号。只放你本人拍摄的视频。

### 14.2 导入照片

先想好作品名（slug），它就是网址的一部分：只用小写英文、数字和单个连字符，如 `tote-bag`、`pine-bookshelf`。

在项目文件夹中执行（PowerShell）：

```powershell
npm run ingest -- --slug tote-bag --category sewing --title "帆布托特包" "D:\photos\tote-bag"
```

| 参数 | 说明 |
| --- | --- |
| `--slug` | 作品名，见上 |
| `--category` | 分类，只能是 `3d-printing`（3D打印）、`sewing`（缝纫）、`woodworking`（木工）、`electronics`（电子DIY）、`handcraft`（手工）之一。分类可以改，见 15.6 |
| `--title` | 作品标题，之后也能在文件里改 |
| `--cover` | 可选，指定做封面的文件名，如 `--cover 3.jpg`；不填就用排在第一的照片 |
| `--force` | 可选，重新导入同一作品时用，会替换已导入的照片（已写的 `notes.md` 会保留，但作品文件会重新生成） |

命令做了这些事：

- 按拍摄方向把照片转正，长边缩小到最多 2000 像素，保存为 JPEG；
- 删除照片里的全部隐藏信息（EXIF、GPS 位置、相机序列号等），并再次检查确认已删除；
- 照片存到 `src/assets/works/tote-bag/`，命名为 `cover.jpg`、`01.jpg`、`02.jpg`……；
- 生成作品文件 `src/content/works/tote-bag.md`（`draft: true`）和制作笔记模板 `src/assets/works/tote-bag/notes.md`。

命令结尾会打印下一步提示。

### 14.3 填写作品文件和制作笔记

用编辑器打开这两个文件。

制作笔记 `notes.md`：按模板的小标题写为什么做、尺寸、步骤、踩过的坑、下次改进。只写你确定的事实，口语化也没关系。如果打算让 AI 起草文字，这里就是 AI 唯一的素材；`<!-- -->` 之间的提示文字不会发给 AI。笔记会和照片一起提交到仓库（公开仓库人人可见），不要写住址、电话等隐私。

作品文件 `tote-bag.md` 的 front-matter，需要你填写或检查的字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 作品标题 |
| `description` | 是 | 一两句话简介，用于列表和分享卡片。导入时是“待填写”，可以留给 AI 写 |
| `pubDate` | 是 | 发布时间，格式同 13.3，导入时自动填为当前时间 |
| `slug` | 是 | 作品名，必须和文件名、照片文件夹名一致，不要改 |
| `draft` | 是 | 保持 `true`，审阅完再改（14.9） |
| `category` | 是 | 分类，见 14.2 |
| `tags` | 否 | 标签，如 `["帆布", "包袋"]`。可以留给 AI 写 |
| `cover`、`coverAlt` | 是 | 封面照片和它的替代文本 |
| `gallery` | 否 | 其余照片。每张有 `src`（照片）、`alt`（替代文本，必填），可加 `caption`（显示在照片下方的说明） |
| `materials`、`tools` | 否 | 材料、工具清单，如 `["10 安帆布 1 米", "棉布内衬 0.5 米"]`。每一项也可以写成带购买链接的 `{ name: "棉织带", url: "https://..." }`，默认按推广链接处理，见 15.8 |
| `shop` | 否 | 这件作品的图纸、模型文件等自己的商品链接，如 `[{ label: "PDF pattern on Etsy", url: "https://..." }]`，见 15.8 |
| `difficulty` | 否 | 难度：`"beginner"` 入门、`"intermediate"` 进阶、`"advanced"` 高阶。去掉行首 `#` 启用 |
| `timeSpent` | 否 | 耗时，如 `"约 6 小时"` |
| `video` | 否 | 视频，如 `{ provider: "bilibili", id: "BV1xx411c7mD", title: "制作过程" }`；`provider` 只能是 `bilibili` 或 `youtube` |
| `status` | 否 | `"finished"` 已完成（默认）或 `"in-progress"` 制作中 |
| `ai_assisted`、`model`、`prompt_version` | 否 | 手写作品不用填。让 AI 起草后会自动写入，页面底部会注明“文字由 AI 辅助起草” |
| `sources` | 否 | 参考资料，格式同 13.3 |

替代文本怎么写：用一句话说清楚照片里是什么，如“橙色帆布托特包正面平放，提手竖起”“缝纫机压脚下正在缝合的内衬口袋”。不要写“图片”“照片 1”。导入时所有替代文本都是“待填写”，**还是“待填写”的作品不能发布**（草稿阶段允许）。AI 看不到照片，所以替代文本只能你来写。

正文（第二个 `---` 之后）：自己写，或者留空交给 AI（14.5）。正文规则同 13.3。

### 14.4 推送到作品分支

在 PowerShell 中执行（把 `tote-bag` 换成你的作品名）：

```powershell
git switch -c work/tote-bag
git add src/assets/works/tote-bag src/content/works/tote-bag.md
git commit -m "work: 帆布托特包 照片与笔记"
git push -u origin work/tote-bag
```

分支名必须是 `work/` 加作品名，AI 起草工作流按这个名字找你的文件。之后在本机继续修改，`git add`、`git commit`、`git push` 即可（第一次之后 `git push` 不用再加参数）。

### 14.5 （可选）让 AI 起草作品文字

1. Actions → 左侧 `Generate work draft (manual)` → Run workflow。
2. `Use workflow from` 保持 `Branch: main`。
3. 填写：`work_slug` 填作品名（如 `tote-bag`）；`prompt_name` 和 `prompt_version` 保持默认的 `work-draft` 和 `1.0.0`。
4. 点 Run workflow，等两个任务都变绿（通常 1～3 分钟）。

AI 会根据你的笔记和材料、工具、照片说明，写出简介、标签和正文，由自动化账号提交到 `work/tote-bag` 分支。你填写的其他字段（标题、照片、替代文本、材料、视频等）原样保留，AI 改不了。运行页面的 Summary 里有创建 PR 的链接。

注意：

- 运行前先把本机修改全部推送上去；工作流读的是 GitHub 上 `work/<作品名>` 分支的内容。运行后要在本机继续改，先执行 `git pull` 拿到 AI 写的内容。
- 笔记还是空模板时，工作流会拒绝运行（报 `notes.md is empty`）。
- AI 遇到笔记里没说清的地方，会写成 `[待确认：缝份宽度]` 这样的标记。发布前要把每一处都核实改掉，否则 review-gate 不通过。
- 想重写，可以改笔记后重新运行。每次重新运行都会覆盖正文、简介和标签，你在这三处的修改会丢失，所以先定好笔记、再精修文字。
- 费用和文章生成相同，使用同一套模型配置（第 8 章）。

不想用 AI，就跳过这一节，自己写好正文、简介和标签。

### 14.6 本机预览

推送前后都可以在本机看效果：

```powershell
npm run dev
```

打开 `http://localhost:4321/works/` 查看作品。草稿和格式不合规的作品不会显示。想预览草稿，临时把 `draft` 改成 `false` 再看，**看完改回 `true`，不要提交这个改动**。格式问题会显示在运行 `npm run dev` 的窗口里，形如 `[works] excluded src/content/works/tote-bag.md: coverAlt: ...`。

### 14.7 创建 PR

1. 打开 14.5 Summary 中的链接；没用 AI 的，到仓库页面点黄色提示条 `work/tote-bag had recent pushes` → Compare & pull request。
2. 确认 `base: main` ← `compare: work/tote-bag`，标题写作品名，点 Create pull request。

### 14.8 六项审阅

在 Files changed 里阅读作品文件（照片可以在文件列表中点开查看），按 11.6 的五项审阅，再加第六项：

| 审阅项 | 要检查什么 |
| --- | --- |
| 事实与来源 | AI 写的步骤、数字是否和你的笔记一致？有没有编造的内容？所有 `[待确认：…]` 都已核实改掉 |
| 读者价值 | 别人能看懂你怎么做的吗 |
| 语气 | 像你自己说话，没有夸张宣传 |
| 链接 | 正文链接能打开；`materials`、`tools`、`shop` 里的链接指向正确的商品页，推广链接确实是你用过的那款，普通链接写了 `affiliate: false` |
| 标题 | 标题准确 |
| 图片与视频 `media` | 照片都是你本人拍的（或已获授权）；每张照片的替代文本都描述了照片内容，没有“待填写”；照片是用 `npm run ingest` 导入的；视频是你本人的作品 |

按 11.7 在网页上修改，按 11.8 在 PR 描述中填写六项记录。第六项示例：

```markdown
- [x] 图片与视频 `media`：5 张照片均为本人拍摄，已用 ingest 导入，替代文本逐张核对；B 站视频为本人上传
```

review-gate 还会自动检查：

- 每张新增或修改的照片都不含 EXIF、GPS、XMP 等隐藏信息，大小不超过 5 MiB，文件名只用小写英文、数字、`_`、`-`；
- 作品引用的照片都存在；
- 发布的作品里没有“待填写”的替代文本，也没有 `[待确认` 标记。

只换了照片、没改作品文件的 PR，也必须填写第六项（其余五项可不填）。

### 14.9 改为可发布并合并

六项审阅完成后，编辑作品文件把 `draft: true` 改为 `draft: false` 并提交。这一步必须由你本人的账号完成（AI 起草工作流的提交不算）。之后按 11.10 等 review-gate 变绿、合并。部署完成后作品出现在：

- 首页“最新作品”；
- `/works/` 全部作品页（可按分类、难度、状态筛选）；
- `/categories/<分类>/` 分类页，以及标签页；
- 作品页 `/works/tote-bag/`，底部会列出同分类的其他作品。

作品页的视频不会自动加载，访客点“播放视频”后才连接哔哩哔哩或 YouTube。分享作品链接到社交平台时，会自动带上封面图。

合并后可以删除 `work/tote-bag` 分支。

### 14.10 修改或下线作品

- 修改文字或信息：和 12.4 相同，在 main 上编辑 `src/content/works/<作品名>.md`，新建分支并创建 PR，填写审阅记录（含第六项），保持 `draft: false`。
- 增加或更换照片：在本机重新导入会覆盖整个作品文件，不推荐。更简单的做法是新建分支，把新照片放到一个临时文件夹，单独运行一次 `npm run ingest -- --slug tmp-photos --category sewing "<临时文件夹>"`，把生成的 `src/assets/works/tmp-photos/01.jpg` 等文件改名移到原作品文件夹（如 `src/assets/works/tote-bag/05.jpg`），删掉 `tmp-photos` 的照片文件夹和 `src/content/works/tmp-photos.md`，再在作品文件的 `gallery` 中加上新照片和替代文本。这样新照片同样去掉了隐藏信息。
- 下线：删除 `src/content/works/<作品名>.md` 和 `src/assets/works/<作品名>/` 整个文件夹，通过 PR 合并。只删除文件的 PR 不需要审阅记录。不要用改回 `draft: true` 的方式下线（原因同 12.5）。

### 14.11 发布一件作品（速查）

1. `npm run ingest -- --slug <作品名> --category <分类> --title "<标题>" "<照片文件夹>"`
2. 写 `notes.md`；在作品文件中填材料、工具、每张照片的替代文本（可选：难度、耗时、视频）。
3. `git switch -c work/<作品名>` → `git add` → `git commit` → `git push -u origin work/<作品名>`。
4. （可选）Actions → Generate work draft (manual) → `work_slug` 填作品名 → Run。
5. 创建 PR，核对文字和 `[待确认]`，填写六项审阅记录。
6. 本人把 `draft` 改为 `false` → review-gate 变绿 → 合并。

---

## 15. 进阶设置

### 15.1 修改网站名称和简介

编辑 `src/lib/site-meta.ts`：

```ts
export const SITE_TITLE = 'DIY Maker Hub';    // 网站名称
export const SITE_DESCRIPTION = '个人手作作品集：……'; // 首页简介，也用于搜索引擎和 RSS
```

改引号里的文字，通过 PR 合并即可。只修改代码、不涉及文章的 PR 不需要填写审阅记录。

### 15.2 修改 AI 写作指令（Prompt）

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

### 15.3 更换模型或服务商

同一服务商换模型（例如从 `deepseek-flash` 换到 `deepseek-v4-pro`），改两处：

1. 通过 PR 修改 `docs/compliance.md` 开头的 `model`，并同步修改正文第 1 节中的模型名称。
2. 在 GitHub Variables 中把 `MODEL_ID` 改为相同的值，并按新模型价格更新两个单价变量，按 8.3 的公式检查费用上限。

换服务商（例如从 DeepSeek 换到硅基流动），改三处：

1. 通过 PR 按 8.5 的方法修改 `docs/compliance.md` 中的 `model_endpoint`、`allowed_endpoints`、`model` 和正文第 1 节。
2. 在 GitHub Variables 中修改 `MODEL_BASE_URL`、`MODEL_ID` 和两个单价变量。
3. 在 GitHub Secrets 中更新 `MODEL_GATEWAY_API_KEY` 为新服务商的密钥（点 Secret 右侧铅笔图标，粘贴新值后保存）。

先合并 PR，再改 Variables 和 Secret。两边不一致时，生成会在调用 AI 之前失败，不会产生费用。

`compliance.md` 中的禁止项只能增加，不能删除，否则生成会失败。

为什么要改两个地方？GitHub 变量谁有仓库设置权限就能改，而 `compliance.md` 的修改必须经过 PR 审阅、有历史记录。要求两边一致，意味着单改变量不能让程序把你的文章和密钥发到未经审阅的地址。

### 15.4 绑定自己的域名

1. Cloudflare 控制台 → Workers & Pages → 点你的项目 → Custom domains → Set up a custom domain，按提示添加域名并完成 DNS 设置。
2. 生效后，把 GitHub Variable `SITE_URL` 改为 `https://<你的域名>`。
3. 下一次部署后，RSS、sitemap 等中的网址就会使用新域名。

### 15.5 在本机检查审阅记录

提交前想先确认审阅记录格式是否正确，可以在本机运行检查（需完成第 6 章）：

1. 把 PR 描述全文复制到一个文本文件，如 `C:\Users\<用户名>\Desktop\pr-body.md`（不要放在项目文件夹里）。
2. 本机切换到 PR 的分支后执行：

   ```powershell
   .\.venv\Scripts\Activate.ps1
   git fetch origin
   python -m content_pipeline.review_gate --base origin/main --head HEAD --body-file "$env:USERPROFILE\Desktop\pr-body.md"
   ```

显示 `passed` 或 `not applicable` 表示通过；否则会逐条列出问题，对照 16.2 处理。检查会同时覆盖 PR 中的作品和作品照片（含照片隐藏信息检查）。

### 15.6 增加或修改作品分类

分类定义在 `src/lib/categories.ts`：

```ts
{ slug: 'sewing', label: '缝纫', description: '布艺、服装与包袋。' },
```

- `slug` 写在作品文件的 `category` 里，也是分类页网址 `/categories/<slug>/`，只用小写英文、数字和连字符；`label` 是显示名称；`description` 显示在分类页。
- 增加分类：照格式加一行。改名：只改 `label` 和 `description`。不要改已有作品在用的 `slug`，否则这些作品会因分类无效而不显示。
- 同时修改 `content_pipeline/work.py` 里的 `CATEGORIES`，两边的 slug 和 label 必须一致（测试会检查，不一致时 `npm run test:py` 失败）。
- 通过 PR 合并。

### 15.7 修改“关于”页面

编辑 `src/pages/about.astro`，把里面的介绍文字改成你自己的手艺背景、联系方式（建议只留公开的社交账号，不要写手机号和住址），通过 PR 合并。

关于页底部的 “My shops” 和 “Support my work” 区块不在这个文件里改，它们来自 `src/lib/monetization.ts`，见 15.8。

### 15.8 推广链接、“支持我”、“购买图纸”和统计

设置都在 `src/lib/monetization.ts`，改完通过 PR 合并。这些区块的文字是英文（面向英文读者），集中在同一文件的 `MONETIZATION_TEXT` 里，可以直接改。

**材料和工具的推广链接。** 在作品文件里把某一项写成对象：

```yaml
materials:
  - "10 安帆布 1 米"                                   # 普通文字，不带链接
  - { name: "Cotton webbing", url: "https://www.amazon.com/dp/..." }   # 推广链接
tools:
  - { name: "Rotary cutter", url: "https://example.com/...", affiliate: false }  # 普通链接
```

- 网址必须是 `https://` 开头的完整地址，两侧 schema 和 review-gate 都会检查。
- 带链接的项默认是推广链接，页面上输出 `rel="sponsored nofollow"`，并在旁边标注 “(affiliate link)”；写 `affiliate: false` 则是普通链接。
- 文章和作品正文里指向 `AFFILIATE_HOSTS`（默认是 Amazon 各站点、amzn.to、Awin、ShareASale、Rakuten、CJ）的链接会被自动加上同样的 `rel`。用了别的联盟平台，就把它的域名加进去。
- 页面只要有推广链接，标题下方就会自动显示披露提示，并链接到 `/disclosure/`。页脚每页都有这个披露页的链接。
- 加入 Amazon Associates 后，把 `AMAZON_ASSOCIATE` 改为 `true`，Amazon 要求的声明会出现在页脚、披露页和每条提示里。
- AI 起草作品文字时只会收到材料和工具的名称，看不到任何链接。

**正文里的推广链接。** 文章和作品正文照常写 Markdown 链接即可，例如 `I printed it with [this PLA](https://amzn.to/xxxx).`。只要域名在 `AFFILIATE_HOSTS` 里，构建时就会自动加上 `rel`，页面也会显示披露提示。

**“购买图纸”。** 作品文件里的 `shop` 列出这件作品自己的商品（图纸、STL 文件、材料包）：

```yaml
shop:
  - { label: "Tote bag PDF pattern on Etsy", url: "https://www.etsy.com/listing/..." }
```

它显示在作品正文和视频下方的 “Get the pattern” 区块。没填 `shop` 的作品显示全站店铺 `SHOP_LINKS`。关于页和披露页也会显示 `SHOP_LINKS`。这些是你自己的商品，不算推广链接，不会显示披露提示。

**“支持我”和全站店铺。** 在 `src/lib/monetization.ts` 里把空列表 `[]` 改成你的链接：

```ts
export const SUPPORT_LINKS: readonly ExternalLink[] = [
  { label: 'Buy me a coffee on Ko-fi', url: 'https://ko-fi.com/yourname' },
];

export const SHOP_LINKS: readonly ExternalLink[] = [
  { label: 'Sewing patterns on Etsy', url: 'https://www.etsy.com/shop/yourshop' },
];
```

`SUPPORT_LINKS` 显示在关于页、披露页和每个作品页底部的 “Support my work” 区块。列表留空时，对应区块不显示。网址同样必须以 `https://` 开头，`npm test` 会检查，不合规时部署前的测试就会失败。

**免 Cookie 统计（Cloudflare Web Analytics）。**

1. 在 Cloudflare 后台 Analytics & Logs > Web Analytics 添加站点，复制代码片段里的 `token` 值。
2. 在 GitHub 仓库 Settings > Secrets and variables > Actions > Variables 新建 variable `CF_ANALYTICS_TOKEN`，值为这个 token。它会出现在网页源码里，本来就是公开的，所以存为 variable 而不是 secret。
3. 下次部署后每个页面都会加载统计脚本，披露页的隐私说明也会自动改成“使用了 Cloudflare Web Analytics”。不设置就不加载任何统计脚本。
4. 统计数据在 Cloudflare 后台 Web Analytics 页面查看，通常几分钟后就有数据。

本机预览默认不加统计脚本。想在本机确认脚本已加入，可以临时设置变量后构建，再在 `dist/index.html` 里搜索 `cloudflareinsights`：

```powershell
$env:PUBLIC_CF_ANALYTICS_TOKEN = "<你的 token>"
npm run build
Remove-Item Env:PUBLIC_CF_ANALYTICS_TOKEN
```

如果 Cloudflare 已经自动注入了统计脚本（在 Pages 项目里开启了 Web Analytics，或者域名走了 Cloudflare 代理并开启了自动注入），就关掉那边的自动注入，或者不设置这个变量，以免同一次访问被统计两次。

披露页（`src/pages/disclosure.astro`）是一个起点，不是法律意见。请按你实际加入的联盟计划核对、修改其中的说法。

---

## 16. 故障排查

### 16.0 怎么看错误信息

1. 仓库顶部 Actions，点红色叉号的运行记录。
2. 点红色叉号的任务。
3. 展开红色叉号的步骤，找以 `error:`、`::error::`、`review gate:` 开头的行。

错误信息只显示出错的字段名或配置名，不会显示密钥内容，可以放心截图求助（截图前仍请确认画面中没有密钥）。

### 16.1 生成草稿失败

| 错误信息或现象 | 原因与解决 |
| --- | --- |
| Actions 左侧找不到 `Generate draft (manual)`，只看到 `.github/workflows/generate-draft.yml`，也没有 Run workflow 按钮 | 工作流文件有语法错误，GitHub 无法识别它。点进这条记录的 Workflow file，查看红色的 `Invalid workflow file` 提示。确认 main 上是最新代码；如果 main 上根本没有这个文件，Actions 列表里也不会出现 |
| `Run this workflow from the default branch` | 触发时没有选 `main` 分支，重新触发并选择 `main` |
| 提到 `topic`、`audience`、`keywords`、`prompt_name`、`prompt_version` | 该输入为空、超长或格式不对，按 11.1 表格修改 |
| `prompt not found: 名称@版本` | Prompt 名称或版本填错，或新版本还没合并到 main |
| `invalid prompt file` 或 `duplicate prompt` | `prompts/` 下有格式错误或版本重复的文件，见 15.2 |
| `missing configuration:` 后列出 `MODEL_GATEWAY`、`MODEL_ID`、`MODEL_BASE_URL`、`MODEL_GATEWAY_API_KEY` 等名称 | 对应的 Secret 或 Variable 没添加，或名字拼错。对照 8.2、8.3 逐个核对 |
| `invalid configuration: MODEL_BASE_URL` | 地址格式不对：必须以 `https://` 开头，不能含空格、`?` 或 `#` |
| `configuration does not match docs/compliance.md` 后列出 `MODEL_GATEWAY`、`MODEL_ID` 或 `MODEL_BASE_URL` | GitHub 变量与 `compliance.md` 登记的不一致。`MODEL_BASE_URL` 加上 `/chat/completions` 后必须与 `model_endpoint` 一字不差，按 8.5 核对 |
| `invalid Compliance_Checklist docs/compliance.md` | 修改 `compliance.md` 时格式出错或删掉了禁止项。对照 8.5 的示例检查缩进、`-` 和冒号 |
| 列出 `BUDGET_...` 名称 | 预算变量缺失或格式不对（写了 `$`、空格或非数字） |
| 提到 `BUDGET_MAX_COST_PER_ARTICLE` 或 `BUDGET_MAX_COST_PER_RUN` 超限 | 预估费用超过上限。调低 token 上限或调高费用上限，按 8.3 公式重算 |
| HTTP 400 | 服务商不接受请求，常见原因是模型名写错，或 `BUDGET_MAX_OUTPUT_TOKENS` 超过了该模型允许的最大输出。核对模型名，并查阅服务商文档中的输出上限 |
| HTTP 401 | api_key 错误、已删除，或与 base_url 不是同一家服务商。重新创建并更新 Secret |
| HTTP 402 | 账户余额不足，去服务商控制台充值 |
| HTTP 403 | 账号没有该模型的使用权限（如未实名认证或未开通），到服务商控制台处理 |
| HTTP 404 | base_url 或模型名写错。检查 base_url 是否缺少 `/v1` 等路径（以服务商文档为准），修改后 8.5 的登记也要一起改 |
| HTTP 429、5xx 或超时，重试后仍失败 | 服务暂时繁忙，程序已自动重试 1 次。过几分钟再运行 |
| 文章格式校验错误（提到 `result`、`body`、`slug`、`title` 等），或 `parse_error` | AI 输出不合格。常见原因是 `BUDGET_MAX_OUTPUT_TOKENS` 太小，思考过程占满了输出长度导致截断。调大（如 16000）并按公式调高费用上限后重新运行；也可以换一个不带思考模式的模型 |
| `Generated draft is identical to the Default_Branch` | 生成的文章与 main 上已有文件完全相同，无需审阅 |
| 运行一直显示排队 | 前一个生成任务还没结束，等待即可 |

### 16.2 审阅检查 review-gate 不通过

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
| 你已经修好了，PR 页面上的 review-gate 还是红的 | 显示的可能是旧结果（比如草稿被重新生成过，见 12.3）。编辑一下 PR 描述并保存，或推送一次修改，让它重新检查 |
| 合并按钮是灰的，提示 `Required statuses must pass` | 这是 11.4 的设置在起作用：review-gate 没通过就不能合并。按上面各行修好 |
| 合并按钮是灰的，提示需要批准（`review required`） | GitHub 不允许批准自己的 PR，见 10.3 |

### 16.3 部署失败

| 错误信息或现象 | 原因与解决 |
| --- | --- |
| 合并后 Actions 中没有出现 Deploy static site | 默认分支不是 `main`，按 5.4 改名 |
| `Install locked dependencies` 步骤失败，日志里有 `EBADENGINE`、`Unsupported engine` | 部署用的 Node.js 版本低于依赖包的要求。把 `.github/workflows/deploy.yml` 中 `node-version` 改为日志里 `required` 要求的版本或更高（当前为 `24.12.0`），按 12.7 提交 |
| `SITE_URL must be set` | Variable `SITE_URL` 没填，或不是 `https://` 开头 |
| `CLOUDFLARE_PAGES_PROJECT is missing` | Variable 没填，或项目名含大写字母、空格 |
| `Project not found` | Pages 项目没创建，或名字与 Variable 不一致。按 7.1 用 `pages project list` 核对 |
| `Authentication error` 或 `code: 10000` | Token 权限不对或 Account ID 错误。检查 7.3 的权限设置，重新创建 Token 并更新 production 环境中的两个 Secret |
| Deploy 任务提示环境不允许部署 | production 环境的部署分支规则不是 `main`，见 8.4 |
| `PUBLIC_CF_ANALYTICS_TOKEN must be a Cloudflare Web Analytics site token` | Variable `CF_ANALYTICS_TOKEN` 填错了（多了引号、空格或复制了整段代码）。只填代码片段里 `token` 后面引号中的那串字符，或删除这个变量关闭统计，见 15.8 |
| `Duplicate published slug` | 两篇已发布文章的 `slug` 相同，修改其中一篇 |
| `Tags ... share slug` | 两个写法不同的标签生成了相同的网址，统一标签写法 |
| `npm test` 失败 | 有人修改了代码导致测试不通过，在本机运行 `npm test` 查看详情 |
| 部署成功但文章没出现 | 见 16.6 |
| 网站显示旧内容 | 浏览器缓存，按 `Ctrl + F5` 强制刷新 |

部署失败时不会影响线上网站，线上会继续显示上一次成功部署的内容。

### 16.4 本机操作问题

| 现象 | 解决 |
| --- | --- |
| 命令提示“无法识别” | 安装后没重开 PowerShell，或安装时没加入 PATH。重开窗口，仍不行就重新安装（Python 注意勾选 `Add python.exe to PATH`） |
| `npm ci` 报 `Unsupported engine` 或 `EBADENGINE` | Node.js 版本低于 22.19，重新安装 LTS 版本 |
| 激活 `.venv` 时提示禁止运行脚本 | 执行 6.1 中的 `Set-ExecutionPolicy` 命令 |
| 运行 Python 命令提示 `No module named ...` | 没有激活 `.venv`，先执行 `.\.venv\Scripts\Activate.ps1` |
| `git push` 被拒绝，提示 `GH013: Repository rule violations`、`Changes must be made through a pull request` 或 `protected branch` | main 已受保护，这是正常的。按 12.7 新建分支推送，再创建 PR 合并 |
| `git push` 或 `git fetch` 提示 `Failed to connect to github.com port 443` | 网络连不上 GitHub。检查网络或代理设置后重试；编辑器自带的 Git 功能如果能连上，可以改用它推送 |
| `git pull` 后提示冲突（`CONFLICT`） | 本地和 GitHub 上都改了同一个文件。不确定怎么处理时先别继续操作，执行 `git merge --abort` 退回原状，再找人帮忙 |
| `git push` 反复要求登录 | 在弹窗中选择浏览器登录；或打开 Windows“凭据管理器”删除旧的 github.com 凭据后重试 |
| `cd` 进入路径失败 | 路径中有空格或中文时，用英文双引号把路径括起来 |

### 16.5 撤销一次发布

最稳妥的方式：打开当初合并的 PR，点页面下方的 Revert 按钮，会自动生成一个撤销 PR，按正常流程合并即可。

Revert 会把那次合并带进来的文件整个删掉。之后想重新发布这篇文章，见 16.6 的情况 C。

Cloudflare 控制台的项目页面也能回滚到之前的部署，但这样线上内容和仓库不一致，下次部署时会被覆盖，只适合应急。

### 16.6 PR 合并了、部署也成功了，文章却没上线

先确认 main 上的文章是什么状态：仓库首页（分支选 `main`）→ `src/content/articles/`。然后对照下面三种情况处理。

情况 A：文件在，但 `draft` 还是 `true`

原因：还没把 `draft` 改为 `false` 就合并了 PR。这篇文章没有经过完整审阅，现在不会显示在网站上，所以不用急着撤销。补救方法：

1. 在 main 上打开这篇文章，点铅笔图标编辑。
2. 按 11.6 把文章完整审阅一遍，需要改的地方一起改掉，最后把 `draft: true` 改为 `draft: false`。
3. Commit changes，选择 `Create a new branch for this commit and start a pull request` → Propose changes → Create pull request。
4. 在新 PR 的描述里完成五项审阅记录，review-gate 变绿后合并。

情况 B：你把 `draft` 改成了 `false`，但是在 PR 合并之后才改的

原因：PR 合并后，再往草稿分支提交的修改不会进入 main。main 上的文章仍然是 `draft: true`。按情况 A 的方法，从 main 重新改一次。

情况 C：文件根本不在

可能的原因：

- PR 没合并，还开着或被关闭了：打开 PR 页面确认。
- 合并后又被 Revert 撤销了：到仓库 Pull requests → Closed 里找标题以 `Revert` 开头的 PR。

要重新发布，可以在原来的草稿分支上重新创建 PR：点仓库顶部 Pull requests → New pull request，`base` 选 `main`，`compare` 选那个 `draft/...` 分支，然后按 11.5～11.10 走完全部流程。如果草稿分支已经删除，就重新生成一篇。

情况 D：文件在，`draft` 也是 `false`，但还是没显示

说明文章格式不合规，被悄悄排除了。按 13.3 检查：日期是否带双引号并符合格式、`slug` 是否只有小写英文、数字和连字符、正文链接是否都是 `https://` 开头。可以在本机同步 main 后运行 `npm run dev` 确认。

另外，部署需要 2～5 分钟。刚合并完就看不到文章是正常的，等 Deploy static site 变绿后再刷新（`Ctrl + F5`）。

### 16.7 作品相关问题

| 错误信息或现象 | 原因与解决 |
| --- | --- |
| `npm run ingest` 报 `--slug must be ...` 或 `--category must be one of` | 作品名或分类写错，见 14.2 |
| `npm run ingest` 报 `already exists` | 这个作品已导入过。确实要重新导入就加 `--force`（作品文件会重新生成，先备份你填过的内容；`notes.md` 会保留） |
| `npm run ingest` 报 `no JPEG/PNG/WebP/AVIF/TIFF photos` | 文件夹路径不对，或照片是 HEIC 格式。先导出为 JPEG，见 14.1 |
| `npm run ingest` 报 `Cannot find package 'sharp'` | 没有安装依赖，在项目文件夹执行 `npm ci` |
| Actions 中 Generate work draft 报 `couldn't find remote ref work/...` 或检出失败 | `work/<作品名>` 分支还没推送，或 `work_slug` 填错，见 14.4 |
| `notes.md is empty` | 笔记还是空模板，先写制作笔记再运行 |
| `has draft: false; only drafts can be generated` | 作品已改为可发布，AI 不再起草。要重写就先改回 `true` |
| `human-owned fields differ` 或 `stable_key does not match` | 工作流运行期间你又推送了修改。等运行结束，重新运行一次 |
| 推送 AI 文字时报 `rejected`（non-fast-forward） | 同上，你在 AI 运行期间推送了新提交。重新运行工作流即可 |
| review-gate：`contains photo metadata (EXIF...)` | 这张照片带有隐藏信息（可能含 GPS 位置），不是用 `npm run ingest` 导入的。删除它，按 14.10 重新导入 |
| review-gate：`file name must be lowercase ...` 或 `exceeds 5 MiB` | 照片文件名有大写、空格、中文，或照片太大。用 `npm run ingest` 导入 |
| review-gate：`coverAlt` / `gallery.N.alt`：`placeholder not allowed` | 还有“待填写”的替代文本，逐张写好，见 14.3 |
| review-gate：`body: still contains "[待确认…]"` | 正文里还有 AI 留下的待确认标记，核实后改写 |
| review-gate：`image not found in the pull request head` | 作品引用的照片不存在：文件名写错或照片没提交（`git add` 漏了文件夹） |
| review-gate：`review.media: review record is missing` | 涉及作品或照片的 PR 必须填第六项，见 14.8 |
| 合并后作品没出现在网站上 | 按 16.6 的方法排查；作品文件在 `src/content/works/`，常见原因是替代文本、`category` 或照片文件名不合规。本机 `npm run dev` 窗口会显示 `[works] excluded ...` 及原因 |
| 作品页没有视频播放框，只有“在哔哩哔哩观看”链接 | 浏览器禁用了 JavaScript，属正常降级 |
| review-gate 或 `[works] excluded`：`materials.N.url` / `tools.N.url` / `shop.N.url`：`must be an absolute HTTPS URL` | 链接必须是 `https://` 开头的完整网址，不能是 `http://`，也不能带 `用户名:密码@` |
| `materials.N` / `tools.N`：`must be a non-empty string or an object with name and url` | 这一项格式不对。写成普通文字 `"帆布"`，或 `{ name: "帆布", url: "https://..." }`，见 15.8 |
| `materials.N.name` / `shop.N.label`：`must be a non-empty string` | 带链接的项缺少显示文字：材料和工具用 `name`，`shop` 用 `label` |
| `materials.N.price`、`shop.N.title` 等：`is not a Work_Schema field` | 写了不支持的键或拼错了键名。材料和工具只支持 `name`、`url`、`affiliate`，`shop` 只支持 `label`、`url` |
| 推广链接旁边没有 “(affiliate link)”、页面没有披露提示 | 这一项写了 `affiliate: false`；或者是正文里的链接，而它的域名不在 `AFFILIATE_HOSTS` 中，见 15.8 |

---

## 17. 安全与合规须知

- 密钥只存放在 GitHub Secrets 中。不要写进代码、文章、PR 描述、聊天记录或截图。怀疑泄露时立即到模型服务商或 Cloudflare 删除旧密钥，创建新密钥并更新 GitHub。
- 不要关闭分支保护，不要把任何人或应用加入 Bypass list，不要开启 “Allow GitHub Actions to create and approve pull requests”。
- review-gate 必须设为必需检查（11.4）。不要合并 review-gate 显示红色的 PR，也不要为了能合并而删掉这项检查。
- 所有 AI 生成的内容都必须经过人工审阅（文章五项，作品六项）才能发布，不要为了省事批量跳过审阅。
- 作品集只放你本人拍摄或已获授权的照片和视频。照片一律用 `npm run ingest` 导入，它会去掉 GPS 位置等隐藏信息；不要把手机原图直接复制进仓库，也不要提交原图文件夹。
- 公开仓库里的 `notes.md`、照片、草稿人人可见，不要在其中写住址、电话、订单信息等隐私，也注意照片画面里是否露出门牌、快递单等。
- 本项目明确禁止：规避 AI 检测或用 “humanizer” 改写、绕过平台限流、多账号、分散 IP、违反第三方服务条款的自动化操作、未经审阅的大规模分发、自动发布到其他平台。
- 不要给项目添加数据库、Redis、任务队列、VPS、Docker、Ollama 等依赖。
- 推广链接必须让读者看得出来：不要删掉自动显示的披露提示、“(affiliate link)” 标注和 `/disclosure/` 页面，也不要把推广链接写成 `affiliate: false` 来隐藏。品牌付费或免费送的产品，要在页面开头写明。面向美国读者时，这是 FTC 的要求，Amazon Associates 等联盟计划也有自己的披露条款，以各计划的最新条款为准。
- 内容以读者价值和准确性为目标。AI 会编造数据和引用，事实类内容务必逐条核实。

完整规则以 [docs/compliance.md](compliance.md) 为准，修改它必须经过 PR 审阅。技术细节可参考 [README](../README.md)。

---

## 18. 附录：配置总表与常用命令

### 18.1 配置总表

| 名称 | 类型 | 在哪里设置 | 值从哪里来 |
| --- | --- | --- | --- |
| `MODEL_GATEWAY_API_KEY` | 仓库 Secret | Settings → Secrets and variables → Actions → Secrets | 模型服务商的 api_key（4.2） |
| `MODEL_GATEWAY` | 仓库 Variable | 同上 → Variables | 固定 `openai_compatible`，与 `docs/compliance.md` 的 `gateway` 一致 |
| `MODEL_BASE_URL` | 仓库 Variable | 同上 | 服务商的 base_url；加上 `/chat/completions` 后与 `compliance.md` 的 `model_endpoint` 一致 |
| `MODEL_ID` | 仓库 Variable | 同上 | 服务商的 model，与 `docs/compliance.md` 的 `model` 一致 |
| `BUDGET_INPUT_PRICE_PER_MTOK` | 仓库 Variable | 同上 | 服务商价格页的输入价格 |
| `BUDGET_OUTPUT_PRICE_PER_MTOK` | 仓库 Variable | 同上 | 服务商价格页的输出价格 |
| `BUDGET_MAX_INPUT_TOKENS` | 仓库 Variable | 同上 | 建议 `4000` |
| `BUDGET_MAX_OUTPUT_TOKENS` | 仓库 Variable | 同上 | 建议 `8000` |
| `BUDGET_MAX_COST_PER_ARTICLE` | 仓库 Variable | 同上 | 按 8.3 公式计算，DeepSeek 美元价格下建议 `0.02` |
| `BUDGET_MAX_COST_PER_RUN` | 仓库 Variable | 同上 | 至少为预估费用的 2 倍，DeepSeek 美元价格下建议 `0.04` |
| `SITE_URL` | 仓库 Variable | 同上 | `https://<项目名>.pages.dev` 或自有域名 |
| `CLOUDFLARE_PAGES_PROJECT` | 仓库 Variable | 同上 | 7.1 创建的项目名 |
| `CF_ANALYTICS_TOKEN` | 仓库 Variable（可选） | 同上 | Cloudflare Web Analytics 站点 token（15.8）；不填则不加统计 |
| `CLOUDFLARE_API_TOKEN` | production 环境 Secret | Settings → Environments → production | Cloudflare API Tokens（7.3） |
| `CLOUDFLARE_ACCOUNT_ID` | production 环境 Secret | 同上 | Cloudflare Workers & Pages 页面（7.2） |

### 18.2 常用命令

| 命令 | 作用 |
| --- | --- |
| `cd "<项目路径>"` | 进入项目文件夹 |
| `.\.venv\Scripts\Activate.ps1` | 激活 Python 环境（每个新窗口执行一次） |
| `git status` | 查看哪些文件被修改 |
| `git pull` | 把 GitHub 上的最新内容同步到本机 |
| `git switch <分支名>` | 切换到某个分支，如 `git switch main` |
| `git switch -c <新分支名>` | 新建分支并切换过去（改代码前用，见 12.7） |
| `git push -u origin <分支名>` | 把分支推送到 GitHub（不要推 main） |
| `git branch -d <分支名>` | 删除本地用完的分支 |
| `npm run dev` | 本地预览网站，`Ctrl + C` 停止 |
| `npm run build` | 构建网站到 `dist` 文件夹 |
| `npm run test:all` | 运行全部测试 |
| `npm run ingest -- --slug <作品名> --category <分类> --title "<标题>" "<照片文件夹>"` | 导入一件作品的照片，生成作品文件和笔记模板（见 14.2） |
| `npm run ingest -- --help` | 查看导入命令的全部参数 |

### 18.3 作品相关文件

| 位置 | 内容 |
| --- | --- |
| `src/content/works/<作品名>.md` | 作品文件（front-matter + 正文） |
| `src/assets/works/<作品名>/` | 作品照片（`cover.jpg`、`01.jpg`……）和制作笔记 `notes.md` |
| `src/lib/categories.ts` | 作品分类（与 `content_pipeline/work.py` 保持一致，见 15.6） |
| `src/lib/site-meta.ts` | 网站名称和简介（15.1） |
| `src/pages/about.astro` | “关于”页面（15.7） |
| `src/lib/monetization.ts` | 推广链接域名、“支持我”和店铺链接、Amazon 声明开关、相关英文文案（15.8） |
| `src/pages/disclosure.astro` | 推广链接披露页 `/disclosure/`（15.8） |
| `prompts/work-draft.md` | AI 起草作品文字的写作指令 |
| `.github/workflows/generate-work-draft.yml` | “Generate work draft (manual)” 工作流 |
