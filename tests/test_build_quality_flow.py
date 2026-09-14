"""Four Build quality cases and their evidence boundary; no live APIs or user DB writes."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from llm.provider import LLMConfig, LLMSchemaError
from solution_analysis import generate_solution, revise_solution
from solution_baseline import baseline_solution
from solution_context import from_market, from_scratch
from solution_export import to_markdown
from solution_prompts import SYSTEM, generate_prompt
from solution_schemas import validate_solution
from solution_grounding import supported_landscape


def opportunity(need="6–8岁孩子主要用单词/短语回答，希望提升完整句表达。", carriers=None):
    return from_scratch({"target_user": "6–8岁儿童及支持他们的成人", "age_range": [72, 107],
                         "skills": ["口语表达"], "contexts": ["家庭固定学习"], "region": "中国大陆",
                         "core_need": need, "preferred_carriers": carriers or ["混合 OMO"]})


def supply():
    return {"id": "E1", "title": "官方分级阅读资料", "source_type": "产品 / 机构官网", "evidence_role": "supply",
            "region": "中国大陆", "content": "该英语分级阅读材料按难度提供故事和阅读理解练习。",
            "url": "https://example.org/reading"}


class BuildQualityFlow(unittest.TestCase):
    def setUp(self):
        config = patch("solution_analysis.load_config", return_value=LLMConfig(provider="mock"))
        config.start()
        self.addCleanup(config.stop)

    def generate_inherited(self, brief):
        brief = deepcopy(brief)
        brief["source_type"] = "solve_need"
        with patch("solution_analysis.get_retriever") as retrieve, patch("requests.post") as network:
            record = generate_solution(brief)
        retrieve.assert_not_called()
        network.assert_not_called()
        self.assertEqual(record["analysis_meta"]["retrieval"]["calls"], 0)
        return record

    def test_a_one_interaction_before_omo_and_unknowns_before_diagnosis(self):
        brief = opportunity()
        brief["evidence_sources"] = [supply()]
        brief["existing_landscape"] = [{"mechanism": "真人教师", "evidence_ids": ["E1"]}]
        record = self.generate_inherited(brief)
        solution = record["solution"]
        self.assertIn(solution["solution_scope"], ("activity", "prompt_tool", "lightweight_app"))
        self.assertNotIn("混合 OMO", solution["carrier"]["choices"])
        self.assertTrue(2 <= len(solution["product_judgment"]["reasons"]) <= 4)
        self.assertIn("提示", solution["core_interaction"])
        self.assertTrue(any(word in solution["core_interaction"] for word in ("换", "新")))
        unknowns = " ".join(solution["opportunity"]["unknowns"])
        self.assertIn("词汇", unknowns)
        self.assertIn("提示", unknowns)
        self.assertNotIn("真人教师", str(solution["solution_landscape"]))
        self.assertLessEqual(len(solution["mvp"]["core_features"]), 5)
        self.assertEqual(len(solution["mvp"]["key_pages"]), 1)
        self.assertEqual(set(solution["validation_decision"]), {"continue", "adjust", "stop"})

    def test_b_human_service_is_a_real_non_app_route(self):
        record = self.generate_inherited(opportunity("孩子开口时非常紧张，需要真人教师现场观察、情绪支持和即时追问，先验证真人服务。"))
        solution = record["solution"]
        self.assertEqual(solution["solution_scope"], "service")
        self.assertTrue(any("教师" in c for c in solution["carrier"]["choices"]))
        self.assertNotIn("App / 网页", solution["carrier"]["choices"])
        self.assertIn("教师", solution["core_interaction"])
        self.assertTrue(solution["validation_decision"]["stop"])

    def test_c_simple_activity_does_not_become_a_product(self):
        record = self.generate_inherited(opportunity("只想用一次图片问答教学活动验证孩子能否独立说出一句英语，不开发软件。"))
        solution = record["solution"]
        self.assertIn(solution["solution_scope"], ("activity", "prompt_tool"))
        self.assertIn("不建议立即开发独立产品", solution["product_judgment"]["recommendation"])
        self.assertTrue(solution["mvp"]["not_now"])
        self.assertEqual(len(solution["risks"]), 3)

    def test_d_market_supply_preserved_without_turning_hypotheses_into_facts(self):
        evidence = [supply()]
        signal = {"id": "signal-1", "signal_title": "完整句迁移支持可能值得验证", "skills": ["口语表达"],
                  "age_range": [72, 107], "contexts": ["家庭固定学习"], "region": "中国大陆",
                  "unmet_need": "完整句表达迁移可能不足", "problem_summary": "短语到完整句的真实瓶颈仍待确认",
                  "analyst": {"hypothesis": "可能存在迁移支持机会，并未证实市场缺口"},
                  "existing_solutions": [{"mechanism": "真人教师", "evidence_ids": ["E1"]}],
                  "evidence_sources": evidence}
        market = {"kind": "market_research", "filters": {}, "signals": [signal], "evidence_sources": evidence,
                  "chat": {"signal-1": [{"question": "真的有缺口吗？", "answer": "资料不足，仍需用户验证。"}]}}
        original = deepcopy(market)
        brief = from_market(market)
        with patch("solution_analysis.get_retriever") as retrieve, patch("requests.post") as network:
            record = generate_solution(brief)
        retrieve.assert_not_called()
        network.assert_not_called()
        self.assertEqual(market, original)
        self.assertEqual(record["evidence_sources"], brief["evidence_sources"])
        self.assertEqual(record["opportunity_brief"]["source_context"]["analyst"], signal["analyst"])
        self.assertEqual(record["solution"]["opportunity_gap"]["status"], "hypothesis")
        self.assertIn("资料不足", record["solution"]["opportunity_gap"]["remaining_friction"])
        self.assertIn("尚待实地核验", str(record["solution"]["opportunity"]["reported_facts"]))
        revised = revise_solution(record, "第一版只用 Web App，不使用硬件")
        self.assertEqual(revised["evidence_sources"], record["evidence_sources"])
        self.assertEqual(revised["solution"]["opportunity_gap"]["status"], "hypothesis")
        self.assertIn("可能存在迁移支持机会", to_markdown(revised))

    def test_live_boundary_rejects_full_product_from_supply_and_mismatched_citation(self):
        brief = opportunity()
        brief["evidence_sources"] = [supply()]
        proposed = baseline_solution(brief)
        proposed["solution_scope"] = "lightweight_app"
        proposed["solution_landscape"] = [{"mechanism": "真人教师", "what_exists": "老师使表达显著提升",
                                           "what_remains_unresolved": "普遍缺少老师支持", "evidence_ids": ["E1"]}]
        proposed["opportunity_gap"].update(status="observed_friction", evidence_ids=["E1"], remaining_friction="已证实普遍市场缺口")
        proposed["opportunity"]["reported_facts"] = ["孩子已被确认存在句法障碍"]
        cfg = LLMConfig(provider="custom", api_key="fixture-secret", base_url="https://fixture.invalid/v1", model="fixture")
        with patch("solution_analysis.load_config", return_value=cfg), patch("solution_analysis.complete_json", return_value=proposed) as live:
            record = generate_solution(brief)
        self.assertEqual(live.call_count, 1)
        self.assertEqual(record["solution"]["solution_landscape"], [])
        self.assertEqual(record["solution"]["opportunity_gap"]["status"], "hypothesis")
        self.assertNotIn("句法障碍", str(record["solution"]["opportunity"]["reported_facts"]))
        proposed["solution_scope"] = "full_product"
        proposed["product_judgment"]["evidence_ids"] = ["E1"]
        with self.assertRaises(LLMSchemaError):
            validate_solution(proposed, brief["evidence_sources"], brief)

    def test_denied_teacher_feature_is_not_a_supported_landscape(self):
        for text in ("本产品仅提供英语分级阅读材料，不提供真人教师反馈或口语互动教学服务。",
                     "English graded readers without teacher feedback or oral interaction."):
            evidence = [dict(supply(), content=text)]
            rows = [{"mechanism": "真人教师", "evidence_ids": ["E1"]}]
            self.assertEqual(supported_landscape(rows, evidence, ["口语表达"]), [])

    def test_scratch_uses_one_lookup_and_contacts_stay_filtered(self):
        brief = opportunity()
        secret = "微信：abc_teacher123。手机：13812345678。邮箱：teacher@example.com。"
        brief["core_need"] += secret
        retriever = Mock()
        retriever.search.return_value = []
        with patch("solution_analysis.get_retriever", return_value=retriever), patch("requests.post") as network:
            record = generate_solution(brief)
        self.assertEqual(retriever.search.call_count, 1)
        network.assert_not_called()
        output = json.dumps(record, ensure_ascii=False) + to_markdown(record)
        for value in ("abc_teacher123", "13812345678", "teacher@example.com"):
            self.assertNotIn(value, output)
        self.assertIn("personal contact", SYSTEM)
        self.assertIn("solution_scope", generate_prompt(brief))


if __name__ == "__main__":
    unittest.main()
