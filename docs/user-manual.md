# 用户使用手册

本手册面向三类使用者：

| 角色 | 主要工作 | 对应章节 |
| --- | --- | --- |
| 维护者 | 首次配置仓库、密钥、分支保护和托管 | 第 2 章、第 8 章 |
| 内容运营 | 手动触发 AI 草稿生成 | 第 3 章 |
| 编辑 | 审阅草稿、手动改为可发布、合并 PR | 第 4、5 章 |

技术细节（草稿身份算法、调用重试规则等）见 [README](../README.md)，合规规则以 [compliance.md](compliance.md) 为准。

---

## 1. 系统概览

这是一个人工审阅后才能发布的静态博客。

```text
运营在 GitHub Actions 手动触发生成
        │
        ▼
generate-draft.yml ──► 调用 1 个模型（最多 2 次）──► 推送到 draft/<64 位哈希> 分支
        │
        ▼
编辑手动创建 PR ──► 五项人工审阅 ──► 手动 draft: true → false
        │
        ▼
review-gate 检查通过 + 人工批准 ──► 人工合并到 main
        │
        ▼
deploy.yml 构建 Astro 静态站 ──► Cloudflare Pages
```

几个固定规则：

- 文章唯一来源是 `src/content/articles/*.md`。
- AI 只生成 `draft: true` 的草稿，永远不会直接写入 `main`，也不会创建、批准或合并 PR。
- 只有 `draft: false` 且格式有效的文章会出现在站点、RSS 和 sitemap 中。
- 发布的唯一途径是人工合并 PR。

站点页面：

| 地址 | 内容 |
| --- | --- |
| `/` | 首页文章列表 |
| `/articles/<slug>/` | 文章页 |
| `/tags/`、`/tags/<标签>/` | 标签索引与标签页 |
| `/archive/` | 按年份归档 |
| `/rss.xml`、`/sitemap.xml`、`/robots.txt` | 订阅与搜索引擎文件 |

---

## 2. 首次配置（维护者）

以下配置只需做一次。全部完成后再让运营和编辑开始使用。

### 2.1 模型网关与预算

在 GitHub 仓库 Settings > Secrets and variables > Actions 中添加：

| 名称 | 类型 | 填写说明 | 示例 |
| --- | --- | --- | --- |
| `MODEL_GATEWAY_API_KEY` | Secret | 网关 API Key | （保密） |
| `MODEL_GATEWAY` | Variable | `openrouter` 或 `litellm`，只能填一个 | `openrouter` |
| `MODEL_ID` | Variable | 单个模型标识，不能含空格或逗号 | `openai/gpt-4o-mini` |
| `BUDGET_INPUT_PRICE_PER_MTOK` | Variable | 每百万输入 token 单价 | `0.15` |
| `BUDGET_OUTPUT_PRICE_PER_MTOK` | Variable | 每百万输出 token 单价 | `0.60` |
| `BUDGET_MAX_INPUT_TOKENS` | Variable | 最大输入 token（整数） | `4000` |
| `BUDGET_MAX_OUTPUT_TOKENS` | Variable | 最大输出 token（整数） | `3000` |
| `BUDGET_MAX_COST_PER_ARTICLE` | Variable | 单篇成本上限 | `0.01` |
| `BUDGET_MAX_COST_PER_RUN` | Variable | 单次运行成本上限 | `0.02` |

注意：

- 示例价格仅用于演示格式，请以网关当前实际报价为准。
- 金额只能写普通小数（如 `0.6`），不能写 `$`、负数或科学计数法（如 `1e-3`）。
- `MODEL_GATEWAY` 和 `MODEL_ID` 必须与 `docs/compliance.md` 顶部的 `gateway`、`model` 完全一致，否则生成会在调用模型前失败。

预算估算公式：

```text
预估成本 = (最大输入 token × 输入单价 + 最大输出 token × 输出单价) ÷ 1,000,000
```

按上面的示例：`(4000 × 0.15 + 3000 × 0.60) ÷ 1,000,000 = 0.002400`。

每次调用（含重试）都会预留一份预估成本。若希望网络错误时能重试一次，`BUDGET_MAX_COST_PER_RUN` 至少要设为预估成本的 2 倍。

### 2.2 部署到 Cloudflare Pages

1. 在 Cloudflare 创建一个 Pages 项目，选择 Direct Upload（直接上传）。不要连接 Git，否则 `draft/*` 分支会被构建为公开预览。
2. 在 Cloudflare 创建 API Token，权限只授予本账号的 “Cloudflare Pages: Edit”。
3. 在 GitHub 仓库 Settings > Environments 创建名为 `production` 的环境：
   - Deployment branches 限制为默认分支（`main`）。
   - 添加环境 Secret `CLOUDFLARE_API_TOKEN` 和 `CLOUDFLARE_ACCOUNT_ID`。必须放在环境里，不要放在仓库 Secret 中。
4. 在仓库 Variables 中添加：
   - `SITE_URL`：站点根地址，必须以 `https://` 开头，如 `https://blog.example.org`。
   - `CLOUDFLARE_PAGES_PROJECT`：Pages 项目名（小写字母、数字、连字符）。

如果默认分支不是 `main`，需要修改 `.github/workflows/deploy.yml` 中的 `branches`。

### 2.3 分支保护（必须）

生成工作流有写仓库的权限，分支保护是防止它绕过人工审阅的最终防线。

在 Settings > Branches（或 Rules）为 `main` 设置：

- 要求通过 Pull Request 合并；
- 至少 1 位人工批准；
- 将 `review-gate` 设为必需状态检查；
- 不允许 GitHub Actions 绕过规则。

在 Settings > Actions > General 中，关闭 “Allow GitHub Actions to create and approve pull requests”。

### 2.4 配置自检

- [ ] 模型 Secret 与 8 个变量已填写；
- [ ] `MODEL_GATEWAY` / `MODEL_ID` 与 `docs/compliance.md` 一致；
- [ ] `production` 环境及两个 Cloudflare Secret 已配置；
- [ ] `SITE_URL`、`CLOUDFLARE_PAGES_PROJECT` 已配置；
- [ ] 分支保护与 Actions 设置已完成。

---

## 3. 生成 AI 草稿（运营）

### 3.1 操作步骤

1. 打开仓库的 Actions 页面，选择左侧 “Generate draft (manual)”。
2. 点击 Run workflow，分支选择默认分支（`main`）。选择其他分支会直接失败。
3. 填写输入并运行：

| 输入 | 要求 | 示例 |
| --- | --- | --- |
| `topic` 选题 | 必填，最多 160 字 | 如何为个人博客选择静态托管 |
| `audience` 读者 | 必填，最多 160 字 | 第一次搭建博客的独立开发者 |
| `keywords` 关键词 | 必填，最多 300 字 | 静态站点, Cloudflare Pages, 部署成本 |
| `prompt_name` | 必填，小写字母、数字和连字符 | `article-draft` |
| `prompt_version` | 必填，`主.次.修订` 格式 | `1.0.0` |

4. 等待运行结束（通常几分钟）。打开运行记录的 Summary，里面有创建 PR 的 compare 链接，把它交给编辑。

同一时间只会运行一个生成任务。运行中再次触发的任务会等待；若连续触发多次，GitHub 只保留最新一个等待中的任务，更早的等待任务会被取消。

### 3.2 运行结果说明

| 情况 | 结果 |
| --- | --- |
| 成功，新草稿 | 新建 `draft/<哈希>` 分支，提交一篇文章 |
| 成功，输入与之前完全相同且内容无变化 | 不产生新提交，日志显示 “Draft content unchanged” |
| 成功，输入相同但模型生成了不同内容 | 在同一分支、同一文件上追加一次提交 |
| 更换了 Prompt 版本或模型 | 生成一个新的独立草稿分支 |
| 失败 | 不会产生任何分支或文件，日志中给出出错的字段或配置名 |

草稿文件路径形如 `src/content/articles/<slug>-<哈希前12位>.md`，front-matter 中会自动写入 `draft: true`、`ai_assisted: true`、所用模型和 Prompt 版本。

注意：编辑已开始审阅某篇草稿后，不要再用完全相同的输入重新生成。重跑会用新生成的内容覆盖同一分支上的文件（包括编辑的修改，并恢复为 `draft: true`）。如需另一个版本，请修改选题或关键词。

### 3.3 写好输入的建议

- 选题要具体。“静态博客托管选择”比“博客”更容易生成有价值的内容。
- 读者画像写清楚对方的水平和目的。
- 关键词只写真正相关的几个，模型被要求自然使用，而不是堆砌。

---

## 4. 审阅与发布（编辑）

### 4.1 创建 PR

1. 打开运营提供的 compare 链接，目标分支为 `main`，点击 Create pull request。
2. PR 描述会自动带出审阅模板。保留模板中的五项清单。

此时 `review-gate` 会显示失败，这是正常的：五项记录还没填，文章仍是 `draft: true`。

### 4.2 五项人工审阅

逐项检查文章，并在 PR 描述里勾选 `[x]`、在冒号后写下具体记录：

| 审阅项 | 检查要点 |
| --- | --- |
| 事实与来源 `facts_and_sources` | 核实数据、结论和引用；`sources` 中的链接真实存在且支持文中说法。模型可能编造来源，必须逐条打开确认 |
| 读者价值 `reader_value` | 对目标读者是否有实际帮助，是否有空话或关键词堆砌 |
| 语气 `tone` | 是否与站点风格一致，没有夸大和误导 |
| 链接 `links` | 正文链接都能打开且指向正确页面 |
| 标题 `title` | 标题准确反映内容，不做标题党 |

填写示例：

```markdown
- [x] 事实与来源 `facts_and_sources`：核对了 3 处数据与 2 个来源链接，删除 1 处无法证实的说法
- [x] 读者价值 `reader_value`：补充了部署步骤示例，适合初次搭建者
- [x] 语气 `tone`：去掉两处夸张用语
- [x] 链接 `links`：5 个链接均可访问，替换 1 个过期链接
- [x] 标题 `title`：改为更具体的“个人博客静态托管的三种选择”
```

填写规则：

- 每项必须勾选 `[x]`，并且只能出现一次；
- 冒号后不能为空，也不能写 `TODO`、`TBD`、`待填写`、`待定`、`-`、`...`；
- 行内保留反引号括起的英文键名（如 `` `tone` ``），检查靠它识别；
- 写在 `<!-- -->` 注释里的内容不计入。

修改 PR 描述后，`review-gate` 会自动重新运行。

### 4.3 修改文章内容

审阅中发现问题可以直接修改文章：在 PR 的 Files changed 中编辑，或在本地检出 `draft/<哈希>` 分支修改后推送。修改内容时请遵守第 6 章的格式要求。

### 4.4 改为可发布

五项审阅都完成后，由编辑本人把文章 front-matter 中的

```yaml
draft: true
```

改为

```yaml
draft: false
```

并提交到该 PR 分支。

这一步必须用你自己的 GitHub 账号提交。由自动化账号（名称以 `[bot]` 结尾）提交的改动会被 `review-gate` 拒绝。

### 4.5 合并发布

1. 确认 `review-gate` 通过。
2. 请另一位有权限的成员批准 PR（按分支保护要求）。
3. 人工点击合并。

合并后 “Deploy static site” 工作流自动运行，成功后新文章即上线。可在 Actions 中查看部署进度。

### 4.6 不发布的草稿

如果草稿不值得发布，直接关闭 PR 并删除对应的 `draft/<哈希>` 分支即可。草稿不会出现在站点上。

---

## 5. 维护已发布文章（编辑）

所有修改都要走 PR。只要 PR 新增或修改了 `src/content/articles/` 下的文件，就必须在描述中填写五项审阅记录。

| 操作 | 做法 |
| --- | --- |
| 修改已发布文章 | 从 `main` 新建分支修改，保持 `draft: false`，建议添加或更新 `updatedDate`，PR 中填写五项记录 |
| 下线文章 | 新建分支删除该文章文件，通过 PR 合并。只删除文件的 PR 不受审阅闸门约束 |
| 修改 slug | 会改变文章网址，旧链接将失效，谨慎操作 |

注意：不要用把 `draft` 改回 `true` 的方式下线文章。`review-gate` 要求 PR 中改动的文章最终为 `draft: false`，这样的 PR 无法通过检查。

---

## 6. 手写文章

也可以不用 AI，直接手写文章。

### 6.1 文件位置与命名

- 放在 `src/content/articles/` 目录下，不能放子目录；
- 文件名只能用小写字母、数字和连字符，以 `.md` 结尾，如 `static-hosting-guide.md`；
- 使用 UTF-8 编码、LF 换行。

### 6.2 文章模板

```markdown
---
title: "个人博客静态托管的三种选择"
description: "比较三种常见静态托管方式的部署流程与限制。"
pubDate: "2026-09-26T08:00:00Z"
tags: ["静态站点", "部署"]
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

正文使用 Markdown……
```

### 6.3 字段说明

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `title` | 是 | 非空文本 |
| `description` | 是 | 非空文本，一两句话 |
| `pubDate` | 是 | UTC 时间，格式 `YYYY-MM-DDTHH:mm:ssZ`，必须加引号 |
| `updatedDate` | 否 | 格式同 `pubDate` |
| `tags` | 是 | 文本数组，可以为 `[]`，支持中文 |
| `slug` | 是 | 小写字母、数字和单个连字符，最长 80 字符，决定网址 `/articles/<slug>/` |
| `draft` | 是 | `true` 或 `false` |
| `ai_assisted` | 是 | 是否使用 AI 辅助，`true` 或 `false` |
| `model` | 是 | 非空文本；手写文章可填 `"none"` |
| `prompt_version` | 是 | 非空文本；手写文章可填 `"none"` |
| `sources` | 是 | 来源数组，可以为 `[]`；每项需 `title`、`url`（https）、`accessedDate`（UTC 时间） |

正文规则：

- 不能为空，最长 100,000 字符；
- 不能包含 `<script>`；
- 链接只能是 `https://` 开头的完整地址，或以 `/` 开头的站内路径（如 `/tags/`）；
- 建议不写原始 HTML，只用标准 Markdown。

### 6.4 发布手写文章

审阅闸门要求 PR 历史中存在 “先 `draft: true`、后由人工改为 `draft: false`” 的过程，手写文章同样适用：

1. 从 `main` 新建分支，以 `draft: true` 提交文章；
2. 创建 PR，按第 4 章完成五项审阅；
3. 再提交一次，把 `draft` 改为 `false`；
4. `review-gate` 通过、人工批准后合并。

如果第一次提交就是 `draft: false`，`review-gate` 会报 “no draft: true -> false transition found”。

---

## 7. 管理 Prompt

Prompt 存放在 `prompts/*.md`，当前内置 `article-draft`，版本 `1.0.0`。

新增或修改 Prompt：

1. 不要直接修改已使用过的版本。复制一份新文件，并提升版本号：

   ```markdown
   ---
   name: article-draft
   version: 1.1.0
   description: 说明本版本的变化。
   ---
   这里是给模型的写作指令……
   ```

2. 规则：
   - `name` 只用小写字母、数字和连字符，最长 64 字符；
   - `version` 为 `主.次.修订` 格式；
   - 正文不能为空；
   - 任意两个文件的 `(name, version)` 不能重复。
3. 通过 PR 合并到 `main` 后，运营在生成时填写新的 `prompt_version` 即可使用。

`prompts/` 下任一文件格式错误，所有生成任务都会失败，因此请在 PR 中仔细检查。

---

## 8. 更换模型或网关（维护者）

需要同时修改两处，缺一不可：

1. 通过 PR 修改 `docs/compliance.md`：
   - front-matter 中的 `gateway`、`model`、`model_endpoint`，并把新端点加入 `allowed_endpoints`；
   - 同步更新正文第 1 节说明；
   - 禁止项只能增加，不能删除，否则生成会失败。
2. 在 GitHub Variables 中更新 `MODEL_GATEWAY`、`MODEL_ID`，必要时更新 `MODEL_GATEWAY_API_KEY` 和预算单价。

端点必须是 HTTPS，并按完整字符串精确匹配。更换模型后，相同选题会生成新的独立草稿，不会覆盖旧草稿。

---

## 9. 本地开发与预览（开发者）

需要 Node.js 22.12.0 或更高版本、Python 3.11 或更高版本。

```powershell
# 安装依赖
npm ci
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

| 命令 | 作用 |
| --- | --- |
| `npm run dev` | 启动本地开发服务器，默认地址 `http://localhost:4321` |
| `npm run build` | 构建静态站点到 `dist/` |
| `npm run preview` | 预览构建结果 |
| `npm test` | 运行前端测试 |
| `npm run test:py` | 运行 Python 测试 |
| `npm run test:all` | 运行全部测试 |

本地预览只显示 `draft: false` 的文章。想看草稿的页面效果，可以在本地临时改为 `false`，但不要提交这次改动。

### 9.1 本地检查审阅闸门

提交 PR 前可以在本地模拟 `review-gate`：

```powershell
# 把 PR 描述保存到仓库外的临时文件，再运行检查
python -m content_pipeline.review_gate --base origin/main --head HEAD --body-file "$env:TEMP\pr-body.md"
```

退出码 0 表示通过或不适用，1 表示未通过（错误原因输出在终端），2 表示读取 Git 或配置出错。

### 9.2 本地生成草稿（可选）

本地生成会真实调用模型并产生费用，一般直接使用 GitHub Actions 即可。确需本地调试时：

```powershell
$env:GEN_TOPIC = "如何为个人博客选择静态托管"
$env:GEN_AUDIENCE = "第一次搭建博客的独立开发者"
$env:GEN_KEYWORDS = "静态站点, Cloudflare Pages"
$env:GEN_PROMPT_NAME = "article-draft"
$env:GEN_PROMPT_VERSION = "1.0.0"
$env:MODEL_GATEWAY = "openrouter"
$env:MODEL_ID = "openai/gpt-4o-mini"
$env:MODEL_GATEWAY_API_KEY = Read-Host "Gateway API key"
$env:BUDGET_INPUT_PRICE_PER_MTOK = "0.15"
$env:BUDGET_OUTPUT_PRICE_PER_MTOK = "0.60"
$env:BUDGET_MAX_INPUT_TOKENS = "4000"
$env:BUDGET_MAX_OUTPUT_TOKENS = "3000"
$env:BUDGET_MAX_COST_PER_ARTICLE = "0.01"
$env:BUDGET_MAX_COST_PER_RUN = "0.02"

python -m content_pipeline.cli generate --bundle-dir "$env:TEMP\draft-bundle" --policy docs/compliance.md --prompts-dir prompts
```

生成结果在 `$env:TEMP\draft-bundle\article.md`（文章）和 `manifest.json`（草稿身份）。不要把 API Key 写进脚本或提交到仓库；用完后关闭终端，或执行 `Remove-Item Env:MODEL_GATEWAY_API_KEY` 清除。

---

## 10. 常见问题排查

### 生成工作流

| 现象 | 原因与处理 |
| --- | --- |
| “Run this workflow from the default branch” | 触发时选择了非默认分支，改选 `main` |
| 报错中出现 `topic`、`keywords` 等字段名 | 输入为空、超长或格式不对，按 3.1 表格修正 |
| `prompt not found: 名称@版本` | 名称或版本填错，或该版本尚未合并到 `main` |
| `invalid prompt file` / `duplicate prompt` | `prompts/` 下有格式错误或重复版本的文件，通过 PR 修复 |
| 报错列出 `MODEL_GATEWAY`、`MODEL_ID` 或 `BUDGET_*` 等名称 | 变量缺失、格式错误，或与 `compliance.md` 不一致 |
| 预算超限（提到 `BUDGET_MAX_COST_PER_ARTICLE` 或 `_PER_RUN`） | 预估成本超过上限，调低最大 token 或调高上限 |
| HTTP 401/403 等 4xx 错误 | API Key 无效或无权限，不会重试，检查 Secret |
| 429/5xx/超时后仍失败 | 已自动重试 1 次，稍后重新触发即可 |
| Schema 校验错误 | 模型输出不符合文章格式，重新运行或调整 Prompt |
| “Generated draft is identical to the Default_Branch” | 生成的文章与 `main` 上已有文件完全相同，无需审阅 |

### 审阅闸门 review-gate

| 提示 | 处理 |
| --- | --- |
| `review.<键名>: review record is missing` | 描述中缺少该项，或删掉了行内的反引号键名 |
| `must appear exactly once` | 同一项写了多次，只保留一行 |
| `must be checked [x]` | 该项未勾选 |
| `review record text must not be empty` | 冒号后为空或只写了占位词 |
| `draft: is still true` | 审阅完成后把 `draft` 改为 `false` |
| `no draft: true -> false transition found` | PR 历史中没有先 `true` 后 `false` 的过程，见 6.4 |
| `committed by automation` | 改 `false` 的提交来自机器人账号，请用本人账号重新提交这一改动 |
| 字段校验错误（如 `pubDate`、`slug`） | 按第 6.3 节修正 front-matter |

### 部署与站点

| 现象 | 原因与处理 |
| --- | --- |
| “SITE_URL must be set” | 未设置或不是 `https://` 开头 |
| “CLOUDFLARE_PAGES_PROJECT is missing” | 未设置或项目名格式不对 |
| 构建失败，提示 `Duplicate published slug` | 两篇已发布文章的 `slug` 相同，修改其中一篇 |
| 构建失败，提示 `Tags ... share slug` | 两个不同标签生成了相同网址，统一标签写法 |
| 合并后文章没有出现在站点 | 检查 `draft` 是否为 `false`、日期是否带引号且为 UTC 格式、正文链接是否符合规则。不合格的文章会被静默排除而不报错，可本地运行 `npm run build` 后查看 |
| 部署失败后站点状态 | 任一步失败都不会部署，线上继续使用上一次成功的版本 |

需要撤销一次上线时，最稳妥的方式是对相应 PR 执行 Revert 并按正常流程合并；Cloudflare Pages 控制台也提供回滚到之前部署的功能，但回滚后仓库与线上会不一致，下次部署时会被覆盖。

---

## 11. 安全与合规须知

- API Key 和 Cloudflare 凭据只存放在 GitHub Secrets 中，不要写入代码、文章、PR 或聊天记录。
- 不要关闭分支保护，不要为 GitHub Actions 开启创建或批准 PR 的权限。
- 所有 AI 生成内容必须经过五项人工审阅才能发布，不能批量跳过审阅。
- 本项目明确禁止：规避 AI 检测或 “humanizer” 改写、绕过平台限流、多账号、分散 IP、违反第三方条款的自动化操作、未经审阅的大规模分发、自动跨平台发布。
- 禁止引入数据库、Redis、任务队列、VPS、Docker、Ollama 等依赖。
- 内容以读者价值和准确性为目标。事实性内容请务必核实来源，AI 可能编造数据和引用。

完整规则以 [docs/compliance.md](compliance.md) 为准，修改该文件必须经过 PR 审阅。

---

## 附录：速查

发布一篇 AI 草稿的完整流程：

1. Actions → Generate draft (manual) → 选 `main` → 填写 5 个输入 → Run
2. 打开运行 Summary 中的 compare 链接 → 创建 PR
3. 审阅并修改文章 → 在 PR 描述中完成五项 `[x]` 记录
4. 本人提交 `draft: true` → `draft: false`
5. `review-gate` 通过 → 他人批准 → 人工合并
6. 等待 Deploy static site 成功 → 上线
