"""Three real-core M5 entry flows on a read-only backup of the user's local KB.

All generated records/configuration/exports are confined to temporary files.
The actual M3/M4/M5 analysis, adapters, schemas and Markdown exporter execute.
"""

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

from db import get_db_path, list_research_sessions
from llm import settings as ai_settings
from web_search import settings as search_settings


class RealBuildEntryFlows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engeduscope-m5-real-entry-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "history.db"
        source_path = PROJECT / "01data" / "02structured" / "eng_eduscope.db"
        with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as source:
            with sqlite3.connect(self.db_path) as destination:
                source.backup(destination)
        env = patch.dict(os.environ, {
            "ENGEDUSCOPE_DB_PATH": str(self.db_path), "ENGEDUSCOPE_LLM_PROVIDER": "mock",
            "ENGEDUSCOPE_LLM_MOCK_MODE": "ok", "ENGEDUSCOPE_SEARCH_API_KEY": "", "TAVILY_API_KEY": "",
        })
        env.start()
        self.addCleanup(env.stop)
        for target, attr, value in ((ai_settings, "CONFIG_PATH", self.root / "llm.json"),
                                    (search_settings, "CONFIG_PATH", self.root / "search.json")):
            mocked = patch.object(target, attr, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        # Call the real exporter, with only the destination redirected to this test directory.
        import solution_export
        real_export = solution_export.export_markdown
        export = patch("solution_export.export_markdown", side_effect=lambda record: real_export(record, output_dir=self.root / "markdown"))
        export.start()
        self.addCleanup(export.stop)
        self.assertEqual(get_db_path(), self.db_path)
        self.app = AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=40).run()
        self.assertEqual(len(self.app.exception), 0)

    def complete_build(self, source_type, instruction="降低家长参与，不依赖硬件"):
        app = self.app
        # Streamlit 1.50 AppTest can retain removed source-page widgets after a
        # programmatic switch; a fresh script run bypasses that stale widget tree.
        app.switch_page("06_build_solution.py")._run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn("bs_result", app.session_state.filtered_state)
        inherited = deepcopy(app.session_state["bs_brief"])
        self.assertEqual(inherited["source_type"], source_type)
        before = len(list_research_sessions())
        app.button(key="bs_generate").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(app.error, [error.value for error in app.error])
        record = deepcopy(app.session_state["bs_result"])
        self.assertEqual(record["analysis_meta"]["mode"], "demo")
        self.assertEqual(record["kind"], "product_concept")
        self.assertEqual(app.session_state["bs_brief"], record["opportunity_brief"])
        self.assertEqual(record["evidence_sources"], record["opportunity_brief"]["evidence_sources"])
        if source_type == "scratch":
            self.assertEqual(record["analysis_meta"]["retrieval"]["calls"], 1)
        else:
            self.assertEqual(record["evidence_sources"], inherited["evidence_sources"])
            self.assertEqual(record["analysis_meta"]["retrieval"]["calls"], 0)
        self.assertTrue(3 <= len(record["solution"]["mvp"]["core_features"]) <= 5)
        self.assertEqual(len(record["solution"]["demo_build_path"]), 5)
        self.assertTrue(record["solution"]["fast_prototype"]["copyable_prompt"])
        self.assertEqual(len(list_research_sessions()), before)
        app.text_area(key="bs_revision_instruction").set_value(instruction)
        next(button for button in app.button if button.label == "调整产品方案").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(app.error, [error.value for error in app.error])
        revised = deepcopy(app.session_state["bs_result"])
        self.assertEqual(revised["analysis_meta"]["revision_history"][-1]["instruction"], instruction)
        self.assertEqual(app.session_state["bs_brief"], revised["opportunity_brief"])
        self.assertEqual(revised["evidence_sources"], record["evidence_sources"])
        self.assertEqual(revised["solution"]["carrier"]["choices"], ["App / 网页"])
        app.button(key="bs_save").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(list_research_sessions()), before + 1)
        saved_row = list_research_sessions()[0]
        self.assertEqual(json.loads(saved_row["summary_json"]), revised)
        app.switch_page("04_history.py").run()
        app.button(key=f"hist_view_{saved_row['id']}").click().run()
        self.assertEqual(len(app.exception), 0)
        app.button(key=f"hist_resume_{saved_row['id']}").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["bs_result"], revised)
        self.assertEqual(app.session_state["bs_brief"], revised["opportunity_brief"])
        app.switch_page("06_build_solution.py").run()
        app.button(key="bs_export_btn").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(app.error, [error.value for error in app.error])
        output = Path(app.session_state["bs_export"]["path"])
        self.assertEqual(output.parent, self.root / "markdown")
        markdown = output.read_text(encoding="utf-8")
        self.assertIn(revised["solution"]["product_concept"]["name"], markdown)
        self.assertIn(revised["solution"]["teaching_goal"]["learning_outcome"], markdown)
        return record, revised

    def test_a_solve_oral_home_to_build(self):
        app = self.app
        app.switch_page("02_solve_need.py").run()
        app.radio(key="sn_identity").set_value("我是教育工作者").run()
        app.radio(key="sn_e_age_mode").set_value("年龄范围").run()
        for key, value in (("start_y", 6), ("start_m", 0), ("end_y", 8), ("end_m", 11)):
            app.selectbox(key=f"sn_e_age_{key}").set_value(value)
        app.multiselect(key="sn_e_skills").set_value(["口语表达"])
        app.multiselect(key="sn_e_contexts").set_value(["家庭固定学习"])
        app.multiselect(key="sn_e_carriers").set_value(["App / 网页"])
        app.text_area(key="sn_e_pain").set_value("6–8岁儿童已有较多英语阅读输入，但主动口语输出不足，希望探索家庭场景下低成本、高频输出机制。")
        app.button(key="sn_e_submit").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.session_state["sn_result"].get("need_analysis"))
        app.button(key="sn_build").click().run()
        self.assertEqual(len(app.exception), 0)
        record, _ = self.complete_build("solve_need")
        self.assertEqual(record["opportunity_brief"]["age_range"], [72, 107])
        self.assertIn("口语表达", record["opportunity_brief"]["skills"])

    def test_b_real_market_insight_to_build(self):
        app = self.app
        app.switch_page("03_explore_market.py").run()
        app.selectbox(key="em_age_start_y").set_value(6)
        app.selectbox(key="em_age_end_y").set_value(8)
        app.multiselect(key="em_skills").set_value(["口语表达"])
        app.multiselect(key="em_contexts").set_value(["家庭固定学习"])
        app.button(key="em_analyze").click().run()
        self.assertEqual(len(app.exception), 0)
        research = app.session_state["em_result"]
        self.assertTrue(research["signals"], "The real KB must yield a source-backed oral-language signal for this entry check.")
        selected = research["signals"][0]
        self.assertTrue(selected["evidence_sources"])
        app.button(key=f"em_build_{selected['id']}").click().run()
        self.assertEqual(len(app.exception), 0)
        market_snapshot = json.loads(list_research_sessions()[0]["summary_json"])
        self.assertEqual(market_snapshot["opportunity_context"]["signal_id"], selected["id"])
        record, _ = self.complete_build("market_insight")
        self.assertEqual(record["evidence_sources"], app.session_state["bs_brief"]["evidence_sources"])

    def test_c_scratch_reading_school_revised_scope(self):
        app = self.app
        app.switch_page("06_build_solution.py").run()
        app.text_input(key="bs_target_user").set_value("9–12岁、面临学校阅读难度提高的儿童及其家庭")
        app.selectbox(key="bs_age_start_y").set_value(9)
        app.selectbox(key="bs_age_end_y").set_value(12)
        app.selectbox(key="bs_age_end_m").set_value(11)
        app.multiselect(key="bs_skills").set_value(["阅读理解"])
        app.multiselect(key="bs_contexts").set_value(["学校课程衔接"])
        app.multiselect(key="bs_preferred_carriers").set_value(["Pad / 学习机"])
        app.text_area(key="bs_core_need").set_value("孩子能读出单词，但学校英语阅读材料变长后很难理解，需要形成找线索与复述的阅读习惯。")
        next(button for button in app.button if button.label == "确认机会输入").click().run()
        initial, revised = self.complete_build("scratch", "年龄改成10–12岁，降低家长参与，不依赖硬件")
        self.assertEqual(initial["opportunity_brief"]["age_range"], [108, 155])
        self.assertEqual(revised["opportunity_brief"]["age_range"], [120, 155])
        self.assertTrue(revised["opportunity_brief"]["scope_notes"])
        self.assertEqual(revised["original_opportunity_brief"]["age_range"], [108, 155])
        # Explicit regeneration must use the revised brief instead of reverting to the original age.
        app.button(key="bs_generate").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["bs_result"]["opportunity_brief"]["age_range"], [120, 155])


if __name__ == "__main__":
    unittest.main()
