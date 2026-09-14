"""Three small Market-local retrieval lanes over the unchanged M2 retriever."""
from market_quality import evidence_kind, prepare_evidence, source_key
from output_safety import sanitize_data

_LEARNING_QUERIES = {
    "阅读理解": ["阅读理解 reading comprehension", "分级阅读 graded readers", "reading level text complexity", "阅读 能力发展 年龄"],
    "口语表达": ["口语表达 oral language development", "句子 词汇 表达 speaking progression"],
    "自然拼读": ["自然拼读 phonics decoding", "拼读 阅读 phonics reading development"],
    "听力理解": ["听力理解 listening comprehension", "听懂 故事 listening development"],
    "听力解码": ["听力解码 speech decoding", "音素 听辨 phonological awareness"],
    "写作表达": ["写作表达 writing development", "句子 篇章 writing progression"],
    "单词拼写": ["单词拼写 spelling development", "字母 音形 spelling stages"],
    "词汇量扩展": ["词汇 vocabulary development", "词义 词汇 breadth depth"],
    "语法知识": ["语法 grammar development", "句式 syntax development"],
    "跨学科素养": ["跨学科 CLIL", "学科语言 academic language development"],
}


def retrieve_lanes(filters, retriever):
    from market_evidence import SKILL_EN, _local_hit
    f = filters
    skills = f["skills"] or ["口语表达", "阅读理解"]
    query = "英语 " + " ".join(skills[:2])
    queries = [query, "English " + " ".join(SKILL_EN[s] for s in skills[:2])]
    failures = []

    def collect(lane, searches, accepted, limit=3):
        candidates, seen = [], set()
        for q, scope in searches:
            try:
                hits = retriever.search(q, scope, 48)
            except Exception:
                failures.append({"stage": "local_retrieval", "lane": lane, "reason": "本地资料检索暂时不可用；已保留其他可用资料。", "url": ""})
                continue
            for hit in hits:
                if hit.chunk_id in seen:
                    continue
                seen.add(hit.chunk_id)
                item = _local_hit(hit, f, skills)
                if not item or evidence_kind(item) not in accepted:
                    continue
                item["retrieval_lane"] = lane
                if lane == "learning_reference_lane":
                    item["evidence_role"] = "learning_reference"
                    item["scope_note"] = "Learning Reference / Background：用于能力发展与学习路径，不用于市场需求、趋势、不满意或缺口判断。"
                candidates.append(item)
        # Each lane has its own quality gate and source-level best chunk selection.
        selected = prepare_evidence(candidates, f)
        if lane == "learning_reference_lane":
            role_order = {"learning_path": 0, "practice_guide": 1, "research_evidence": 2, "parent_experience": 3}
            selected.sort(key=lambda ev: (role_order.get(ev.get("content_role"), 2),
                                          ev.get("source_kind") == "web"))
            # Prefer complementary guides/tables over three accounts of the same type.
            diverse, used_kinds = [], set()
            for item in selected:
                kind = item.get("source_kind")
                if kind not in used_kinds:
                    diverse.append(item)
                    used_kinds.add(kind)
            selected = diverse + [item for item in selected if item not in diverse]
        return selected[:limit]

    region = {"region": f["region"]}
    demand = collect("demand_lane", [
        (q, dict(region, source_type=["公开用户讨论", "应用商店 / 产品评价", "用户评价", "论坛 / 社区讨论"]))
        for q in queries] + [(q, dict(region, raw_category=["research", "reports"])) for q in queries], {"demand"})
    supply = collect("supply_lane", [(q, dict(region, raw_category=["product_docs", "reports"])) for q in queries]
                     + [(q, dict(region, source_type="产品 / 机构官网")) for q in queries], {"supply"})
    learning = []
    if f["skills"]:
        learning_queries = list(dict.fromkeys(q for skill in skills[:2] for q in _LEARNING_QUERIES.get(skill, [skill])))[:6]
        learning = collect("learning_reference_lane", [(q, {"region": "general_reference", "raw_category": "learnpath"})
                                                        for q in learning_queries], {"learning"})
        if len(learning) < 3:
            extra = collect("learning_reference_lane", [(q, dict(region, raw_category="research"))
                                                         for q in learning_queries[:2]], {"research", "learning"})
            used = {source_key(item) for item in learning}
            learning.extend(item for item in extra if source_key(item) not in used)
            learning = learning[:3]
    # Stable separate IDs prevent learning citations from being mistaken for Market Evidence.
    for index, item in enumerate(demand + supply, 1):
        item["id"] = f"E{index}"
    for index, item in enumerate(learning, 1):
        item["id"] = f"L{index}"
    return sanitize_data(demand + supply + learning), sanitize_data(failures)
