"""M5 adapter and entry checks: snapshots only, no live API or user History writes."""

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

from solution_context import SolutionContextError, from_market, from_need, from_scratch, normalize_brief


def parent_result():
    return {
        "user_type": "parent", "entry_type": "parent_specific", "generated_at": "2026-09-13T18:00:00+08:00",
        "age": {"mode": "exact", "years": 7, "months": 4, "age_months": 88},
        "problem": "孩子读过故事，但很少主动开口。", "skills": ["读", "说"], "contexts": ["家庭固定学习"],
        "methods": ["分级阅读"], "analysis_meta": {"mode": "mock"},
        "need_analysis": {"problem_summary": "孩子需要把熟悉的故事输入转化为自主表达。",
                          "primary_skills": ["口语表达"], "secondary_skills": ["阅读理解"], "contexts": ["亲子共学"]},
        "solution_routes": [{"route_name": "家庭故事续说", "mechanism": "家庭活动", "why_it_fits": "利用熟悉内容减少表达负担", "evidence_ids": ["E1"]}],
        "evidence_sources": [{"id": "E1", "title": "家庭口语研究", "text": "保留原始证据文字", "source_url": "https://example.org/study#part",
                              "region": "中国大陆", "source_type": "研究论文", "original_path": "fixtures/oral.pdf", "pages": "p.3"}],
    }


def market_result():
    filters = {"region": "海外 Benchmark", "age_range": [72, 107], "skills": ["口语表达"],
               "contexts": ["家庭固定学习"], "audiences": ["家长"], "time_window": "近90天"}
    evidence = [{"id": "W3", "title": "用户讨论", "content": "用户仍依赖成人提示。", "url": "https://example.org/discussion",
                 "source_type": "公开用户讨论", "credibility_level": "C", "content_kind": "search_snippet",
                 "date": None, "date_basis": "unknown", "region": "海外 Benchmark"}]
    insight = {"id": "signal-3", "signal_title": "输入后的表达需求", "age_range": [72, 107], "skills": ["口语表达"],
               "contexts": ["家庭固定学习"], "audiences": ["家长"], "region": "海外 Benchmark",
               "problem_summary": "自由表达依赖提示", "unmet_need": "减少提示依赖的练习", "evidence_sources": evidence,
               "existing_solutions": [{"mechanism": "家庭活动", "summary": "熟悉故事复述", "evidence_ids": ["W3"]}],
               "analyst": {"interpretation": "输入向输出迁移可能不足"}, "overseas_observation": "海外家庭具体体验，待验证本地适配性"}
    chat = [{"question": "怎样减少提示？", "answer": {"hypothesis": "逐轮撤掉图片提示"}}]
    return {"kind": "market_research", "region": filters["region"], "filters": filters, "signals": [insight],
            "evidence_sources": evidence, "chat": {"signal-3": chat}, "generated_at": "2026-09-13T18:00:00+08:00",
            "opportunity_context": {"signal_id": "signal-3", "insight": insight, "filters": deepcopy(filters),
                                    "evidence_sources": evidence, "chat": chat}}


class ContextTests(unittest.TestCase):
    def test_parent_mapping_preserves_snapshot_and_evidence_ids(self):
        source = parent_result()
        before = deepcopy(source)
        with patch("llm.provider.complete_json") as llm, patch("knowledge.retrieval.get_retriever") as retrieve:
            brief = from_need(source)
            llm.assert_not_called()
            retrieve.assert_not_called()
        self.assertEqual(source, before)
        self.assertEqual(brief["source_type"], "solve_need")
        self.assertEqual(brief["age_range"], [88, 88])
        self.assertEqual(brief["skills"], ["口语表达", "阅读理解"])
        self.assertEqual(brief["contexts"], ["亲子共学"])
        self.assertEqual(brief["existing_landscape"], source["solution_routes"])
        evidence = brief["evidence_sources"][0]
        self.assertEqual(evidence["id"], "E1")
        self.assertEqual(evidence["content"], source["evidence_sources"][0]["text"])
        self.assertEqual(evidence["source_url"], "https://example.org/study#part")
        self.assertEqual(evidence["url"], "https://example.org/study")
        self.assertEqual(brief["source_context"]["need_result"], source)
        self.assertEqual(brief["source_context"]["analysis_meta"], source["analysis_meta"])
        self.assertIn("problem_summary", brief["source_context"]["interpretation"])
        brief["source_context"]["need_result"]["problem"] = "modified copy"
        self.assertEqual(source, before)

    def test_educator_revised_age_and_design_win_over_original_input(self):
        source = parent_result()
        source.update(user_type="professional", entry_type="professional", pain_point="原始口语需求",
                      product_direction={"carrier": ["网页"]})
        source["need_analysis"] = {
            "user_need": {"target_user": "10–12岁自主学习者", "age": "10–12 岁", "core_skills": ["writing"],
                          "contexts": ["自主学习"], "pain_point": "修订后需要用英语完成短篇叙事"},
            "solution_landscape": [{"mechanism": "写作反馈", "summary": "已有句子级纠错", "evidence_ids": ["E1"]}],
            "gap": ["篇章组织支持不足", "自主修改机会不足"],
        }
        brief = from_need(source)
        self.assertEqual(brief["age_range"], [120, 155])
        self.assertEqual(brief["skills"], ["写作表达"])
        self.assertEqual(brief["contexts"], ["自主学习"])
        self.assertEqual(brief["preferred_carriers"], ["App / 网页"])
        self.assertIn("篇章组织", brief["gap"])
        self.assertEqual(brief["source_context"]["original_input"]["age"]["age_months"], 88)

    def test_market_saved_opportunity_wins_and_keeps_comparison_chat_metadata(self):
        research = market_result()
        original = deepcopy(research)
        research["filters"] = dict(research["filters"], region="中国大陆", age_range=[36, 71])
        brief = from_market(research, {"id": "different-live-selection"})
        self.assertEqual(brief["source_type"], "market_insight")
        self.assertEqual(brief["region"], "海外 Benchmark")
        self.assertEqual(brief["age_range"], [72, 107])
        self.assertIn("英语学习者", brief["target_user"])
        self.assertIn("6岁", brief["target_user"])
        self.assertEqual(brief["source_context"]["audiences"], ["家长"])
        self.assertEqual(brief["core_need"], "减少提示依赖的练习")
        self.assertEqual(brief["source_context"]["chat"], original["opportunity_context"]["chat"])
        self.assertEqual(brief["source_context"]["analyst"], original["signals"][0]["analyst"])
        self.assertIn("海外家庭", brief["source_context"]["overseas_observation"])
        self.assertEqual(brief["evidence_sources"][0]["credibility_level"], "C")
        self.assertEqual(brief["evidence_sources"][0]["content_kind"], "search_snippet")
        self.assertIsNone(brief["evidence_sources"][0]["date"])

    def test_scratch_and_normalize_preserve_source_type_and_validate_scope(self):
        data = {"target_user": "家庭英语学习者", "age_range": [72, 107], "skills": ["speaking"],
                "contexts": ["家庭"], "core_need": "将熟悉故事转为自主讲述", "region": "中国大陆"}
        brief = from_scratch(data)
        self.assertEqual(brief["skills"], ["口语表达"])
        self.assertEqual(brief["contexts"], ["家庭固定学习"])
        self.assertEqual(brief["source_context"]["original_input"], data)
        inherited = from_need(parent_result())
        self.assertEqual(normalize_brief(inherited), inherited)
        constrained = dict(inherited, constraints=["减少家长参与", "先不做硬件"], scope_notes=["年龄调整后需要重新验证来源适配性"])
        self.assertEqual(normalize_brief(constrained)["constraints"], constrained["constraints"])
        self.assertEqual(normalize_brief(constrained)["scope_notes"], constrained["scope_notes"])
        with self.assertRaises(SolutionContextError):
            normalize_brief(dict(inherited, constraints=[{"not": "text"}]))
        for update in ({"age_range": [35, 90]}, {"age_range": [90, 192]}, {"age_range": [100, 90]},
                       {"age_range": [True, 90]}, {"contexts": []}, {"skills": []}, {"target_user": ""}):
            with self.subTest(update=update):
                with self.assertRaises(SolutionContextError):
                    from_scratch(dict(data, **update))

    def test_missing_inherited_scope_is_explicit_and_conflicting_ids_rejected(self):
        brief = from_market({"signals": [{"id": "s1", "signal_title": "英语学习需求待进一步明确"}], "filters": {}})
        self.assertTrue(brief["skills"])
        self.assertTrue(brief["contexts"])
        self.assertTrue(brief["source_context"]["adaptation_notes"])
        duplicate = parent_result()
        duplicate["evidence_sources"].append(dict(duplicate["evidence_sources"][0], text="conflicting source"))
        with self.assertRaises(SolutionContextError):
            from_need(duplicate)


class EntryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="engeduscope-m5-entry-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        for patcher in (
            patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(self.directory / "history.db"), "ENGEDUSCOPE_LLM_PROVIDER": "mock"}),
            patch("llm.settings.CONFIG_PATH", self.directory / "llm.json"),
            patch("web_search.settings.CONFIG_PATH", self.directory / "search.json"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=20).run()

    def test_parent_build_handoff_does_not_generate(self):
        app = self.app()
        app.session_state["sn_result"] = parent_result()
        app.switch_page("02_solve_need.py").run()
        self.assertFalse(app.exception)
        with patch("solution_analysis.generate_solution") as generate:
            app.button(key="sn_build").click().run()
            generate.assert_not_called()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["bs_brief"]["source_type"], "solve_need")
        self.assertEqual(app.session_state["bs_brief"]["evidence_sources"][0]["id"], "E1")

    def test_market_saves_opportunity_before_build_without_generating(self):
        app = self.app()
        research = market_result()
        research.pop("opportunity_context")
        app.session_state["em_result"] = research
        app.switch_page("03_explore_market.py").run()
        self.assertFalse(app.exception)
        build = next(button for button in app.button if button.label == "基于这个需求 Build a Solution")
        with patch("market_session.save_research_session", return_value=51) as save, patch("solution_analysis.generate_solution") as generate:
            build.click().run()
            save.assert_called_once()
            generate.assert_not_called()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["bs_brief"]["source_type"], "market_insight")
        self.assertEqual(app.session_state["em_result"]["opportunity_context"]["signal_id"], "signal-3")

    def test_product_history_branch_restores_without_regeneration(self):
        brief = from_need(parent_result())
        record = {"kind": "product_concept", "opportunity_brief": brief, "generated_at": "2026-09-13T18:00:00+08:00",
                  "solution": {"product_concept": {"name": "家庭故事续说"}}, "analysis_meta": {"mode": "demo"}}
        row = {"id": 52, "title": "家庭故事续说", "user_type": "教育工作者", "entry_type": "build_solution",
               "created_at": "2026-09-13T18:00:00+08:00", "summary_json": json.dumps(record, ensure_ascii=False)}
        with patch("db.list_research_sessions", return_value=[row]):
            app = self.app()
            app.switch_page("04_history.py").run()
            app.button(key="hist_view_52").click().run()
            self.assertFalse(app.exception)
            with patch("solution_analysis.generate_solution") as generate:
                app.button(key="hist_resume_52").click().run()
                generate.assert_not_called()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["bs_result"], record)
            self.assertEqual(app.session_state["bs_brief"], brief)


if __name__ == "__main__":
    unittest.main()
