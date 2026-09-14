"""Targeted M5 page tests: explicit generation, handoff/history, revisions and exports."""

import json
import os
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "03app"))

from streamlit.testing.v1 import AppTest

from db import list_research_sessions


def visible(app):
    return "\n".join(str(item.value) for kind in ("markdown", "caption", "warning", "info", "success", "error", "subheader", "code")
                     for item in app.get(kind))


def brief_fixture():
    return {"source_type": "market_insight", "target_user": "已有阅读输入但主动表达少的儿童及其家庭",
            "age_range": [72, 107], "skills": ["口语表达"], "contexts": ["家庭固定学习"], "region": "中国大陆",
            "core_need": "在家庭中形成低成本、高频的主动表达机会", "pain_point": "缺少自主开口机会",
            "existing_landscape": [{"mechanism": "家庭活动", "summary": "围绕读物安排对话"}], "gap": "提示较多，独立表达少",
            "preferred_carriers": ["App / 网页"],
            "evidence_sources": [{"id": "E1", "title": "家庭口语使用记录", "source_type": "公开用户讨论",
                                  "region": "中国大陆", "url": "https://example.org/family", "content": "自由表达仍需提示。"}],
            "source_context": {"signal_id": "signal_1", "adaptation_notes": ["需要验证家庭场景适配性。"]}}


def record_fixture(brief):
    solution = {
        "teaching_goal": {"learning_outcome": "在熟悉情境下自主表达完整意思", "behavior_change": "主动发起简短表达"},
        "solution_landscape": [{"mechanism": "家庭活动", "what_exists": "已有共读机会", "what_remains_unresolved": "自主表达仍依赖提示", "evidence_ids": []}],
        "opportunity_gap": {"existing_strength": "熟悉已有学习内容", "remaining_friction": "成人提示较多", "opportunity": "逐步减少提示的微任务"},
        "product_concept": {"name": "今日表达小任务", "value_proposition": "把已读内容转成短表达机会",
                            "target_user": brief["target_user"], "core_problem": brief["core_need"],
                            "core_mechanism": "短任务加逐级提示", "core_scenario": "家庭阅读后"},
        "solution_mechanism": {"steps": ["选材料", "尝试表达", "记录提示"], "why_it_might_work": "复用熟悉材料降低负担", "assumptions": ["儿童愿意尝试"]},
        "carrier": {"choices": ["App / 网页"], "rationale": "复用家庭已有设备"},
        "ai_role": ["生成短问题"], "human_role": ["成人确认材料与观察体验"],
        "mvp": {"core_features": [{"name": name, "why_essential": "用于检验核心机制"} for name in ("材料选择", "短任务", "提示记录")],
                "key_pages": [{"name": "今日任务", "purpose": "完成表达练习"}], "minimal_data": ["目标年龄和材料"],
                "minimal_ai_capability": ["从材料生成一个问题"], "not_now": ["硬件和精细发音评分"]},
        "demo_build_path": [{"step": 1, "title": "画出任务页", "action": "用静态页面串联练习", "deliverable": "可点击页面"}],
        "fast_prototype": {"approach": "先用静态网页验证流程", "copyable_prompt": "请创建一个儿童英语短表达任务页面，使用示例数据。"},
        "validation_metrics": {key: {"metric": text, "how_to_measure": "记录试用表现"} for key, text in
                               (("learning", "无提示表达"), ("behavior", "主动启动"), ("product", "任务完成"))},
        "validation_plan": {"sample": "少量有相似需求的家庭", "duration": "一周试用", "comparison": "与当前共读方式比较",
                            "decision_criteria": ["能够独立完成核心任务则继续验证"]},
        "risks": [{"risk": "任务兴趣不足", "cheap_test": "先请家庭试用纸面任务"}], "evidence_ids": [],
    }
    return {"kind": "product_concept", "entry_type": "build_solution", "opportunity_brief": deepcopy(brief),
            "solution": solution, "evidence_sources": deepcopy(brief.get("evidence_sources") or []),
            "generated_at": "2026-09-13T19:00:00+08:00", "analysis_meta": {"mode": "demo", "provider": "Demo", "revision_history": []}}


class BuildSolutionUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engeduscope-build-ui-")
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(Path(self.temp.name) / "history.db")})
        env.start()
        self.addCleanup(env.stop)
        self.generate = Mock(side_effect=record_fixture)
        self.revise = Mock(side_effect=self.revision)
        analysis = types.ModuleType("solution_analysis")
        analysis.generate_solution = self.generate
        analysis.revise_solution = self.revise
        exporter = types.ModuleType("solution_export")
        exporter.to_markdown = lambda record: "# " + record["solution"]["product_concept"]["name"] + "\n\n" + record["solution"]["fast_prototype"]["copyable_prompt"]
        self.export = Mock(side_effect=lambda record: self.write_export(exporter.to_markdown(record)))
        exporter.export_markdown = self.export
        modules = patch.dict(sys.modules, {"solution_analysis": analysis, "solution_export": exporter})
        modules.start()
        self.addCleanup(modules.stop)
        self.app = AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=20).run()

    def write_export(self, markdown):
        path = Path(self.temp.name) / "concept.md"
        path.write_text(markdown, encoding="utf-8")
        return path

    @staticmethod
    def revision(record, instruction):
        changed = deepcopy(record)
        changed["solution"]["product_concept"]["name"] = "低参与表达小任务"
        changed["solution"]["human_role"] = ["成人只需首次确认材料"]
        changed["analysis_meta"]["revision_history"].append({"instruction": instruction, "at": "2026-09-13T19:01:00+08:00"})
        return changed

    def open_build(self, brief=None):
        if brief:
            self.app.session_state["bs_handoff"] = brief
        self.app.switch_page("06_build_solution.py").run()
        self.assertEqual(len(self.app.exception), 0)
        return self.app

    def test_scratch_requires_preview_then_explicit_generate(self):
        app = self.open_build()
        self.assertFalse(self.generate.called)
        app.text_input(key="bs_target_user").set_value("小学低年级英语学习家庭")
        app.multiselect(key="bs_skills").select("口语表达")
        app.multiselect(key="bs_contexts").select("家庭固定学习")
        app.text_area(key="bs_core_need").set_value("阅读输入后很少主动表达，希望建立简短练习机会。")
        next(button for button in app.button if button.label == "确认机会输入").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(self.generate.called)
        self.assertTrue(any("Opportunity Brief" in item.label for item in app.expander))
        app.button(key="bs_generate").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.generate.call_count, 1)
        for expected in ("① 产品判断", "② Opportunity", "③ 核心机制", "④ MVP", "⑤ Validation",
                         "Teaching Goal", "Carrier", "AI Role", "Human Role"):
            self.assertIn(expected, visible(app))
        self.assertIn("当前为规则生成的产品假设", visible(app))
        for label in ("Solution Landscape", "Demo Build Path", "查看 / 复制 Prompt", "参考资料", "Later", "Risks"):
            self.assertTrue(any(label in item.label and not item.proto.expanded for item in app.expander))
        self.assertFalse(self.export.called)
        self.assertEqual(list_research_sessions(), [])

    def test_handoff_revise_save_export_and_history_restore(self):
        brief = brief_fixture()
        app = self.open_build(brief)
        self.assertFalse(self.generate.called)
        self.assertIn("家庭口语使用记录", visible(app))
        self.assertIn("需要验证家庭场景适配性", visible(app))
        app.button(key="bs_generate").click().run()
        self.assertEqual(self.generate.call_args.args[0], brief)
        app.text_area(key="bs_revision_instruction").set_value("减少家长参与，不依赖硬件")
        next(button for button in app.button if button.label == "调整产品方案").click().run()
        self.assertEqual(len(app.exception), 0)
        record = deepcopy(app.session_state["bs_result"])
        self.assertEqual(record["opportunity_brief"], brief)
        self.assertEqual(record["analysis_meta"]["revision_history"][-1]["instruction"], "减少家长参与，不依赖硬件")
        app.button(key="bs_save").click().run()
        saved_row = list_research_sessions()[0]
        self.assertEqual(json.loads(saved_row["summary_json"]), record)
        self.assertEqual(saved_row["entry_type"], "build_solution")
        self.assertFalse(self.export.called)
        app.button(key="bs_export_btn").click().run()
        self.assertEqual(self.export.call_count, 1)
        self.assertIn("低参与表达小任务", (Path(self.temp.name) / "concept.md").read_text())
        self.assertIn("Markdown 文件已导出", visible(app))
        app.switch_page("04_history.py").run()
        app.button(key=f"hist_view_{saved_row['id']}").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("低参与表达小任务", visible(app))
        self.assertNotIn("M1 旧版输入记录", visible(app))
        calls = self.generate.call_count
        revision_calls = self.revise.call_count
        app.button(key=f"hist_resume_{saved_row['id']}").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.generate.call_count, calls)
        self.assertEqual(self.revise.call_count, revision_calls)
        self.assertEqual(app.session_state["bs_result"], record)
        self.assertEqual(app.session_state["bs_brief"], brief)
        self.assertIn("产品方案已保存到 History", visible(app))
        # AppTest retains the previous page's script path after st.switch_page;
        # explicitly target Build for the next user interaction.
        app.switch_page("06_build_solution.py")._run()
        self.assertEqual(self.generate.call_count, calls)
        self.assertEqual(self.revise.call_count, revision_calls)
        app.text_area(key="bs_revision_instruction").set_value("恢复后只验证一个核心交互")
        next(button for button in app.button if button.label == "调整产品方案").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.generate.call_count, calls)
        self.assertEqual(self.revise.call_count, revision_calls + 1)
        self.assertEqual(app.session_state["bs_result"]["analysis_meta"]["revision_history"][-1]["instruction"], "恢复后只验证一个核心交互")
        self.assertEqual(json.loads(list_research_sessions()[0]["summary_json"]), record)

    def test_failures_preserve_brief_and_current_solution(self):
        app = self.open_build(brief_fixture())
        self.generate.side_effect = RuntimeError("private service details")
        app.button(key="bs_generate").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("本次产品方案暂时无法生成", visible(app))
        self.assertNotIn("private service details", visible(app))
        self.assertEqual(app.session_state["bs_brief"], brief_fixture())
        self.generate.side_effect = record_fixture
        app.button(key="bs_generate").click().run()
        original = deepcopy(app.session_state["bs_result"])
        self.revise.side_effect = RuntimeError("private revision details")
        app.text_area(key="bs_revision_instruction").set_value("更简短")
        next(button for button in app.button if button.label == "调整产品方案").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["bs_result"], original)
        self.assertEqual(app.text_area(key="bs_revision_instruction").value, "更简短")
        self.assertIn("本次调整暂时无法完成", visible(app))


if __name__ == "__main__":
    unittest.main()
