# Product Polish Update Report

2026-09-13。恢复后先检查磁盘，保留 M1–M6 与现有启动入口，只补齐本次收口修改。

## Branding

页面、侧栏、首页、提示词、README 和启动器文案使用 English Education Explorer / 英探探：英语学习与教育探索器。旧 History 文本在展示时转换品牌，工程目录与启动文件名保持不变。12 个页面及共享展示模块的用户可见字符串检查未发现旧品牌。

## Homepage Copy

居中展示指定双语 Hero 和说明。三个主入口使用完全相同的标题组件、字号和字重，保留完整中文标题与说明；History 显示“查看我的历史方案记录”。普通页面的入口说明改为用户可以做什么。

## API Entry

首页提供“启用 AI 与联网能力”和“配置 AI 与联网服务”，展示 AI Demo / Live、搜索 Local Only / Live Search Ready。点击后进入既有 Manage Data，默认打开 AI Settings，旁边保留 Search Settings。配置、测试、保存、清除均可通过网页完成；密钥不回填密码框、不进入 History 或导出。

## Learnpath Mapping

`03learnpath` 复用已有解析、Markdown、元数据、chunks 和全文检索，内部标记 `raw_category=learnpath`、`region=general_reference`，显示为“通用学习路径参考资料”。没有增加第三个市场。

真实资料包含 20 个学习路径来源，8 个成功处理，产生 37 个内容块。Solve 和 Build 各检索到 2 条学习参考；Market 取得 7 条市场依据，学习参考为 0。Market 汇总及引用校验同时排除学习参考；如旧结果含有此类资料，展示时明确标为 Learning Reference。

## Data Incremental Update

整个 raw 目录已于 22:00:44–22:02:14 完成一次增量更新。

| 项目 | 结果 |
| --- | --- |
| 发现来源 | 67 |
| 新增来源 / 移除旧来源索引 | 28 / 7 |
| 已存在本地文件内容变化 / 已存在网页登记元数据变化 | 0 / 0 |
| 实际处理 / 无变化跳过 | 37 / 30 |
| 本次成功 / 失败 | 11 / 26 |
| 最终登记文档 / 可检索成功文档 | 67 / 40 |
| 最终内容块 | 3,803 |
| 构建及测试前后 raw 文件哈希 | 30 个文件完全一致 |

失败包含抓取失败 22、正文解析失败 2、需要 OCR 2；均记录后跳过，没有追抓受限网站。最终库另保留一条早前的 OCR 待处理记录。

更新前发现一份产品来源登记表经 WPS 另存，已排除本轮代码和测试写入。按更新全部最新资料的既有要求读取当前版本，并单独建立更新前快照；恢复时及上一轮的旧快照均保留。没有修改、覆盖或删除 raw 原件。

审计记录：`.local/polish_raw_update_before.json`、`.local/polish_update_report.json`；构建日志：`01data/03knowledge/00_logs/build_20260913_220044.log`。

用户随后确认 WPS 保存属于正常手动更新。22:09 重新建立独立快照并复查整个 raw，发现另有 1 条新增登记来源。22:11:16–22:11:18 已完成补充增量更新：发现 68 个来源，处理新增 1 条，跳过未变化的 67 条；新来源正文解析失败，已记录，没有反复抓取。当前共 68 个登记文档、3,803 个内容块。30 个 raw 文件在此次处理前后哈希完全一致；没有回滚、覆盖或修改原件。

补充快照：`.local/polish_raw_confirmed_20260913_220922.json`；补充更新记录：`.local/polish_update_report_20260913_2210.json`；日志：`01data/03knowledge/00_logs/build_20260913_221116.log`。之前的快照和更新记录均保留。

## Personal Contact Protection

新增共享 `output_safety.py`，覆盖模型返回、资料摘录、搜索摘要、Solve / Market / Build 展示、追问、History 保存与旧记录恢复、资料管理表格及 Markdown 导出。相关 Prompt 同时加入禁止输出个人联系方式、禁止引导联系私人教师的明确约束。

测试覆盖手机号、邮箱、微信 / VX / QQ、个人社媒链接、私信与扫码引导、具名私人教师推广，以及折行、全角、零宽字符、HTML 实体和 URL 编码变体。不安全句子省略，必要时显示“[个人联系方式已隐藏]”；未经检查的图片不输出。正式机构、产品官网与一般教师类型建议正常保留。旧数据库和 raw 原件不做清洗。

保护采用保守规则与 Prompt 约束，已知形式均有定向验证；无法对任意未知混淆或隐写形式作绝对保证。

## Targeted Check

- 本轮 28 项定向检查全部通过：品牌、首页层级、API 入口、真实展示过滤、模型与搜索返回、聊天、History、导出，以及临时资料的新增、修改、安全移除和学习参考隔离。
- 4 条既有核心链通过：Solve 保存恢复并重分析；Market 追问保存恢复并继续；Solve → Build 保存恢复、调整与导出；Manage Data 各设置及状态页面。
- 导出相关 6 项检查、既有设置 6 项检查通过；没有运行 exhaustive regression。
- 启动器可执行权限为 755，Shell 语法检查通过；实际启动应用并打开本地网址，`/_stcore/health` 返回 HTTP 200 / `ok`。
- 当前使用 Demo 与本地资料；Live AI / Search 返回使用隔离 fixture 验证，本次未使用真实 API Key 发起模型或搜索 API 连接测试。

## Files Changed

页面与品牌：

`03app/00_app.py`、`01_home.py`、`02_solve_need.py`、`03_explore_market.py`、`04_history.py`、`05_manage_data.py`、`06_build_solution.py`、`app_status.py`；根目录 `README.md`、`00_OPEN_ENGEDUSCOPE.command`。

共享输出、研究与恢复（均在 `03app/`）：

`output_safety.py`、`db.py`、`history_library.py`、`need_analysis.py`、`need_session.py`、`market_analysis.py`、`market_evidence.py`、`market_schemas.py`、`market_session.py`、`solution_analysis.py`、`solution_session.py`、`solution_export.py`。

提示词与服务返回（均在 `03app/`）：

`llm/prompts.py`、`llm/provider.py`、`market_prompts.py`、`solution_prompts.py`、`web_search/provider.py`、`web_search/intake.py`。

知识库（均在 `03app/knowledge/`）：

`paths.py`、`pipeline.py`、`retrieval.py`、`ui_kb.py`。

新增测试：

`tests/test_polish_boundaries.py`、`tests/test_polish_home.py`、`tests/test_polish_learnpath.py`、`tests/test_polish_rendering.py`、`tests/test_polish_safety.py`。

更新生成层：`01data/03knowledge/` 中相关 Markdown 与构建日志、`01data/02structured/eng_eduscope.db` 中知识库和索引。审计快照、原数据库备份及一次性更新脚本保存在 `.local/`。本报告位于 `02docs/PRODUCT_POLISH_UPDATE_REPORT.md`。

## Blocking Issues

没有运行阻塞。不可抓取、正文解析失败和 OCR 来源保留失败状态，不阻塞现有应用。个人联系方式过滤的能力边界及未进行真实 Key 测试的范围已如上说明。没有新增产品模块或进入下一阶段。
