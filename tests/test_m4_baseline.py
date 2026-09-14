"""M4 deterministic evidence baseline: no invented trends, experience or brands."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from market_baseline import baseline_answer, baseline_market

FILTERS = {"region": "中国大陆", "time_window": "近90天", "age_range": [72, 107],
           "skills": ["口语表达"], "contexts": ["家庭固定学习"], "audiences": ["家长"]}


def ev(number, content, source_type="公开用户讨论", region="中国大陆", title="公开阅读与口语讨论"):
    return {"id": f"E{number}", "title": title, "source_type": source_type, "region": region,
            "content": content, "time_scope": "historical", "date": "2020.05.01", "origin": "local",
            "url": f"https://fixture.invalid/{number}"}


class BaselineChecks(unittest.TestCase):
    def setUp(self):
        self.evidence = [
            ev(1, "我是一个家长。我家孩子读了两年分级阅读，在家做过亲子对话练习，但是孩子仍然不愿意主动开口说英语。"),
            ev(2, "本课程提供真人口语陪练老师，围绕熟悉材料进行对话练习。", "产品 / 机构官网", title="示例产品官网"),
            ev(3, "I am a parent. We tried phonics, but my child still cannot read independently.", region="海外 Benchmark", title="Overseas phonics discussion"),
        ]

    def test_observations_are_grounded_and_do_not_estimate_trends(self):
        signals = baseline_market(FILTERS, self.evidence)["signals"]
        self.assertTrue(1 <= len(signals) <= 2)
        signal = signals[0]
        self.assertEqual(signal["age_range"], [72, 107])
        self.assertIn("仍需核验", signal["problem_summary"])
        for key in ("trend", "demand_level", "signal_status"):
            self.assertIsNone(signal[key])
        self.assertEqual(signal["trend_evidence_ids"], [])
        self.assertIn("历史背景", signal["trend_basis"])
        self.assertEqual(signal["region"], "中国大陆")
        self.assertNotIn("E3", signal["evidence_ids"])
        self.assertIn("不作海外市场比较", signal["overseas_observation"])
        self.assertTrue(signal["attempted_solutions"])
        self.assertTrue(signal["dissatisfaction"])
        self.assertIn("读了两年分级阅读", signal["attempted_solutions"][0]["description"])
        self.assertIn("待验证", signal["opportunity_hypothesis"])
        mechanisms = {m["mechanism"] for m in signal["existing_solutions"]}
        self.assertIn("真人教师", mechanisms)
        self.assertNotIn("AI口语", mechanisms)
        self.assertIn("官网自述", str(signal["analyst"]["evidence"]))
        self.assertIn("真人教师", signal["analyst"]["interpretation"])
        self.assertIn("新图片", signal["analyst"]["hypothesis"])

    def test_official_product_title_does_not_invent_features_or_experience(self):
        evidence = [ev(1, "本页介绍英语阅读课程及适龄读物，更多细节请查看课程说明。", "产品 / 机构官网", title="Super AI Speaking Robot 产品官网")]
        filters = dict(FILTERS, skills=["阅读理解"])
        signal = baseline_market(filters, evidence)["signals"][0]
        self.assertEqual(signal["attempted_solutions"], [])
        self.assertEqual(signal["dissatisfaction"], [])
        self.assertNotIn("AI口语", str(signal["existing_solutions"]))
        self.assertNotIn("智能硬件", str(signal["existing_solutions"]))
        self.assertIn("不能认定现有方案已经失败", signal["problem_summary"])
        answer = baseline_answer(signal, evidence, "为什么现有方案没有解决这个问题？")
        self.assertIn("没有直接记录使用后不满意", answer["interpretation"])
        focused = [ev(4, "企业销售同比增长87.7%，相关硬件市场规模很大。产品提供英语口语对话练习，成人可选择熟悉话题并提供提示。",
                      "产品 / 机构官网", title="口语工具资料")]
        focused_signal = baseline_market(FILTERS, focused)["signals"][0]
        focused_answer = baseline_answer(focused_signal, focused, "这些资料说明哪些支持机制？")
        self.assertIn("口语对话练习", focused_answer["evidence"][0]["statement"])
        self.assertNotIn("87.7", focused_answer["evidence"][0]["statement"])

    def test_actual_dissatisfaction_and_missing_named_product_answers(self):
        signal = baseline_market(FILTERS, self.evidence)["signals"][0]
        answer = baseline_answer(signal, self.evidence, "现有方案为什么没有解决这个问题？")
        self.assertEqual(answer["mode"], "local_evidence")
        self.assertTrue(answer["evidence"])
        self.assertEqual(answer["evidence"][0]["evidence_ids"], ["E1"])
        self.assertIn("仍然不愿意主动开口", answer["evidence"][0]["statement"])
        for question in ("为什么伴鱼没有解决这个问题？", "伴鱼为什么没有解决？"):
            with self.subTest(question=question):
                unsupported = baseline_answer(signal, self.evidence, question)
                self.assertEqual(unsupported["evidence"], [])
                self.assertIn("伴鱼", unsupported["interpretation"])
                self.assertIn("没有", unsupported["interpretation"])

    def test_regional_phonics_observation_and_empty_evidence(self):
        filters = dict(FILTERS, region="海外 Benchmark", skills=["自然拼读"])
        signal = baseline_market(filters, self.evidence)["signals"][0]
        self.assertEqual(signal["evidence_ids"], ["E3"])
        self.assertTrue(signal["attempted_solutions"])
        self.assertTrue(signal["dissatisfaction"])
        self.assertIn("不作中国市场判断", signal["china_observation"])
        self.assertEqual(signal["existing_solutions"][0]["mechanism"], "其他")
        self.assertIn("未练过的同规则词", signal["analyst"]["hypothesis"])
        self.assertEqual(baseline_market(FILTERS, [self.evidence[2]])["signals"], [])
        self.assertEqual(baseline_market(FILTERS, []) , {"signals": []})

    def test_general_discussion_is_not_personal_trial_or_parent_identity(self):
        evidence = [ev(1, "家长经常讨论英语口语。建议家长试用数字练习，有些孩子仍然不愿开口，这不说明他们用过哪种产品。")]
        signal = baseline_market(FILTERS, evidence)["signals"][0]
        self.assertEqual(signal["attempted_solutions"], [])
        self.assertEqual(signal["dissatisfaction"], [])
        self.assertEqual(signal["audiences"], ["无法判断"])
        outcome_only = [ev(2, "我是一个家长。我发现孩子已经开口输出长句，而且用了难度较高的反问疑问句。")]
        self.assertEqual(baseline_market(FILTERS, outcome_only)["signals"][0]["attempted_solutions"], [])
        changed = copy.deepcopy(evidence)
        changed[0]["time_scope"] = "within_window"
        signal = baseline_market(FILTERS, changed)["signals"][0]
        self.assertIsNone(signal["trend"])
        self.assertIn("缺少一致采样", signal["trend_basis"])


if __name__ == "__main__":
    unittest.main()
