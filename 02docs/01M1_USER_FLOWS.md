# EngEduScope｜M1 User Flows

## 01 M1 Purpose
M1 validates the product information architecture and interaction skeleton.

M1 does not need production AI intelligence.

The key question is:

> Can a user understand the product and successfully move through the intended paths?

---

# 02 Homepage

## Main Hero

# Build a Solution

> 从真实英语学习需求出发，理解问题、观察市场，并构建可验证的教育解决方案。

## Primary Entry 01
🔍 **Solve a Need**  
**我有具体英语学习需求**

## Primary Entry 02
📡 **Explore the Market**  
**我想观察英语教育需求变化**

## Supporting Entry
📚 **History**  
**回到我的历史方案库**

## Maintenance
Top-right:
⚙ **Manage Data**

Visual priority:
1. Build a Solution
2. Solve a Need / Explore the Market
3. History
4. Manage Data

---

# 03 Solve a Need｜Identity Selection

First choose:

- 我是家长
- 我是教育工作者

When “教育工作者” is selected, display:

> 本 Demo 所指教育工作者，主要包括教研工作者、课程设计师、AI 教育产品经理与创业者。针对一线英语教师与培训机构负责人的功能将在后续版本中推出。

---

# 04 Parent Flow A｜I Have a Specific Problem

Parent  
→ Exact Age  
→ Describe Problem  
→ Optional high-level skill support  
→ Learning Context  
→ Current Learning Method  
→ Result Placeholder

### Age
- 3–15 years
- 0–11 months

Display:
`X岁X个月`

### Parent Skill UI
Use:
- 听
- 说
- 读
- 写

Parent does not need to see the full professional taxonomy in M1.

### Problem Description
Large text input.

Example placeholder:
> 例如：孩子分级阅读已经读了一段时间，但平时很少主动开口说英语……

### Learning Context
Multi-select.

### Current Learning Method
Allow a simple text field and/or multi-select:
- 机构课程
- 分级阅读
- AI / App
- 真人外教
- 线下老师
- 家长陪伴
- 其他

### M1 Submit
Button:
**分析这个学习需求**

M1 result:
show a clearly labeled placeholder result card.

No real LLM analysis required in M1.

---

# 05 Parent Flow B｜I Am Not Sure What the Problem Is

Parent  
→ Exact Age  
→ choose:
**我想整体看看孩子目前需要什么**
→ short learning-background form
→ high-level Listen / Speak / Read / Write status
→ contexts
→ current carriers
→ Result Placeholder

M1 only needs the entry and simple form shell.

---

# 06 Education Professional Flow｜Solve a Need

Education Professional  
→ Exact Age or Age Range  
→ Detailed Skill  
→ Learning Context  
→ Learning Carrier  
→ Pain Point  
→ Generate Placeholder

Fields:

### Age
Support:
- exact age: X岁X个月
- age range where useful

### Skill
Use professional taxonomy.

### Context
Use M1 taxonomy.

Show note:

> 本 Demo 目前主要针对日常生活与常规英语学习情境。针对考试备考的功能将在后续版本中推出。

### Carrier
Use M1 taxonomy.

### Pain Point
Large text input.

### Future Output Preview
M1 may show a preview structure:

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

Button:
**生成解决方案路径**

No production generation required in M1.

---

# 07 Explore the Market Flow

Education-professional oriented.

Flow:

Explore the Market  
→ Region  
→ Time Window  
→ Age  
→ Skill  
→ Context  
→ Audience  
→ Demand Signal Cards  
→ Insight Detail placeholder  
→ Build a Solution placeholder

### Region
- 中国大陆
- 海外 Benchmark

Do not mix them into one combined metric.

### Time
- 近30天
- 近90天
- 近1年

### Age
Support exact age / age range UI appropriate to market research.

### Skill
Professional taxonomy.

### Context
M1 taxonomy.

### Audience
Six audience groups.

### Online Update UI
Show:

**更新联网信息**

Next to it:

**已更新至 YYYY年MM月DD日**

In M1:
- button does not perform real web search;
- button may refresh the displayed date or show a “M4将接入联网更新” message.

### Market Cards
Use 3–5 static demo cards.

Each card can include:
- Need title
- trend: 上升 / 稳定 / 下降
- demand level: 高 / 中 / 低
- age tag
- skill tag
- audience tag
- China / overseas tag

Avoid fake percentages.

---

# 08 History Flow

History  
→ list Research Sessions  
→ open session detail

M1 must:
- initialize SQLite;
- store at least a basic Research Session;
- show an empty state if no sessions exist;
- allow saving one demo Solve a Need submission.

M1 does not need full restoration of AI state.

---

# 09 Manage Data Flow

Manage Data should have four tabs:

1. Knowledge Base
2. Structured Data
3. Sources
4. System Status

## Sources
Must be friendly to non-technical maintainers.

Suggested visible form fields:
- 来源名称
- 官网 / 来源网址
- 地域
- 来源类型
- 是否启用

Do not expose:
- database IDs
- vector settings
- crawler config
- embedding config

M1 only needs simple storage and display.

---

# 10 M1 Success Flow

A tester should be able to:

Home  
→ Solve a Need  
→ choose Parent  
→ enter age and problem  
→ submit  
→ see result placeholder  
→ save to History  
→ open History

and:

Home  
→ Explore the Market  
→ change market filters  
→ inspect demo cards  
→ see last-updated date

and:

Home  
→ Manage Data  
→ Sources  
→ add one source record

If these three flows work, the M1 interaction skeleton is successful.
