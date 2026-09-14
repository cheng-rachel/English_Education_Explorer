"""Targeted M3 A/B/C checks, grounded in a temporary copy of the existing M2 DB.

Run: .venv/bin/python -B -m unittest discover -s tests -p 'test_m3_*.py' -v
No external API, real API configuration, or original History writes.
"""

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))

from llm import settings
from llm.mock import mock_complete_json
from llm.provider import LLMConfig, LLMBadResponse, LLMSchemaError, LLMTimeout
from need_analysis import (
    _call_validated, analyze_educator, analyze_parent, apply_analysis,
    fallback_diy, retrieve_evidence, revise_educator,
)


def age(years, months=0):
    return {"mode": "exact", "years": years, "months": months,
            "age_months": 12 * years + months, "display": f"{years}岁{months}个月"}


CASE_A = {
    "user_type": "parent", "entry_type": "parent_specific", "age": age(7, 4),
    "problem": "7岁4个月，已经读了一段时间分级阅读，自己读得还可以，但是平时几乎不会主动说英语。",
    "skills": [], "contexts": ["家庭固定学习"], "methods": ["分级阅读"],
}
CASE_B = {
    "user_type": "parent", "entry_type": "parent_overview", "age": age(5, 6),
    "background": "接触英语半年，晚上和家长听英语儿歌、看绘本，每周有一次启蒙课。希望整体看看学习需要。",
    "skills": [], "contexts": ["亲子共学", "睡前"], "methods": ["家长陪伴"],
}
CASE_C = {
    "user_type": "professional", "entry_type": "professional",
    "age": {"mode": "range", "start": age(6), "end": age(8, 11)},
    "pain_point": "6–8岁儿童已有较多英语阅读输入，但主动口语输出不足，希望探索家庭场景下低成本、高频输出机制。",
    "skills": ["口语表达"], "contexts": ["家庭固定学习"], "carriers": ["App / 网页"],
}


class NeedFlowChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="engeduscope-m3-flow-")
        cls.db_path = Path(cls.temp.name) / "test.db"
        original = ROOT / "01data/02structured/eng_eduscope.db"
        if original.exists():
            with sqlite3.connect(f"file:{original}?mode=ro", uri=True) as source:
                with sqlite3.connect(cls.db_path) as destination:
                    source.backup(destination)
        cls.env = patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(cls.db_path),
                                        "ENGEDUSCOPE_LLM_PROVIDER": "mock",
                                        "ENGEDUSCOPE_LLM_MOCK_MODE": "ok"})
        cls.env.start()
        cls.config = patch.object(settings, "CONFIG_PATH", Path(cls.temp.name) / "llm_config.json")
        cls.config.start()
        from db import init_db
        from knowledge.kb_db import init_schema
        init_db()
        init_schema()

    @classmethod
    def tearDownClass(cls):
        cls.config.stop()
        cls.env.stop()
        cls.temp.cleanup()

    def assert_parent(self, result):
        self.assertEqual(result["analysis_meta"]["mode"], "mock")
        self.assertTrue(result["generated_at"])
        self.assertTrue(1 <= len(result["analysis_meta"]["queries"]) <= 3)
        need = result["need_analysis"]
        self.assertTrue(2 <= len(need["possible_causes"]) <= 4)
        self.assertTrue(need["priority"]["focus_now"])
        routes = result["solution_routes"]
        self.assertEqual(len(routes), 3)
        self.assertEqual(len({r["mechanism"] for r in routes}), 3)
        for route in routes:
            for key in ("route_name", "why_it_fits", "recommended_actions", "suitable_for", "limitations"):
                self.assertTrue(route[key])
            for key in ("time_cost", "money_cost", "parent_involvement"):
                self.assertIn(route[key], ["低", "中", "高"])
        self.assertTrue(any(r["teacher_profile"] for r in routes))
        self.assertTrue(result["ai_diy"]["copyable_prompt"])

    def test_case_a_specific_parent_real_kb_retrieval(self):
        result = analyze_parent(CASE_A)
        self.assert_parent(result)
        self.assertIn("口语表达", result["need_analysis"]["primary_skills"])
        self.assertIn("阅读理解", result["need_analysis"]["secondary_skills"])
        with sqlite3.connect(self.db_path) as conn:
            has_documents = conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]
        if has_documents:
            self.assertTrue(result["evidence_sources"])
        for source in result["evidence_sources"]:
            self.assertTrue(source["title"] and source["source_type"])
            self.assertTrue(source["original_path"] or source["source_url"])
            self.assertEqual(source["region"], "中国大陆")

    def test_case_b_overview_without_specific_problem(self):
        result = analyze_parent(CASE_B)
        self.assert_parent(result)
        self.assertTrue(result["need_analysis"]["problem_summary"])
        self.assertTrue(result["need_analysis"]["primary_skills"])

    def test_case_c_educator_and_cumulative_revision(self):
        result = analyze_educator(CASE_C)
        for key in ("user_need", "teaching_goal", "solution_landscape", "gap"):
            self.assertTrue(result["need_analysis"][key])
        for key in ("solution_mechanism", "carrier", "core_scenario", "ai_role", "human_role"):
            self.assertTrue(result["product_direction"][key])
        self.assertTrue(3 <= len(result["mvp_spec"]["core_features"]) <= 5)
        for key in ("key_pages", "min_data", "min_ai_capability", "not_now"):
            self.assertTrue(result["mvp_spec"][key])
        self.assertEqual(set(result["validation_metrics"]), {"learning", "behavior", "product"})
        revised = revise_educator(CASE_C, result, "不依赖硬件，年龄改成10–12岁，降低家长参与")
        self.assertIn("10", revised["need_analysis"]["user_need"]["age"])
        self.assertIn("12", revised["need_analysis"]["user_need"]["age"])
        self.assertEqual(revised["product_direction"]["carrier"], ["App / 网页"])
        self.assertEqual(len(revised["analysis_meta"]["revision_history"]), 1)
        again = revise_educator(CASE_C, revised, "不要语音评分")
        self.assertEqual(again["need_analysis"]["user_need"]["age"], revised["need_analysis"]["user_need"]["age"])
        self.assertEqual(len(again["analysis_meta"]["revision_history"]), 2)

    def test_live_pipeline_through_provider_with_stubbed_http(self):
        cfg = LLMConfig(provider="custom", api_key="test-placeholder", base_url="https://test.invalid/v1", model="test-model")
        seen = []

        def post(url, **kwargs):
            seen.append((url, kwargs))
            messages = kwargs["json"]["messages"]
            response_data = mock_complete_json(messages[0]["content"], messages[1]["content"])

            class Response:
                status_code = 200

                def json(self):
                    return {"choices": [{"message": {"content": json.dumps(response_data, ensure_ascii=False)}}]}

            return Response()

        with patch("llm.provider.load_config", return_value=cfg), patch("need_analysis.load_config", return_value=cfg), patch("requests.post", side_effect=post):
            result = analyze_parent(CASE_A)
        self.assertEqual(result["analysis_meta"]["mode"], "live")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], "https://test.invalid/v1/chat/completions")
        self.assertNotIn(cfg.api_key, json.dumps(apply_analysis(CASE_A, result)))

    def test_one_shared_retry_budget_and_friendly_failure(self):
        for failure in (LLMBadResponse(), LLMTimeout()):
            with patch("need_analysis.complete_json", side_effect=[failure, {"ok": True}]) as call:
                self.assertEqual(_call_validated("system", "user", lambda data: data), {"ok": True})
                self.assertEqual(call.call_count, 2)
                self.assertEqual(call.call_args.kwargs["retries"], 0)
        with patch("need_analysis.complete_json", return_value={}) as call:
            with self.assertRaises(LLMSchemaError):
                _call_validated("system", "user", lambda data: (_ for _ in ()).throw(LLMSchemaError()))
            self.assertEqual(call.call_count, 2)

    def test_retriever_unavailable_and_skill_specific_diy(self):
        diagnostics = {}
        with patch("need_analysis.get_retriever", side_effect=sqlite3.OperationalError("test")):
            self.assertEqual(retrieve_evidence(["英语"], [("中国大陆", 6)], diagnostics=diagnostics), [])
        self.assertEqual(diagnostics["retrieval_status"], "unavailable")
        prompt = fallback_diy(CASE_A, {"primary_skills": ["写作表达"]})["copyable_prompt"]
        self.assertIn("写两句", prompt)

    def new_ui(self, educator=False, overview=False):
        app = AppTest.from_file(str(ROOT / "03app/00_app.py"), default_timeout=20).run()
        app.switch_page("02_solve_need.py").run()
        app.radio(key="sn_identity").set_value("我是教育工作者" if educator else "我是家长").run()
        if not educator:
            app.radio(key="sn_parent_path").set_value(
                "我想整体看看孩子目前需要什么" if overview else "我有一个具体英语学习问题").run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_case_a_form_submit_and_bad_output_retry_ui(self):
        app = self.new_ui()
        app.selectbox(key="sn_p_age_y").set_value(7)
        app.selectbox(key="sn_p_age_m").set_value(4)
        app.text_area(key="sn_p_problem").set_value(CASE_A["problem"])
        app.multiselect(key="sn_p_methods").set_value(["分级阅读"])
        with patch.dict(os.environ, {"ENGEDUSCOPE_LLM_MOCK_MODE": "schema_error"}):
            app.button(key="sn_p_submit").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.error)
        self.assertEqual(app.session_state["sn_result"]["problem"], CASE_A["problem"])
        self.assertNotIn("need_analysis", app.session_state["sn_result"])
        app.button(key="sn_retry").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("口语表达", app.session_state["sn_result"]["need_analysis"]["primary_skills"])
        self.assertTrue(any("Analysis Result" in item.value for item in app.subheader))

    def test_case_b_form_submit_ui(self):
        app = self.new_ui(overview=True)
        app.selectbox(key="sn_p_age_y").set_value(5)
        app.selectbox(key="sn_p_age_m").set_value(6)
        app.text_area(key="sn_p_background").set_value(CASE_B["background"])
        app.button(key="sn_p_submit").click().run()
        self.assertEqual(len(app.exception), 0)
        result = app.session_state["sn_result"]
        self.assertEqual(result["entry_type"], "parent_overview")
        self.assert_parent(result)

    def test_case_c_form_submit_ui(self):
        app = self.new_ui(educator=True)
        app.radio(key="sn_e_age_mode").set_value("年龄范围").run()
        for key, value in (("start_y", 6), ("start_m", 0), ("end_y", 8), ("end_m", 11)):
            app.selectbox(key=f"sn_e_age_{key}").set_value(value)
        app.multiselect(key="sn_e_skills").set_value(["口语表达"])
        app.multiselect(key="sn_e_contexts").set_value(["家庭固定学习"])
        app.multiselect(key="sn_e_carriers").set_value(["App / 网页"])
        app.text_area(key="sn_e_pain").set_value(CASE_C["pain_point"])
        app.button(key="sn_e_submit").click().run()
        self.assertEqual(len(app.exception), 0)
        result = app.session_state["sn_result"]
        self.assertTrue(result["product_direction"])
        self.assertTrue(result["mvp_spec"])
        self.assertEqual(set(result["validation_metrics"]), {"learning", "behavior", "product"})


if __name__ == "__main__":
    unittest.main()
