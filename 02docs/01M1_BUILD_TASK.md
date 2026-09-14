# EngEduScope｜M1 Build Task

## 01 Agent Instruction

Before coding, read in this order:

1. `02docs/00_PRODUCT_OVERVIEW.md`
2. `02docs/01M1_USER_FLOWS.md`
3. `02docs/01M1_TAXONOMY.md`
4. `02docs/01M1_MVP_SCOPE.md`
5. `02docs/01M1_BUILD_TASK.md`

Current milestone:
# M1｜Skeleton

Do not implement M2–M6.

---

# 02 Build Objective

Create the first runnable local EngEduScope Web App skeleton.

The output should be good enough to:
- demonstrate the product idea;
- click through the main user flows;
- validate information architecture;
- store basic History locally;
- maintain basic Source records.

---

# 03 Implementation Principle

**能跑 > 完整 > 工程化**

Prefer the shortest reliable implementation.

Recommended:
- Python
- Streamlit
- SQLite

Do not introduce:
- React / Next.js
- FastAPI
- Docker
- Redis
- cloud DB
- authentication framework

unless the current codebase already depends on them.

---

# 04 Suggested App Structure

Follow the user’s numbered-folder convention.

A minimal possible structure:

```text
EngEduScope/
├── 01data/
│   ├── 01raw/
│   ├── 02structured/
│   ├── 03knowledge/
│   └── 04generated/
│
├── 02docs/
│   ├── 00_PRODUCT_OVERVIEW.md
│   ├── 01M1_USER_FLOWS.md
│   ├── 01M1_TAXONOMY.md
│   ├── 01M1_MVP_SCOPE.md
│   └── 01M1_BUILD_TASK.md
│
└── 03app/
    ├── 01_home.py
    ├── 02_solve_need.py
    ├── 03_explore_market.py
    ├── 04_history.py
    ├── 05_manage_data.py
    └── ...
```

If Streamlit multipage requires a different runtime file arrangement, preserve numeric logical ordering as far as practical.

Do not rename the user’s numbered top-level structure without need.

---

# 05 Task 01｜App Shell

Build:
- EngEduScope title
- English subtitle
- Chinese explanation
- navigation
- coherent wide layout

Homepage hero:

# Build a Solution

Text:

> 从真实英语学习需求出发，理解问题、观察市场，并构建可验证的教育解决方案。

Primary cards:
- 🔍 Solve a Need
- 📡 Explore the Market

Secondary:
- 📚 History

Low-key:
- ⚙ Manage Data

---

# 06 Task 02｜Solve a Need

## Identity
Buttons / radio:
- 我是家长
- 我是教育工作者

Education-professional note must appear conditionally.

## Parent Mode

Support two starts:
- 我有一个具体问题
- 我想整体看看孩子目前需要什么

Fields:
- age: year + month
- high-level skill: 听 / 说 / 读 / 写
- problem description / learning background
- contexts
- current learning method

Submit:
**分析这个学习需求**

Show a Demo placeholder result.

Add:
**保存到 History**

## Education Professional Mode

Fields:
- age / age range
- detailed skill
- context
- carrier
- Pain Point

Submit:
**生成解决方案路径**

Show placeholder sections:
- 用户痛点
- 教学目标
- 目标年龄
- 核心场景
- 解决机制
- 最适载体
- AI 可介入环节
- MVP 功能
- 关键页面
- 验证指标

---

# 07 Task 03｜Explore the Market

Top filters:
- 中国大陆 / 海外 Benchmark
- 近30天 / 近90天 / 近1年
- age
- skill
- context
- audience

Online area:
- Button: **更新联网信息**
- Label: **已更新至 YYYY年MM月DD日**

M1 behavior:
- no real web request;
- update date UI or show an M4 message only.

Create 3–5 static demo cards.

Example card structure:
- title
- directional trend
- demand level
- age
- skill
- audience
- region
- one-sentence AI-style interpretation

Mark cards as Demo Data.

Do not show fake growth percentages.

---

# 08 Task 04｜SQLite

Create local SQLite DB.

Minimum table:

## research_sessions
Suggested fields:
- id
- title
- user_type
- entry_type
- created_at
- updated_at
- status
- summary_json

Also acceptable in M1:

## sources
- id
- name
- url
- region
- source_type
- active
- created_at

Use migrations only if trivially necessary.
Simple create-if-not-exists is sufficient.

---

# 09 Task 05｜History

History page:
- show Research Sessions;
- newest first;
- empty state;
- simple session detail;
- reopen basic saved data.

M1 does not need full conversational restoration.

At least one Solve a Need flow must be able to create a History record.

---

# 10 Task 06｜Manage Data

Create tabs:

### 1. Knowledge Base
M1:
- explanatory placeholder
- show future raw-data location
- optional demo count

### 2. Structured Data
M1:
- explanatory placeholder
- show taxonomy / data categories

### 3. Sources
Implement basic form.

Fields:
- 来源名称
- 官网 / 来源 URL
- 地域
  - 中国大陆
  - 海外
- 来源类型
- 启用 / 停用

Display existing source records below.

Keep interaction friendly to non-technical maintainers.

### 4. System Status
Show simple local status:
- App: Ready
- SQLite: Ready / error
- Knowledge Base: M2
- Live Search: M4
- LLM: not connected in M1

---

# 11 UI Rules

- Professional, clean, research/product-tool feel.
- Do not use childlike visual design.
- Chinese is the primary explanatory language.
- Keep English module names.
- Avoid excessive gradients, animations, or decorative UI.
- Use cards, spacing, tags, and clear hierarchy.
- Build a Solution must dominate the homepage.
- Explore and Solve have equal primary weight.
- History is smaller.
- Manage Data is unobtrusive.

---

# 12 Self-Check

Before reporting completion:

Run the app locally.

Check:
1. Homepage loads.
2. All four destinations open.
3. Parent flow works.
4. Education-professional flow works.
5. Age month selector works.
6. Market filters render.
7. China / Overseas renders.
8. update-date label renders.
9. History persists after app refresh / restart.
10. Source form stores data.
11. No API key is required.
12. No future milestone feature was unnecessarily implemented.

---

# 13 Completion Report

When done, report only useful implementation information:

## Built
What was completed.

## Files Changed
List important files.

## Run
Exact local start command.

## M1 Acceptance
PASS / PARTIAL for each key acceptance group.

## Remaining M1 Issues
Only real unfinished M1 items.

## Not Implemented by Design
Confirm that M2–M6 functionality was intentionally not built.

Do not propose large refactors unless M1 cannot function without them.
