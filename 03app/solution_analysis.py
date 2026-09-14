"""M5 generation/revision: existing LLM provider, inherited evidence, one local lookup.

No search provider is imported here and no web search is triggered by M5.
"""
from copy import deepcopy
from datetime import datetime
import re

from knowledge.retrieval import get_retriever
from knowledge.paths import LEARNING_REFERENCE_REGION
from llm.provider import LLMConfigurationError, LLMError, LLMNotConfigured, complete_json, load_config
from market_evidence import SKILL_EN, credibility
from solution_context import normalize_brief
from solution_prompts import SYSTEM, generate_prompt, revision_prompt
from solution_schemas import validate_solution
from output_safety import sanitize_data, sanitize_text


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _retrieve(brief):
    skills = list(dict.fromkeys(brief["skills"][:2] + [SKILL_EN.get(skill, skill) for skill in brief["skills"][:2]]))
    query = " ".join([*skills, *brief["contexts"][:1], "英语", brief["core_need"][:50]])
    evidence, seen = [], set()
    try:
        # One local lookup; learning paths take priority over research background.
        regions = [brief["region"], LEARNING_REFERENCE_REGION]
        hits = get_retriever().search(query, {"region": regions, "raw_category": ["learnpath", "research"]}, 48)
        hits = sorted(hits, key=lambda hit: hit.raw_category != "learnpath")
        used_ids = {str(item.get("id")) for item in brief.get("evidence_sources") or []}
        for hit in hits:
            identity = hit.source_url or hit.document_id
            if identity in seen:
                continue
            index = 1
            while f"E{index}" in used_ids:
                index += 1
            identifier = f"E{index}"
            used_ids.add(identifier)
            evidence.append({"id": identifier, "title": hit.title,
                             "content": sanitize_text(hit.chunk_text)[:1200], "text": sanitize_text(hit.chunk_text)[:1200],
                             "source_type": hit.source_type or "其他", "region": hit.region,
                             "raw_category": hit.raw_category,
                             "document_id": hit.document_id,
                             "content_role": getattr(hit, "content_role", "general_reference"),
                             "evidence_role": "learning_reference",
                             "credibility_level": credibility(hit.source_type), "origin": "local",
                             "scope_note": "Learning Reference｜用于年龄阶段、能力发展路径、技能机制与教学练习方式；适用性需核验，不能证明真实市场需求、用户不满或市场缺口。",
                             "url": hit.source_url or "", "source_url": hit.source_url or "",
                             "original_path": hit.original_path or "", "date": hit.date or "",
                             "source_kind": hit.source_kind, "content_kind": "local_chunk",
                             "page_start": hit.page_start, "page_end": hit.page_end})
            seen.add(identity)
            if len(evidence) == 5:
                break
        return evidence, {"status": "retrieved" if evidence else "no_matches", "query": query, "calls": 1}
    except Exception:
        return [], {"status": "unavailable", "query": query, "calls": 1,
                    "message": "本地知识库暂时不可用；本次方案为待验证设计建议，没有补充资料依据。"}


def _configured_provider():
    cfg = load_config()
    if cfg.configuration_error:
        raise LLMConfigurationError(user_message=cfg.configuration_error)
    if not cfg.configured:
        raise LLMNotConfigured()
    return cfg


def _validated(prompt, evidence, cfg, brief):
    last = None
    for _ in range(2):
        try:
            data = complete_json(SYSTEM, prompt, retries=0, cfg=cfg)
            return validate_solution(data, evidence, brief)
        except LLMNotConfigured:
            raise
        except LLMError as exc:
            last = exc
            prompt += "\n上次输出未通过检查。请补全产品判断、solution_scope、Opportunity未知点、一个核心交互、Continue/Adjust/Stop；MVP1–5项、Risks恰3项、Demo详情5步、三类指标。无匹配来源的Landscape为空；缺乏独立真实需求证据时选择轻量验证scope。只输出合法JSON。"
    raise last


def generate_solution(brief):
    from solution_baseline import baseline_solution

    brief = normalize_brief(sanitize_data(brief))
    retrieval_meta = {"status": "inherited" if brief["evidence_sources"] else "not_requested", "calls": 0}
    if not brief["evidence_sources"]:
        brief["evidence_sources"], retrieval_meta = _retrieve(brief)
    brief = sanitize_data(brief)
    evidence = deepcopy(brief["evidence_sources"])
    cfg = _configured_provider()
    if cfg.is_mock:
        solution = validate_solution(baseline_solution(brief), evidence, brief)
    else:
        solution = _validated(generate_prompt(brief), evidence, cfg, brief)
    return sanitize_data({"kind": "product_concept", "entry_type": "build_solution", "opportunity_brief": brief,
            "solution": solution, "evidence_sources": evidence, "generated_at": _now(),
            "analysis_meta": {"mode": "demo" if cfg.is_mock else "live", "provider": cfg.describe(),
                              "revision_history": [], "retrieval": retrieval_meta}})


def _updated_brief(original, instruction):
    brief = deepcopy(original)
    brief["constraints"] = list(brief.get("constraints") or []) + [instruction]
    lower = instruction.lower()
    if any(token in lower for token in ("不使用硬件", "不依赖硬件", "不要硬件", "不用硬件", "不做硬件", "去掉硬件", "取消硬件", "no hardware", "只用 web", "只用web", "web app", "只用网页")):
        brief["preferred_carriers"] = ["App / 网页"]
    if "中国" in instruction and any(word in instruction for word in ("适合", "面向", "改", "家庭")):
        brief["region"] = "中国大陆"
    age_matches = [match for match in re.finditer(r"(?<!\d)(\d{1,2})\s*(?:岁)?\s*[–—\-至到~～]\s*(\d{1,2})\s*岁", instruction)
                   if not re.search(r"(?:不要|不用|不必).{0,4}$", instruction[:match.start()])]
    age_match = age_matches[-1] if age_matches else None
    if age_match:
        start, end = int(age_match[1]), int(age_match[2])
        if not 3 <= start <= end <= 15:
            raise ValueError("调整后的年龄需在 3–15 岁之间，结束年龄不能早于起始年龄。")
        brief["age_range"] = [start * 12, end * 12 + 11]
        age_text = f"{start}–{end}岁"
        target = brief["target_user"]
        age_pattern = r"\d+\s*岁(?:\d+\s*个月)?\s*[–—\-至到~～]\s*\d+\s*岁(?:\d+\s*个月)?|\d+\s*[–—\-至到~～]\s*\d+\s*岁|\d+\s*岁(?:\d+\s*个月)?"
        new_target, changed = re.subn(age_pattern, age_text, target, count=1)
        brief["target_user"] = new_target if changed else f"{age_text}：{target}"
    if brief["age_range"] != original["age_range"] or brief["region"] != original["region"]:
        note = "目标年龄或市场已调整，沿用资料对新对象的适用性需重新核验；本次未重新检索。"
        brief["scope_notes"] = list(dict.fromkeys(list(brief.get("scope_notes") or []) + [note]))
    return normalize_brief(brief)


def revise_solution(record, instruction):
    from solution_baseline import revise_baseline
    record, instruction = sanitize_data(record), sanitize_text(instruction)

    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("请先填写希望调整的内容。")
    instruction = instruction.strip()
    if len(instruction) > 2000:
        raise ValueError("请将调整要求缩短到 2000 字以内。")
    if not isinstance(record, dict) or record.get("kind") != "product_concept":
        raise ValueError("请先生成或恢复一份产品方案。")
    updated = deepcopy(record)
    updated.setdefault("original_opportunity_brief", deepcopy(record["opportunity_brief"]))
    updated["opportunity_brief"] = _updated_brief(record["opportunity_brief"], instruction)
    evidence = updated["evidence_sources"]
    cfg = _configured_provider()
    if cfg.is_mock:
        solution = validate_solution(revise_baseline(updated, instruction), evidence, updated["opportunity_brief"])
    else:
        solution = _validated(revision_prompt(updated, instruction), evidence, cfg, updated["opportunity_brief"])
    updated["solution"] = solution
    updated["generated_at"] = _now()
    meta = updated.setdefault("analysis_meta", {})
    meta.update(mode="demo" if cfg.is_mock else "live", provider=cfg.describe())
    meta["revision_history"] = list(meta.get("revision_history") or []) + [{"instruction": instruction, "at": updated["generated_at"]}]
    return sanitize_data(updated)
