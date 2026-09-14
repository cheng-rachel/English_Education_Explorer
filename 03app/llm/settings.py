"""Private local AI settings; no secrets are logged or included in errors."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.provider import LLMConfig

CONFIG_PATH = Path(__file__).resolve().parents[2] / ".local" / "llm_config.json"


class SettingsError(Exception):
    """A safe, user-facing local configuration error."""


def read_local_config(path: Path | None = None) -> dict | None:
    target = Path(path) if path is not None else CONFIG_PATH
    try:
        if not target.exists():
            return None
        # Never follow a symlink to a key file outside the local config location.
        if target.is_symlink():
            raise SettingsError("AI 配置文件不可用，请在 AI Settings 重新保存配置。")
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except SettingsError:
        raise
    except (OSError, ValueError, UnicodeError):
        raise SettingsError("无法读取本地 AI 配置，请在 AI Settings 重新保存或清除配置。") from None


def save_config(cfg: LLMConfig, path: Path | None = None) -> Path:
    """Atomically persist an explicitly selected mode, replacing any env fallback."""
    from llm.provider import validate_config

    validate_config(cfg)
    target = Path(path) if path is not None else CONFIG_PATH
    data = {
        "version": 1,
        "provider": "openai_compatible" if cfg.provider in ("none", "mock") else cfg.provider,
        "mode": "demo" if cfg.is_mock else "live",
        "base_url": cfg.base_url,
        "model": cfg.model,
        "api_key": cfg.api_key,
        "timeout": cfg.timeout,
    }
    temporary = None
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.parent.is_symlink() or target.is_symlink():
            raise OSError
        fd, temporary = tempfile.mkstemp(prefix=".llm_config-", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
        return target
    except OSError:
        raise SettingsError("无法保存 AI 配置，请检查项目 .local 目录是否可写。") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def clear_config(path: Path | None = None) -> Path:
    """Remove saved secrets and explicitly select Demo, preventing env reactivation."""
    from llm.provider import LLMConfig

    return save_config(LLMConfig(provider="openai_compatible", mode="demo"), path)
