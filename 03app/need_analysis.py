"""EngEduScope｜Solve a Need 分析编排（M3）。

用户输入 → 初步需求映射（规则基线）→ 1–3 个检索 query → M2 本地知识库检索（knowledge.retrieval）
→ 少量 Top chunks 作为 evidence → LLM 结构化输出（llm.provider / prompts / schemas）→ 结果字典。

- 家长：映射到专业能力、可能原因、优先级、3 条路径、AI DIY、下一步；evidence 只取中国大陆资料。
- 教育工作者：用户需求、教学目标、Existing Solution Landscape、Gap、Product Direction、MVP、验证指标；
  evidence 取中国大陆 + 海外 Benchmark。支持「继续调整方案」：当前结果 + 新指令 → 再生成一次。
- schema 校验失败自动重试 1 次；所有 LLMError 由页面统一友好提示。
不做 multi-hop RAG，不做排序推荐。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from knowledge.pipeline import KIND_LABELS
from knowledge.paths import LEARNING_REFERENCE_REGION
from knowledge.retrieval import get_retriever
from knowledge.tagging import CONTEXT_KEYWORDS, SKILL_KEYWORDS
from knowledge.textutil import clean_for_display, count_occurrences
from llm import prompts
from llm.provider import LLMError, LLMNotConfigured, LLMSchemaError, complete_json, load_config
from output_safety import sanitize_data, sanitize_text
from llm.schemas import normalize_skills, validate_educator, validate_parent, validate_student
from need_practice import practical_plan, parent_reasoning
from need_session import age_text
from need_intent import content_role_strategy, infer_need_intent, local_queries
from need_evidence import INSUFFICIENT_NOTE, evidence_sufficient, rank_evidence, supplement_search

PARENT_LABEL_TO_SKILLS = {"听": ["听力理解"], "说": ["口语表达"], "读": ["阅读理解"], "写": ["写作表达"],
                         "听力": ["听力理解"], "口语": ["口语表达"], "阅读": ["阅读理解"],
                         "写作": ["写作表达"], "单词": ["词汇量扩展"], "语法": ["语法知识"]}

SKILL_QUERIES = {
    "口语表达": ["AI 口语 陪练 少儿 英语", "英语 口语 输出 外教 孩子"],
    "阅读理解": ["分级阅读 英语 绘本 孩子", "少儿 英语 阅读 理解"],
    "听力理解": ["英语 听力 输入 儿童", "磨耳朵 英语 听力"],
    "听力解码": ["音素 语音 意识 英语 启蒙"],
    "写作表达": ["少儿 英语 写作"],
    "单词拼写": ["英语 拼写 单词 儿童"],
    "词汇量扩展": ["英语 词汇 单词 记忆 儿童"],
    "自然拼读": ["自然拼读 phonics 英语 启蒙"],
    "语法知识": ["英语 语法 小学"],
    "跨学科素养": ["STEAM 跨学科 英语 儿童"],
}
CONTEXT_QUERIES = {
    "家庭固定学习": "家庭 英语 学习 家长 陪伴",
    "亲子共学": "亲子 英语 共读 家长",
    "碎片时间": "碎片 时间 英语 学习 工具",
    "自主学习": "自主 学习 英语 孩子",
    "真实生活使用": "真实 场景 英语 运用",
    "睡前": "睡前 英语 绘本 听",
    "正式课堂": "课堂 英语 教学 小学",
    "学校课程衔接": "校内 英语 课程 衔接",
}
_OUTPUT_PROBLEM_RE = re.compile(r"(不|很少|几乎不|不太|不愿|不敢).{0,8}(说|开口|表达|讲)")


# ── 家长输入 → 专业能力映射（规则基线，供检索与 LLM 参考）───────────────
def map_parent_need(result: dict) -> dict:
    text = " ".join(filter(None, [result.get("problem"), result.get("background"), result.get("methods_note")])).lower()
    primary: List[str] = []
    for label in result.get("skills") or []:
        for skill in PARENT_LABEL_TO_SKILLS.get(label, []):
            if skill not in primary:
                primary.append(skill)
    hinted = [skill for skill, kws in SKILL_KEYWORDS.items() if any(count_occurrences(text, kw) for kw in kws)]
    if _OUTPUT_PROBLEM_RE.search(text) and "口语表达" not in primary:
        primary.insert(0, "口语表达")
    if "分级阅读" in (result.get("methods") or []) and "阅读理解" not in hinted:
        hinted.append("阅读理解")
    confidence = "high" if primary else ("medium" if hinted else "low")
    if not primary:
        # 无明确困难时只是选定观察起点，不把年龄/学习背景解释为能力缺陷。
        age_months = (result.get("age") or {}).get("age_months") or 84
        baseline = ["听力理解", "口语表达"] if age_months < 108 else ["阅读理解", "口语表达"]
        primary = hinted[:2] or baseline
    primary = primary[:2]
    secondary = [s for s in hinted if s not in primary][:3]
    contexts = list(result.get("contexts") or [])
    for ctx, kws in CONTEXT_KEYWORDS.items():
        if ctx not in contexts and any(count_occurrences(text, kw) for kw in kws):
            contexts.append(ctx)
    return {
        "primary_skills": primary,
        "secondary_skills": secondary,
        "contexts": contexts[:3],
        "method": "rule_baseline",
        "confidence": confidence,
    }


# ── 检索 ──────────────────────────────────────────────────────────────────
def build_queries(text: str, skills: List[str], contexts: List[str], extra: Optional[List[str]] = None) -> List[str]:
    queries: List[str] = []
    for skill in skills[:2]:
        queries.extend(SKILL_QUERIES.get(skill, [])[:1])
    for ctx in contexts[:1]:
        if CONTEXT_QUERIES.get(ctx):
            queries.append(CONTEXT_QUERIES[ctx])
    for q in extra or []:
        queries.append(q)
    text = " ".join((text or "").split())
    if text:
        queries.append(text[:60])
    seen, out = set(), []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:3]


def retrieve_evidence(queries: List[str], region_quotas: List[Tuple[str, int]], per_query: int = 4,
                      max_per_doc: int = 2, diagnostics: Optional[dict] = None) -> List[dict]:
    """按地域配额检索，去重后编号 E1…；每条带原始出处，供 Prompt 与结果页「参考依据」使用。"""
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics["retrieval_status"] = "no_matches"
    try:
        retriever = get_retriever()
    except Exception:  # 知识库未就绪时保留无依据的分析流程，并明确标记。
        diagnostics["retrieval_status"] = "unavailable"
        return []
    evidence: List[dict] = []
    seen_chunks = set()
    per_doc: Dict[str, int] = {}
    for region, quota in region_quotas:
        taken = 0
        for query in queries:
            if taken >= quota:
                break
            try:
                hits = retriever.search(query, {"region": region}, per_query)
            except Exception:  # noqa: BLE001  不暴露底层路径/错误，只记录检索不可用。
                diagnostics["retrieval_status"] = "unavailable"
                hits = []
            for hit in hits:
                if taken >= quota:
                    break
                if hit.chunk_id in seen_chunks or per_doc.get(hit.document_id, 0) >= max_per_doc:
                    continue
                seen_chunks.add(hit.chunk_id)
                per_doc[hit.document_id] = per_doc.get(hit.document_id, 0) + 1
                pages = ""
                if hit.page_start is not None:
                    pages = f"p.{hit.page_start}" if hit.page_end in (None, hit.page_start) else f"p.{hit.page_start}–{hit.page_end}"
                evidence.append({
                    "id": f"E{len(evidence) + 1}",
                    "title": hit.title or "（无标题）",
                    "region": hit.region,
                    "source_type": hit.source_type or "",
                    "raw_category": hit.raw_category,
                    "content_role": getattr(hit, "content_role", ""),
                    "document_id": hit.document_id,
                    "chunk_id": hit.chunk_id,
                    "retrieval_score": getattr(hit, "score", 0),
                    "evidence_role": "learning_reference" if hit.region == LEARNING_REFERENCE_REGION else "need_evidence",
                    "scope_note": "通用学习路径参考资料；用于理解能力发展与教学方法，不代表市场需求或趋势。" if hit.region == LEARNING_REFERENCE_REGION else "",
                    "source_kind": hit.source_kind,
                    "kind_label": KIND_LABELS.get(hit.source_kind, hit.source_kind),
                    "source_url": hit.source_url,
                    "original_path": hit.original_path,
                    "markdown_path": hit.markdown_path,
                    "section": hit.section_title,
                    "pages": pages,
                    "date": hit.date,
                    "text": sanitize_text(clean_for_display(hit.chunk_text))[:1000],
                    "query": query,
                })
                taken += 1
    if evidence:
        diagnostics["retrieval_status"] = (
            "partial" if diagnostics["retrieval_status"] == "unavailable" else "available"
        )
    return sanitize_data(evidence)


def _need_evidence(result, mapping, intent):
    strategy = content_role_strategy(result.get("user_type", "parent"), intent)
    queries = local_queries(result, mapping, intent)
    diagnostics = {}
    regions = [("中国大陆", 24), (LEARNING_REFERENCE_REGION, 24)]
    if result.get("user_type") == "professional":
        regions.insert(1, ("海外 Benchmark", 18))
    candidates = retrieve_evidence(queries, regions, per_query=12, max_per_doc=4, diagnostics=diagnostics)
    top_k = 11 if result.get("user_type") == "professional" else 8
    local = rank_evidence(candidates, strategy, mapping, top_k=top_k)
    combined, search_meta = supplement_search(result, mapping, intent, local)
    evidence = rank_evidence(combined, strategy, mapping, top_k=top_k)
    diagnostics.update(need_intent=intent, content_role_strategy=strategy, search_meta=search_meta,
                       evidence_note="" if evidence_sufficient(evidence, intent, user_type=result.get("user_type")) else INSUFFICIENT_NOTE)
    return evidence, queries, diagnostics


# ── LLM 调用（schema 校验失败自动重试 1 次）──────────────────────────────
def _call_validated(system: str, user: str, validator: Callable[[dict], dict]) -> dict:
    last: Optional[LLMError] = None
    for attempt in range(2):
        try:
            # 传输、JSON 解析与 schema 共用一次重试预算，避免嵌套放大 API 调用。
            data = complete_json(system, user, retries=0)
            return validator(data)
        except LLMNotConfigured:
            raise
        except LLMError as exc:
            last = exc
            if isinstance(exc, LLMSchemaError):
                user += "\n\n（上一次输出不符合结构要求。请检查所有必填字段、字段类型与条数，只输出完整合法的 JSON 对象。）"
    raise last  # type: ignore[misc]


def _meta(kind: str, mapping: Optional[dict], queries: List[str], diagnostics: Optional[dict] = None) -> dict:
    cfg = load_config()
    return {
        "kind": kind,
        "provider": cfg.describe(),
        "mode": "mock" if cfg.is_mock else "live",
        "mapping": mapping or {},
        "queries": queries,
        "revision_history": [],
        **(diagnostics or {}),
    }


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 家长 ──────────────────────────────────────────────────────────────────
def fallback_diy(result: dict, mapping: dict) -> dict:
    """LLM 未给出可执行 AI DIY 时的兜底：至少提供一段可复制 Prompt。"""
    skill = (mapping.get("primary_skills") or ["口语表达"])[0]
    age = age_text(result.get("age"))
    tasks = {
        "口语表达": "围绕孩子熟悉的内容，每次只问一个简单问题；答不出时给两个选项，鼓励自愿表达",
        "听力理解": "请家长朗读一条简短英语指令，让孩子用动作或选择图片回应，再核对是否理解",
        "听力解码": "给出两组常见词的声音对比，由家长朗读，让孩子辨别听到的是哪一个",
        "阅读理解": "提供一段符合年龄的简短文字，先问字面意思，再问一个需要从原文找线索的问题",
        "写作表达": "从孩子今天的一件小事开始，帮孩子选择词语写两句英语，再请孩子自行补充一个细节",
        "单词拼写": "选三个熟悉词，让孩子看词、遮住、尝试拼写、自己核对，关注音与字母的联系",
        "词汇量扩展": "选三个生活中常见的词，先在语境中理解，再换一个情境让孩子选择或使用",
        "自然拼读": "选择一组相同字母音对应关系的简单词，示范一个，再让孩子尝试合成其余词",
        "语法知识": "在同一个生活情境中对比两种简单句式，让孩子选择表达意思合适的一句并尝试改写",
        "跨学科素养": "围绕一个生活科学问题提供两条简单英语线索，让孩子选择、分类并解释理由",
    }
    return {
        "title": "可复制的 AI 练习提示词",
        "duration": "5–10 分钟",
        "steps": [],
        "scaffold_reduction": "",
        "copyable_prompt": (
            f"我的孩子{age}，正在学英语，想练习{skill}。请帮我组织一个 5 分钟活动："
            f"{tasks.get(skill, tasks['口语表达'])}。每次只给一个任务，等待我提供孩子的回应再继续；"
            "英语难度先从简单开始，根据孩子回应调整。用中文告诉家长如何协助。"
            "只根据我实际提供的回应总结可观察表现，不推断未观察到的能力，不诊断。"
        ),
    }


def _ground_parent_options(data, evidence):
    """A named option needs actual product information, not just a valid E number."""
    sources = {ev["id"]: ev for ev in evidence}
    for route in data.get("solution_routes", []):
        options = []
        for option in route.get("existing_options", []):
            name = option.get("name", "").strip()
            ids = [key for key in option.get("evidence_ids", []) if key in sources
                   and (sources[key].get("content_role") == "product_info"
                        or sources[key].get("source_type") == "产品 / 机构官网")
                   and name and name.casefold() in (sources[key].get("title", "") + " " + sources[key].get("text", "")).casefold()]
            if not ids:
                continue
            option = dict(option, evidence_ids=ids)
            if re.search(r"保证.{0,12}(?:效果|学会|提高|提升)|一定能|必然|效果已验证|显著提升|包会", option.get("why_match", "")):
                option["why_match"] = "资料可核对其功能；是否适合孩子，需要用本次小任务试用并观察实际表现。"
            options.append(option)
        route["existing_options"] = options
    return data


def analyze_parent(result: dict) -> dict:
    result = sanitize_data(result)
    result["user_type"] = "parent"
    mapping = map_parent_need(result)
    text = result.get("problem") or result.get("background") or ""
    intent = infer_need_intent(result)
    evidence, queries, diagnostics = _need_evidence(result, mapping, intent)
    inputs = {
        "user_type": "parent",
        "need_intent": intent,
        "age": age_text(result.get("age")),
        "age_months": (result.get("age") or {}).get("age_months"),
        "entry_type": "具体问题" if result.get("entry_type") == "parent_specific" else "整体看看孩子目前需要什么",
        "description": text,
        "parent_focus_listen_speak_read_write": result.get("skills") or [],
        "contexts": result.get("contexts") or [],
        "current_methods": result.get("methods") or [],
        "methods_note": result.get("methods_note") or "",
    }
    ids = [e["id"] for e in evidence]
    data = _call_validated(prompts.SYSTEM_PARENT, prompts.build_parent_prompt(inputs, mapping, evidence),
                           lambda d: validate_parent(d, ids))
    data = _ground_parent_options(data, evidence)
    plan = data.get("practice_plan")
    if not plan or (intent["primary_intent"] == "getting_started" and len(plan.get("stages", [])) < 2):
        plan = practical_plan(inputs, mapping, intent, user_type="parent")
        diagnostics["practice_plan_mode"] = "general_baseline"
    reported = parent_reasoning(inputs, mapping, intent)
    reasoning = dict(data.get("need_reasoning") or reported)
    # The "known" section repeats the submitted account, never a model's added history.
    reasoning["reported_facts"] = reported["reported_facts"]
    ai_diy = data["ai_diy"]
    if not ai_diy.get("steps") and not ai_diy.get("copyable_prompt"):
        ai_diy = fallback_diy(result, mapping)
    elif not ai_diy.get("copyable_prompt"):
        ai_diy["copyable_prompt"] = fallback_diy(result, mapping)["copyable_prompt"]
    return sanitize_data({
        "generated_at": _now(),
        "analysis_meta": _meta("parent", mapping, queries, diagnostics),
        **_saved_strategy(diagnostics),
        "parent_action_plan": plan,
        "need_reasoning": reasoning,
        "need_analysis": {
            "problem_summary": data["problem_summary"],
            "primary_skills": data["primary_skills"],
            "secondary_skills": data["secondary_skills"],
            "skills_explanation": data["skills_explanation"],
            "contexts": data["contexts"],
            "possible_causes": data["possible_causes"],
            "priority": data["priority"],
            "evidence_needed": data["evidence_needed"],
            "next_steps": data["next_steps"],
            "evidence_ids": data["evidence_ids"],
        },
        "solution_routes": data["solution_routes"],
        "ai_diy": ai_diy,
        "evidence_sources": evidence,
    })


def _saved_strategy(meta: dict) -> dict:
    return {key: meta.get(key) for key in ("need_intent", "content_role_strategy", "search_meta", "evidence_note")}


def analyze_student(result: dict) -> dict:
    result = sanitize_data(result)
    result["user_type"] = "student"
    mapping = map_parent_need(result)
    intent = infer_need_intent(result)
    evidence, queries, diagnostics = _need_evidence(result, mapping, intent)
    inputs = {
        "user_type": "student", "age": age_text(result.get("age")),
        "age_months": (result.get("age") or {}).get("age_months"),
        "description": result.get("problem") or "", "skills": result.get("skills") or [],
        "contexts": result.get("contexts") or [], "need_intent": intent,
    }
    ids = [e["id"] for e in evidence]
    data = _call_validated(prompts.SYSTEM_STUDENT, prompts.build_student_prompt(inputs, mapping, evidence, intent),
                           lambda d: validate_student(d, ids))
    plan = data["practice_plan"]
    return sanitize_data({
        "generated_at": _now(), "analysis_meta": _meta("student", mapping, queries, diagnostics),
        **_saved_strategy(diagnostics), "student_practice_plan": plan,
        "need_analysis": {"problem_summary": plan["bottleneck"], "primary_skills": data["primary_skills"],
                          "contexts": data["contexts"], "priority": plan["priorities"], "evidence_ids": data["evidence_ids"]},
        "evidence_sources": evidence,
    })


# ── 教育工作者 ────────────────────────────────────────────────────────────
def _educator_inputs(result: dict) -> dict:
    return {
        "age": age_text(result.get("age")),
        "skills": result.get("skills") or [],
        "contexts": result.get("contexts") or [],
        "carriers": result.get("carriers") or [],
        "pain_point": result.get("pain_point") or "",
    }


def _educator_core(analysis: dict) -> dict:
    need = analysis.get("need_analysis") or {}
    return {
        "user_need": need.get("user_need"),
        "teaching_goal": need.get("teaching_goal"),
        "solution_landscape": need.get("solution_landscape"),
        "gap": need.get("gap"),
        "product_direction": analysis.get("product_direction"),
        "mvp_spec": analysis.get("mvp_spec"),
        "validation_metrics": analysis.get("validation_metrics"),
        "evidence_ids": need.get("evidence_ids") or [],
    }


def _pack_educator(data: dict, evidence: List[dict], meta: dict) -> dict:
    return sanitize_data({
        "generated_at": _now(),
        "analysis_meta": meta,
        **_saved_strategy(meta),
        "need_analysis": {
            "user_need": data["user_need"],
            "teaching_goal": data["teaching_goal"],
            "solution_landscape": data["solution_landscape"],
            "gap": data["gap"],
            "evidence_ids": data["evidence_ids"],
        },
        "product_direction": data["product_direction"],
        "mvp_spec": data["mvp_spec"],
        "validation_metrics": data["validation_metrics"],
        "evidence_sources": evidence,
    })


def analyze_educator(result: dict) -> dict:
    result = sanitize_data(result)
    result["user_type"] = "professional"
    inputs = _educator_inputs(result)
    mapping = map_parent_need({"problem": inputs["pain_point"], "contexts": inputs["contexts"],
                               "age": result.get("age")})
    skills = normalize_skills(inputs["skills"]) or mapping["primary_skills"]
    inputs["skills"] = skills
    mapping["primary_skills"] = skills
    intent = infer_need_intent(result)
    evidence, queries, diagnostics = _need_evidence(result, mapping, intent)
    ids = [e["id"] for e in evidence]
    data = _call_validated(prompts.SYSTEM_EDUCATOR, prompts.build_educator_prompt(inputs, evidence),
                           lambda d: validate_educator(d, ids))
    return _pack_educator(data, evidence, _meta("educator", mapping, queries, diagnostics))


def revise_educator(result: dict, analysis: dict, instruction: str) -> dict:
    result, analysis, instruction = sanitize_data(result), sanitize_data(analysis), sanitize_text(instruction)
    """当前结果 + 新指令 → 再生成一次（复用上一轮 evidence，不做长期聊天）。"""
    inputs = _educator_inputs(result)
    evidence = analysis.get("evidence_sources") or []
    ids = [e["id"] for e in evidence]
    data = _call_validated(prompts.SYSTEM_EDUCATOR,
                           prompts.build_revision_prompt(inputs, _educator_core(analysis), instruction, evidence),
                           lambda d: validate_educator(d, ids))
    meta = dict(analysis.get("analysis_meta") or _meta("educator", None, []))
    meta["revision_history"] = list(meta.get("revision_history") or []) + [{"instruction": instruction.strip(), "at": _now()}]
    cfg = load_config()
    meta["provider"] = cfg.describe()
    meta["mode"] = "mock" if cfg.is_mock else "live"
    return _pack_educator(data, evidence, meta)


# ── 合并到 sn_result（History 的 summary_json 即此结构）───────────────────
ANALYSIS_KEYS = ("generated_at", "analysis_meta", "need_analysis", "solution_routes", "ai_diy", "evidence_sources",
                 "product_direction", "mvp_spec", "validation_metrics", "need_intent", "content_role_strategy",
                 "search_meta", "evidence_note", "parent_action_plan", "student_practice_plan", "need_reasoning")


def apply_analysis(result: dict, analysis: dict) -> dict:
    merged = {k: v for k, v in result.items() if k not in ANALYSIS_KEYS}
    merged.update(analysis)
    return sanitize_data(merged)


def has_analysis(result: Optional[dict]) -> bool:
    return bool(result and result.get("generated_at") and result.get("need_analysis"))
