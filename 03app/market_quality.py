"""Conservative Market-only evidence labels and presentation helpers.

These helpers operate on copies of result evidence. Registries, raw files and
the shared knowledge index are never changed.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from knowledge.tagging import SKILL_KEYWORDS
from output_safety import sanitize_data, sanitize_text

KIND_LABELS = {"demand": "需求侧", "supply": "供给侧", "research": "研究背景",
               "policy": "政策背景", "learning": "学习参考", "background": "一般背景"}
_DISCUSSION_TYPES = {"公开用户讨论", "应用商店 / 产品评价", "用户评价", "论坛 / 社区讨论"}
_SURVEY = re.compile(r"(?:调查|调研|问卷|访谈).{0,40}(?:\d+\s*(?:位|名|个|份)|样本|受访)|(?:\d+\s*(?:位|名|个|份)|样本|受访).{0,40}(?:调查|调研|问卷|访谈)|\b(?:survey|interview)(?:ed|s)?\b.{0,40}(?:\d+|respondents|participants)", re.I)
_FINDING = re.compile(r"(?:家长|学生|用户|受访者).{0,50}(?:反馈|表示|反映|认为|困难|不满|希望|尝试)|(?:反馈|反映|发现).{0,40}(?:困难|不满|需求)|(?:parents|students|users|respondents).{0,50}(?:reported|struggl|difficult|dissatisf|tried)", re.I)
_FIRST_PERSON = re.compile(r"我家|我(?:的孩子|的儿子|的女儿|是学生)|我们家|\bmy (?:child|son|daughter)\b|\bI (?:tried|used|struggle|cannot)\b", re.I)
_DIFFICULTY = re.compile(r"不会|不懂|困难|没效果|没有效果|不满意|尝试|试过|还是|太贵|坚持不了|cannot|struggl|difficult|dissatisf|tried|didn.t work", re.I)
_SALES = re.compile(r"立即购买|限时优惠|预约(?:体验|试听)|免费(?:体验|试听)|报名咨询|联系我们|buy now|book (?:a |your )?(?:demo|trial)|start (?:your |a )?free trial", re.I)
_PRODUCT_SCAN = re.compile(r"产品(?:全景|扫描|盘点|发布|介绍|功能)|教育产品.{0,8}(?:全景|扫描)|产品矩阵|product (?:landscape|launch|overview|features)", re.I)


def clean_evidence_url(url):
    """Clean a user-facing reference, leaving the source registry untouched."""
    try:
        parts = urlsplit(sanitize_text(str(url or "")).strip())
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            return ""
        tracking = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid", "spm", "scm", "_hsenc", "_hsmi"}
        query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                 if not key.lower().startswith("utm_") and key.lower() not in tracking]
        # Keep ordinary anchors (including an anchor preceding a text fragment).
        fragment = parts.fragment.split(":~:text=", 1)[0]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query, doseq=True), fragment))
    except (ValueError, TypeError):
        return ""


def evidence_kind(ev):
    ev = ev if isinstance(ev, dict) else {}
    source = str(ev.get("source_type") or "")
    category = str(ev.get("raw_category") or "")
    role = str(ev.get("content_role") or "")
    title = str(ev.get("title") or "")
    text = str(ev.get("content") or ev.get("text") or ev.get("snippet") or "")
    combined = title + "\n" + text
    if category == "learnpath" or source == "通用学习路径参考资料" or ev.get("region") == "general_reference" or ev.get("evidence_role") == "learning_reference":
        return "learning"
    if category == "policies" or "政策" in source or "政府" in source or role == "policy_background":
        return "policy"
    # An official sales page's claim about a parent pain point is still supply.
    if category == "product_docs" or source == "产品 / 机构官网" or _PRODUCT_SCAN.search(title) or re.search(r"来源[：:].{0,10}(?:产品官网|机构官网)", text):
        return "supply"
    if _SALES.search(combined) and (role == "product_info" or source not in ("行业报告", "学术 / 研究机构")):
        return "supply"
    is_research = category in ("research", "reports") or source in ("行业报告", "行业分析", "学术 / 研究机构") or role == "research_evidence"
    if is_research:
        # A market-size chart or "parents are anxious" is not a needs survey.
        return "demand" if _SURVEY.search(text) and _FINDING.search(text) else "research"
    if source in _DISCUSSION_TYPES or category == "public_discussions":
        return "demand"
    if role == "product_info":
        return "supply"
    if _FIRST_PERSON.search(text) and _DIFFICULTY.search(text):
        return "demand"
    if role in ("learning_path", "practice_guide"):
        return "learning"
    return "background"


def source_key(ev):
    url = clean_evidence_url(ev.get("url") or ev.get("source_url") or "")
    if url:
        parts = urlsplit(url)
        return "url:" + urlunsplit(("", parts.netloc.removeprefix("www."), parts.path.rstrip("/"), parts.query, ""))
    if ev.get("document_id"):
        return "doc:" + str(ev["document_id"])
    if ev.get("original_path"):
        return "file:" + str(ev["original_path"])
    return "title:" + re.sub(r"\W+", "", str(ev.get("title") or "")).lower()


def noisy_text(text):
    """Reject broken extraction, not normally unspaced Chinese prose."""
    value = str(text or "").strip()
    if not value:
        return True
    if value.count("\ufffd") + value.count("\x00") >= max(2, len(value) * .015):
        return True
    if re.search(r"[A-Za-z]{65,}", value):
        return True
    if len(re.findall(r"[•●▪★☆]", value)) >= 12:
        return True  # flattened multi-column lists and rating tables
    if len(re.findall(r"[\ue000-\uf8ff]", value)) >= 2:
        return True  # PDF font glyphs with no portable character meaning
    if len(re.findall(r"[•●▪]", value)) >= 6 and len(re.findall(r"[。！？!?]", value)) <= 1:
        return True
    meaningful = len(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", value))
    if len(value) > 40 and meaningful / len(value) < .48:
        return True
    separators = len(re.findall(r"[|│┃┼┤├═_]{1,}", value))
    if separators >= 12 and separators > meaningful / 10:
        return True
    tokens = value.split()
    if len(tokens) >= 20 and sum(len(token) == 1 for token in tokens) / len(tokens) > .65:
        return True
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) >= 12 and sum(len(line) <= 3 for line in lines) / len(lines) > .6:
        return True
    return False


def readable_excerpt(text, limit=140):
    value = sanitize_text(str(text or ""))
    if noisy_text(value):
        return ""
    value = re.sub(r"https?://[^\s<>）)]+", "", value)
    value = re.sub(r"(?:©|copyright).{0,90}?(?:www\.[A-Za-z0-9.-]+(?:/\S*)?|all rights reserved[.。]?)", "", value, flags=re.I)
    value = re.sub(r"\bwww\.[A-Za-z0-9.-]+(?:/\S*)?", "", value)
    value = re.sub(r"(?m)^\s*(?:第?\s*\d+\s*页?|page\s+\d+)\s*$", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    # Do not expose an uninterrupted PDF blob as a quote.
    if len(value) > 350 and not re.search(r"[。！？.!?；;]", value):
        return ""
    sentences = re.findall(r"[^。！？.!?]+[。！？.!?]?", value)
    result = ""
    for sentence in sentences[:3]:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = (result + " " + sentence).strip()
        if len(candidate) <= limit:
            result = candidate
        else:
            break
        if len(result) > limit * .6:
            break
    if result:
        return result
    short = value[:max(0, limit - 1)].rstrip()
    # Prefer a natural clause boundary when one is available near the limit.
    cut = max(short.rfind("，"), short.rfind("；"), short.rfind(", "), short.rfind("; "))
    if cut >= limit // 2:
        short = short[:cut]
    elif re.search(r"[A-Za-z]$", short) and " " in short:
        short = short.rsplit(" ", 1)[0]
    return short + "…" if short else ""


def _term_count(text, terms):
    patterns = []
    for term in sorted(set(terms), key=len, reverse=True):
        escaped = re.escape(term.lower())
        patterns.append(r"\b" + escaped + r"\b" if term.isascii() else escaped)
    return len(re.findall("|".join(patterns), text.lower())) if patterns else 0


def _relevance(ev, filters):
    title = str(ev.get("title") or "")
    content = str(ev.get("content") or ev.get("text") or ev.get("snippet") or "")
    if noisy_text(content):
        return None
    scope_text = title + " " + content[:300]
    region = (filters or {}).get("region")
    china_scope = bool(re.search(r"中国(?:市场|校外|校内|家庭)|国内(?:市场|家庭|教育)", scope_text))
    foreign_scope = bool(re.search(r"(?:美国|英国|海外)(?:校外|校内|市场|家庭|教育智能硬件)", scope_text))
    if region == "中国大陆" and foreign_scope and not china_scope:
        return None
    if region == "海外 Benchmark" and china_scope and not foreign_scope:
        return None
    skills = (filters or {}).get("skills") or []
    terms = [term for skill in skills for term in SKILL_KEYWORDS.get(skill, [])]
    body_hits, title_hits = _term_count(content, terms), _term_count(title, terms)
    if skills and not body_hits:
        return None  # A broad source title cannot rescue an unrelated chunk.
    if skills and body_hits == 1 and not title_hits and len(content) > 350:
        return None  # one incidental mention inside a broad report is not enough
    other_terms = [term for skill, words in SKILL_KEYWORDS.items() if skill not in skills for term in words]
    other_hits = _term_count(content, other_terms)
    other_title = _term_count(title, other_terms)
    unrelated = _term_count(title + " " + content, ["数学", "数理", "物理", "化学", "math", "mathematics", "algebra"])
    if skills and ((body_hits <= 1 and (other_hits >= 3 or other_title > title_hits))
                   or (unrelated >= 2 and unrelated > body_hits * 2)
                   or (other_hits >= 8 and other_hits > body_hits * 3 and title_hits == 0)):
        return None
    ages = (filters or {}).get("age_range")
    if ages:
        age = re.search(r"(?<!\d)(\d{1,2})\s*(?:[–—\-至到]\s*(\d{1,2}))?\s*(?:岁|years? old)", title, re.I)
        if age and not (int(age[1]) * 12 <= ages[1] and (int(age[2] or age[1]) + 1) * 12 - 1 >= ages[0]):
            return None
        # Check the passages matching the requested skill, not unrelated age
        # labels elsewhere in a broad product scan (e.g. adult PDF tools).
        skill_passages = " ".join(sentence for sentence in re.split(r"[。！？.!?;；\n]", content)
                                  if _term_count(sentence, terms)) if skills else content
        school = _term_count(skill_passages, ["小学", "初中", "中学生", "小学生", "school children", "school students"])
        adult = _term_count(skill_passages, ["高等教育", "学术科研", "论文", "文献综述", "研究人员", "实验数据", "职场", "在职人士", "成年学习者", "higher education", "academic research"])
        preschool = _term_count(skill_passages, ["幼儿", "学龄前", "早教", "preschool", "toddler"])
        preschool_total = _term_count(content, ["幼儿", "学龄前", "早教", "preschool", "toddler"])
        if adult >= 2 and not school:
            return None
        if ages[0] >= 84 and (preschool >= 2 or preschool_total >= 3) and not school:
            return None
    return min(body_hits, 8) * 3 + min(title_hits, 3) * 4 + (2 if readable_excerpt(content) else 0)


def evidence_description(ev):
    kind = evidence_kind(ev)
    texts = {
        "demand": "记录用户的学习困难或使用体验；只代表这些具体记录。",
        "supply": "提供现有产品功能与学习机制参考，不能单独证明用户需求。",
        "research": "帮助理解研究机制与行业背景，不直接代表近期用户需求。",
        "policy": "提供教育方向与制度背景，不作为家长或学生需求证据。",
        "learning": "提供学习路径与教育原理参考，不作为市场趋势证据。",
        "background": "作为相关背景参考，资料能否支持需求判断仍需核验。",
    }
    if kind == "demand" and str(ev.get("source_type") or "") in ("行业报告", "行业分析", "学术 / 研究机构"):
        return "包含用户调查或访谈反馈；结论限于该调查的样本与范围。"
    return texts[kind]


def prepare_evidence(evidence, filters=None):
    """One best readable, relevant chunk per source; no retrieval or API calls."""
    best = {}
    for index, raw in enumerate(evidence or []):
        if not isinstance(raw, dict):
            continue
        ev = sanitize_data(dict(raw))
        ev["content"] = str(ev.get("content") or ev.get("text") or ev.get("snippet") or "")
        region = (filters or {}).get("region")
        if region and ev.get("region") and ev["region"] not in (region, "general_reference"):
            continue
        score = _relevance(ev, filters)
        if score is None:
            continue
        ev["url"] = clean_evidence_url(ev.get("url") or ev.get("source_url") or "")
        if "source_url" in ev:
            ev["source_url"] = ev["url"]
        ev["evidence_kind"] = evidence_kind(ev)
        ev["evidence_kind_label"] = KIND_LABELS[ev["evidence_kind"]]
        ev["description"] = evidence_description(ev)
        ev["excerpt"] = readable_excerpt(ev["content"])
        key = source_key(ev)
        # Prefer substantive/full-page context to the same page's search snippet.
        score += 2 if ev.get("content_kind") != "search_snippet" else 0
        score += 2 if ev.get("time_scope") == "within_window" else 0
        if key not in best or score > best[key][0]:
            best[key] = (score, index, ev)
    order = {"demand": 0, "supply": 1, "research": 2, "learning": 3, "background": 4, "policy": 5}
    chosen = sorted(best.values(), key=lambda item: (order[item[2]["evidence_kind"]], -item[0], item[1]))[:12]
    used_ids = {str(item[2].get("id")) for item in chosen if item[2].get("id")}
    next_id = 1
    output = []
    for _, _, ev in chosen:
        if not ev.get("id"):
            while f"E{next_id}" in used_ids:
                next_id += 1
            ev["id"] = f"E{next_id}"
            used_ids.add(ev["id"])
        output.append(ev)
    return sanitize_data(output)
