"""Targeted intent-aware Solve checks, using fixtures and no real API credentials."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))
from llm.provider import LLMConfig
from need_analysis import analyze_parent, analyze_student, apply_analysis
from need_evidence import rank_evidence, supplement_search
from need_intent import content_role_strategy, infer_need_intent, live_queries
from web_search.settings import SearchConfig


def need(user, years, problem, skills=None):
    return {"user_type": user, "entry_type": "student_specific" if user == "student" else "parent_specific",
            "problem": problem, "skills": skills or [], "contexts": ["自主学习"],
            "age": {"mode": "exact", "years": years, "months": 0, "age_months": years * 12, "display": f"{years}岁0个月"}}


CASES = [
    ("A", need("parent", 4, "4岁，零基础，不知道怎么开始英语启蒙。"), "getting_started", "learning_path"),
    ("B", need("student", 12, "我12岁，英语听力总是听不懂，每天应该怎么练？", ["听力"]), "skill_practice", "practice_guide"),
    ("C", need("parent", 7, "7岁，分级阅读不错，但几乎不开口。"), "diagnose_bottleneck", "learning_path"),
    ("D", need("parent", 5, "5岁英语启蒙适合买什么类型产品？"), "product_choice", "product_info"),
]


def sources():
    roles = ["policy_background", "policy_background", "product_info", "parent_experience", "research_evidence", "practice_guide", "learning_path"]
    return [{"id": f"E{i}", "document_id": f"doc{i}", "chunk_id": f"chunk{i}", "title": f"英语参考{i}",
             "text": "听力理解 口语表达 英语 每天十分钟，先听再复述；官方材料 https://www.britishcouncil.org/。\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com",
             "source_url": "https://www.britishcouncil.org/", "content_role": role, "region": "中国大陆",
             "source_type": "产品资料" if role == "product_info" else "通用学习路径参考资料"}
            for i, role in enumerate(roles, 1)]


class NeedQualityChecks(unittest.TestCase):
    def setUp(self):
        for item in (patch("llm.provider.load_config", return_value=LLMConfig(provider="mock")),
                     patch("need_analysis.load_config", return_value=LLMConfig(provider="mock")),
                     patch("need_evidence.load_search_config", return_value=SearchConfig()),
                     patch("requests.sessions.Session.request", side_effect=AssertionError("No real network in checks"))):
            item.start()
            self.addCleanup(item.stop)

    def test_four_requested_cases_have_matching_evidence_and_executable_plans(self):
        for label, result, intent, first_role in CASES:
            with self.subTest(case=label), patch("need_analysis.retrieve_evidence", return_value=sources()):
                output = (analyze_student if result["user_type"] == "student" else analyze_parent)(result)
                self.assertEqual(output["need_intent"]["primary_intent"], intent)
                evidence = output["evidence_sources"]
                self.assertEqual(evidence[0]["content_role"], first_role)
                self.assertLessEqual(sum(e["content_role"] == "policy_background" for e in evidence), 1)
                plan = output.get("student_practice_plan") or output["parent_action_plan"]
                self.assertTrue(plan["today"]["steps"])
                self.assertIn("分钟", plan["today"]["duration"])
                self.assertTrue(plan["week_plan"])
                self.assertTrue(plan["progress_signals"])
                self.assertTrue(plan["increase_difficulty_when"])
                self.assertLessEqual(len(plan["priorities"]), 2)
                if label == "A":
                    self.assertEqual(len(plan["stages"]), 2)
                    self.assertTrue(all(stage["advance_when"] and stage["materials"] for stage in plan["stages"]))
                if label == "B":
                    self.assertNotIn("solution_routes", output)
                    self.assertNotIn("购买", json.dumps(plan, ensure_ascii=False))
                serialized = json.dumps(apply_analysis(result, output), ensure_ascii=False)
                for private in ("abc_teacher123", "13812345678", "teacher@example.com"):
                    self.assertNotIn(private, serialized)
                self.assertIn("https://www.britishcouncil.org/", serialized)

    def test_intent_handles_beginner_daily_plan_and_explicit_refusal_to_shop(self):
        first = infer_need_intent(need("parent", 4, "孩子4岁，英语零基础，不知道怎么启蒙，也想知道每天怎么安排。"))
        self.assertEqual(first["primary_intent"], "getting_started")
        second = infer_need_intent(need("student", 12, "单词总记不住，不想买课程，只想知道每天怎么练。"))
        self.assertEqual(second["primary_intent"], "skill_practice")
        self.assertNotIn("product_choice", second["secondary_intents"])
        self.assertEqual(infer_need_intent(need("parent", 8, "什么时候需要找老师帮助？"))["primary_intent"], "teacher_support")
        self.assertEqual(infer_need_intent(need("parent", 8, "怎么判断英语有没有进步？"))["primary_intent"], "progress_check")

    def test_search_only_when_eligible_and_needed_with_safe_fallback(self):
        mapping = {"primary_skills": ["听力理解"]}
        cfg = SearchConfig(api_key="test-placeholder")
        starter = CASES[0][1]
        intent = infer_need_intent(starter)
        with patch("need_evidence.search_web") as web:
            unchanged, meta = supplement_search(starter, mapping, intent, [])
            self.assertEqual(meta["status"], "not_configured")
            web.assert_not_called()
        with patch("need_evidence.load_search_config", return_value=cfg), patch("need_evidence.search_web") as web:
            supplement_search(starter, mapping, intent, sources())
            web.assert_not_called()
            web.return_value = {"status": "partial", "searched_at": "2026-09-13T12:00:00+00:00",
                                "failures": [{"stage": "fetch", "reason": "403，已跳过", "url": "https://example.org/"}],
                                "results": [{"title": "英语学习具体步骤", "url": "https://www.britishcouncil.org/",
                                             "content": "第一步听英语，第二步再回答。\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com",
                                             "content_kind": "search_snippet"}]}
            evidence, meta = supplement_search(starter, mapping, intent, [])
            self.assertEqual(web.call_count, 1)
            self.assertEqual(meta["status"], "partial")
            self.assertEqual(evidence[0]["content_role"], "practice_guide")
            self.assertEqual(evidence[0]["content_kind"], "search_snippet")
            self.assertEqual(evidence[0]["source_url"], "https://www.britishcouncil.org/")
            for private in ("abc_teacher123", "13812345678", "teacher@example.com"):
                self.assertNotIn(private, json.dumps(evidence))
            product = CASES[3][1]
            supplement_search(product, mapping, infer_need_intent(product), sources())
            self.assertEqual(web.call_count, 2)
            diagnose = CASES[2][1]
            supplement_search(diagnose, mapping, infer_need_intent(diagnose), [])
            self.assertEqual(web.call_count, 2)
            web.side_effect = RuntimeError("private transport detail")
            _, meta = supplement_search(starter, mapping, intent, [])
            self.assertEqual(meta["status"], "failed")
            self.assertNotIn("private transport", json.dumps(meta))
            self.assertLessEqual(len(live_queries(starter, mapping, intent)), 3)

    def test_no_evidence_and_old_live_parent_schema_still_produce_starting_plan(self):
        from llm.mock import mock_complete_json
        def legacy(system, user, **kwargs):
            data = mock_complete_json(system, user)
            data.pop("practice_plan", None)
            return data
        with patch("need_analysis.retrieve_evidence", return_value=[]), patch("need_analysis.complete_json", side_effect=legacy):
            result = analyze_parent(CASES[0][1])
        self.assertTrue(result["evidence_note"])
        self.assertEqual(len(result["parent_action_plan"]["stages"]), 2)
        self.assertEqual(result["analysis_meta"]["practice_plan_mode"], "general_baseline")

    def test_educator_role_strategy_keeps_research_first(self):
        intent = {"primary_intent": "diagnose_bottleneck"}
        strategy = content_role_strategy("professional", intent)
        self.assertEqual(strategy["role_priority"][:3], ["research_evidence", "market_signal", "product_info"])
        self.assertEqual(rank_evidence(sources(), strategy, {"primary_skills": ["听力理解"]})[0]["content_role"], "research_evidence")


if __name__ == "__main__":
    unittest.main()
