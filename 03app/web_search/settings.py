"""Private local settings for one active search provider."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

CONFIG_PATH = Path(__file__).resolve().parents[2] / ".local" / "search_config.json"
FAILURE_LOG_PATH = CONFIG_PATH.parent / "search_failures.jsonl"
DEFAULT_TIMEOUT = 12
PROVIDERS = {"tavily": "Tavily", "serper": "Serper", "custom": "Custom"}


class SearchError(Exception):
    def __init__(self, user_message="联网搜索暂时不可用，请稍后重试。"):
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(repr=False)
class SearchConfig:
    api_key: str = field(default="", repr=False)
    provider: str = "tavily"
    enabled: bool = True
    timeout: int = DEFAULT_TIMEOUT
    configuration_error: str = ""
    base_url: str = ""
    provider_name: str = ""

    @property
    def configured(self):
        return bool(self.enabled and self.api_key and self.provider in ("tavily", "serper")
                    and not self.configuration_error)

    def __repr__(self):
        return f"SearchConfig(configured={self.configured})"


def validate_config(cfg):
    if cfg.configuration_error:
        raise SearchError(cfg.configuration_error)
    if cfg.provider not in PROVIDERS or not isinstance(cfg.enabled, bool):
        raise SearchError("搜索配置无效，请重新保存搜索服务设置。")
    if not isinstance(cfg.api_key, str) or any(ord(char) < 33 or ord(char) > 126 for char in cfg.api_key):
        raise SearchError("API Key 格式有误，请重新输入。")
    if not isinstance(cfg.timeout, int) or isinstance(cfg.timeout, bool) or not 5 <= cfg.timeout <= 300:
        raise SearchError("Timeout 请填写 5–300 之间的整数秒数。")
    if not isinstance(cfg.base_url, str) or not isinstance(cfg.provider_name, str):
        raise SearchError("自定义搜索配置格式有误，请重新填写。")
    if len(cfg.provider_name) > 80 or any(ord(char) < 32 for char in cfg.provider_name):
        raise SearchError("Provider Name 请填写不超过 80 个字符的名称。")
    if cfg.base_url:
        try:
            parsed = urlsplit(cfg.base_url)
        except ValueError:
            raise SearchError("Base URL 格式有误，请重新填写 HTTPS 地址。") from None
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise SearchError("Base URL 请填写不含密钥或查询参数的 HTTPS 地址。")
    if cfg.enabled and not cfg.api_key and cfg.provider != "custom":
        raise SearchError("尚未配置联网搜索，请到 Manage Data → Search Settings 保存 API Key。")


def load_config(path=None):
    target = Path(path) if path is not None else CONFIG_PATH
    try:
        if target.is_symlink():
            raise SearchError("搜索配置文件不可用，请重新保存配置。")
        if target.exists():
            with target.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError
            cfg = SearchConfig(api_key=data.get("api_key", ""), provider=data.get("provider", "tavily"),
                               enabled=data.get("enabled", True), timeout=data.get("timeout", DEFAULT_TIMEOUT),
                               base_url=data.get("base_url", ""), provider_name=data.get("provider_name", ""))
        else:
            key = (os.environ.get("ENGEDUSCOPE_SEARCH_API_KEY") or os.environ.get("TAVILY_API_KEY") or "").strip()
            cfg = SearchConfig(api_key=key, enabled=bool(key))
        validate_config(cfg)
        return cfg
    except SearchError as exc:
        return SearchConfig(enabled=False, configuration_error=exc.user_message)
    except (OSError, ValueError, UnicodeError):
        return SearchConfig(enabled=False, configuration_error="无法读取本地搜索配置，请重新保存或清除配置。")


def save_config(cfg, path=None):
    validate_config(cfg)
    target = Path(path) if path is not None else CONFIG_PATH
    temporary = None
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.parent.is_symlink() or target.is_symlink():
            raise OSError
        fd, temporary = tempfile.mkstemp(prefix=".search-config-", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump({"version": 1, "provider": cfg.provider, "api_key": cfg.api_key,
                       "enabled": cfg.enabled, "timeout": cfg.timeout, "base_url": cfg.base_url,
                       "provider_name": cfg.provider_name}, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        return target
    except OSError:
        raise SearchError("无法保存搜索配置，请检查项目 .local 目录是否可写。") from None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def clear_config(path=None):
    # An explicit disabled record prevents legacy environment keys reactivating.
    return save_config(SearchConfig(enabled=False), path)


def append_failures(failures, timestamp):
    if not failures:
        return True
    try:
        FAILURE_LOG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if FAILURE_LOG_PATH.parent.is_symlink() or FAILURE_LOG_PATH.is_symlink():
            return False
        flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(FAILURE_LOG_PATH, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            for failure in failures:
                json.dump({"recorded_at": timestamp, **failure}, handle, ensure_ascii=False)
                handle.write("\n")
        return True
    except OSError:
        return False
