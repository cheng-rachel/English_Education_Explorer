"""M5 产品概念的共享展示与本地 History 保存，不调用生成或搜索服务。"""

import json
import re
from difflib import SequenceMatcher

import streamlit as st

from db import save_research_session
from app_status import KNOWLEDGE_UNAVAILABLE, source_type_label
from market_session import age_range_text, market_datetime, display_text
from market_quality import clean_evidence_url, readable_excerpt
from need_session import join_labels
from output_safety import sanitize_data, sanitize_text

RESULT_KEY = "bs_result"
BRIEF_KEY = "bs_brief"
SAVED_KEY = "bs_saved"
HANDOFF_KEY = "bs_handoff"
RESTORE_KEY = "bs_history_restore"


def is_product_concept(record):
    return isinstance(record, dict) and record.get("kind") == "product_concept"


def fingerprint(record):
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def product_title(record):
    record = sanitize_data(record)
    concept = (record.get("solution") or {}).get("product_concept") or {}
    return f"{concept.get('name') or '英语教育产品概念'}｜Build a Solution"


def restore_state(record, session_id=None):
    record = sanitize_data(record)
    state = {RESULT_KEY: record, BRIEF_KEY: sanitize_data(record.get("opportunity_brief") or {})}
    if session_id is not None:
        state[SAVED_KEY] = {"fingerprint": fingerprint(record), "id": session_id}
    return state


def save_product_concept(record):
    record = sanitize_data(record)
    value = fingerprint(record)
    saved = st.session_state.get(SAVED_KEY) or {}
    if saved.get("fingerprint") == value:
        return saved["id"]
    session_id = save_research_session(
        title=product_title(record), user_type="教育工作者", entry_type="build_solution",
        summary=record, status="product_concept",
    )
    st.session_state[SAVED_KEY] = {"fingerprint": value, "id": session_id}
    return session_id


def _bullets(items, empty="待进一步明确。"):
    items = sanitize_data(items)
    if not items:
        st.caption(empty)
    else:
        for item in items:
            st.markdown(f"- {_short(item, 400)}")


def render_opportunity_brief(brief, expanded=True, title="Opportunity Brief｜机会简报"):
    brief = sanitize_data(brief)
    title = sanitize_text(title)
    with st.expander(title, expanded=expanded):
        source = {"solve_need": "Solve a Need · 已有学习需求", "market_insight": "Explore the Market · 所选洞察",
                  "scratch": "从空白开始"}.get(brief.get("source_type"), "已有机会资料")
        st.caption(f"来源：{source}")
        for note in (brief.get("source_context") or {}).get("adaptation_notes") or []:
            st.info(note)
        for note in brief.get("scope_notes") or []:
            st.info(note)
        c1, c2 = st.columns(2)
        c1.markdown(f"**目标用户**  \n{brief.get('target_user') or '待明确'}")
        c2.markdown(f"**目标年龄**  \n{age_range_text(brief.get('age_range'))}")
        st.markdown(f"**核心能力**：{join_labels(brief.get('skills'))}")
        st.markdown(f"**学习场景**：{join_labels(brief.get('contexts'))} · **市场范围**：{brief.get('region') or '中国大陆'}")
        st.markdown("**核心需求**")
        st.write(brief.get("core_need") or brief.get("pain_point") or "待明确")
        if brief.get("pain_point") and brief.get("pain_point") != brief.get("core_need"):
            st.markdown("**具体痛点**")
            st.write(brief["pain_point"])
        landscape = brief.get("existing_landscape") or []
        if landscape:
            st.markdown("**已知解决方式**")
            for item in landscape:
                if isinstance(item, dict):
                    name = item.get("route_name") or item.get("title") or item.get("mechanism") or "已有方式"
                    description = item.get("summary") or item.get("description") or item.get("what_exists") or item.get("why_it_fits") or "待补充说明"
                    st.markdown(f"- **{name}**：{description}")
                else:
                    st.markdown(f"- {item}")
        if brief.get("gap"):
            st.markdown("**继承的机会线索 · 仍需验证**")
            st.write(brief["gap"])
        if brief.get("preferred_carriers"):
            st.caption(f"载体偏好：{join_labels(brief['preferred_carriers'])}")
        evidence = brief.get("evidence_sources") or []
        st.caption(f"已携带 {len(evidence)} 条参考资料。生成将使用当前简报与已有资料，不自动联网补充。")
        if evidence:
            st.caption("主要资料：" + "；".join(item.get("title") or "未命名来源" for item in evidence[:3]))


_SCOPE_LABELS = {
    "activity": "教学活动", "prompt_tool": "Prompt / AI 小工具", "lightweight_app": "轻量应用",
    "full_product": "完整产品", "service": "真人服务", "hybrid": "混合方案",
}


def _short(value, limit=180):
    return display_text(value or "", limit=limit)


def _same_statement(first, second):
    """Hide repeated wording in presentation; keep the complete record untouched."""
    first = re.sub(r"[\W_]+", "", str(first or ""))
    second = re.sub(r"[\W_]+", "", str(second or ""))
    if not first or not second:
        return False
    return first == second or (min(len(first), len(second)) >= 12 and
                              ((first in second or second in first) or SequenceMatcher(None, first, second).ratio() >= .72))


def _source_reason(source, solution):
    """Explain an existing citation without inferring effects from a title or excerpt."""
    if source.get("evidence_role") == "learning_reference":
        return "Learning Reference｜用于年龄适配、能力发展与教学练习方式，不证明真实市场需求或产品效果。"
    source_id = source.get("id")
    matches = [item.get("mechanism") for item in solution.get("solution_landscape") or []
               if source_id and source_id in (item.get("evidence_ids") or []) and item.get("mechanism")]
    if matches:
        return "用于核对" + "、".join(matches[:2]) + "的已有做法，不代表效果已得到验证。"
    if source.get("region") == "general_reference" or source.get("raw_category") == "learnpath":
        return "提供学习路径与年龄适配背景，不证明市场需求或产品效果。"
    if source_id and source_id in (solution.get("evidence_ids") or []):
        return "本方案引用的设计背景；具体适用范围和效果仍需核验。"
    return "继承的参考资料，尚未用于支持具体方案判断。"


def render_solution_evidence(evidence, solution, title="参考资料"):
    """Build presentation only: preserve inherited evidence, without Market reclassification."""
    evidence = sanitize_data(evidence or [])
    with st.expander(f"{title}（{len(evidence)}）", expanded=False):
        if not evidence:
            st.caption("当前没有可引用的资料，以下方案应作为待验证假设。")
        for source in evidence:
            st.markdown(f"**{_short(source.get('id') or '—', 30)}｜{_short(source.get('title') or '未命名资料', 80)}**")
            kind = source_type_label(source.get("source_type")) or "参考资料"
            st.caption(_short(kind, 80))
            st.markdown(_source_reason(source, solution))
            url = clean_evidence_url(source.get("url") or source.get("source_url") or "")
            if url:
                label = "查看官网" if kind in ("产品 / 机构官网", "产品官网", "教育机构官网", "官方产品") else "查看原文"
                st.markdown(f"[{label}](<{url}>)")
            else:
                st.caption("本地资料")
            excerpt = readable_excerpt(source.get("content") or source.get("text") or "", limit=140)
            if excerpt:
                with st.expander("查看引用片段", expanded=False):
                    st.markdown(_short(excerpt, 140))


def render_product_concept(record, key_prefix="bs"):
    """Five decision sections, shared by Build and History; never generate on restore."""
    record = sanitize_data(record)
    solution = record.get("solution") or {}
    brief = record.get("opportunity_brief") or {}
    evidence = record.get("evidence_sources") or brief.get("evidence_sources") or []
    meta = record.get("analysis_meta") or {}
    concept = solution.get("product_concept") or {}
    st.subheader(_short(concept.get("name") or "待验证的方案", 100))
    st.caption(f"生成时间：{market_datetime(record.get('generated_at'))} · {_short(meta.get('provider') or '生成方式待确认', 70)}")
    references = {source.get("source_url") or source.get("url") or source.get("document_id")
                  or source.get("original_path") or source.get("title") for source in evidence
                  if source.get("evidence_role") == "learning_reference" or source.get("region") == "general_reference"
                  or source.get("raw_category") == "learnpath"}
    st.caption(f"本次带入学习参考（Learning Reference）：{len(references - {None, ''})} 条 · 用于学习与教学设计，不代表市场需求证据。")
    if meta.get("mode") == "demo":
        st.caption("Demo：当前为规则生成的产品假设，尚未经过 Live AI 综合判断。")
    else:
        st.caption("这是待验证的设计判断，模型分析不代表已验证事实。")
    if meta.get("error"):
        st.info("本次 AI 生成未完成，已提供 Demo 方案。可在 Manage Data → AI Settings 检查配置后重新生成。")
    retrieval = meta.get("retrieval") or {}
    if retrieval.get("status") == "unavailable":
        st.info(KNOWLEDGE_UNAVAILABLE)
    elif retrieval.get("status") == "no_matches":
        st.caption("本次未检索到匹配的本地资料；以下是待验证的设计建议。")

    judgment = solution.get("product_judgment") or {}
    with st.container(border=True):
        st.markdown("### ① 产品判断")
        st.markdown("**这个需求最适合做成什么？**")
        st.markdown(f"**{_SCOPE_LABELS.get(solution.get('solution_scope'), '尚未判断')}**")
        st.markdown(f"**当前建议**：{_short(judgment.get('recommendation') or '这份历史方案尚未记录产品化判断；可继续调整方案后再决定。', 260)}")
        if judgment.get("reasons"):
            st.markdown("**为什么**")
            _bullets([_short(reason) for reason in judgment["reasons"][:4]])

    opportunity = solution.get("opportunity") or {}
    gap = solution.get("opportunity_gap") or {}
    goal = solution.get("teaching_goal") or {}
    with st.container(border=True):
        st.markdown("### ② Opportunity · 真正要解决什么")
        st.markdown(f"**目标用户**：{_short(concept.get('target_user') or brief.get('target_user') or '待明确')} · {age_range_text(brief.get('age_range'))}")
        st.markdown(f"**能力 / 场景**：{join_labels(brief.get('skills'))} / {join_labels(brief.get('contexts'))}")
        core_need = brief.get("core_need") or concept.get("core_problem") or "待明确"
        problem = opportunity.get("problem_to_solve") or concept.get("core_problem") or core_need
        shown = [core_need]
        st.markdown(f"**核心需求**：{_short(core_need)}")
        if not _same_statement(problem, core_need):
            st.markdown(f"**要解决的问题**：{_short(problem)}")
            shown.append(problem)
        facts = [item for item in opportunity.get("reported_facts") or [] if not any(_same_statement(item, value) for value in shown)]
        if opportunity.get("reported_facts"):
            st.caption("已提供的情况 · 尚非独立核验")
        if facts:
            _bullets([_short(item) for item in facts[:3]])
        st.markdown("**尚待确认**")
        _bullets([_short(item) for item in opportunity.get("unknowns") or []], "这份历史方案尚未区分已知情况与待确认问题。")
        st.markdown(f"**待验证机会假设**：{_short(gap.get('opportunity') or '现有资料尚不足以判断机会缺口。', 240)}")
        st.caption("已有使用阻力仅代表所附资料中的观察，不能据此推断普遍市场缺口。" if gap.get("status") == "observed_friction"
                   else "现有资料尚不足以证明普遍市场缺口；以上机会需要先验证。")

    mechanism = solution.get("solution_mechanism") or {}
    carrier = solution.get("carrier") or {}
    with st.container(border=True):
        st.markdown("### ③ 核心机制 · 最值得先验证什么")
        steps = mechanism.get("steps") or []
        st.markdown(" → ".join(_short(step, 90) for step in steps[:6]) if steps
                    else _short(concept.get("core_mechanism") or "机制待明确"))
        st.markdown(f"**为什么值得先试**：{_short(mechanism.get('why_it_might_work') or '仍需明确机制依据。', 240)}")
        st.markdown("**如果第一版只能保留一个交互，会是什么？**")
        st.markdown(_short(solution.get("core_interaction") or "这份历史方案尚未明确一个核心交互。", 260))
        st.markdown(f"**Carrier · 最轻可验证载体**：{join_labels(carrier.get('choices'))}")
        st.caption(_short(carrier.get("rationale") or "需先确认现有设备或活动能否完成验证。", 250))
        st.markdown(f"**Teaching Goal · 学习变化**：{_short(goal.get('learning_outcome') or '待明确')}")
        st.caption(f"希望看到的行为变化：{_short(goal.get('behavior_change') or '待明确')}")

    mvp = solution.get("mvp") or {}
    prototype = solution.get("fast_prototype") or {}
    validation = solution.get("validation_plan") or {}
    with st.container(border=True):
        st.markdown("### ④ MVP · 第一版只做什么")
        st.markdown("**Must Have · 验证所必需**")
        for item in (mvp.get("core_features") or [])[:5]:
            st.markdown(f"- **{_short(item.get('name') or '待明确', 70)}**：{_short(item.get('why_essential') or '需说明如何验证核心交互。')}")
        st.markdown("**最小 Demo**")
        st.markdown(f"- **验证什么**：{_short(goal.get('learning_outcome') or '观察核心交互能否带来目标学习变化。', 150)}")
        pages = "；".join(_short(page.get("name") or "待明确", 70) for page in mvp.get("key_pages") or [])
        st.markdown("- **页面 / 材料**：" + (pages or "待明确"))
        st.markdown("- **最少数据**：" + join_labels(mvp.get("minimal_data")))
        st.markdown("- **最少 AI 能力**：" + join_labels(mvp.get("minimal_ai_capability")))
        st.markdown(f"- **一周内怎么测**：{_short(validation.get('sample') or '先找少量目标用户')}；{_short(validation.get('comparison') or '观察同一核心交互前后的变化。')}")
        with st.expander("Later · 这次先不做", expanded=False):
            _bullets(mvp.get("not_now"))
        st.caption("快速原型：" + _short(prototype.get("approach") or "先用最轻的材料和一个交互验证核心机制。", 180))
        with st.expander("查看快速原型方案", expanded=False):
            for page in mvp.get("key_pages") or []:
                st.markdown(f"- **{_short(page.get('name') or '页面')}**：{_short(page.get('purpose') or '待明确')}")
            st.markdown("**AI Role｜AI 负责什么**")
            _bullets(solution.get("ai_role"))
            st.markdown("**Human Role｜人负责什么**")
            _bullets(solution.get("human_role"))
            with st.expander("查看 / 复制 Prompt", expanded=False):
                if prototype.get("copyable_prompt"):
                    st.code(prototype["copyable_prompt"], language="text")
                else:
                    st.caption("本方案未保存 Prompt。")

    metrics = solution.get("validation_metrics") or {}
    decision = solution.get("validation_decision") or {}
    with st.container(border=True):
        st.markdown("### ⑤ Validation · 什么结果值得继续")
        columns = st.columns(3)
        for col, key, label in zip(columns, ("learning", "behavior", "product"), ("Learning Metric", "Behavior Metric", "Product Metric")):
            with col:
                metric = metrics.get(key) or {}
                st.markdown(f"**{label}**")
                st.markdown(_short(metric.get("metric") or "待明确"))
                st.caption(_short(metric.get("how_to_measure") or "测量方式待明确"))
        st.caption(f"验证周期：{_short(validation.get('duration') or '待明确')}")
        for key, label in (("continue", "Continue · 继续"), ("adjust", "Adjust · 调整"), ("stop", "Stop · 停止产品化")):
            st.markdown(f"**{label}**：{_short(decision.get(key) or '这份历史方案尚未单独记录该条件。', 240)}")
        if not decision and validation.get("decision_criteria"):
            with st.expander("查看原有验证条件", expanded=False):
                _bullets(validation["decision_criteria"])

    with st.expander("Solution Landscape · 现有解决方式", expanded=False):
        landscape = solution.get("solution_landscape") or []
        if landscape:
            rows = []
            for item in landscape:
                rows.append({"解决方式": _short(item.get("mechanism") or "待明确", 60),
                             "已经解决什么": _short(item.get("what_exists") or "待核验", 150),
                             "仍需验证什么": _short(item.get("what_remains_unresolved") or "待核验", 150)})
            st.table(rows)
            ids = {source_id for item in landscape for source_id in item.get("evidence_ids") or []}
            render_solution_evidence([source for source in evidence if source.get("id") in ids], solution, "查看相关资料")
        else:
            st.caption("当前资料不足，暂不展开该类方案。")
        st.markdown(f"**已有方案的优势**：{_short(gap.get('existing_strength') or '待核验')}")
        st.markdown(f"**使用阻力 / 缺少的支持**：{_short(gap.get('remaining_friction') or '尚缺直接使用记录。')}")
    render_solution_evidence(evidence, solution)
    with st.expander("Demo Build Path · 查看详细搭建路径", expanded=False):
        for index, item in enumerate(solution.get("demo_build_path") or [], 1):
            st.markdown(f"**{item.get('step') or index}. {_short(item.get('title') or '搭建步骤')}**")
            st.markdown(_short(item.get("action") or "待明确行动。", 500))
            st.caption(f"产出：{_short(item.get('deliverable') or '待明确')}")
        st.markdown("**机制依赖的假设**")
        _bullets(mechanism.get("assumptions"))
    with st.expander("Risks · 三个关键风险", expanded=False):
        for item in (solution.get("risks") or [])[:3]:
            st.markdown(f"- **{_short(item.get('risk') or '待确认风险')}**")
            st.markdown(f"低成本检验：{_short(item.get('cheap_test') or '待明确')}")
    if meta.get("revision_history"):
        with st.expander("方案调整记录", expanded=False):
            for revision in meta["revision_history"]:
                st.markdown(f"- {market_datetime(revision.get('at') or revision.get('generated_at'))}：{_short(revision.get('instruction') or '', 300)}")
    if record.get("original_opportunity_brief"):
        render_opportunity_brief(record["original_opportunity_brief"], expanded=False, title="调整前的原始机会简报")
