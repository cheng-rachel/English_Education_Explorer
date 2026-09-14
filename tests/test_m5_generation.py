"""M5 targeted provider/revision boundaries; no external API or user data writes."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))

from llm.provider import LLMConfig, LLMSchemaError, LLMTimeout
from solution_analysis import _updated_brief, generate_solution, revise_solution
from solution_baseline import baseline_solution
from solution_context import from_scratch
from solution_schemas import validate_solution


def brief():
    value = from_scratch({"target_user": "6–8岁儿童及家长", "age_range": [72, 107],
                          "skills": ["口语表达"], "contexts": ["家庭固定学习"], "region": "中国大陆",
                          "core_need": "阅读输入较多但主动口语不足", "preferred_carriers": ["App / 网页"]})
    value["evidence_sources"] = [{"id": "E1", "title": "家庭输出观察记录（测试资料）",
                                  "content": "已尝试共读，但孩子在生活中很少主动使用英语。",
                                  "source_type": "公开用户讨论", "region": "中国大陆", "date": "2026-09-01",
                                  "url": "https://example.org/test-evidence", "credibility_level": "C"}]
    return value


class GenerationChecks(unittest.TestCase):
    def setUp(self):
        self.mock_config = patch("solution_analysis.load_config", return_value=LLMConfig(provider="mock"))
        self.mock_config.start()
        self.addCleanup(self.mock_config.stop)

    def test_cumulative_revision_preserves_evidence_original_and_scope(self):
        original = brief()
        original["source_type"] = "solve_need"
        with patch("solution_analysis.get_retriever", side_effect=AssertionError("inherited evidence")):
            record = generate_solution(original)
            frozen = deepcopy(record)
            first = revise_solution(record, "第一版只用 Web App，不使用硬件，改成10–12岁，减少家长参与")
            revised = revise_solution(first, "更适合中国家庭")
        self.assertEqual(record, frozen)
        self.assertEqual(revised["original_opportunity_brief"], record["opportunity_brief"])
        self.assertEqual(revised["evidence_sources"], record["evidence_sources"])
        self.assertEqual(revised["opportunity_brief"]["age_range"], [120, 155])
        self.assertIn("10–12岁", revised["opportunity_brief"]["target_user"])
        self.assertEqual(revised["solution"]["carrier"]["choices"], ["App / 网页"])
        self.assertEqual(len(revised["analysis_meta"]["revision_history"]), 2)
        self.assertEqual(len(revised["opportunity_brief"]["constraints"]), 2)
        self.assertTrue(revised["opportunity_brief"]["scope_notes"])
        self.assertNotIn("6–8岁", json.dumps(revised["solution"], ensure_ascii=False))
        self.assertIn("10–12", revised["solution"]["fast_prototype"]["copyable_prompt"])

    def test_revision_uses_destination_age_and_common_hardware_instruction(self):
        original = brief()
        original["preferred_carriers"] = ["AI 玩具 / 机器人"]
        revised = _updated_brief(original, "先不做硬件，年龄从6–8岁改为10–12岁")
        self.assertEqual(revised["age_range"], [120, 155])
        self.assertEqual(revised["preferred_carriers"], ["App / 网页"])
        self.assertEqual(_updated_brief(original, "改成10–12岁，不要6–8岁")["age_range"], [120, 155])

    def test_scratch_empty_or_unavailable_kb_still_generates_once_without_web(self):
        raw = brief()
        raw["evidence_sources"] = []
        for failed in (False, True):
            retriever = Mock()
            if failed:
                retriever.search.side_effect = RuntimeError("private internal response")
            else:
                retriever.search.return_value = []
            with patch("solution_analysis.get_retriever", return_value=retriever), patch("requests.post", side_effect=AssertionError("no network")):
                record = generate_solution(raw)
            self.assertEqual(retriever.search.call_count, 1)
            self.assertEqual(record["analysis_meta"]["retrieval"]["calls"], 1)
            self.assertEqual(record["evidence_sources"], [])
            self.assertEqual(record["solution"]["evidence_ids"], [])
            self.assertTrue(record["solution"]["demo_build_path"])
            self.assertNotIn("private internal response", json.dumps(record))

    def test_live_reuses_existing_http_provider_and_includes_current_evidence(self):
        raw = brief()
        fixture = baseline_solution(raw)
        cfg = LLMConfig(provider="custom", api_key="test-not-real", base_url="https://test.invalid/v1", model="test")
        seen = []

        def post(url, **kwargs):
            seen.append((url, kwargs))
            response = Mock(status_code=200)
            response.json.return_value = {"choices": [{"message": {"content": json.dumps(fixture, ensure_ascii=False)}}]}
            return response

        with patch("solution_analysis.load_config", return_value=cfg), patch("requests.post", side_effect=post):
            record = generate_solution(raw)
            revised = revise_solution(record, "第一版只用 Web App")
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0][0], "https://test.invalid/v1/chat/completions")
        prompt = seen[0][1]["json"]["messages"][1]["content"]
        self.assertIn(raw["evidence_sources"][0]["content"], prompt)
        self.assertIn("current_solution", seen[1][1]["json"]["messages"][1]["content"])
        self.assertEqual(revised["analysis_meta"]["mode"], "live")
        self.assertNotIn(cfg.api_key, json.dumps(revised))

    def test_invalid_schema_gets_one_repair_then_failures_leave_record_intact(self):
        raw = brief()
        record = generate_solution(raw)
        frozen = deepcopy(record)
        cfg = LLMConfig(provider="custom", api_key="test", base_url="https://test.invalid/v1", model="test")
        fixture = baseline_solution(raw)
        with patch("solution_analysis.load_config", return_value=cfg), patch("solution_analysis.complete_json", side_effect=[{}, fixture]) as call:
            self.assertTrue(generate_solution(raw)["solution"])
            self.assertEqual(call.call_count, 2)
            self.assertEqual(call.call_args.kwargs["retries"], 0)
        with patch("solution_analysis.load_config", return_value=cfg), patch("solution_analysis.complete_json", side_effect=LLMTimeout()) as call:
            with self.assertRaises(LLMTimeout):
                revise_solution(record, "缩小范围")
            self.assertEqual(call.call_count, 2)
        self.assertEqual(record, frozen)

    def test_schema_rejects_unusable_demo_and_filters_unknown_evidence(self):
        raw = brief()
        fixture = baseline_solution(raw)
        for key, value in (("demo_build_path", fixture["demo_build_path"][:4]), ("risks", fixture["risks"][:2])):
            invalid = dict(fixture, **{key: value})
            with self.assertRaises(LLMSchemaError):
                validate_solution(invalid, raw["evidence_sources"])
        fixture["evidence_ids"] = ["E1", "invented"]
        self.assertEqual(validate_solution(fixture, raw["evidence_sources"])["evidence_ids"], ["E1"])


if __name__ == "__main__":
    unittest.main()
