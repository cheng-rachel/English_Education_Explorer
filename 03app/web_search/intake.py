"""Small bounded public-page reader: no login, JS execution, redirect or retries."""

from __future__ import annotations

import ipaddress
import re
import time
from urllib import robotparser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from output_safety import sanitize_text

USER_AGENT = "EngEduScope/0.4 (local research tool)"
BLOCKED_CONTENT = re.compile(r"verify (?:that )?you are human|checking your browser|enable javascript(?: and cookies)?|captcha|cf-chl-|登录后(?:查看|阅读)|请先登录|人机验证|安全验证", re.I)


def public_url(value):
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").lower()
        if (parts.scheme not in ("http", "https") or parts.username or parts.password
                or not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal"))
                or any(char.isspace() for char in value) or (parts.port not in (None, 80, 443))):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            if "." not in host:
                return ""
        query = []
        for key, val in parse_qsl(parts.query, keep_blank_values=True):
            if re.search(r"(?:api.?key|token|secret|password|authorization)", key, re.I):
                return ""
            if not key.lower().startswith("utm_"):
                query.append((key, val))
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(query), ""))
    except (TypeError, ValueError):
        return ""


def safe_failure_url(value):
    normalized = public_url(value)
    if not normalized:
        return ""
    parts = urlsplit(normalized)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:600]


def _bounded_bytes(response, max_bytes, seconds=8):
    body = bytearray()
    deadline = time.monotonic() + seconds
    for chunk in response.iter_content(16384):
        if chunk:
            body.extend(chunk)
        if len(body) > max_bytes or time.monotonic() > deadline:
            raise ValueError
    return bytes(body)


def _robots_allowed(url, session):
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    with session.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=(3, 3),
                     allow_redirects=False, stream=True) as response:
        if response.status_code == 404:
            return True
        if response.status_code != 200:
            return False
        raw = _bounded_bytes(response, 65536, seconds=4).decode("utf-8", errors="replace")
    parser = robotparser.RobotFileParser()
    parser.parse(raw.splitlines())
    return parser.can_fetch("EngEduScope", url)


def fetch_page(url):
    """Return content/title on success, otherwise a fixed safe reason; no raw errors."""
    url = public_url(url)
    if not url:
        return {"reason": "页面地址不适合公开抓取，已跳过。"}
    try:
        with requests.Session() as session:
            # Public pages never inherit API credentials, netrc credentials or cookies.
            session.trust_env = False
            if not _robots_allowed(url, session):
                return {"reason": "robots.txt 禁止抓取或无法确认许可，已保留搜索摘要。"}
            with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=(3, 5),
                             allow_redirects=False, stream=True) as response:
                if response.status_code in (401, 403, 429):
                    return {"reason": "页面要求登录、限制访问或触发验证，已保留搜索摘要。"}
                if 300 <= response.status_code < 400:
                    return {"reason": "页面需要跳转，已保留搜索摘要。"}
                if response.status_code != 200:
                    return {"reason": "页面暂时无法访问，已保留搜索摘要。"}
                content_type = response.headers.get("Content-Type", "").lower()
                if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml")):
                    return {"reason": "当前仅抓取普通文本网页，已保留搜索摘要。"}
                raw = _bounded_bytes(response, 1_000_000)
                encoding = response.encoding or "utf-8"
                if encoding.lower() in ("iso-8859-1", "latin-1", "ascii"):
                    encoding = "utf-8"
                text = raw.decode(encoding, errors="replace")
        if BLOCKED_CONTENT.search(text[:30000]):
            return {"reason": "页面包含登录、验证或动态加载提示，已保留搜索摘要。"}
        if "text/plain" in content_type:
            title, content = "", text
        else:
            from knowledge.webfetch import extract_main_content
            title, content = extract_main_content(text, url)
        if not isinstance(content, str) or len(content.strip()) < 200:
            return {"reason": "未识别到足够正文，可能是动态页面，已保留搜索摘要。"}
        return {"title": sanitize_text(title), "content": sanitize_text(content)[:16000]}
    except requests.Timeout:
        return {"reason": "页面请求超时，已保留搜索摘要。"}
    except (requests.RequestException, ValueError, TypeError, LookupError):
        return {"reason": "页面抓取或解析失败，已保留搜索摘要。"}
