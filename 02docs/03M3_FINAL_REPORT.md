# M3 Final Report

日期：2026-09-13。实现已完成；28 项本地定向检查通过。真实外部 API 连通性尚未用有效凭据验证。

## Implemented

Solve a Need 已从输入快照接通为：输入 → 规则需求映射 → 1–3 个查询 → M2 检索 → Provider → JSON 校验 → 结果与参考依据 → History。

保留现有 Streamlit、Taxonomy、SQLite、知识库与页面结构。未新增第三方依赖，未进入 M4。

本地启动：

```sh
.venv/bin/python -B -m streamlit run 03app/00_app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

地址：`http://127.0.0.1:8501`。启动及 `/_stcore/health` 检查通过。

## Existing partial work reused

接管时项目未启用 Git；根据文件内容与修改时间确认已有：

- `03app/llm/provider.py`、`prompts.py`、`schemas.py`、`mock.py`。
- `03app/need_analysis.py`：需求映射、查询构建、检索、分析与调整接口。
- `03app/need_session.py`：M3 结果组件与会话命名。
- `03app/02_solve_need.py`：已有表单与部分分析辅助函数，但提交与展示仍停留在 M1 快照。

复用了这些模块的职责与调用接口，补齐配置和页面连接，修正校验、演示内容、重试及恢复行为。未重做 M1 / M2。

## AI Settings

入口：**Manage Data → AI Settings**。

- 支持 OpenAI-compatible、Anthropic、Custom；Custom 使用 OpenAI-compatible 请求协议。
- 可填写 Base URL、Model、API Key、Timeout，切换 Live API / Demo / Mock。
- 提供测试连接、保存配置、清除配置；显示当前 Provider / Model 与 API 状态。
- Key 保存至项目 `.local/llm_config.json`，文件权限 `0600`，原子写入；`.local/` 已加入 `.gitignore`。
- 密码框从不回填已保存的 Key；测试后可直接保存。切换服务地址时不会自动使用旧服务的 Key。
- 清除删除保存的凭据并明确回到 Demo，避免启动环境中的 Key 静默恢复。
- 新进程能读回保存的配置。测试均使用临时配置；未写入真实用户 Key。

## LLM Provider

统一入口为 `llm.provider.complete_json()`，支持真实 HTTP 请求、JSON 解析、统一友好错误。业务层不依赖具体 Provider，后续 M4 / M5 可复用。

API 和本地配置错误不显示请求体、服务响应正文或凭据。网络、解析和 schema 错误共用一次自动重试预算；验证失败保留输入，页面可以重试。

## Parent Flow

具体问题和整体梳理均支持年龄、听说读写、背景、场景与学习方式。输出包括问题理解、主要及相关能力、2–4 个可能原因、优先级、3 条机制不同的路径、投入/成本/参与程度、适用条件、局限、教师类型和可复制 AI DIY。

建议成本仅使用低 / 中 / 高。具体产品需关联给定资料编号，不提供排名。“希望根据需求匹配排序”仅显示反馈收讫。

## Educator Flow

输出 User Need、Teaching Goal、按机制归纳的 Existing Solution Landscape、Gap、Product Direction、AI / Human Role、MVP 与三类 Validation Metrics。

MVP 包含 3–5 项功能、关键页面、最小数据、最小 AI 能力与当前不做。支持当前结果 + 新指令调整；连续调整保留前次方案，保存标题反映调整后的年龄等信息，原始输入保留供追溯。

## Knowledge Retrieval

直接调用 `knowledge.retrieval.get_retriever()`，未修改 M2 Retriever、表结构或采集链路。

家长使用中国大陆资料；教育工作者另外保留海外 Benchmark。结果列出标题、类型、原始文件或 URL，区分实际引用和检索背景。资料正文按不可信参考内容传入 Prompt，产品宣传不作为学习效果证明。

知识库不可用和无匹配资料有明确状态。原始数据库保持 38 份资料、3,736 个文本块，测试未新增正式 History 记录。

## History

继续写入 `research_sessions.summary_json`：原始输入、`need_analysis`、`solution_routes`、`ai_diy`、`evidence_sources`、`generated_at`、Provider/模式/查询元信息；教育工作者另存 `product_direction`、`mvp_spec`、`validation_metrics` 与调整记录。

详情复用结果组件，可恢复到 Solve a Need，无需重新调用 API；恢复表单与原始输入，兼容 M1 旧记录，避免同一结果重复保存。跨页面进入 AI Settings 再返回时保留需求与结果。

## Targeted Check

```sh
.venv/bin/python -B -m unittest discover -s tests -p 'test_m3_*.py' -v
```

28 项检查通过。测试范围为 M3 行为及必要错误边界，不做 M1 / M2 全量回归。

| 案例 | 结果 | 验证内容 |
| --- | --- | --- |
| A：7 岁 4 个月，阅读尚可但不主动说 | PASS（Demo + 真实本地检索） | 表单提交、口语表达主能力与阅读相关能力、原因、优先级、3 路径、教师、DIY、来源 |
| B：年龄 + 背景，无明确问题 | PASS（Demo） | 无需具体问题可提交并生成整体梳理；不预设能力缺陷 |
| C：6–8 岁家庭口语输出产品探索 | PASS（Demo） | 完整设计输出；连续调整；保存、详情、恢复；调整年龄后标题一致 |
| D：AI Settings | PASS（本地 + 模拟 HTTP） | 填写→测试→保存→重新读取→清除、独立进程读回、密码不回显、失败提示、地址切换不复用 Key |
| Live 调用链 | PASS（模拟 HTTP） | OpenAI-compatible / Custom 与 Anthropic 请求结构、JSON 回复、错误边界；完整 Live 分析路径经过 Provider |
| 本地启动与页面挂载 | PASS | HTTP 健康检查、Manage Data 全页 AI Settings Tab 挂载 |

测试使用临时数据库（部分用现有知识库副本）、临时配置和虚构测试凭据。未发送真实付费 API 请求。

## Known Limitations

- 外部服务的真实鉴权、可用模型、网络及输出质量仍需在 AI Settings 配置有效凭据后验证。重新打开应用时显示“已配置·未测试”，不会冒充持续连接。
- 初步 Need Mapping 为轻量规则；Live 模型可结合输入修正。FTS5 关键词基线可能带回弱相关内容，来源存在并不意味着支持所有判断。
- Demo 为按能力区分的确定性演示，不生成具体品牌或虚构引用；检索到的资料仅作为背景展示。Demo 调整支持年龄、不依赖专用硬件、降低家长参与，其他要求明确显示尚未自动实现。
- Live 结构与来源编号经过校验，但没有自动验证每项自然语言判断是否被原文充分支持。
- 当前 `.venv` 的 Python 3.9 / LibreSSL 会出现 urllib3 兼容性提示；本地检查通过，真实 HTTPS 服务兼容性需结合实际配置验证。

## Blocking Issues

无本地功能开发阻塞。真实外部 API 验收待使用者提供有效配置；当前无 Key 可完整使用 Demo。未开展 M4 联网搜索、市场分析、推荐排序或 M5 独立页面。
