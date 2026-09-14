"""Small local form for a single active search service."""

import hashlib

import streamlit as st

from app_status import SEARCH_UNAVAILABLE, search_status
from web_search.provider import test_connection
from web_search.settings import PROVIDERS, SearchConfig, SearchError, clear_config, load_config, save_config


def _fingerprint(cfg):
    return hashlib.sha256(f"{cfg.provider}:{cfg.base_url}:{cfg.provider_name}:{cfg.timeout}:{cfg.api_key}".encode()).hexdigest()


def _selected_provider():
    selected = st.session_state.get("search_provider", "Tavily")
    return next((key for key, label in PROVIDERS.items() if label == selected), "tavily")


def _candidate():
    saved = load_config()
    provider = _selected_provider()
    # A provider switch never borrows the old provider's credentials.
    saved_key = saved.api_key if saved.provider == provider else ""
    key = (st.session_state.get("search_key_input", "") or
           st.session_state.get("_search_pending_key", "") or saved_key).strip()
    return SearchConfig(api_key=key, provider=provider,
                        timeout=int(st.session_state.get("search_timeout", 12)),
                        base_url=st.session_state.get("search_base_url", "").strip() if provider == "custom" else "",
                        provider_name=st.session_state.get("search_provider_name", "").strip() if provider == "custom" else "")


def _switch_provider():
    saved = load_config()
    same = saved.provider == _selected_provider()
    st.session_state["search_key_input"] = ""
    st.session_state["search_timeout"] = saved.timeout if same else 12
    st.session_state["search_base_url"] = saved.base_url if same else ""
    st.session_state["search_provider_name"] = saved.provider_name if same else ""
    for key in ("_search_pending_key", "_search_connection", "_search_flash"):
        st.session_state.pop(key, None)


def _action(action):
    cfg = None
    try:
        if action == "clear":
            clear_config()
            st.session_state["search_provider"] = "Tavily"
            _switch_provider()
            st.session_state["_search_flash"] = ("success", "已清除联网搜索配置与保存的 API Key。")
            return
        cfg = _candidate()
        if action == "test":
            st.session_state["_search_pending_key"] = cfg.api_key
            with st.spinner("正在测试搜索连接…"):
                test_connection(cfg)
            st.session_state["_search_connection"] = {"fingerprint": _fingerprint(cfg), "ok": True}
            st.session_state["_search_flash"] = ("success", "搜索连接成功。点击「保存配置」后，可在 Explore the Market 手动更新联网信息。")
        else:
            connection = st.session_state.get("_search_connection", {})
            failed_test = connection.get("fingerprint") == _fingerprint(cfg) and not connection.get("ok")
            if failed_test:
                cfg.enabled = False
            save_config(cfg)
            st.session_state.pop("_search_pending_key", None)
            message = "搜索配置已保存，重启后仍会读取。"
            if cfg.provider == "custom":
                message = "Custom 配置已保存；接口暂未启用，当前仅使用本地知识库。"
            elif failed_test:
                message = "配置已保存；连接测试未通过，当前仅使用本地知识库。测试成功后可重新保存并启用。"
            st.session_state["_search_flash"] = ("success", message)
    except SearchError as exc:
        if action == "test" and cfg is not None:
            st.session_state["_search_connection"] = {"fingerprint": _fingerprint(cfg), "ok": False}
        st.session_state["_search_flash"] = ("error", exc.user_message)
    finally:
        st.session_state["search_key_input"] = ""


def render_search_settings():
    cfg = load_config()
    if "search_provider" not in st.session_state:
        st.session_state["search_provider"] = PROVIDERS.get(cfg.provider, "Tavily")
    if "search_key_input" not in st.session_state or "search_timeout" not in st.session_state:
        st.session_state["search_key_input"] = ""
        st.session_state["search_timeout"] = cfg.timeout
        st.session_state["search_base_url"] = cfg.base_url
        st.session_state["search_provider_name"] = cfg.provider_name
        st.session_state.pop("_search_pending_key", None)
    connection = st.session_state.get("_search_connection", {})
    if cfg.configuration_error:
        status = "连接失败 · 请检查配置"
    elif cfg.provider == "custom":
        status = "配置占位 · 尚未启用"
    elif connection.get("fingerprint") == _fingerprint(cfg):
        status = "已连接" if connection.get("ok") else "连接失败"
    elif not cfg.configured:
        status = "未启用" if cfg.api_key else "未配置"
    else:
        status = "已配置 · 未测试"
    st.caption("配置联网搜索以发现新的公开资料；点击「更新联网信息」时才会搜索。测试连接会执行一次轻量搜索。")
    with st.container(border=True):
        left, right = st.columns(2)
        left.metric("当前 Provider", PROVIDERS.get(cfg.provider, "未配置"))
        right.metric("API 状态", status)
        failed_saved_test = connection.get("fingerprint") == _fingerprint(cfg) and not connection.get("ok")
        st.caption("当前模式：" + ("Local Only" if failed_saved_test else search_status(cfg)["label"]))
        st.caption("API Key 状态：" + ("已配置" if cfg.api_key else "未配置"))
    if cfg.configuration_error:
        st.warning("搜索配置暂时不可用，请重新保存或清除配置。" + SEARCH_UNAVAILABLE)
    elif not cfg.configured:
        st.info(SEARCH_UNAVAILABLE)
    same_provider = cfg.provider == _selected_provider()
    if cfg.api_key and same_provider:
        st.caption("API Key 已配置。留空可保留当前 Key，页面不会回显已保存的 Key。")
    elif not same_provider:
        st.caption("更换搜索服务后，请填写该服务的 API Key；保存后才会切换当前服务。")
    if connection.get("fingerprint") == _fingerprint(_candidate()) and connection.get("fingerprint") != _fingerprint(cfg):
        if connection.get("ok"):
            st.success("当前填写的搜索 API：已连接 · 尚未保存。")
        else:
            st.error("当前填写的搜索 API：连接失败。")
    flash = st.session_state.pop("_search_flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    st.selectbox("Search Provider", list(PROVIDERS.values()), key="search_provider", on_change=_switch_provider)
    if _selected_provider() == "custom":
        st.text_input("Base URL", key="search_base_url", placeholder="https://search.example.com/search")
        st.text_input("Provider Name（可选）", key="search_provider_name")
        st.info("Custom 当前仅保留配置入口，尚未接入搜索协议；保存后继续使用本地资料。")
    st.text_input("API Key", type="password", key="search_key_input", placeholder="输入新的 API Key，或留空保留当前服务已有 Key")
    st.number_input("Timeout（秒）", min_value=5, max_value=300, step=1, key="search_timeout", help="单次请求等待回复的最长时间。")
    if st.session_state.get("_search_pending_key"):
        st.caption("本次测试的 Key 已暂存，可直接保存；不会填回密码输入框。")
    first, second, third = st.columns(3)
    first.button("测试连接", key="search_test", on_click=_action, args=("test",), use_container_width=True)
    second.button("保存配置", key="search_save", type="primary", on_click=_action, args=("save",), use_container_width=True)
    third.button("清除配置", key="search_clear", on_click=_action, args=("clear",), use_container_width=True)
    st.caption("一次只启用一个搜索服务。Key 保存在本机私有文件中；清除配置后不会自动恢复环境变量中的 Key。")
