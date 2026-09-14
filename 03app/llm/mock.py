"""Deterministic M3 Demo fallback; examples are not evidence-based AI analysis.

No brand features or efficacy are inferred from retrieval titles. Skill templates show
complete flows; revisions support age, no dedicated hardware, and less parent input.
ENGEDUSCOPE_LLM_MOCK_MODE=ok / schema_error / timeout exercises safe failure paths.
"""
from __future__ import annotations

import copy
import json
import os
import re
from typing import Dict

from llm.prompts import TASK_EDUCATOR, TASK_PARENT, TASK_REVISION, TASK_STUDENT
from need_practice import practical_plan, parent_reasoning

_SECTION_RE = re.compile(r"^## (.+?)\s*$", re.M)


def _sections(prompt: str) -> Dict[str, str]:
    parts = _SECTION_RE.split(prompt)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def _json_block(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        value = json.loads(text[start:end + 1])
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _age(inputs: dict) -> str:
    age = inputs.get("age")
    if isinstance(age, dict):
        if age.get("display"):
            return age["display"]
        if age.get("mode") == "range":
            return f"{_age({'age': age.get('start')})} – {_age({'age': age.get('end')})}"
        return f"{age['years']}岁{age.get('months', 0)}个月" if "years" in age else "目标年龄"
    return age or "目标年龄"


# explanation, task, concrete steps, observation, teacher expertise, digital selection
_PROFILES = {
    "口语表达": (
        "把熟悉的意思用自己的英语表达出来",
        "熟悉内容的三轮小对话",
        ["选一张孩子熟悉的图片，成人先说一句示例：I see a cat.",
         "问一个简单问题，如 What can you see? 等孩子回答；不强求完整句子。",
         "孩子愿意时再追问一句；答不出就给两个选项，结束时肯定一次自主表达。"],
        "同类任务中不靠示范、主动表达的次数与所需提示",
        "熟悉儿童互动教学、能等待回答并用追问引导表达的老师，因为这类任务需要真实对话与渐进提示",
        "围绕熟悉材料互动、允许等待和重复尝试，并能查看实际回答的工具"),
    "阅读理解": (
        "读完后知道人物做了什么，并能从文字里找理由",
        "一小段阅读找线索",
        ["选孩子能轻松读出的短文，先看图预测主题。", "读完后问 Who is in the story? 允许用中文或指图回答。",
         "再问一个为什么，请孩子指向文字线索；不把朗读流利当成理解。"],
        "同难度新短文中独立找对信息与解释线索的表现",
        "能区分解码与理解、用提问和文字线索观察阅读过程的阅读教师，因为流利朗读不等于理解",
        "提供难度合适短文、理解问题和原文线索反馈的阅读工具"),
    "听力理解": (
        "听到一句话或短故事后明白意思并做出回应",
        "听一句做一件事",
        ["成人读一句熟悉指令，如 Point to the red book. 同时摆出两件物品。",
         "请孩子指物或行动，不要求跟读；没听明白可慢速重复一次。", "换物品再试一次，记录是否需要手势提示。"],
        "相近难度的新指令中独立正确回应的比例与重复次数",
        "会用动作回应区分听懂与跟读、能调整语速和难度的儿童教师，因为需要看真实理解",
        "能控制语速、重复播放，并用选择或行动任务检查理解的听力工具"),
    "听力解码": (
        "从连续语音中听清熟悉的词和声音区别",
        "声音与图片配对",
        ["准备两张熟悉物品图片，成人说出其中一个词，如 cat。", "孩子指图后再听一次，在短句 I see a cat. 中找同一个词。",
         "换一句熟悉短句，不显示文字，观察是否还能听出目标词。"],
        "熟悉词换到短句后听辨的正确情况与所需重复次数",
        "有儿童语音意识和听辨教学经验、能区分词义未知与语音没听清的老师，因为两者需要不同支持",
        "有清晰音频、词与短句对照、允许反复听辨的工具"),
    "写作表达": (
        "围绕一个想法写出别人能看懂的句子",
        "一张图写两句",
        ["选熟悉图片，先让孩子用中文或英语说想表达什么。", "按当前水平写一到两句，如 This is my dog. 允许先写关键词。",
         "一起只检查一个地方：读者能否明白；孩子自己修改一次。"],
        "同难度新图片中能独立写清的意思与修改时所需提示",
        "能先帮助组织意思、再选择少量语言点反馈的儿童写作教师，因为只改错可能挤占表达",
        "提供写作支架和一次一个修改提示、不会直接代写全文的工具"),
    "单词拼写": (
        "听到或想用熟悉的单词时，能把字母顺序写出来",
        "三个熟词看听写检查",
        ["选三个孩子已经理解的短词，边听边观察字母组合。", "盖住单词，让孩子按听到的声音尝试写一个词，如 cat。",
         "对照原词，只圈一个需要调整的地方，再隔一会儿试一次。"],
        "隔天不看范例写出已学词的情况及错误类型",
        "能结合音形对应和记忆提取分析拼写错误的老师，因为机械抄写未必能帮助独立拼写",
        "支持听写、延迟复习和查看具体错误的拼写工具"),
    "词汇量扩展": (
        "理解并在新场景里认出或使用更多词",
        "三个新词连到生活",
        ["从孩子熟悉的情境选三个词，用图片或动作说明意思。", "把词放进短句，如 The apple is red. 请孩子指物或选择。",
         "换一张图片再次认词，隔天再用一次，避免只背中文对应。"],
        "隔天在不同图片或短句中认出并使用目标词的表现",
        "会把词义、例句和间隔复习结合起来的老师，因为词表记忆还需要迁移到真实语境",
        "支持语境例句、图片和间隔复习的词汇工具"),
    "自然拼读": (
        "把学过的字母与声音对应起来，尝试读出新词",
        "换一个字母读新词",
        ["选已经学过的音形对应，成人示范把 c-a-t 合成 cat。", "换成同规则的词，如 mat，请孩子分音再合起来。",
         "确认词义后放进一句短句，不一次引入许多新规则。"],
        "对相同规则但未练过的词，独立合成读音的表现",
        "能明确示范音形对应并观察合音过程的拼读教师，因为背熟单词不能替代规则迁移",
        "有清晰音素示范、渐进难度和新词迁移练习的拼读工具"),
    "语法知识": (
        "在表达意思时选用合适的句子结构",
        "对比两张图说变化",
        ["只选一个已学结构，如 This is a cat. / These are cats.。", "给单个和多个物品图片，让孩子选句或自己说写一句。",
         "换物品再试，解释形式和意思的联系，不一次纠正所有错误。"],
        "新图片情境中能否独立使用同一结构表达正确意思",
        "会用语境和对比任务解释形式与意义的老师，因为只背规则不一定能用于表达",
        "支持语境练习、简短解释和一次一个语法点反馈的工具"),
    "跨学科素养": (
        "借助英语理解并讨论熟悉的学科内容",
        "英语观察小实验",
        ["选安全熟悉的小任务，如观察两种物品能否浮在水上，成人操作。", "先预测再观察，用 float / sink 或中文说明结果。",
         "用图片加一句简单英语记录发现，如 The leaf floats.，把概念理解与语言困难分开看。"],
        "能否解释观察结果，以及表达学科概念时需要的语言提示",
        "兼具儿童学科活动设计和英语支架经验的老师，因为语言难度不应遮住概念学习",
        "把学科图片、简短语言支架和观察记录结合起来的工具"),
}


def _skill_list(inputs: dict, mapping: dict = None) -> list:
    from llm.schemas import normalize_skills
    mapping = mapping or {}
    skills = normalize_skills(mapping.get("primary_skills") or inputs.get("skills") or [])
    if skills:
        return skills[:2]
    text = " ".join(str(inputs.get(k, "")) for k in ("problem", "background", "pain_point", "description"))
    cues = [("口语表达", ("不主动说", "不会主动说", "不开口", "主动口语", "口语", "输出不足")),
            ("写作表达", ("写作", "作文", "写句")), ("单词拼写", ("拼写", "听写")),
            ("自然拼读", ("拼读",)), ("阅读理解", ("阅读", "读懂", "绘本")),
            ("听力理解", ("听不懂", "听力", "儿歌")), ("词汇量扩展", ("词汇", "单词")),
            ("语法知识", ("语法",)), ("跨学科素养", ("跨学科", "学科"))]
    for skill, keywords in cues:
        if any(word in text for word in keywords):
            return [skill]
    return ["听力理解", "阅读理解"]


def _parent(prompt: str) -> dict:
    sections = _sections(prompt)
    inputs = _json_block(sections.get("家长输入", ""))
    mapping = _json_block(sections.get("系统初步映射（规则基线，供参考，可以修正）", ""))
    from llm.schemas import normalize_contexts, normalize_skills
    primary = _skill_list(inputs, mapping)
    secondary = [s for s in normalize_skills(mapping.get("secondary_skills", [])) if s not in primary][:3]
    contexts = normalize_contexts(inputs.get("contexts")) or ["家庭固定学习"]
    skill, age = primary[0], _age(inputs)
    explanation, activity, steps, observation, teacher, digital = _PROFILES[skill]
    entry_type = inputs.get("entry_type", "")
    overview = entry_type == "parent_overview" or "整体" in entry_type or (
        not entry_type and not (inputs.get("problem") or inputs.get("description")))
    if overview:
        summary = (f"这份 Demo 先围绕{age}孩子的学习背景梳理机会，不预设已经存在某种困难。"
                   f"目前可从{'、'.join(primary)}的小任务观察起，再看听说读写之间是否平衡；信息还不足以判断强弱。")
    else:
        summary = (f"这份 Demo 将关注点放在{skill}：观察孩子能否在熟悉情境中独立完成任务，"
                   "比只看学过多少内容更能帮助选择下一步。下面是可尝试的机制示例，原因需要用实际观察验证。")
    intent = inputs.get("need_intent") or {"primary_intent": "skill_practice"}
    intent_name = intent.get("primary_intent", "") if isinstance(intent, dict) else str(intent)
    plan = practical_plan(inputs, mapping, intent)
    reasoning = parent_reasoning(inputs, mapping, intent)
    if intent_name == "getting_started":
        summary = (f"可以先给{age}孩子安排一个听、看图和做动作的短活动，用家中已有材料就能开始。"
                   "先观察哪些表达能听懂、愿意怎样回应，再决定是否加一点难度；2–4周是回看做法的时间，不是要求达到等级的期限。")
    elif intent_name == "diagnose_bottleneck":
        summary = plan["bottleneck"]
    elif intent_name == "product_choice":
        summary = (f"先按{skill}需要的练习挑产品类型，再比较具体产品，暂时不能只凭年龄或宣传判断效果。"
                   "用同一个短任务试材料是否听读得懂、操作是否简单、反馈是否有帮助；官网可以核对功能，真实适配还要看孩子的试用表现。")
    causes = [
        {"cause": "练习内容与当前独立完成任务的难度可能不匹配", "why": "需要看一次实际尝试，区分太难、太容易或缺少适当提示；目前不能确认。"},
        {"cause": f"日常可能缺少直接练习{skill}的机会", "why": "现有学习方式是否让孩子真正使用这项能力，需要结合一周活动记录确认。"},
        {"cause": "反馈或重复练习方式可能还不够适合孩子", "why": "比较有提示与无提示、当日与隔日的表现，可以进一步判断。"},
    ]
    causes = [{"cause": item["cause"], "why": item["check"]} for item in reasoning["hypotheses"]]
    routes = [
        {"route_name": f"家庭微任务：练习{skill}", "mechanism": "家庭方案",
         "why_it_fits": "使用熟悉材料做短任务，便于家长先观察需求，再决定是否增加其他支持。",
         "recommended_actions": [f"从「{activity}」开始，每次只做一小步。", f"记录{observation}。", "一周后按孩子的兴趣与实际表现调整难度。"],
         "time_cost": "低", "money_cost": "低", "parent_involvement": "高", "suitability": "需进一步确认",
         "suitable_for": "能陪伴几分钟、愿意先用现有材料试一试的家庭", "limitations": "需要成人持续观察；模板任务未经过个体学习水平评估。",
         "existing_options": [], "teacher_profile": "", "evidence_ids": []},
        {"route_name": f"数字工具：提供{skill}的示范与反馈", "mechanism": "数字产品",
         "why_it_fits": "可利用可重复的材料与提示补充家庭练习，但适配性需要成人先体验。",
         "recommended_actions": [f"优先试用{digital}。", "成人先检查内容和难度，孩子每次完成一个短任务。", f"查看真实表现：{observation}，不要只看打卡数。"],
         "time_cost": "中", "money_cost": "中", "parent_involvement": "中", "suitability": "需进一步确认",
         "suitable_for": "接受数字互动、需要可重复材料与提示的家庭", "limitations": "功能、收费和适配程度需逐项确认；AI 反馈可能出错，低龄使用需成人陪伴。",
         "existing_options": [], "teacher_profile": "", "evidence_ids": []},
        {"route_name": f"真人教师：观察并调整{skill}任务", "mechanism": "真人支持",
         "why_it_fits": "真人可观察孩子完成任务的过程，调整难度、等待时间与提示，帮助家庭找到适合的练法。",
         "recommended_actions": ["试听时请老师围绕孩子熟悉的材料设计一个小任务。", "看老师是否先观察孩子如何完成，再解释如何调整。", "请老师给一个课后可延续的简短活动。"],
         "time_cost": "中", "money_cost": "高", "parent_involvement": "中", "suitability": "需进一步确认",
         "suitable_for": "希望获得个别观察与针对性反馈、时间预算允许的家庭", "limitations": "投入与课程形式有关；效果取决于教师与孩子匹配程度，需试听确认。",
         "existing_options": [], "teacher_profile": teacher, "evidence_ids": []},
    ]
    if intent_name != "product_choice":
        routes[1]["why_it_fits"] = f"只有现有材料难以提供{skill}需要的重复、示范或反馈时，才考虑用工具补这一小步。"
        routes[1]["recommended_actions"][0] = f"先按本周记录确认缺少什么支持；确实缺少时，再试{digital}。"
        routes[2]["why_it_fits"] = "只有降低难度、比较提示后仍看不清卡点，或活动持续无法开展时，再请老师观察一次真实任务。"
        routes[2]["recommended_actions"][0] = "先带一份本周任务记录；确有需要时，请老师围绕熟悉材料做一次观察。"
    else:
        routes[0]["route_name"] = "纸质材料：少量、难度合适的绘本或练习材料"
        routes[0]["why_it_fits"] = "适合先用具体画面和简短任务观察理解；家中或图书馆已有材料就能试，不必先买成套课程。"
        routes[0]["recommended_actions"] = ["先看一页或一个样章：画面能否帮助理解，孩子是否愿意参与。", f"用同一任务观察{observation}，试过后再决定是否补同难度材料。"]
        routes[1]["route_name"] = f"数字工具：补足{skill}需要的重复与反馈"
        routes[1]["why_it_fits"] = f"如果需要更容易重复的材料和即时提示，可试{digital}；这些是待核对功能，不代表已证明有效。"
        routes[1]["recommended_actions"] = ["先从官方入口核对适用年龄、试用方式、是否有成人能检查的内容与反馈。", "用相同的小任务试一次，记录孩子是否理解、提示是否有帮助，再比较使用负担。"]
        routes[2]["why_it_fits"] = "如果难点在如何带活动或判断孩子哪里没懂，真人观察可能比再买一套材料更适合；先体验一次再决定。"
    return {"problem_summary": summary, "primary_skills": primary, "secondary_skills": secondary,
            "skills_explanation": f"{skill}就是{explanation}。相关能力还需要在观察后确认。", "contexts": contexts[:3],
            "possible_causes": causes, "need_reasoning": reasoning, "priority": {"focus_now": plan["priorities"], "observe_later": ["换材料后能否独立完成", "难度与提示是否合适"]},
            "evidence_needed": [f"观察{observation}", "记录孩子愿意尝试的材料、情境与频率"], "solution_routes": routes,
            "ai_diy": {"title": f"今日 5 分钟：{activity}", "duration": "5 分钟", "steps": steps,
                       "scaffold_reduction": "先示范一次，再给选项，孩子能完成时逐渐减少提示；困难时恢复支架。",
                       "copyable_prompt": f"我的孩子{age}，目标是{skill}（{explanation}）。请为成人带领的「{activity}」生成一个 5 分钟活动，先问材料和当前水平，每次只给一个简短任务、一个示例和一个备选提示，等回应后再继续。按表现调整难度，不诊断、不代做全部任务。"},
            "next_steps": ["今天先做一次短任务，观察孩子是否愿意参与", f"本周记录{observation}", "根据记录选择继续家庭活动、数字工具或教师支持"], "evidence_ids": [],
            "practice_plan": plan}


def _student(prompt: str) -> dict:
    sections = _sections(prompt)
    inputs = _json_block(sections.get("学生输入", ""))
    mapping = _json_block(sections.get("系统初步映射（规则基线，供参考，可以修正）", ""))
    from llm.schemas import normalize_contexts
    primary = _skill_list(inputs, mapping)
    mapping = dict(mapping, primary_skills=primary)
    return {"practice_plan": practical_plan(inputs, mapping, inputs.get("need_intent") or "skill_practice", user_type="student"),
            "primary_skills": primary, "contexts": normalize_contexts(inputs.get("contexts"))[:3] or ["自主学习"],
            "evidence_ids": []}


def _educator(prompt: str, previous: dict = None, instruction: str = "") -> dict:
    sections = _sections(prompt)
    inputs = _json_block(sections.get("教育工作者输入", "") or sections.get("教育工作者原始输入", ""))
    from llm.schemas import normalize_carriers, normalize_contexts
    skills, age = _skill_list(inputs), _age(inputs)
    contexts = normalize_contexts(inputs.get("contexts")) or ["家庭固定学习"]
    carriers = normalize_carriers(inputs.get("carriers")) or ["App / 网页"]
    skill = skills[0]
    explanation, activity, steps, observation, teacher, digital = _PROFILES[skill]
    result = {
        "user_need": {"target_user": f"{age}、希望在日常场景中练习{skill}的孩子及其照护者", "age": age,
                      "core_skills": skills, "contexts": contexts[:3], "pain_point": inputs.get("pain_point") or f"希望找到适合{skill}的高频练习方式"},
        "teaching_goal": f"设计适合{age}的渐进短任务，帮助孩子{explanation}，逐步减少提示。以相近难度的新任务观察迁移，不能把打卡直接当成学习效果。",
        "solution_landscape": [
            {"mechanism": "家庭活动", "summary": f"机制示例：成人借熟悉材料带领「{activity}」，能贴近日常；持续实施的难点需要访谈验证。", "examples": [], "evidence_ids": []},
            {"mechanism": "系统课程", "summary": f"机制示例：按难度序列提供{skill}材料和反馈；是否能迁移到日常情境需要观察。", "examples": [], "evidence_ids": []},
            {"mechanism": "真人教师", "summary": "机制示例：教师通过观察任务过程给出个别支持；实际频率、投入及课后延续方式需确认。", "examples": [], "evidence_ids": []},
        ],
        "gap": ["待验证假设：已有材料与孩子当天熟悉的生活内容可能衔接不足。", "待验证假设：练习完成记录可能缺少对独立表现和提示需求的区分。", "待验证假设：家庭组织活动的准备负担可能限制持续使用。"],
        "product_direction": {"solution_mechanism": f"把熟悉的材料转成适合{age}的「{activity}」微任务，通过示范、选择提示与提示递减形成练习循环。",
                              "carrier": carriers[:2], "core_scenario": contexts[:2],
                              "ai_role": "基于成人提供的短文本生成任务、示范和分级提示；整理观察记录，学习判断由成人复核。",
                              "human_role": "成人检查材料与难度，低龄儿童由成人带领；教师可定期复核任务与表现。"},
        "mvp_spec": {"core_features": ["年龄、目标与材料设置", f"生成「{activity}」短任务", "按需显示示范与分级提示", "记录完成情况与所需提示", "查看练习回顾并调整难度"],
                     "key_pages": ["目标与年龄设置", "材料输入", "今日任务", "观察反馈", "练习回顾"],
                     "min_data": ["目标年龄与能力", "成人提供的简短文字材料", "任务完成情况与提示使用记录"],
                     "min_ai_capability": ["依据文字生成适龄短任务与示范", "生成不同强度的提示", "整理成人填写的观察记录"],
                     "not_now": ["OCR 与硬件识别", "自动诊断或宣称学习效果", "精细语音评分", "社交与复杂游戏系统"]},
        "validation_metrics": {"learning": [observation, "同难度新任务的独立完成表现；用试用前后同类任务比较"],
                               "behavior": ["每周实际尝试天数", "每次完成活动所需的成人提示次数"],
                               "product": ["任务完成率（完成次数 / 启动次数）", "从材料设置到开始任务的耗时"]}, "evidence_ids": []}
    if previous is not None:
        result = copy.deepcopy(previous)
        matched = False
        if "硬件" in instruction and any(w in instruction for w in ("不", "去掉", "取消", "移除")):
            matched = True
            result["product_direction"]["carrier"] = ["App / 网页"]
            result["product_direction"]["solution_mechanism"] += " 使用现有浏览器与文字材料即可启动。"
            result["mvp_spec"]["not_now"] = list(dict.fromkeys(result["mvp_spec"]["not_now"] + ["任何专用硬件"]))
            for key in ("core_features", "min_data", "min_ai_capability"):
                result["mvp_spec"][key] = [re.sub(r"拍照|扫描|摄像头|机器人|传感器|硬件采集", "文字输入", item) for item in result["mvp_spec"][key]]
        ages = re.findall(r"(?:\d+\s*岁?\s*[–—－~～至到-]\s*\d+\s*岁?|\d+\s*岁)", instruction)
        if ages:
            nums = [int(n) for n in re.findall(r"\d+", ages[0])]
            if all(3 <= n <= 15 for n in nums) and nums == sorted(nums):
                matched = True
                old_age = result["user_need"]["age"]
                new_age = ages[0].strip() + ("" if ages[0].strip().endswith("岁") else "岁")
                def replace_age(value):
                    if isinstance(value, str):
                        return value.replace(old_age, new_age)
                    if isinstance(value, list):
                        return [replace_age(v) for v in value]
                    if isinstance(value, dict):
                        return {k: replace_age(v) for k, v in value.items()}
                    return value
                result = replace_age(result)
                result["user_need"]["age"] = new_age
                result["mvp_spec"]["min_data"][0] = f"目标年龄（{new_age}）与能力"
                result["teaching_goal"] += " 按新的年龄段重新检查材料兴趣、文本难度与自主操作要求。"
        if "家长" in instruction and any(w in instruction for w in ("减少", "降低", "减轻", "更少", "less")):
            matched = True
            result["product_direction"]["human_role"] = "家长首次检查材料与难度，之后查看简短周回顾；低龄儿童保留必要陪伴，教师可定期复核。"
            result["product_direction"]["solution_mechanism"] += " 使用预选材料和屏内提示降低家长逐次组织任务的负担。"
            result["mvp_spec"]["core_features"] = ["首次年龄、目标与材料设置", "从预选材料自主启动短任务", "屏内示范与分级提示", "记录完成情况与提示使用", "简短周回顾"]
            result["mvp_spec"]["key_pages"] = ["首次设置", "今日任务", "自主提示", "简短周回顾"]
            result["mvp_spec"]["min_data"] = ["目标年龄与能力", "首次确认的材料文本", "任务完成与提示记录"]
            result["validation_metrics"]["behavior"] = ["每周自主启动次数", "每次活动家长直接参与时长"]
            result["validation_metrics"]["product"] = ["任务完成率（完成次数 / 启动次数）", "首次设置到启动任务的耗时"]
        if not matched:
            result["gap"] = result["gap"][:3] + [f"Demo 尚未自动实现该调整，需 Live API 或人工进一步设计：{instruction[:180]}"]
    return result


def mock_complete_json(system: str, user: str) -> dict:
    from llm.provider import LLMTimeout
    mode = (os.environ.get("ENGEDUSCOPE_LLM_MOCK_MODE") or "ok").strip().lower()
    if mode == "timeout":
        raise LLMTimeout("mock timeout")
    if mode == "schema_error":
        return {"unexpected": True}
    match = re.match(r"TASK:\s*(\S+)", user)
    task = match.group(1) if match else ""
    if task == TASK_PARENT:
        return _parent(user)
    if task == TASK_STUDENT:
        return _student(user)
    if task == TASK_EDUCATOR:
        return _educator(user)
    if task == TASK_REVISION:
        sections = _sections(user)
        return _educator(user, previous=_json_block(sections.get("当前方案（上一轮结果）", "")), instruction=sections.get("调整要求", ""))
    return {}
