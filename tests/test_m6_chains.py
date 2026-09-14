"""M6 only: four presentation/recovery chains, isolated from private settings and History."""
from contextlib import ExitStack
from copy import deepcopy
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

from streamlit.testing.v1 import AppTest
from db import list_research_sessions
from llm.provider import LLMNotConfigured


def visible(app):
    return "\n".join(str(item.value) for kind in ("title", "markdown", "caption", "warning", "info", "success", "error", "subheader") for item in app.get(kind))


class ResearchChains(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engeduscope-m6-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        target = self.directory / "library.db"
        with sqlite3.connect(f"file:{ROOT / '01data/02structured/eng_eduscope.db'}?mode=ro", uri=True) as source:
            with sqlite3.connect(target) as destination:
                source.backup(destination)
                destination.execute("DELETE FROM research_sessions")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(target), "ENGEDUSCOPE_LLM_PROVIDER": "mock",
                                                       "ENGEDUSCOPE_LLM_MOCK_MODE": "ok", "ENGEDUSCOPE_SEARCH_API_KEY": "", "TAVILY_API_KEY": ""}))
        self.stack.enter_context(patch("llm.settings.CONFIG_PATH", self.directory / "ai.json"))
        self.stack.enter_context(patch("web_search.settings.CONFIG_PATH", self.directory / "search.json"))
        self.stack.enter_context(patch("solution_export.DEFAULT_OUTPUT_DIR", self.directory / "exports"))
        for request in ("requests.get", "requests.post"):
            self.stack.enter_context(patch(request, side_effect=AssertionError("M6 Demo never makes an external request")))
        self.app = AppTest.from_file(str(ROOT / "03app/00_app.py"), default_timeout=30).run()
        self.clean()

    def clean(self):
        self.assertFalse(self.app.exception, [item.message for item in self.app.exception])
        self.assertNotIn("Traceback", visible(self.app))

    def solve(self):
        app = self.app
        app.switch_page("02_solve_need.py").run()
        app.radio(key="sn_identity").set_value("我是家长").run()
        app.radio(key="sn_parent_path").set_value("我有一个具体英语学习问题").run()
        app.selectbox(key="sn_p_age_y").set_value(7)
        app.selectbox(key="sn_p_age_m").set_value(4)
        app.text_area(key="sn_p_problem").set_value("阅读输入较多但很少主动说英语，希望在家庭场景练习主动表达。")
        app.multiselect(key="sn_p_contexts").set_value(["家庭固定学习"])
        app.multiselect(key="sn_p_methods").set_value(["分级阅读"])
        app.button(key="sn_p_submit").click().run()
        self.clean()
        result = deepcopy(app.session_state["sn_result"])
        self.assertTrue(result.get("need_analysis"))
        self.assertTrue(result.get("evidence_sources"))
        return result

    def restore(self, row, page, key):
        app = self.app
        with ExitStack() as forbidden:
            for function in ("need_analysis.analyze_parent", "need_analysis.analyze_educator", "need_analysis.revise_educator",
                             "market_analysis.analyze_market", "market_analysis.follow_up", "market_analysis.search_web",
                             "solution_analysis.generate_solution", "solution_analysis.revise_solution",
                             "need_analysis.get_retriever", "market_evidence.get_retriever", "solution_analysis.get_retriever"):
                forbidden.enter_context(patch(function, side_effect=AssertionError("Restoring must not generate, search or retrieve")))
            app.switch_page("04_history.py").run()
            app.button(key=f"hist_view_{row['id']}").click().run()
            self.clean()
            app.button(key=f"hist_resume_{row['id']}").click().run()
            self.clean()
            app.switch_page(page)._run()  # AppTest 1.50 removes the previous page's widget tree.
            self.clean()
            self.assertEqual(app.session_state[key], json.loads(row["summary_json"]))

    def test_chain_a_home_solve_save_history_restore_and_reanalyze(self):
        result = self.solve()
        self.app.button(key="sn_save").click().run()
        row = list_research_sessions()[0]
        self.assertEqual(json.loads(row["summary_json"]), result)
        self.restore(row, "02_solve_need.py", "sn_result")
        from need_analysis import analyze_parent
        with patch("need_analysis.analyze_parent", wraps=analyze_parent) as analyze:
            self.app.button(key="sn_reanalyze").click().run()
        self.assertEqual(analyze.call_count, 1)
        self.clean()

    def test_chain_b_home_market_followup_save_history_restore_continue(self):
        app = self.app
        app.switch_page("03_explore_market.py").run()
        app.selectbox(key="em_age_start_y").set_value(6)
        app.selectbox(key="em_age_end_y").set_value(8)
        app.multiselect(key="em_skills").set_value(["口语表达"])
        app.multiselect(key="em_contexts").set_value(["自主学习"])
        app.button(key="em_update").click().run()  # No Search key: local evidence stays usable.
        self.clean()
        research = app.session_state["em_result"]
        self.assertEqual(research["search_meta"]["status"], "not_configured")
        self.assertTrue(research["evidence_sources"])
        signal_id = str(research["signals"][0]["id"])
        app.text_input(key=f"em_question_{signal_id}").set_value("这个需求为什么现有产品还没有解决？")
        app.button(key=f"em_ask_{signal_id}").click().run()
        self.clean()
        self.assertEqual(len(app.session_state["em_result"]["chat"][signal_id]), 1)
        app.button(key="em_save").click().run()
        row = list_research_sessions()[0]
        self.restore(row, "03_explore_market.py", "em_result")
        app.text_input(key=f"em_question_{signal_id}").set_value("哪些结论仍然需要验证？")
        app.button(key=f"em_ask_{signal_id}").click().run()
        self.clean()
        self.assertEqual(len(app.session_state["em_result"]["chat"][signal_id]), 2)

    def test_chain_c_solve_build_save_restore_revision_and_export(self):
        app = self.app
        need = self.solve()
        app.button(key="sn_build").click().run()
        app.switch_page("06_build_solution.py")._run()
        self.clean()
        self.assertNotIn("bs_result", app.session_state.filtered_state)
        app.button(key="bs_generate").click().run()
        self.clean()
        initial = deepcopy(app.session_state["bs_result"])
        self.assertEqual([e["id"] for e in initial["evidence_sources"]], [e["id"] for e in need["evidence_sources"]])
        app.button(key="bs_save").click().run()
        row = list_research_sessions()[0]
        self.restore(row, "06_build_solution.py", "bs_result")
        app.text_area(key="bs_revision_instruction").set_value("改成10–12岁，第一版只用 Web App，减少家长参与")
        next(button for button in app.button if button.label == "调整产品方案").click().run()
        self.clean()
        revised = app.session_state["bs_result"]
        self.assertEqual(revised["opportunity_brief"]["age_range"], [120, 155])
        self.assertEqual(revised["evidence_sources"], initial["evidence_sources"])
        self.assertEqual(len(revised["analysis_meta"]["revision_history"]), 1)
        app.button(key="bs_export_btn").click().run()
        self.clean()
        path = Path(app.session_state["bs_export"]["path"])
        self.assertEqual(path.parent, self.directory / "exports")
        self.assertIn("product_concept", path.name)
        text = path.read_text(encoding="utf-8")
        self.assertIn("Evidence", text)
        self.assertIn(initial["evidence_sources"][0]["title"], text)
        self.assertIn(str(path), visible(app))

    def test_chain_d_manage_data_tabs_status_and_public_discussions(self):
        app = self.app
        app.switch_page("05_manage_data.py").run()
        self.clean()
        self.assertEqual([tab.label for tab in app.tabs], ["Knowledge Base", "Structured Data", "Sources", "AI Settings", "Search Settings", "System Status"])
        text = visible(app)
        self.assertIn("Demo", text)
        self.assertIn("Local Only", text)
        self.assertIn("公开用户讨论", text)
        self.assertNotIn("待 M5", text)

    def test_empty_library_and_ai_save_errors_are_friendly(self):
        app = self.app
        app.switch_page("04_history.py").run()
        self.clean()
        self.assertIn("还没有保存过研究或方案", visible(app))
        self.solve()
        with patch("need_analysis.analyze_parent", side_effect=LLMNotConfigured()):
            app.button(key="sn_reanalyze").click().run()
        self.clean()
        self.assertIn("当前未配置可用 AI，可切换至 Demo 或前往 AI Settings", visible(app))
        self.assertTrue(app.session_state["sn_result"]["need_analysis"])
        with patch("db.save_research_session", side_effect=sqlite3.OperationalError("private database details")):
            # Rebind the script's imported save function before clicking its callback.
            app.run()
            app.button(key="sn_save").click().run()
        self.clean()
        self.assertIn("当前需求分析已保留", visible(app))
        self.assertNotIn("private database details", visible(app))


if __name__ == "__main__":
    unittest.main()
