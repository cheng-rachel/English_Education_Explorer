"""Small M4 JSON boundary: grounded ids, regional scope and honest unknown trends."""
import re
from copy import deepcopy

from llm.provider import LLMSchemaError
from market_prompts import MECHANISMS
from taxonomy import AUDIENCES, CONTEXTS, DEMAND_LEVELS, SIGNAL_STATUSES, SKILLS_PROFESSIONAL, TRENDS
from output_safety import sanitize_data
from market_analyst_evidence import analyst_findings, interpretation_for_display
from market_learning_reference import apply_learning_background


def demand_sources(evidence):
    from market_quality import source_key
    from market_baseline import demand_support
    eligible_ids = set(demand_support(evidence)["evidence_ids"])
    sources = {}
    for ev in evidence:
        if ev.get("id") in eligible_ids:
            sources[source_key(ev)] = ev
    return list(sources.values())


def _comparable_demand(evidence):
    """Dates alone or multiple search hits do not create a comparable observation."""
    eligible = [ev for ev in demand_sources(evidence)
                if ev.get("time_scope") == "within_window"
                and ev.get("date_basis") not in ("provider_metadata", "provider_estimated_published_or_updated", "title_year")
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ev.get("normalized_date") or ev.get("date") or ""))
                and re.search(r"同一(?:样本|问卷|问题|口径)|相同(?:样本|问卷|口径)|追踪调查|same (?:cohort|sample|question)|longitudinal survey", ev.get("content", ""), re.I)]
    dates = {ev.get("normalized_date") or ev.get("date") for ev in eligible}
    return eligible if len(eligible) >= 2 and len(dates) >= 2 else []


def _baseline_for(filters, evidence, learning_references=()):
    from market_baseline import baseline_market
    signals = baseline_market(filters, evidence, learning_references).get("signals") or []
    if signals:
        return signals[0]
    focus = "、".join(filters.get("skills") or []) or "英语学习"
    judgment = "当前相关资料不足，尚不能确认真实用户需求或现有方案的使用效果。"
    return {"signal_title": f"{focus}：真实用户需求证据仍不足", "current_judgment": judgment,
            "signal_kind": "scope_observation", "problem_summary": judgment,
            "unmet_need": "尚不能确认未解决的问题，需要补充真实使用记录。",
            "opportunity_hypothesis": "先记录具体困难、已尝试的方式和使用后的表现。",
            "validation_questions": ["用户具体在哪一步遇到困难？", "尝试现有方案后，哪些问题仍然存在？"],
            "analyst": {"evidence": [], "interpretation": "资料不足，暂不作需求或效果判断。",
                        "hypothesis": "先补充与目标年龄和能力相关的真实使用记录。"}}


def text(value, required=True):
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise LLMSchemaError("market text field is missing or invalid")
    return value.strip()


def array(value):
    if not isinstance(value, list):
        raise LLMSchemaError("market array field is invalid")
    return value


def obj(value):
    if not isinstance(value, dict):
        raise LLMSchemaError("market object field is invalid")
    return value


def refs(value, valid):
    return list(dict.fromkeys(v for v in array(value or []) if isinstance(v, str) and v in valid))


def labels(value, allowed, fallback):
    found = [v for v in array(value or []) if isinstance(v, str) and v in allowed]
    return list(dict.fromkeys(found)) or list(fallback)


def statements(value, valid, field="statement"):
    output = []
    for item in array(value or [])[:8]:
        item = obj(item)
        ids = refs(item.get("evidence_ids"), valid)
        description = text(item.get(field))
        if ids:
            output.append({field: description, "evidence_ids": ids})
    return output


def validate_answer(data, evidence, insight=None, question=""):
    data, evidence = sanitize_data([data, evidence])
    if insight is not None and len(demand_sources(evidence)) < 2:
        from market_baseline import baseline_answer
        data = baseline_answer(sanitize_data(insight), evidence, question)
    data = obj(data)
    valid = {e["id"]: e for e in evidence}
    facts = analyst_findings(statements(data.get("evidence"), valid), evidence)
    limitations = [text(v) for v in array(data.get("limitations", []))[:6]]
    if not facts and "当前资料不足以确认" not in limitations:
        limitations.append("当前资料不足以确认")
    result = {"evidence": facts[:3], "interpretation": text(data.get("interpretation")),
            "hypothesis": text(data.get("hypothesis")),
            "limitations": limitations}
    references = (insight or {}).get("learning_references") or []
    if references:
        background = apply_learning_background(dict(insight, analyst=result), references, insight)
        result.update(learning_references=background["learning_references"], learning_background=background["learning_background"])
        if len(demand_sources(evidence)) < 2 and background["learning_background"]["skill_structure"]:
            result.update(interpretation=background["analyst"]["interpretation"], hypothesis=background["analyst"]["hypothesis"])
    result["interpretation"] = interpretation_for_display(result["interpretation"])
    return sanitize_data(result)


def validate_market(data, evidence, filters, learning_references=()):
    from market_quality import evidence_kind
    data, evidence = sanitize_data([data, evidence])
    data = obj(data)
    raw_signals = array(data.get("signals"))
    if len(raw_signals) > 3:
        raise LLMSchemaError("too many market signals")
    valid = {e["id"]: e for e in evidence if e.get("region") == filters["region"]
             and evidence_kind(e) != "learning"}
    discussions = {key: ev for key, ev in valid.items() if evidence_kind(ev) == "demand"}
    solution_sources = {key: ev for key, ev in valid.items() if evidence_kind(ev) in {"supply", "demand"}}
    supply = [ev for ev in valid.values() if evidence_kind(ev) == "supply"]
    signals = []
    for raw in raw_signals:
        raw = obj(raw)
        if raw.get("region") != filters["region"]:
            raise LLMSchemaError("market region must match requested scope")
        ids = refs(raw.get("evidence_ids"), valid)
        scoped_filters = dict(filters, skills=raw.get("skills") or filters["skills"])
        if not ids and supply:
            ids = _baseline_for(scoped_filters, supply).get("evidence_ids", [])
        if not ids and learning_references:
            # A background observation is valid, but has no Market Evidence and no trend.
            safe = _baseline_for(filters, [], learning_references)
            safe.update(evidence_ids=[], evidence_sources=[], trend=None, demand_level=None, signal_status=None,
                        trend_evidence_ids=[], demand_evidence_count=0, attempted_solutions=[], dissatisfaction=[])
            signals.append(apply_learning_background(safe, learning_references, filters))
            continue
        if not ids:
            raise LLMSchemaError("market signal has no valid supporting source")
        # Only this insight's cited sources count; unrelated demand elsewhere in
        # the same research cannot legitimize a supply-only conclusion.
        cited = [valid[key] for key in ids]
        has_demand = len(demand_sources(cited)) >= 2
        # A model's short citation list must not hide already accepted supply.
        # Demand judgments still depend only on the originally cited sources.
        safe_baseline = _baseline_for(scoped_filters, cited + [ev for ev in supply if ev["id"] not in ids], learning_references)
        landscape = []
        for entry in array(raw.get("existing_solutions", []))[:8]:
            entry = obj(entry)
            mechanism = text(entry.get("mechanism"))
            examples = []
            for example in array(entry.get("examples", []))[:4]:
                example = obj(example)
                example_ids = refs(example.get("evidence_ids"), solution_sources)
                name = text(example.get("name"))
                # Named examples must actually occur in the cited text/title.
                example_ids = [key for key in example_ids if name.casefold() in (valid[key]["title"] + " " + valid[key]["content"]).casefold()]
                if example_ids:
                    examples.append({"name": name, "evidence_ids": example_ids})
                    ids.extend(example_ids)
            entry_ids = refs(entry.get("evidence_ids", []), solution_sources)
            ids.extend(entry_ids)
            if entry_ids or examples:
                landscape.append({"mechanism": mechanism,
                                  "summary": text(entry.get("summary")), "examples": examples, "evidence_ids": entry_ids})
        landscape = [item for item in landscape if item["mechanism"] != "其他"
                     and "专项语言练习" not in item["summary"]]
        if not has_demand:
            # Keep concrete model extractions when the supply text verifies them.
            landscape = [item for item in landscape if any(
                item["summary"].strip("。.!！ ") in valid[key]["content"]
                and (item["mechanism"] in MECHANISMS or item["mechanism"] in valid[key]["content"])
                for key in item["evidence_ids"] if evidence_kind(valid[key]) == "supply")]
        for item in safe_baseline.get("existing_solutions", []):
            if item["mechanism"] not in {entry["mechanism"] for entry in landscape}:
                landscape.append(deepcopy(item))
        landscape = landscape[:5]
        for item in landscape:
            ids.extend(item["evidence_ids"])
        if not has_demand:
            ids.extend(safe_baseline.get("evidence_ids", []))
        scoped_discussions = {key: ev for key, ev in discussions.items() if key in ids}
        attempted = statements(raw.get("attempted_solutions"), scoped_discussions, "description")[:3] if has_demand else []
        dissatisfaction = statements(raw.get("dissatisfaction"), scoped_discussions, "description")[:3] if has_demand else []
        analyst = obj(raw.get("analyst"))
        facts = analyst_findings(statements(analyst.get("evidence"), valid), list(valid.values()))
        for item in facts + attempted + dissatisfaction:
            ids.extend(item["evidence_ids"])
        trend_ids = refs(raw.get("trend_evidence_ids"), scoped_discussions)
        comparable = _comparable_demand([valid[key] for key in trend_ids])
        direction = {"上升": r"上升|增加|增长|increase|grow", "下降": r"下降|减少|降低|decrease|declin", "稳定": r"稳定|持平|stable|unchanged"}
        supported = raw.get("trend") in TRENDS and comparable and all(re.search(direction[raw["trend"]], ev["content"], re.I) for ev in comparable)
        trend = raw.get("trend") if has_demand and supported else None
        trend_basis = text(raw.get("trend_basis"))
        if trend is None:
            trend_basis = "缺少多个时间点、独立来源且口径可比较的需求记录；趋势、需求程度和信号状态均为证据不足。"
            trend_ids = []
        demand = raw.get("demand_level") if trend and raw.get("demand_level") in DEMAND_LEVELS and len(comparable) >= 3 and raw.get("demand_basis") else None
        status = raw.get("signal_status") if trend and raw.get("signal_status") in SIGNAL_STATUSES and raw.get("status_basis") else None
        ids = list(dict.fromkeys(ids + trend_ids))
        signal = {"id": f"signal_{len(signals) + 1}", "signal_title": text(raw.get("signal_title")),
                  "age_range": list(filters["age_range"]), "skills": labels(raw.get("skills"), SKILLS_PROFESSIONAL, filters["skills"]),
                  "contexts": labels(raw.get("contexts"), CONTEXTS, filters["contexts"]),
                  "audiences": labels(raw.get("audiences"), AUDIENCES, ["无法判断"]), "region": filters["region"],
                  "trend": trend, "trend_basis": trend_basis, "trend_evidence_ids": trend_ids,
                  "demand_level": demand, "demand_basis": text(raw.get("demand_basis"), False),
                  "signal_status": status, "status_basis": text(raw.get("status_basis"), False),
                  "problem_summary": text(raw.get("problem_summary")), "existing_solutions": landscape,
                  "attempted_solutions": attempted, "dissatisfaction": dissatisfaction,
                  "unmet_need": text(raw.get("unmet_need")), "opportunity_hypothesis": text(raw.get("opportunity_hypothesis")),
                  "analyst": {"evidence": facts, "interpretation": text(analyst.get("interpretation")), "hypothesis": text(analyst.get("hypothesis"))},
                  "evidence_ids": ids, "evidence_sources": [valid[key] for key in ids],
                  "china_observation": text(raw.get("china_observation")), "overseas_observation": text(raw.get("overseas_observation"))}
        signal.update(signal_kind="demand_signal" if has_demand else "scope_observation",
                      current_judgment=text(raw.get("current_judgment") or raw.get("problem_summary")),
                      validation_questions=[text(v) for v in array(raw.get("validation_questions", safe_baseline.get("validation_questions", [])))[:3]],
                      demand_evidence_count=len(demand_sources(cited)))
        if not has_demand:
            # A prompt is not a safety boundary. Replace demand claims, including
            # the Analyst's facts, when only supply/background or one case exists.
            for key in ("signal_title", "current_judgment", "problem_summary", "unmet_need", "opportunity_hypothesis", "analyst", "validation_questions", "china_observation", "overseas_observation"):
                if key in safe_baseline:
                    signal[key] = deepcopy(safe_baseline[key])
            signal["demand_basis"] = "真实用户需求证据不足，不能从供给或背景资料估计需求程度。"
            signal["status_basis"] = "尚缺足够真实用户记录。"
        elif not trend:
            # Keep unsupported trend claims out of headlines/prose as well as badges.
            ungrounded = re.compile(r"(?:需求|关注|讨论).{0,8}(?:上升|增长|下降|稳定|激增)|(?:家长|学生|用户).{0,5}(?:普遍|越来越|大多)")
            for key in ("signal_title", "problem_summary", "current_judgment"):
                if ungrounded.search(signal[key]):
                    signal[key] = safe_baseline.get(key) or safe_baseline["problem_summary"]
            for key in ("interpretation", "hypothesis"):
                if ungrounded.search(signal["analyst"][key]):
                    signal["analyst"][key] = safe_baseline["analyst"][key]
        opposite = "overseas_observation" if filters["region"] == "中国大陆" else "china_observation"
        signal[opposite] = "本次未纳入该市场资料；请切换市场单独分析，不能据此进行中外比较。"
        signal = apply_learning_background(signal, learning_references, filters) if learning_references else signal
        signal["analyst"]["interpretation"] = interpretation_for_display(signal["analyst"]["interpretation"])
        signals.append(signal)
    return sanitize_data({"signals": signals})


def safe_signal_for_display(signal, evidence, filters=None):
    """Recheck an old snapshot in memory; no model, search, retrieval or DB writes."""
    from market_evidence import normalize_filters
    from market_quality import prepare_evidence
    signal, evidence = sanitize_data([signal, evidence])
    scope = dict(filters or {})
    for key in ("region", "skills", "contexts", "audiences", "age_range"):
        scope.setdefault(key, signal.get(key))
    try:
        scope = normalize_filters(scope)
    except (TypeError, ValueError):
        scope = normalize_filters({"region": signal.get("region") or "中国大陆"})
    ids = set(signal.get("evidence_ids") or [])
    learning_references = signal.get("learning_references") or []
    from market_quality import evidence_kind
    selected = [ev for ev in evidence if ev.get("id") in ids or evidence_kind(ev) == "supply"
                or (not ids and not learning_references)]
    selected = prepare_evidence(selected, scope)
    try:
        safe = validate_market({"signals": [signal]}, selected, scope, learning_references)["signals"][0]
    except (LLMSchemaError, KeyError, TypeError, ValueError, IndexError):
        safe = _baseline_for(scope, selected, learning_references)
        safe = dict(safe, region=scope["region"], age_range=scope["age_range"], skills=scope["skills"],
                    trend=None, demand_level=None, signal_status=None, evidence_sources=selected,
                    evidence_ids=[ev["id"] for ev in selected], attempted_solutions=[], dissatisfaction=[])
    safe["id"] = signal.get("id") or safe.get("id") or "signal_1"
    return apply_learning_background(safe, learning_references, scope) if learning_references else sanitize_data(safe)


def safe_answer_for_display(answer, insight, evidence, question=""):
    """Apply the same grounding boundary to stored chat, without a new request."""
    from market_quality import prepare_evidence
    answer, insight = sanitize_data([answer, insight])
    selected = prepare_evidence(evidence)
    selected = [ev for ev in selected if ev.get("id") in set(insight.get("evidence_ids") or [])
                and ev.get("region") == insight.get("region")]
    try:
        checked = validate_answer(answer, selected, insight, question)
    except (LLMSchemaError, KeyError, TypeError, ValueError):
        from market_baseline import baseline_answer
        checked = baseline_answer(insight, selected, question)
    return sanitize_data(dict(answer, **checked))
