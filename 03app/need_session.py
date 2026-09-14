"""EngEduScope｜Solve a Need 会话的共享展示与命名逻辑（M1 Step 4 + M3）。

供 02_solve_need.py 与 04_history.py 共同使用：
- Analysis Result 渲染（M3：家长 / 教育工作者两套，保存前后展示一致）
- Demo 占位结果渲染（M1；无 LLM 时或旧记录仍可显示）
- Research Session 标题自动生成（简单规则，不用 AI，不新增分类标签）
- sn_result → research_sessions 字段映射
- 时间格式化

sn_result 的字段结构由 02_solve_need.py / need_analysis.py 定义，这里只读不改。
"""

import json
from datetime import datetime

import streamlit as st
from app_status import KNOWLEDGE_UNAVAILABLE, source_type_label
from output_safety import sanitize_data, sanitize_text

RESULT_NOTE = "这条历史记录保存了需求输入，尚未生成分析。恢复到 Solve a Need 后即可继续。"
DISCLAIMER = (
    "English Education Explorer 提供学习建议，不作医学、心理、学习障碍或语言障碍诊断。以上分析基于家长、学生或教育工作者提供的信息与参考资料，"
    "描述的是可能性与可验证的方向；如果孩子仍存在明显困难，可以进一步咨询专业人士。"
)
MOCK_NOTE = "这份结果使用 Demo 生成：分析内容为模板示意，参考资料与本次检索状态见下方。可在 Manage Data → AI Settings 配置 Live AI 后重新分析。"
FEEDBACK_KEY = "sn_rank_feedback"

# sn_result.user_type → research_sessions.user_type
USER_TYPE_LABELS = {"parent": "家长", "student": "学生", "professional": "教育工作者"}
STUDENT_SKILL_LABELS = ["听力", "口语", "阅读", "写作", "单词", "语法", "不确定"]

# sn_result.entry_type → research_sessions.entry_type
DB_ENTRY_TYPES = {
    "parent_specific": "solve_need_parent_specific",
    "parent_overview": "solve_need_parent_overview",
    "professional": "solve_need_educator",
    "student_specific": "solve_need_student",
}

# research_sessions.entry_type → 用户可见说明
ENTRY_TYPE_LABELS = {
    "solve_need_parent_specific": "家长 · 具体问题",
    "solve_need_parent_overview": "家长 · 整体看看",
    "solve_need_educator": "教育工作者 · 需求探索",
    "solve_need_student": "学生 · 英语练习需求",
}


# ── 通用小工具 ────────────────────────────────────────────────────────────
def join_labels(values):
    return "、".join(sanitize_data(values)) if values else "未选择"


def age_text(age, sep=" – "):
    """精确年龄 → 7岁4个月；年龄范围 → 6岁0个月 – 8岁11个月。"""
    if not isinstance(age, dict):
        return "—"
    age = sanitize_data(age)
    if age.get("mode") == "range":
        return f"{age['start']['display']}{sep}{age['end']['display']}"
    return age.get("display", "—")


def format_datetime(iso_text):
    """2026-09-13T09:20:00 → 2026年09月13日 09:20；解析失败则原样返回。"""
    try:
        value = datetime.fromisoformat(iso_text)
        # macOS C locale 的 strftime 在部分 Python 环境下会将中文格式返回为空。
        return f"{value.year:04d}年{value.month:02d}月{value.day:02d}日 {value.hour:02d}:{value.minute:02d}"
    except (TypeError, ValueError):
        return sanitize_text(iso_text) or "—"


def need_excerpt(result, limit=60):
    """列表卡片摘要：描述 / 学习情况 / Pain Point，超长截断。"""
    result = sanitize_data(result)
    text = (result.get("problem") or result.get("background") or result.get("pain_point") or "").strip()
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit] + "……"
    return text


# ── sn_result → research_sessions 映射 ───────────────────────────────────
def db_user_type(result):
    return USER_TYPE_LABELS.get(result.get("user_type"), result.get("user_type") or "—")


def db_entry_type(result):
    return DB_ENTRY_TYPES.get(result.get("entry_type"), result.get("entry_type") or "—")


def result_fingerprint(result):
    """保存与恢复使用同一指纹，避免从 History 返回后再次保存相同内容。"""
    return json.dumps(result, sort_keys=True, ensure_ascii=False)


def history_restore_state(result, session_id=None):
    """恢复原始表单和完整分析快照；不触发新的 API 调用。"""
    from taxonomy import SKILL_PARENT_LABELS

    result = sanitize_data(result)
    state = {"sn_result": result}
    if session_id is not None:
        state["sn_saved"] = {"fingerprint": result_fingerprint(result), "id": session_id}
    parent = result.get("user_type") == "parent"
    student = result.get("user_type") == "student"
    state["sn_identity"] = "我是学生" if student else "我是家长" if parent else "我是教育工作者"

    def age_fields(prefix, age):
        if isinstance(age, dict):
            state[f"{prefix}_y"] = age.get("years")
            state[f"{prefix}_m"] = age.get("months")

    age = result.get("age") or {}
    if student:
        age_fields("sn_s_age", age)
        state["sn_s_problem"] = result.get("problem") or ""
        for field in ("skills", "contexts"):
            state[f"sn_s_{field}"] = result.get(field) or []
    elif parent:
        state["sn_parent_path"] = (
            "我有一个具体英语学习问题" if result.get("entry_type") == "parent_specific"
            else "我想整体看看孩子目前需要什么"
        )
        age_fields("sn_p_age", age)
        for field in ("problem", "background", "methods_note"):
            state[f"sn_p_{field}"] = result.get(field) or ""
        for field in ("contexts", "methods"):
            state[f"sn_p_{field}"] = result.get(field) or []
        for index, label in enumerate(SKILL_PARENT_LABELS):
            state[f"sn_p_skill_{index}"] = label in (result.get("skills") or [])
    else:
        state["sn_e_age_mode"] = "年龄范围" if age.get("mode") == "range" else "精确年龄"
        if age.get("mode") == "range":
            age_fields("sn_e_age_start", age.get("start"))
            age_fields("sn_e_age_end", age.get("end"))
        else:
            age_fields("sn_e_age", age)
        state["sn_e_pain"] = result.get("pain_point") or ""
        for field in ("skills", "contexts", "carriers"):
            state[f"sn_e_{field}"] = result.get(field) or []
    return state


def make_title(result):
    """按简单规则生成标题，只使用已有标签。

    家长（具体问题）：7岁4个月｜说、读相关学习需求（无能力选择时：7岁4个月｜英语学习需求）
    家长（整体看看）：7岁4个月｜整体英语学习需求
    教育工作者：      6岁0个月–8岁11个月｜口语表达、听力解码｜家庭固定学习｜需求探索
                      （无场景时最后一段为「学习需求探索」）
    """
    result = sanitize_data(result)
    age = age_text(result.get("age"), sep="–")
    skills = result.get("skills") or []
    entry = result.get("entry_type")
    analysis_skills = (result.get("need_analysis") or {}).get("primary_skills") or []

    if entry == "student_specific":
        focus = analysis_skills or [skill for skill in skills if skill != "不确定"]
        return f"{age}｜{'、'.join(focus[:2]) or '英语'}练习计划"

    if entry == "parent_specific":
        if analysis_skills:
            return f"{age}｜{'、'.join(analysis_skills[:2])}相关学习需求"
        return f"{age}｜{'、'.join(skills)}相关学习需求" if skills else f"{age}｜英语学习需求"
    if entry == "parent_overview":
        if analysis_skills:
            return f"{age}｜整体英语学习需求（{'、'.join(analysis_skills[:2])}）"
        return f"{age}｜整体英语学习需求"

    # 调整后的方案标题跟随当前设计需求；result.age 等原始表单仍保留供追溯。
    current_need = (result.get("need_analysis") or {}).get("user_need") or {}
    age = current_need.get("age") or age
    skills = current_need.get("core_skills") or skills
    parts = [age]
    if skills:
        parts.append("、".join(skills[:2]))
    contexts = current_need.get("contexts") or result.get("contexts") or []
    if contexts:
        parts.append(contexts[0])
        parts.append("需求探索")
    else:
        parts.append("学习需求探索")
    return "｜".join(parts)


# ── Demo 占位结果渲染 ─────────────────────────────────────────────────────
def _render_parent_result(r):
    is_specific = r.get("entry_type") == "parent_specific"
    st.markdown(f"**孩子年龄**：{age_text(r.get('age'))}")
    st.markdown("**孩子目前遇到的问题**" if is_specific else "**孩子目前的英语学习情况**")
    st.write((r.get("problem") if is_specific else r.get("background")) or "—")

    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**当前关注能力**  \n{join_labels(r.get('skills'))}")
    c2.markdown(f"**主要学习场景**  \n{join_labels(r.get('contexts'))}")
    methods = join_labels(r.get("methods"))
    if r.get("methods_note"):
        methods += f"（{r['methods_note']}）"
    c3.markdown(f"**{'已尝试方式' if is_specific else '当前学习方式'}**  \n{methods}")

    st.markdown("**恢复后可分析**")
    st.markdown("- 可能原因\n- 优先级\n- 3 条解决路径")


def _render_pro_result(r):
    st.markdown("**用户痛点**")
    st.write(r.get("pain_point") or "—")

    c1, c2, c3 = st.columns(3)
    c1.markdown("**教学目标**  \n恢复后可根据痛点与目标年龄生成")
    c2.markdown(f"**目标年龄**  \n{age_text(r.get('age'))}")
    c3.markdown(f"**核心能力**  \n{join_labels(r.get('skills'))}")
    c4, c5 = st.columns(2)
    c4.markdown(f"**核心场景**  \n{join_labels(r.get('contexts'))}")
    c5.markdown(f"**学习载体**  \n{join_labels(r.get('carriers'))}")

    st.markdown("**恢复后可生成**")
    st.markdown("- 解决机制\n- AI 可介入环节\n- MVP 功能\n- 关键页面\n- 验证指标")


def render_demo_result(result):
    """渲染「Demo Result｜M1 占位结果」区块（标题 + 提示 + 内容），不含外层容器。"""
    result = sanitize_data(result)
    st.subheader("已保存的需求输入")
    st.warning(RESULT_NOTE)
    if result.get("user_type") == "student":
        st.markdown(f"**你的年龄**：{age_text(result.get('age'))}")
        st.write(result.get("problem") or "—")
        st.caption(f"想练的能力：{join_labels(result.get('skills'))} · 学习场景：{join_labels(result.get('contexts'))}")
        st.caption("恢复后可以根据这条需求生成今天和接下来一周的练习计划。")
    elif result.get("user_type") == "parent":
        _render_parent_result(result)
    else:
        _render_pro_result(result)


# ── M3：Analysis Result 渲染 ─────────────────────────────────────────────
def _bullets(items, empty="—"):
    items = [i for i in sanitize_data(items or []) if i]
    st.markdown("\n".join(f"- {i}" for i in items) if items else empty)


def _ev_tag(ids):
    ids = [i for i in (ids or []) if i]
    return f" `{'、'.join(ids)}`" if ids else ""


def _used_evidence_ids(result):
    used = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "evidence_ids" and isinstance(v, list):
                    used.update(str(x) for x in v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for key in ("need_analysis", "solution_routes", "product_direction", "mvp_spec", "student_practice_plan", "parent_action_plan"):
        walk(result.get(key))
    return used


def render_evidence(result):
    result = sanitize_data(result)
    evidence = result.get("evidence_sources") or []
    if not evidence:
        if (result.get("analysis_meta") or {}).get("retrieval_status") == "unavailable":
            st.info(KNOWLEDGE_UNAVAILABLE)
        else:
            st.caption("本次未检索到相关资料，以上建议基于机制层面的判断。可前往 Manage Data 补充或更新知识库。")
        return
    used = _used_evidence_ids(result)
    with st.expander(f"Evidence｜参考依据（{len(evidence)} 条）", expanded=False):
        st.caption("以下为本次分析参考的资料；标注「已引用」的条目被分析直接引用，其余为相关背景。资料来源与日期见各条目。")
        for ev in evidence:
            flag = "已引用 · " if ev.get("id") in used else ""
            learning = ev.get("region") == "general_reference" or ev.get("raw_category") == "learnpath"
            region = "通用学习路径参考资料" if learning else ev.get("region", "")
            role = "Learning Reference · " if learning else ""
            head = f"**[{ev.get('id')}] 《{ev.get('title', '')}》**  \n{flag}{role}{region} · {source_type_label(ev.get('source_type')) or '—'} · {ev.get('kind_label', '')}"
            if ev.get("pages"):
                head += f" · {ev['pages']}"
            if ev.get("date"):
                head += f" · {ev['date']}"
            st.markdown(head)
            if ev.get("origin") == "web" and ev.get("content_kind") == "search_snippet":
                st.caption("这条资料来自搜索摘要，尚未取得可读正文。")
            if ev.get("source_url"):
                st.markdown(f"原始来源：[{ev['source_url']}]({ev['source_url']})")
            elif ev.get("original_path"):
                st.caption(f"原始文件：{ev['original_path']}")
            if ev.get("text"):
                st.caption(ev["text"][:220] + ("…" if len(ev["text"]) > 220 else ""))


def _source_counts(result):
    """Count final analysis sources from the saved snapshot, never fetch again."""
    sources = {"local": set(), "web": set()}
    for ev in result.get("evidence_sources") or []:
        identity = (ev.get("source_url") or ev.get("url") or ev.get("document_id")
                    or ev.get("original_path") or ev.get("title"))
        if identity:
            origin = "web" if ev.get("origin") == "web" else "local"
            sources[origin].add(identity)
    return len(sources["local"]), len(sources["web"])


def _result_header(result, title):
    result = sanitize_data(result)
    st.subheader(title)
    meta = result.get("analysis_meta") or {}
    bits = [f"生成时间：{format_datetime(result.get('generated_at'))}"]
    if meta.get("provider"):
        bits.append(f"模型：{meta['provider']}")
    if meta.get("revision_history"):
        bits.append(f"已调整 {len(meta['revision_history'])} 次")
    st.caption(" · ".join(bits))
    local_count, web_count = _source_counts(result)
    st.caption(f"本地知识库：{local_count} 条 · 联网补充：{web_count} 条")
    if meta.get("mode") == "mock":
        st.warning(MOCK_NOTE)
    search = result.get("search_meta") or meta.get("search_meta") or {}
    if isinstance(search, dict) and search:
        messages = {
            "not_configured": "未启用联网服务，本次使用本地资料。",
            "not_requested": "本次未请求联网补充。",
            "local_sufficient": "本地资料已覆盖当前需要，本次未联网。",
            "success": "本次已补充少量公开联网资料。",
            "partial": "部分联网资料未能读取，以下结合已取得的资料与本地资料。",
            "failed": "联网补充未完成，以下仍使用已有本地资料。",
        }
        message = search.get("message") or messages.get(search.get("status"))
        if message:
            st.caption(message)
        if search.get("status") in ("success", "partial") and search.get("searched_at"):
            st.caption(f"本次联网时间：{format_datetime(search['searched_at'])}")
    if result.get("evidence_note"):
        st.info(result["evidence_note"])
    if meta.get("practice_plan_mode") == "general_baseline":
        st.caption("以下练习为通用起步示例，请根据实际表现调整材料和时长。")


def _render_plan_steps(plan, *, student=False):
    """Only the parent/student plan: keep the next action and timing together."""
    plan = sanitize_data(plan or {})
    today = plan.get("today") or {}
    st.markdown("**今天可以怎么练**" if student else "**每天具体做什么**")
    if today.get("duration"):
        st.caption(today["duration"])
    steps = today.get("steps") or []
    st.markdown("\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)) or "先完成一个短任务，观察需要哪一步提示。")
    stages = plan.get("stages") or []
    if stages:
        for stage in stages[:2]:
            st.markdown(f"**{stage.get('period') or '下一阶段'}**")
            if stage.get("duration"):
                st.caption(stage["duration"])
            if stage.get("materials"):
                st.caption("材料：" + "、".join(stage["materials"]))
            _bullets(stage.get("actions"))
            st.markdown("**什么时候进入下一阶段**")
            _bullets(stage.get("advance_when"))
    else:
        st.markdown("**接下来一周怎么安排**")
        for item in plan.get("week_plan") or []:
            st.markdown(f"**{item.get('days') or '本周'}**")
            _bullets(item.get("actions"))
    if plan.get("increase_difficulty_when"):
        st.markdown("**什么时候增加难度**")
        _bullets(plan["increase_difficulty_when"])


def _render_learning_progress(plan, *, student=False):
    plan = sanitize_data(plan or {})
    with st.container(border=True):
        st.markdown("**怎么判断有没有进步**")
        _bullets(plan.get("progress_signals"))
        teacher = plan.get("teacher_support") or {}
        if teacher.get("when") or teacher.get("profile"):
            st.markdown("**什么时候建议找老师**" if student else "**什么时候换方案 / 找老师**")
            _bullets(teacher.get("when"))
            if teacher.get("profile"):
                st.caption("适合的老师类型：" + teacher["profile"])


def _render_learning_evidence(result):
    """Compact parent/student references; professional evidence remains unchanged."""
    result = sanitize_data(result)
    evidence = result.get("evidence_sources") or []
    with st.expander(f"参考资料（{len(evidence)}）", expanded=False):
        if not evidence:
            st.caption("目前可用资料不足，以上是可先试做、再按表现调整的通用方案。")
            return
        st.caption("学习路径和研究帮助解释练法；个人经验只代表该使用者，产品介绍不能单独证明学习效果。")
        uses = {
            "learning_path": "学习路径参考", "practice_guide": "练习方法参考",
            "research_evidence": "研究背景", "parent_experience": "个体使用经验",
            "product_info": "产品功能参考", "policy_background": "政策背景",
            "market_signal": "市场背景", "general_reference": "相关背景",
        }
        for ev in evidence:
            st.markdown(f"**{ev.get('id') or ''}｜{ev.get('title') or '参考资料'}**")
            detail = [uses.get(ev.get("content_role"), "相关背景"), source_type_label(ev.get("source_type"))]
            if ev.get("date"):
                detail.append(ev["date"])
            st.caption(" · ".join(value for value in detail if value))
            if ev.get("source_url"):
                st.markdown(f"[查看原文]({ev['source_url']})")
            elif ev.get("original_path"):
                st.caption("本地资料")
            if ev.get("text"):
                with st.expander(f"查看引用片段 · {ev.get('id') or '资料'}", expanded=False):
                    text = ev["text"]
                    st.caption(text[:150] + ("…" if len(text) > 150 else ""))


def _render_student_analysis(result):
    _result_header(result, "我的英语练习计划")
    plan = result.get("student_practice_plan") or {}
    with st.container(border=True):
        st.markdown("**你现在可能卡在哪里**")
        st.write(plan.get("bottleneck") or "先做一个短任务，再观察具体卡在哪一步。")
        st.markdown("**先解决什么**")
        _bullets((plan.get("priorities") or [])[:2])
    with st.container(border=True):
        _render_plan_steps(plan, student=True)
    _render_learning_progress(plan, student=True)
    _render_learning_evidence(result)
    st.caption(DISCLAIMER)


def _render_route(route, index, *, show_options=False):
    route = sanitize_data(route)
    with st.container(border=True):
        st.markdown(f"**路径 {index}｜{route.get('route_name', '')}**")
        if route.get("mechanism"):
            st.caption(f"机制：{route['mechanism']}")
        st.write(route.get("why_it_fits") or "")
        st.markdown(
            f"时间投入 **{route.get('time_cost', '—')}** ｜ 成本 **{route.get('money_cost', '—')}** ｜ "
            f"家长参与 **{route.get('parent_involvement', '—')}** ｜ 匹配度 **{route.get('suitability', '—')}**"
        )
        with st.expander("具体怎么做", expanded=show_options):
            st.markdown("**建议做法**")
            _bullets(route.get("recommended_actions"))
            options = route.get("existing_options") or []
            if options:
                st.markdown("**可以考虑的现有方案（不排名）**")
                for opt in options:
                    st.markdown(f"- **{opt.get('name', '')}**：{opt.get('why_match', '')}{_ev_tag(opt.get('evidence_ids'))}")
            if route.get("teacher_profile"):
                st.markdown(f"**更适合找什么类型的老师**  \n{route['teacher_profile']}")
            if route.get("suitable_for"):
                st.markdown(f"**适合**：{route['suitable_for']}")
            if route.get("limitations"):
                st.markdown(f"**局限**：{route['limitations']}")
            if route.get("evidence_ids"):
                st.caption(f"参考依据：{'、'.join(route['evidence_ids'])}")


def _render_diy(diy):
    if not diy:
        return
    diy = sanitize_data(diy)
    with st.container(border=True):
        st.markdown(f"**AI DIY｜{diy.get('title') or '今日小任务'}**" + (f" · {diy['duration']}" if diy.get("duration") else ""))
        steps = diy.get("steps") or []
        if steps:
            st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(steps, start=1)))
        if diy.get("scaffold_reduction"):
            st.caption(f"逐步减少提示：{diy['scaffold_reduction']}")
        if diy.get("copyable_prompt"):
            with st.expander("复制给任意 AI 助手使用的提示词", expanded=not steps):
                st.code(diy["copyable_prompt"], language="text")


def _render_parent_analysis(result, key_prefix):
    need = result.get("need_analysis") or {}
    plan = result.get("parent_action_plan") or {}
    reasoning = result.get("need_reasoning") or need.get("need_reasoning") or {}
    intent = (result.get("need_intent") or {}).get("primary_intent")
    _result_header(result, "需求分析与行动建议")

    with st.container(border=True):
        st.markdown("**当前判断**")
        st.write(need.get("problem_summary") or plan.get("bottleneck") or "先根据一次实际尝试观察孩子需要哪些支持。")
        if reasoning.get("reported_facts"):
            st.caption("已知：以下来自你的描述，尚未经过实际练习核验。")
            _bullets(reasoning["reported_facts"][:2])
        if plan.get("bottleneck") and plan["bottleneck"] != need.get("problem_summary"):
            st.caption(plan["bottleneck"])

    hypotheses = reasoning.get("hypotheses") or []
    if hypotheses or need.get("possible_causes"):
        with st.expander("最可能卡在哪里 · 先怎么验证", expanded=intent == "diagnose_bottleneck"):
            st.caption("以下是待验证的可能原因，不是诊断；先比较表现，再决定采用哪条路径。")
            for item in hypotheses[:4]:
                st.markdown(f"**可能原因：{item.get('cause') or '待确认'}**")
                if item.get("check"):
                    st.write("先验证：" + item["check"])
                if item.get("if_observed"):
                    st.caption("根据表现再行动：" + item["if_observed"])
            if not hypotheses:
                for item in (need.get("possible_causes") or [])[:4]:
                    st.markdown(f"- **{item.get('cause', '')}**：{item.get('why') or '需要结合实际任务确认。'}")
            confirmations = reasoning.get("to_confirm") or need.get("evidence_needed") or []
            if confirmations:
                st.markdown("**仍需确认**")
                _bullets(confirmations[:3])

    with st.container(border=True):
        st.markdown("**先解决什么**")
        priorities = plan.get("priorities") or (need.get("priority") or {}).get("focus_now") or need.get("next_steps") or []
        _bullets(priorities[:2])
    with st.container(border=True):
        st.markdown("**具体怎么做**")
        if plan:
            _render_plan_steps(plan)
        else:
            _bullets(need.get("next_steps") or ["选一个熟悉的小任务，记录是否能独立完成、哪一步需要提示。"])

    routes = result.get("solution_routes") or []
    with st.expander("可以考虑的产品 / 支持方式" if intent == "product_choice" else "其他可选方案", expanded=intent == "product_choice"):
        st.caption("按支持方式列出，不排名。产品资料用于核对功能，实际是否适合需要先试用观察。")
        for i, route in enumerate(routes, 1):
            _render_route(route, i, show_options=intent == "product_choice")
        if result.get("ai_diy"):
            with st.expander("需要时，用 AI 准备一个小任务", expanded=False):
                _render_diy(result["ai_diy"])
    fb_key = f"{key_prefix}_rank_feedback"
    if st.session_state.get(fb_key):
        st.caption("已收到您的反馈。")
    else:
        if st.button("希望根据需求匹配排序", key=f"{key_prefix}_rank_btn"):
            st.session_state[fb_key] = True
            st.rerun()

    if plan:
        _render_learning_progress(plan)
    _render_learning_evidence(result)
    st.caption(DISCLAIMER)


def _render_educator_analysis(result, key_prefix):
    need = result.get("need_analysis") or {}
    user_need = need.get("user_need") or {}
    _result_header(result, "Analysis Result｜产品方案路径")

    with st.container(border=True):
        st.markdown("**User Need｜用户需求**")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Target User**  \n{user_need.get('target_user') or '—'}")
        c2.markdown(f"**Age**  \n{user_need.get('age') or age_text(result.get('age'))}")
        c3.markdown(f"**Core Skill**  \n{join_labels(user_need.get('core_skills'))}")
        c4, c5 = st.columns([1, 2])
        c4.markdown(f"**Context**  \n{join_labels(user_need.get('contexts'))}")
        c5.markdown(f"**Pain Point**  \n{user_need.get('pain_point') or result.get('pain_point') or '—'}")

    with st.container(border=True):
        st.markdown("**Teaching Goal｜教学目标**")
        st.write(need.get("teaching_goal") or "—")

    with st.container(border=True):
        st.markdown("**Existing Solution Landscape｜现有解决方式**")
        landscape = need.get("solution_landscape") or []
        if not landscape:
            st.caption("—")
        for item in landscape:
            line = f"- **{item.get('mechanism', '其他')}**：{item.get('summary', '')}{_ev_tag(item.get('evidence_ids'))}"
            st.markdown(line)
            for ex in item.get("examples") or []:
                st.markdown(f"    - {ex.get('name', '')}：{ex.get('note', '')}{_ev_tag(ex.get('evidence_ids'))}")
        st.caption("按机制归纳，不排名；具体产品 / 机构只来自本地知识库资料。")

    with st.container(border=True):
        st.markdown("**Gap｜现有方案为什么没有完全解决**")
        _bullets(need.get("gap"))

    pd = result.get("product_direction") or {}
    with st.container(border=True):
        st.markdown("**Product Direction｜产品方向**")
        st.markdown(f"**Solution Mechanism**  \n{pd.get('solution_mechanism') or '—'}")
        c1, c2 = st.columns(2)
        c1.markdown(f"**Carrier｜最适载体**  \n{join_labels(pd.get('carrier'))}")
        c2.markdown(f"**Core Scenario｜核心场景**  \n{join_labels(pd.get('core_scenario'))}")
        c3, c4 = st.columns(2)
        c3.markdown(f"**AI Role｜AI 可介入环节**  \n{pd.get('ai_role') or '—'}")
        c4.markdown(f"**Human Role**  \n{pd.get('human_role') or '—'}")

    mvp = result.get("mvp_spec") or {}
    with st.container(border=True):
        st.markdown("**MVP**")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**核心功能**")
            _bullets(mvp.get("core_features"))
            st.markdown("**最小数据需求**")
            _bullets(mvp.get("min_data"))
            st.markdown("**当前不做**")
            _bullets(mvp.get("not_now"))
        with c2:
            st.markdown("**关键页面**")
            _bullets(mvp.get("key_pages"))
            st.markdown("**最小 AI 能力**")
            _bullets(mvp.get("min_ai_capability"))

    vm = result.get("validation_metrics") or {}
    with st.container(border=True):
        st.markdown("**Validation Metrics｜验证指标**")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Learning Metric**")
            _bullets(vm.get("learning"))
        with c2:
            st.markdown("**Behavior Metric**")
            _bullets(vm.get("behavior"))
        with c3:
            st.markdown("**Product Metric**")
            _bullets(vm.get("product"))

    meta = result.get("analysis_meta") or {}
    if meta.get("revision_history"):
        with st.expander("调整记录"):
            for rev in meta["revision_history"]:
                st.markdown(f"- {format_datetime(rev.get('at'))}：{rev.get('instruction', '')}")

    render_evidence(result)
    st.caption(DISCLAIMER)


def render_analysis_result(result, key_prefix="sn"):
    """渲染 M3 Analysis Result（家长 / 教育工作者），不含外层容器。key_prefix 用于区分页面内的按钮 key。"""
    result = sanitize_data(result)
    if result.get("user_type") == "student":
        _render_student_analysis(result)
    elif result.get("user_type") == "parent":
        _render_parent_analysis(result, key_prefix)
    else:
        _render_educator_analysis(result, key_prefix)
