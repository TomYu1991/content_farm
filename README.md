# content-pipeline-skeleton

最低经济投入、人工审阅后发布的静态内容博客 MVP。

- 文章内容的唯一手写来源是 `src/content/articles/*.md`（Markdown + YAML front-matter）。HTML 只由 Astro 在构建时生成（`dist/`），仓库中没有第二份手写 HTML。
- 草稿由 GitHub Actions 手动触发、Python 3.11+ 脚本通过**恰好一个**网关（LiteLLM、OpenRouter，或任意 OpenAI 兼容接口，如 DeepSeek）调用**恰好一个**模型生成，只写入非默认分支 `draft/<sha256>`。
- 发布的唯一路径：编辑人员在 Pull Request 中完成五项审阅、手动将 `draft: true` 改为 `draft: false`、人工合并到默认分支，随后由部署工作流构建并发布静态站点。
- 不使用数据库、Redis、队列、VPS、Docker、Ollama 或任何动态运行时服务。基础设施月固定成本目标为 0（不含域名与按量 LLM API 费用），这只是目标，不是对任何服务价格的承诺。

## 目录

| 路径 | 用途 |
| --- | --- |
| `src/content/articles/` | 文章 Content_File（唯一文章源） |
| `src/pages/`、`src/lib/` | Astro 路由（首页、文章、标签、归档、`rss.xml`、`sitemap.xml`、`robots.txt`）与生产集合/排序/canonical 纯函数 |
| `prompts/*.md` | 版本化 Prompt（front-matter 含 `name`、`version`） |
| `content_pipeline/` | Python 生成包；入口 `python -m content_pipeline.cli` |
| `docs/compliance.md` | 合规清单与机器可读策略（端点、模型、调用上限、审阅项、禁止项） |
| `.github/workflows/generate-draft.yml` | 手动生成草稿（仅 `workflow_dispatch`） |
| `.github/workflows/review-gate.yml` | PR 只读审阅闸门检查 |
| `.github/workflows/deploy.yml` | 默认分支静态部署 |
| `.github/pull_request_template.md` | 五项人工审阅记录模板 |

## 本地构建与测试

需要 Node.js >= 22.12.0 与 Python >= 3.11。

```powershell
# Node / Astro（锁定依赖）
npm ci

# Python（锁定依赖，含测试依赖）
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

| 命令 | 作用 |
| --- | --- |
| `npm run dev` | 本地开发服务器 |
| `npm run build` | 静态构建到 `dist/` |
| `npm run preview` | 预览构建产物 |
| `npm test` | TypeScript 测试（Vitest + fast-check） |
| `npm run test:py` | Python 测试（pytest + Hypothesis + respx） |
| `npm run test:all` | 依次运行上面两组测试 |

构建时通过环境变量 `SITE_URL` 设置站点根 URL（必须是绝对 HTTPS URL；未设置时为 `https://example.com`）。它用于 canonical、RSS、sitemap 和 `robots.txt` 的 `Sitemap` 指令。

`draft` 缺失、非布尔或为 `true` 的文章不会出现在任何页面、RSS 或 sitemap 中。

## 手动生成草稿

在 GitHub 的 Actions 页面从**默认分支**运行 “Generate draft (manual)”（`generate-draft.yml`）。它只接受 `workflow_dispatch`，没有定时、push 或 PR 触发器。

| 输入 | 约束 |
| --- | --- |
| `topic` | 必填，最多 160 个 Unicode 字符 |
| `audience` | 必填，最多 160 个 Unicode 字符 |
| `keywords` | 必填，最多 300 个 Unicode 字符 |
| `prompt_name` | 必填，匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$`，最多 64 个字符；对应 `prompts/*.md` 的 `name`（如 `article-draft`） |
| `prompt_version` | 必填，匹配 `^[0-9]+\.[0-9]+\.[0-9]+$`；对应 Prompt 的 `version`（如 `1.0.0`） |

任一输入为空、超长或格式错误，所选 Prompt 不存在或格式无效，或两个 Prompt 文件有相同的 `(name, version)`，工作流都会在模型调用前失败并输出字段名或文件路径。

工作流分两个 job：

1. `generate`（`contents: read`）：校验输入 → 读取 Prompt → 校验合规策略与网关配置 → 预算检查 → 调用模型（每运行最多 2 次）→ 组装草稿并执行 Article_Schema 校验 → 生成草稿包。任何失败都在草稿包产生前结束，因此不会出现 Git 变更。
2. `draft-branch`（`contents: write`，不持有模型密钥）：再次校验草稿包，只向 `draft/<64 位十六进制>` 分支提交文章文件，并在运行摘要中输出用于创建 Pull Request 的 compare 链接。工作流不自动创建、批准或合并 PR。

### 生成的草稿

- front-matter 固定包含 `title`、`description`、`pubDate`、`tags`、`slug`、`draft: true`、`ai_assisted: true`、`model`（已配置模型）、`prompt_version`（所选版本）和 `sources`（无来源时为 `[]`），可选 `updatedDate`。
- 原始 HTML 被转义为文本；含可执行 `script` 的内容被拒绝；正文链接只能是绝对 HTTPS URL 或以 `/` 开头的站内路径；文件以无 BOM 的 UTF-8 与 LF 换行写入。

### 稳定草稿身份与幂等

`topic`、`audience`、`keywords`、`prompt_version` 和模型标识经 NFC 规范化、去首尾空白并压缩内部空白后，以 U+001F 分隔计算 SHA-256 稳定生成键：

- 分支：`draft/<稳定生成键>`
- 文件：`src/content/articles/<slug>-<稳定生成键前 12 位>.md`

相同输入重跑会落到同一分支和文件：内容不变时不产生新提交，也不会产生第二个同草稿文件。更换 Prompt 版本或模型会得到新的独立草稿。

## 网关、模型与预算配置

在 Settings > Secrets and variables > Actions 中配置：

| 名称 | 类型 | 说明 |
| --- | --- | --- |
| `MODEL_GATEWAY_API_KEY` | secret | 唯一网关凭据，只注入 `generate` job 的 “Generate draft bundle” 一个步骤 |
| `MODEL_GATEWAY` | variable | `litellm`、`openrouter` 或 `openai_compatible`，只能填一个 |
| `MODEL_ID` | variable | 单一模型标识 |
| `MODEL_BASE_URL` | variable | 服务商 base URL（如 `https://api.deepseek.com`）；`openai_compatible` 必填，其他网关可选。程序在其后拼接 `/chat/completions`（已包含时不重复） |
| `BUDGET_INPUT_PRICE_PER_MTOK` | variable | 输入单价（每百万 token） |
| `BUDGET_OUTPUT_PRICE_PER_MTOK` | variable | 输出单价（每百万 token） |
| `BUDGET_MAX_INPUT_TOKENS` | variable | 最大输入 token |
| `BUDGET_MAX_OUTPUT_TOKENS` | variable | 最大输出 token |
| `BUDGET_MAX_COST_PER_ARTICLE` | variable | 单篇成本上限 |
| `BUDGET_MAX_COST_PER_RUN` | variable | 单次工作流成本上限 |

`MODEL_GATEWAY`、`MODEL_ID` 必须与 `docs/compliance.md` front-matter 中的 `gateway`、`model` 一致，请求只发往其中列出的 `model_endpoint`（须在 `allowed_endpoints` 内，精确匹配、不跟随重定向）。配置了 `MODEL_BASE_URL` 时，`<MODEL_BASE_URL>/chat/completions` 也必须与 `model_endpoint` 完全一致，因此单改变量无法把请求发往未登记的地址。当前占位默认值为 `openrouter` / `openai/gpt-4o-mini`；更换网关或模型时，通过 PR 同时修改清单与变量。

使用 OpenAI 兼容服务商（以 DeepSeek 为例）：

| 位置 | 设置 |
| --- | --- |
| `docs/compliance.md` front-matter | `gateway: openai_compatible`、`model: deepseek-flash`、`model_endpoint` 与 `allowed_endpoints` 均为 `https://api.deepseek.com/chat/completions`，并同步正文第 1 节 |
| Variables | `MODEL_GATEWAY=openai_compatible`、`MODEL_ID=deepseek-flash`、`MODEL_BASE_URL=https://api.deepseek.com` |
| Secret | `MODEL_GATEWAY_API_KEY` = 服务商 API Key |

任一网关、模型、凭据或预算配置缺失或无效，都会在模型调用前失败，只输出配置名称。

预算在每次调用前检查，以六位固定小数（向上取整）计算：

```text
estimated_cost = (max_input_tokens × input_unit_price + max_output_tokens × output_unit_price) / 1000000
```

`estimated_cost` 超过单篇上限，或加上本次运行已预留成本超过单次上限时，阻止调用并失败。每次调用尝试（包括重试）都会预留一份 `estimated_cost`，因此若希望允许重试，`BUDGET_MAX_COST_PER_RUN` 需至少为估算值的 2 倍。成本只在运行内存中记录，不使用数据库或账本。

### 调用次数与重试

- 每次运行最多 2 次模型调用：一次调用，加最多一次重试。
- 只有首次调用因连接超时、连接中断、HTTP 429 或 HTTP 5xx 失败时才重试一次。HTTP 429 带 `Retry-After` 时按其等待时间重试；其他情况使用固定短延迟。
- 其他 HTTP 4xx、响应解析错误和 Article_Schema 校验错误直接失败，不重试。
- 成功生成并通过校验后即结束；没有自动改写、质量循环或多模型路由。

## 密钥与权限

- `MODEL_GATEWAY_API_KEY` 只在生成步骤可读；日志、草稿、PR 说明和构建产物中都不会出现其完整值（输出会做脱敏）。
- 部署凭据 `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID` 必须存为 `production` **环境** secret（不要存为仓库 secret），只由 `deploy.yml` 的发布步骤读取；生成工作流和 `review-gate` 不引用也无法读取它们。
- 所有工作流默认 `permissions: {}`，按 job 授予最小权限。生成工作流不授予 `pull-requests` 权限，因此其令牌不能批准 PR；`review-gate` 仅有 `contents: read`、`pull-requests: read`。
- `contents: write` 无法限定到分支，因此必须在默认分支上配置分支保护作为强制防线：
  - 要求通过 Pull Request 合并，并至少一位人工批准；
  - 将 `review-gate` 设为必需状态检查；
  - 不允许 GitHub Actions 绕过保护，并在 Settings > Actions > General 中关闭 “Allow GitHub Actions to create and approve pull requests”。

## 人工审阅与发布

生成的文章始终是 `draft: true`，只存在于 `draft/<sha256>` 分支。发布步骤全部由人完成：

1. 打开工作流运行摘要中的 compare 链接，以默认分支为目标创建 Pull Request（描述使用 `.github/pull_request_template.md`）。
2. 逐项审阅，并在 PR 描述中勾选 `[x]`、在冒号后写下审核记录（不可留空或写 TODO）：
   - 事实与来源 `facts_and_sources`
   - 读者价值 `reader_value`
   - 语气 `tone`
   - 链接 `links`
   - 标题 `title`
3. 五项完成后，编辑人员手动把文章 front-matter 的 `draft: true` 改为 `draft: false`，并提交到该 PR 分支。
4. `review-gate` 检查五项记录齐全、文章为 `draft: false`，且该变更由非自动化提交完成。它只报告通过/失败，不批准、不合并、不发布。
5. 人工批准并人工合并 PR。这是唯一发布路径。

## 部署

`deploy.yml` 只在默认分支（当前为 `main`，若不同请修改 `branches`）接收 push（即 PR 合并）后运行；生成工作流推送的 `draft/*` 分支不会触发部署。

- `build` job（无 secret）：`npm ci` → `npm test` → `npm run build` → 检查 `dist/` 中 `index.html`、`rss.xml`、`sitemap.xml`、`robots.txt` 存在 → 上传产物。
- `deploy` job（`production` 环境）：把已构建的 `dist/` 通过 Cloudflare Pages Direct Upload 发布。

需要的配置：

| 名称 | 位置 | 说明 |
| --- | --- | --- |
| `SITE_URL` | 仓库 variable | 绝对 HTTPS 站点根 URL |
| `CLOUDFLARE_PAGES_PROJECT` | 仓库 variable | Pages 项目名（Direct Upload 项目，不要连接 Git，否则草稿分支会被构建为预览） |
| `CLOUDFLARE_API_TOKEN` | `production` 环境 secret | 仅授予本账号 “Cloudflare Pages: Edit” |
| `CLOUDFLARE_ACCOUNT_ID` | `production` 环境 secret | Cloudflare 账号 ID |

`production` 环境的部署分支应限制为默认分支。构建或检查任一步失败时，`deploy` 不会运行，本次部署以失败结束，托管目标继续提供之前的部署。

## 安全与合规限制

`docs/compliance.md` 是唯一合规清单，生成脚本在调用模型前读取并校验它；修改须经 PR 审阅，禁止项只能增加不能删除。要点：

- 只访问清单列出的 HTTPS 端点和指定模型；访问未列出的端点即失败。
- 禁止能力：AI 检测规避与 humanizer、平台限流绕过、多账号、分散 IP、违反第三方条款的 UI 自动化或 Selenium、未经人工审阅的大规模分发、自动跨平台分发。
- 禁止依赖：数据库、Redis、Postgres、pgvector、Prefect、任务队列、VPS、Docker、Ollama。
- 禁止持有第三方内容发布凭据。
- 站点不提供登录、评论、CMS、支付或管理后台。
- 内容以读者价值、准确性和可审阅性为目标；任何生成内容都必须经过上面的人工审阅才能发布。

测试站点部署
