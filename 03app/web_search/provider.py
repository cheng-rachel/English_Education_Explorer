"""One active search adapter with shared bounded result intake.

Protocol verified against https://docs.tavily.com/documentation/api-reference/endpoint/search
on 2026-09-13. Search dates are provider estimates of publication OR last update;
fetch timestamps never stand in for publication dates.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import math

import requests

from web_search.intake import fetch_page, public_url, safe_failure_url
from web_search.settings import SearchConfig, SearchError, append_failures, load_config, validate_config
from output_safety import sanitize_data, sanitize_text, sanitize_url
from web_search.serper import ENDPOINT as SERPER_ENDPOINT, search_once as _serper_search_once

ENDPOINT = "https://api.tavily.com/search"
MAX_QUERIES = 3
MAX_RESULTS = 6
MAX_PAGE_FETCHES = 3


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        try:
            return parsedate_to_datetime(value).date()
        except (ValueError, TypeError, OverflowError):
            return None


def date_bounds(filters):
    """Exact days, plus explicit date boundaries; no false 90-day/3-month mapping."""
    if filters.get("start_date") or filters.get("end_date"):
        start = _date(filters.get("start_date"))
        end = _date(filters.get("end_date")) or date.today()
        if not start or start > end:
            raise SearchError("搜索时间范围无效，请重新选择。")
        return start, end
    selected = filters.get("window_days", filters.get("time_window", filters.get("time_range", "近90天")))
    windows = {"近30天": 30, "近90天": 90, "近1年": 365, "30d": 30, "90d": 90, "1y": 365,
               "30": 30, "90": 90, "365": 365, "month": 30, "year": 365}
    days = windows.get(str(selected))
    if days is None:
        raise SearchError("搜索时间范围无效，请选择近30天、近90天或近1年。")
    end = date.today()
    return end - timedelta(days=days), end


def _search_once(cfg, query, maximum, bounds):
    start, end = bounds
    payload = {"query": query, "search_depth": "basic", "topic": "general", "max_results": maximum,
               "include_answer": False, "include_raw_content": False, "include_images": False,
               "include_published_date": True, "filter_by_published_date": False,
               "start_date": start.isoformat(), "end_date": end.isoformat(), "auto_parameters": False}
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(ENDPOINT, headers={"Authorization": f"Bearer {cfg.api_key}",
                                    "Content-Type": "application/json"}, json=payload,
                                    timeout=(5, cfg.timeout), allow_redirects=False)
            try:
                if response.status_code in (401, 403):
                    raise SearchError("搜索服务拒绝了身份验证，请检查 Tavily API Key。")
                if response.status_code in (429, 432, 433):
                    raise SearchError("搜索服务限流或额度不足，请检查账户额度后重试。")
                if response.status_code != 200:
                    raise SearchError("搜索服务暂时不可用，请稍后重试。")
                data = response.json()
            finally:
                response.close()
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise SearchError("搜索服务返回格式异常，请稍后重试。")
        return {"results": data["results"][:maximum]}
    except requests.Timeout:
        return {"reason": "联网搜索超时，请稍后重试。"}
    except requests.RequestException:
        return {"reason": "无法连接搜索服务，请检查网络后重试。"}
    except (ValueError, TypeError, UnicodeError):
        return {"reason": "搜索服务返回格式异常，请稍后重试。"}
    except SearchError as exc:
        return {"reason": exc.user_message}


def _failure(url, reason, stage):
    return sanitize_data({"url": safe_failure_url(url), "reason": reason, "stage": stage})


def search_web(queries: list[str], filters: dict, *, cfg: SearchConfig | None = None) -> dict:
    """Return results/failures/searched_at/status; no credentials or raw errors.

    Result dates may be unknown. content_kind is full_text only after a successful
    page read; otherwise content remains explicitly labeled search_snippet.
    """
    cfg = cfg if cfg is not None else load_config()
    result = {"results": [], "failures": [], "searched_at": None, "status": "not_configured",
              "provider": cfg.provider}
    if not cfg.configured:
        result["message"] = cfg.configuration_error or "当前联网搜索不可用，本次仅使用本地资料。可前往 Manage Data → Search Settings 配置。"
        if cfg.provider == "custom" and not cfg.configuration_error:
            result["message"] = "Custom 配置已保留，接口暂未启用。当前联网搜索不可用，本次仅使用本地资料。"
        if cfg.configuration_error:
            result["status"] = "failed"
        return result
    try:
        validate_config(cfg)
        if not isinstance(filters, dict) or not isinstance(queries, list):
            raise SearchError("搜索条件无效，请重新选择筛选条件。")
        clean_queries = list(dict.fromkeys(query.strip()[:500] for query in queries if isinstance(query, str) and query.strip()))[:MAX_QUERIES]
        if not clean_queries:
            raise SearchError("请输入需要观察的英语教育需求或主题后更新联网信息。")
        bounds = date_bounds(filters)
    except SearchError as exc:
        result.update(status="failed", message=exc.user_message)
        return result
    maximum = math.ceil(MAX_RESULTS / len(clean_queries))
    search_once = _search_once if cfg.provider == "tavily" else _serper_search_once
    endpoint = ENDPOINT if cfg.provider == "tavily" else SERPER_ENDPOINT
    # At most three independent requests, each once. Deterministic query order is
    # retained even when the HTTP requests complete in a different order.
    with ThreadPoolExecutor(max_workers=len(clean_queries)) as pool:
        outcomes = list(pool.map(lambda query: search_once(cfg, query, maximum, bounds), clean_queries))
    seen = set()
    start, end = bounds
    successes = 0
    for query, outcome in zip(clean_queries, outcomes):
        if "reason" in outcome:
            result["failures"].append(_failure(endpoint, outcome["reason"], "search"))
            continue
        successes += 1
        for item in outcome["results"]:
            if not isinstance(item, dict):
                result["failures"].append(_failure("", "搜索条目格式不完整，已跳过。", "normalize"))
                continue
            url = sanitize_url(public_url(item.get("url")))
            if not url:
                result["failures"].append(_failure("", "搜索条目的网址不适合公开读取，已跳过。", "normalize"))
                continue
            if url in seen or len(result["results"]) >= MAX_RESULTS:
                continue
            published = _date(item.get("published_date"))
            if published and not start <= published <= end:
                result["failures"].append(_failure(url, "来源日期不在当前时间范围内，已跳过。", "date_filter"))
                continue
            content = item.get("content")
            title = item.get("title")
            if not isinstance(content, str) or not content.strip():
                result["failures"].append(_failure(url, "搜索条目没有可用摘要，已跳过。", "normalize"))
                continue
            seen.add(url)
            result["results"].append({
                "title": sanitize_text(title)[:300] if isinstance(title, str) and title.strip() else url,
                "url": url, "content": sanitize_text(content)[:5000], "content_kind": "search_snippet",
                "published_date": published.isoformat() if published else None,
                "date_basis": "provider_estimated_published_or_updated" if published else "unknown",
                "fetched_at": None, "source_type": "未知来源", "search_provider": cfg.provider,
                "source": cfg.provider, "query": sanitize_text(query),
                "query_purpose": None, "language": None,
                "snippet": sanitize_text(content)[:5000], "fetch_status": "search_snippet",
            })
    if successes:
        result["searched_at"] = _now()
    if filters.get("fetch_pages", True) and result["results"]:
        targets = result["results"][:MAX_PAGE_FETCHES]
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            pages = list(pool.map(lambda item: fetch_page(item["url"]), targets))
        for item, page in zip(targets, pages):
            if page.get("content"):
                item.update(content=page["content"], content_kind="full_text", fetched_at=_now(), fetch_status="full_text")
                if page.get("title"):
                    item["title"] = sanitize_text(page["title"])[:300]
            else:
                item["fetch_status"] = "fetch_failed_snippet_retained"
                result["failures"].append(_failure(item["url"], page.get("reason", "未取得网页正文，已保留搜索摘要。"), "fetch"))
    result["status"] = "failed" if not successes else "partial" if result["failures"] else "success"
    if not append_failures(result["failures"], _now()):
        result["failures"].append(_failure("", "本次失败记录未能写入本地日志。", "log"))
        if result["status"] == "success":
            result["status"] = "partial"
    return sanitize_data(result)


def test_connection(cfg):
    """One small actual search checks credentials; this never changes update dates."""
    validate_config(cfg)
    if not cfg.configured:
        raise SearchError("Custom 目前仅保存配置，尚未启用搜索接口。" if cfg.provider == "custom" else "请先输入搜索 API Key。")
    search_once = _search_once if cfg.provider == "tavily" else _serper_search_once
    outcome = search_once(cfg, "English education", 1, date_bounds({"time_window": "近1年"}))
    if "reason" in outcome:
        raise SearchError(outcome["reason"])
