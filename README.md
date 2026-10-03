# DIY Maker Hub（content-pipeline-skeleton）

最低经济投入、人工审阅后发布的静态网站：个人手作作品集 + 博客。

零基础搭建与日常操作见 [docs/user-manual.md](docs/user-manual.md)（作品集流程在第 14 章）。

- 内容的唯一手写来源是 Markdown + YAML front-matter：文章在 `src/content/articles/*.md`，作品在 `src/content/works/*.md`，作品照片在 `src/assets/works/<slug>/`。HTML 与优化后的图片只由 Astro 在构建时生成（`dist/`），仓库中没有第二份手写 HTML。
- 作品照片由作者本人通过 `npm run ingest` 导入（转正、压缩、去除 EXIF/GPS 等全部元数据）；模型看不到照片，只能根据作者的制作笔记起草作品文字。
- 草稿由 GitHub Actions 手动触发、Python 3.11+ 脚本通过**恰好一个**网关（LiteLLM、OpenRouter，或任意 OpenAI 兼容接口，如 DeepSeek）调用**恰好一个**模型生成，只写入非默认分支：文章草稿写入 `draft/<sha256>`，作品文字写入作者推送的 `work/<slug>`。
- 发布的唯一路径：编辑人员在 Pull Request 中完成五项审阅（作品与照片另加第六项 `media`）、手动将 `draft: true` 改为 `draft: false`、人工合并到默认分支，随后由部署工作流构建并发布静态站点。
- 不使用数据库、Redis、队列、VPS、Docker、Ollama 或任何动态运行时服务。基础设施月固定成本目标为 0（不含域名与按量 LLM API 费用），这只是目标，不是对任何服务价格的承诺。

## 目录

| 路径 | 用途 |
| --- | --- |
| `src/content/articles/` | 文章 Content_File（唯一文章源） |
| `src/content/works/` | 作品文件（Work_Schema，见下文“作品集”） |
| `src/assets/works/<slug>/` | 作品照片（`cover.jpg`、`01.jpg`……）与制作笔记 `notes.md` |
| `src/pages/`、`src/lib/` | Astro 路由（首页、作品、分类、文章、标签、归档、关于、`rss.xml`、`sitemap.xml`、`robots.txt`）与 schema、生产集合、排序、canonical 等纯函数 |
| `src/components/` | 作品网格、图集灯箱、点击加载的视频嵌入、分类导航与筛选、材料/工具清单（`SupplyList`）、推广披露提示（`AffiliateNotice`）、外链入口（`ExternalLinks`）等组件 |
| `src/lib/monetization.ts` | 推广链接域名 `AFFILIATE_HOSTS`、`SUPPORT_LINKS`、`SHOP_LINKS`、`AMAZON_ASSOCIATE` 开关、相关英文文案，以及给正文链接加 `rel` 的 Markdown 插件 |
| `src/lib/analytics.ts` | Cloudflare Web Analytics token 校验与脚本配置 |
| `scripts/ingest-work.mjs` | 照片导入脚本（`npm run ingest`） |
| `prompts/*.md` | 版本化 Prompt（front-matter 含 `name`、`version`）：`article-draft`、`work-draft` |
| `content_pipeline/` | Python 生成包；入口 `python -m content_pipeline.cli` |
| `docs/compliance.md` | 合规清单与机器可读策略（端点、模型、调用上限、审阅项、禁止项） |
| `.github/workflows/generate-draft.yml` | 手动生成文章草稿（仅 `workflow_dispatch`） |
| `.github/workflows/generate-work-draft.yml` | 手动起草作品文字（仅 `workflow_dispatch`） |
| `.github/workflows/review-gate.yml` | PR 只读审阅闸门检查（含作品照片元数据检查） |
| `.github/workflows/deploy.yml` | 默认分支静态部署 |
| `.github/pull_request_template.md` | 人工审阅记录模板（五项 + 作品用的 `media`） |

## 本地构建与测试

需要 Node.js >= 22.19.0（CI 使用 24.12.0）与 Python >= 3.11。

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
| `npm run ingest -- --slug <slug> --category <分类> [--title <标题>] [--cover <文件名>] [--force] <照片文件夹>` | 导入一件作品的照片，生成作品文件与笔记模板 |

构建时通过环境变量 `SITE_URL` 设置站点根 URL（必须是绝对 HTTPS URL；未设置时为 `https://example.com`）。它用于 canonical、RSS、sitemap 和 `robots.txt` 的 `Sitemap` 指令。

`draft` 缺失、非布尔或为 `true` 的文章和作品不会出现在任何页面、RSS 或 sitemap 中。不合规的条目在构建时被排除并输出警告（`[articles] excluded …` / `[works] excluded …`），不会让构建失败。

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

## 作品集

### 站点

| 路由 | 内容 |
| --- | --- |
| `/` | 最新作品封面网格、分类入口、最新文章 |
| `/works/` | 全部作品；分类筛选（链接），难度/状态筛选（页内脚本，选择保存在 URL 查询参数，无 JS 时隐藏且列出全部作品） |
| `/works/<slug>/` | 封面、作品信息（分类、难度、耗时、状态、材料、工具，可带推广链接）、正文、视频、“购买图纸”入口、图集灯箱、“支持我”入口、同分类相关作品；含推广链接时标题下显示披露提示 |
| `/articles/<slug>/` | 文章；正文含推广链接时标题下显示披露提示 |
| `/categories/`、`/categories/<category>/` | 分类索引与分类页（每个已配置分类都有页面，空分类也不会 404） |
| `/tags/<tag>/` | 同时列出带该标签的作品和文章 |
| `/about/` | 关于页（`src/pages/about.astro`，请改成自己的介绍），含店铺与“支持我”链接 |
| `/disclosure/` | 英文推广链接披露页（`src/pages/disclosure.astro`），每页页脚都有链接 |

- 照片在构建时由 `astro:assets` 生成多尺寸 WebP 与 `srcset`，非首屏懒加载。
- 作品页输出 `og:image`（1200px 宽的封面 JPEG）和 `twitter:card=summary_large_image`。
- 视频只支持哔哩哔哩与 YouTube（`youtube-nocookie.com`）。front-matter 只存校验过的视频 ID，播放器域名写死在组件里；页面先显示“播放”按钮，点击后才创建 iframe，打开页面时不向视频平台发请求。无 JS 时只显示视频页链接。
- RSS 与 sitemap 同时包含已发布的文章和作品。
- 推广链接与外链入口（`src/lib/monetization.ts`，详见用户手册 15.8）：带 `url` 的材料/工具默认是推广链接，输出 `rel="sponsored nofollow"` 和可见的 “(affiliate link)” 标注；正文中指向 `AFFILIATE_HOSTS` 的链接由 `astro.config.mjs` 中的 Sätteri hast 插件加同样的 `rel`。页面含任一推广链接时，标题下自动显示英文披露提示。`AMAZON_ASSOCIATE` 控制 Amazon 声明；`SUPPORT_LINKS`（“支持我”）和 `SHOP_LINKS`（全站店铺）显示在关于页和作品页，作品的 `shop` 优先于 `SHOP_LINKS`。列表为空时不显示。模型输入只含材料/工具名称，不含链接。
- 免 Cookie 统计：构建时设置 `PUBLIC_CF_ANALYTICS_TOKEN`（部署工作流从仓库 variable `CF_ANALYTICS_TOKEN` 读取）后，每页加载 Cloudflare Web Analytics 脚本；未设置时不加载任何第三方统计脚本。格式不对时构建失败。
- 分类定义在 `src/lib/categories.ts`，须与 `content_pipeline/work.py` 的 `CATEGORIES` 一致（有测试检查）。站点名称与简介在 `src/lib/site-meta.ts`。

### Work_Schema

作品文件 `src/content/works/<slug>.md`，文件名必须等于 `slug`。Astro 侧为 `src/lib/work-schema.ts`，Python 侧为 `content_pipeline/work.py`（额外拒绝未知字段）。

| 字段 | 规则 |
| --- | --- |
| `title`、`description` | 必填，非空字符串 |
| `pubDate`、`updatedDate` | UTC 时间戳 `YYYY-MM-DDTHH:mm:ssZ`；`updatedDate` 可选 |
| `slug` | 必填，规则同文章 |
| `draft` | 必填布尔值 |
| `category` | 必填，`categories.ts` 中的 slug 之一 |
| `cover` | 必填，`<slug>/<文件名>.(jpg\|jpeg\|png\|webp)`，小写，必须位于本作品的照片目录 |
| `coverAlt` | 必填替代文本；`待填写`、`TODO` 等占位只允许出现在草稿中 |
| `gallery` | 可选数组：`src`（规则同 `cover`）、`alt`（规则同 `coverAlt`）、可选 `caption` |
| `video` | 可选：`{ provider: bilibili, id: BV + 10 位, title }` 或 `{ provider: youtube, id: 11 位, title }` |
| `materials`、`tools` | 可选数组；每项为非空字符串，或 `{ name, url, affiliate? }`（`url` 为绝对 HTTPS，`affiliate` 默认 `true`，Python 侧拒绝未知键） |
| `shop` | 可选数组：`{ label, url }`，作者自己的图纸/文件等商品链接（绝对 HTTPS） |
| `tags` | 可选字符串数组 |
| `difficulty` | 可选：`beginner`、`intermediate`、`advanced` |
| `timeSpent` | 可选非空字符串 |
| `status` | 可选：`finished`（默认）或 `in-progress` |
| `ai_assisted` | 可选，默认 `false`；为 `true` 时 `model`、`prompt_version` 必填 |
| `sources` | 可选，规则同文章 |

正文可为空；不为空时按文章正文规则校验。引用的照片不存在时，该作品在构建时被排除。

### 照片导入

```powershell
npm run ingest -- --slug tote-bag --category sewing --title "帆布托特包" "D:\photos\tote-bag"
```

`scripts/ingest-work.mjs`（sharp）按文件名排序处理 JPEG/PNG/WebP/AVIF/TIFF（不支持 HEIC）：

- 按 EXIF 方向旋转，长边缩小到最多 2000px，转为 sRGB JPEG，并去除全部元数据（EXIF、GPS、XMP、IPTC），写入后再次确认；
- 输出 `src/assets/works/<slug>/cover.jpg`、`01.jpg`……（`--cover` 指定封面）；
- 生成 `src/content/works/<slug>.md`（`draft: true`，替代文本为 `待填写`）和笔记模板 `notes.md`；
- 已有输出时拒绝覆盖，`--force` 替换照片与作品文件，但保留已有的 `notes.md`。

### 起草作品文字（可选）

作者先把照片、`notes.md` 和作品文件推送到 `work/<slug>`，再从**默认分支**运行 “Generate work draft (manual)”（`generate-work-draft.yml`）：

| 输入 | 约束 |
| --- | --- |
| `work_slug` | 必填，Slug 规则；分支 `work/<work_slug>` 必须存在 |
| `prompt_name` | 默认 `work-draft` |
| `prompt_version` | 默认 `1.0.0` |

1. `generate`（`contents: read`，唯一持有模型密钥的步骤）：以只读方式检出 `work/<slug>`，读取作品文件（必须 `draft: true`）与 `notes.md`（去掉 HTML 注释后不能是空模板，最多 8000 字符），把作者的事实和笔记发给模型（不含照片路径），模型只返回 `description`、`tags`、`body`。其余字段由作者负责，原样保留。生成 `manifest.json` + `work.md` 草稿包。
2. `work-branch`（`contents: write`，无模型密钥）：在 `work/<slug>` 的当前内容上重新校验草稿包（Work_Schema、`draft: true`/`ai_assisted: true`、指定模型与 Prompt 版本、规范字节形式、作者字段逐一相同、稳定键），只改写并提交 `src/content/works/<slug>.md` 这一个文件；其他路径有变化即拒绝推送。推送不使用 force，作者在运行期间推送过新提交时会失败，重跑即可。

稳定键是 SHA-256(作品 slug、发给模型的事实与笔记、作者字段、Prompt 版本、模型)。笔记或任何作者字段变化后，旧草稿包不能再应用。照片不经过草稿包，也不由工作流提交。

模型会把笔记中不明确的事实写成 `[待确认：…]`；发布时残留该标记会被 review-gate 拒绝。

### 作品的审阅闸门

`review-gate` 在文章规则之外：

- 新增或修改的作品文件按 Work_Schema 校验；只有 `draft: true` 时允许占位替代文本。必须经历人工完成的 `draft: true → false`；已发布作品不能含 `[待确认`；引用的照片必须存在于 PR head。
- 凡新增或修改作品、或修改 `src/assets/works/` 下任何文件的 PR，都必须记录 `media`（图片与视频）。只改照片的 PR 只需 `media`。
- `src/assets/works/` 下每个新增或修改的文件（`content_pipeline/media_check.py`，只解析结构，不解码图片）：路径为 `<slug>/<文件>`；文件名为 `notes.md`（UTF-8，≤ 32 KiB）或小写 `[a-z0-9_-]` 的 `.jpg/.jpeg/.png/.webp`；照片 ≤ 5 MiB，字节与扩展名格式一致，且不含 JPEG APP1（EXIF/XMP）/APP13（IPTC）/COM、PNG `eXIf`/`tEXt`/`zTXt`/`iTXt`、WebP `EXIF`/`XMP ` 块。

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

- `MODEL_GATEWAY_API_KEY` 只在两个生成工作流各自的一个生成步骤（“Generate draft bundle”、“Generate work bundle”）可读；日志、草稿、PR 说明和构建产物中都不会出现其完整值（输出会做脱敏）。
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

作品走同一流程，PR 来自 `work/<slug>`，另需第六项记录 ``- [x] 图片与视频 `media`：…``（照片为本人拍摄或已获授权、替代文本描述了图片、照片已去除元数据、视频为本人作品），并满足上文“作品的审阅闸门”的检查。只改文章的 PR 不需要 `media`。

## 部署

`deploy.yml` 只在默认分支（当前为 `main`，若不同请修改 `branches`）接收 push（即 PR 合并）后运行；生成工作流推送的 `draft/*`、`work/*` 分支不会触发部署。

- `build` job（无 secret；环境变量只有 `SITE_URL` 和可选的 `PUBLIC_CF_ANALYTICS_TOKEN`）：`npm ci` → `npm test` → `npm run build` → 检查 `dist/` 中 `index.html`、`rss.xml`、`sitemap.xml`、`robots.txt` 存在 → 上传产物。
- `deploy` job（`production` 环境）：把已构建的 `dist/` 通过 Cloudflare Pages Direct Upload 发布。

需要的配置：

| 名称 | 位置 | 说明 |
| --- | --- | --- |
| `SITE_URL` | 仓库 variable | 绝对 HTTPS 站点根 URL |
| `CLOUDFLARE_PAGES_PROJECT` | 仓库 variable | Pages 项目名（Direct Upload 项目，不要连接 Git，否则草稿分支会被构建为预览） |
| `CF_ANALYTICS_TOKEN` | 仓库 variable（可选） | Cloudflare Web Analytics 站点 token；本身公开，不是 secret。为空则不加统计 |
| `CLOUDFLARE_API_TOKEN` | `production` 环境 secret | 仅授予本账号 “Cloudflare Pages: Edit” |
| `CLOUDFLARE_ACCOUNT_ID` | `production` 环境 secret | Cloudflare 账号 ID |

`production` 环境的部署分支应限制为默认分支。构建或检查任一步失败时，`deploy` 不会运行，本次部署以失败结束，托管目标继续提供之前的部署。

## 安全与合规限制

`docs/compliance.md` 是唯一合规清单，生成脚本在调用模型前读取并校验它；修改须经 PR 审阅，禁止项只能增加不能删除。要点：

- 只访问清单列出的 HTTPS 端点和指定模型；访问未列出的端点即失败。
- 禁止能力：AI 检测规避与 humanizer、平台限流绕过、多账号、分散 IP、违反第三方条款的 UI 自动化或 Selenium、未经人工审阅的大规模分发、自动跨平台分发。
- 禁止依赖：数据库、Redis、Postgres、pgvector、Prefect、任务队列、VPS、Docker、Ollama。
- 禁止持有第三方内容发布凭据。
- 站点不提供登录、评论、CMS、支付或管理后台。商品销售与打赏只通过外部平台的链接完成（`shop`、`SHOP_LINKS`、`SUPPORT_LINKS`）。
- 推广链接必须对读者可见：标为 `rel="sponsored nofollow"`，带可见标注，页面含推广链接时自动显示披露提示，并在每页页脚链接到 `/disclosure/`。不要移除这些提示，也不要用 `affiliate: false` 隐藏推广链接。`src/pages/disclosure.astro` 是模板，不是法律意见，请按实际加入的联盟计划条款核对。
- 本站不设置 Cookie。只有配置了 `CF_ANALYTICS_TOKEN` 时，页面才会加载 Cloudflare Web Analytics 的 `beacon.min.js`（第三方脚本，不设置 Cookie）。若 Cloudflare 已自动注入统计脚本，请只保留一种，避免重复计数。
- 作品照片和视频只能是作者本人拍摄或已获授权的；照片必须去除元数据（review-gate 强制检查）。模型看不到照片，不写替代文本。
- 内容以读者价值、准确性和可审阅性为目标；任何生成内容都必须经过上面的人工审阅才能发布。

