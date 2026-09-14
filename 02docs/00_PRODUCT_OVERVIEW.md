# EngEduScope｜Product Overview

## 01 Product Identity

**Product Name:** EngEduScope  
**English Subtitle:** English Education Opportunity Explorer  
**Chinese Description:** 英语教育需求与机会探索器

EngEduScope is a locally deployed Web App Demo designed to help users move from:
- a specific English-learning need, or
- a broader market / education trend signal

toward:
- clearer need understanding,
- solution landscape analysis,
- actionable learning or product recommendations,
- and eventually a testable education product Demo.

The product is a **decision-support tool**, not a clinical, psychological, developmental, or language-disorder diagnostic tool.

---

## 02 Core Users

### 02.01 Parents
Parents use EngEduScope to:
- describe a concrete English-learning problem their child is facing;
- or explore what the child may currently need when the problem is unclear;
- receive several possible solution paths rather than one single answer;
- compare existing products, institutions, teacher support, AI DIY, and family-based options.

The parent-facing UI should use simple language such as:
- 听
- 说
- 读
- 写

The system can later map parent input to the more detailed internal skill taxonomy.

### 02.02 Education Professionals
For this Demo, “education professionals” mainly refers to:
- 教研工作者
- 课程设计师
- AI 教育产品经理
- 教育创业者

When the user selects this identity, display a small note:

> 本 Demo 所指教育工作者，主要包括教研工作者、课程设计师、AI 教育产品经理与创业者。针对一线英语教师与培训机构负责人的功能将在后续版本中推出。

---

## 03 Homepage Information Architecture

The homepage is organized around one primary goal:

# Build a Solution

Supporting statement:

> 从真实英语学习需求出发，理解问题、观察市场，并构建可验证的教育解决方案。

### Main Entry 01
## 🔍 Solve a Need
**我有具体英语学习需求**

Use when the user starts from:
- a child’s learning problem,
- a learning need,
- a teaching need,
- or a clearly defined education problem.

### Main Entry 02
## 📡 Explore the Market
**我想观察英语教育需求变化**

Use when an education professional wants to explore:
- demand signals,
- user discussion,
- education directions,
- existing solution supply,
- unmet needs,
- China market trends,
- overseas benchmarks.

### Supporting Entry
## 📚 History
**回到我的历史方案库**

Used to restore previous:
- need analyses,
- market explorations,
- AI conversations,
- solution concepts,
- product Demo ideas.

### Maintenance Entry
Top-right, visually low-key:

## ⚙ Manage Data

This is not a third user identity. It is a local maintenance interface.

---

## 04 Product Logic

EngEduScope has two main discovery routes that eventually converge into Build a Solution.

### 04.01 Need-Driven Route
Specific Need  
→ Age  
→ Skill Need  
→ Learning Context  
→ Learning Carrier  
→ Problem Understanding  
→ Solution Routes  
→ Build a Solution

### 04.02 Market-Driven Route
User Discussion / Product Supply / Reports / Policy / Overseas Benchmark  
→ Demand Signal  
→ Existing Solutions  
→ Dissatisfaction / Friction  
→ Unmet Need  
→ AI Market Analyst  
→ Build a Solution

---

## 05 Core Analytical Dimensions

The product uses four primary dimensions:

1. **Age**
2. **English Skill Need**
3. **Learning Context / Scenario**
4. **Learning Carrier / Delivery Mode**

Additional decision modifiers may include:
- learning goal,
- time,
- budget,
- parent involvement,
- existing solution,
- dissatisfaction with current solution.

These modifiers should support decision-making but should not replace the four primary dimensions.

---

## 06 Age Scope

Target age range:

**3–15 years old**

User-facing input supports:

**X 岁 X 个月**

Internal storage:

`age_months`

Example:

7 岁 4 个月  
→ 88 months

For aggregation, the system may map exact age into:
- 3–5
- 6–8
- 9–12
- 13–15

Exact age remains the preferred user-facing representation.

---

## 07 Market Scope

### 07.01 China Mainland
Primary market.

Used to analyze:
- family demand,
- education products,
- institutions,
- learning behavior,
- policy,
- local education discussion.

### 07.02 Overseas Benchmark
Used as a separate benchmark layer.

Used to observe:
- different product mechanisms,
- AI-native education products,
- international learning design,
- alternative solution patterns.

China and overseas data should be visibly distinguished in the UI and should not be mixed into one undifferentiated statistic.

---

## 08 Trend Display Principle

The Demo must not show false precision.

Allowed Demo-level trend labels:
- 上升
- 稳定
- 下降

Allowed demand-level labels:
- 高
- 中
- 低

Possible discussion-state labels:
- 新兴
- 持续出现
- 成熟
- 分歧明显

If precise numbers are introduced later, the product must define:
- data source,
- sample scope,
- time window,
- metric definition,
- comparison baseline,
- deduplication method where applicable.

Market pages should include a short methodology note explaining that current Demo signals are directional decision-support signals, not market-size estimates or statistical inference.

---

## 09 Data Philosophy

Use structured data for information that must be:
- filtered,
- sorted,
- matched,
- grouped,
- counted,
- compared precisely.

Examples:
- age
- region
- skill
- context
- carrier
- audience
- source type
- solution type
- trend labels

Use a semantic knowledge base for content that requires:
- meaning understanding,
- evidence retrieval,
- summarization,
- explanation,
- source-grounded reasoning.

Examples:
- reports,
- policy documents,
- research documents,
- product website content,
- user discussion,
- qualitative market material.

A document may exist in both layers:
- metadata in structured storage,
- text / chunks in the knowledge base.

---

## 10 Local Deployment Principle

Current product form:
- local deployment,
- local data,
- local history storage.

The Demo does not require:
- social functions,
- account system,
- cloud collaboration,
- payment,
- multi-user permission system.

---

# 11 Milestone Roadmap

## M1｜Skeleton

### Goal
Make EngEduScope runnable and clickable as a coherent Web App skeleton.

### Expected Outcome
The user can understand:
- what EngEduScope is,
- who it serves,
- how the three main entries differ,
- how Solve a Need works,
- how Explore the Market will work,
- where History lives,
- how Manage Data will be accessed.

### M1 Includes
- Homepage
- Solve a Need shell
- Parent and education-professional entry differences
- Exact age picker: years + months
- Market exploration shell
- China / overseas benchmark distinction
- Trend card placeholders
- last-updated date placeholder
- local SQLite History
- Manage Data shell
- Sources maintenance form

### M1 Does NOT Include
- production LLM logic
- vector database
- document ingestion
- live web search
- crawler
- real market trend calculation
- social media collection

---

## M2｜Data Foundation

### Goal
Create the local data foundation.

### Expected Outcome
EngEduScope can ingest and organize local materials and prepare them for structured filtering and semantic retrieval.

### M2 Includes
- raw file handling
- structured metadata
- taxonomy mapping
- report / document parsing
- AI-assisted tagging
- knowledge-base indexing
- hybrid retrieval foundation
- China / overseas separation
- Manage Data: Knowledge Base / Structured Data maintenance

### Important Principle
Users should not have to manually pre-classify every report before importing it.

---

## M3｜Solve a Need

### Goal
Turn user input into a structured English-learning need analysis and route the user toward useful solution paths.

### Parent Outcome
Problem understanding  
→ possible causes  
→ priority  
→ 3 solution routes  
→ time / cost / parent involvement / suitability  
→ product / institution / teacher / AI DIY / family activity options

### Education Professional Outcome
User Pain Point  
→ Teaching Goal  
→ Age  
→ Skill  
→ Context  
→ Mechanism  
→ Carrier  
→ AI Opportunity  
→ MVP Feature  
→ Key Pages  
→ Validation Metric

### Positioning
Decision support, not diagnosis.

---

## M4｜Explore the Market

### Goal
Allow education professionals to observe current English-education demand signals and existing solution supply.

### Main Data Channels
- local knowledge base
- product / institution official websites
- policy / industry material
- public education discussion
- overseas benchmarks
- live web search when triggered by user

### M4 Interaction
- China Mainland / Overseas Benchmark
- 30 days / 90 days / 1 year
- age
- skill
- context
- audience
- demand signals
- solution landscape
- AI Market Analyst
- follow-up chat

### Live Web Search
M4 should include a manual button:

**更新联网信息**

Next to it show:

**已更新至 YYYY年MM月DD日**

Live web search should be:
- user-triggered,
- not continuous background crawling,
- demand-oriented,
- source-ranked,
- evidence-visible.

### Source Levels
A-level:
- official product websites
- government / policy sources
- formal reports
- academic / institutional material

B-level:
- education media
- technology media
- industry analysis
- app store / product review sources

C-level:
- public user discussion
- forums
- reviews
- social demand signals

### Search Principle
Search both:
- Problem Space
- Solution Space

Do not require the user to know competitors in advance.

Use a **Solution Landscape** concept rather than a competitor-only view.

---

## M5｜Build a Solution

### Goal
Convert a concrete need or a market opportunity into a testable product concept.

### Expected Output
Pain Point  
→ Teaching Goal  
→ Target Age  
→ Core Context  
→ Solution Mechanism  
→ Best Carrier  
→ AI Intervention  
→ MVP Features  
→ Key Pages  
→ Validation Metrics

The user can enter M5 from:
- Solve a Need
- Explore the Market
- History

---

## M6｜History & Polish

### Goal
Turn temporary analyses into reusable research assets and improve Demo usability.

### History should preserve
- original question
- filters
- age
- skill
- context
- region
- market signals
- sources
- AI insights
- conversation
- solution concept
- user notes

### Final M6 Focus
- restore previous Research Sessions
- continue previous analysis
- improve UI clarity
- improve navigation
- improve research traceability
- improve Demo presentation quality

---

# 12 Current Development Stage

## Current Stage: M6 — History & Polish

M1–M5 已完成，M3（Solve a Need）、M4（Explore the Market）与 M5（Build a Solution）已验收并冻结。当前为 **M6｜History & Polish**。

M3 已接入本地 AI Settings、Live / Demo Provider、需求映射、本地知识检索、结构化分析、教育工作者方案调整与 History 恢复。

M3 实施记录见 `03M3_FINAL_REPORT.md`。M4 已接入公开讨论类别、本地证据市场分析、用户触发的 Tavily 搜索、市场洞察追问、History 与待构建机会上下文，详见 `04M4_FINAL_REPORT.md`。

M5 新增正式 Build 页面，汇流 Solve、Market opportunity_context 与手动输入三种来源。方案包括教学目标、机会缺口、教育机制、载体、人机分工、MVP、五步 Demo 路径和小规模验证计划；支持继续调整、History 保存恢复及 Markdown 导出。详见 `05M5_FINAL_REPORT.md`。

M5 复用 M3 Provider、M2 FTS5 与 research_sessions，继承上游资料；直接输入时最多做一次轻量本地检索，不自动联网。真实 LLM 需要有效配置；Demo 模式明确展示规则生成的设计建议，不声称效果已验证。M3 / M4 分析核心保持冻结，仅增加通向 Build 的页面入口与 History 分支。

M6 已统一 History 的三类研究卡片与 Type / Skill / Age / Region 筛选，支持不调用 API、不联网、不检索的结果恢复及继续工作。导航、首页、AI / Search 状态、配置操作与失败提示已整理，公开用户讨论标签保持一致，README 提供本地启动与隐私说明。详见 `06M6_FINAL_REPORT.md`。

本地 Demo 的核心用户链已完成定向检查；未新增产品模块、Provider、数据库或抓取架构。真实外部服务仍需有效配置与实际验证。M6 为当前收口阶段，不自动开启后续开发。`01M1_*` 文档保留为历史范围记录。

---

# 13 Development Principles

1. **先跑起来。**
2. Prefer the shortest reliable path.
3. Build milestones sequentially.
4. Do not over-engineer for hypothetical future requirements.
5. Do not implement future milestone features early.
6. Do not create unnecessary infrastructure.
7. Keep future extension possible without making M1 complex.
8. Keep user-facing taxonomy consistent.
9. All folders and documents follow numbered logical ordering.
10. Local-first unless a later milestone explicitly requires an external service.
11. Make targeted checks; do not block progress with excessive validation.
12. Working Demo > theoretical perfection.

---

# 14 Agent Reading Rule

Before any development task, the Agent must read this file first:

`02docs/00_PRODUCT_OVERVIEW.md`

For M1, the Agent must then read:

- `02docs/01M1_USER_FLOWS.md`
- `02docs/01M1_TAXONOMY.md`
- `02docs/01M1_MVP_SCOPE.md`
- `02docs/01M1_BUILD_TASK.md`

If there is a conflict:
1. `00_PRODUCT_OVERVIEW.md` defines global product direction.
2. Current milestone BUILD_TASK defines implementation scope.
3. MVP_SCOPE defines what must and must not be built.
4. TAXONOMY defines user-facing and internal categories.
5. USER_FLOWS defines interaction order.

Do not invent new product requirements when the documents already define them.
