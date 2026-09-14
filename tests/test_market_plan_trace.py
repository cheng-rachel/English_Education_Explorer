"""Search-plan trace rendering and History checks, without live requests."""
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))

from streamlit.testing.v1 import AppTest
from market_search_trace import build_search_trace, search_trace_for


def fixture(provider="serper"):
    queries = [
        {"query": "孩子 英语 阅读理解 看不懂 怎么办", "query_purpose": "demand_problem", "language": "zh", "round": "initial", "query_language_strategy": "zh_first", "evidence_role": "demand"},
        {"query": "英语 阅读训练 家长 经验", "query_purpose": "attempted_solution", "language": "zh", "round": "initial"},
        {"query": "英语 分级阅读 学了还是不会 阅读理解", "query_purpose": "dissatisfaction", "language": "zh", "round": "initial"},
        {"query": "英语 阅读理解 AI 产品", "query_purpose": "solution_supply", "language": "zh", "round": "initial"},
        {"query": "adolescent EFL reading comprehension difficulties", "query_purpose": "research", "language": "en", "round": "initial", "query_language_strategy": "bilingual"},
        {"query": "初中生 英语 阅读理解 学了还是不会", "query_purpose": "demand_refill", "language": "zh", "round": "demand_refill"},
    ]
    sources = [{"id": "E1", "title": "本地阅读资料", "document_id": "local-1", "origin": "local", "content_kind": "local_chunk"},
               {"id": "E2", "title": "英语阅读练习家庭反馈", "url": "https://example.org/experience?utm_source=test#:~:text=reading", "origin": "web", "content_kind": "search_snippet"}]
    checks = {"demand_sources": 1, "supply_sources": 1, "independent_sources": 2, "recent_demand_sources": 1, "source_diversity": True, "sufficient": True}
    meta = {"provider": provider, "status": "success", "requested": True, "searched_at": date.today().isoformat(),
            "queries": [query["query"] for query in queries], "query_details": queries,
            "rounds": [{"name": "initial", "queries": queries[:-1], "status": "success", "evidence_sufficiency": dict(checks, demand_sources=0, sufficient=False)},
                       {"name": "demand_refill", "queries": queries[-1:], "status": "success", "evidence_sufficiency": checks}]}
    return {"kind": "market_research", "filters": {"region": "中国大陆", "time_window": "近90天", "age_range": [84, 180], "skills": ["阅读理解"], "audiences": ["家长"], "contexts": ["自主学习"]},
            "region": "中国大陆", "time_window": "近90天", "signals": [], "evidence_sources": sources,
            "search_meta": meta, "search_trace": build_search_trace(sources, meta, sources[1:])}


def visible(app):
    return "\n".join(str(item.value) for kind in ("markdown", "caption", "info", "warning") for item in app.get(kind))


class MarketPlanTraceChecks(unittest.TestCase):
    def render(self, research, script=None):
        script = script or 'from market_session import render_search_status\nrender_search_status(st.session_state["fixture"])'
        app = AppTest.from_string('import sys\n' + f'sys.path.insert(0, {str(ROOT / "03app")!r})\n' +
                                 'import streamlit as st\n' + script, default_timeout=15)
        app.session_state["fixture"] = deepcopy(research)
        with patch("requests.sessions.Session.request", side_effect=AssertionError("render/restore cannot search")), \
                patch("web_search.settings.load_config", side_effect=AssertionError("must use saved provider")), \
                patch("knowledge.retrieval.get_retriever", side_effect=AssertionError("render/restore cannot retrieve")):
            app.run()
        self.assertFalse(app.exception, [item.message for item in app.exception])
        return app

    def test_plan_trace_has_provider_purpose_language_and_existing_statuses(self):
        research = fixture()
        app = self.render(research)
        output = visible(app)
        for text in ("搜索服务：Serper", "需求问题 · 中文", "已有尝试 · 中文", "使用阻力 · 中文", "市场供给 · 中文",
                     "研究背景 · English", "需求侧补搜 · 中文", "仅使用搜索摘要", "本地知识库：1 条", "本轮联网搜索：1 条"):
            self.assertIn(text, output)
        for query in research["search_trace"]["queries"]:
            self.assertIn(query, output)
        self.assertIn("[查看原文](<https://example.org/experience>)", output)
        self.assertNotIn("https://", re.sub(r"\[[^\]]+\]\(<https?://[^>]+>\)", "", output))
        self.assertFalse(next(item for item in app.expander if item.label == "查看本次联网搜索").proto.expanded)

    def test_trace_only_records_public_plan_fields_and_still_filters_contacts(self):
        research = fixture()
        meta = research["search_meta"]
        meta["query_details"][0].update(api_key="SECRET_API_KEY", request_body={"secret": "SECRET_REQUEST"}, prompt="SECRET_PROMPT")
        meta["rounds"][0].update(error_traceback="SECRET_TRACEBACK")
        meta["rounds"][0]["evidence_sufficiency"]["raw_response"] = "SECRET_RESPONSE"
        meta["query_details"][0]["query"] += "\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com"
        trace = build_search_trace(research["evidence_sources"], meta)
        serialized = json.dumps(trace, ensure_ascii=False)
        for private in ("SECRET_", "abc_teacher123", "13812345678", "teacher@example.com", "raw_response", "request_body", "api_key", "error_traceback"):
            self.assertNotIn(private, serialized)
        research["search_trace"] = trace
        output = visible(self.render(research))
        self.assertNotIn("SECRET_", output)
        self.assertNotIn("zh_first", output)
        self.assertNotIn("bilingual", output)

    def test_unavailable_and_local_only_do_not_display_queries_that_were_not_sent(self):
        research = fixture("custom")
        research["evidence_sources"] = research["evidence_sources"][:1]
        research["search_meta"].update(status="not_configured", searched_at=None)
        research["evidence_note"] = "近期真实需求证据不足。"
        research["search_trace"] = build_search_trace(research["evidence_sources"], research["search_meta"])
        output = visible(self.render(research))
        for text in ("当前联网搜索不可用，本次仅使用本地资料。", "本轮联网搜索：0 条", "本次未执行联网搜索。", "Search Settings", "近期真实需求证据不足。"):
            self.assertIn(text, output)
        self.assertNotIn(research["search_meta"]["queries"][0], output)
        self.assertEqual(output.count("近期真实需求证据不足。"), 1)

    def test_history_preserves_provider_plan_and_refill_without_calling_services(self):
        research = fixture("serper")
        script = ('from db import init_db, get_research_session\n'
                  'from market_session import save_market_research, restore_state, render_search_status\n'
                  'import json\n'
                  'init_db()\n'
                  'record_id = save_market_research(st.session_state["fixture"])\n'
                  'saved = json.loads(get_research_session(record_id)["summary_json"])\n'
                  'restored = restore_state(saved, record_id)["em_result"]\n'
                  'st.session_state["restored"] = restored\n'
                  'render_search_status(restored)')
        with tempfile.TemporaryDirectory(prefix="market-plan-trace-") as folder, \
                patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(Path(folder) / "history.db")}):
            app = self.render(research, script)
        restored = app.session_state["restored"]["search_trace"]
        self.assertEqual(restored, research["search_trace"])
        self.assertEqual(restored["provider"], "serper")
        self.assertEqual(restored["rounds"][-1]["name"], "demand_refill")
        self.assertIn("搜索服务：Serper", visible(app))

    def test_old_trace_uses_saved_provider_or_legacy_tavily_without_mutation(self):
        research = fixture("serper")
        for key in ("provider", "query_details", "rounds"):
            research["search_trace"].pop(key)
        before = deepcopy(research)
        enriched = search_trace_for(research)
        self.assertEqual(enriched["provider"], "serper")
        self.assertEqual(enriched["query_details"], research["search_meta"]["query_details"])
        self.assertEqual(research, before)
        research["search_meta"].pop("provider")
        research["search_meta"].pop("query_details")
        research["search_meta"].pop("rounds")
        self.assertEqual(search_trace_for(research)["provider"], "tavily")
        output = visible(self.render(research))
        self.assertIn("搜索服务：Tavily", output)
        self.assertIn(research["search_trace"]["queries"][0], output)


if __name__ == "__main__":
    unittest.main()
