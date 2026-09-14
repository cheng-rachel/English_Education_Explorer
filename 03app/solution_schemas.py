"""M5 structured product concept boundary; no new schema dependency."""
from llm.provider import LLMSchemaError
from llm.schemas import normalize_carriers
from solution_prompts import MECHANISMS
from solution_grounding import friction_refs, ground_gap, supported_landscape

SOLUTION_SCOPES = {"activity", "prompt_tool", "lightweight_app", "full_product", "service", "hybrid"}


def _obj(value, where):
    if not isinstance(value, dict):
        raise LLMSchemaError(f"{where} must be an object")
    return value


def _text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise LLMSchemaError(f"{where} must be nonempty text")
    return value.strip()


def _texts(value, where, minimum=1, maximum=12):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise LLMSchemaError(f"{where} has invalid items/count")
    return [_text(item, where) for item in value]


def _fields(value, fields, where):
    value = _obj(value, where)
    return {key: _text(value.get(key), where + "." + key) for key in fields}


def _rows(value, fields, where, minimum=1, maximum=8):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise LLMSchemaError(f"{where} has invalid items/count")
    return [_fields(item, fields, where) for item in value]


def _refs(value, valid):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise LLMSchemaError("evidence_ids must be a string array")
    return list(dict.fromkeys(item for item in value if item in valid))


def validate_solution(data, evidence, brief=None):
    data = _obj(data, "solution")
    valid = {item["id"] for item in evidence}
    result = {"teaching_goal": _fields(data.get("teaching_goal"), ("learning_outcome", "behavior_change"), "teaching_goal"),
              "opportunity_gap": _fields(data.get("opportunity_gap"), ("existing_strength", "remaining_friction", "opportunity"), "opportunity_gap"),
              "product_concept": _fields(data.get("product_concept"), ("name", "value_proposition", "target_user", "core_problem", "core_mechanism", "core_scenario"), "product_concept"),
              "ai_role": _texts(data.get("ai_role"), "ai_role", maximum=6),
              "human_role": _texts(data.get("human_role"), "human_role", maximum=6),
              "fast_prototype": _fields(data.get("fast_prototype"), ("approach", "copyable_prompt"), "fast_prototype"),
              "risks": _rows(data.get("risks"), ("risk", "cheap_test"), "risks", 3, 3),
              "evidence_ids": _refs(data.get("evidence_ids", []), valid)}
    scope = _text(data.get("solution_scope"), "solution_scope")
    if scope not in SOLUTION_SCOPES:
        raise LLMSchemaError("solution_scope must describe the smallest viable scope")
    result["solution_scope"] = scope
    judgment = _obj(data.get("product_judgment"), "product_judgment")
    result["product_judgment"] = {
        "recommendation": _text(judgment.get("recommendation"), "judgment.recommendation"),
        "reasons": _texts(judgment.get("reasons"), "judgment.reasons", 2, 4),
        "evidence_ids": _refs(judgment.get("evidence_ids", []), valid)}
    opportunity = _obj(data.get("opportunity"), "opportunity")
    result["opportunity"] = {
        "problem_to_solve": _text(opportunity.get("problem_to_solve"), "opportunity.problem_to_solve"),
        "reported_facts": _texts(opportunity.get("reported_facts"), "opportunity.reported_facts", 0, 4),
        "unknowns": _texts(opportunity.get("unknowns"), "opportunity.unknowns", 1, 4)}
    if brief is not None:
        # The model cannot convert upstream interpretations into observed learner facts.
        context = brief.get("source_context") or {}
        original = context.get("original_input") or {}
        supplied = original.get("problem") or brief.get("pain_point") or brief.get("core_need") or "需求仍待确认"
        label = "继承的需求线索（尚待实地核验）" if brief.get("source_type") == "market_insight" else "用户描述（尚未独立观察）"
        result["opportunity"]["reported_facts"] = [f"{label}：{supplied}"]
    result["core_interaction"] = _text(data.get("core_interaction"), "core_interaction")
    result["validation_decision"] = _fields(data.get("validation_decision"), ("continue", "adjust", "stop"), "validation_decision")
    landscape = data.get("solution_landscape")
    if not isinstance(landscape, list) or len(landscape) > 9:
        raise LLMSchemaError("solution_landscape must contain at most 9 supported mechanisms; empty is allowed")
    result["solution_landscape"] = []
    for row in landscape:
        item = _fields(row, ("mechanism", "what_exists", "what_remains_unresolved"), "solution_landscape")
        if item["mechanism"] not in MECHANISMS:
            item["mechanism"] = "其他"
        item["evidence_ids"] = _refs(row.get("evidence_ids", []), valid)
        result["solution_landscape"].append(item)
    result["solution_landscape"] = supported_landscape(result["solution_landscape"], evidence, (brief or {}).get("skills", ()))
    gap = dict(result["opportunity_gap"], status=data["opportunity_gap"].get("status", "hypothesis"),
               evidence_ids=_refs(data["opportunity_gap"].get("evidence_ids", []), valid))
    result["opportunity_gap"] = ground_gap(gap, evidence, result["solution_landscape"])
    if scope == "full_product":
        refs = friction_refs(result["product_judgment"]["evidence_ids"], evidence)
        sources = {s.get("url") or s.get("source_url") or s.get("original_path") or s.get("title")
                   for s in evidence if s.get("id") in refs}
        if len(sources - {None, ""}) < 2:
            raise LLMSchemaError("full_product needs independent observed need evidence; choose a smaller validation scope")
    mechanism = _obj(data.get("solution_mechanism"), "solution_mechanism")
    result["solution_mechanism"] = {"steps": _texts(mechanism.get("steps"), "mechanism.steps", 3, 8),
                                    "why_it_might_work": _text(mechanism.get("why_it_might_work"), "mechanism.why"),
                                    "assumptions": _texts(mechanism.get("assumptions"), "mechanism.assumptions", 1, 8)}
    carrier = _obj(data.get("carrier"), "carrier")
    choices = normalize_carriers(_texts(carrier.get("choices"), "carrier.choices", 1, 4))
    if not choices:
        raise LLMSchemaError("carrier must use existing taxonomy")
    result["carrier"] = {"choices": choices, "rationale": _text(carrier.get("rationale"), "carrier.rationale")}
    if scope == "service" and not any("教师" in choice for choice in choices):
        raise LLMSchemaError("service needs a human teaching carrier, not an app by default")
    if scope in ("activity", "prompt_tool", "lightweight_app") and any(
            choice in ("混合 OMO", "AI 玩具 / 机器人", "Pad / 学习机", "点读笔 / 听力机") for choice in choices):
        raise LLMSchemaError("lightweight validation must use existing materials or a simple tool, not dedicated hardware/OMO")
    mvp = _obj(data.get("mvp"), "mvp")
    result["mvp"] = {"core_features": _rows(mvp.get("core_features"), ("name", "why_essential"), "mvp.core_features", 1, 5),
                     "key_pages": _rows(mvp.get("key_pages"), ("name", "purpose"), "mvp.key_pages", 1, 5),
                     **{key: _texts(mvp.get(key), "mvp." + key, maximum=8) for key in ("minimal_data", "minimal_ai_capability", "not_now")}}
    raw_path = data.get("demo_build_path")
    path = _rows(raw_path, ("title", "action", "deliverable"), "demo_build_path", 5, 5)
    result["demo_build_path"] = []
    for i, (row, raw) in enumerate(zip(path, raw_path), 1):
        if type(raw.get("step")) is not int or raw["step"] != i:
            raise LLMSchemaError("Demo Build Path needs steps 1 through 5")
        result["demo_build_path"].append(dict(row, step=i))
    metrics = _obj(data.get("validation_metrics"), "validation_metrics")
    result["validation_metrics"] = {key: _fields(metrics.get(key), ("metric", "how_to_measure"), "metrics." + key)
                                    for key in ("learning", "behavior", "product")}
    plan = _obj(data.get("validation_plan"), "validation_plan")
    result["validation_plan"] = _fields(plan, ("sample", "duration", "comparison"), "validation_plan")
    result["validation_plan"]["decision_criteria"] = _texts(plan.get("decision_criteria"), "validation_plan.criteria", 1, 5)
    return result
