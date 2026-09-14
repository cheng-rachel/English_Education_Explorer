"""Thin Serper organic-results adapter; planning and quality gates stay upstream.

Response fields follow the public example at https://serper.dev/.
Unknown publication dates remain unknown; no fetch date is substituted.
"""

from datetime import datetime

import requests

from web_search.settings import SearchError

ENDPOINT = "https://google.serper.dev/search"


def _published_date(value):
    if not isinstance(value, str):
        return None
    for pattern in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date().isoformat()
        except ValueError:
            pass
    return None


def search_once(cfg, query, maximum, bounds):
    # Exact dates are checked by the common intake after normalization. Serper's
    # relative date strings are not promoted to invented publication dates.
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(ENDPOINT, headers={"X-API-KEY": cfg.api_key,
                                    "Content-Type": "application/json"},
                                    json={"q": query, "num": maximum},
                                    timeout=(5, cfg.timeout), allow_redirects=False)
            try:
                if response.status_code in (401, 403):
                    raise SearchError("搜索服务拒绝了身份验证，请检查 Serper API Key。")
                if response.status_code == 429:
                    raise SearchError("搜索服务限流或额度不足，请检查账户额度后重试。")
                if response.status_code != 200:
                    raise SearchError("搜索服务暂时不可用，请稍后重试。")
                data = response.json()
            finally:
                response.close()
        if not isinstance(data, dict) or not isinstance(data.get("organic"), list):
            raise SearchError("搜索服务返回格式异常，请稍后重试。")
        results = []
        for item in data["organic"][:maximum]:
            if not isinstance(item, dict):
                results.append(item)
                continue
            results.append({"title": item.get("title"), "url": item.get("link"),
                            "content": item.get("snippet"),
                            "published_date": _published_date(item.get("date"))})
        return {"results": results}
    except requests.Timeout:
        return {"reason": "联网搜索超时，请稍后重试。"}
    except requests.RequestException:
        return {"reason": "无法连接搜索服务，请检查网络后重试。"}
    except (ValueError, TypeError, UnicodeError):
        return {"reason": "搜索服务返回格式异常，请稍后重试。"}
    except SearchError as exc:
        return {"reason": exc.user_message}
