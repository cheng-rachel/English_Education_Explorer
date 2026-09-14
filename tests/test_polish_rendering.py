"""Contact fixtures through real Streamlit renderers and legacy History recovery."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))
from streamlit.testing.v1 import AppTest
from history_library import parse_summary, session_metadata
from need_session import history_restore_state
from market_session import restore_state as restore_market
from solution_session import restore_state as restore_solution

CONTACT = "微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com"
OFFICIAL = "https://learnenglishkids.britishcouncil.org/"


def visible(app):
    kinds = ("title", "subheader", "markdown", "caption", "warning", "info", "success", "error", "text", "code")
    return "\n".join(str(element.value) for kind in kinds for element in app.get(kind))


def evidence():
    return [
        {"id": "E1", "title": "官方英语学习材料", "source_type": "公开用户讨论", "region": "中国大陆",
         "source_url": OFFICIAL, "url": OFFICIAL, "text": CONTACT, "content": CONTACT},
        {"id": "L1", "title": "自然拼读到阅读", "source_type": "通用学习路径参考资料", "region": "general_reference",
         "raw_category": "learnpath", "content": "练习把字音与阅读意义联系起来。", "text": "练习把字音与阅读意义联系起来。"},
    ]


def need_record():
    return {"user_type": "parent", "entry_type": "parent_specific", "problem": CONTACT, "skills": ["读"],
            "contexts": ["家庭固定学习"], "methods": ["分级阅读"],
            "age": {"years": 7, "months": 0, "age_months": 84, "display": "7岁0个月"},
            "need_analysis": {"problem_summary": "EngEduScope 分析。" + CONTACT,
                              "possible_causes": [{"cause": CONTACT, "why": CONTACT}], "primary_skills": ["阅读理解"]},
            "solution_routes": [{"route_name": "阅读练习", "teacher_profile": "建议联系王老师安排试听。",
                                 "recommended_actions": [CONTACT]}],
            "ai_diy": {"title": "阅读小任务", "copyable_prompt": CONTACT},
            "evidence_sources": evidence(), "analysis_meta": {"mode": "mock"}, "generated_at": "2026-09-13T12:00:00"}


def market_record():
    analyst = {"evidence": [{"statement": CONTACT, "evidence_ids": ["E1"]}],
               "interpretation": CONTACT, "hypothesis": "通过短任务验证。", "limitations": [CONTACT]}
    signal = {"id": "M1", "signal_title": "阅读迁移困难", "region": "中国大陆", "age_range": [72, 107],
              "problem_summary": CONTACT, "analyst": analyst, "evidence_sources": evidence()}
    return {"kind": "market_research", "region": "中国大陆",
            "filters": {"region": "中国大陆", "time_window": "近90天", "age_range": [72, 107],
                        "skills": ["阅读理解"], "contexts": ["自主学习"], "audiences": ["家长"]},
            "signals": [signal], "evidence_sources": evidence(), "analysis_meta": {"mode": "demo"},
            "chat": {"M1": [{"question": CONTACT, "answer": analyst, "generated_at": "2026-09-13T12:00:00"}]},
            "search_meta": {"status": "local_only", "failures": [{"reason": CONTACT,
                            "url": "https://www.xiaohongshu.com/user/profile/abc_teacher123"}]}}


def solution_record():
    return {"kind": "product_concept", "entry_type": "build_solution", "evidence_sources": evidence(),
            "opportunity_brief": {"source_type": "scratch", "target_user": "7岁儿童", "age_range": [84, 84],
                                  "skills": ["阅读理解"], "contexts": ["家庭固定学习"], "region": "中国大陆",
                                  "core_need": CONTACT, "evidence_sources": evidence()},
            "solution": {"product_concept": {"name": "阅读练习工具", "value_proposition": CONTACT, "core_problem": CONTACT},
                         "teaching_goal": {"learning_outcome": CONTACT}, "ai_role": [CONTACT], "human_role": [CONTACT],
                         "fast_prototype": {"copyable_prompt": CONTACT}, "risks": [{"risk": "阅读难度", "cheap_test": CONTACT}]},
            "analysis_meta": {"mode": "demo", "revision_history": [{"instruction": CONTACT, "at": "2026-09-13T12:00:00"}]}}


class RenderSafetyChecks(unittest.TestCase):
    def assert_clean(self, app):
        self.assertFalse(app.exception, [item.message for item in app.exception])
        output = visible(app)
        for secret in ("abc_teacher123", "13812345678", "teacher@example.com", "建议联系王老师", "EngEduScope"):
            self.assertNotIn(secret, output)
        self.assertIn(OFFICIAL, output)
        return output

    def render(self, script, fixture):
        app = AppTest.from_string(
            "import sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(ROOT / '03app')!r})\n"
            "import streamlit as st\n" + script, default_timeout=15)
        app.session_state["fixture"] = deepcopy(fixture)
        with patch("requests.get", side_effect=AssertionError("rendering must not fetch")), patch("requests.post", side_effect=AssertionError("rendering must not call AI")):
            app.run()
        return app

    def test_need_result_and_direct_evidence_renderer(self):
        app = self.render("from need_session import render_analysis_result, render_evidence\n"
                          "render_analysis_result(st.session_state['fixture'])\n"
                          "render_evidence(st.session_state['fixture'])\n", need_record())
        output = self.assert_clean(app)
        self.assertIn("Learning Reference", output)
        self.assertIn("通用学习路径参考资料", output)

    def test_market_chat_analyst_and_search_snippets(self):
        app = self.render("from market_session import render_market_research, render_analyst\n"
                          "render_market_research(st.session_state['fixture'])\n"
                          "render_analyst(st.session_state['fixture']['signals'][0]['analyst'])\n", market_record())
        output = self.assert_clean(app)
        self.assertIn("Market Evidence", output)
        self.assertIn("不用于判断市场趋势", output)
        self.assertIn("追问 1", output)

    def test_build_brief_result_and_revision(self):
        app = self.render("from solution_session import render_opportunity_brief, render_product_concept\n"
                          "render_opportunity_brief(st.session_state['fixture']['opportunity_brief'])\n"
                          "render_product_concept(st.session_state['fixture'])\n", solution_record())
        self.assert_clean(app)

    def test_legacy_history_visible_restore_and_no_rewrite(self):
        original = need_record()
        encoded = json.dumps(original, ensure_ascii=False)
        row = {"id": 42, "entry_type": "solve_need_parent_specific", "title": "EngEduScope 保存的阅读研究。" + CONTACT,
               "user_type": "家长", "created_at": "2026-09-13T12:00:00", "summary_json": encoded}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"ENGEDUSCOPE_LLM_PROVIDER": "mock"}), \
                patch("llm.settings.CONFIG_PATH", Path(folder) / "ai.json"), \
                patch("web_search.settings.CONFIG_PATH", Path(folder) / "search.json"), \
                patch("db.list_research_sessions", return_value=[row]), \
                patch("requests.get", side_effect=AssertionError("History must not fetch")), \
                patch("requests.post", side_effect=AssertionError("History must not call AI")):
            app = AppTest.from_file(str(ROOT / "03app/00_app.py"), default_timeout=30).run()
            app.switch_page("04_history.py").run()
            app.button(key="hist_view_42").click().run()
            self.assert_clean(app)
        self.assertEqual(row["summary_json"], encoded)
        self.assertTrue(session_metadata(row)["readable"])
        outputs = [parse_summary(encoded), history_restore_state(original),
                   restore_market(market_record()), restore_solution(solution_record())]
        for state in outputs:
            text = json.dumps(state, ensure_ascii=False)
            for secret in ("abc_teacher123", "13812345678", "teacher@example.com", "EngEduScope"):
                self.assertNotIn(secret, text)
            self.assertIn(OFFICIAL, text)


if __name__ == "__main__":
    unittest.main()
