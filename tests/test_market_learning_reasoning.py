"""Learning background stays source-grounded and outside market evidence gates."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from market_baseline import baseline_answer, baseline_market, demand_support
from market_learning_reference import apply_learning_background
from market_prompts import SYSTEM, market_prompt, chat_prompt
from market_schemas import safe_answer_for_display, safe_signal_for_display, validate_market

FILTERS = {"region": "中国大陆", "age_range": [36, 191], "skills": ["阅读理解"], "contexts": [], "audiences": []}


def reference(text, number=1):
    return {"id": f"L{number}", "title": "英语阅读理解能力发展路径", "content": text,
            "region": "general_reference", "raw_category": "learnpath", "evidence_role": "learning_reference",
            "source_type": "通用学习路径参考资料", "document_id": f"learning-{number}"}


class LearningReasoningTests(unittest.TestCase):
    def test_learning_only_can_explain_but_never_proves_demand_or_market_gap(self):
        refs = [reference("英语阅读理解包括识词解码、词汇理解和对篇章主旨的推理，需要分别观察这些环节。")]
        result = baseline_market(FILTERS, [], learning_references=refs)["signals"][0]
        self.assertEqual(result["signal_kind"], "scope_observation")
        for field in ("evidence_ids", "trend_evidence_ids", "attempted_solutions", "dissatisfaction", "existing_solutions"):
            self.assertEqual(result[field], [])
        for field in ("trend", "demand_level", "signal_status"):
            self.assertIsNone(result[field])
        self.assertFalse(demand_support(refs)["sufficient"])
        self.assertIn("尚不能确认", result["unmet_need"])
        self.assertIn("识词", result["analyst"]["interpretation"])
        self.assertNotIn("解释线索", result["analyst"]["interpretation"])
        self.assertNotIn("不能证明市场缺口", result["analyst"]["interpretation"])
        self.assertTrue(result["learning_background"]["skill_structure"])
        rendered = str(result["analyst"]) + str(result["validation_questions"])
        self.assertNotIn("换同难度", rendered)
        self.assertNotIn("减少提示", rendered)
        self.assertEqual(result["learning_references"], refs)

    def test_four_explicit_table_stages_are_grounded_and_distinguished(self):
        refs = [reference("| 年龄 | 英语能力 | 学习重点 |\n|---|---|---|\n"
                          "| 3–5岁 | 阅读理解 | 通过图画和共读理解故事中的人物与事件 |\n"
                          "| 6–8岁 | 阅读理解 | 将音形对应与识词解码用于短句理解 |\n"
                          "| 9–12岁 | 阅读理解 | 区分文章主旨与支持细节 |\n"
                          "| 13–15岁 | 阅读理解 | 根据篇章结构和文本线索进行推理 |")]
        result = apply_learning_background({"signal_kind": "scope_observation", "skills": ["阅读理解"]}, refs, FILTERS)
        background = result["learning_background"]
        self.assertEqual(background["development_notice"], "该年龄范围跨越多个发展阶段，不宜视为单一学习需求。")
        self.assertEqual([row["age_band"] for row in background["age_stages"]], ["3–5", "6–8", "9–12", "13–15"])
        self.assertTrue(all(row["evidence_ids"] == ["L1"] for row in background["age_stages"]))
        self.assertIn("图画", background["age_stages"][0]["statement"])
        self.assertIn("推理", background["age_stages"][-1]["statement"])

    def test_live_and_old_history_keep_concrete_interpretation(self):
        refs = [reference("英语阅读理解包括识词解码、词汇理解和对篇章主旨的推理，需要分别观察这些环节。")]
        raw = baseline_market(FILTERS, [], refs)
        signal = raw["signals"][0]
        signal["analyst"]["interpretation"] += "这属于学习问题的解释线索，不能证明市场缺口。"
        before = deepcopy(signal)
        live = validate_market(raw, [], FILTERS, refs)["signals"][0]
        restored = safe_signal_for_display(signal, [], FILTERS)
        chat = safe_answer_for_display(dict(signal["analyst"], limitations=[]), signal, [], "阅读理解包括哪些环节？")
        for interpretation in (live["analyst"]["interpretation"], restored["analyst"]["interpretation"], chat["interpretation"]):
            self.assertIn("识词", interpretation)
            self.assertNotIn("解释线索", interpretation)
            self.assertNotIn("不能证明市场缺口", interpretation)
        self.assertEqual(signal, before)

    def test_broad_age_label_or_missing_material_cannot_invent_development(self):
        refs = [reference("3–15岁英语阅读理解参考，介绍分级阅读指南和产品。")]
        result = apply_learning_background({"signal_kind": "scope_observation"}, refs, FILTERS)
        self.assertEqual(result["learning_background"]["development_notice"], "")
        self.assertTrue(all(not row["evidence_ids"] for row in result["learning_background"]["age_stages"]))
        self.assertEqual(result["learning_background"]["skill_structure"], [])

    def test_helper_preserves_market_decisions_and_contacts_remain_hidden(self):
        original = {"signal_kind": "demand_signal", "skills": ["阅读理解"], "evidence_ids": ["E1", "E2"],
                    "trend": None, "demand_level": None, "unmet_need": "仍需验证", "analyst": {"interpretation": "原有解释"}}
        before = deepcopy(original)
        refs = [reference("英语阅读理解需要区分文章主旨与细节。\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com")]
        result = apply_learning_background(original, refs, FILTERS)
        self.assertEqual(original, before)
        for key, value in original.items():
            self.assertEqual(result[key], value)
        for secret in ("abc_teacher123", "13812345678", "teacher@example.com"):
            self.assertNotIn(secret, str(result))

    def test_chat_and_prompts_keep_reference_lane_separate(self):
        refs = [reference("英语阅读理解包括主旨与细节理解，需要分开观察儿童的回答。")]
        signal = baseline_market(FILTERS, [], refs)["signals"][0]
        answer = baseline_answer(signal, [], "阅读理解可以分成哪些环节？", refs)
        self.assertEqual(answer["evidence"], [])
        self.assertTrue(answer["learning_background"]["skill_structure"])
        self.assertIn("learning_references", market_prompt(FILTERS, [], refs))
        self.assertIn("learning_references", chat_prompt(signal, [], "为什么", learning_references=refs))
        self.assertIn("不能放 trend_evidence_ids", SYSTEM)

    def test_spreadsheet_header_only_retains_actual_reading_sequence(self):
        refs = [reference("阅读顺序：绘本-分级-桥梁-章节-原版名著：国外年纪；"
                          "阅读顺序：绘本-分级-桥梁-章节-原版名著：RAZ级别；"
                          "列19：普通美国学生的阅读能力；列20：美国教材要求的阅读能力。")]
        background = apply_learning_background({"signal_kind": "scope_observation"}, refs, FILTERS)["learning_background"]
        self.assertEqual(len(background["skill_structure"]), 1)
        self.assertIn("绘本-分级-桥梁-章节-原版名著", background["skill_structure"][0]["statement"])
        self.assertNotIn("列20", str(background))
        self.assertNotIn("美国教材要求的阅读能力", str(background))
        self.assertTrue(all("未能对应" in stage["statement"] for stage in background["age_stages"]))

    def test_english_pdf_missing_sentence_spaces_does_not_hide_readable_statement(self):
        refs = [reference("minimum score reported for A2 Key Reading The Reading section consists of Parts 1–5 of the Reading and Writing paper."
                          "Correct answers in Parts 1–5 are worth 1 mark each.There are 30 possible marks in the Reading section."
                          "Writing The Writing section consists of Parts 6 and 7 of the Reading and Writing paper.")]
        background = apply_learning_background({"signal_kind": "scope_observation"}, refs, FILTERS)["learning_background"]
        self.assertTrue(background["skill_structure"])
        self.assertIn("The Reading section consists of Parts 1–5", background["skill_structure"][0]["statement"])
        self.assertNotIn("minimum score", background["skill_structure"][0]["statement"])
        self.assertEqual(background["development_notice"], "")

    def test_foreign_school_grade_does_not_become_a_chinese_age_stage(self):
        refs = [reference("美国幼儿园的分级阅读包括GK下的aa、A、B、C四级。")]
        background = apply_learning_background({"signal_kind": "scope_observation"}, refs, FILTERS)["learning_background"]
        self.assertTrue(background["skill_structure"])
        self.assertTrue(all(not stage["evidence_ids"] for stage in background["age_stages"]))
        english = [reference("Kindergarten reading includes picture books. Middle school reading includes chapter books.")]
        background = apply_learning_background({"signal_kind": "scope_observation"}, english, FILTERS)["learning_background"]
        self.assertTrue(all(not stage["evidence_ids"] for stage in background["age_stages"]))


if __name__ == "__main__":
    unittest.main()
