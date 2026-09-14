"""M5 Build a Solution：机会简报 → 显式生成 / 调整 → History 与 Markdown。"""

from copy import deepcopy
import sqlite3

import streamlit as st

from llm.provider import LLMError
from app_status import ai_error_message
from output_safety import sanitize_data, sanitize_text
from solution_analysis import generate_solution, revise_solution
from solution_context import from_scratch
from solution_export import export_markdown, to_markdown
from solution_session import (
    BRIEF_KEY, HANDOFF_KEY, RESTORE_KEY, RESULT_KEY, SAVED_KEY, fingerprint,
    render_opportunity_brief, render_product_concept, restore_state, save_product_concept,
)
from taxonomy import AGE_MONTHS, AGE_YEARS, CARRIERS, CONTEXTS, REGIONS, SKILLS_PROFESSIONAL, age_to_months


def _clear_work():
    for key in list(st.session_state):
        if key.startswith("bs_"):
            st.session_state.pop(key, None)


def _consume_context():
    restored = st.session_state.pop(RESTORE_KEY, None)
    handoff = st.session_state.pop(HANDOFF_KEY, None)
    if restored:
        _clear_work()
        st.session_state.update(restore_state(restored["result"], restored["id"]))
    elif handoff:
        _clear_work()
        st.session_state[BRIEF_KEY] = sanitize_data(handoff)


def _age_input(label, key, default):
    st.caption(label)
    c1, c2 = st.columns(2)
    year = c1.selectbox("岁", AGE_YEARS, index=AGE_YEARS.index(default), key=f"{key}_y")
    month = c2.selectbox("个月", AGE_MONTHS, index=0, key=f"{key}_m")
    return age_to_months(year, month)


def _scratch_form():
    st.markdown("**从一个学习需求开始**")
    with st.form("bs_scratch_form"):
        target_user = st.text_input("目标用户", key="bs_target_user", placeholder="例如：6–8 岁、已有阅读输入但很少主动说英语的儿童及其家庭")
        c1, c2 = st.columns(2)
        with c1:
            start = _age_input("起始年龄", "bs_age_start", 6)
        with c2:
            end = _age_input("结束年龄", "bs_age_end", 8)
        skills = st.multiselect("主要英语能力", SKILLS_PROFESSIONAL, key="bs_skills")
        contexts = st.multiselect("使用场景", CONTEXTS, key="bs_contexts")
        core_need = st.text_area("核心问题或学习需求", key="bs_core_need", height=120,
                                 placeholder="描述当前困难、已尝试方式，以及希望出现的变化。")
        region = st.radio("主要市场范围", REGIONS, index=0, horizontal=True, key="bs_region")
        preferred = st.multiselect("载体偏好（可选）", CARRIERS, key="bs_preferred_carriers")
        confirmed = st.form_submit_button("确认机会输入", type="primary")
    if confirmed:
        if not target_user.strip() or not core_need.strip():
            st.error("请填写目标用户与核心问题。")
        elif end < start:
            st.error("结束年龄不能早于起始年龄。")
        elif not skills:
            st.error("请至少选择一项主要英语能力。")
        else:
            try:
                brief = from_scratch({"target_user": target_user.strip(), "age_range": [start, end],
                                      "skills": skills, "contexts": contexts, "region": region,
                                      "core_need": core_need.strip(), "preferred_carriers": preferred})
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[BRIEF_KEY] = brief
                st.rerun()


def _generate(brief):
    try:
        with st.spinner("正在根据机会简报形成产品概念与验证计划……"):
            record = generate_solution(brief)
    except LLMError as exc:
        st.session_state["bs_error"] = ai_error_message(exc)
    except Exception:  # noqa: BLE001  输入和旧方案保持可用，不回显服务响应。
        st.session_state["bs_error"] = "本次产品方案暂时无法生成，机会简报已保留。请重试，或在 Manage Data → AI Settings 检查配置。"
    else:
        st.session_state[RESULT_KEY] = record
        st.session_state[BRIEF_KEY] = deepcopy(record.get("opportunity_brief") or brief)
        st.session_state.pop("bs_error", None)
        st.session_state.pop("bs_export", None)
        st.rerun()


def _revision_area(record):
    with st.form("bs_revision_form"):
        st.markdown("**继续调整产品方案**")
        instruction = st.text_area("你希望调整什么？", key="bs_revision_instruction", max_chars=2000,
                                   placeholder="例如：先不做硬件；减少家长参与；缩小到一个核心功能闭环。")
        submitted = st.form_submit_button("调整产品方案")
    if submitted:
        if not instruction.strip():
            st.warning("请先填写调整要求。")
        else:
            try:
                with st.spinner("正在根据当前方案与新要求调整……"):
                    revised = revise_solution(record, instruction.strip())
            except LLMError as exc:
                st.error(ai_error_message(exc))
            except Exception:  # noqa: BLE001
                st.error("本次调整暂时无法完成，原方案与调整要求已保留，请稍后重试。")
            else:
                st.session_state[RESULT_KEY] = revised
                st.session_state[BRIEF_KEY] = deepcopy(revised.get("opportunity_brief") or record["opportunity_brief"])
                st.session_state.pop("bs_error", None)
                st.session_state.pop("bs_export", None)
                st.rerun()


def _save_export_area(record):
    value = fingerprint(record)
    saved = st.session_state.get(SAVED_KEY) or {}
    st.markdown("**保存与导出**")
    if saved.get("fingerprint") == value:
        st.success("产品方案已保存到 History。")
        st.page_link("04_history.py", label="前往 History", icon="📚")
    elif st.button("保存产品方案到 History", key="bs_save"):
        try:
            save_product_concept(record)
        except sqlite3.Error:
            st.error("暂时无法保存到本地 History，当前产品方案仍已保留，请稍后重试。")
        else:
            st.rerun()
    try:
        markdown = to_markdown(record)
    except Exception:  # noqa: BLE001
        st.error("Markdown 暂时无法生成，方案仍可保存到 History。")
        return
    st.download_button("下载 Markdown", data=markdown, file_name="English_Education_Explorer_product_concept.md", mime="text/markdown", key="bs_download")
    if st.button("导出 Markdown 文件", key="bs_export_btn"):
        try:
            path = export_markdown(record)
        except (OSError, ValueError):
            st.error("暂时无法写入 Markdown 文件，请使用下载按钮保存。")
        else:
            st.session_state["bs_export"] = {"fingerprint": value, "path": str(path)}
    exported = st.session_state.get("bs_export") or {}
    if exported.get("fingerprint") == value:
        st.success("Markdown 文件已导出。")
        st.caption(sanitize_text(f"文件位置：{exported['path']}"))


st.title("🧩 Build a Solution")
st.markdown("**我想把已有需求做成一个 AI 英语教学工具**")
st.caption("想清楚工具解决什么、怎么使用，再用一个小 Demo 验证是否有帮助。")
_consume_context()
brief = st.session_state.get(BRIEF_KEY)
if not brief:
    _scratch_form()
else:
    render_opportunity_brief(brief, expanded=not bool(st.session_state.get(RESULT_KEY)))
    st.button("从空白重新开始", key="bs_reset", on_click=_clear_work)
    record = st.session_state.get(RESULT_KEY)
    if st.button("重新生成产品方案" if record else "生成产品方案", key="bs_generate", type="primary"):
        _generate(brief)
    if st.session_state.get("bs_error"):
        st.error(st.session_state["bs_error"])
    record = st.session_state.get(RESULT_KEY)
    if record:
        render_product_concept(record)
        _revision_area(record)
        _save_export_area(record)

st.page_link("01_home.py", label="返回 Home", icon="🏠")
