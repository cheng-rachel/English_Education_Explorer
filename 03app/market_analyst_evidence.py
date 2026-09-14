"""Analyst wording only: short observations from already selected evidence.

Does not retrieve, rank or classify sources. Unreadable/abstract passages remain
in the original evidence snapshot, but cannot stand in for an Analyst finding.
"""
import re

from market_quality import evidence_kind, readable_excerpt
from output_safety import sanitize_data

_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z])|[\r\n]+")
_META = re.compile(r"(?:包含|含有|提供|涉及|用于|记录了?).{0,14}(?:调查|功能|产品|机制|学习路径|需求|经验).{0,8}(?:参考|资料|介绍|背景|记录|信息)|包含用户调查|提供产品功能参考|contains? (?:a )?(?:survey|research)|provides? .{0,20}(?:reference|background)", re.I)
_DETAIL = re.compile(r"分级|读物|词汇|短文|提示|问答|追问|反馈|复述|发音|跟读|完整句|句子|语法|工作记忆|音形|识词|理解|练习|教师|课堂|课程|家长|孩子|学生|phonics|read\w*|vocab\w*|prompt\w*|feedback|tutor\w*|child\w*|student\w*|comprehension", re.I)
_ACTION = re.compile(r"通过|先.{1,30}再|按.{1,12}(?:难度|水平)|提供|使用|支持|要求|发现|显示|相关|关联|用过|试过|读完|学了|练了|不能|不会|仍|还是|难以|困难|负担|[0-9]+(?:\.[0-9]+)?\s*(?:%|％|位|名|人)|\b(?:offers?|uses?|provides?|reported|found|showed|associated|tried|still|cannot|struggle\w*|difficult\w*|feedback)\b", re.I)
_BOUNDARY = {
    "demand": "仅代表这些用户的具体记录，不能推断普遍需求、产品失败原因或市场趋势。",
    "supply": "产品方的功能自述不证明学习效果、用户满意度或需求增长。",
    "research": "结论限于原研究的样本与条件，不能直接证明普遍市场需求或产品效果。",
    "policy": "制度要求不等于用户的实际困难、使用经历或市场需求。",
    "learning": "学习路径参考不证明市场需求或趋势。",
}
_INTERPRETATION_META = re.compile(
    r"不能证明市场缺口|(?:这属于|仅作为|仅用于)学习问题(?:的)?解释线索")


def interpretation_for_display(value):
    """Drop internal writing/boundary clauses, preserving concrete explanations."""
    parts = re.split(r"(?<=[。！？!?；;，,])|[\r\n]+", str(value or ""))
    if not any(_INTERPRETATION_META.search(part) for part in parts):
        return str(value or "").strip()
    result = "".join(part for part in parts if not _INTERPRETATION_META.search(part)).strip()
    return result.rstrip("，,；;") + ("。" if result.endswith(("，", ",", "；", ";")) else "")


def source_finding(source, preferred=""):
    source = sanitize_data(source)
    content = source.get("content") or source.get("text") or source.get("snippet") or ""
    candidates = _SPLIT.split(str(content))
    # Keep a model's concise wording when it is also explicitly present in the source.
    if preferred and preferred in content:
        candidates.insert(0, preferred)
    for sentence in candidates:
        sentence = sentence.strip(" #\t")
        if not 14 <= len(sentence) <= 180 or _META.search(sentence):
            continue
        if not (_DETAIL.search(sentence) and _ACTION.search(sentence)):
            continue
        excerpt = readable_excerpt(sentence, limit=180)
        if not excerpt or excerpt.endswith("…"):
            continue
        kind = evidence_kind(source)  # Reuse the existing classification without changing it.
        prefix = "来源自述" if kind == "supply" else "用户记录" if kind == "demand" else "资料写明"
        return {"statement": f"{prefix}：“{excerpt}”", "evidence_ids": [source["id"]],
                "boundary": _BOUNDARY.get(kind, "仅说明这份资料中的内容，适用范围与效果仍需核验。")}
    return None


def analyst_findings(facts, evidence):
    """Replace metadata-only or unsupported summaries with a cited concrete passage."""
    sources = {item.get("id"): item for item in evidence or []}
    result, seen = [], set()
    for item in facts or []:
        for key in item.get("evidence_ids") or []:
            if key in seen or key not in sources:
                continue
            finding = source_finding(sources[key], item.get("statement") or "")
            if finding:
                result.append(finding)
                seen.add(key)
            if len(result) == 3:
                return result
    return result
