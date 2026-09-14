"""Only Analyst wording and presentation; synthetic sources, no external requests."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))

from streamlit.testing.v1 import AppTest
from market_analyst_evidence import analyst_findings, source_finding
from market_baseline import baseline_answer, baseline_market
from market_schemas import safe_signal_for_display, validate_answer, validate_market

FILTERS = {"region": "中国大陆", "age_range": [84, 191], "skills": ["阅读理解"], "contexts": [], "audiences": []}


def source(content, number=1, kind="产品 / 机构官网"):
    return {"id": f"E{number}", "title": "英语阅读工具使用说明", "content": content,
            "source_type": kind, "region": "中国大陆", "url": f"https://example.org/{number}",
            "date": "2026-09-14", "time_scope": "within_window"}


def answer():
    return {"evidence": [{"statement": "提供产品功能参考", "evidence_ids": ["E1"]}],
            "interpretation": "任务设计可能降低操作负担，仍需观察。", "hypothesis": "用一篇新短文检验是否能独立回答。"}


class AnalystWordingTests(unittest.TestCase):
    def render(self, data, sources):
        app = AppTest.from_string(
            "import sys\n" + f"sys.path.insert(0, {str(ROOT / '03app')!r})\n" +
            "import streamlit as st\nfrom market_session import render_analyst\n"
            "render_analyst(st.session_state['answer'], evidence=st.session_state['sources'], "
            "already_shown=[st.session_state['answer']['hypothesis']])")
        app.session_state["answer"] = deepcopy(data)
        app.session_state["sources"] = deepcopy(sources)
        with patch("requests.get", side_effect=AssertionError("no fetch")), patch("requests.post", side_effect=AssertionError("no API")):
            app.run()
        self.assertFalse(app.exception)
        return app, "\n".join(item.value for kind in ("markdown", "caption") for item in app.get(kind))

    def test_product_finding_is_specific_and_type_boundary_is_separate(self):
        text = "本工具按阅读难度提供分级短文，读完后要求学生回答人物行动与原因的问题。"
        evidence = [source(text)]
        result = analyst_findings(answer()["evidence"], evidence)
        self.assertIn(text, result[0]["statement"])
        self.assertNotIn("不证明", result[0]["statement"])
        self.assertIn("不证明学习效果", result[0]["boundary"])
        app, visible = self.render(answer(), evidence)
        self.assertIn("英语阅读工具使用说明 · 产品 / 机构官网", visible)
        self.assertIn("证据边界", visible)
        self.assertNotIn("E1", visible)
        self.assertNotIn("提供产品功能参考", visible)
        for layer in ("Evidence｜我们实际看到什么", "Interpretation｜这可能意味着什么", "Hypothesis｜接下来值得验证什么"):
            self.assertIn(layer, visible)
        self.assertIn(answer()["interpretation"], visible)
        self.assertIn(answer()["hypothesis"], visible)

    def test_live_interpretation_drops_internal_clauses_but_retains_source_boundary(self):
        sources = [source("本工具提供英语分级阅读材料，通过理解问答练习复述文章。")]
        data = answer()
        data["interpretation"] = "理解问答把阅读任务拆成具体问题，仅作为学习问题解释线索。不能证明市场缺口。"
        data["limitations"] = ["产品方的功能自述不证明学习效果。"]
        checked = validate_answer(data, sources)
        self.assertEqual(checked["interpretation"], "理解问答把阅读任务拆成具体问题。")
        self.assertEqual(checked["limitations"], data["limitations"])
        self.assertIn("不证明学习效果", checked["evidence"][0]["boundary"])

    def test_survey_result_and_user_feedback_are_actual_source_observations(self):
        report = source("本报告包含用户调查。20位受访家长中，12位报告孩子换成陌生英语短文后仍难以回答理解问题。", kind="行业报告")
        finding = source_finding(report)
        self.assertIn("20位受访家长中，12位", finding["statement"])
        self.assertNotIn("包含用户调查", finding["statement"])
        user = source("我家孩子用过分级阅读，但换成陌生短文后还是看不懂理解问题。", kind="公开用户讨论")
        finding = source_finding(user)
        self.assertIn("换成陌生短文", finding["statement"])
        self.assertIn("不能推断普遍需求", finding["boundary"])

    def test_no_concrete_content_is_allowed_without_fabricating_facts(self):
        sources = [source("本英语阅读理解报告包含用户调查，提供产品功能参考。")]
        self.assertIsNone(source_finding(sources[0]))
        checked = validate_answer(answer(), sources)
        self.assertEqual(checked["evidence"], [])
        self.assertIn("当前资料不足以确认", checked["limitations"])
        raw = baseline_market(FILTERS, sources)
        checked_market = validate_market(raw, sources, FILTERS)
        self.assertEqual(checked_market["signals"][0]["analyst"]["evidence"], [])
        _, visible = self.render(answer(), sources)
        self.assertIn("当前资料不足以确认", visible)

    def test_old_history_and_chat_gain_specific_wording_without_api_or_mutation(self):
        sources = [source("本工具提供英语分级阅读材料，通过理解问答练习复述文章。")]
        signal = baseline_market(FILTERS, sources)["signals"][0]
        signal["analyst"]["evidence"] = answer()["evidence"]
        before = deepcopy(signal)
        with patch("market_analysis.complete_json", side_effect=AssertionError("no AI")), \
             patch("market_analysis.search_web", side_effect=AssertionError("no search")):
            restored = safe_signal_for_display(signal, sources, FILTERS)
            chat = baseline_answer(restored, sources, "这个工具提供什么练习？")
        self.assertIn("理解问答", restored["analyst"]["evidence"][0]["statement"])
        self.assertIn("理解问答", chat["evidence"][0]["statement"])
        self.assertEqual(signal, before)
        self.assertEqual(restored["evidence_ids"], signal["evidence_ids"])

    def test_contacts_and_ocr_do_not_become_visible_findings(self):
        sources = [source("本工具提供英语分级阅读材料与理解问答。\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com")]
        _, visible = self.render(answer(), sources)
        for secret in ("abc_teacher123", "13812345678", "teacher@example.com"):
            self.assertNotIn(secret, visible)
        self.assertIsNone(source_finding(source("英语阅读理解 " + "�|□_" * 30)))


if __name__ == "__main__":
    unittest.main()
