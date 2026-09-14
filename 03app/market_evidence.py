"""M4 evidence helpers; reuse M2 FTS5 and keep requested scope distinct from evidence."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from urllib.parse import urlsplit

from knowledge.retrieval import get_retriever
from knowledge.tagging import CONTEXT_KEYWORDS, SKILL_KEYWORDS, discussion_audiences
from knowledge.textutil import clean_for_display, normalize_date
from knowledge.content_roles import classify_content_role
from market_quality import clean_evidence_url, prepare_evidence
from taxonomy import AUDIENCES, CONTEXTS, REGIONS, SKILLS_PROFESSIONAL, TIME_WINDOWS

WINDOW_DAYS = {"近30天": 30, "近90天": 90, "近1年": 365, "近3年": 365 * 3, "近5年": 365 * 5, "近10年": 365 * 10}
SKILL_EN = {"听力理解": "listening comprehension", "听力解码": "speech decoding",
            "口语表达": "English speaking", "阅读理解": "reading comprehension", "写作表达": "English writing",
            "单词拼写": "spelling", "词汇量扩展": "vocabulary", "自然拼读": "phonics reading transfer",
            "语法知识": "English grammar", "跨学科素养": "CLIL cross curricular English"}
CONTEXT_EN = dict(zip(CONTEXTS, ["classroom", "home learning", "short daily practice", "parent child learning",
                              "independent learning", "real life use", "travel", "bedtime", "peer interaction", "school curriculum"]))
AUDIENCE_EN = dict(zip(AUDIENCES, ["students", "parents", "teachers curriculum designers", "edtech developers", "education publishers", "learners"]))
ISSUES = {"口语表达": ("阅读输入多 不主动开口 只会跟读", "reading input reluctant to speak repeat only"),
          "自然拼读": ("学过拼读 仍不能自主阅读", "learned phonics cannot read independently transfer"),
          "阅读理解": ("读得出 不理解 阅读难度提高", "decoding without comprehension reading difficulty"),
          "听力理解": ("听不懂 听力材料太难", "cannot understand listening material too difficult")}


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_filters(filters):
    filters = filters if isinstance(filters, dict) else {}
    region = filters.get("region", REGIONS[0])
    if region not in REGIONS:
        raise ValueError("请选择中国大陆或海外 Benchmark。")
    window = filters.get("time_window", "近90天")
    if window not in TIME_WINDOWS:
        raise ValueError("请选择有效的时间范围。")
    ages = filters.get("age_range") or [36, 191]
    if not isinstance(ages, (list, tuple)) or len(ages) != 2 or any(type(n) is not int for n in ages):
        raise ValueError("请填写完整的年龄范围。")
    if not 36 <= ages[0] <= ages[1] <= 191:
        raise ValueError("年龄范围应为 3–15 岁，结束年龄不能早于起始年龄。")
    result = {"region": region, "time_window": window, "age_range": list(ages)}
    for key, allowed in (("skills", SKILLS_PROFESSIONAL), ("contexts", CONTEXTS), ("audiences", AUDIENCES)):
        values = filters.get(key) or []
        if not isinstance(values, (list, tuple)):
            raise ValueError("筛选标签格式有误，请重新选择。")
        result[key] = [v for v in dict.fromkeys(values) if v in allowed]
    return result


def age_label(ages):
    return f"{ages[0] // 12}岁{ages[0] % 12}个月–{ages[1] // 12}岁{ages[1] % 12}个月"


def window_start(filters):
    return date.today() - timedelta(days=WINDOW_DAYS[filters["time_window"]])


def build_search_queries(filters):
    """Compatibility entry point; the Market plan owns intent and language."""
    from market_search_plan import build_search_plan
    return [item["query"] for item in build_search_plan(normalize_filters(filters))["queries"]]


def date_scope(raw, filters):
    raw = str(raw or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]", raw):
        raw = raw[:10]
    _, normalized = normalize_date(raw)
    if not normalized:
        return "unknown_date", None
    if len(normalized) != 10:
        # Partial dates are never treated as a recent observation.
        return "imprecise_date", normalized
    day = date.fromisoformat(normalized)
    if day > date.today():
        return "future_date_unverified", normalized
    return ("within_window" if day >= window_start(filters) else "historical"), normalized


def credibility(source_type):
    if source_type in ("产品 / 机构官网", "政策 / 政府", "行业报告", "学术 / 研究机构"):
        return "A"
    if source_type in ("教育 / 科技媒体", "行业分析"):
        return "B"
    if source_type in ("公开用户讨论", "应用商店 / 产品评价"):
        return "C"
    return "待核验"


def _relevant(text, skills):
    lower = text.lower()
    if skills:
        terms = [term for skill in skills for term in SKILL_KEYWORDS.get(skill, [])]
        return any(term.lower() in lower for term in terms)
    return any(term in lower for term in ("英语", "英文", "english", "phonics", "language learning"))


def _age_matches(title, ages):
    # Only explicit ages in the source title filter out a known mismatch. Most
    # reports have no age metadata and remain clearly marked as background.
    numbers = dict(zip(["三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五"], range(3, 16)))
    title = re.sub(r"(十五|十四|十三|十二|十一|十|九|八|七|六|五|四|三)岁", lambda m: str(numbers[m[1]]) + "岁", title)
    match = re.search(r"(?<!\d)(\d{1,2})\s*(?:[–\-至到]\s*(\d{1,2}))?\s*岁", title)
    if not match:
        return True, "资料年龄覆盖待核验"
    start, end = int(match[1]) * 12, int(match[2] or match[1]) * 12 + 11
    return (start <= ages[1] and end >= ages[0]), "来源标题明确提及年龄，与目标范围有交集"


def _local_hit(hit, f, skills):
    """Existing hit normalization, shared by the three Market-local lanes."""
    from output_safety import sanitize_text
    text = sanitize_text(clean_for_display(hit.chunk_text))
    if not _relevant(hit.title + " " + text, f["skills"]):
        return None
    matches_age, age_basis = _age_matches(hit.title, f["age_range"])
    if not matches_age:
        return None
    # Keep the skill-bearing section even when a long chunk begins with unrelated text.
    terms = [t.lower() for s in skills for t in SKILL_KEYWORDS.get(s, [])]
    positions = [text.lower().find(t) for t in terms if t in text.lower()]
    start = max(0, min(positions) - 180) if positions else 0
    text = text[start:start + 1400]
    scope, normalized = date_scope(hit.date, f)
    source_date = hit.date or ""
    date_basis = "source_metadata"
    year = re.search(r"(?<!\d)(20\d{2})(?!\d)", hit.title)
    if not normalized and year:
        source_date, normalized = year[1], year[1]
        date_basis = "title_year"
        scope = "historical" if int(year[1]) < window_start(f).year else "imprecise_date"
    return {"id": "", "title": hit.title, "source_type": hit.source_type or "其他",
                     "region": hit.region, "date": source_date, "normalized_date": normalized,
                     "date_basis": date_basis, "time_scope": scope, "age_basis": age_basis,
                     "matched_contexts": [c for c in f["contexts"] if any(term.lower() in text.lower() for term in CONTEXT_KEYWORDS[c])],
                     "discussion_audiences": discussion_audiences(text) if hit.source_type == "公开用户讨论" else [],
                     "url": hit.source_url or "", "original_path": hit.original_path or "",
                     "content": text, "content_kind": "local_chunk", "origin": "local",
                     "source_kind": hit.source_kind, "document_id": hit.document_id,
                     "chunk_id": hit.chunk_id, "raw_category": getattr(hit, "raw_category", ""),
                     "content_role": getattr(hit, "content_role", "general_reference"),
                     "credibility_level": credibility(hit.source_type),
                     "page_start": hit.page_start, "page_end": hit.page_end}


def retrieve_local(filters):
    from market_local_lanes import retrieve_lanes
    f = normalize_filters(filters)
    try:
        retriever = get_retriever()
    except Exception:
        return [], [{"stage": "local_retrieval", "reason": "本地知识库暂时不可用；可以继续使用其他已有资料。", "url": ""}]
    return retrieve_lanes(f, retriever)


def combine_evidence(local, results, filters):
    from output_safety import sanitize_data, sanitize_text
    # Keep geography separate. General learning references may explain a
    # mechanism, but their explicit kind can never supply a market signal.
    local = [ev for ev in local if ev.get("region") == filters["region"]
             and ev.get("raw_category") != "learnpath" and ev.get("evidence_role") != "learning_reference"]
    combined = list(local)
    known_hosts = {}
    for ev in local:
        if ev.get("url"):
            known_hosts[urlsplit(ev["url"]).hostname] = ev["source_type"]
    for item in results[:6]:
        if item.get("region") == "general_reference" or item.get("raw_category") == "learnpath" or item.get("evidence_role") == "learning_reference":
            continue
        url = clean_evidence_url(item.get("url") or "")
        parts = urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
            continue
        if not item.get("content"):
            continue
        content = sanitize_text(clean_for_display(item["content"]))[:1600]
        if not _relevant(str(item.get("title", "")) + " " + content, filters["skills"]):
            continue
        host = parts.hostname.lower()
        source_type = item.get("source_type") or known_hosts.get(host, "其他")
        if any(host == h or host.endswith("." + h) for h in ("reddit.com", "zhihu.com", "xiaohongshu.com", "xiaohuasheng.cn", "douban.com", "mumsnet.com", "netmums.com")):
            source_type = "公开用户讨论"
        elif host in ("apps.apple.com", "play.google.com"):
            source_type = "应用商店 / 产品评价"
        elif host.endswith((".gov.cn", ".gov")):
            source_type = "政策 / 政府"
        elif host.endswith((".edu", ".edu.cn", ".ac.uk")):
            source_type = "学术 / 研究机构"
        scope, normalized = date_scope(item.get("published_date"), filters)
        combined.append({"id": "", "title": str(item.get("title") or host), "source_type": source_type,
                         "region": filters["region"], "region_basis": "搜索目标范围，页面适用市场待核验",
                         "date": item.get("published_date") or "", "normalized_date": normalized,
                         "date_basis": item.get("date_basis") or "provider_metadata", "time_scope": scope,
                         "url": url, "original_path": "", "content": content, "origin": "web",
                         "content_kind": item.get("content_kind") or "search_snippet",
                         "content_role": classify_content_role(content, source_type=source_type, title=str(item.get("title") or "")),
                         "credibility_level": credibility(source_type)})
    # Freshly assembled results receive contiguous IDs after deduplication.
    return prepare_evidence([dict(ev, id="") for ev in combined], filters)
