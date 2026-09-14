"""M3 History round-trip and resume checks, using a temporary SQLite database."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "03app"))

from streamlit.testing.v1 import AppTest

from db import get_research_session, init_db, list_research_sessions, save_research_session
from knowledge.kb_db import init_schema
from need_analysis import analyze_educator, analyze_parent, apply_analysis
from need_session import db_entry_type, db_user_type, format_datetime, make_title


def exact_age(years, months):
    return {"mode": "exact", "years": years, "months": months,
            "age_months": years * 12 + months, "display": f"{years}岁{months}个月"}


def visible_text(app):
    return "\n".join(str(item.value) for kind in (
        "markdown", "caption", "warning", "info", "success", "code", "subheader"
    ) for item in app.get(kind))


class HistoryFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engeduscope-history-")
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "ENGEDUSCOPE_DB_PATH": str(Path(self.temp.name) / "history.db"),
            "ENGEDUSCOPE_LLM_PROVIDER": "mock",
            "ENGEDUSCOPE_LLM_MOCK_MODE": "ok",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.settings = patch("llm.settings.CONFIG_PATH", Path(self.temp.name) / "llm_config.json")
        self.settings.start()
        self.addCleanup(self.settings.stop)
        init_db()
        init_schema()

    def snapshot(self, professional=False):
        if professional:
            inputs = {
                "user_type": "professional", "entry_type": "professional",
                "age": {"mode": "range", "start": exact_age(6, 0), "end": exact_age(8, 11)},
                "skills": ["口语表达"], "contexts": ["家庭固定学习"], "carriers": ["App / 网页"],
                "pain_point": "已有阅读输入，但主动口语不足，希望探索家庭低成本高频输出机制。",
            }
            result = apply_analysis(inputs, analyze_educator(inputs))
        else:
            inputs = {
                "user_type": "parent", "entry_type": "parent_specific", "age": exact_age(7, 4),
                "skills": ["说", "读"], "contexts": ["家庭固定学习"], "methods": ["分级阅读"],
                "methods_note": "每天一起读绘本", "background": "",
                "problem": "已经读了一段时间分级阅读，自己读得还可以，但是平时几乎不会主动说英语。",
            }
            result = apply_analysis(inputs, analyze_parent(inputs))
        result["evidence_sources"] = [{
            "id": "E1", "title": "测试家庭口语研究", "source_type": "研究论文",
            "source_kind": "pdf", "kind_label": "PDF", "region": "中国大陆",
            "original_path": "fixtures/family-speaking.pdf", "source_url": "",
            "text": "家庭口语活动的研究摘要", "pages": "p.3",
        }]
        result["analysis_meta"]["retrieval_status"] = "available"
        return result

    def save(self, result):
        return save_research_session(make_title(result), db_user_type(result), db_entry_type(result), result)

    def open_history(self, session_id):
        app = AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=20).run()
        app.switch_page("04_history.py").run()
        app.button(key=f"hist_view_{session_id}").click().run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_parent_saved_evidence_feedback_and_resume(self):
        result = self.snapshot()
        session_id = self.save(result)
        self.assertEqual(json.loads(get_research_session(session_id)["summary_json"]), result)
        app = self.open_history(session_id)
        text = visible_text(app)
        self.assertIn(format_datetime(result["generated_at"]), text)
        self.assertIn("年", format_datetime(result["generated_at"]))
        for expected in ("我们理解的问题", "AI DIY", "测试家庭口语研究", "研究论文", "fixtures/family-speaking.pdf"):
            self.assertIn(expected, text)
        app.button(key=f"hist_{session_id}_rank_btn").click().run()
        self.assertIn("已收到您的反馈", visible_text(app))
        self.assertEqual(len(list_research_sessions()), 1)
        with patch("need_analysis.analyze_parent", side_effect=AssertionError("restore must not call API")):
            app.button(key=f"hist_resume_{session_id}").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["sn_result"], result)
        self.assertEqual(app.selectbox(key="sn_p_age_y").value, 7)
        self.assertEqual(app.selectbox(key="sn_p_age_m").value, 4)
        self.assertEqual(app.text_area(key="sn_p_problem").value, result["problem"])
        self.assertIn("已保存到 History", visible_text(app))
        self.assertFalse(any(button.label == "保存到 History" for button in app.button))
        app.switch_page("01_home.py").run()
        app.switch_page("02_solve_need.py").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.text_area(key="sn_p_problem").value, result["problem"])
        self.assertEqual(app.session_state["sn_result"], result)

    def test_educator_restores_design_and_can_revise(self):
        result = self.snapshot(professional=True)
        session_id = self.save(result)
        app = self.open_history(session_id)
        for field in ("Teaching Goal", "Existing Solution Landscape", "Gap", "Product Direction", "MVP", "Validation Metrics"):
            self.assertIn(field, visible_text(app))
        app.button(key=f"hist_resume_{session_id}").click().run()
        self.assertEqual(len(app.exception), 0)
        for field in ("generated_at", "need_analysis", "evidence_sources", "product_direction", "mvp_spec", "validation_metrics"):
            self.assertEqual(app.session_state["sn_result"][field], result[field])
        self.assertEqual(app.selectbox(key="sn_e_age_start_y").value, 6)
        self.assertEqual(app.selectbox(key="sn_e_age_end_y").value, 8)
        # AppTest does not retain programmatic st.switch_page as its next run target.
        app.switch_page("02_solve_need.py").run()
        instruction = "年龄改成 10–12 岁，不依赖硬件，降低家长参与"
        app.text_area(key="sn_revision_instruction").set_value(instruction)
        next(button for button in app.button if button.label == "调整方案").click().run()
        self.assertEqual(len(app.exception), 0)
        revised = app.session_state["sn_result"]
        self.assertEqual(revised["analysis_meta"]["revision_history"][-1]["instruction"], instruction)
        self.assertEqual(revised["age"], result["age"])
        app.button(key="sn_save").click().run()
        self.assertEqual(len(list_research_sessions()), 2)
        saved_session = list_research_sessions()[0]
        self.assertIn("10", saved_session["title"])
        self.assertNotIn("6岁", saved_session["title"])
        saved = json.loads(saved_session["summary_json"])
        self.assertEqual(saved, revised)

    def test_legacy_record_stays_readable_and_can_resume(self):
        legacy = {"user_type": "parent", "entry_type": "parent_overview", "age": exact_age(8, 0),
                  "background": "每天听英文儿歌，还没有确定关注哪项能力。", "skills": [], "contexts": [], "methods": []}
        session_id = self.save(legacy)
        app = self.open_history(session_id)
        self.assertIn("M1 旧版输入记录", visible_text(app))
        app.button(key=f"hist_resume_{session_id}").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["sn_result"], legacy)
        self.assertEqual(app.text_area(key="sn_p_background").value, legacy["background"])
        self.assertTrue(any(button.label == "根据这条需求生成分析" for button in app.button))


if __name__ == "__main__":
    unittest.main()
