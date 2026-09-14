"""Small, deterministic source-role labels; no model calls or text rewriting."""
from __future__ import annotations

import re

CONTENT_ROLES = (
    "learning_path", "practice_guide", "research_evidence", "parent_experience",
    "product_info", "policy_background", "market_signal", "general_reference",
)

CONTENT_ROLE_LABELS = {
    "learning_path": "学习发展路径", "practice_guide": "具体练习方法",
    "research_evidence": "研究依据", "parent_experience": "家长经验",
    "product_info": "产品资料", "policy_background": "政策背景",
    "market_signal": "市场观察", "general_reference": "一般参考",
}

_PARENT = re.compile(r"我家(?:的)?(?:孩子|娃|儿子|女儿)|我的(?:孩子|儿子|女儿)|作为家长|我是(?:一[位名个])?家长|\bmy (?:child|son|daughter)\b|\bour (?:child|son|daughter)\b", re.I)
_POLICY = re.compile(r"法律法规|本条例|本规定|行政许可|义务教育课程标准|教育部印发|依法|\bstatu(?:te|tory)\b|\bregulation[s]?\b", re.I)
_MARKET = re.compile(r"市场规模|市场份额|渗透率|竞争格局|同比(?:增长|下降)|融资|营收|行业趋势|\bmarket (?:size|share|growth)\b|\brevenue\b|\bfunding\b", re.I)
_PRODUCT = re.compile(r"产品功能|订阅价格|免费试用|立即购买|价格套餐|会员权益|\bsubscription (?:plan|price|cost)\b|\bfree trial\b|\bbuy now\b", re.I)
_RESEARCH = re.compile(r"样本量|随机分组|对照组|效应量|研究结果|实验结果|\bparticipants\b|\bcontrol group\b|\bstudy (?:found|showed)\b|\beffect size\b", re.I)
_PRACTICE = re.compile(r"第一步|第二步|具体步骤|读后提问|示范.{0,8}(?:再|然后)|先.{2,28}(?:再|然后)|每天.{0,12}(?:分钟|次)|复述故事|轮流.{0,8}(?:提问|回答)|\bstep [12]\b|\bask (?:the |your )?child\b|\bretell\b|\bread aloud\b", re.I)
_LEARNING = re.compile(r"学习路径|发展顺序|能力发展|语言发展|音素意识|字母音|拼读.{0,8}阅读|解码.{0,8}理解|\blearning (?:path|progression)\b|\bphonemic awareness\b|\bdecoding.{0,35}comprehension\b", re.I)
_EDUCATION = re.compile(r"英语|儿童|孩子|阅读|词汇|口语|拼读|学习|\benglish\b|\bchild\b|\bread(?:ing)?\b|\blearn(?:ing)?\b|\bphonics\b", re.I)


def _default_role(raw_category="", source_type="", region="", text=""):
    if raw_category == "learnpath":
        return "learning_path"
    if raw_category == "policies" or "政策" in source_type or "政府" in source_type:
        return "policy_background"
    if raw_category == "product_docs" or "产品" in source_type:
        return "product_info"
    if raw_category == "research" or "学术" in source_type or "研究机构" in source_type:
        return "research_evidence"
    if raw_category == "public_discussions" or source_type == "公开用户讨论":
        return "parent_experience" if _PARENT.search(text) else "market_signal"
    if raw_category == "reports" or source_type == "行业报告":
        return "market_signal"
    return "general_reference"


def classify_content_role(text, raw_category="", source_type="", region="", title=""):
    """Label a chunk using explicit cues, falling back to its registered source scope.

    A role describes the material's purpose, not its authority or effectiveness.
    For example, first-person practice accounts remain parent experience.
    """
    text = str(text or "")
    combined = str(title or "") + "\n" + text
    source_type = str(source_type or "")
    if _PARENT.search(text):
        return "parent_experience"
    for pattern, role in ((_POLICY, "policy_background"), (_MARKET, "market_signal"),
                          (_PRODUCT, "product_info"), (_RESEARCH, "research_evidence")):
        if pattern.search(combined):
            return role
    default = _default_role(raw_category, source_type, region, text)
    practice_matches = _PRACTICE.findall(text)
    if default == "product_info" and len(practice_matches) < 2 and not re.search(r"第一步|\bstep 1\b", text, re.I):
        return default
    if _EDUCATION.search(combined) and practice_matches:
        return "practice_guide"
    if _LEARNING.search(combined):
        return "learning_path"
    return default


def infer_doc_role(raw_category="", source_type="", region="", title="", text=""):
    """Prefer the user's directory/source category for a whole document."""
    role = _default_role(raw_category, str(source_type or ""), region, str(text or ""))
    if role != "general_reference":
        return role
    return classify_content_role(text, raw_category, source_type, region, title)
