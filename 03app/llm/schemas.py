"""EngEduScope｜结构化输出校验与规范化（M3）。

不依赖自由文本解析：前端只消费这里校验过的字典。
- 必填键缺失 / 类型不对 / 路径条数不足 → LLMSchemaError（由调用方决定重试或提示）
- 能力 / 场景 / 载体标签规范化回正式 Taxonomy（同义词、去空格），无法映射的丢弃
- 低 / 中 / 高、匹配度 等枚举做兼容映射（含英文）
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from llm.prompts import LEVELS, MECHANISMS, SUITABILITY
from llm.provider import LLMSchemaError
from taxonomy import CARRIERS, CONTEXTS, SKILLS_PROFESSIONAL
from need_practice import validate_practice_plan
from output_safety import sanitize_data

_SKILL_SYNONYMS = {
    "口语": "口语表达", "口语输出": "口语表达", "说": "口语表达", "speaking": "口语表达", "表达": "口语表达",
    "阅读": "阅读理解", "读": "阅读理解", "reading": "阅读理解", "分级阅读": "阅读理解",
    "听力": "听力理解", "听": "听力理解", "listening": "听力理解",
    "语音辨识": "听力解码", "音素意识": "听力解码", "语音意识": "听力解码", "decoding": "听力解码",
    "写作": "写作表达", "写": "写作表达", "writing": "写作表达",
    "拼写": "单词拼写", "spelling": "单词拼写",
    "词汇": "词汇量扩展", "词汇量": "词汇量扩展", "单词": "词汇量扩展", "vocabulary": "词汇量扩展", "词汇调用": "词汇量扩展",
    "拼读": "自然拼读", "phonics": "自然拼读",
    "语法": "语法知识", "grammar": "语法知识",
    "跨学科": "跨学科素养", "学科英语": "跨学科素养", "clil": "跨学科素养",
}
_CONTEXT_SYNONYMS = {
    "课堂": "正式课堂", "学校课堂": "正式课堂", "家庭学习": "家庭固定学习", "家庭": "家庭固定学习", "在家": "家庭固定学习",
    "碎片化": "碎片时间", "亲子": "亲子共学", "亲子互动": "亲子共学", "自学": "自主学习", "真实生活": "真实生活使用",
    "生活场景": "真实生活使用", "日常生活": "真实生活使用", "旅行": "出行", "睡前阅读": "睡前", "社交": "社交互动",
    "同伴互动": "社交互动", "校内衔接": "学校课程衔接", "课程衔接": "学校课程衔接",
}
_CARRIER_SYNONYMS = {
    "app": "App / 网页", "应用": "App / 网页", "网页": "App / 网页", "小程序": "App / 网页", "学习机": "Pad / 学习机",
    "平板": "Pad / 学习机", "pad": "Pad / 学习机", "点读笔": "点读笔 / 听力机", "听力机": "点读笔 / 听力机",
    "机器人": "AI 玩具 / 机器人", "ai玩具": "AI 玩具 / 机器人", "智能玩具": "AI 玩具 / 机器人", "绘本": "纸质书", "书": "纸质书",
    "外教": "真人线上教师", "线上老师": "真人线上教师", "在线教师": "真人线上教师", "线下老师": "真人线下教师",
    "机构": "真人线下教师", "培训机构": "真人线下教师", "家长": "家长陪伴", "omo": "混合 OMO", "混合": "混合 OMO",
}
_LEVEL_MAP = {"low": "低", "medium": "中", "mid": "中", "high": "高", "较低": "低", "较高": "高", "中等": "中"}
_SUIT_MAP = {"high": "高", "medium": "中", "mid": "中", "low": "需进一步确认", "uncertain": "需进一步确认",
             "需确认": "需进一步确认", "待确认": "需进一步确认", "较高": "高", "中等": "中"}
_MECHANISM_SYNONYMS = {
    "ai 口语": "AI口语", "ai口语陪练": "AI口语", "ai对话": "AI口语", "在线课程": "系统课程", "系统课": "系统课程",
    "课程": "系统课程", "绘本": "分级阅读", "阅读": "分级阅读", "外教": "真人教师", "教师": "真人教师", "老师": "真人教师",
    "硬件": "智能硬件", "学习机": "智能硬件", "点读笔": "智能硬件", "家庭": "家庭活动", "亲子": "家庭活动",
}

_WS_RE = re.compile(r"\s+")


def _norm_key(text: str) -> str:
    return _WS_RE.sub("", str(text or "")).lower()


def _normalize_label(value: Any, official: List[str], synonyms: Dict[str, str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    key = _norm_key(value)
    if not key:
        return None
    by_norm = {_norm_key(o): o for o in official}
    if key in by_norm:
        return by_norm[key]
    if key in synonyms:
        return synonyms[key]
    for o in official:                       # 「阅读理解能力」→ 阅读理解
        if _norm_key(o) in key:
            return o
    for syn, target in synonyms.items():
        if syn and syn in key:
            return target
    return None


def normalize_labels(values: Any, official: List[str], synonyms: Dict[str, str], limit: Optional[int] = None) -> List[str]:
    if isinstance(values, str):
        values = [values] if values in official else re.split(r"[,，、;]", values)
    elif values is None:
        values = []
    elif not isinstance(values, (list, tuple)):
        raise LLMSchemaError("taxonomy labels must be a list or string")
    out: List[str] = []
    for v in values or []:
        label = _normalize_label(v, official, synonyms)
        if label and label not in out:
            out.append(label)
    return out[:limit] if limit else out


def normalize_skills(values: Any, limit: Optional[int] = None) -> List[str]:
    return normalize_labels(values, SKILLS_PROFESSIONAL, _SKILL_SYNONYMS, limit)


def normalize_contexts(values: Any, limit: Optional[int] = None) -> List[str]:
    return normalize_labels(values, CONTEXTS, _CONTEXT_SYNONYMS, limit)


def normalize_carriers(values: Any, limit: Optional[int] = None) -> List[str]:
    return normalize_labels(values, CARRIERS, _CARRIER_SYNONYMS, limit)


def _level(value: Any) -> str:
    text = _text(value)
    if text in LEVELS:
        return text
    if text.lower() in _LEVEL_MAP:
        return _LEVEL_MAP[text.lower()]
    raise LLMSchemaError("cost and involvement must be 低 / 中 / 高")


def _suitability(value: Any) -> str:
    text = _text(value)
    if text in SUITABILITY:
        return text
    return _SUIT_MAP.get(text.lower(), "需进一步确认")


def _mechanism(value: Any) -> str:
    text = str(value or "").strip()
    if text in MECHANISMS:
        return text
    key = _norm_key(text)
    for m in MECHANISMS:
        if _norm_key(m) in key:
            return m
    for syn, target in _MECHANISM_SYNONYMS.items():
        if syn in key:
            return target
    return "其他"


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise LLMSchemaError("text field must be a string")
    return value.strip()


def _str_list(value: Any, limit: Optional[int] = None) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [p.strip() for p in re.split(r"\n|；|;", value) if p.strip()]
    elif isinstance(value, (list, tuple)):
        items = [_text(v) for v in value]
    else:
        raise LLMSchemaError("text list must be an array or string")
    items = [i for i in items if i]
    return items[:limit] if limit else items


def _evidence_ids(value: Any, valid: set) -> List[str]:
    ids = []
    for v in _str_list(value):
        for token in re.findall(r"E\d+", str(v), flags=re.I):
            token = token.upper()
            if token in valid and token not in ids:
                ids.append(token)
    return ids


def _require(data: dict, keys: List[str], where: str) -> None:
    if not isinstance(data, dict):
        raise LLMSchemaError(f"{where} must be an object")
    missing = [k for k in keys if k not in data]
    if missing:
        raise LLMSchemaError(f"{where} missing keys: {missing}")


def _array(value: Any, where: str, minimum: int = 0, maximum: Optional[int] = None) -> list:
    if not isinstance(value, list):
        raise LLMSchemaError(f"{where} must be an array")
    if len(value) < minimum or (maximum is not None and len(value) > maximum):
        raise LLMSchemaError(f"{where} has an invalid item count")
    return value


def _filled(value: Any, where: str) -> str:
    text = _text(value)
    if not text:
        raise LLMSchemaError(f"{where} must not be empty")
    return text


def _items(value: Any, where: str, minimum: int = 1, maximum: Optional[int] = None) -> list:
    items = _str_list(value)
    if len(items) < minimum or (maximum is not None and len(items) > maximum):
        raise LLMSchemaError(f"{where} has an invalid item count")
    return items


def _labels(value: Any, normalizer, where: str, limit: int) -> list:
    labels = normalizer(value, limit=limit)
    if not labels:
        raise LLMSchemaError(f"{where} must include a taxonomy label")
    return labels


def _grounded_examples(value: Any, valid: set, note_key: str, where: str) -> list:
    examples = []
    for item in _array(value, where, maximum=4):
        _require(item, ["name", note_key, "evidence_ids"], where)
        ids = _evidence_ids(item["evidence_ids"], valid)
        # An unknown/missing source must never become an apparently grounded brand recommendation.
        if not ids:
            raise LLMSchemaError(f"{where} needs a provided evidence id")
        examples.append({"name": _filled(item["name"], where),
                         note_key: _filled(item[note_key], where), "evidence_ids": ids})
    return examples


# ── 家长 ──────────────────────────────────────────────────────────────────
def validate_parent(data: Any, evidence_ids: List[str]) -> dict:
    data = sanitize_data(data)
    _require(data, ["problem_summary", "primary_skills", "secondary_skills", "skills_explanation",
                    "contexts", "possible_causes", "priority", "evidence_needed", "solution_routes",
                    "next_steps", "evidence_ids"], "parent result")
    valid = set(_str_list(evidence_ids))
    primary = _labels(data["primary_skills"], normalize_skills, "primary_skills", 2)
    secondary = [s for s in normalize_skills(data["secondary_skills"], limit=3) if s not in primary]
    causes = []
    for item in _array(data["possible_causes"], "possible_causes", 2, 4):
        _require(item, ["cause", "why"], "possible cause")
        causes.append({"cause": _filled(item["cause"], "cause"), "why": _filled(item["why"], "cause.why")})

    priority_raw = data["priority"]
    _require(priority_raw, ["focus_now", "observe_later"], "priority")
    priority = {k: _items(priority_raw[k], f"priority.{k}", 1, 2) for k in ("focus_now", "observe_later")}
    routes = []
    route_fields = ["route_name", "mechanism", "why_it_fits", "recommended_actions", "time_cost", "money_cost",
                    "parent_involvement", "suitability", "suitable_for", "limitations", "existing_options",
                    "teacher_profile", "evidence_ids"]
    families = set()
    for raw in _array(data["solution_routes"], "solution_routes", 3, 3):
        _require(raw, route_fields, "solution route")
        route = {k: _filled(raw[k], f"route.{k}") for k in
                 ("route_name", "mechanism", "why_it_fits", "suitable_for", "limitations")}
        mechanism = route["mechanism"]
        family = {"AI产品": "数字产品", "AI口语": "数字产品", "家庭活动": "家庭方案",
                  "真人教师": "真人支持"}.get(mechanism, mechanism)
        if family in families:
            raise LLMSchemaError("solution routes need three distinct mechanisms")
        families.add(family)
        route.update({k: _level(raw[k]) for k in ("time_cost", "money_cost", "parent_involvement")})
        route["recommended_actions"] = _items(raw["recommended_actions"], "route.recommended_actions", 1, 5)
        route["suitability"] = _suitability(raw["suitability"])
        route["existing_options"] = _grounded_examples(raw["existing_options"], valid, "why_match", "existing_options")
        route["teacher_profile"] = _text(raw["teacher_profile"])
        if any(word in mechanism for word in ("真人", "教师", "老师")) and not route["teacher_profile"]:
            raise LLMSchemaError("teacher route must describe the suitable teacher and why")
        route["evidence_ids"] = _evidence_ids(raw["evidence_ids"], valid)
        routes.append(route)
    if len({r["route_name"] for r in routes}) != 3:
        raise LLMSchemaError("solution route names must differ")

    # The orchestrator supplies a safe skill-specific fallback when this optional block is empty.
    # A copyable prompt alone is the supported minimum activity.
    diy = data.get("ai_diy", {})
    _require(diy, [], "ai_diy")
    ai_diy = {k: _text(diy.get(k)) for k in ("title", "duration", "copyable_prompt", "scaffold_reduction")}
    ai_diy["steps"] = _items(diy.get("steps", []), "ai_diy.steps", 0, 6)
    result = {
        "problem_summary": _filled(data["problem_summary"], "problem_summary"),
        "primary_skills": primary, "secondary_skills": secondary,
        "skills_explanation": _filled(data["skills_explanation"], "skills_explanation"),
        "contexts": _labels(data["contexts"], normalize_contexts, "contexts", 3),
        "possible_causes": causes, "priority": priority,
        "evidence_needed": _items(data["evidence_needed"], "evidence_needed", 1, 3),
        "solution_routes": routes, "ai_diy": ai_diy,
        "next_steps": _items(data["next_steps"], "next_steps", 1, 4),
        "evidence_ids": _evidence_ids(data["evidence_ids"], valid),
    }
    if data.get("practice_plan") is not None:
        result["practice_plan"] = validate_practice_plan(data["practice_plan"])
    if data.get("need_reasoning") is not None:
        reasoning = data["need_reasoning"]
        _require(reasoning, ["reported_facts", "hypotheses", "to_confirm"], "need_reasoning")
        hypotheses = []
        for item in _array(reasoning["hypotheses"], "need_reasoning.hypotheses", 1, 4):
            _require(item, ["cause", "check", "if_observed"], "hypothesis")
            hypotheses.append({key: _filled(item[key], f"hypothesis.{key}") for key in ("cause", "check", "if_observed")})
        result["need_reasoning"] = {"reported_facts": _items(reasoning["reported_facts"], "reported_facts", 1, 3),
                                    "hypotheses": hypotheses, "to_confirm": _items(reasoning["to_confirm"], "to_confirm", 1, 3)}
    return sanitize_data(result)


def validate_student(data: Any, evidence_ids: List[str]) -> dict:
    data = sanitize_data(data)
    _require(data, ["practice_plan", "primary_skills", "contexts", "evidence_ids"], "student result")
    return {"practice_plan": validate_practice_plan(data["practice_plan"]),
            "primary_skills": _labels(data["primary_skills"], normalize_skills, "primary_skills", 2),
            "contexts": _labels(data["contexts"], normalize_contexts, "contexts", 3),
            "evidence_ids": _evidence_ids(data["evidence_ids"], set(_str_list(evidence_ids)))}


# ── 教育工作者 ────────────────────────────────────────────────────────────
def validate_educator(data: Any, evidence_ids: List[str]) -> dict:
    _require(data, ["user_need", "teaching_goal", "solution_landscape", "gap", "product_direction",
                    "mvp_spec", "validation_metrics", "evidence_ids"], "educator result")
    valid = set(_str_list(evidence_ids))
    need = data["user_need"]
    _require(need, ["target_user", "age", "core_skills", "contexts", "pain_point"], "user_need")
    user_need = {k: _filled(need[k], f"user_need.{k}") for k in ("target_user", "age", "pain_point")}
    user_need["core_skills"] = _labels(need["core_skills"], normalize_skills, "core_skills", 3)
    user_need["contexts"] = _labels(need["contexts"], normalize_contexts, "contexts", 3)

    landscape = []
    for item in _array(data["solution_landscape"], "solution_landscape", 1, 7):
        _require(item, ["mechanism", "summary", "examples", "evidence_ids"], "landscape item")
        landscape.append({
            "mechanism": _mechanism(_filled(item["mechanism"], "landscape.mechanism")),
            "summary": _filled(item["summary"], "landscape.summary"),
            "examples": _grounded_examples(item["examples"], valid, "note", "landscape.examples"),
            "evidence_ids": _evidence_ids(item["evidence_ids"], valid),
        })
    direction = data["product_direction"]
    _require(direction, ["solution_mechanism", "carrier", "core_scenario", "ai_role", "human_role"], "product_direction")
    product_direction = {k: _filled(direction[k], f"product_direction.{k}") for k in
                         ("solution_mechanism", "ai_role", "human_role")}
    product_direction["carrier"] = _labels(direction["carrier"], normalize_carriers, "carrier", 2)
    product_direction["core_scenario"] = _labels(direction["core_scenario"], normalize_contexts, "core_scenario", 2)

    mvp = data["mvp_spec"]
    mvp_fields = ["core_features", "key_pages", "min_data", "min_ai_capability", "not_now"]
    _require(mvp, mvp_fields, "mvp_spec")
    mvp_spec = {k: _items(mvp[k], f"mvp_spec.{k}", 3 if k == "core_features" else 1,
                         5 if k == "core_features" else 8) for k in mvp_fields}
    metrics = data["validation_metrics"]
    _require(metrics, ["learning", "behavior", "product"], "validation_metrics")
    validation_metrics = {k: _items(metrics[k], f"validation_metrics.{k}", 1, 3) for k in
                          ("learning", "behavior", "product")}
    return {
        "user_need": user_need,
        "teaching_goal": _filled(data["teaching_goal"], "teaching_goal"),
        "solution_landscape": landscape,
        "gap": _items(data["gap"], "gap", 2, 4),
        "product_direction": product_direction,
        "mvp_spec": mvp_spec, "validation_metrics": validation_metrics,
        "evidence_ids": _evidence_ids(data["evidence_ids"], valid),
    }
