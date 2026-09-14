"""Manage Data AI Settings: keep saved credentials out of widget values."""

from __future__ import annotations

import hashlib
import json

import streamlit as st

from app_status import AI_UNAVAILABLE, ai_status
from llm.provider import DEFAULTS, LLMConfig, LLMError, load_config, test_connection, validate_config
from llm.settings import SettingsError, clear_config, save_config

PROVIDER_LABELS = {"OpenAI-compatible": "openai_compatible", "Anthropic": "anthropic", "Custom": "custom"}
MODES = ["Demo / Mock", "Live API"]
WIDGET_KEYS = ("ai_provider", "ai_mode", "ai_base_url", "ai_model", "ai_timeout", "ai_key_input")


def _fingerprint(cfg: LLMConfig) -> str:
    # Only a digest is retained in connection status; never the submitted key.
    payload = [cfg.provider, cfg.base_url, cfg.model, cfg.api_key, cfg.timeout, cfg.mode]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def _set_fields(cfg: LLMConfig) -> None:
    provider = cfg.provider if cfg.provider in PROVIDER_LABELS.values() else "openai_compatible"
    default_base, default_model = DEFAULTS[provider]
    st.session_state.update({
        "ai_provider": next(label for label, value in PROVIDER_LABELS.items() if value == provider),
        "ai_mode": "Demo / Mock" if cfg.is_mock else "Live API",
        "ai_base_url": cfg.base_url or default_base,
        "ai_model": cfg.model or default_model,
        "ai_timeout": cfg.timeout,
        "ai_key_input": "",
        "_ai_initialized": True,
    })


def _provider_changed() -> None:
    provider = PROVIDER_LABELS[st.session_state["ai_provider"]]
    st.session_state["ai_base_url"], st.session_state["ai_model"] = DEFAULTS[provider]
    st.session_state["ai_key_input"] = ""
    st.session_state.pop("_ai_connection", None)
    st.session_state.pop("_ai_pending_key", None)


def _candidate() -> LLMConfig:
    active = load_config()
    provider = PROVIDER_LABELS[st.session_state["ai_provider"]]
    base = st.session_state["ai_base_url"].strip().rstrip("/")
    key = st.session_state.get("ai_key_input", "").strip()
    pending = st.session_state.get("_ai_pending_key", {})
    if not key and pending.get("provider") == provider and pending.get("base_url") == base:
        key = pending.get("api_key", "")
    # Editing a model may retain its key; changing provider/URL requires an
    # explicit fresh key, so an old key is never sent to a newly typed service.
    if not key and provider == active.provider and base == active.base_url:
        key = active.api_key
    return LLMConfig(
        provider=provider, base_url=base,
        model=st.session_state["ai_model"].strip(), api_key=key,
        timeout=int(st.session_state["ai_timeout"]),
        mode="demo" if st.session_state["ai_mode"] == "Demo / Mock" else "live",
    )


def _settings_action(action: str) -> None:
    try:
        if action == "clear":
            clear_config()
            _set_fields(load_config())
            st.session_state.pop("_ai_connection", None)
            st.session_state.pop("_ai_pending_key", None)
            st.session_state["_ai_flash"] = ("success", "已清除保存的 API Key 与配置，并切换到 Demo。")
            return
        candidate = _candidate()
        validate_config(candidate)
        if action == "test":
            # Keep a just-entered key only in server memory so Test → Save works
            # after clearing the password widget. Never send it back as a value.
            st.session_state["_ai_pending_key"] = {
                "provider": candidate.provider, "base_url": candidate.base_url, "api_key": candidate.api_key,
            }
            with st.spinner("正在测试 API 连接…"):
                test_connection(candidate)
            st.session_state["_ai_connection"] = {"fingerprint": _fingerprint(candidate), "ok": True}
            st.session_state["_ai_flash"] = ("success", "连接成功。测试已确认 API Key、Model 与 JSON 回复可用；点击「保存配置」后用于分析。")
        else:
            save_config(candidate)
            st.session_state.pop("_ai_pending_key", None)
            st.session_state["_ai_flash"] = ("success", "配置已保存，下次分析立即生效，重启后仍会读取。")
    except (LLMError, SettingsError) as exc:
        if action == "test":
            # Safe error details are shown once; no request or response is retained.
            st.session_state["_ai_connection"] = {"fingerprint": _fingerprint(candidate) if "candidate" in locals() else "", "ok": False}
        st.session_state["_ai_flash"] = ("error", exc.user_message if isinstance(exc, LLMError) else str(exc))
    finally:
        # The saved key is never populated into the password widget, and a key
        # manually entered for this action is cleared before the next render.
        st.session_state["ai_key_input"] = ""


def render_ai_settings() -> None:
    cfg = load_config()
    if not st.session_state.get("_ai_initialized") or any(key not in st.session_state for key in WIDGET_KEYS):
        _set_fields(cfg)
        st.session_state.pop("_ai_pending_key", None)
    st.caption("Demo 可直接演示完整流程；Live API 使用您配置的服务分析需求与少量参考资料。修改后点击「保存配置」，下一次分析即生效。")
    if cfg.configuration_error:
        st.warning(AI_UNAVAILABLE)
    provider_label = next((label for label, value in PROVIDER_LABELS.items() if value == cfg.provider), "未配置")
    connection = st.session_state.get("_ai_connection", {})
    try:
        draft_matches_test = bool(connection) and connection.get("fingerprint") == _fingerprint(_candidate())
    except (LLMError, KeyError, ValueError):
        draft_matches_test = False
    if cfg.configuration_error:
        status = "连接失败 · 请检查配置"
    elif cfg.is_mock:
        status = "Demo · 无需连接"
    elif not cfg.api_key:
        status = "未配置"
    elif connection.get("fingerprint") == _fingerprint(cfg):
        status = "已连接" if connection.get("ok") else "连接失败"
    else:
        status = "已配置 · 未测试"
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("当前 Provider", provider_label)
        c2.metric("当前 Model", cfg.model or "未配置")
        c3.metric("API 状态", status)
        st.caption("当前模式：" + ai_status(cfg)["label"])
        st.caption("API Key 状态：" + ("已配置" if cfg.api_key else "未配置"))
        if cfg.api_key:
            st.caption("API Key 已配置。页面不会回显已保存的 Key；保留相同 Provider 与 Base URL 时，留空表示继续使用。")
    if draft_matches_test and connection.get("fingerprint") != _fingerprint(cfg):
        if connection.get("ok"):
            st.success("当前填写的 API：已连接 · 尚未保存，请点击「保存配置」后用于分析。")
        else:
            st.error("当前填写的 API：连接失败。请检查设置后重新测试。")
    flash = st.session_state.pop("_ai_flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    st.selectbox("Provider", list(PROVIDER_LABELS), key="ai_provider", on_change=_provider_changed)
    st.radio("运行模式", MODES, key="ai_mode", horizontal=True,
             format_func=lambda value: "Demo" if value == "Demo / Mock" else "Live")
    st.text_input("Base URL", key="ai_base_url", placeholder="https://your-api.example/v1")
    st.text_input("Model", key="ai_model", placeholder="填写服务提供方的模型名称")
    st.text_input("API Key", type="password", key="ai_key_input", placeholder="输入新的 Key，或留空保留相同服务的已有 Key")
    if st.session_state.get("_ai_pending_key"):
        st.caption("本次测试使用的 Key 已暂存，可直接保存配置；刷新或关闭会话前请保存。")
    st.number_input("Timeout（秒）", min_value=1, max_value=300, step=5, key="ai_timeout", help="单次请求等待回复的最长时间。")
    st.caption("Custom 使用 OpenAI-compatible 接口，可自定义 Base URL、Model 与 API Key。切换 Provider 或 Base URL 后请重新填写 Key。")
    c1, c2, c3 = st.columns(3)
    c1.button("测试连接", key="ai_test", on_click=_settings_action, args=("test",), use_container_width=True)
    c2.button("保存配置", key="ai_save", type="primary", on_click=_settings_action, args=("save",), use_container_width=True)
    c3.button("清除配置", key="ai_clear", on_click=_settings_action, args=("clear",), use_container_width=True)
    st.caption("配置仅保存在本机项目的私有文件中。清除配置会删除保存的 Key 并启用 Demo；不会自动恢复启动环境中的 Key。")
