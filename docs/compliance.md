---
# 机器可读合规策略（由 content_pipeline.compliance 读取与校验）。
# gateway / allowed_endpoints / model_endpoint / model 为占位默认值，维护者可按实际
# 网关修改；修改时须同步更新下方正文，且不得删除任何禁止项。
policy_version: 1
gateway: openai_compatible
model_endpoint: https://api.deepseek.com/chat/completions
allowed_endpoints:
  - https://api.deepseek.com/chat/completions
model: deepseek-flash
max_model_calls_per_run: 2
human_editorial_gate:
  review_items:
    - facts_and_sources
    - reader_value
    - tone
    - links
    - title
  draft_transition:
    from: true
    to: false
  performed_by: human
  publish_via: pull_request_merge
forbidden_dependencies:
  - database
  - redis
  - postgres
  - pgvector
  - prefect
  - task_queue
  - vps
  - docker
  - ollama
forbidden_credentials:
  - third_party_content_publishing
forbidden_capabilities:
  - ai_detection_evasion
  - humanizer
  - rate_limit_circumvention
  - multi_account
  - distributed_ip
  - tos_violating_ui_automation
  - selenium
  - unreviewed_mass_distribution
  - automatic_cross_platform_publishing
---

# MVP 合规清单（Compliance_Checklist）

本文件是 `content-pipeline-skeleton` MVP 的唯一合规清单。上方 front-matter 是生成脚本在任何模型调用前读取并校验的机器可读策略；本正文是面向维护者和审阅者的说明。两者必须保持一致，任何修改都通过 Pull Request 审阅。

内容自动化的目标是读者价值、准确性和可审阅性，而不是操纵平台或规避规则。

## 1. 模型网关与允许网络端点

- 网关：`openrouter`（LiteLLM 或 OpenRouter 中恰好一个）。
- Allowed_Network_Endpoint（仅 HTTPS）：
  - `https://openrouter.ai/api/v1/chat/completions`（模型调用端点）
- 指定模型标识：`openai/gpt-4o-mini`
- 端点按完整字符串精确匹配：不接受 HTTP、其他主机、其他路径或变体；网关客户端不得跟随重定向。
- 访问未列出的端点即阻止并以失败状态结束工作流。
- 运行时配置 `MODEL_GATEWAY` 与 `MODEL_ID` 必须与本清单的网关和模型一致，否则在调用前失败。

以上网关、端点和模型为占位默认值，维护者可按实际使用的单一网关修改 front-matter 与本节，修改须经 PR 审阅。

## 2. 模型调用上限

- 每次 Generation_Workflow 运行最多 **2** 次模型调用：一次调用，加上最多一次针对 Retryable_Network_Error（连接超时、连接中断、HTTP 429、HTTP 5xx）的重试。
- 其他 HTTP 4xx、响应解析错误或 Article_Schema 校验错误不重试。
- 不进行自动内容改写、质量循环或多模型路由。
- 调用前按预算配置估算成本，超出单篇或单次运行上限时零调用。

## 3. Human_Editorial_Gate（人工审阅闸门）

所有生成内容均为 `draft: true` 的草稿，只能出现在非默认分支的可审阅变更中。发布前编辑人员必须在该文章的 Pull Request 中逐项审阅并保留记录：

1. 事实与来源（`facts_and_sources`）
2. 读者价值（`reader_value`）
3. 语气（`tone`）
4. 链接（`links`）
5. 标题（`title`）

完成五项审阅后，由编辑人员**手动**将 `draft` 从 `true` 改为 `false`，并通过合并 Pull Request 进入默认分支。这是唯一发布路径；工作流不得自动批准、自动合并或自动发布。

- 审核记录格式：`.github/pull_request_template.md` 中的五行清单，每项勾选 `[x]` 并在冒号后写明记录。
- 只读校验：`.github/workflows/review-gate.yml`（`python -m content_pipeline.review_gate`）仅以 `contents: read`、`pull-requests: read` 权限读取 PR 描述与 Git 历史，校验五项记录齐全、文章 `draft: false`，且 `draft: true → false` 由非自动化提交完成；它只报告通过/失败，不批准、不合并、不发布。
- 维护者应在默认分支保护规则中将 `review-gate` 设为必需状态检查，并要求至少一位人工批准。Git 作者身份可自行声明，因此分支保护与人工批准才是强制防线。

## 4. 禁止依赖（MVP）

数据库、Redis、Postgres、pgvector、Prefect、任务队列、VPS、Docker、Ollama。

## 5. 禁止持有的凭据（MVP）

第三方内容发布凭据（任何用于向外部平台、社交媒体或内容分发渠道发布内容的账号令牌、API 密钥或 Cookie）。生成工作流仅持有单一模型网关凭据与最小权限的仓库令牌。

静态托管部署凭据（`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`）只用于把本站构建产物发布到已配置的静态托管目标，不属于第三方内容发布凭据。它们只能作为 GitHub `production` 环境机密存放，仅由 `.github/workflows/deploy.yml` 的部署步骤读取；该工作流只在默认分支接收已合并变更后运行，生成工作流与 `review-gate` 均无法读取或触发部署。

## 6. 永久禁止能力

- AI 检测规避（`ai_detection_evasion`）与 humanizer（`humanizer`）
- 平台限流绕过（`rate_limit_circumvention`）
- 多账号（`multi_account`）
- 分散 IP（`distributed_ip`）
- 违反第三方条款的 UI 自动化（`tos_violating_ui_automation`）或 Selenium（`selenium`）
- 未经 Human_Editorial_Gate 审核的大规模分发（`unreviewed_mass_distribution`）
- 自动跨平台分发/发布（`automatic_cross_platform_publishing`）

这些禁止项是固定下限：生成脚本校验 front-matter 时，缺少任一项即失败。维护者可以增加禁止项，但不能删除。
