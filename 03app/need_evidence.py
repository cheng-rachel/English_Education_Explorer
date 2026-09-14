"""Solve-only candidate reranking and bounded reuse of the existing web search."""
from datetime import date
import re
from urllib.parse import urlsplit

from knowledge.content_roles import CONTENT_ROLES, classify_content_role
from knowledge.tagging import SKILL_KEYWORDS
from need_intent import live_queries
from output_safety import HIDDEN, sanitize_data, sanitize_text, sanitize_url
from web_search.provider import search_web
from web_search.settings import load_config as load_search_config

INSUFFICIENT_NOTE = "目前已有资料不足以支持非常具体的产品判断，但可以先根据学习路径和通用教学原则给你一个可执行的起步方案。"

_ROLE_LIMITS = {
    "product_info": "产品资料用于核对功能与适用方式，不能单独证明学习效果。",
    "parent_experience": "这是个别家庭或用户的经验，不能据此推断所有学习者的效果。",
    "research_evidence": "研究用于解释可能的学习机制；能否适用于当前孩子仍需观察确认。",
    "policy_background": "政策仅补充教育背景，不作为每日练习方案或效果判断的主要依据。",
    "market_signal": "行业与讨论资料仅作背景，不代表当前学习者已经存在同样问题。",
}
_ACTION = re.compile(r"第一步|第二步|每天.{0,15}(?:分钟|次)|先.{1,25}(?:再|然后)|读后提问|复述|轮流|分阶段|达到.{0,12}(?:后|再)|\bstep [1-5]\b|\b(?:daily|minutes|retell|read aloud)\b", re.I)
_ENGLISH = re.compile(r"英语|英文|启蒙|语言发展|二语|外语|\b(?:english|efl|esl|phonics|language acquisition)\b", re.I)


def _readable(body):
    """Reject obvious extraction damage, without changing stored source material."""
    plain = re.sub(r"https?://\S+", "", body)
    compact = re.sub(r"\s+", "", plain)
    if len(compact) < 12:
        return False
    if plain.count("\ufffd") >= 3 or re.search(r"[A-Za-z]{60,}", plain):
        return False
    meaningful = sum(char.isalnum() for char in compact)
    if len(compact) >= 40 and meaningful / len(compact) < 0.55:
        return False
    lines = [line.strip() for line in plain.splitlines() if line.strip()]
    if len(lines) >= 12 and sum(len(line) <= 3 for line in lines) / len(lines) > 0.7:
        return False
    return True


def _useful_for_learner(source, terms, mapping, intent):
    body = (source.get("text") or source.get("content") or "").lower()
    if not _readable(body):
        return False
    title = (source.get("title") or "").lower()
    body_hits = sum(body.count(term) for term in terms)
    target_skills = mapping.get("primary_skills", [])
    # A passing mention of listening/reading in an essay or mathematics document
    # is not evidence for the child's current practice question.
    unrelated = r"数学|代数|几何|数学题|\bmathematics\b|\balgebra\b"
    if "写作表达" not in target_skills:
        unrelated += r"|作文(?:评阅|批改|评分)|写作评估|\bessay (?:scoring|grading|assessment)\b"
    if len(re.findall(unrelated, title + " " + body, re.I)) >= 2 and body_hits <= 2:
        return False
    if body_hits:
        return True
    # Broad beginner / product questions may need general English learning
    # material even when it does not name a single skill explicitly.
    broad_roles = {"learning_path", "practice_guide", "research_evidence", "parent_experience"}
    if intent == "product_choice":
        broad_roles.add("product_info")
    return (not terms or (intent in ("getting_started", "product_choice")
                          and source["content_role"] in broad_roles and bool(_ENGLISH.search(body))))


def _with_scope(source):
    limit = _ROLE_LIMITS.get(source["content_role"], "")
    current = source.get("scope_note") or ""
    return dict(source, scope_note=(current + (" " if current else "") + limit).strip()) if limit and limit not in current else source


def role_for(evidence):
    role = evidence.get("content_role")
    if role in CONTENT_ROLES:
        return role
    return classify_content_role(evidence.get("text") or evidence.get("content") or "",
                                 raw_category=evidence.get("raw_category") or "",
                                 source_type=evidence.get("source_type") or "",
                                 region=evidence.get("region") or "", title=evidence.get("title") or "")


def rank_evidence(candidates, strategy, mapping, top_k=8):
    """Keep FTS candidates; modest skill relevance and role priority choose the evidence."""
    candidates = sanitize_data(candidates)
    learner = strategy["user_type"] not in ("professional", "educator")
    terms = [term.lower() for skill in mapping.get("primary_skills", []) for term in SKILL_KEYWORDS.get(skill, [])]
    weighted = []
    for index, source in enumerate(candidates):
        source = dict(source, content_role=role_for(source))
        body = source.get("text") or source.get("content") or ""
        if not body or body == HIDDEN:
            continue
        if learner:
            if not _useful_for_learner(source, terms, mapping, strategy.get("primary_intent")):
                continue
            source = _with_scope(source)
        text = (source.get("title", "") + " " + body).lower()
        relevance = min(sum(term in text for term in terms), 3)
        role_weight = strategy["weights"].get(source["content_role"], 1)
        weighted.append((role_weight * 4 + relevance * 2, -index, source))
    weighted.sort(key=lambda row: (row[0], row[1]), reverse=True)
    result, seen, counts = [], set(), {}
    for _, _, source in weighted:
        key = source.get("chunk_id") or (source.get("source_url") or source.get("url"), source.get("text") or source.get("content"))
        document = source.get("document_id") or source.get("source_url") or source.get("url") or source.get("original_path") or source.get("title")
        if key in seen or counts.get(document, 0) >= 2:
            continue
        # Policy is background, never the bulk of a parent's or student's practice answer.
        if learner and source["content_role"] in ("policy_background", "market_signal"):
            if any(item["content_role"] in ("policy_background", "market_signal") for item in result):
                continue
        seen.add(key)
        counts[document] = counts.get(document, 0) + 1
        result.append(source)
        if len(result) >= top_k:
            break
    return [dict(source, id=f"E{index}") for index, source in enumerate(result, 1)]


def evidence_sufficient(evidence, intent, user_type=None):
    primary = intent["primary_intent"]
    preferred = ({"product_info", "parent_experience"} if primary == "product_choice"
                 else {"learning_path", "practice_guide", "research_evidence", "parent_experience"})
    documents = {source.get("document_id") or source.get("source_url") or source.get("url") or source.get("title")
                 for source in evidence if role_for(source) in preferred}
    if len(documents) < 2:
        return False
    if user_type in ("professional", "educator"):
        return True
    if primary in ("getting_started", "skill_practice"):
        return any(role_for(source) in ("learning_path", "practice_guide")
                   and _ACTION.search(source.get("text") or source.get("content") or "") for source in evidence)
    if primary == "product_choice":
        return any(role_for(source) == "product_info" for source in evidence)
    return True


def _search_source(item, local):
    item = sanitize_data(item)
    url = sanitize_url(item.get("url"))
    if not url or not item.get("content") or item["content"] == HIDDEN:
        return None
    host = (urlsplit(url).hostname or "").lower()
    known = {(urlsplit(ev.get("source_url") or ev.get("url") or "").hostname or "").lower(): ev.get("source_type")
             for ev in local if ev.get("source_url") or ev.get("url")}
    source_type = known.get(host) or "其他"
    if any(host == domain or host.endswith("." + domain) for domain in ("reddit.com", "zhihu.com", "xiaohongshu.com", "xiaohuasheng.cn", "douban.com")):
        source_type = "公开用户讨论"
    elif host.endswith((".gov", ".gov.cn")):
        source_type = "政策 / 政府"
    elif host.endswith((".edu", ".edu.cn", ".ac.uk")):
        source_type = "学术 / 研究机构"
    role = classify_content_role(item["content"], source_type=source_type, title=item.get("title") or "")
    learning = role in ("learning_path", "practice_guide", "research_evidence", "general_reference")
    return {"id": "", "title": item.get("title") or host, "text": sanitize_text(item["content"])[:1200],
            "source_url": url, "url": url, "original_path": "", "source_kind": "web",
            "kind_label": "联网公开资料", "source_type": source_type, "content_role": role,
            "region": "general_reference" if learning else "适用地域待核验",
            "evidence_role": "learning_reference" if learning else "need_evidence",
            "origin": "web", "content_kind": item.get("content_kind") or "search_snippet",
            "date": item.get("published_date") or "", "date_basis": item.get("date_basis") or "unknown",
            "scope_note": "联网补充资料；适用年龄、地域和产品功能仍需核验，搜索日期不等于内容发布日期。"}


def supplement_search(result, mapping, intent, local):
    """Only explicit Solve analysis reaches here; History/rendering never call this."""
    meta = {"status": "not_requested", "requested": False, "searched_at": None, "failures": [],
            "message": "本次使用本地知识库资料。"}
    if result.get("user_type") not in ("parent", "student"):
        return local, meta
    try:
        cfg = load_search_config()
    except Exception:
        meta.update(status="not_configured", message="联网设置暂时不可用，继续使用本地资料与通用练习建议。")
        return local, meta
    if not cfg.configured:
        meta.update(status="not_configured", message="当前仅使用本地知识库；未启用联网搜索。")
        return local, meta
    primary = intent["primary_intent"]
    if primary not in ("getting_started", "product_choice", "teacher_support", "skill_practice"):
        return local, meta
    # A general question about needing a teacher does not require live service
    # information. Explicit questions about current official services do.
    request = " ".join(str(result.get(key) or "") for key in ("problem", "background", "pain_point"))
    current_service = primary == "teacher_support" and bool(re.search(r"最近|最新|现在.{0,8}(?:机构|平台|课程)|官方|机构|平台|预约|服务入口|在哪里找", request))
    refresh = primary == "product_choice" or current_service
    if not refresh and evidence_sufficient(local, intent):
        meta.update(status="local_sufficient", message="本次已有相关本地资料，未发起联网搜索。")
        return local, meta
    queries = live_queries(result, mapping, intent)[:3]
    filters = {"region": "中国大陆", "time_window": "近1年", "fetch_pages": True}
    if not refresh:
        filters.update(start_date="1900-01-01", end_date=date.today().isoformat())
    meta.update(requested=True, queries=queries)
    try:
        outcome = search_web(queries, filters, cfg=cfg)
        meta.update({key: outcome.get(key) for key in ("status", "searched_at", "failures")})
        incoming = [_search_source(item, local) for item in outcome.get("results", [])[:6]]
        incoming = [item for item in incoming if item]
        meta["message"] = ("本次已补充少量联网公开资料；建议中的解释与练习安排仍需实际观察验证。" if incoming
                           else "本次联网未取得可用补充资料，继续使用本地资料与通用练习建议。")
        return sanitize_data(local + incoming), sanitize_data(meta)
    except Exception:
        meta.update(status="failed", message="联网补充暂时不可用，继续使用本地资料与通用练习建议。",
                    failures=[{"url": "", "stage": "search", "reason": "联网补充失败，已跳过。"}])
        return local, sanitize_data(meta)
