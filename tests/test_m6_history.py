"""M6 unified History metadata, filters, safe failures and restore-only behavior."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "03app"))

from streamlit.testing.v1 import AppTest

from db import get_research_session, init_db, save_research_session
from history_library import filter_records, session_metadata
from solution_baseline import baseline_solution
from solution_context import from_scratch


def visible(app):
    return "\n".join(str(item.value) for kind in ("markdown", "caption", "warning", "info", "error", "success")
                     for item in app.get(kind))


def age(year, month=0):
    return {"mode": "exact", "years": year, "months": month, "age_months": year * 12 + month,
            "display": f"{year}岁{month}个月"}


class UnifiedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engeduscope-m6-history-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "history.db"
        env = patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(self.db), "ENGEDUSCOPE_LLM_PROVIDER": "mock",
                                      "ENGEDUSCOPE_LLM_MOCK_MODE": "ok", "TAVILY_API_KEY": "", "ENGEDUSCOPE_SEARCH_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)
        for target, path in (("llm.settings.CONFIG_PATH", self.root / "llm.json"),
                              ("web_search.settings.CONFIG_PATH", self.root / "search.json")):
            configuration = patch(target, path)
            configuration.start()
            self.addCleanup(configuration.stop)
        init_db()
        self.solve = {
            "user_type": "professional", "entry_type": "professional", "region": "中国大陆",
            "age": {"mode": "range", "start": age(6), "end": age(8, 11)}, "skills": ["口语表达"],
            "contexts": ["家庭固定学习"], "carriers": ["App / 网页"], "pain_point": "希望增加主动表达机会。",
            "generated_at": "2026-09-13T19:00:00+08:00", "analysis_meta": {"mode": "mock"},
            "need_analysis": {"user_need": {"age": "10–12岁", "core_skills": ["口语表达"], "contexts": ["自主学习"],
                                            "target_user": "儿童", "pain_point": "减少提示后仍能自主表达。"},
                              "teaching_goal": "自主表达完整意思", "solution_landscape": [], "gap": []},
            "product_direction": {}, "mvp_spec": {}, "validation_metrics": {}, "evidence_sources": [],
        }
        self.market = {
            "kind": "market_research", "region": "海外 Benchmark", "time_window": "近90天",
            "filters": {"region": "海外 Benchmark", "time_window": "近90天", "age_range": [60, 107],
                        "skills": ["自然拼读"], "contexts": ["自主学习"], "audiences": ["家长"]},
            "signals": [], "evidence_sources": [], "chat": {}, "generated_at": "2026-09-13T19:00:00+08:00",
            "search_meta": {"status": "not_configured", "searched_at": None}, "analysis_meta": {"mode": "local_evidence"},
        }
        brief = from_scratch({"target_user": "9–12岁儿童及家庭", "age_range": [108, 155], "skills": ["阅读理解"],
                              "contexts": ["学校课程衔接"], "region": "中国大陆", "core_need": "理解变长的英语阅读材料。"})
        self.product = {"kind": "product_concept", "entry_type": "build_solution", "opportunity_brief": brief,
                        "solution": baseline_solution(brief), "evidence_sources": [],
                        "generated_at": "2026-09-13T19:00:00+08:00", "analysis_meta": {"mode": "demo", "revision_history": []}}
        self.rows = []
        for title, entry, snapshot in (("自主表达需求", "solve_need_educator", self.solve),
                                       ("海外拼读研究", "explore_market", self.market),
                                       ("阅读产品方案", "build_solution", self.product)):
            session_id = save_research_session(title, "教育工作者", entry, snapshot)
            self.rows.append(get_research_session(session_id))

    def app(self):
        app = AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=25).run()
        app.switch_page("04_history.py").run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_metadata_and_filtering_use_current_scope(self):
        original = deepcopy(self.rows)
        records = [session_metadata(row) for row in self.rows]
        self.assertEqual([item["type"] for item in records], ["Solve a Need", "Market Research", "Build a Solution"])
        self.assertEqual(records[0]["age_range"], [120, 155])
        self.assertEqual(records[0]["contexts"], ["自主学习"])
        self.assertEqual(records[1]["region"], "海外 Benchmark")
        self.assertEqual(records[2]["age_range"], [108, 155])
        self.assertEqual([item["id"] for item in filter_records(records, record_type="Market Research", skill="自然拼读", age="6–8", region="海外 Benchmark")], [self.rows[1]["id"]])
        self.assertEqual(filter_records(records, record_type="Solve a Need", age="6–8"), [])
        self.assertEqual(filter_records(records, skill="单词拼写"), [])
        self.assertEqual(self.rows, original)
        invalid_market = deepcopy(self.market)
        invalid_market["filters"]["skills"] = ["invalid-widget-option"]
        invalid_row = dict(self.rows[1], summary_json=json.dumps(invalid_market))
        self.assertFalse(session_metadata(invalid_row)["readable"])
        invalid_need = deepcopy(self.solve)
        invalid_need["age"] = dict(age(7), years=100)
        self.assertFalse(session_metadata(dict(self.rows[0], summary_json=json.dumps(invalid_need)))["readable"])

    def test_cards_filters_and_bad_record_remain_friendly(self):
        broken_id = save_research_session("保留的异常记录", "家长", "solve_need_parent_specific", {})
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE research_sessions SET summary_json = ? WHERE id = ?", ("{unreadable", broken_id))
        app = self.app()
        content = visible(app)
        for label in ("Solve a Need", "Market Research", "Build a Solution", "创建于", "年龄：10岁0个月", "能力：口语表达", "场景：自主学习", "地域：海外 Benchmark"):
            self.assertIn(label, content)
        self.assertIn("原记录已保留", content)
        self.assertNotIn("{unreadable", content)
        self.assertFalse(any(button.key == f"hist_view_{broken_id}" for button in app.button))
        app.selectbox(key="hist_filter_type").set_value("Market Research").run()
        self.assertIn("当前显示 1 条", visible(app))
        app.selectbox(key="hist_filter_skill").set_value("口语表达").run()
        self.assertIn("没有符合当前筛选条件", visible(app))
        app.button(key="hist_reset_filters").click().run()
        self.assertIn("当前显示 4 条", visible(app))
        self.assertEqual(len(app.exception), 0)

    def test_restore_never_generates_searches_or_retrieves(self):
        targets = (
            "need_analysis.analyze_parent", "need_analysis.analyze_educator", "need_analysis.revise_educator",
            "market_analysis.analyze_market", "market_analysis.follow_up", "market_analysis.search_web",
            "solution_analysis.generate_solution", "solution_analysis.revise_solution", "solution_analysis._retrieve",
            "knowledge.retrieval.get_retriever", "web_search.provider.search_web", "llm.provider.complete_json",
        )
        spies = []
        for target in targets:
            blocked = patch(target, side_effect=AssertionError(f"Restore must not call {target}"))
            spies.append(blocked.start())
            self.addCleanup(blocked.stop)
        for row, expected, result_key, saved_key in zip(self.rows, (self.solve, self.market, self.product),
                                                       ("sn_result", "em_result", "bs_result"), ("sn_saved", "em_saved", "bs_saved")):
            app = self.app()
            app.button(key=f"hist_view_{row['id']}").click().run()
            self.assertEqual(len(app.exception), 0)
            app.button(key=f"hist_resume_{row['id']}").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state[result_key], expected)
            self.assertEqual(app.session_state[saved_key]["id"], row["id"])
        for spy in spies:
            spy.assert_not_called()

    def test_empty_library_and_database_read_error(self):
        with patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(self.root / "empty.db")}):
            app = self.app()
            self.assertIn("还没有保存过研究", visible(app))
        app = self.app()
        with patch("db.list_research_sessions", side_effect=sqlite3.DatabaseError("private SQLite details")):
            app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("暂时无法读取本地历史记录", visible(app))
        self.assertNotIn("private SQLite details", visible(app))


if __name__ == "__main__":
    unittest.main()
