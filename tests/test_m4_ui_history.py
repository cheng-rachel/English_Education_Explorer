"""M4 UI actions and History snapshots, with temporary DB and isolated analysis stubs."""

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
    return "\n".join(str(item.value) for kind in ("markdown", "caption", "warning", "info", "success", "error", "subheader")
                     for item in app.get(kind))


def research_fixture(filters, live_search=False, configured=False):
    evidence = [{"id": "E1", "title": "家庭口语活动用户讨论", "source_type": "公开用户讨论",
                 "region": filters["region"], "date": "2026-09-01", "url": "https://example.org/discussion",
                 "original_path": "", "credibility_level": "C", "content": "家长表示孩子理解故事，但自由表达时仍需提示。",
                 "content_kind": "search_snippet", "time_scope": "所选时间窗口内"}]
    signal = {
        "id": "s1", "signal_title": "阅读输入后的主动口语表达需求", "age_range": filters["age_range"],
        "skills": ["口语表达"], "contexts": ["家庭固定学习"], "audiences": ["家长"], "region": filters["region"],
        "trend": None, "demand_level": None, "signal_status": None,
        "trend_basis": "只有单期材料，缺少跨时间对照。", "problem_summary": "已有阅读输入的孩子可能缺少自主表达机会。",
        "existing_solutions": [{"mechanism": "家庭活动", "summary": "围绕熟悉故事安排短对话。", "examples": []}],
        "attempted_solutions": [{"description": "用户提及分级阅读。", "evidence_ids": ["E1"]}],
        "dissatisfaction": [{"description": "自由表达仍依赖成人提示。", "evidence_ids": ["E1"]}],
        "unmet_need": "需要可逐步减少提示的练习机制。", "opportunity_hypothesis": "短任务可能降低家庭练习负担，需验证。",
        "analyst": {"evidence": [{"statement": "讨论中提及成人提示。", "evidence_ids": ["E1"]}],
                    "interpretation": "可能存在输入向输出迁移的练习缺口。", "hypothesis": "减少提示的短任务可能有帮助。"},
        "evidence_ids": ["E1"], "evidence_sources": evidence,
        "china_observation": "讨论描述的是具体家庭的体验。" if filters["region"] == "中国大陆" else "",
        "overseas_observation": "海外机制需要进一步检验本地适配性。" if filters["region"] != "中国大陆" else "",
    }
    status = "success" if live_search and configured else ("local_only" if configured else "not_configured")
    return {"kind": "market_research", "filters": deepcopy(filters), "region": filters["region"], "time_window": filters["time_window"],
            "signals": [signal], "evidence_sources": evidence, "generated_at": "2026-09-13T18:01:00+08:00",
            "search_meta": {"status": status, "searched_at": "2026-09-13T18:00:00+08:00" if status == "success" else None,
                            "queries": ["儿童 英语 家庭 口语"], "failures": []},
            "analysis_meta": {"mode": "local_evidence", "provider": "rules"}, "chat": {}}


class MarketUIHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="engeduscope-market-ui-")
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(Path(temporary.name) / "market.db")})
        env.start()
        self.addCleanup(env.stop)
        self.configured = False
        search = patch("web_search.provider.load_config", side_effect=lambda: types.SimpleNamespace(configured=self.configured))
        search.start()
        self.addCleanup(search.stop)
        self.analyze = Mock(side_effect=lambda filters, live_search=False: research_fixture(filters, live_search, self.configured))
        self.followup = Mock(return_value={
            "evidence": [{"statement": "原始讨论只支持个案描述。", "evidence_ids": ["E1"]}],
            "interpretation": "现有信息不能代表整体家庭。", "hypothesis": "需要访谈更多不同背景的家庭。",
            "limitations": "只有一条资料。", "mode": "local_evidence",
        })
        analysis = types.ModuleType("market_analysis")
        analysis.analyze_market = self.analyze
        analysis.follow_up = self.followup
        mocked_module = patch.dict(sys.modules, {"market_analysis": analysis})
        mocked_module.start()
        self.addCleanup(mocked_module.stop)
        self.app = AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=20).run()
        self.app.switch_page("03_explore_market.py").run()
        self.assertEqual(len(self.app.exception), 0)

    def test_manual_local_update_and_changed_market(self):
        app = self.app
        self.assertFalse(self.analyze.called)
        self.assertNotIn("已更新至", visible(app))
        self.assertIn("联网搜索未配置", visible(app))
        app.multiselect(key="em_skills").select("口语表达").run()
        self.assertFalse(self.analyze.called)
        app.button(key="em_analyze").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertFalse(self.analyze.call_args.kwargs["live_search"])
        self.assertIn("**趋势** 证据不足", visible(app))
        self.assertNotIn("Demo Data", visible(app))
        self.assertNotIn("已更新至", visible(app))
        app.button(key="em_update").click().run()
        self.assertTrue(self.analyze.call_args.kwargs["live_search"])
        self.assertNotIn("已更新至", visible(app))
        calls = self.analyze.call_count
        app.radio(key="em_region").set_value("海外 Benchmark").run()
        self.assertEqual(self.analyze.call_count, calls)
        self.assertIn("观察维度已改变", visible(app))
        self.assertIn("本次结果：中国大陆", visible(app))
        app.button(key="em_analyze").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("本次结果：海外 Benchmark", visible(app))
        self.assertNotIn("观察维度已改变", visible(app))

    def test_search_chat_history_restore_and_build_context(self):
        app = self.app
        self.configured = True
        app.selectbox(key="em_age_start_y").set_value(6)
        app.selectbox(key="em_age_end_y").set_value(8)
        app.button(key="em_update").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("已更新至 2026年09月13日 18:00", visible(app))
        for text in ("证据陈述", "分析解释", "待验证假设", "家庭口语活动用户讨论", "公开用户讨论", "来源等级 C", "搜索摘要"):
            self.assertIn(text, visible(app))
        app.text_input(key="em_question_s1").set_value("哪些仍只是推测？")
        app.button(key="em_ask_s1").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.followup.call_args.args[0]["id"], "s1")
        self.assertEqual(self.followup.call_args.args[1][0]["id"], "E1")
        self.assertEqual(self.followup.call_args.kwargs["chat"], [])
        app.button(key="em_save").click().run()
        saved_row = list_research_sessions()[0]
        saved = json.loads(saved_row["summary_json"])
        self.assertEqual(saved["chat"]["s1"][0]["question"], "哪些仍只是推测？")
        self.assertEqual(saved_row["status"], "market")
        app.switch_page("04_history.py").run()
        app.button(key=f"hist_view_{saved_row['id']}").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("哪些仍只是推测", visible(app))
        self.assertNotIn("M1 旧版输入记录", visible(app))
        calls = self.analyze.call_count
        app.button(key=f"hist_resume_{saved_row['id']}").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.analyze.call_count, calls)
        self.assertEqual(app.session_state["em_result"], saved)
        self.assertEqual(app.selectbox(key="em_age_start_y").value, 6)
        self.assertEqual(app.selectbox(key="em_age_end_y").value, 8)
        app.switch_page("03_explore_market.py").run()
        app.button(key="em_build_s1").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(list_research_sessions()), 2)
        built = json.loads(list_research_sessions()[0]["summary_json"])
        self.assertEqual(built["opportunity_context"]["signal_id"], "s1")
        self.assertEqual(built["opportunity_context"]["chat"], saved["chat"]["s1"])
        self.assertIn("M5", visible(app))

    def test_failure_and_invalid_age_keep_previous_research(self):
        app = self.app
        app.button(key="em_analyze").click().run()
        original = deepcopy(app.session_state["em_result"])
        self.analyze.side_effect = RuntimeError("private provider response must not be exposed")
        app.button(key="em_update").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["em_result"], original)
        self.assertIn("本次市场分析暂时无法完成", visible(app))
        self.assertNotIn("private provider response", visible(app))
        self.followup.side_effect = RuntimeError("private answer must not be exposed")
        app.text_input(key="em_question_s1").set_value("还有什么不足？")
        app.button(key="em_ask_s1").click().run()
        self.assertEqual(app.session_state["em_result"], original)
        self.assertIn("本次追问暂时无法完成", visible(app))
        calls = self.analyze.call_count
        app.selectbox(key="em_age_start_y").set_value(12)
        app.selectbox(key="em_age_end_y").set_value(8)
        app.button(key="em_update").click().run()
        self.assertEqual(self.analyze.call_count, calls)
        self.assertIn("结束年龄早于起始年龄", visible(app))


if __name__ == "__main__":
    unittest.main()
