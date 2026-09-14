"""M6 History card metadata and filtering, computed from saved snapshots only."""

import json
import re
from output_safety import sanitize_data, sanitize_text

from taxonomy import AGE_BANDS, AUDIENCES, CARRIERS, CONTEXTS, PARENT_LEARNING_METHODS, REGIONS, SKILLS_PROFESSIONAL, TIME_WINDOWS

TYPE_LABELS = ("Solve a Need", "Market Research", "Build a Solution")
ALL_TYPES = "全部类型"
ALL_SKILLS = "全部能力"
ALL_AGES = "全部年龄"
ALL_REGIONS = "全部地域"
UNSPECIFIED = "未指定"

_PARENT_SKILLS = {"听": "听力理解", "说": "口语表达", "读": "阅读理解", "写": "写作表达"}
_STUDENT_SKILLS = {"听力": "听力理解", "口语": "口语表达", "阅读": "阅读理解", "写作": "写作表达",
                   "单词": "词汇量扩展", "语法": "语法知识", "不确定": "不确定"}
_SOLVE_ENTRIES = {"solve_need_parent_specific", "solve_need_parent_overview", "solve_need_educator", "solve_need_student"}


def parse_summary(value):
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, RecursionError):
        return None
    return sanitize_data(parsed) if isinstance(parsed, dict) else None


def _object(value):
    return value if isinstance(value, dict) else {}


def _text(value, limit=160):
    if not isinstance(value, str):
        return ""
    value = " ".join(sanitize_text(value).split())
    return value[:limit] + ("……" if len(value) > limit else "")


def _labels(value, allowed, mapping=None):
    if not isinstance(value, list):
        return []
    mapping = mapping or {}
    return list(dict.fromkeys(mapping.get(item, item) for item in value
                             if isinstance(item, str) and mapping.get(item, item) in allowed))


def parse_age_range(value):
    """Recognize M3 exact/range dicts, revised age text, and M4/M5 month pairs."""
    if isinstance(value, dict):
        if value.get("mode") == "range":
            start = parse_age_range(value.get("start"))
            end = parse_age_range(value.get("end"))
            return [start[0], end[1]] if start and end and start[0] <= end[1] else None
        if type(value.get("age_months")) is int:
            value = [value["age_months"], value["age_months"]]
        elif type(value.get("years")) is int and type(value.get("months", 0)) is int:
            months = value["years"] * 12 + value.get("months", 0)
            value = [months, months] if 0 <= value.get("months", 0) <= 11 else None
        else:
            return parse_age_range(value.get("display"))
    if isinstance(value, str):
        parts = re.split(r"\s*[-–—~～至到]\s*", value.strip())
        ages = []
        for part in parts[:2]:
            match = re.search(r"(\d{1,2})\s*(?:岁)?(?:\s*(\d{1,2})\s*个?月)?", part)
            if not match:
                return None
            month = int(match[2]) if match[2] is not None else None
            if month is not None and month > 11:
                return None
            ages.append([int(match[1]) * 12 + (month or 0), month is not None])
        value = ([ages[0][0], ages[1][0] + (0 if ages[1][1] else 11)] if len(ages) == 2
                 else [ages[0][0], ages[0][0]] if ages else None)
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(type(months) is int for months in value):
        if 36 <= value[0] <= value[1] <= 191:
            return list(value)
    return None


def age_label(value):
    ages = parse_age_range(value)
    if not ages:
        return UNSPECIFIED
    def exact(months):
        return f"{months // 12}岁{months % 12}个月"
    return exact(ages[0]) if ages[0] == ages[1] else f"{exact(ages[0])} – {exact(ages[1])}"


def _record_type(session, summary):
    if summary.get("kind") == "product_concept" or session.get("entry_type") == "build_solution":
        return "Build a Solution"
    if summary.get("kind") == "market_research" or session.get("entry_type") == "explore_market":
        return "Market Research"
    if session.get("entry_type") in _SOLVE_ENTRIES or summary.get("entry_type") in ("parent_specific", "parent_overview", "professional", "student_specific"):
        return "Solve a Need"
    return "历史记录"


def _valid_choices(value, allowed):
    return value is None or (isinstance(value, list) and all(isinstance(item, str) and item in allowed for item in value))


def _valid_restore_age(value):
    if value is None or value == {}:
        return True
    if not isinstance(value, dict):
        return False
    if value.get("mode") == "range":
        return bool(parse_age_range(value) and _valid_restore_age(value.get("start")) and _valid_restore_age(value.get("end")))
    year, month = value.get("years"), value.get("months")
    return ((year is None or type(year) is int and 3 <= year <= 15)
            and (month is None or type(month) is int and 0 <= month <= 11))


def _restorable(summary, record_type):
    if not summary:
        return False
    for key in ("analysis_meta", "need_analysis"):
        if key in summary and not isinstance(summary[key], dict):
            return False
    if record_type == "Build a Solution":
        brief = _object(summary.get("opportunity_brief"))
        return bool(summary.get("kind") == "product_concept" and parse_age_range(brief.get("age_range"))
                    and isinstance(summary.get("solution"), dict))
    if record_type == "Market Research":
        filters = _object(summary.get("filters"))
        return bool(summary.get("kind") == "market_research" and parse_age_range(filters.get("age_range"))
                    and filters.get("region") in REGIONS and filters.get("time_window") in TIME_WINDOWS
                    and _valid_choices(filters.get("skills"), SKILLS_PROFESSIONAL)
                    and _valid_choices(filters.get("contexts"), CONTEXTS)
                    and _valid_choices(filters.get("audiences"), AUDIENCES)
                    and isinstance(summary.get("signals"), list))
    parent = summary.get("user_type") == "parent"
    student = summary.get("user_type") == "student"
    entries = ("student_specific",) if student else ("parent_specific", "parent_overview") if parent else ("professional",)
    skill_choices = _STUDENT_SKILLS if student else _PARENT_SKILLS if parent else SKILLS_PROFESSIONAL
    return bool(record_type == "Solve a Need" and summary.get("user_type") in ("parent", "student", "professional")
                and summary.get("entry_type") in entries
                and _valid_restore_age(summary.get("age"))
                and _valid_choices(summary.get("skills"), skill_choices)
                and _valid_choices(summary.get("contexts"), CONTEXTS)
                and _valid_choices(summary.get("methods"), PARENT_LEARNING_METHODS)
                and _valid_choices(summary.get("carriers"), CARRIERS))


def session_metadata(session):
    """Filtered read-only library view; the original saved JSON is not overwritten."""
    parsed = parse_summary(session.get("summary_json"))
    summary = parsed or {}
    record_type = _record_type(session, summary)
    title = _text(session.get("title"), 180) or "未命名研究"
    need = _object(summary.get("need_analysis"))
    region = _text(summary.get("region")) or UNSPECIFIED
    if record_type == "Build a Solution":
        scope = _object(summary.get("opportunity_brief"))
        concept = _object(_object(summary.get("solution")).get("product_concept"))
        title = _text(concept.get("name"), 180) or title
        ages = parse_age_range(scope.get("age_range"))
        skills, contexts = scope.get("skills"), scope.get("contexts")
        region = _text(scope.get("region")) or UNSPECIFIED
        excerpt = _text(concept.get("value_proposition") or scope.get("core_need"))
    elif record_type == "Market Research":
        scope = _object(summary.get("filters"))
        ages = parse_age_range(scope.get("age_range"))
        skills, contexts = scope.get("skills"), scope.get("contexts")
        region = _text(scope.get("region")) or region
        signals = summary.get("signals") if isinstance(summary.get("signals"), list) else []
        names = [_text(item.get("signal_title"), 80) for item in signals[:2] if isinstance(item, dict)]
        excerpt = _text("；".join(name for name in names if name)) or "尚未形成有依据的需求信号"
    else:
        current = _object(need.get("user_need")) if summary.get("user_type") == "professional" else {}
        ages = parse_age_range(current.get("age")) or parse_age_range(summary.get("age"))
        skills = current.get("core_skills") or need.get("primary_skills") or summary.get("skills")
        contexts = current.get("contexts") or need.get("contexts") or summary.get("contexts")
        region = _text(current.get("region")) or region
        excerpt = _text(current.get("pain_point") or need.get("problem_summary") or summary.get("problem")
                        or summary.get("background") or summary.get("pain_point"))
    return {"id": session.get("id"), "type": record_type, "title": title,
            "created_at": _text(session.get("created_at")), "age_range": ages, "age": age_label(ages),
            "skills": _labels(skills, SKILLS_PROFESSIONAL, {**_PARENT_SKILLS, **_STUDENT_SKILLS}),
            "contexts": _labels(contexts, CONTEXTS), "region": region,
            "excerpt": excerpt, "summary": parsed, "readable": _restorable(parsed, record_type)}


def filter_records(records, record_type=ALL_TYPES, skill=ALL_SKILLS, age=ALL_AGES, region=ALL_REGIONS):
    bands = {label: (start, end) for label, start, end in AGE_BANDS}
    matches = []
    for item in records:
        if record_type != ALL_TYPES and item["type"] != record_type:
            continue
        if skill != ALL_SKILLS and skill not in item["skills"]:
            continue
        if region != ALL_REGIONS and item["region"] != region:
            continue
        if age != ALL_AGES:
            ages, band = item.get("age_range"), bands.get(age)
            if not ages or not band or ages[1] < band[0] or ages[0] > band[1]:
                continue
        matches.append(item)
    return matches
