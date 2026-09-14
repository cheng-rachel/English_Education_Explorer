"""M4 targeted A/B/D/E, real local DB copy + isolated API fixtures; no paid calls."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))

from llm.provider import LLMConfig
from market_analysis import analyze_market, follow_up
from market_baseline import baseline_market
from market_evidence import build_search_queries, date_scope, normalize_filters, retrieve_local
from market_schemas import validate_market

CASE_A = {"region": "中国大陆", "time_window": "近90天", "age_range": [72, 107],
          "skills": ["口语表达"], "contexts": ["自主学习"], "audiences": ["家长"]}
CASE_B = dict(CASE_A, region="海外 Benchmark", age_range=[60, 131], audiences=[])


class MarketChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="m4-market-")
        cls.path = Path(cls.temp.name)
        cls.database = cls.path / "market.db"
        source = ROOT / "01data/02structured/eng_eduscope.db"
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as conn:
            with sqlite3.connect(cls.database) as dest:
                conn.backup(dest)
        cls.patches = [patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(cls.database), "ENGEDUSCOPE_LLM_PROVIDER": "mock"}),
                       patch("llm.settings.CONFIG_PATH", cls.path / "ai.json"),
                       patch("web_search.settings.CONFIG_PATH", cls.path / "search.json")]
        for p in cls.patches:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):
            p.stop()
        cls.temp.cleanup()

    def test_case_a_real_local_signal_and_evidence(self):
        with patch("market_analysis.search_web", side_effect=AssertionError("local button cannot search")):
            research = analyze_market(CASE_A)
        self.assertTrue(research["signals"])
        self.assertTrue(research["evidence_sources"])
        self.assertEqual(research["analysis_meta"]["mode"], "local_evidence")
        signal = research["signals"][0]
        self.assertTrue(signal["existing_solutions"])
        self.assertTrue(signal["analyst"]["evidence"])
        self.assertTrue(signal["analyst"]["interpretation"])
        self.assertTrue(signal["analyst"]["hypothesis"])
        self.assertIsNone(signal["trend"])
        self.assertTrue(signal["trend_basis"])
        self.assertTrue(all(e["region"] == "中国大陆" and e["origin"] == "local" for e in research["evidence_sources"]))
        for e in research["evidence_sources"]:
            self.assertTrue(e["title"] and e["source_type"])
            self.assertTrue(e["url"] or e["original_path"])
            self.assertIn(e["credibility_level"], ["A", "B", "C", "待核验"])

    def test_case_b_separate_overseas_sources(self):
        research = analyze_market(CASE_B)
        self.assertTrue(research["signals"])
        self.assertEqual(research["region"], "海外 Benchmark")
        self.assertTrue(all(e["region"] == "海外 Benchmark" for e in research["evidence_sources"]))
        self.assertIn("本次未纳入", research["signals"][0]["china_observation"])

    def test_queries_cover_both_spaces_and_filters_dates(self):
        a, b = build_search_queries(CASE_A), build_search_queries(CASE_B)
        self.assertEqual(len(a), 2)
        self.assertEqual(len(b), 2)
        self.assertIn("不主动开口", a[0])
        self.assertIn("解决方案", a[1])
        for part in ("中国", "6–8", "自主学习", "家长", "口语表达"):
            self.assertIn(part, a[0])
        self.assertIn("ages 5-10", b[0])
        self.assertIn("independent learning", b[0])
        self.assertIn("teaching mechanism", b[1])
        self.assertNotEqual(a, build_search_queries(dict(CASE_A, time_window="近30天")))
        self.assertEqual(date_scope("2020.05.27", CASE_A)[0], "historical")
        self.assertEqual(date_scope("", CASE_A)[0], "unknown_date")

    def test_case_d_followup_uses_current_sources_and_unknown_brand_is_honest(self):
        research = analyze_market(CASE_A)
        signal = research["signals"][0]
        answer = follow_up(signal, research["evidence_sources"], "这个需求为什么现有产品还没有解决？")
        self.assertTrue(answer["evidence"])
        self.assertTrue(answer["interpretation"])
        valid = set(signal["evidence_ids"])
        self.assertTrue(all(set(fact["evidence_ids"]) <= valid for fact in answer["evidence"]))
        overseas = analyze_market(CASE_B)
        answer = follow_up(overseas["signals"][0], overseas["evidence_sources"], "为什么伴鱼不能解决这个问题？")
        self.assertTrue(answer["limitations"])
        self.assertTrue(any(word in answer["interpretation"] for word in ("未", "没有", "不足", "不能")))

    def test_case_e_no_search_api_and_failed_search_retain_local_evidence(self):
        with patch("web_search.provider._search_once", side_effect=AssertionError("no credential no search")):
            research = analyze_market(CASE_A, live_search=True)
        self.assertEqual(research["search_meta"]["status"], "not_configured")
        self.assertIsNone(research["search_meta"]["searched_at"])
        self.assertTrue(research["signals"])
        with patch("market_analysis.search_web", return_value={"results": [], "failures": [{"url": "", "reason": "timeout", "stage": "search"}], "searched_at": None, "status": "failed"}):
            failed = analyze_market(CASE_A, live_search=True)
        self.assertTrue(failed["signals"])
        self.assertEqual(failed["search_meta"]["status"], "failed")
        self.assertIsNone(failed["search_meta"]["searched_at"])

    def test_manual_live_search_fixture_merges_and_dates_only_on_success(self):
        fixture = {"results": [{"title": "英语口语家庭练习讨论", "url": "https://example.com/english-speaking",
                                 "content": "我是家长。我们用过英语口语 App，但是孩子只会跟读，换个问题不会主动说。",
                                 "published_date": "2026-09-12", "content_kind": "search_snippet"}],
                   "failures": [{"url": "https://example.com/english-speaking", "reason": "403，使用摘要", "stage": "fetch"}],
                   "searched_at": "2026-09-13T08:00:00+00:00", "status": "partial"}
        with patch("market_analysis.search_web", return_value=fixture) as search:
            research = analyze_market(CASE_A, live_search=True)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(search.call_args.args[1], normalize_filters(CASE_A))
        self.assertEqual(research["search_meta"]["searched_at"], fixture["searched_at"])
        self.assertTrue(any(e["origin"] == "local" for e in research["evidence_sources"]))
        self.assertTrue(any(e["origin"] == "web" and e["content_kind"] == "search_snippet" for e in research["evidence_sources"]))

    def test_live_llm_synthesis_and_chat_with_single_schema_retry(self):
        from market_evidence import combine_evidence
        local, _ = retrieve_local(CASE_A)
        evidence = combine_evidence(local, [], CASE_A)
        fixture = baseline_market(CASE_A, evidence)
        cfg = LLMConfig(provider="custom", api_key="test-not-a-real-key", base_url="https://test.invalid/v1", model="test")
        with patch("market_analysis.load_config", return_value=cfg), patch("market_analysis.complete_json", side_effect=[{"signals": "bad shape"}, fixture]) as call:
            research = analyze_market(CASE_A)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args.kwargs["retries"], 0)
        self.assertEqual(research["analysis_meta"]["mode"], "live")
        signal = research["signals"][0]
        answer = dict(signal["analyst"], limitations=["仅限当前证据"])
        with patch("market_analysis.load_config", return_value=cfg), patch("market_analysis.complete_json", return_value=answer) as call:
            response = follow_up(signal, research["evidence_sources"], "为什么现有方案没有解决？")
        self.assertEqual(response["mode"], "live")
        self.assertIn("为什么现有方案没有解决", call.call_args.args[1])
        self.assertNotIn(cfg.api_key, json.dumps(research))

    def test_unsupported_trend_is_not_invented_and_no_cross_region_signal(self):
        research = analyze_market(CASE_A)
        evidence = research["evidence_sources"]
        raw = baseline_market(CASE_A, evidence)
        raw["signals"][0].update(trend="上升", trend_evidence_ids=[e["id"] for e in evidence if e["time_scope"] == "historical"])
        self.assertIsNone(validate_market(raw, evidence, CASE_A)["signals"][0]["trend"])
        raw["signals"][0]["region"] = "海外 Benchmark"
        from llm.provider import LLMSchemaError
        with self.assertRaises(LLMSchemaError):
            validate_market(raw, evidence, CASE_A)


if __name__ == "__main__":
    unittest.main()
