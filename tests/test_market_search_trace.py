"""Focused source-count / search-trace checks. No real network or user DB writes."""
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
from llm.provider import LLMConfig
from market_analysis import analyze_market
from market_evidence import build_search_queries
from market_quality import source_key
from market_search_trace import build_search_trace, search_trace_for
from web_search.settings import SearchConfig

FILTERS = {"region": "中国大陆", "time_window": "近90天", "age_range": [84, 191],
           "skills": ["阅读理解"], "contexts": ["自主学习"], "audiences": ["家长"]}


def local_source():
    return {"id": "E1", "title": "英语阅读支持产品", "source_type": "产品 / 机构官网",
            "region": "中国大陆", "date": date.today().isoformat(), "time_scope": "within_window",
            "url": "https://example.org/local?utm_source=registry", "document_id": "local-doc",
            "chunk_id": "chunk-1", "origin": "local", "content_kind": "local_chunk",
            "content": "本产品提供英语分级阅读、阅读理解提问和真人教师反馈，帮助安排阅读练习。"}


def incoming_sources():
    content = "我家孩子试过分级阅读，但是英语阅读理解还是困难，换文章就看不懂。"
    full = {"title": "阅读理解迁移的家庭经验", "url": "https://www.zhihu.com/question/88?utm_source=test#:~:text=reading",
            "published_date": date.today().isoformat(), "content_kind": "full_text", "content": content,
            "request_body": "INTERNAL_REQUEST_SECRET", "api_key": "INTERNAL_KEY_SECRET"}
    summary = {"title": "孩子阅读练习使用反馈", "url": "https://www.zhihu.com/question/99?utm_medium=test",
               "published_date": date.today().isoformat(), "content_kind": "search_snippet", "content": content}
    unrelated = {"title": "数学自动评阅产品", "url": "https://example.org/math", "content_kind": "full_text",
                 "content": "小学数学计算题自动评阅，支持数学运算和几何作业。"}
    failed = {"title": "未取得正文的阅读资料", "url": "https://example.org/blocked", "content_kind": "search_snippet", "content": ""}
    return [full, dict(full, url="https://www.zhihu.com/question/88?utm_campaign=duplicate"), summary, unrelated, failed]


def live_research():
    search = {"results": incoming_sources(), "status": "partial", "searched_at": date.today().isoformat(),
              "failures": [{"url": "https://example.org/blocked", "stage": "fetch",
                            "reason": "403 页面限制访问; INTERNAL_REQUEST_SECRET timeout=15 api_key=INTERNAL_KEY_SECRET"}]}
    with patch("market_analysis.retrieve_local", return_value=([local_source()], [])), \
            patch("market_analysis.load_config", return_value=LLMConfig(provider="mock")), \
            patch("market_analysis.load_search_config", return_value=SearchConfig(api_key="fixture")), \
            patch("market_analysis.search_web", return_value=search) as web:
        research = analyze_market(FILTERS, live_search=True)
    return research, web


def visible(app):
    return "\n".join(str(item.value) for kind in ("markdown", "caption", "info", "warning", "error", "success", "subheader")
                     for item in app.get(kind))


class MarketSearchTraceChecks(unittest.TestCase):
    def render(self, research, script=None):
        script = script or 'from market_session import render_search_status\nrender_search_status(st.session_state["fixture"])'
        app = AppTest.from_string('import sys\n' + f'sys.path.insert(0, {str(ROOT / "03app")!r})\n' +
                                 'import streamlit as st\n' + script, default_timeout=15)
        app.session_state["fixture"] = deepcopy(research)
        with patch("market_analysis.search_web", side_effect=AssertionError("render cannot search")), \
                patch("market_analysis.complete_json", side_effect=AssertionError("render cannot call AI")), \
                patch("knowledge.retrieval.get_retriever", side_effect=AssertionError("render cannot retrieve")), \
                patch("requests.sessions.Session.request", side_effect=AssertionError("render cannot access network")):
            app.run()
        self.assertFalse(app.exception, [item.message for item in app.exception])
        return app

    def test_local_only_counts_unique_sources_and_does_not_show_planned_queries(self):
        source = local_source()
        evidence = [source, dict(source, id="E2", chunk_id="chunk-2", url="https://example.org/local?utm_medium=duplicate"),
                    {"id": "E3", "title": "本地研究资料", "origin": "local", "document_id": "pdf-1", "chunk_id": "pdf-chunk-1"},
                    {"id": "E4", "title": "本地研究资料", "content_kind": "local_chunk", "document_id": "pdf-1", "chunk_id": "pdf-chunk-2"}]
        meta = {"status": "not_configured", "requested": True, "queries": ["尚未发送的计划查询"]}
        trace = build_search_trace(evidence, meta)
        self.assertEqual((trace["local_source_count"], trace["web_source_count"]), (2, 0))
        self.assertFalse(trace["executed"])
        self.assertEqual(trace["queries"], [])
        app = self.render({"evidence_sources": evidence, "search_meta": meta, "search_trace": trace})
        output = visible(app)
        for text in ("本地知识库：2 条", "本轮联网搜索：0 条", "当前仅基于本地资料分析。", "本次未执行联网搜索。", "Search Settings"):
            self.assertIn(text, output)
        self.assertNotIn("尚未发送的计划查询", output)
        trace_box = next(item for item in app.expander if item.label == "查看本次联网搜索")
        self.assertFalse(trace_box.proto.expanded)

    def test_live_fixture_counts_final_context_not_raw_results_and_keeps_queries(self):
        research, web = live_research()
        expected_queries = build_search_queries(FILTERS)
        self.assertEqual([query for call in web.call_args_list for query in call.args[0]], expected_queries)
        trace = research["search_trace"]
        self.assertTrue(trace["executed"])
        self.assertEqual(trace["queries"], expected_queries)
        self.assertEqual((trace["local_source_count"], trace["web_source_count"]), (1, 2))
        final_web = [source for source in research["evidence_sources"] if source.get("origin") == "web"]
        self.assertEqual(trace["web_source_count"], len({source_key(source) for source in final_web}))
        self.assertLess(trace["web_source_count"], len(incoming_sources()))
        sources = {item["url"]: item for item in trace["sources"]}
        self.assertEqual(len(sources), len(trace["sources"]))
        self.assertEqual(sources["https://www.zhihu.com/question/88"]["status"], "已读取正文")
        self.assertEqual(sources["https://www.zhihu.com/question/99"]["status"], "仅使用搜索摘要")
        self.assertFalse(sources["https://example.org/math"]["used"])
        self.assertEqual(sources["https://example.org/math"]["status"], "未用于本次分析")
        self.assertTrue(sources["https://www.zhihu.com/question/88"]["used"])

    def test_trace_ui_shows_short_links_statuses_and_no_contacts_or_internal_details(self):
        research, _ = live_research()
        # Raw source metadata is intentionally rich; the view may expose only safe trace fields.
        research["search_trace"]["sources"][0]["title"] += "\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com"
        app = self.render(research)
        output = visible(app)
        for text in ("本地知识库：1 条", "本轮联网搜索：2 条", "阅读理解迁移的家庭经验", "已读取正文", "仅使用搜索摘要"):
            self.assertIn(text, output)
        for text in ("abc_teacher123", "13812345678", "teacher@example.com", "INTERNAL_REQUEST_SECRET", "INTERNAL_KEY_SECRET",
                     "timeout=15", "api_key", "request_body", "utm_", ":~:text="):
            self.assertNotIn(text, output)
        for query in research["search_trace"]["queries"]:
            self.assertIn(query, output)
        self.assertRegex(output, r"\[(?:查看原文|打开来源)\]\(<https://www\.zhihu\.com/question/88>\)")
        self.assertNotIn("https://", re.sub(r"\[[^\]]+\]\(<?https?://[^\s)]+>?\)", "", output))

    def test_supply_diagnostic_counts_kept_web_roles_not_query_purposes(self):
        supply = dict(local_source(), id="W1", origin="web", url="https://example.org/product", content_kind="full_text")
        demand = {"id": "W2", "title": "家长阅读反馈", "url": "https://example.org/discussion", "origin": "web",
                  "source_type": "公开用户讨论", "query_purpose": "solution_supply", "content_kind": "search_snippet"}
        background = [{"id": f"W{i}", "title": f"背景资料 {i}", "url": f"https://example.org/background/{i}",
                       "origin": "web", "content_kind": "search_snippet"} for i in range(3, 11)]
        evidence = [local_source(), supply, dict(supply, id="duplicate"), demand, *background]
        unused = dict(supply, url="https://example.org/unused-product")
        meta = {"status": "success", "searched_at": date.today().isoformat()}
        trace = build_search_trace(evidence, meta, [supply, demand, unused])
        self.assertEqual((trace["local_source_count"], trace["web_source_count"], trace["web_supply_count"]), (1, 10, 1))
        rows = {row["url"]: row for row in trace["sources"]}
        self.assertEqual(rows[supply["url"]]["evidence_role"], "supply")
        self.assertEqual(rows[demand["url"]]["evidence_role"], "demand")
        self.assertNotIn("evidence_role", rows[unused["url"]])
        output = visible(self.render({"evidence_sources": evidence, "search_meta": meta, "search_trace": trace}))
        self.assertIn("Supply Evidence: 1 / 10", output)
        self.assertIn("Evidence Role: solution_supply（供给侧）", output)

    def test_legacy_trace_recovers_supply_count_and_roles_from_saved_evidence(self):
        supply = dict(local_source(), origin="web", url="https://example.org/legacy-product")
        meta = {"status": "success", "searched_at": date.today().isoformat()}
        trace = build_search_trace([supply], meta)
        trace.pop("web_supply_count")
        trace["sources"][0].pop("evidence_role")
        research = {"evidence_sources": [supply], "search_meta": meta, "search_trace": trace}
        before = deepcopy(research)
        restored = search_trace_for(research)
        self.assertEqual(restored["web_supply_count"], 1)
        self.assertEqual(restored["web_source_count"], 1)
        self.assertEqual(restored["sources"][0]["evidence_role"], "supply")
        self.assertEqual(research, before)

    def test_history_save_restore_preserves_trace_without_network_or_reanalysis(self):
        research, _ = live_research()
        script = ('from db import get_research_session, init_db\n'
                  'from market_session import save_market_research, restore_state, render_search_status\n'
                  'import json\n'
                  'init_db()\n'
                  'record_id = save_market_research(st.session_state["fixture"])\n'
                  'saved = json.loads(get_research_session(record_id)["summary_json"])\n'
                  'restored = restore_state(saved, record_id)\n'
                  'st.session_state["restored_fixture"] = restored["em_result"]\n'
                  'render_search_status(restored["em_result"])')
        with tempfile.TemporaryDirectory(prefix="market-trace-check-") as folder, \
                patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(Path(folder) / "trace.db")}):
            app = self.render(research, script)
            self.assertEqual(app.session_state["restored_fixture"]["search_trace"], research["search_trace"])
        output = visible(app)
        self.assertIn("本地知识库：1 条", output)
        self.assertIn("本轮联网搜索：2 条", output)
        self.assertIn(research["search_trace"]["queries"][0], output)

    def test_legacy_history_reconstructs_only_saved_origins_without_fetching(self):
        local = local_source()
        web = {"id": "W1", "title": "旧联网资料", "url": "https://example.org/legacy", "content_kind": "search_snippet"}
        old = {"evidence_sources": [local, web], "search_meta": {"status": "success", "searched_at": date.today().isoformat(),
               "queries": ["保存的阅读理解查询"]}}
        before = deepcopy(old)
        with patch("market_analysis.search_web", side_effect=AssertionError("legacy restore cannot search")):
            trace = search_trace_for(old)
        self.assertEqual((trace["local_source_count"], trace["web_source_count"]), (1, 1))
        self.assertEqual(trace["queries"], ["保存的阅读理解查询"])
        self.assertEqual(old, before)
        # An old saved search_snippet is not evidence of a current search by itself.
        old["search_meta"] = {"status": "not_configured", "queries": ["未发送查询"]}
        trace = search_trace_for(old)
        self.assertFalse(trace["executed"])
        self.assertEqual(trace["web_source_count"], 0)


if __name__ == "__main__":
    unittest.main()
