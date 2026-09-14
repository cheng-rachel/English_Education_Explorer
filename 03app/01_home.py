"""Homepage-only presentation; existing copy, navigation and settings actions stay intact."""

import streamlit as st

from app_status import get_status

# Stable keyed containers scope every style to this page, including after navigation.
st.markdown("""
<style>
.st-key-ee_home {
    --ee-orange: #B75B2B;
    --ee-orange-soft: #FFF7F0;
    --ee-ink: #30312F;
    --ee-muted: #696761;
    --ee-border: #E8E2DB;
    container-type: inline-size;
    container-name: ee-home;
    gap: 1.4rem;
    color: var(--ee-ink);
}
.st-key-ee_home .ee-hero {
    text-align:center;
    padding: 1.2rem 0 2.2rem;
    max-width: 880px;
    margin: 0 auto;
}
.st-key-ee_home .ee-hero::before {
    content: "";
    display: block;
    width: 38px;
    height: 4px;
    margin: 0 auto 1.35rem;
    background: var(--ee-orange);
    border-radius: 4px;
}
.st-key-ee_home .ee-hero h1 {
    color: var(--ee-ink);
    font-size: clamp(1.9rem, 3.4cqi, 2.75rem);
    font-weight: 700;
    line-height: 1.2;
    letter-spacing: -0.035em;
    padding: 0;
    margin: 0 0 0.8rem;
}
.st-key-ee_home .ee-hero .ee-brand-cn {
    color: #80563E;
    font-size: clamp(1.1rem, 2cqi, 1.35rem);
    font-weight: 600;
    line-height: 1.6;
    margin: 0 0 1rem;
}
.st-key-ee_home .ee-hero .ee-tagline {
    color: var(--ee-muted);
    font-size: 1rem;
    line-height: 1.8;
    margin: 0;
}
.st-key-ee_home .st-key-ee_routes [data-testid="stHorizontalBlock"] {
    gap: 1.15rem;
    align-items: stretch;
}
.st-key-ee_home .st-key-ee_routes [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {
    height: 100%;
}
.st-key-ee_home [class*="st-key-ee_card_"] {
    flex: 1;
    height: 100%;
    min-height: 355px;
    padding: 1.55rem;
    gap: 1rem;
    border: 1px solid var(--ee-border);
    border-radius: 18px;
    background: #FFFFFF;
    box-shadow: 0 3px 12px rgba(66, 48, 31, 0.025);
    transition: border-color 140ms ease, box-shadow 140ms ease, background-color 140ms ease;
}
.st-key-ee_home [class*="st-key-ee_card_"]::before {
    content: "";
    width: 28px;
    height: 3px;
    flex: 0 0 3px;
    background: #D99268;
    border-radius: 3px;
}
.st-key-ee_home [class*="st-key-ee_card_"]:hover,
.st-key-ee_home [class*="st-key-ee_card_"]:focus-within {
    border-color: #CE8A60;
    background: #FFFCF9;
    box-shadow: 0 5px 18px rgba(112, 68, 35, 0.06);
}
.st-key-ee_home [class*="st-key-ee_card_"] h3 {
    min-height: 4.5em;
    margin: 0;
    padding: 0;
    color: var(--ee-ink);
    font-size: 1.3rem;
    font-weight: 650;
    line-height: 1.5;
    overflow-wrap: anywhere;
}
.st-key-ee_home [class*="st-key-ee_card_"] [data-testid="stMarkdownContainer"] p {
    color: var(--ee-muted);
    font-size: 0.94rem;
    line-height: 1.8;
    margin: 0;
}
.st-key-ee_home [class*="st-key-ee_card_"] > div:last-child {
    margin-top: auto;
    padding-top: 0.5rem;
}
.st-key-ee_home [data-testid="stPageLink-NavLink"] {
    width: fit-content;
    max-width: 100%;
    min-height: 2.4rem;
    border-radius: 8px;
    padding: 0.35rem 0;
    text-decoration: none;
}
.st-key-ee_home [class*="st-key-ee_card_"] [data-testid="stPageLink-NavLink"] p,
.st-key-ee_home .st-key-ee_history [data-testid="stPageLink-NavLink"] p {
    color: var(--ee-orange);
    font-size: 0.95rem;
    font-weight: 600;
}
.st-key-ee_home [class*="st-key-ee_card_"] [data-testid="stPageLink-NavLink"]::after,
.st-key-ee_home .st-key-ee_history [data-testid="stPageLink-NavLink"]::after {
    content: "→";
    color: var(--ee-orange);
    margin-left: 0.55rem;
    font-size: 1.1rem;
}
.st-key-ee_home [data-testid="stPageLink-NavLink"]:focus-visible,
.st-key-ee_home button:focus-visible {
    outline: 2px solid var(--ee-orange);
    outline-offset: 4px;
}
.st-key-ee_home .st-key-ee_history,
.st-key-ee_home .st-key-ee_services {
    border: 1px solid var(--ee-border);
    border-radius: 18px;
    padding: 1.45rem 1.6rem;
    background: #FDFCFB;
}
.st-key-ee_home .st-key-ee_history:hover {
    border-color: #D9B79F;
}
.st-key-ee_home .st-key-ee_history h4,
.st-key-ee_home .st-key-ee_services h4 {
    padding: 0;
    margin: 0 0 0.25rem;
    color: var(--ee-ink);
    font-size: 1.05rem;
    font-weight: 600;
    line-height: 1.5;
}
.st-key-ee_home .st-key-ee_history p,
.st-key-ee_home .st-key-ee_services p {
    font-size: 0.92rem;
    line-height: 1.8;
    color: var(--ee-muted);
}
.st-key-ee_home .st-key-ee_services {
    background: var(--ee-orange-soft);
    border-color: #EFE0D3;
}
.st-key-ee_home .st-key-ee_service_actions [data-testid="stCaptionContainer"] {
    width: fit-content;
    padding: 0.35rem 0.7rem;
    border: 1px solid #EED8C8;
    border-radius: 10px;
    background: #FFFFFF;
}
.st-key-ee_home .st-key-ee_service_actions [data-testid="stCaptionContainer"] p {
    font-size: 0.8rem;
    line-height: 1.7;
    color: #785139;
    margin: 0;
}
.st-key-ee_home .st-key-ee_service_actions button {
    background: #FFFFFF;
    border: 1px solid #C77B50;
    border-radius: 9px;
    padding: 0.5rem 0.9rem;
    min-height: 2.65rem;
}
.st-key-ee_home .st-key-ee_service_actions button p {
    color: var(--ee-orange);
    font-weight: 600;
}
.st-key-ee_home .st-key-ee_service_actions button:hover {
    background: #FFF0E4;
    border-color: var(--ee-orange);
}
.st-key-ee_home .st-key-ee_footer [data-testid="stPageLink-NavLink"] p {
    color: var(--ee-muted);
    font-size: 0.85rem;
}
@container ee-home (max-width: 820px) {
    .st-key-ee_home .st-key-ee_routes [data-testid="stHorizontalBlock"],
    .st-key-ee_home .st-key-ee_services [data-testid="stHorizontalBlock"] {
        flex-direction: column;
    }
    .st-key-ee_home .st-key-ee_routes [data-testid="stColumn"],
    .st-key-ee_home .st-key-ee_services [data-testid="stColumn"] {
        width: 100%;
        flex: 1 1 100%;
        min-width: 0;
    }
    .st-key-ee_home .st-key-ee_services [data-testid="stHorizontalBlock"] {
        gap: 1rem;
    }
    .st-key-ee_home [class*="st-key-ee_card_"] {
        min-height: 0;
        padding: 1.35rem;
        gap: 0.85rem;
    }
    .st-key-ee_home [class*="st-key-ee_card_"] h3 {
        min-height: 0;
    }
    .st-key-ee_home .ee-hero { padding: 0.5rem 0 1.3rem; }
}
@media (prefers-reduced-motion: reduce) {
    .st-key-ee_home [class*="st-key-ee_card_"] { transition: none; }
}
</style>
""", unsafe_allow_html=True)

ROUTES = [
    ("我想解决一个具体的英语学习问题", "Solve a Need", "02_solve_need.py",
     "告诉我孩子现在遇到了什么困难，我们一起看看可能卡在哪里，以及接下来可以怎么做。"),
    ("我想看看英语教育市场现在需要什么", "Explore the Market", "03_explore_market.py",
     "看看家长、教师和教育产品最近都在关注什么，还有哪些问题没有被很好解决。"),
    ("我想把已有需求做成一个 AI 英语教学工具", "Build a Solution", "06_build_solution.py",
     "从一个学习问题或市场机会出发，快速想清楚工具应该解决什么、怎么做，以及第一版 Demo 怎么验证。"),
]

with st.container(key="ee_home"):
    st.markdown(
        '<div class="ee-hero">'
        '<h1>English Education Explorer</h1>'
        '<p class="ee-brand-cn">英探探：英语学习与教育探索器</p>'
        '<p class="ee-tagline">从具体学习问题，到市场需求，再到可以落地的 AI 英语教学工具。</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.container(key="ee_routes"):
        for index, (column, (title, label, page, description)) in enumerate(zip(st.columns(3), ROUTES)):
            with column:
                with st.container(border=True, key=f"ee_card_{index}"):
                    st.subheader(title)
                    st.write(description)
                    st.page_link(page, label=label)

    with st.container(border=True, key="ee_history"):
        st.markdown("#### 查看我的历史方案记录")
        st.write("回到之前保存的需求分析、市场观察和工具方案，继续查看或修改。")
        st.page_link("04_history.py", label="History")

    with st.container(border=True, key="ee_services"):
        service_copy, service_actions = st.columns([3, 2], gap="large", vertical_alignment="center")
        with service_copy:
            st.markdown("#### 启用 AI 与联网能力")
            st.write("当前可以直接体验本地 Demo。如果希望使用真实 AI 分析或联网搜索，可以在这里配置自己的 API，不需要打开终端。")
        with service_actions:
            with st.container(key="ee_service_actions"):
                status = get_status()
                ai_label = status["ai_label"] if status["ai_available"] else "尚未启用（可在设置中选择 Demo）"
                search_label = "Live Search Ready（点击后联网）" if status["search_available"] else "Local Only（仅使用本地资料）"
                st.caption(f"AI：{ai_label} · 联网搜索：{search_label}")
                if st.button("配置 AI 与联网服务", key="home_configure_services"):
                    st.session_state["md_open_services"] = True
                    st.switch_page("05_manage_data.py")

    with st.container(key="ee_footer"):
        st.page_link("05_manage_data.py", label="Manage Data", icon="⚙")
