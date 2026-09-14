"""M4 manual web discovery; importing this package performs no network calls."""

from web_search.provider import load_config, search_web

__all__ = ["load_config", "search_web"]
