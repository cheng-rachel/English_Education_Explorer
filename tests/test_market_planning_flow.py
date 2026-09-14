"""Market planning/refill orchestration, using the real unchanged quality gate."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))
from llm.provider import LLMConfig
from market_analysis import analyze_market
from market_quality import source_key
from web_search.settings import SearchConfig

FILTERS = {"region": "中国大陆", "time_window": "近90天", "age_range": [84, 191],
           "skills": ["阅读理解"], "contexts": ["自主学习"], "audiences": ["家长"]}


def local_source(number=1, demand=False):
    return {"id": f"L{number}", "title": "英语阅读理解家庭记录" if demand else "英语阅读理解产品功能",
            "url": f"https://example.org/local/{number}", "region": "中国大陆", "origin": "local",
            "source_type": "公开用户讨论" if demand else "产品 / 机构官网", "time_scope": "within_window",
            "date": date.today().isoformat(), "content_kind": "local_chunk",
            "content": ("我家孩子试过分级阅读，但是英语阅读理解还是困难，换文章就看不懂。" if demand else
                        "提供英语阅读理解练习、分级阅读内容与文本提问功能，支持阅读任务。")}


def unrelated():
    return [{"title": "SAR和光学卫星哪个更先进", "url": "https://example.org/satellite", "content": "SAR光学卫星遥感数据与测量。"},
            {"title": "升學智能日程", "url": "https://example.org/calendar", "content": "學校申請日程、報名時間和升學活動安排。"},
            {"title": "数学练习工具", "url": "https://example.org/math", "content": "小学数学练习自动批改和代数几何。"}]


def response(queries, sources):
    return {"status": "success", "searched_at": date.today().isoformat(), "failures": [], "results": [
        dict(item, query=queries[index % len(queries)], content_kind="search_snippet",
             published_date=date.today().isoformat()) for index, item in enumerate(sources)]}


class MarketPlanningFlowChecks(unittest.TestCase):
    def setUp(self):
        for item in (patch("market_analysis.load_config", return_value=LLMConfig(provider="mock")),
                     patch("market_analysis.load_search_config", return_value=SearchConfig(api_key="fixture-key")),
                     patch("market_analysis.retrieve_local", return_value=([local_source()], [])),
                     patch("requests.sessions.Session.request", side_effect=AssertionError("No network in fixture"))):
            item.start()
            self.addCleanup(item.stop)

    def test_one_refill_uses_later_batches_and_preserves_intents_and_gates(self):
        seen = []
        def search(queries, filters, cfg=None):
            seen.extend(queries)
            if len(seen) <= 5:
                # Initial calls still contain no usable demand, including a
                # genuine supply result arriving in the later (fourth) query.
                incoming = unrelated() if len(seen) == 3 else [
                    {"title": "新英语阅读理解产品", "url": "https://example.org/new-product",
                     "source_type": "产品 / 机构官网", "content": "英语阅读理解产品提供分级阅读与原文线索提问功能。"}]
            else:
                incoming = [{"title": "我家孩子英语阅读理解的困难", "url": f"https://www.zhihu.com/question/{n}",
                             "content": "我家孩子试过分级阅读，但是英语阅读理解仍有困难，换了文章还是看不懂。\n微信：abc_teacher123"}
                            for n in (88, 99)]
            return response(queries, incoming)
        with patch("market_analysis.search_web", side_effect=search) as web:
            research = analyze_market(FILTERS, live_search=True)
        self.assertEqual(web.call_count, 3)
        self.assertEqual([len(call.args[0]) for call in web.call_args_list], [3, 2, 2])
        self.assertEqual(len(seen), 7)
        self.assertEqual([item["name"] for item in research["search_meta"]["rounds"]], ["initial", "demand_refill"])
        self.assertEqual(research["search_meta"]["rounds"][0]["evidence_sufficiency"]["demand_sources"], 0)
        self.assertEqual(research["evidence_sufficiency"]["demand_sources"], 2)
        self.assertTrue(research["evidence_sufficiency"]["sufficient"])
        sources = research["evidence_sources"]
        self.assertEqual(len(sources), len({source_key(item) for item in sources}))
        self.assertTrue(any(item["title"] == "新英语阅读理解产品" for item in sources))
        self.assertEqual(research["search_trace"]["web_source_count"], 3)
        self.assertEqual(research["search_trace"]["query_details"][-1]["query_purpose"], "demand_refill")
        self.assertNotIn("abc_teacher123", json.dumps(research, ensure_ascii=False))
        self.assertIn("analysis_elapsed", research["analysis_meta"])
        self.assertEqual(research["signals"][0]["signal_kind"], "demand_signal")

    def test_empty_refill_stops_and_reports_insufficiency_without_relaxing_relevance(self):
        with patch("market_analysis.search_web", side_effect=lambda queries, filters, cfg=None: response(queries, unrelated())) as web:
            research = analyze_market(FILTERS, live_search=True)
        self.assertEqual(web.call_count, 3)
        self.assertEqual(research["search_trace"]["web_source_count"], 0)
        self.assertEqual(research["evidence_note"], "近期真实需求证据不足。")
        self.assertFalse(research["evidence_sufficiency"]["sufficient"])
        for signal in research["signals"]:
            self.assertEqual(signal["signal_kind"], "scope_observation")
            for field in ("trend", "demand_level", "signal_status"):
                self.assertIsNone(signal[field])
            self.assertEqual(signal["dissatisfaction"], [])
            self.assertEqual(signal["attempted_solutions"], [])

    def test_existing_valid_demand_prevents_refill(self):
        with patch("market_analysis.retrieve_local", return_value=([local_source(), local_source(2, True)], [])), \
             patch("market_analysis.search_web", side_effect=lambda queries, filters, cfg=None: response(queries, [])) as web:
            research = analyze_market(FILTERS, live_search=True)
        self.assertEqual(web.call_count, 2)
        self.assertEqual(len(research["search_meta"]["rounds"]), 1)
        self.assertEqual(research["evidence_sufficiency"]["demand_sources"], 1)

    def test_unavailable_provider_stops_and_never_switches_engine(self):
        cfg = SearchConfig(provider="serper", api_key="fixture-serper")
        with patch("market_analysis.load_search_config", return_value=cfg), \
             patch("market_analysis.search_web", return_value={"status": "failed", "results": [], "failures": [
                 {"stage": "search", "reason": "搜索服务暂时不可用。", "url": ""}]}) as web:
            research = analyze_market(FILTERS, live_search=True)
        self.assertEqual(web.call_count, 1)
        self.assertIs(web.call_args.kwargs["cfg"], cfg)
        self.assertEqual(research["search_trace"]["provider"], "serper")
        self.assertEqual(research["search_trace"]["web_source_count"], 0)
        self.assertEqual(research["search_meta"]["status"], "failed")

    def test_no_provider_and_local_only_never_search(self):
        for configured, requested in ((False, True), (True, False)):
            with self.subTest(configured=configured, requested=requested), \
                 patch("market_analysis.load_search_config", return_value=SearchConfig(api_key="key" if configured else "")), \
                 patch("market_analysis.search_web", side_effect=AssertionError("Must remain local")) as web:
                research = analyze_market(FILTERS, live_search=requested)
            web.assert_not_called()
            self.assertFalse(research["search_trace"]["executed"])
            self.assertEqual(research["search_meta"]["queries"], [])
            self.assertEqual(research["search_meta"]["rounds"], [])
            self.assertTrue(research["signals"])


if __name__ == "__main__":
    unittest.main()
