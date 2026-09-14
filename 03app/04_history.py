"""EngEduScope｜M6 History：统一研究方案库。

- 数据来自本地 SQLite research_sessions（见 db.py），最新在前。
- 空状态 / 列表卡片 / 内联详情（由 session_state 中选中的 id 驱动，不另开路由）。
- M3 详情复用共享结构化结果展示，支持恢复原始输入、依据与教育工作者方案；兼容 M1 旧记录。
- 不向用户展示原始 summary_json。
"""

import sqlite3

import streamlit as st

from db import list_research_sessions
from history_library import (
    ALL_AGES, ALL_REGIONS, ALL_SKILLS, ALL_TYPES, TYPE_LABELS, UNSPECIFIED,
    filter_records, parse_summary, session_metadata,
)
from market_session import is_market_research, render_market_research
from solution_session import is_product_concept, render_opportunity_brief, render_product_concept
from need_analysis import has_analysis
from need_session import (
    age_text,
    format_datetime,
    join_labels,
    render_analysis_result,
    render_demo_result,
)
from taxonomy import AGE_BANDS, REGIONS, SKILLS_PROFESSIONAL
from output_safety import sanitize_data

SELECTED_KEY = "hist_selected_id"
FOOTER_NOTE = "保存的分析与参考依据按生成时的内容保留；恢复到 Solve a Need 后可以重新分析或继续调整方案。"
PARSE_WARNING = "这条记录的内容暂时无法完整读取，暂不能查看详情或恢复。原记录已保留。"
FILTER_KEYS = ("hist_filter_type", "hist_filter_skill", "hist_filter_age", "hist_filter_region")


def _parse_summary(summary_json):
    return parse_summary(summary_json)


def _or_dash(text):
    return text if text else "—"


def _toggle_detail(session_id):
    """按钮回调：在脚本主体渲染前更新选中 id，同一时间只展开一条。"""
    current = st.session_state.get(SELECTED_KEY)
    st.session_state[SELECTED_KEY] = None if current == session_id else session_id


def _resume_session(summary, session_id):
    summary = sanitize_data(summary)
    if is_product_concept(summary):
        st.session_state["bs_history_restore"] = {"result": summary, "id": session_id}
        st.switch_page("06_build_solution.py")
        return
    if is_market_research(summary):
        st.session_state["em_history_restore"] = {"result": summary, "id": session_id}
        st.switch_page("03_explore_market.py")
        return
    st.session_state["sn_history_restore"] = {"result": summary, "id": session_id}
    st.switch_page("02_solve_need.py")


def _render_need_section(summary):
    """本次需求：描述 / Pain Point、能力、场景、当前学习方式 / 载体。"""
    summary = sanitize_data(summary)
    st.markdown("**原始输入｜本次需求**")
    if summary.get("user_type") == "student":
        st.markdown("你想解决的英语学习困难")
        st.write(_or_dash(summary.get("problem") or ""))
        c1, c2 = st.columns(2)
        c1.markdown(f"**想练的能力**  \n{join_labels(summary.get('skills'))}")
        c2.markdown(f"**学习场景**  \n{join_labels(summary.get('contexts'))}")
    elif summary.get("user_type") == "parent":
        is_specific = summary.get("entry_type") == "parent_specific"
        st.markdown("孩子目前遇到的问题" if is_specific else "孩子目前的英语学习情况")
        st.write(_or_dash((summary.get("problem") if is_specific else summary.get("background")) or ""))
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**关注能力**  \n{join_labels(summary.get('skills'))}")
        c2.markdown(f"**学习场景**  \n{join_labels(summary.get('contexts'))}")
        methods = join_labels(summary.get("methods"))
        if summary.get("methods_note"):
            methods += f"（{summary['methods_note']}）"
        c3.markdown(f"**{'已尝试方式' if is_specific else '当前学习方式'}**  \n{methods}")
    else:
        st.markdown("Pain Point｜原始输入")
        st.write(_or_dash(summary.get("pain_point") or ""))
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**能力**  \n{join_labels(summary.get('skills'))}")
        c2.markdown(f"**场景**  \n{join_labels(summary.get('contexts'))}")
        c3.markdown(f"**学习载体**  \n{join_labels(summary.get('carriers'))}")


def _render_detail(session, summary):
    session = sanitize_data(session)
    summary = sanitize_data(summary)
    st.divider()
    if is_product_concept(summary):
        render_opportunity_brief(summary.get("opportunity_brief") or {}, expanded=False)
        render_product_concept(summary, key_prefix=f"hist_product_{session['id']}")
        if st.button("恢复到 Build a Solution", key=f"hist_resume_{session['id']}"):
            _resume_session(summary, session["id"])
        return
    if is_market_research(summary):
        render_market_research(summary, key_prefix=f"hist_market_{session['id']}")
        st.caption("这里保留生成时的市场范围、资料依据、追问与机会记录；恢复后可继续研究，联网更新需手动触发。")
        if st.button("恢复到 Explore the Market", key=f"hist_resume_{session['id']}"):
            _resume_session(summary, session["id"])
        return
    st.markdown("**基本信息**")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**用户类型**  \n{_or_dash(session.get('user_type'))}")
    c2.markdown(f"**创建时间**  \n{format_datetime(session.get('created_at'))}")
    age_label = "年龄范围" if (summary.get("age") or {}).get("mode") == "range" else "年龄"
    c3.markdown(f"**原始输入｜{age_label}**  \n{age_text(summary.get('age'))}")

    st.write("")
    _render_need_section(summary)

    st.write("")
    if has_analysis(summary):
        render_analysis_result(summary, key_prefix=f"hist_{session['id']}")
    else:
        render_demo_result(summary)

    st.caption(FOOTER_NOTE)
    if st.button("恢复到 Solve a Need", key=f"hist_resume_{session['id']}"):
        _resume_session(summary, session["id"])


def _render_card(session, selected_id, metadata=None):
    metadata = metadata if metadata is not None else session_metadata(session)
    metadata = sanitize_data(metadata)
    session = sanitize_data(session)
    summary = metadata["summary"]
    session_id = session["id"]
    is_selected = selected_id == session_id

    with st.container(border=True):
        text_col, action_col = st.columns([5, 1], vertical_alignment="center")
        with text_col:
            st.markdown(f"**{metadata['title']}**")
            st.badge(metadata["type"], color={"Solve a Need": "blue", "Market Research": "orange", "Build a Solution": "green"}.get(metadata["type"], "gray"))
            st.caption(f"创建于 {format_datetime(metadata['created_at'])}")
            st.caption(f"年龄：{metadata['age']} · 能力：{'、'.join(metadata['skills']) or UNSPECIFIED}")
            st.caption(f"场景：{'、'.join(metadata['contexts']) or UNSPECIFIED} · 地域：{metadata['region']}")
            if not metadata["readable"]:
                st.warning(PARSE_WARNING)
            else:
                mode = (summary.get("analysis_meta") or {}).get("mode")
                if mode in ("mock", "demo"):
                    st.caption("Demo 结果 · 未调用真实 AI")
                elif metadata["type"] == "Solve a Need" and not has_analysis(summary):
                    st.caption("旧版需求输入，恢复后可以继续分析。")
                if metadata["excerpt"]:
                    st.write(metadata["excerpt"])
        with action_col:
            if metadata["readable"]:
                st.button(
                    "收起详情" if is_selected else "查看详情",
                    key=f"hist_view_{session_id}",
                    on_click=_toggle_detail,
                    args=(session_id,),
                )

        if is_selected and metadata["readable"]:
            try:
                _render_detail(session, summary)
            except Exception:  # noqa: BLE001  结构异常的旧记录不应让页面崩溃
                st.warning(PARSE_WARNING)


def _clear_filters():
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def _filter_controls(records):
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        record_type = c1.selectbox("Type｜研究类型", [ALL_TYPES, *TYPE_LABELS], key=FILTER_KEYS[0])
        skill = c2.selectbox("Skill｜英语能力", [ALL_SKILLS, *SKILLS_PROFESSIONAL], key=FILTER_KEYS[1])
        age = c3.selectbox("Age｜年龄段", [ALL_AGES, *(item[0] for item in AGE_BANDS)], key=FILTER_KEYS[2])
        region = c4.selectbox("Region｜地域", [ALL_REGIONS, *REGIONS, UNSPECIFIED], key=FILTER_KEYS[3])
        if (record_type, skill, age, region) != (ALL_TYPES, ALL_SKILLS, ALL_AGES, ALL_REGIONS):
            st.button("清除筛选", key="hist_reset_filters", on_click=_clear_filters)
    return filter_records(records, record_type=record_type, skill=skill, age=age, region=region)


# ── 页面 ──────────────────────────────────────────────────────────────────
st.title("📚 History")
st.markdown("**回到我的历史方案库**")
st.caption("集中查看需求分析、市场研究与产品方案。选择一条记录查看详情，或恢复到对应页面继续。")

try:
    sessions = list_research_sessions()
except (sqlite3.Error, OSError):
    sessions = None
    st.error("暂时无法读取本地历史记录。请稍后重试；已有记录不会被修改。")
    st.button("重试读取", key="hist_retry_read")

if sessions == []:
    st.info("还没有保存过研究或方案。可从学习需求、市场观察或产品构建开始，完成后保存到这里。")
    st.page_link("02_solve_need.py", label="前往 Solve a Need", icon="🔍")
    st.page_link("03_explore_market.py", label="前往 Explore the Market", icon="📡")
    st.page_link("06_build_solution.py", label="前往 Build a Solution", icon="🧩")
elif sessions:
    records = [session_metadata(session) for session in sessions]
    matched = _filter_controls(records)
    st.caption(f"共 {len(sessions)} 条研究 · 当前显示 {len(matched)} 条 · 最新在前")
    selected_id = st.session_state.get(SELECTED_KEY)
    by_id = {session["id"]: session for session in sessions}
    if not matched:
        st.info("没有符合当前筛选条件的研究。可以调整筛选，或清除筛选查看全部记录。")
    for item in matched:
        _render_card(by_id[item["id"]], selected_id, metadata=item)

st.page_link("01_home.py", label="返回 Home", icon="🏠")
