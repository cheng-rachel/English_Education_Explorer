# M4 Final Report

日期：2026-09-13。M4 实现完成，30 项 M4 定向检查通过；实际本地资料链路已验证。真实 Tavily 搜索及 Live LLM 分析尚未使用有效凭据验证，不将模拟 HTTP 检查记为外部服务实测。

## Implemented

保留现有 Explore the Market 筛选与洞察页面结构，替换静态 Demo Cards：

本地知识库 + 用户手动联网更新 → Demand Signals → Solution Landscape → Evidence / Interpretation / Hypothesis → 追问 → History。

无后台爬虫、浏览器自动化、多 Agent 产品工作流或新增数据库架构。M3 分析与配置模块保持冻结；History 增加市场研究分支，Manage Data 增加搜索配置。

运行方式保持：

```sh
.venv/bin/python -B -m streamlit run 03app/00_app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

应用地址 `http://127.0.0.1:8501`，健康检查正常。

## 05public_discussions

新增标准类别 `05public_discussions/online_discussions.xlsx`，类型固定为「公开用户讨论」。地域沿用目录推断，不新增 XLSX region 列。

现场用户文件实际使用单数 `05public_discussion/online_discussion.xlsx`，已做兼容；没有重命名或重写登记表。Sources 与 Knowledge Base 可以识别标准与既有路径。

复用既有 URL → Markdown → metadata → chunks → FTS5。公开讨论只有明确作者角色线索才分类，无法可靠判断则「无法判断」。

对实际新增 8 条来源做了一次短超时 ingestion：6 条成功、2 条失败并跳过，成功内容生成 19 个文本块。知识库目前 46 条来源记录、3,755 个文本块（包括失败记录）。

## Live Search

仅接入 Tavily，一个薄适配层 `03app/web_search/provider.py`；业务层只调用通用 `search_web(queries, filters)`。

Manage Data → **Search Settings** 提供 Provider / API Key / 测试 / 保存 / 清除。密钥保存在 `.local/search_config.json`，权限 `0600`；既有 `.gitignore` 的 `.local/` 规则覆盖，密码框不回填已保存 Key。

只有「更新联网信息」触发搜索。当前页面生成两条查询，适配层上限为三条查询、六条结果、三次普通正文读取。搜索配置测试是单独的小请求，不改变市场更新时间。

认证错误、超时、403、robots、登录或动态页面等跳过并记录；正文不可用时保留明确标注的搜索摘要。成功搜索才写入更新时间，失败或未配置不伪造日期。普通读取不登录、不执行 JavaScript、不绕过访问限制。

请求参数依据 [Tavily 官方 API 文档](https://docs.tavily.com/documentation/api-reference/endpoint/search) 核对。日期区分服务估计的发表/更新时间与实际抓取时间。

## Query Generation

根据市场、时间范围、精确年龄、能力、场景、人群生成两个方向：

- Problem Space：学习困难、已有尝试、使用阻力与讨论。
- Solution Space：产品、教学机制、家庭练习和支持方式。

中国大陆以中文问题查询为主；海外以英文能力与机制查询为主。时间范围落实到搜索日期条件，不只改变 UI 标签；不以品牌清单替代需求搜索。

## Demand Signals

包含标题、目标年龄、能力、场景、讨论人群、地域、趋势及依据、需求程度、信号状态、问题、尝试过的方案、不满、未满足需求、机会假设与来源。

初步年龄筛选会排除标题中明确与目标年龄不符的资料；其他资料保留年龄覆盖待核验说明。场景和人群是研究目标，不能冒充样本已经覆盖这些人群。

窗口外、未知日期和日期精度不足的资料明确标为背景。缺少可比较证据时，trend / demand_level / signal_status 为 null，页面显示「证据不足」，不会默认判为稳定或高需求。

## Solution Landscape

按系统课程、分级阅读、真人教师、AI口语、游戏化学习、智能硬件、家庭活动、其他归纳。

机制及代表性产品关联资料；产品名称必须出现在所引用材料中，不排名。官网描述标识为供给方自述，不当成效果证明。用户「尝试过」「不满意」只从公开讨论/评价的明确经历提取，不从产品介绍虚构失败经历。

## AI Market Analyst

Live 模式复用冻结的 M3 `complete_json()`，新增 M4 独立 Prompt 与 JSON 校验，共用一次重试预算。

输出分为实际观察、可能解释、可验证假设，并回答现有机制为何可能仍留下支持缺口。另一个市场没有证据时明确不做比较。

没有 Live LLM 配置时，使用实际资料的规则分析：摘取原文、识别已出现机制、区分经历与宣传、提出有提示和独立任务对照等可检验假设。页面明确标识「本地证据规则分析 / 回答，未调用 AI」，不使用静态市场 Demo 数据冒充真实分析。

## Evidence

核心洞察保留 title、source_type、region、date、URL / 原文件、引用编号与来源等级。

A 为官方/政策/正式报告/研究；B 为媒体和行业分析；C 为公开讨论、论坛、产品评价。不能可靠识别的来源为「待核验」，不强行升级成权威来源。

标识本地片段、网页正文或搜索摘要，并显示日期与地域依据。联网结果地域表示检索目标，未核验市场归属会明确说明。资料内容按不可信参考数据传给 LLM，不能覆盖系统指令。

## Chat

每条 Insight 支持「继续追问」，传入当前洞察、对应来源、用户问题及最多三轮近期对话。回答继续区分 Evidence / Interpretation / Hypothesis。

没有相应品牌或失败经历的资料时明确无法确认；不凭名称编造“产品为什么不能解决”。追问不自行搜索，补充新资料需手动点击联网更新。

## History

继续使用 `research_sessions`。市场研究保存筛选、时间窗口、地域、signals、evidence_sources、分析解释、chat、generated_at 与联网状态。

可恢复筛选和完整研究，无需重新联网或调用 AI。Build 按钮保存当前 Insight、来源、筛选与聊天为 `opportunity_context`，显示 M5 后续提示；没有实现 M5 产品生成。

## Targeted Check

```sh
.venv/bin/python -B -m unittest discover -s tests -p 'test_m4_*.py' -v
```

30 项 M4 检查通过，范围包括公开讨论接入、查询/分析/追问、搜索配置与失败边界、页面与 History。未进行 exhaustive regression。

| 案例 | 结果与实际验证范围 |
| --- | --- |
| A：中国大陆，6–8 岁，口语表达，家长，自主学习 | 实际知识库 + 完整页面通过；形成 1 条洞察、8 条来源，抽取到已尝试方式及使用阻力；联网触发与合并使用模拟响应验证 |
| B：海外，5–10 岁，口语表达，自主学习 | 实际海外知识库独立生成洞察，引用仅限海外；无证据时不编造中国比较 |
| C：公开讨论 | 实际 8 条登记来源完成 6 成功 / 2 robots 拒绝；另用隔离 fixture 验证 403 / 登录跳过、Markdown、metadata、FTS5 及增量跳过 |
| D：现有产品为何仍未解决 | 实际洞察 + 完整追问 UI 通过，回答引用当前来源并标出无法确认的原因；Live JSON 合成与一次重试采用模拟返回验证 |
| E：无 Search API | 不发搜索请求、不写成功日期，仍使用实际本地资料，页面正常；搜索失败也保留本地分析 |
| 配置与 History | Key 私有存储、不回显、测试后保存、重新读取、清除通过；市场聊天与机会资料可保存恢复 |

定向测试使用临时数据库和配置。完整页面补充检查覆盖 Market 分析、追问、History、Manage Data 全部 Tab；正式 History 未写入测试研究。

## Failed Sources

实际 ingestion 中以下两条知乎来源被 `robots.txt` 拒绝，已写入知识库失败记录并跳过，没有尝试绕过或反复抓取：

- 知乎：【家长必看】科大讯飞AI学习机、学而思、作业帮实测3个月，来聊聊实际体验，这几点差距让我想退货...
- 知乎：经验分享：家有初中生，英语成绩从70分到90分，看看我都做了什么！

详细日志：`01data/03knowledge/00_logs/m4_discussions_20260913_181057.log`。

后续 Live Search 失败记录写入 `.local/search_failures.jsonl`，当前研究也保留安全的失败摘要。未配置搜索时不伪造搜索失败事件。

## Known Limitations

- 未配置真实 Search / Live LLM 凭据；真实鉴权、额度、网络及生成质量尚待用户配置后实测。协议、合并、失败回退与 UI 已通过模拟 HTTP / JSON 检查。
- 新增讨论主要是 2018–2025 年资料，只能作为历史背景，不能证明近30/90天需求变化。现有样本不足时会保留空的趋势判断。
- FTS5、规则年龄匹配、经历抽取与人物角色识别是轻量基线，可能漏检；缺失观察不能解释为市场没有该需求。
- Schema 校验保证结构、编号与基本地域/时间约束，不能完全验证每项 Live 自然语言解释是否被原文支持。
- 搜索日期可能是估计更新时间，未知来源地域仍待核验；搜索摘要与官网宣传的证据能力有限。
- 联网发现仅用于当前研究，暂未增加「加入 Sources」按钮或自动写回登记表。
- 当前 Python 3.9 / LibreSSL 环境存在 urllib3 兼容性提示；现有真实来源 ingestion 与本地测试通过，搜索 API HTTPS 兼容性仍需有效凭据实测。

## Blocking Issues

无本地功能开发阻塞。真实联网搜索 / Live AI 外部验收待有效配置；无配置仍可使用本地 Market Radar。未进入 M5。
