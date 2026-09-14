"""M5 pure adapters: preserve M3/M4 evidence and turn snapshots into an editable brief.

No retrieval, LLM, database or network calls occur here. Original snapshots remain
in source_context; normalized fields are a proposal scope for the user to confirm.
"""

from __future__ import annotations

from copy import deepcopy
import re
from urllib.parse import urlsplit, urlunsplit

from llm.schemas import normalize_carriers, normalize_contexts, normalize_skills
from taxonomy import REGIONS

SOURCE_TYPES = ("solve_need", "market_insight", "scratch")


class SolutionContextError(ValueError):
    def __init__(self, user_message):
        self.user_message = user_message
        super().__init__(user_message)


def _text(value, limit=6000):
    if isinstance(value, str):
        return value.strip()[:limit]
    if isinstance(value, (list, tuple)):
        return "；".join(_text(item, limit) for item in value if isinstance(item, str))[:limit]
    return ""


def _labels(normalizer, value):
    if not isinstance(value, (str, list, tuple)):
        return []
    return normalizer(value)


def _string_list(value, label):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise SolutionContextError(f"{label}需要使用文字列表。")
    return list(dict.fromkeys(item.strip()[:6000] for item in value if item.strip()))


def _month(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("age_months"), int):
            return value["age_months"]
        if isinstance(value.get("years"), int):
            return value["years"] * 12 + int(value.get("months", 0))
    return None


def _age_range(value):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [_month(value[0]), _month(value[1])]
    if isinstance(value, dict):
        if value.get("mode") == "range" or "start" in value:
            return [_month(value.get("start")), _month(value.get("end"))]
        months = _month(value)
        if months is not None:
            return [months, months]
        return _age_range(value.get("display"))
    if isinstance(value, str):
        # M3 age_text and model revisions: 7岁4个月, 6岁0个月 – 8岁11个月,
        # or an inclusive whole-year audience range such as 10–12岁.
        parts = re.split(r"\s*[-–—~～至到]\s*", value.strip())
        ages = []
        for part in parts[:2]:
            match = re.search(r"(\d{1,2})\s*(?:岁|years?|yrs?)?(?:\s*(\d{1,2})\s*(?:个?月|months?))?", part, re.I)
            if not match:
                return None
            year = int(match.group(1))
            month = int(match.group(2)) if match.group(2) is not None else None
            if month is not None and month > 11:
                return None
            ages.append((year * 12 + (month or 0), month is not None))
        if len(ages) == 2:
            return [ages[0][0], ages[1][0] + (0 if ages[1][1] else 11)]
        if ages:
            return [ages[0][0], ages[0][0]]
    return None


def _evidence(values):
    if values is None:
        return []
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise SolutionContextError("参考依据格式异常，请返回原研究检查来源。")
    output, originals = [], {}
    used_ids = {str(item.get("id")) for item in values if item.get("id") is not None}
    for raw in values:
        item = deepcopy(raw)
        identifier = str(item.get("id") or "").strip()
        if not identifier:
            counter = 1
            while f"S{counter}" in used_ids:
                counter += 1
            identifier = f"S{counter}"
            used_ids.add(identifier)
        if identifier in originals:
            if originals[identifier] != raw:
                raise SolutionContextError("参考依据存在冲突的重复编号，请返回原研究检查来源。")
            continue
        originals[identifier] = raw
        item["id"] = identifier
        item["title"] = _text(item.get("title"), 300) or "未命名来源"
        item["content"] = _text(item.get("content") or item.get("text"), 16000)
        url = _text(item.get("url") or item.get("source_url"), 2048)
        try:
            parts = urlsplit(url)
            item["url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "")) if (
                parts.scheme in ("http", "https") and parts.hostname and not parts.username and not parts.password
            ) else ""
        except ValueError:
            item["url"] = ""
        output.append(item)
    return output


def normalize_brief(brief):
    """Return validated canonical scope, retaining inherited source_type and context."""
    if not isinstance(brief, dict):
        raise SolutionContextError("构建上下文无法读取，请重新选择需求或填写构建目标。")
    source = brief.get("source_type")
    if source not in SOURCE_TYPES:
        raise SolutionContextError("构建来源无效，请从需求分析、市场洞察或直接构建入口开始。")
    target = _text(brief.get("target_user"), 500)
    core = _text(brief.get("core_need"))
    if not target or not core:
        raise SolutionContextError("请填写目标用户与核心需求。")
    age = brief.get("age_range")
    if (not isinstance(age, (list, tuple)) or len(age) != 2
            or any(not isinstance(months, int) or isinstance(months, bool) for months in age)
            or not 36 <= age[0] <= age[1] <= 191):
        raise SolutionContextError("年龄范围需要在 3岁0个月至15岁11个月之间，且起始年龄不能晚于结束年龄。")
    source_context = deepcopy(brief.get("source_context") or {})
    if not isinstance(source_context, dict):
        raise SolutionContextError("原研究上下文格式异常，请重新进入构建页面。")
    notes = list(source_context.get("adaptation_notes") or [])
    skills = _labels(normalize_skills, brief.get("skills"))
    contexts = _labels(normalize_contexts, brief.get("contexts"))
    if source == "scratch" and (not skills or not contexts):
        raise SolutionContextError("请至少选择一项英语能力与一个学习场景。")
    if not skills:
        skills = _labels(normalize_skills, core) or ["听力理解", "口语表达", "阅读理解", "写作表达"]
        notes.append("上游未明确英语能力，当前范围按需求文字或听说读写暂填，请在构建前确认。")
    if not contexts:
        contexts = _labels(normalize_contexts, core) or ["家庭固定学习"]
        notes.append("上游未明确学习场景，当前按需求文字或家庭固定学习暂填，请在构建前确认。")
    if notes:
        source_context["adaptation_notes"] = list(dict.fromkeys(notes))
    region = brief.get("region") or "中国大陆"
    if region not in REGIONS:
        raise SolutionContextError("请选择中国大陆或海外 Benchmark，避免混合不同市场范围。")
    landscape = brief.get("existing_landscape") or []
    if not isinstance(landscape, list):
        raise SolutionContextError("已有方案资料格式异常，请返回原研究检查。")
    return {
        "source_type": source, "target_user": target, "age_range": list(age),
        "skills": skills, "contexts": contexts, "region": region, "core_need": core,
        "pain_point": _text(brief.get("pain_point")) or core,
        "existing_landscape": deepcopy(landscape), "gap": _text(brief.get("gap")),
        "evidence_sources": _evidence(brief.get("evidence_sources") or []),
        "source_context": source_context,
        "preferred_carriers": _labels(normalize_carriers, brief.get("preferred_carriers")),
        "constraints": _string_list(brief.get("constraints"), "构建约束"),
        "scope_notes": _string_list(brief.get("scope_notes"), "范围说明"),
    }


def from_need(result):
    if not isinstance(result, dict) or not isinstance(result.get("need_analysis"), dict):
        raise SolutionContextError("请先完成需求分析，再进入 Build a Solution。")
    original = deepcopy(result)
    need = result["need_analysis"]
    professional = result.get("user_type") == "professional"
    user_need = need.get("user_need") or {}
    direction = result.get("product_direction") or {}
    original_input = {key: deepcopy(value) for key, value in result.items() if key in (
        "user_type", "entry_type", "age", "skills", "contexts", "carriers", "problem", "background",
        "pain_point", "methods", "methods_note",
    )}
    age = _age_range(user_need.get("age")) if professional and user_need.get("age") else None
    age = age or _age_range(result.get("age")) or [36, 191]
    if professional:
        core = _text(user_need.get("pain_point")) or _text(result.get("pain_point"))
        skills = user_need.get("core_skills") or result.get("skills")
        contexts = user_need.get("contexts") or result.get("contexts")
        target = _text(user_need.get("target_user")) or "目标英语学习者与教育工作者"
        landscape = need.get("solution_landscape") or []
        gap = need.get("gap") or ""
    else:
        core = _text(need.get("problem_summary")) or _text(result.get("problem") or result.get("background"))
        skills = list(need.get("primary_skills") or []) + list(need.get("secondary_skills") or [])
        skills = skills or result.get("skills")
        contexts = need.get("contexts") or result.get("contexts")
        target = "有此英语学习需求的孩子及其家长"
        landscape = result.get("solution_routes") or []
        gap = need.get("gap") or ""
    return normalize_brief({
        "source_type": "solve_need", "target_user": target, "age_range": age,
        "skills": skills, "contexts": contexts, "region": result.get("region") or "中国大陆",
        "core_need": core, "pain_point": _text(user_need.get("pain_point")) or core,
        "existing_landscape": landscape, "gap": gap,
        "preferred_carriers": direction.get("carrier") or result.get("carriers") or [],
        "evidence_sources": result.get("evidence_sources") or [],
        "source_context": {"need_result": original, "original_input": original_input,
                           "analysis_meta": deepcopy(result.get("analysis_meta") or {}),
                           "interpretation": {key: deepcopy(need[key]) for key in (
                               "problem_summary", "skills_explanation", "possible_causes", "priority", "teaching_goal"
                           ) if key in need},
                           "comparison_note": "不同地域的参考资料保留原地域；海外机制不能直接推定中国大陆的需求或效果。"},
    })


def from_market(research, signal=None):
    if not isinstance(research, dict):
        raise SolutionContextError("市场研究无法读取，请重新选择洞察。")
    opportunity = research.get("opportunity_context") or {}
    selected = opportunity.get("insight") or signal or next(iter(research.get("signals") or []), None)
    if not isinstance(selected, dict):
        raise SolutionContextError("请先选择一条市场需求洞察，再进入 Build a Solution。")
    filters = opportunity.get("filters") or research.get("filters") or {}
    evidence = opportunity.get("evidence_sources") or selected.get("evidence_sources") or research.get("evidence_sources") or []
    signal_id = str(selected.get("id") or opportunity.get("signal_id") or "")
    chat = opportunity.get("chat") if "chat" in opportunity else (research.get("chat") or {}).get(signal_id, [])
    core = _text(selected.get("unmet_need")) or _text(selected.get("problem_summary")) or _text(selected.get("signal_title"))
    region = selected.get("region") or filters.get("region") or research.get("region") or "中国大陆"
    landscape = selected.get("existing_landscape") or selected.get("existing_solutions") or []
    age = _age_range(selected.get("age_range")) or _age_range(filters.get("age_range")) or [36, 191]
    audiences = selected.get("audiences") or filters.get("audiences") or []
    def age_label(months):
        return f"{months // 12}岁{months % 12}个月" if isinstance(months, int) else "年龄待确认"
    age_scope = age_label(age[0]) if age[0] == age[1] else f"{age_label(age[0])}–{age_label(age[1])}"
    target = _text(selected.get("target_user")) or f"{age_scope}英语学习者"
    if not selected.get("target_user") and audiences:
        target += f"；相关人群：{_text(audiences)}"
    return normalize_brief({
        "source_type": "market_insight",
        "target_user": target,
        "age_range": age,
        "skills": selected.get("skills") or filters.get("skills") or [],
        "contexts": selected.get("contexts") or filters.get("contexts") or [],
        "region": region, "core_need": core, "pain_point": selected.get("problem_summary") or core,
        "existing_landscape": landscape, "gap": selected.get("unmet_need") or "",
        "evidence_sources": evidence, "preferred_carriers": selected.get("preferred_carriers") or [],
        "source_context": {
            "market_research": deepcopy(research), "opportunity_context": deepcopy(opportunity),
            "insight": deepcopy(selected), "signal_id": signal_id, "filters": deepcopy(filters),
            "region": region, "unmet_need": selected.get("unmet_need") or "",
            "audiences": deepcopy(audiences),
            "existing_landscape": deepcopy(landscape), "analyst": deepcopy(selected.get("analyst") or {}),
            "analysis_meta": deepcopy(research.get("analysis_meta") or {}),
            "chat": deepcopy(chat), "china_observation": selected.get("china_observation") or "",
            "overseas_observation": selected.get("overseas_observation") or "",
            "comparison_note": "中国大陆与海外 Benchmark 保持分开；海外方案仅作为机制对照，适配性仍需验证。",
        },
    })


def from_scratch(data):
    if not isinstance(data, dict):
        raise SolutionContextError("请填写目标用户、年龄、能力、场景与核心需求。")
    copied = deepcopy(data)
    copied["source_type"] = "scratch"
    copied["age_range"] = _age_range(data.get("age_range") or data.get("age"))
    copied.setdefault("source_context", {"original_input": deepcopy(data)})
    return normalize_brief(copied)
