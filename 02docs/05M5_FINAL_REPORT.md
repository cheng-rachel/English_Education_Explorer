# M5 Final Report

日期：2026-09-13。M5 实现完成，26 项 M5 定向检查通过；三条入口的真实本地流程已验证。当前 AI Settings 为 Demo，未使用真实外部 LLM 凭据；模拟 HTTP 验证不计为外部模型实测。

## Implemented

正式页面 `03app/06_build_solution.py` 已注册，地址为 `http://127.0.0.1:8501/build_solution`。Home 保留 Solve / Market 两个主要发现入口，增加次级 Build 入口。

本地应用健康检查返回 `200 ok`，页面路由正常。

复用 M3 Provider、M2 本地检索、既有 Taxonomy 与 SQLite。新增 M5 Prompt、结构校验、方案编排和共享展示；未修改 M3 / M4 分析核心。未新增搜索、爬虫、数据库或依赖，不进入 M6。

## Entry Paths

- Solve a Need：接收家长及教育工作者结果，继承需求、年龄、能力、场景、痛点、已有路径与证据；专业模式已调整过的需求范围优先于最初输入。
- Explore the Market：保留现有保存 opportunity_context 行为，随后进入 Build；包含所选需求信号、地域、未满足需求、解决方式、分析与追问。
- Start from Scratch：填写目标用户、年龄、能力、问题、场景和可选载体。确认简报后，点击生成才开始分析。

跳转、查看、History 恢复均不会自动生成或联网。

## Opportunity Brief

展示目标用户、精确年龄范围、核心需求、能力、场景、地域、已有方案、缺口、载体偏好、来源数量与主要资料。原研究完整保存在来源上下文中。

修改年龄或地域后保留原始简报，提示已有资料对新对象的适用性需要核验。生成与调整后同步页面简报，避免恢复旧范围。

## Product Concept

结构化输出工作名、价值主张、目标用户、核心问题、核心场景与教育机制。

包含 Teaching Goal 的学习结果与行为改变、按机制组织的 Solution Landscape、Opportunity Gap 的已有优势／剩余摩擦／机会、Carrier 选择理由，以及 AI Role / Human Role。设计假设与来源陈述分开，不把产品介绍或个别讨论当成已证明的效果。

## MVP

限定 3–5 个核心功能并逐项解释必要性，给出关键页面、最小数据、最小 AI 能力与当前不做的边界。

包含 Learning / Behavior / Product 三类指标、记录方法、小样本验证周期与比较方式、继续／调整／停止标准，以及 3–5 个风险和对应低成本检验。

## Demo Build Path

五步覆盖最小输入、最小页面、最小 AI Prompt / API、最小交互和验证。Fast Prototype 提供可复制提示词，支持先用人工检查的材料与小页面验证机制，再按需接入 AI。

EngEduScope 输出构建路径，不执行产品代码生成、部署或自动开发流程。

## Evidence

Solve / Market 直接沿用已有资料、引用编号、地域、日期、URL / 本地路径与上游分析状态，不再次检索。

Scratch 缺少资料时只调用一次 M2 检索，按目标地域获取最多五个片段。不触发 Live Search。无命中或检索不可用时仍可生成明确标注的设计假设，界面说明资料不足。

中国大陆与海外来源保持原地域；改变目标市场不会重写原证据。未知引用编号不会成为有效引用。完整证据与原研究快照进入 History。

## Revision

当前方案 + 新要求 → 完整修订方案，复用证据。支持年龄调整、Web App、不使用硬件、降低家长参与、中国家庭适配等常见要求，并保留调整记录。

Live 模式复用既有结构化 Provider；JSON 或结构不合格最多重试一次。失败保留原方案与输入，不用 Demo 冒充成功的 Live 结果。

Demo 仅对有限的常见约束做规则调整；其他要求会明确列为尚待人工或 Live 模型处理。

## History

继续使用 `research_sessions`，新增 `entry_type=build_solution` 和产品概念类型标签。保存完整简报、方案、证据、生成信息与调整记录。相同方案重复保存去重，修订版可另存；恢复后可继续调整。

## Export

提供「下载 Markdown」及「导出 Markdown 文件」，文件写入 `01data/04generated/YYYYMMDD_product_concept_名称_摘要.md`。

导出覆盖机会、教学目标、缺口、产品概念、机制、MVP、Demo 路径、指标、验证计划、风险、资料与调整信息。相同内容复用既有导出，不覆盖不同内容。

已生成 Case C 示例：[篇章阅读接力｜Demo 产品概念](../01data/04generated/20260913_product_concept_篇章阅读接力_be7afd3168ac.md)。使用一次实际本地检索取得五个参考片段，版图引用其中两项；没有调用外部 LLM，也未向 History 写入示例记录。

## Targeted Check

运行 M5 定向检查，不运行 exhaustive regression：

```sh
.venv/bin/python -B -m unittest discover -s tests -p 'test_m5_*.py' -v
```

- Case A：6–8 岁，阅读输入多但主动口语不足，家庭场景；真实 Solve → Build → Product Concept。
- Case B：真实本地资料形成的 Market Signal → 保存 opportunity_context → Build。
- Case C：9–12 岁，阅读理解、学校课程衔接、长篇阅读困难；直接输入 → 一次本地检索 → 完整方案。

三条路径均检查调整、History 保存与恢复、Markdown 导出。另检查继承资料不重新检索、空知识库降级、结构重试、错误保留和常见调整约束。

检查分布：上下文与入口 8 项、真实三入口流程 3 项、生成与调整边界 6 项、页面交互 3 项、Demo 内容与导出 6 项，共 26 项通过。额外核验了高等教育／成人材料不会被规则版图作为儿童方案引用，并读回实际导出的 Markdown。

测试使用用户数据库的只读备份、临时配置与临时导出目录，不向用户 History 插入测试记录。外部 Provider 通过模拟 HTTP 响应验证，未使用真实 Key 调用。

## Known Limitations

- 当前本机使用 Demo。Live 生成和自由调整还需有效 AI Settings，并由实际模型验证内容质量。
- 规则方案是设计起点，能力／场景适配较粗；来源相关性、产品机制及学习效果仍需人工审核和小规模试用。
- 调整后的年龄与市场继续沿用原资料，不自动补齐新证据。
- 验证计划提供试用建议，不是已经完成的实验，也不提供总体统计推断。

## Blocking Issues

本地 Demo 使用无阻塞。真实外部 LLM 的端到端验证尚缺有效配置。M6 未启动。
