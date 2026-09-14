"""Small, skill-specific practice plans; no retrieval, services or product shopping.

These are adjustable mechanism examples, not evidence of a learner's deficit or
promises of improvement. The existing provider may supply a more tailored plan.
"""
from __future__ import annotations

import re

from llm.provider import LLMSchemaError
from output_safety import sanitize_data


PRACTICE_SHAPE = {
    "bottleneck": "最值得先验证的具体卡点，不把推测当诊断",
    "priorities": ["现在先做的1–2件事"],
    "today": {"duration": "每次几分钟", "steps": ["材料与操作", "一个具体英文例子", "怎样检查"]},
    "week_plan": [{"days": "第1–2天", "actions": ["具体练什么、重复多少、怎样减少提示"]}],
    "stages": [{"period": "前2–4周", "actions": ["具体做法"], "duration": "每次几分钟、每周几次",
                "materials": ["现有材料的类型和难度"], "advance_when": ["观察到什么再前进"]}],
    "progress_signals": ["可以观察或记录的表现"],
    "increase_difficulty_when": ["什么表现出现后怎样增加一点难度"],
    "teacher_support": {"when": ["何时值得找老师观察"], "profile": "需要什么教学经验的老师，不推荐具体私人教师"},
}


# bottleneck, task steps, a transfer task, observable progress, next difficulty, teacher profile
_TASKS = {
    "听力理解": (
        "先分清是不认识内容，还是听过后抓不住意思；听懂可以用动作或选择回答，不必先会跟读。",
        ["准备熟悉的30–45秒音频和2–3个图片或物品；先看图说出主题，生词太多就换短一些的材料。",
         "先听一遍，只回答谁、在哪里或发生了什么；例如听 Put the book on the desk. 后摆放书本。",
         "第二遍只找一个没听清的线索；最后才看文字核对，记录哪一步需要重听。"],
        "换同样长度、相同主题的新音频，先听一遍再用中文说出大意或完成一个动作。",
        "相同难度的新音频中，能说出主要意思或做对动作，需要重听的次数减少。",
        "连续两次新材料能抓住大意后，只增加一句话或一个信息点，暂不同时加快语速。",
        "会用动作、图片与理解问题检查是否听懂，能调整语速和信息量的教师"),
    "听力解码": (
        "熟词可能在连续语音里辨认不出来；先比较单独听词和放进短句听的差别。",
        ["选3个已经懂意思的词和清晰音频，如 cat、cap、bag；先听词并指图。",
         "再听 I have a cat. 等短句，不看文字，指出听到的目标词；拿不准只重听相关片段。",
         "最后看文字核对，圈出刚才没听清的声音，再闭眼听一次短句。"],
        "保留同一组熟词，换一个短句，观察不看文字时还能否听出目标词。",
        "熟词换到新短句后仍能认出，能说明混淆的是哪两个声音。",
        "新短句中连续两次能辨认目标词，再增加一个词或自然语速片段。",
        "有儿童听辨与语音教学经验，能区分词义未知和声音没有听清的教师"),
    "口语表达": (
        "会跟读不等于能自己选词表达；先用熟悉内容观察没有示范时能说多少。",
        ["选今天真实做过的一件事或一张熟悉的图片，只准备3个可能用到的词。",
         "先说一句自己的意思，例如 I played with my dog.；卡住时先用关键词，再补成短句。",
         "回答一个追问，如 Where did you play?；录下或写下自己说过的一句，隔一分钟不看示例再说。"],
        "换一件真实发生的小事，用相同句型说一句，再加一个地点或感受。",
        "能主动开口表达自己的意思，提示词更少；记录独立表达的句子而不是跟读次数。",
        "连续两次能独立说出一句并回应简单追问，再增加一句原因，暂不追求更长或更快。",
        "能等待回答、组织开放式对话并逐步减少提示，重视真实表达的教师"),
    "阅读理解": (
        "先区分词句读不懂，还是读完后找不到人物、事件和原因；朗读流利不能替代理解。",
        ["选大部分词都认识的一小段故事或课内短文；先看标题，猜它要讲什么。",
         "读后只答两个问题：Who is the story about? 和 What happened?；每个答案指向一句原文。",
         "圈出 but、because 等线索，选一个为什么的问题，说出理由；最后用一句话概括，允许先用中文。"],
        "选主题相近的新短文，自己写人物、事件、原因三格，并给一个答案划出原文依据。",
        "不靠提示能概括主要事件，回答时能指出支持答案的原文，遇到不懂处会回读。",
        "连续两篇同难度新短文能独立概括并找对线索，再增加一小段，暂不同时增加生词。",
        "能区分词汇、解码与篇章理解，用原文线索和思考过程指导阅读的教师"),
    "写作表达": (
        "先看有没有明确想表达的意思，再看句子如何连接；不要一开始就同时修改所有错误。",
        ["选熟悉主题，如今天的一件事；先列谁、做什么、感受三个关键词。",
         "写2–3句初稿，例如 I went to the park. I saw a dog. It was fun.，先保证别人看得懂。",
         "读一遍，只改一个问题：信息是否缺失或句子是否说清；标出自己修改的一处并说明理由。"],
        "换一个熟悉主题，保留三格提纲，独立写一小段后再检查意思与一个语言点。",
        "能从关键词写成连贯句子，读者能明白主要意思，并能自己解释一次修改。",
        "连续两次小段落都能表达完整事件，再增加一句原因或感受，暂不要求篇幅翻倍。",
        "先帮助组织意思，再针对少量问题反馈、让学生自己修改的写作教师"),
    "单词拼写": (
        "先看错误来自音和字母对应，还是看过后无法独立回想；机械抄写次数不能说明记住了。",
        ["选3个已懂意思的短词，如 cat、ship、park；听读并圈出容易混的字母组合。",
         "盖住原词，听一个词后自己写；核对时只标不同处，说出对应的声音或词块。",
         "做一分钟别的事后再写一次；把仍不确定的词留给隔天复习，不连续抄一整页。"],
        "隔一天不看范例写同一组词，再把其中一个词用进自己的短句。",
        "隔天仍能独立写出，且能发现并修正同类错误，而不只是当时照抄正确。",
        "隔天两次都能独立写出并使用后，加1–2个具有相同音形规律的新词。",
        "能结合音形对应与提取练习分析拼写错误，而不只要求反复抄写的教师"),
    "词汇量扩展": (
        "认识中文意思不等于隔天能想起、在句子里认出；先把少量词连到具体情境。",
        ["从正在读的材料中只选3个有用词，配一个图片、动作或自己的生活例子。",
         "看图回想词，再把一个词放进简单句，如 I carry my bag.；不记得时再看答案。",
         "隔几分钟遮住词重试，记录哪些能自己想起；明天先复习这3个词再加新词。"],
        "在另一句话或真实生活里认出、使用这3个词；区分看着认识和不看能想起。",
        "隔天能通过图片想起词，在不同句子里也懂意思，并愿意用一个词表达。",
        "连续两次隔天能回想并在新句子里理解，再添加2–3个词，仍保留旧词复习。",
        "会用语境、间隔回想和多次使用来教词汇，能调整词量的教师"),
    "自然拼读": (
        "学过字母发音后，还要练把声音合起来，再把拼出的词连到意思；先观察卡在哪一步。",
        ["用已学过的字母音组成3个短词，如 cat、mat、sat；逐音指读后把声音连起来。",
         "读一个新排列的短词，不先播放答案；不会就恢复逐音提示，避免只背整词外形。",
         "读一条只含已学规律的短句，如 The cat sat.，用图片或动作说明意思。"],
        "用相同字母音换一个没练过的短词，再读含这些规律的极短故事并说出意思。",
        "能拼出没背过但规则已学过的短词，读短句时也能说明意思。",
        "连续两次能独立拼出新组合并理解短句后，再引入一个新字母组合，不急着加长篇幅。",
        "能观察语音意识、拼合与阅读理解之间的连接，使用可解码短文的教师"),
    "语法知识": (
        "会背规则不等于能在自己的句子里选择形式；先只练一个意思与形式的对应。",
        ["选当前学过的一个语法点，例如第三人称单数；比较 I play. 与 She plays. 谁发生了变化。",
         "用熟悉人物写或说3个真实句子，如 My brother likes milk.；每句先想意思，再检查一个变化。",
         "隔开几分钟换一个人物重说一句；若出错先自己找原因，再核对课本例句。"],
        "在新人物或新场景里使用同一个语法点，判断什么时候需要变化、什么时候不用。",
        "不看规则也能在新句子里作出选择，并能用简单话说明为什么。",
        "连续两次新场景能正确表达并解释选择，再加入一个对照情境，暂不同时增加多个规则。",
        "把语法放在意思和情境中教学，能用对比和迁移任务检查理解的教师"),
    "跨学科素养": (
        "先分清学科概念没有理解，还是英语挡住了表达；可以先用中文、图示说明想法。",
        ["选一个已学过的安全小观察，如比较两片叶子的大小，准备 big、small 等熟词。",
         "先画或用中文说发现，再用一句英语记录，如 This leaf is bigger.，不追求长句。",
         "换一组物品再比较，检查概念是否正确，再只改一个英语表达问题。"],
        "换熟悉材料做同样的比较，用图片加一句英语说明发现和理由。",
        "能解释观察结果，并把熟悉英语用于新的材料，分开记录概念理解与表达提示。",
        "连续两次新材料能解释结果后，增加一个比较维度或一句理由，不同时加难概念与语言。",
        "能把儿童学科活动与英语提示结合、区分概念理解和语言困难的教师"),
}


def _age_months(inputs):
    age = inputs.get("age")
    if isinstance(age, dict):
        if type(age.get("age_months")) is int:
            return age["age_months"]
        if type(age.get("years")) is int:
            return age["years"] * 12 + int(age.get("months") or 0)
    if type(inputs.get("age_months")) is int:
        return inputs["age_months"]
    match = re.search(r"(\d{1,2})\s*岁", str(age or ""))
    return int(match[1]) * 12 if match else None


def _beginner_plan(months):
    young = months is None or months < 72
    duration = "每次5–8分钟，每周4–5天；孩子疲倦或拒绝时提前结束" if young else "每次8–10分钟，每周4–5天，先少量重复"
    return {
        "bottleneck": "零基础先建立声音和意思的联系，让英语出现在能看懂、愿意参与的小情境里；暂不把不开口看成能力问题。",
        "priorities": ["先听懂并愿意回应几个熟悉的生活表达", "固定一个轻松的短时段，重复比一次学很多更合适"],
        "today": {"duration": duration,
                  "steps": ["准备现有玩具或书本，再选一段动作清楚、句子反复的短儿歌；家长先听懂要表达什么。",
                            "用1–2分钟边做边说，如 Open the book. / Close the book.，让孩子只做动作，不要求跟读。",
                            "再用2–3分钟一起看一页图片或听同一首儿歌，指着实物重复一句 Look! A ball.；不要逐词考中文。",
                            "结束前用1分钟让孩子选一次或做一次动作；记录是否愿意参加、是否需要手势，肯定尝试。"]},
        "week_plan": [
            {"days": "第1–2天", "actions": ["在同一生活时段重复 Open / Close the book.，配动作；每次只用两句话。"]},
            {"days": "第3–4天", "actions": ["保留熟悉儿歌或绘本，在收玩具时加一句 Put it here.；先示范，再等孩子行动。"]},
            {"days": "第5–7天", "actions": ["换一本书或一个玩具试同样指令；用1分钟记录孩子愿意参与的材料和不靠手势也听懂的表达。", "安排休息或孩子自选重温，不用补打卡。"]},
        ],
        "stages": [
            {"period": "前2–4周", "duration": duration,
             "materials": ["1–2首动作和画面能解释意思、句子反复的短儿歌", "2–3本每页一句、图片清楚的短绘本，优先用家中或图书馆已有材料"],
             "actions": ["每天只安排一个短活动，把同一材料看听多次。", "把 Open the book. / Wash your hands. / Put it here. 放进生活，先做动作再等孩子回应。", "记录孩子是否理解、愿意参与，以及需要多少手势提示；本周先稳定这一个活动。"],
             "advance_when": ["孩子通常愿意参与，并能在熟悉情境中听懂几句表达、用动作回应。", "换一个物品后仍能理解，减少手势也能尝试；没达到就重复这一阶段，不按日历硬推进。"]},
            {"period": "第4–8周（按表现推进）", "duration": "每次8–10分钟以内，每周4–5天；保留熟悉活动和生活中1分钟的小使用",
             "materials": ["保留原有儿歌与绘本，逐步加同主题、句型相近的新故事", "玩具、餐具、衣物等现有物品，用于选择和请求"],
             "actions": ["从熟悉的句子开始给选择，如 A red cup or a blue cup?，允许指物、单词或短句回答。", "孩子愿意时示范 I want the red cup.，下一次先等待，不要求完整复述。", "把学过的表达换到新物品或新地点，观察是否仍懂意思。"],
             "advance_when": ["能把熟悉表达用到稍新的情境，并出现自发回应或主动表达。", "之后每次只增加一个词或一句短句；字母音与拼读是否适合开始，要结合听懂程度和兴趣再决定。"]},
        ],
        "progress_signals": ["愿意靠近、参与或主动选同一材料，而不是只看完成了多少页。", "听到熟悉表达后，不靠完整示范也能做动作或选择。", "换一个物品仍能理解；出现模仿、单词回应或自发表达都可记录，不催开口。"],
        "increase_difficulty_when": ["在两次不同活动里都能轻松回应后，只增加一句或一个物品；不会时退回熟悉内容。", "2–4周和4–8周只是检查窗口，不是必须达到某等级的期限。"],
        "teacher_support": {"when": ["尝试降低难度和缩短时间后，家长仍难以判断材料是否适合。", "持续数周活动都难以开展，希望有人观察互动并调整做法。"],
                            "profile": "有低龄英语启蒙经验，会用动作、游戏和共读观察理解，尊重孩子回应节奏、并能示范家长怎样配合的教师"},
    }


def _reading_to_speaking(inputs, intent):
    text = " ".join(str(inputs.get(key, "")) for key in ("description", "problem", "pain_point", "background"))
    return intent == "diagnose_bottleneck" and bool(re.search(r"阅读|分级|读得|读的", text)) and bool(
        re.search(r"不开口|不主动说|不会主动说|不说|不愿说|口语|主动表达", text))


def parent_reasoning(inputs, mapping, intent):
    """Separate the parent's report from possible explanations and small checks."""
    inputs, mapping = sanitize_data(inputs or {}), sanitize_data(mapping or {})
    intent = intent.get("primary_intent", "") if isinstance(intent, dict) else str(intent or "")
    description = str(inputs.get("description") or inputs.get("problem") or inputs.get("background") or "").strip()
    facts = [f"你提供的情况：{description[:240]}"] if description else ["目前只有年龄与关注能力，还没有一次具体学习过程的记录。"]
    if _reading_to_speaking(inputs, intent):
        hypotheses = [
            {"cause": "熟词可能认得出，却还不能主动想起来", "check": "用读过故事里的3个熟悉物品，只给图片，等孩子自己说词；之后再给两个词选项比较。", "if_observed": "如果选得对但自己想不起，先练看图回想一个熟词，隔几分钟换图再试。"},
            {"cause": "可能想得到词，还需要帮助把词连成一句话", "check": "能说出物品名后，问一个真实问题；比较不给句型与只给 I want… 开头时的表现。", "if_observed": "如果给句子开头才说得出，就保留一个开头，下一次逐步减少提示。"},
            {"cause": "可能习惯跟读，缺少不看范例自己回答的练习", "check": "示范一句后隔一分钟换图片再问；先等5秒，再按需给选项，比较与立即跟读的区别。", "if_observed": "如果只能立即跟读，先把等待与延后重试加入活动，记录独立表达而非跟读次数。"},
            {"cause": "日常表达机会或换场景使用的机会可能不足", "check": "先看一周是否有真正需要孩子选择或请求的时刻，再把书中熟句换到选玩具等生活场景。", "if_observed": "如果只在读书时会说，先每天保留一次真实选择，接受单词回答，再慢慢接成短句。"},
        ]
        confirm = ["“阅读不错”指朗读流利、理解内容，还是能回答熟悉的问题？", "在愿意参与的场景里，不给完整示范时，孩子能独立说词还是短句？"]
    else:
        skills = mapping.get("primary_skills") or ["当前能力"]
        skill = skills[0]
        hypotheses = [
            {"cause": "材料难度可能还没有对准当前能独立完成的水平", "check": f"选一小段熟悉材料，做一个{skill}任务，记录卡在内容、操作还是表达。", "if_observed": "如果内容本身就不懂，先缩短材料、减少新信息，再试相同任务。"},
            {"cause": "可能需要更清楚的提示，或更多独立尝试的机会", "check": "比较不给提示、给一个选项、示范一次时的表现，不根据一次失败下结论。", "if_observed": "如果提示后能完成，就先保留最少够用的提示；隔天再检查能否减少。"},
        ]
        confirm = ["哪类材料愿意参与、每次能轻松做多久？", "相同难度换一份新材料后，是否仍能完成？"]
    return sanitize_data({"reported_facts": facts, "hypotheses": hypotheses, "to_confirm": confirm})


def _listening_student_plan():
    return {
        "bottleneck": "听不懂可能是词句本身不熟，也可能是熟词连成语音后认不出来。先比较不看文本和看过文本后能听懂多少，别急着把整项听力都判成差。",
        "priorities": ["先用一段短音频分清：内容不懂，还是声音没认出来", "这一周只练抓大意和关键词，记录需要重听几次"],
        "today": {"duration": "今天20分钟；用一段30–60秒、附文本且大部分词认识的音频", "steps": [
            "2分钟｜第一次听：先听一遍，不看文本，只回答谁、在哪里、发生了什么；听完先用中文记一句大意。",
            "4分钟｜第二次抓关键词：再听同一段，记3个左右关键词和一个漏听位置，不逐词抄写。",
            "5分钟｜对照文本：确认刚才漏的是不认识的词，还是认识却没听出；只查影响大意的1–2处，例如 last night。",
            "5分钟｜再听：先重听漏听的小段，再关掉文本完整听一次，检查能否连上意思。",
            "4分钟｜简单复述：用1–2句话说出主要意思，如 He went to the park.；说不出来时可先用中文，记录还漏了什么。"]},
        "week_plan": [
            {"days": "第1–2天", "actions": ["每天按20分钟步骤练一段；第二天先不看文本重听旧材料，再比较漏听点。"]},
            {"days": "第3–4天", "actions": ["换同主题、同长度的新音频，继续记录第一遍大意和第二遍关键词；不要同时增加语速与生词。"]},
            {"days": "第5–7天", "actions": ["选一段未练过但同难度的音频，不看文本说大意；比较第一天的重听次数与遗漏。", "其余时间安排一次喜欢的重听和休息，无需补做更长任务。"]},
        ],
        "stages": [],
        "progress_signals": ["第二遍能比第一遍补出更多关键信息，而不只是认出更多孤立单词。", "换同难度新音频，关掉文本仍能用1–2句话复述大意，所需重听次数减少。", "能说清漏听来自生词、声音连在一起没认出，还是抓不住句子意思。"],
        "increase_difficulty_when": ["连续两段同难度新音频都能抓住大意并核对关键细节后，只增加10–15秒长度，或一点语速，二选一。", "如果看文本仍有很多句子不懂，先换更熟悉、更短的内容，不继续堆听力时长。"],
        "teacher_support": {"when": ["按较短材料练一周后，仍分不清是词句不懂还是声音没听清。", "反复降低难度后仍无法完成小任务，或压力让你不愿继续尝试。"], "profile": "能看你的漏听记录、区分词汇与听辨困难，并示范怎样听一句、核对和复述的英语教师"},
    }


def _reading_to_speaking_plan():
    plan = {
        "bottleneck": "读得不错和主动说出自己的意思是两项不同的任务，目前还不能从“不常开口”确定原因。先用熟悉内容比较词语回想、句子组织及有无提示的表现，再决定练什么。",
        "priorities": ["先确认“读得不错”是否也包括理解内容，再观察不用示范能说多少", "只选最明显的一个卡点练一周，不同时增加新词和长句"],
        "today": {"duration": "今天8–10分钟，用孩子读过并理解的一个短故事和家中玩具", "steps": [
            "2分钟｜请孩子用中文说故事大意或指图解释，确认理解；随后指3个熟悉物品，等孩子自己想词。",
            "2分钟｜给一次真实选择，如选杯子，先等5秒；没回应再给 red or blue?，比较无提示与有选项。",
            "3分钟｜能说词就试一个句子开头 I want…；隔一分钟换物品再问，观察是能自己组织还是只会立即跟读。",
            "1–3分钟｜记录最需要的提示，在生活里再给一次相同请求机会；孩子不愿参与就结束，不把拒绝当成能力证据。"]},
        "week_plan": [
            {"days": "第1–2天", "actions": ["按今天步骤比较词、句子和提示需求；两天只确认一个最明显卡点。"]},
            {"days": "第3–4天", "actions": ["如果想不起熟词，练看图回想；如果有词连不成句，保留一个句子开头；如果只能跟读，隔一分钟换图再试。", "每天5–8分钟，只选对应的一种练法。"]},
            {"days": "第5–7天", "actions": ["把熟悉表达换到选玩具、喝水或收物品的生活时刻，减少一次提示。", "比较是否出现独立词语、短句或请求；其余时间重温或休息。"]},
        ],
        "stages": [],
        "progress_signals": ["相同难度的新情境里，能独立说出词或短句，所需选项、句子开头或完整示范减少。", "出现一次为了表达真实选择或请求而开口，不只是在指令下跟读。"],
        "increase_difficulty_when": ["两次不同情境都能不靠完整示范表达后，再增加一个信息点，例如颜色或地点。", "若增加难度后只剩跟读，就回到已能独立表达的短句，先换场景再加长。"],
        "teacher_support": {"when": ["用熟悉、理解的内容比较一周后，仍看不清卡在词、句子还是提示。", "不同轻松场景都难以开展互动，希望老师观察一次真实任务，而非再增加固定课程量。"], "profile": "能用开放式选择和追问观察主动表达、等待孩子回答，并逐步减少提示的儿童英语教师"},
    }
    return plan


def practical_plan(inputs, mapping, intent, user_type="parent"):
    """Return a concrete, safe plan using the current skill and stated learning intent."""
    from llm.schemas import normalize_skills

    inputs, mapping = sanitize_data(inputs or {}), sanitize_data(mapping or {})
    intent = intent.get("primary_intent", "") if isinstance(intent, dict) else str(intent or "")
    months = _age_months(inputs)
    if user_type == "parent" and intent == "getting_started":
        return validate_practice_plan(_beginner_plan(months))
    if user_type == "parent" and _reading_to_speaking(inputs, intent):
        return validate_practice_plan(_reading_to_speaking_plan())
    skills = normalize_skills(mapping.get("primary_skills") or inputs.get("skills") or inputs.get("skill") or [])
    skill = skills[0] if skills else ("阅读理解" if user_type == "student" else "听力理解")
    if user_type == "student" and skill == "听力理解" and intent == "skill_practice" and (months is None or months >= 108):
        return validate_practice_plan(_listening_student_plan())
    bottleneck, steps, transfer, progress, increase, teacher = _TASKS[skill]
    duration = "每次10–12分钟" if months is None or months >= 108 else "每次5–8分钟"
    beginner = user_type == "parent" and months is not None and months < 72
    if beginner:
        # Preschool practice keeps the same skill focus but adults supply text/audio.
        steps = ["家长负责读文字或播放熟悉材料；只选一个小任务，孩子可以指图、行动或口头回答。", *steps]
    elif user_type == "student" and months is not None and months < 96:
        steps = ["如果读题或操作有困难，请家长帮忙准备材料和读题，你来尝试回答。", *steps]
    plan = {
        "bottleneck": bottleneck,
        "priorities": [f"先把一个熟悉的{skill}任务做明白", "用隔天或换材料后的独立表现判断下一步，不只看练习次数"],
        "today": {"duration": duration, "steps": list(steps)},
        "week_plan": [
            {"days": "第1–2天", "actions": [f"按今天的步骤，每天安排{duration.replace('每次', '')}；先做一次并记下需要的提示。", "第二天先不看示例重试，再核对一个最困惑的地方。"]},
            {"days": "第3–4天", "actions": [transfer, "先自己尝试，再按需看提示；一次只改一个问题。"]},
            {"days": "第5–7天", "actions": ["选同难度的新材料做一次，和第一天比较所需提示；其余时间安排一次喜欢的重温和休息。", f"记录：{progress}"]},
        ],
        "stages": [],
        "progress_signals": [progress, "遇到困难时能指出具体卡在哪一步，而不只说整项能力都不会。"],
        "increase_difficulty_when": [increase, "新难度让理解或参与明显下降时，退回上一档，再检查词汇、材料或提示是否合适。"],
        "teacher_support": {"when": ["降低难度并重复一周后，仍不清楚总是卡在哪一步，希望获得一次具体观察。", "持续几周都难以完成很小的任务，或练习压力明显影响继续尝试。"], "profile": teacher},
    }
    if intent in {"learning_path", "overview", "overall_review"}:
        plan["priorities"] = [f"先用{skill}的一个小任务确定合适起点", "本周只稳定一种练习，再按观察结果决定下一项能力"]
    if intent in {"low_motivation", "motivation", "engagement"}:
        plan["priorities"] = ["先让孩子在两种熟悉材料中选一种，缩短任务并保留停止的选择", f"把{skill}放到孩子愿意参与的真实小情境里"]
        plan["today"]["duration"] = "先试3–5分钟，孩子不愿继续就结束，换时间再试"
        plan["progress_signals"].insert(0, "愿意自己选材料、再次尝试或主动开始；不把不愿意直接解释为懒惰。")
    if intent == "diagnose_bottleneck":
        plan["priorities"] = [f"先在一个{skill}小任务中定位卡住的那一步", "比较有提示与无提示的表现，再决定练习内容"]
    elif intent == "progress_check":
        plan["priorities"] = ["用同难度的新任务检查是否能独立完成，避免把记住旧题当成进步", "只记录一个能力表现和所需提示，一周后再比较"]
    elif intent == "teacher_support":
        plan["priorities"] = [f"先留下一个{skill}实际尝试，方便老师看到卡点", "观察老师如何调整任务与反馈，再判断支持是否合适"]
    elif intent == "product_choice":
        example = "例如读后问 Who is the story about?。" if skill == "阅读理解" else ""
        plan["priorities"] = [f"先明确{skill}到底需要哪种练习与反馈", "用同一个小任务试现有方式，观察能否独立完成，再决定是否需要工具"]
        plan["bottleneck"] = f"先区分缺的是{skill}材料、练习机会还是反馈，再选产品类型；产品功能介绍本身不能证明孩子用了会进步。"
        plan["today"] = {"duration": "今天先试10分钟，不需要先购买", "steps": [
            f"2分钟｜从现有材料选一个{skill}小任务，写下目前缺少材料、重复播放还是具体反馈。",
            "3分钟｜查看候选产品的官方示例或试用：内容大部分是否能理解，操作与提示是否适合这个任务。",
            "5分钟｜用相同的小任务实际试一次，只记录理解情况、提示是否有用和操作负担；不要把完成动画或打卡当效果。"]}
        plan["week_plan"] = [
            {"days": "第1–2天", "actions": ["用已有材料建立一次观察记录，再核对是否真的缺少工具支持。" + example]},
            {"days": "第3–4天", "actions": ["如有需要，试一个正式产品的同类短任务；比较内容难度和使用负担，不按宣传效果排序。"]},
            {"days": "第5–7天", "actions": ["换一份同难度材料检查能否独立完成，再决定继续现有方式、换材料或请老师观察。"]},
        ]
    return validate_practice_plan(plan)


def validate_practice_plan(data):
    """Validate the bounded UI contract without inventing or repairing missing actions."""
    def obj(value, name):
        if not isinstance(value, dict):
            raise LLMSchemaError(f"{name} must be an object")
        return value

    def text(value, name):
        if not isinstance(value, str) or not value.strip():
            raise LLMSchemaError(f"{name} must contain text")
        return value.strip()

    def items(value, name, minimum=1, maximum=8):
        if not isinstance(value, list) or not minimum <= len(value) <= maximum:
            raise LLMSchemaError(f"{name} must contain {minimum}–{maximum} items")
        return [text(item, name) for item in value]

    data = obj(sanitize_data(data), "practice_plan")
    today = obj(data.get("today"), "today")
    support = obj(data.get("teacher_support"), "teacher_support")
    week = data.get("week_plan")
    stages = data.get("stages")
    if not isinstance(week, list) or not 1 <= len(week) <= 7:
        raise LLMSchemaError("week_plan needs 1–7 day groups")
    if not isinstance(stages, list) or len(stages) > 4:
        raise LLMSchemaError("stages must be an array of at most 4 stages")
    result = {
        "bottleneck": text(data.get("bottleneck"), "bottleneck"),
        "priorities": items(data.get("priorities"), "priorities", 1, 2),
        "today": {"duration": text(today.get("duration"), "today.duration"), "steps": items(today.get("steps"), "today.steps", 2, 6)},
        "week_plan": [], "stages": [],
        "progress_signals": items(data.get("progress_signals"), "progress_signals", 1, 5),
        "increase_difficulty_when": items(data.get("increase_difficulty_when"), "increase_difficulty_when", 1, 5),
        "teacher_support": {"when": items(support.get("when"), "teacher_support.when", 1, 4), "profile": text(support.get("profile"), "teacher_support.profile")},
    }
    for item in week:
        item = obj(item, "week_plan item")
        result["week_plan"].append({"days": text(item.get("days"), "week_plan.days"), "actions": items(item.get("actions"), "week_plan.actions", 1, 5)})
    for item in stages:
        item = obj(item, "stage")
        result["stages"].append({"period": text(item.get("period"), "stage.period"), "duration": text(item.get("duration"), "stage.duration"),
                                 "actions": items(item.get("actions"), "stage.actions", 1, 5), "materials": items(item.get("materials"), "stage.materials", 1, 5),
                                 "advance_when": items(item.get("advance_when"), "stage.advance_when", 1, 4)})
    return result
