"""Student input, plan rendering and History restore; isolated storage, no real services."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "03app"))

from streamlit.testing.v1 import AppTest
from db import get_research_session, init_db, list_research_sessions, save_research_session
from history_library import session_metadata
from need_session import STUDENT_SKILL_LABELS, db_entry_type, db_user_type, history_restore_state, make_title

HEADINGS = ["你现在可能卡在哪里", "先解决什么", "今天可以怎么练", "接下来一周怎么安排", "怎么判断有没有进步", "什么时候建议找老师"]


def visible(app):
    return "\n".join(str(item.value) for kind in ("subheader", "markdown", "caption", "warning", "info", "error", "success", "code")
                     for item in app.get(kind))


def age(year=12, month=0):
    return {"mode": "exact", "years": year, "months": month, "age_months": year * 12 + month,
            "display": f"{year}岁{month}个月"}


def plan():
    return {
        "bottleneck": "你能读懂单句，但还没把相邻段落的信息连起来。",
        "priorities": ["先找每段的主旨", "再说明两段之间的联系"],
        "today": {"duration": "10分钟", "steps": ["选一篇熟悉的两段短文，每段用一句话概括。", "圈出两段里指向同一人物的词。"]},
        "week_plan": [{"days": "第1–3天", "actions": ["每天选两段，写一句段间联系。"]},
                      {"days": "第4–7天", "actions": ["换一篇相近难度的文章，自己完成。"]}],
        "stages": [], "progress_signals": ["不看提示也能说出两段之间的联系。"],
        "increase_difficulty_when": ["连续两次能找到原文线索再增加一段。"],
        "teacher_support": {"when": ["反复练习后仍不知道怎样找原文线索时。"],
                            "profile": "能示范阅读思考步骤、愿意逐步减少提示的英语老师。"},
    }


def analysis():
    return {
        "generated_at": "2026-09-14T14:00:00+08:00", "analysis_meta": {"mode": "mock", "retrieval_status": "available"},
        "need_analysis": {"problem_summary": "认识单词但阅读长文时难以建立段间联系。", "primary_skills": ["阅读理解"], "contexts": ["自主学习"]},
        "student_practice_plan": plan(),
        "need_intent": {"primary_intent": "skill_difficulty", "secondary_intents": [], "method": "hidden_engineering_marker"},
        "content_role_strategy": {"mechanism_weight": "hidden_strategy_marker"},
        "evidence_sources": [{"id": "E1", "title": "阅读策略资料", "region": "general_reference", "raw_category": "learnpath",
                              "source_type": "通用学习路径参考资料", "original_path": "fixtures/reading.md", "text": "先概括各段，再找段间联系。"}],
        "search_meta": {"status": "not_configured", "requested": False, "searched_at": None, "message": "未启用联网服务，本次使用本地资料。"},
        "evidence_note": "这份资料提供练习方法参考，具体难度还需试练后调整。",
    }


def snapshot():
    return {"user_type": "student", "entry_type": "student_specific", "age": age(), "skills": ["阅读", "单词"],
            "contexts": ["自主学习"], "problem": "单词大多认识，但长文章读不懂。", **analysis()}


class StudentNeedUITests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="need-student-ui-")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        for patcher in (
            patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(self.directory / "history.db"),
                                   "ENGEDUSCOPE_RAW_ROOT": str(self.directory / "raw"),
                                   "ENGEDUSCOPE_KNOWLEDGE_ROOT": str(self.directory / "knowledge"),
                                   "ENGEDUSCOPE_LLM_PROVIDER": "mock"}, clear=True),
            patch("llm.settings.CONFIG_PATH", self.directory / "llm.json"),
            patch("web_search.settings.CONFIG_PATH", self.directory / "search.json"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        init_db()

    def app(self, page="02_solve_need.py"):
        app = AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=25).run()
        app.switch_page(page).run()
        self.assertFalse(app.exception)
        return app

    def test_student_form_uses_full_existing_age_range_and_validates_before_analysis(self):
        with patch("need_analysis.analyze_student", return_value=analysis(), create=True) as analyze:
            app = self.app()
            app.radio(key="sn_identity").set_value("我是学生").run()
            self.assertEqual(app.multiselect(key="sn_s_skills").options, STUDENT_SKILL_LABELS)
            self.assertEqual(app.selectbox(key="sn_s_age_y").options, [str(year) for year in range(3, 16)])
            app.button(key="sn_s_submit").click().run()
            analyze.assert_not_called()
            self.assertIn("请先选择你的年龄", visible(app))
            app.selectbox(key="sn_s_age_y").set_value(3)
            app.selectbox(key="sn_s_age_m").set_value(0)
            app.text_area(key="sn_s_problem").set_value("听懂一点英语，但是不知道怎么说。")
            app.multiselect(key="sn_s_skills").set_value(["不确定"])
            app.multiselect(key="sn_s_contexts").set_value(["自主学习"])
            app.button(key="sn_s_submit").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(analyze.call_count, 1)
            submitted = analyze.call_args.args[0]
            self.assertEqual((submitted["user_type"], submitted["entry_type"], submitted["age"]["age_months"]), ("student", "student_specific", 36))
            self.assertEqual(submitted["skills"], ["不确定"])
            for heading in HEADINGS:
                self.assertIn(heading, visible(app))
            self.assertIn("未启用联网服务，本次使用本地资料", visible(app))
            self.assertIn("具体难度还需试练后调整", visible(app))
            self.assertNotIn("hidden_engineering_marker", visible(app))
            self.assertNotIn("hidden_strategy_marker", visible(app))
            self.assertFalse(any(button.key == "sn_build" for button in app.button))
            self.assertNotIn("MVP", visible(app))
            app.button(key="sn_save").click().run()
        saved = list_research_sessions()
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0]["user_type"], saved[0]["entry_type"]), ("学生", "solve_need_student"))
        self.assertEqual(json.loads(saved[0]["summary_json"])["student_practice_plan"], plan())

    def test_saved_student_restores_inputs_and_plan_without_services_then_can_reanalyze(self):
        result = snapshot()
        session_id = save_research_session(make_title(result), db_user_type(result), db_entry_type(result), result)
        row = get_research_session(session_id)
        self.assertEqual(session_metadata(row)["type"], "Solve a Need")
        self.assertTrue(session_metadata(row)["readable"])
        self.assertEqual(session_metadata(row)["skills"], ["阅读理解"])
        self.assertNotIn("sn_pending_analysis", history_restore_state(result, session_id))
        targets = ["need_analysis.analyze_student", "need_analysis.analyze_parent", "need_analysis.analyze_educator",
                   "knowledge.retrieval.get_retriever", "web_search.provider.search_web", "llm.provider.complete_json"]
        blockers = []
        try:
            for target in targets:
                blocker = patch(target, side_effect=AssertionError("History restore must be read-only"), create=True)
                blockers.append((blocker, blocker.start()))
            app = self.app("04_history.py")
            app.button(key=f"hist_view_{session_id}").click().run()
            self.assertFalse(app.exception)
            for heading in HEADINGS:
                self.assertIn(heading, visible(app))
            self.assertIn("你想解决的英语学习困难", visible(app))
            app.button(key=f"hist_resume_{session_id}").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key="sn_identity").value, "我是学生")
            self.assertEqual(app.selectbox(key="sn_s_age_y").value, 12)
            self.assertEqual(app.text_area(key="sn_s_problem").value, result["problem"])
            self.assertEqual(app.multiselect(key="sn_s_skills").value, ["阅读", "单词"])
            self.assertEqual(app.session_state["sn_result"], result)
            self.assertIn("已保存到 History", visible(app))
            self.assertFalse(any(button.key == "sn_build" for button in app.button))
            app.switch_page("01_home.py").run()
            app.switch_page("02_solve_need.py").run()
            self.assertEqual(app.session_state["sn_result"], result)
            for _, spy in blockers:
                spy.assert_not_called()
        finally:
            for blocker, _ in reversed(blockers):
                blocker.stop()
        updated = analysis()
        updated["generated_at"] = "2026-09-14T15:00:00+08:00"
        updated["student_practice_plan"]["today"]["steps"] = ["重新分析后先独立概括两段。"]
        with patch("need_analysis.analyze_student", return_value=updated, create=True) as analyze:
            app.button(key="sn_reanalyze").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(analyze.call_count, 1)
            self.assertIn("重新分析后先独立概括两段", visible(app))
        self.assertEqual(json.loads(get_research_session(session_id)["summary_json"]), result)

    def test_parent_starting_action_plan_precedes_routes_and_filters_contact_text(self):
        parent = {"user_type": "parent", "entry_type": "parent_overview", "age": age(4), "background": "想在家开始英语启蒙。",
                  "skills": ["听"], "contexts": [], "methods": [], **analysis()}
        parent.pop("student_practice_plan")
        parent["parent_action_plan"] = plan()
        parent["parent_action_plan"]["stages"] = [
            {"period": "前2–4周", "actions": ["围绕同一本图画书听和指认。"], "duration": "每天5分钟", "materials": ["熟悉的图画书"], "advance_when": ["愿意听并能指认熟悉图片。"]},
            {"period": "4–8周", "actions": ["加一句可以选择回应的简单问题。"], "duration": "每天5–8分钟", "materials": ["同主题图画书"], "advance_when": ["能在少量提示下选择或回应。"]},
        ]
        parent["parent_action_plan"]["teacher_support"]["profile"] += " 联系王老师，微信：private_teacher_88，电话13800138000。"
        parent["solution_routes"] = [{"route_name": "家庭共读", "recommended_actions": []}]
        original = deepcopy(parent)
        script = "from need_session import render_analysis_result\nimport streamlit as st\nrender_analysis_result(st.session_state['fixture'])"
        app = AppTest.from_string(script)
        app.session_state["fixture"] = parent
        app.run()
        self.assertFalse(app.exception)
        text = visible(app)
        self.assertLess(text.index("家长行动方案"), text.index("3 条解决路径"))
        for heading in ["现在从哪里开始", "每天具体做什么（时长/材料）", "前2–4周", "4–8周", "什么时候进入下一阶段", "怎么判断有效"]:
            self.assertIn(heading, text)
        self.assertNotIn("private_teacher_88", text)
        self.assertNotIn("13800138000", text)
        self.assertEqual(parent, original)

    def test_real_demo_student_analysis_save_and_history_restore_without_network(self):
        import need_analysis

        with patch("requests.sessions.Session.request", side_effect=AssertionError("No external network in this test")) as network, \
             patch("requests.post", side_effect=AssertionError("No external API in this test")) as post, \
             patch("need_analysis.analyze_student", wraps=need_analysis.analyze_student) as analyze, \
             patch("need_analysis.get_retriever", wraps=need_analysis.get_retriever) as retrieve:
            app = self.app()
            app.radio(key="sn_identity").set_value("我是学生").run()
            app.selectbox(key="sn_s_age_y").set_value(12)
            app.selectbox(key="sn_s_age_m").set_value(3)
            app.text_area(key="sn_s_problem").set_value("单词大多认识，但长一点的英语文章读不懂，尤其不清楚每段之间有什么联系。")
            app.multiselect(key="sn_s_skills").set_value(["阅读", "单词"])
            app.multiselect(key="sn_s_contexts").set_value(["自主学习"])
            app.button(key="sn_s_submit").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(analyze.call_count, 1)
            result = deepcopy(app.session_state["sn_result"])
            self.assertEqual(result["analysis_meta"]["mode"], "mock")
            self.assertTrue(result["need_intent"]["primary_intent"])
            self.assertIn("阅读理解", result["need_analysis"]["primary_skills"])
            self.assertTrue(result["student_practice_plan"]["today"]["steps"])
            self.assertTrue(result["student_practice_plan"]["week_plan"])
            self.assertEqual(result["search_meta"]["status"], "not_configured")
            for heading in HEADINGS:
                self.assertIn(heading, visible(app))
            self.assertFalse(any(button.key == "sn_build" for button in app.button))
            app.button(key="sn_save").click().run()
            saved = list_research_sessions()
            self.assertEqual(len(saved), 1)
            row = saved[0]
            self.assertEqual((row["user_type"], row["entry_type"]), ("学生", "solve_need_student"))
            self.assertEqual(json.loads(row["summary_json"]), result)
            retrieval_calls = retrieve.call_count
            app.switch_page("04_history.py").run()
            app.button(key=f"hist_view_{row['id']}").click().run()
            self.assertFalse(app.exception)
            for heading in HEADINGS:
                self.assertIn(heading, visible(app))
            app.button(key=f"hist_resume_{row['id']}").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key="sn_identity").value, "我是学生")
            self.assertEqual(app.selectbox(key="sn_s_age_y").value, 12)
            self.assertEqual(app.selectbox(key="sn_s_age_m").value, 3)
            self.assertEqual(app.session_state["sn_result"], result)
            self.assertEqual(app.session_state["sn_saved"]["id"], row["id"])
            self.assertEqual(analyze.call_count, 1)
            self.assertEqual(retrieve.call_count, retrieval_calls)
            network.assert_not_called()
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
