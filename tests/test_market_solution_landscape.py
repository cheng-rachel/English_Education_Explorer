"""Regression checks for accepted supply reaching the Market output."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from market_baseline import baseline_market
from market_evidence import combine_evidence
from market_quality import evidence_kind, prepare_evidence
from market_schemas import safe_signal_for_display, validate_market
from market_search_trace import build_search_trace

FILTERS = {"region": "中国大陆", "time_window": "近90天", "age_range": [84, 191],
           "skills": ["阅读理解"], "contexts": [], "audiences": []}


def source(number, content, source_type="产品 / 机构官网", **extra):
    return dict({"id": f"E{number}", "title": f"英语阅读理解资料{number}", "content": content,
                 "source_type": source_type, "region": "中国大陆", "origin": "web",
                 "url": f"https://example.org/{number}", "content_kind": "search_snippet"}, **extra)


class MarketSolutionLandscapeTests(unittest.TestCase):
    def setUp(self):
        self.sources = prepare_evidence([
            source(1, "阅读理解工具通过划线标注呈现文本中的信息线索。", title="线索阅读器"),
            source(2, "产品提供分级文本和读后提问，支持英语阅读理解练习。", title="分级阅读工具"),
            source(3, "自然拼读课程提供音形对应和合音练习，配合短文阅读理解。", title="拼读课程"),
            source(4, "研究结果显示词汇知识与英语阅读理解相关。", "学术 / 研究机构"),
        ], FILTERS)

    def assert_concrete_supply(self, signal):
        landscape = signal["existing_solutions"]
        self.assertTrue(landscape)
        prose = " ".join(item["summary"] for item in landscape)
        for detail in ("划线标注", "分级文本", "音形对应"):
            self.assertIn(detail, prose)
        self.assertNotIn("专项语言练习", prose)
        self.assertNotIn("其他", [item["mechanism"] for item in landscape])
        ids = {key for item in landscape for key in item["evidence_ids"]}
        self.assertTrue({"E1", "E2", "E3"}.issubset(ids))
        self.assertTrue(ids.issubset(signal["evidence_ids"]))
        self.assertEqual(signal["attempted_solutions"], [])
        self.assertEqual(signal["dissatisfaction"], [])
        self.assertIsNone(signal["trend"])

    def test_baseline_extracts_features_outside_fixed_taxonomy(self):
        self.assert_concrete_supply(baseline_market(FILTERS, self.sources)["signals"][0])

    def test_model_and_history_do_not_drop_uncited_accepted_supply(self):
        raw = baseline_market(FILTERS, self.sources)["signals"][0]
        raw.update(evidence_ids=["E4"], existing_solutions=[])
        before = deepcopy(raw)
        with patch("market_analysis.search_web", side_effect=AssertionError("No search")), \
             patch("market_analysis.complete_json", side_effect=AssertionError("No model")):
            self.assert_concrete_supply(validate_market({"signals": [raw]}, self.sources, FILTERS)["signals"][0])
            self.assert_concrete_supply(safe_signal_for_display(raw, self.sources, FILTERS))
        self.assertEqual(raw, before)

    def test_empty_model_citations_recover_available_supply(self):
        raw = baseline_market(FILTERS, self.sources)["signals"][0]
        raw.update(evidence_ids=[], existing_solutions=[])
        self.assert_concrete_supply(validate_market({"signals": [raw]}, self.sources, FILTERS)["signals"][0])

    def test_concrete_model_mechanism_survives_supply_only_validation(self):
        evidence = [source(1, "ReadFlow 英语阅读理解：自适应词义消歧、阅读轨迹分析与难度动态匹配。")]
        raw = baseline_market(FILTERS, evidence)
        self.assertTrue(raw["signals"][0]["existing_solutions"])
        raw["signals"][0]["existing_solutions"] = [{"mechanism": "阅读轨迹分析",
            "summary": "阅读轨迹分析与难度动态匹配。", "examples": [], "evidence_ids": ["E1"]}]
        result = validate_market(raw, evidence, FILTERS)["signals"][0]
        self.assertEqual(result["existing_solutions"][0]["mechanism"], "阅读轨迹分析")

    def test_one_local_ten_web_flow_counts_actual_supply_not_query_intent(self):
        local = source(20, "研究结果显示词汇知识与英语阅读理解相关。", "学术 / 研究机构", origin="local")
        web = [dict(ev, query_purpose="research_background") for ev in self.sources[:3]]
        web.extend(source(n, "研究结果显示词汇知识与英语阅读理解相关。", "学术 / 研究机构",
                          query_purpose="solution_supply") for n in range(4, 11))
        evidence = combine_evidence([local], web[:6], FILTERS)
        evidence = combine_evidence(evidence, web[6:], FILTERS)
        self.assertEqual(sum(ev.get("origin") == "web" for ev in evidence), 10)
        self.assertEqual(sum(ev.get("origin") == "web" and evidence_kind(ev) == "supply" for ev in evidence), 3)
        trace = build_search_trace(evidence, {"status": "success"}, web)
        self.assertEqual(trace["local_source_count"], 1)
        self.assertEqual(trace["web_source_count"], 10)
        self.assertEqual(trace["web_supply_count"], 3)
        signal = validate_market(baseline_market(FILTERS, evidence), evidence, FILTERS)["signals"][0]
        prose = " ".join(item["summary"] for item in signal["existing_solutions"])
        for detail in ("划线标注", "分级文本", "音形对应"):
            self.assertIn(detail, prose)


if __name__ == "__main__":
    unittest.main()
