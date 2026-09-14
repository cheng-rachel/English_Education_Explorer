"""M3 HTTP providers and safe configuration (local settings before legacy env).

complete_json keeps the original API. Orchestration passes retries=0 so its one
structured-output retry owns the entire request budget; there are no hidden
HTTP retries. Custom uses the same small OpenAI-compatible request protocol.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlsplit

DEFAULT_TIMEOUT = 90
MAX_TOKENS = 4096
PROVIDERS = ("openai_compatible", "anthropic", "custom")
DEFAULTS = {
    "openai_compatible": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "anthropic": ("https://api.anthropic.com", ""),
    "custom": ("", ""),
}
_KEY_CANDIDATES = [
    ("ENGEDUSCOPE_LLM_API_KEY", None, None, None),
    ("OPENAI_API_KEY", "openai_compatible", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("DEEPSEEK_API_KEY", "openai_compatible", "https://api.deepseek.com/v1", "deepseek-chat"),
    ("DASHSCOPE_API_KEY", "openai_compatible", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("MOONSHOT_API_KEY", "openai_compatible", "https://api.moonshot.cn/v1", "moonshot-v1-32k"),
    ("ANTHROPIC_API_KEY", "anthropic", "https://api.anthropic.com", "claude-3-5-haiku-latest"),
]


class LLMError(Exception):
    """All messages supplied by the provider are sanitized and safe for display."""

    user_message = "AI 分析暂时不可用，请稍后重试。"

    def __init__(self, message: str = "", user_message: Optional[str] = None):
        super().__init__(message or user_message or self.user_message)
        if user_message:
            self.user_message = user_message


class LLMNotConfigured(LLMError):
    user_message = "尚未配置 Live API，请到 Manage Data → AI Settings 填写并保存配置；也可选择 Demo / Mock 演示完整流程。"


class LLMConfigurationError(LLMError):
    user_message = "AI 配置不完整或格式有误，请到 Manage Data → AI Settings 检查并重新保存。"


class LLMTimeout(LLMError):
    user_message = "AI 请求超时，请稍后再试，或在 AI Settings 调整超时时间。"


class LLMRequestError(LLMError):
    user_message = "无法连接 AI 服务，请检查网络、Base URL、API Key 与模型名称。"


class LLMBadResponse(LLMError):
    user_message = "AI 服务未返回可用的 JSON 结果，请重新尝试；如持续出现，请检查模型或接口地址。"


class LLMSchemaError(LLMError):
    user_message = "模型返回的结果不完整或格式不符合要求。请重新点击分析；如持续出现，可尝试更换模型。"


@dataclass(repr=False)
class LLMConfig:
    provider: str
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    model: str = ""
    timeout: int = DEFAULT_TIMEOUT
    key_source: str = ""
    mode: str = "live"
    configuration_error: str = ""

    @property
    def configured(self) -> bool:
        if self.configuration_error:
            return False
        return self.is_mock or (self.provider in PROVIDERS and bool(self.api_key and self.base_url and self.model))

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock" or self.mode == "demo"

    def __repr__(self) -> str:
        return f"LLMConfig(configured={self.configured}, is_mock={self.is_mock})"

    def describe(self) -> str:
        if self.configuration_error:
            return "配置需要检查"
        if self.is_mock:
            return "Demo / Mock（演示内容，未调用 Live API）"
        if not self.configured:
            return "未配置"
        return f"{self.model} @ {urlsplit(self.base_url).hostname}"


def _clean_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise LLMConfigurationError(user_message=f"{label} 需要填写文本。")
    value = value.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise LLMConfigurationError(user_message=f"{label} 含有无效字符，请重新填写。")
    return value


def _timeout(value: object) -> int:
    try:
        if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
            raise ValueError
        timeout = int(value)
        if not 1 <= timeout <= 300:
            raise ValueError
        return timeout
    except (ValueError, TypeError, OverflowError):
        raise LLMConfigurationError(user_message="Timeout 请填写 1–300 之间的整数秒数。") from None


def validate_config(cfg: LLMConfig) -> None:
    if cfg.configuration_error:
        raise LLMConfigurationError(user_message=cfg.configuration_error)
    if cfg.provider not in (*PROVIDERS, "mock", "none") or cfg.mode not in ("live", "demo"):
        raise LLMConfigurationError(user_message="请选择有效的 Provider 与运行模式。")
    _timeout(cfg.timeout)
    for value, label in ((cfg.api_key, "API Key"), (cfg.base_url, "Base URL"), (cfg.model, "Model")):
        _clean_text(value, label)
    if cfg.base_url:
        try:
            parsed = urlsplit(cfg.base_url)
            valid = (parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username
                     and not parsed.password and not parsed.query and not parsed.fragment
                     and not any(char.isspace() for char in cfg.base_url))
            _ = parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise LLMConfigurationError(user_message="Base URL 需为有效的 http:// 或 https:// 地址，且不能包含账号、密码或查询参数。")
    if cfg.is_mock:
        return
    if not cfg.api_key:
        raise LLMNotConfigured()
    if cfg.provider not in PROVIDERS or not cfg.base_url or not cfg.model:
        raise LLMConfigurationError(user_message="Live API 需要有效的 Provider、Base URL 和 Model。")


def _from_local(data: dict) -> LLMConfig:
    cfg = LLMConfig(
        provider=_clean_text(data.get("provider", "openai_compatible"), "Provider"),
        api_key=_clean_text(data.get("api_key", ""), "API Key"),
        base_url=_clean_text(data.get("base_url", ""), "Base URL").rstrip("/"),
        model=_clean_text(data.get("model", ""), "Model"),
        timeout=_timeout(data.get("timeout", DEFAULT_TIMEOUT)),
        mode=_clean_text(data.get("mode", "live"), "运行模式"),
        key_source="local" if data.get("api_key") else "",
    )
    validate_config(cfg)
    return cfg


def _from_environment() -> LLMConfig:
    provider = (os.environ.get("ENGEDUSCOPE_LLM_PROVIDER") or "auto").strip().lower()
    timeout = _timeout(os.environ.get("ENGEDUSCOPE_LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    if provider == "mock":
        return LLMConfig(provider="mock", mode="demo", timeout=timeout)
    if provider not in ("auto", *PROVIDERS):
        raise LLMConfigurationError(user_message="环境变量中的 Provider 无效，请在 AI Settings 保存配置。")
    candidates = _KEY_CANDIDATES
    # An explicit provider must not accidentally receive another provider's key.
    if provider == "anthropic":
        candidates = [item for item in candidates if item[0] in ("ENGEDUSCOPE_LLM_API_KEY", "ANTHROPIC_API_KEY")]
    elif provider in ("openai_compatible", "custom"):
        candidates = [item for item in candidates if item[1] != "anthropic"]
    for name, inferred, base, model in candidates:
        key = (os.environ.get(name) or "").strip()
        if key:
            selected = (inferred or "openai_compatible") if provider == "auto" else provider
            default_base, default_model = DEFAULTS[selected]
            cfg = LLMConfig(
                provider=selected, api_key=key,
                base_url=(os.environ.get("ENGEDUSCOPE_LLM_BASE_URL") or base or default_base).strip().rstrip("/"),
                model=(os.environ.get("ENGEDUSCOPE_LLM_MODEL") or model or default_model).strip(),
                timeout=timeout, key_source=name,
            )
            validate_config(cfg)
            return cfg
    # First launch works without credentials and is explicitly identified as Demo.
    return LLMConfig(provider="none", mode="demo", timeout=timeout)


def load_config(path=None) -> LLMConfig:
    """Local settings win, including a cleared Demo record; env remains compatible."""
    from llm.settings import SettingsError, read_local_config

    try:
        local = read_local_config(path)
        return _from_local(local) if local is not None else _from_environment()
    except (SettingsError, LLMError) as exc:
        message = exc.user_message if isinstance(exc, LLMError) else str(exc)
        return LLMConfig(provider="none", configuration_error=message)


def is_configured() -> bool:
    return load_config().configured


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def extract_json(text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise LLMBadResponse()
    candidates = [match.group(1) for match in _FENCE_RE.finditer(text)] + [text]
    for candidate in candidates:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            data = json.loads(candidate[start:end + 1])
        except (ValueError, RecursionError):
            continue
        if isinstance(data, dict):
            return data
    raise LLMBadResponse()


def _response_json(response) -> dict:
    if response.status_code >= 300:
        if response.status_code in (401, 403):
            raise LLMRequestError(user_message="AI 服务拒绝了身份验证，请检查 API Key 及其访问权限。")
        if response.status_code == 429:
            raise LLMRequestError(user_message="AI 服务暂时限流或额度不足，请检查账户额度后稍后重试。")
        raise LLMRequestError(user_message=f"AI 服务返回 HTTP {response.status_code}，请检查接口地址与模型设置后重试。")
    try:
        data = response.json()
    except (ValueError, RecursionError):
        raise LLMBadResponse() from None
    if not isinstance(data, dict):
        raise LLMBadResponse()
    return data


def _call_openai_compatible(cfg: LLMConfig, system: str, user: str, temperature: float, json_mode: bool = False) -> str:
    import requests

    payload = {
        "model": cfg.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature, "max_tokens": MAX_TOKENS,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    base = cfg.base_url.rstrip("/")
    endpoint = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    response = requests.post(
        endpoint, headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
        json=payload, timeout=(min(15, cfg.timeout), cfg.timeout), allow_redirects=False,
    )
    data = _response_json(response)
    try:
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError
        return content
    except (KeyError, IndexError, TypeError):
        raise LLMBadResponse() from None


def _call_anthropic(cfg: LLMConfig, system: str, user: str, temperature: float) -> str:
    import requests

    base = cfg.base_url.rstrip("/")
    endpoint = base if base.endswith("/messages") else f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"
    response = requests.post(
        endpoint,
        headers={"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        json={"model": cfg.model, "max_tokens": MAX_TOKENS, "temperature": temperature,
              "system": system, "messages": [{"role": "user", "content": user}]},
        timeout=(min(15, cfg.timeout), cfg.timeout), allow_redirects=False,
    )
    data = _response_json(response)
    try:
        blocks = data["content"]
        if not isinstance(blocks, list) or any(not isinstance(block, dict) for block in blocks):
            raise TypeError
        return "".join(block["text"] for block in blocks if block.get("type") == "text")
    except (KeyError, TypeError):
        raise LLMBadResponse() from None


def _call_once(cfg: LLMConfig, system: str, user: str, temperature: float) -> str:
    import requests

    try:
        if cfg.provider == "anthropic":
            return _call_anthropic(cfg, system, user, temperature)
        # JSON is requested by prompts; omitting response_format also supports
        # compatible services that do not implement that optional OpenAI field.
        return _call_openai_compatible(cfg, system, user, temperature)
    except requests.exceptions.Timeout:
        raise LLMTimeout() from None
    except requests.exceptions.RequestException:
        raise LLMRequestError() from None
    except (ValueError, TypeError, UnicodeError):
        raise LLMBadResponse() from None


def complete_json(system: str, user: str, temperature: float = 0.3, retries: int = 1, *, cfg: LLMConfig | None = None) -> dict:
    from output_safety import sanitize_data
    cfg = cfg if cfg is not None else load_config()
    validate_config(cfg)
    if cfg.is_mock:
        from llm.mock import mock_complete_json
        return sanitize_data(mock_complete_json(system, user))
    last_error: LLMError | None = None
    for attempt in range(max(0, min(1, retries)) + 1):
        try:
            return sanitize_data(extract_json(_call_once(cfg, system, user, temperature)))
        except (LLMTimeout, LLMRequestError, LLMBadResponse) as exc:
            last_error = exc
            if attempt < retries and isinstance(exc, LLMBadResponse):
                user += "\n\n上一次输出无法解析。请只输出一个合法 JSON 对象，不要说明文字或 Markdown 围栏。"
    raise last_error  # type: ignore[misc]


def test_connection(cfg: LLMConfig) -> None:
    """One harmless real generation proves auth, model access and JSON responses."""
    validate_config(cfg)
    if cfg.is_mock:
        raise LLMNotConfigured(user_message="Demo / Mock 无需连接 API。请选择 Live API 后测试连接。")
    result = complete_json('Reply only with the JSON object {"ok": true}.', "Connection test.", retries=0, cfg=cfg)
    if result.get("ok") is not True:
        raise LLMBadResponse(user_message="已收到 AI 服务回复，但未通过 JSON 格式测试，请检查模型设置后重试。")
