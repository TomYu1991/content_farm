# Requirements Document

## Introduction

本文档定义 `content-pipeline-skeleton` 的最低经济投入静态内容博客 MVP。MVP 以 Git 仓库中的 Markdown 文件及其 YAML front-matter 作为文章内容的唯一手写来源；Astro 在构建时将 Markdown 编译为 HTML，HTML 仅为构建产物，不保存第二份手写 HTML。

MVP 使用 Astro 构建静态站点，并可部署至已配置的静态托管目标。GitHub Actions 仅由 `workflow_dispatch` 手动触发；Python 3.11+ 脚本通过单一且可配置的 LiteLLM、OpenRouter 或 OpenAI 兼容 API 网关生成草稿。生成结果仅可成为非默认分支上的可审阅变更；人工审阅、将 `draft` 改为 `false` 并合并 Pull Request 是唯一发布路径。

MVP 的基础设施月固定成本目标为 0，不含域名费用和按量计费的 LLM API 费用。该目标不构成对 Cloudflare、GitHub 或任何商业服务价格的承诺。MVP 不要求 grounding；每个 Content_File 仍必须包含可为空的 `sources` 数组。本文档聚焦内容生产、审阅与静态发布闭环，不引入数据库、队列、服务器或动态运行时服务。

## Glossary

- **MVP_System**：本 MVP 的静态内容博客、生成脚本、自动化工作流和合规清单的整体。
- **Content_Repository**：保存站点源代码、Content_File 和版本化 Prompt 的 Git 仓库。
- **Content_File**：Content_Repository 中带有 YAML front-matter 的 Markdown 文章文件，是文章内容的唯一手写来源。
- **Front-matter**：Content_File 开头由 `---` 包围的 YAML 元数据块。
- **Article_Schema**：Content_File 的路径、文件名、front-matter 和 Markdown 正文必须满足的结构、类型和格式规则。
- **Markdown_Body**：Content_File 中 Front-matter 之后的 CommonMark 正文。
- **Slug**：由小写 ASCII 字母、数字和单个连字符组成、长度为 1 至 80 个字符，且匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$` 的文章 URL 标识。
- **UTC_Timestamp**：以 `YYYY-MM-DDTHH:mm:ssZ` 表示的 ISO 8601／RFC 3339 UTC 日期时间字符串。
- **Source_Item**：`sources` 数组中的对象，包含非空 `title`、HTTPS `url` 和 UTC_Timestamp 格式的 `accessedDate`。
- **Draft_Article**：front-matter 中 `draft` 为 `true` 的 Content_File，不属于生产站点可发布文章集合。
- **Publishable_Article**：front-matter 中 `draft` 为 `false` 且通过 Article_Schema 校验的 Content_File。
- **Production_Article_Set**：Astro 为生产构建收集的 Publishable_Article 集合。
- **Canonical_URL**：由 Site_URL_Setting 与 Publishable_Article 的发布路径确定的绝对 HTTPS URL。
- **Site_URL_Setting**：静态站点配置中的绝对 HTTPS 站点根 URL。
- **Prompt_Store**：读取 `prompts/*.md` 中版本化 Prompt 的组件。
- **Prompt_Version**：Prompt 文件 YAML front-matter 中匹配 `^[0-9]+\.[0-9]+\.[0-9]+$` 的 `version` 值。
- **Model_Gateway**：通过 LiteLLM、OpenRouter 或 任意 OpenAI 兼容接口（由 base URL 指定，且须登记在 Compliance_Checklist 中）访问单一已配置模型的接口。
- **Generation_Workflow**：由 GitHub Actions 执行、接收人工输入并调用 Python 生成脚本的工作流。
- **Budget_Controller**：在模型调用前按配置估算并比较单篇与单次工作流成本上限的组件。
- **Git_Change_Manager**：在非 Default_Branch 创建或更新可供人工审阅的内容变更的组件。
- **Workflow_Token**：Generation_Workflow 用于写入其生成分支以及在实现自动创建 Pull Request 时创建 Pull Request 的令牌。
- **Human_Editorial_Gate**：要求人工审阅事实与来源、读者价值、语气、链接和标题，并将 Draft_Article 改为 Publishable_Article 后合并 Pull Request 的强制闸门。
- **Static_Site**：由 Astro 构建的静态网站。
- **Deployment_Pipeline**：在 Default_Branch 合并后构建并发布 Static_Site 的流程。
- **Retryable_Network_Error**：连接超时、连接中断、HTTP 429 或 HTTP 5xx 导致的 Model_Gateway 调用失败。
- **Default_Branch**：Content_Repository 配置为发布来源的主分支。
- **Compliance_Checklist**：`docs/compliance.md` 中可验证的 MVP 合规清单。
- **Allowed_Network_Endpoint**：Compliance_Checklist 明确列出的 HTTPS 网络端点。

## Requirements

### Requirement 1: 静态站点与零固定成本部署

**User Story:** 作为站点维护者，我想以静态站点部署内容，以便在不购买 VPS 和不维护运行时服务的条件下发布文章。

#### Acceptance Criteria

1. THE Static_Site SHALL 使用 Astro 在构建时将 Production_Article_Set 的 Markdown_Body 编译为 HTML 页面。
2. WHEN Default_Branch 接收已合并的内容变更，THE Deployment_Pipeline SHALL 构建并发布 Static_Site 至已配置的静态托管目标。
3. IF 生产构建失败，THEN THE Deployment_Pipeline SHALL 保留该次构建开始前已可访问的部署，并以失败状态结束该次部署。
4. THE Content_Repository SHALL 将 Content_File 作为文章内容的唯一手写来源，并将 HTML 限定为 Astro 构建产物。
5. THE MVP_System SHALL 将基础设施月固定成本目标设为 0，且该目标不计域名费用和按量计费的 LLM API 费用。
6. THE MVP_System SHALL 不运行用于提供文章内容的动态运行时服务。

### Requirement 2: P0 阅读与发现体验

**User Story:** 作为读者，我想在桌面与移动设备上发现和阅读文章，以便获得清晰、可索引的内容体验。

#### Acceptance Criteria

1. THE Static_Site SHALL 提供首页、文章页、标签页、归档页、`/rss.xml`、`/sitemap.xml` 和 `/robots.txt`。
2. WHEN Static_Site 构建 `/rss.xml`，THE Static_Site SHALL 输出 RSS 2.0 文档，并为每个 Production_Article_Set 文章输出标题、描述、`pubDate` 和 Canonical_URL。
3. WHEN Static_Site 构建 `/sitemap.xml`，THE Static_Site SHALL 输出 XML Sitemap 文档，并仅列出 Production_Article_Set 文章的 Canonical_URL。
4. WHEN Static_Site 构建 `/robots.txt`，THE Static_Site SHALL 输出指向由 Site_URL_Setting 确定的 `/sitemap.xml` 的 `Sitemap` 指令。
5. WHEN Static_Site 构建首页、标签页、归档页、`/rss.xml` 或 `/sitemap.xml`，THE Static_Site SHALL 仅使用 Production_Article_Set 中的文章。
6. WHEN Static_Site 输出首页、标签页、归档页或 `/rss.xml` 中的文章集合，THE Static_Site SHALL 按 `pubDate` 降序排列文章，并按 Canonical_URL 升序排列 `pubDate` 相同的文章。
7. WHEN Production_Article_Set 为空，THE Static_Site SHALL 输出不含文章项的首页、标签页、归档页、`/rss.xml` 和 `/sitemap.xml`。
8. WHEN Static_Site 构建 Publishable_Article 的文章页，THE Static_Site SHALL 输出该文章的标题、描述、发布日期、Canonical_URL 和 Open Graph 元数据。
9. WHEN 键盘焦点进入标签页，THE Static_Site SHALL 允许通过键盘焦点与 Enter 键访问每个标签链接。
10. WHILE 视口宽度为 320 至 768 CSS 像素，THE Static_Site SHALL 显示正文文本、标题和链接，且正文阅读不需要水平滚动。
11. THE Static_Site SHALL 不提供登录、评论、CMS、支付或管理后台功能。

### Requirement 3: 版本化 Prompt 与手动触发输入

**User Story:** 作为内容运营者，我想手动输入选题、读者画像和关键词并使用可追溯 Prompt，以便以低成本生成可审阅的草稿。

#### Acceptance Criteria

1. WHEN 操作者通过 `workflow_dispatch` 触发 Generation_Workflow，THE Generation_Workflow SHALL 接收 `topic`、`audience`、`keywords`、`prompt_name` 和 `prompt_version` 输入。
2. IF `topic`、`audience`、`keywords`、`prompt_name` 或 `prompt_version` 为空，THEN THE Generation_Workflow SHALL 以失败状态结束并输出缺失输入名称。
3. IF `topic` 或 `audience` 长度超过 160 个 Unicode 字符，THEN THE Generation_Workflow SHALL 以失败状态结束并输出超长输入名称。
4. IF `keywords` 长度超过 300 个 Unicode 字符，THEN THE Generation_Workflow SHALL 以失败状态结束并输出超长输入名称。
5. IF `prompt_name` 不匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$` 或长度超过 64 个字符，THEN THE Generation_Workflow SHALL 以失败状态结束并输出无效输入名称。
6. IF `prompt_version` 不匹配 `^[0-9]+\.[0-9]+\.[0-9]+$`，THEN THE Generation_Workflow SHALL 以失败状态结束并输出无效输入名称。
7. WHEN Prompt_Store 读取被选定的 Prompt，THE Prompt_Store SHALL 从 `prompts/*.md` 读取匹配 `prompt_name` 和 Prompt_Version 的 Prompt 正文及其 YAML front-matter。
8. IF 被选定的 Prompt 缺少 `name` 或 `version`、格式无效或不存在，THEN THE Prompt_Store SHALL 以失败状态结束并输出 Prompt 路径或所选标识。
9. IF 两个 Prompt 文件具有相同的 `name` 和 Prompt_Version，THEN THE Prompt_Store SHALL 以失败状态结束并输出冲突文件路径。
10. IF Model_Gateway 缺少单一模型标识、网关配置或访问凭据，THEN THE Generation_Workflow SHALL 在模型调用前以失败状态结束并输出缺失配置名称。
11. WHEN Generation_Workflow 调用 Model_Gateway，THE Generation_Workflow SHALL 使用 Python 3.11 或更高版本的脚本通过 LiteLLM、OpenRouter 或 OpenAI 兼容接口中恰好一个已配置的 API 网关访问单一已配置模型。
12. WHILE MVP 未启用定时生成，THE Generation_Workflow SHALL 仅接受 `workflow_dispatch` 触发。
13. WHEN Generation_Workflow 输出日志，THE Generation_Workflow SHALL 排除 API 密钥及其完整值。

### Requirement 4: 草稿结构、校验与编码

**User Story:** 作为编辑，我想获得结构一致且可校验的 Markdown 草稿，以便在 Pull Request 中高效审阅内容。

#### Acceptance Criteria

1. WHEN Model_Gateway 返回生成结果，THE Generation_Workflow SHALL 生成一个 Content_File，其 Front-matter 包含 `title`、`description`、`pubDate`、`tags`、`slug`、`draft`、`ai_assisted`、`model`、`prompt_version` 和 `sources` 字段。
2. WHERE 生成结果包含更新时间，THE Generation_Workflow SHALL 在 Content_File 的 Front-matter 中写入 `updatedDate` 字段。
3. THE Generation_Workflow SHALL 将新生成 Content_File 的 `draft` 设为 `true`、`ai_assisted` 设为 `true`、`model` 设为已配置模型标识，并将所选 Prompt_Version 写入 `prompt_version`。
4. THE Generation_Workflow SHALL 在每个 Content_File 中写入 `sources` 数组，且在没有来源时写入空数组。
5. WHEN Generation_Workflow 校验 `sources`，THE Generation_Workflow SHALL 接受空数组，并为每个非空 Source_Item 验证非空 `title`、HTTPS `url` 和 UTC_Timestamp 格式的 `accessedDate`。
6. WHEN Generation_Workflow 校验 Content_File，THE Generation_Workflow SHALL 验证 `title` 和 `description` 为非空字符串、`pubDate` 与存在的 `updatedDate` 为 UTC_Timestamp、`tags` 为字符串数组、`slug` 为 Slug、`draft` 与 `ai_assisted` 为布尔值、`model` 与 `prompt_version` 为非空字符串且 `sources` 为数组。
7. WHEN Generation_Workflow 校验 Content_File，THE Generation_Workflow SHALL 验证 Content_File 路径位于配置内容目录内、文件名匹配 `^[a-z0-9][a-z0-9-]{0,99}\.md$`、路径不含 `..` 段，且路径解析后不离开配置内容目录。
8. WHEN Generation_Workflow 校验 Markdown_Body，THE Generation_Workflow SHALL 验证正文非空、长度不超过配置的最大字符数，并验证每个链接目标为绝对 HTTPS URL 或以 `/` 开头的站内绝对路径。
9. WHEN 生成结果包含原始 HTML，THE Generation_Workflow SHALL 将原始 HTML 转义为文本后写入 Markdown_Body。
10. WHEN Generation_Workflow 校验 Markdown_Body，THE Generation_Workflow SHALL 拒绝包含可执行 `script` 元素的 Content_File。
11. IF Content_File 未通过 Article_Schema 校验，THEN THE Generation_Workflow SHALL 以失败状态结束并输出校验字段或链接位置，且不得创建或改动可审阅草稿变更。
12. THE Generation_Workflow SHALL 以无 BOM 的 UTF-8 编码和 LF 换行符写入 Content_File。

### Requirement 5: 稳定的草稿变更与最小 GitHub 权限

**User Story:** 作为内容运营者，我想安全地重跑相同生成请求，以便重复执行不会制造相同草稿的副本。

#### Acceptance Criteria

1. WHEN Article_Schema 校验成功，THE Git_Change_Manager SHALL 使用以明确分隔符连接的、经 NFC 规范化、去首尾空白并压缩内部空白的 `topic`、`audience`、`keywords`、Prompt_Version 和模型标识计算 SHA-256 稳定生成键。
2. WHEN Git_Change_Manager 处理稳定生成键，THE Git_Change_Manager SHALL 使用 `draft/<稳定生成键>` 作为生成分支，并使用 `src/content/articles/<slug>-<稳定生成键前12个十六进制字符>.md` 作为 Content_File 路径。
3. WHEN 相同稳定生成键再次触发 Generation_Workflow，THE Git_Change_Manager SHALL 选择相同的生成分支和 Content_File 路径。
4. WHEN 相同稳定生成键再次触发 Generation_Workflow，THE Git_Change_Manager SHALL 更新既有 Content_File 或保持既有 Content_File 不变，且不得增加第二个表示相同草稿的 Content_File。
5. WHEN 生成的 Content_File 与目标路径的已有文件内容相同，THE Git_Change_Manager SHALL 不创建额外提交。
6. WHEN Prompt_Version 或模型标识变化，THE Git_Change_Manager SHALL 使用由变化后的输入计算出的稳定生成键创建或更新独立草稿变更。
7. WHEN Git_Change_Manager 成功写入或更新 Content_File，THE Git_Change_Manager SHALL 产生指向非 Default_Branch 的可审阅 Pull Request 或清晰的 Pull Request 创建说明。
8. IF Git_Change_Manager 未能产生非 Default_Branch 的可审阅结果，THEN THE Generation_Workflow SHALL 以失败状态结束并输出失败原因。
9. THE Workflow_Token SHALL 仅拥有向 Generation_Workflow 创建或选定的非 Default_Branch 内容分支写入的权限，以及在实现自动创建 Pull Request 时所需的最小 Pull Request 创建权限。
10. THE Workflow_Token SHALL 不拥有向 Default_Branch 写入、合并 Pull Request 或批准 Pull Request 的权限。
11. THE Git_Change_Manager SHALL 不要求 MVP 采用自动创建 Pull Request 的特定 GitHub API。

### Requirement 6: 预算预估与受限重试

**User Story:** 作为项目负责人，我想在调用模型前限制成本并仅重试暂时性网络故障，以便控制按量 API 支出。

#### Acceptance Criteria

1. THE Budget_Controller SHALL 配置输入单价、输出单价、最大输入 token、最大输出 token、单篇成本上限和单次工作流成本上限。
2. WHEN Generation_Workflow 准备调用 Model_Gateway，THE Budget_Controller SHALL 以六位固定小数计算 `estimated_cost = (max_input_tokens × input_unit_price + max_output_tokens × output_unit_price) / 1000000`，其中单价单位为每百万 token。
3. IF 输入单价、输出单价、最大输入 token、最大输出 token、单篇成本上限或单次工作流成本上限缺失，THEN THE Budget_Controller SHALL 在模型调用前以失败状态结束 Generation_Workflow 并输出缺失配置名称。
4. IF `estimated_cost` 超过单篇成本上限，THEN THE Budget_Controller SHALL 阻止 Model_Gateway 调用并以失败状态结束 Generation_Workflow。
5. IF `estimated_cost` 加上本次运行已预留成本超过单次工作流成本上限，THEN THE Budget_Controller SHALL 阻止 Model_Gateway 调用并以失败状态结束 Generation_Workflow。
6. WHEN Model_Gateway 的首次调用因 HTTP 429 失败且响应包含 `Retry-After`，THE Generation_Workflow SHALL 在 `Retry-After` 指定的等待时间后发起唯一一次重试调用。
7. WHEN Model_Gateway 的首次调用因 Retryable_Network_Error 且不属于带有 `Retry-After` 的 HTTP 429 失败，THE Generation_Workflow SHALL 发起唯一一次重试调用。
8. IF Model_Gateway 调用因其他 HTTP 4xx、响应解析错误或 Article_Schema 校验错误失败，THEN THE Generation_Workflow SHALL 以失败状态结束且不得发起重试调用。
9. WHILE 一次 Generation_Workflow 运行已调用 Model_Gateway 两次，THE Generation_Workflow SHALL 以失败状态结束且不得发起额外模型调用。
10. THE Generation_Workflow SHALL 不执行自动内容改写、质量循环或多模型路由。
11. WHEN Generation_Workflow 输出日志，THE Generation_Workflow SHALL 排除 API 密钥及其完整值。
12. THE Budget_Controller SHALL 不要求使用数据库、账本、队列或并发事务记录成本。

### Requirement 7: 强制人工审阅与受限发布权限

**User Story:** 作为项目负责人，我想让人工编辑控制所有发布，以便未核实的生成内容不会自动对外发布。

#### Acceptance Criteria

1. THE Generation_Workflow SHALL 将所有新生成 Content_File 标记为 Draft_Article。
2. WHEN Static_Site 收集 Production_Article_Set，THE Static_Site SHALL 防御性排除 `draft` 缺失、`draft` 值非法或 `draft` 为 `true` 的 Content_File。
3. WHEN 编辑人员准备发布 Draft_Article，THE Human_Editorial_Gate SHALL 要求编辑人员审阅事实与来源、读者价值、语气、链接和标题。
4. WHEN 编辑人员确认 Human_Editorial_Gate 的五项审阅项目，THE Human_Editorial_Gate SHALL 在该文章的 Pull Request 中保留事实与来源、读者价值、语气、链接和标题各自的审核记录。
5. WHEN 编辑人员完成 Human_Editorial_Gate 审阅，THE Human_Editorial_Gate SHALL 要求编辑人员将 `draft` 从 `true` 修改为 `false` 并通过 Pull Request 合并至 Default_Branch。
6. THE Generation_Workflow SHALL 不自动发布 Content_File。

### Requirement 8: Markdown 编译语义与基础 SEO

**User Story:** 作为读者和搜索引擎，我想让发布页准确呈现 Markdown 的结构和元数据，以便内容可读且可发现。

#### Acceptance Criteria

1. WHEN Astro 编译 Publishable_Article，THE Static_Site SHALL 按 CommonMark 语义编译 Markdown_Body。
2. WHEN Astro 编译 Publishable_Article，THE Static_Site SHALL 将原始 HTML 转义为文本，且不得在文章 HTML 中输出可执行 `script` 元素。
3. WHEN Astro 编译 Publishable_Article，THE Static_Site SHALL 将 Markdown 标题编译为具有相同层级顺序的 HTML 标题元素。
4. WHEN Astro 编译 Publishable_Article，THE Static_Site SHALL 将 Markdown 链接编译为具有相同目标 URL 的 HTML 链接元素。
5. WHEN Astro 编译 Publishable_Article，THE Static_Site SHALL 使 HTML 提取的纯文本在折叠连续空白后与 Markdown_Body 提取的纯文本相等。
6. WHEN Static_Site 构建 Publishable_Article 的文章页，THE Static_Site SHALL 使用 Site_URL_Setting 和该文章发布路径生成 Canonical_URL。
7. WHEN Static_Site 输出 HTML 元数据，THE Static_Site SHALL 转义来自 Content_File 的 `title`、`description`、`pubDate` 和 tags 元数据值。
8. THE Static_Site SHALL 从 Content_File 的 Markdown_Body 生成 HTML，且不得要求维护第二份手写 HTML 内容。

### Requirement 9: 合规边界与读者价值

**User Story:** 作为项目负责人，我想在需求中固定合规边界，以便内容自动化服务读者而非操纵平台或规避规则。

#### Acceptance Criteria

1. THE MVP_System SHALL 在 `docs/compliance.md` 中维护 Compliance_Checklist。
2. THE Compliance_Checklist SHALL 列出 Allowed_Network_Endpoint、指定模型标识、每次 Generation_Workflow 运行的模型调用上限、Human_Editorial_Gate 审核要求、禁止依赖和禁止持有的第三方发布凭据。
3. IF Generation_Workflow 尝试访问未列入 Compliance_Checklist 的网络端点，THEN THE Generation_Workflow SHALL 阻止该网络访问并以失败状态结束。
4. WHEN Generation_Workflow 调用 Model_Gateway，THE Generation_Workflow SHALL 仅使用 Compliance_Checklist 指定的模型标识和 Allowed_Network_Endpoint。
5. WHEN Generation_Workflow 生成内容，THE Generation_Workflow SHALL 以读者价值、准确性和可审阅性为目标。
6. WHEN 一次 Generation_Workflow 运行完成一次成功生成和 Article_Schema 校验，THE Generation_Workflow SHALL 结束内容生成，且仅可按 Requirement 6 对 Retryable_Network_Error 发起唯一一次额外模型调用。
7. THE Compliance_Checklist SHALL 将 AI 检测规避与 humanizer、平台限流绕过、多账号、分散 IP、违反第三方条款的 UI 自动化或 Selenium、未经 Human_Editorial_Gate 审核的大规模分发及自动跨平台分发列为禁止能力。
8. THE Compliance_Checklist SHALL 将数据库、Redis、Postgres、pgvector、Prefect、任务队列、VPS、Docker 和 Ollama 列为 MVP 禁止依赖，并将第三方内容发布凭据列为 MVP 禁止持有凭据。

## Out of Scope / 延后启用

以下能力不属于 MVP，不应在 MVP 实现中引入。除表中明确的触发条件外，MVP 不自动启用任何延后能力。

| 能力 | MVP 状态 | 延后启用触发条件 |
| --- | --- | --- |
| GitHub Actions 每周定时生成 1–2 篇草稿 | 延后 | 人工确认已具备稳定审阅能力并显式启用定时工作流时 |
| Tally | 延后 | 上线后需要选题或反馈表单时 |
| PostHog | 延后 | 至少已经发布内容且出现真实访问后，需要分析阅读和外链点击时 |
| Resend | 延后 | 存在合法订阅者并已建立确认订阅流程时 |
| Cloudflare Worker 与 Turnstile | 延后 | 需要自建公开写接口时 |
| D1 或 Supabase（两者择一） | 延后 | 需要持久化表单、订阅者或用户数据时 |
| Upstash Redis | 延后 | 公开 API 出现滥用或需要限流时 |
| Sentry | 延后 | 出现动态后端或复杂客户端故障且需要观测时 |

以下技术和能力明确不在 MVP 范围内：数据库、Redis、Postgres、pgvector、Prefect、任务队列、VPS、Docker、Ollama、第二份手写 HTML、登录、评论、CMS、支付、管理后台、AI 检测规避、humanizer、平台限流绕过、多账号、分散 IP、违反第三方条款的后台 UI 自动化，以及未经审核的大规模或自动跨平台分发。

## PBT/测试策略附录

下表列出设计阶段应优先实现的七类可测试性质。属性测试仅覆盖本项目的纯逻辑或内存替身；静态托管、GitHub 权限、外部 API 网关和网络端点使用少量集成测试或配置审查。

| 编号 | 行为类别与关键性质 | 测试类型 | 对应验收标准 |
| --- | --- | --- | --- |
| P1 | 对任意 front-matter、路径、文件名和正文输入，Article_Schema 当且仅当全部字段类型、UTC 日期、Slug、来源结构、路径安全、正文长度、链接格式和脚本限制有效时接受 Content_File。 | 属性测试：校验与错误条件 | 4.5–4.12 |
| P2 | 对任意 Publishable_Article 集合，首页、标签页、归档页与 RSS 仅含 Production_Article_Set，按发布日期降序并以 Canonical_URL 解决同日顺序；对空集合产生空文章项集合。 | 属性测试：集合、排序与空值不变量 | 2.5–2.7、7.2 |
| P3 | 对任意工作流输入和 Prompt 清单，空值、超长值、格式错误、缺失模型配置或重复 Prompt 标识均在模型调用前失败；有效选定标识唯一解析到一个 Prompt。 | 属性测试：输入边界与唯一选择 | 3.1–3.11 |
| P4 | 对任意有效 CommonMark，原始 HTML 经转义后不产生可执行脚本，且编译 HTML 的标题层级序列、链接目标序列和归一化纯文本分别与 Markdown_Body 对应序列一致。 | 属性测试：转义与变形关系 | 4.9、4.10、8.1–8.5 |
| P5 | 对任意规范化输入，稳定生成键、生成分支和 Content_File 路径保持确定；相同键重复执行不增加文件，内容相同不增加提交，Prompt_Version 或模型标识改变时生成不同键。 | 属性测试：确定性与幂等性 | 5.1–5.6 |
| P6 | 对任意配置成本和错误序列，缺失或超预算调用在访问 Model_Gateway 前被拒绝；仅 Retryable_Network_Error 可额外调用一次，带 `Retry-After` 的 HTTP 429 优先使用该等待时间，任意运行最多两次模型调用。 | 属性测试：预算、重试状态机与边界 | 6.1–6.10、9.6 |
| P7 | 对任意生成和审阅事件序列，工作流仅访问白名单端点和指定模型，不直接写入 Default_Branch、不合并或批准 Pull Request，且只有保留五项审核记录并将 `draft` 设为 `false` 的文章可进入发布路径。 | 属性测试：权限、合规与发布闸门不变量 | 5.9、5.10、7.1–7.6、9.2–9.7 |

以下内容使用集成测试或人工配置审查：Default_Branch 合并后静态托管目标是否发布、生产构建失败是否保留既有部署、GitHub Actions 是否仅允许 `workflow_dispatch` 触发、Workflow_Token 是否符合最小权限、Compliance_Checklist 是否列出实际允许端点，以及 Model_Gateway 是否配置为 LiteLLM、OpenRouter 或 OpenAI 兼容接口中的单一网关与指定模型。
