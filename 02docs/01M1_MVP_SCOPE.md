# EngEduScope｜M1 MVP Scope

## 01 M1 Goal

Build a local, runnable, clickable Web App skeleton that accurately expresses EngEduScope’s product structure.

M1 is successful when the product can be demonstrated end-to-end without production AI.

---

# 02 Must Build

## 02.01 Home

Must show:
- EngEduScope
- Build a Solution
- product subtitle / explanation
- 🔍 Solve a Need
- 📡 Explore the Market
- 📚 History
- ⚙ Manage Data

Visual hierarchy:
- Build a Solution is dominant.
- Solve a Need and Explore the Market are large primary paths.
- History is secondary.
- Manage Data is low-key.

---

## 02.02 Solve a Need

Must include:
- parent / education-professional identity selection;
- education-professional note;
- X岁X个月 age input;
- parent-specific form;
- education-professional-specific form;
- learning context;
- context note about exam-prep not yet included;
- result placeholder;
- ability to save a Demo session to History.

---

## 02.03 Explore the Market

Must include:
- China Mainland / Overseas Benchmark;
- 30 days / 90 days / 1 year;
- age filter;
- skill filter;
- context filter;
- audience filter;
- static Demand Signal demo cards;
- directional trend labels only;
- “更新联网信息” button;
- “已更新至 YYYY年MM月DD日” display.

M1 does not perform real live search.

---

## 02.04 History

Must use SQLite.

Minimum:
- create database if missing;
- create `research_sessions`;
- show sessions;
- empty state;
- save basic Demo session;
- open a basic session detail.

Do not rely only on runtime session state.

---

## 02.05 Manage Data

Must include four tabs:
1. Knowledge Base
2. Structured Data
3. Sources
4. System Status

### Sources
Must support a non-technical maintenance form.

Minimum visible fields:
- 来源名称
- URL
- 地域
- 来源类型
- 是否启用

M1 may store sources in SQLite.

---

# 03 M1 Must NOT Build

Do not implement:
- production LLM calls;
- vector database;
- embeddings;
- PDF / DOCX ingestion pipeline;
- auto-tagging;
- hybrid retrieval;
- live web search;
- Tavily;
- crawler;
- social media collection;
- precise demand statistics;
- recommendation ranking;
- user login;
- cloud database;
- multi-user access control;
- payment;
- social sharing;
- background jobs;
- scheduled tasks.

---

# 04 Allowed M1 Placeholders

Static / demo content is allowed for:
- Market Signal Cards
- AI analysis result preview
- Solution path preview
- Knowledge Base counts
- System Status
- future M4 web-update message

Placeholders must be visually labeled so they are not mistaken for live data.

---

# 05 Technical Priority

M1 priority:

1. runnable
2. correct page structure
3. correct flow
4. local persistence
5. clear UI
6. visual polish

Do not reverse this priority.

---

# 06 Recommended Minimal Stack

Default shortest path:
- Python
- Streamlit
- SQLite
- local filesystem

Do not add a separate backend service in M1 unless an existing project architecture already requires it.

---

# 07 Acceptance Criteria

M1 PASS requires all of the following:

1. App starts locally with one documented command.
2. Homepage clearly shows the correct four navigation destinations.
3. Solve a Need supports Parent and Education Professional.
4. Forms differ by user type.
5. Age supports years + months.
6. Professional skill taxonomy matches `01M1_TAXONOMY.md`.
7. Market page visibly distinguishes China and Overseas Benchmark.
8. Market page supports 30d / 90d / 1y.
9. Market page avoids fake precise percentages.
10. Market page shows “更新联网信息”.
11. Market page shows “已更新至 YYYY年MM月DD日”.
12. History persists in SQLite.
13. At least one Demo Research Session can be saved and reopened.
14. Manage Data exists.
15. Sources can be added through a simple non-technical form.
16. M1 does not require any external API key.
17. M1 does not prematurely implement M2–M6.
