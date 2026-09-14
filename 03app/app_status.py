"""M6 read-only configuration labels; never connect, fetch, or expose credentials."""

from llm import provider as llm_provider
from web_search import settings as search_settings
from output_safety import sanitize_data, sanitize_text

AI_UNAVAILABLE = "还没有启用 AI 服务，可以先体验本地 Demo，或在 Manage Data 中配置 AI 与联网服务。"
SEARCH_UNAVAILABLE = "当前仅使用本地知识库。"
KNOWLEDGE_UNAVAILABLE = "当前没有可用知识库资料，请前往 Manage Data 更新知识库。"

_PROVIDER_LABELS = {"openai_compatible": "OpenAI-compatible", "anthropic": "Anthropic", "custom": "Custom"}


def source_type_label(value):
    """Display legacy discussion aliases uniformly without rewriting stored tags."""
    if not isinstance(value, str):
        return sanitize_text(value or "")
    alias = value.strip().lower().replace("_", " ")
    if alias in {"public discussion", "public discussions", "user discussion", "user discussions",
                 "用户帖子", "用户讨论", "公开讨论", "公开用户讨论"}:
        return "公开用户讨论"
    return sanitize_text(value)


def ai_status(cfg=None):
    """Return only safe scalar labels for the current configuration, not a result."""
    try:
        cfg = cfg if cfg is not None else llm_provider.load_config()
        if getattr(cfg, "configuration_error", ""):
            return {"label": "不可用", "available": False, "mode": "unavailable"}
        if getattr(cfg, "is_mock", False):
            return {"label": "Demo", "available": True, "mode": "demo"}
        if getattr(cfg, "configured", False):
            name = _PROVIDER_LABELS.get(getattr(cfg, "provider", ""), "AI Provider")
            return {"label": f"{name} · Live", "available": True, "mode": "live"}
    except Exception:  # noqa: BLE001  Status must remain available even with a broken local config.
        pass
    return {"label": "不可用", "available": False, "mode": "unavailable"}


def search_status(cfg=None):
    try:
        cfg = cfg if cfg is not None else search_settings.load_config()
        ready = bool(getattr(cfg, "configured", False) and not getattr(cfg, "configuration_error", ""))
    except Exception:  # noqa: BLE001
        ready = False
    return {"label": "Live Search Ready" if ready else "Local Only", "available": ready}


def get_status():
    ai, search = ai_status(), search_status()
    return {"ai_label": ai["label"], "ai_available": ai["available"], "ai_mode": ai["mode"],
            "search_label": search["label"], "search_available": search["available"]}


def ai_error_message(exc):
    if isinstance(exc, (llm_provider.LLMNotConfigured, llm_provider.LLMConfigurationError)):
        return AI_UNAVAILABLE
    if isinstance(exc, llm_provider.LLMError):
        return sanitize_text(exc.user_message)
    return "AI 暂时不可用，请稍后重试。"


def render_status(compact=True):
    """Render current configuration state without testing any external service."""
    import streamlit as st

    status = sanitize_data(get_status())
    ai_label = status["ai_label"] if status["ai_available"] else "尚未启用"
    search_label = "Live Search Ready" if status["search_available"] else "Local Only（仅本地资料）"
    if compact:
        st.caption(f"AI · {ai_label}")
        st.caption(f"联网搜索 · {search_label}")
        st.caption("当前配置状态；联网仅由手动操作触发。")
    else:
        first, second = st.columns(2)
        first.metric("当前 AI 模式", ai_label)
        second.metric("当前搜索模式", search_label)
    if not status["ai_available"]:
        st.info(AI_UNAVAILABLE)
    return status
