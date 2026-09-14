"""Bounded Solve-only evidence checks. No database writes or real web calls."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from need_evidence import evidence_sufficient, rank_evidence, supplement_search
from need_intent import content_role_strategy, infer_need_intent
from web_search.settings import SearchConfig


def source(name, role, text="英语听力练习：先听一遍，再根据关键词复述；每天十分钟。", **extra):
    return dict({"document_id": name, "chunk_id": name, "title": name,
                 "content_role": role, "text": text}, **extra)


def intent(primary):
    return {"primary_intent": primary, "secondary_intents": []}


class SolveDeepEvidenceChecks(unittest.TestCase):
    def test_learner_filters_noise_and_incidental_skill_mentions(self):
        items = [source("听力入门", "practice_guide"),
                 source("听力学习路径", "learning_path"),
                 source("数学平台", "research_evidence", "数学平台提供数学题训练与代数讲解，也涉及听力。"),
                 source("作文自动评阅", "research_evidence", "作文评分与写作评估用于作文批改，另含听力。"),
                 source("听力研究标题", "research_evidence", "主要讲企业融资情况以及科技公司年度收入变化。"),
                 source("噪声", "practice_guide", "听力练习\n" + "�#|" * 40)]
        ranked = rank_evidence(items, content_role_strategy("student", intent("skill_practice")),
                               {"primary_skills": ["听力理解"]})
        self.assertEqual([item["document_id"] for item in ranked], ["听力入门", "听力学习路径"])

    def test_role_limits_and_product_priority_do_not_claim_effect(self):
        items = [source("政策", "policy_background"), source("研究", "research_evidence"),
                 source("个案", "parent_experience"),
                 source("官网", "product_info", source_url="https://www.britishcouncil.org/")]
        strategy = content_role_strategy("parent", intent("product_choice"))
        ranked = rank_evidence(items, strategy, {"primary_skills": ["听力理解"]})
        self.assertEqual(ranked[0]["document_id"], "官网")
        by_role = {item["content_role"]: item for item in ranked}
        self.assertIn("不能单独证明学习效果", by_role["product_info"]["scope_note"])
        self.assertIn("个别", by_role["parent_experience"]["scope_note"])
        self.assertIn("可能的学习机制", by_role["research_evidence"]["scope_note"])
        reranked = rank_evidence(ranked, strategy, {"primary_skills": ["听力理解"]})
        self.assertEqual(reranked[0]["scope_note"].count("不能单独证明学习效果"), 1)

    def test_practice_shortage_needs_actionable_material_not_two_studies(self):
        research = [source("研究甲", "research_evidence"), source("研究乙", "research_evidence")]
        self.assertFalse(evidence_sufficient(research, intent("getting_started")))
        self.assertFalse(evidence_sufficient(research, intent("skill_practice")))
        self.assertTrue(evidence_sufficient(research, intent("diagnose_bottleneck")))
        self.assertTrue(evidence_sufficient(research, intent("getting_started"), user_type="professional"))
        conceptual = [source("路径", "learning_path", "英语能力发展应遵循语言发展的整体学习路径。"), research[0]]
        self.assertFalse(evidence_sufficient(conceptual, intent("getting_started")))
        useful = [source("步骤", "practice_guide"), research[0]]
        self.assertTrue(evidence_sufficient(useful, intent("getting_started")))
        only_reviews = [source("个案甲", "parent_experience"), source("个案乙", "parent_experience")]
        self.assertFalse(evidence_sufficient(only_reviews, intent("product_choice")))

    def test_professional_rerank_matches_unchanged_golden_output(self):
        expected_roles = ["research_evidence", "market_signal", "product_info", "learning_path",
                          "parent_experience", "practice_guide", "general_reference", "policy_background"]
        items = [source(role, role) for role in reversed(expected_roles)]
        ranked = rank_evidence(items, content_role_strategy("professional", intent("getting_started")),
                               {"primary_skills": ["听力理解"]})
        # The previous algorithm returned these exact objects in this order,
        # adding only sequential citation identifiers, with no new scope notes.
        self.assertEqual(ranked, [dict(source(role, role), id=f"E{index}")
                                  for index, role in enumerate(expected_roles, 1)])

    def test_config_failures_and_search_failures_preserve_local_answer(self):
        local = [source("已有资料", "research_evidence")]
        result = {"user_type": "parent", "problem": "4岁零基础，不知道怎么开始英语启蒙", "age": {"years": 4}}
        with patch("need_evidence.load_search_config", side_effect=OSError("private detail")), patch("need_evidence.search_web") as web:
            evidence, meta = supplement_search(result, {}, intent("getting_started"), local)
            self.assertEqual(evidence, local)
            self.assertEqual(meta["status"], "not_configured")
            self.assertNotIn("private detail", json.dumps(meta))
            web.assert_not_called()
        with patch("need_evidence.load_search_config", return_value=SearchConfig(api_key="fixture-only")), patch("need_evidence.search_web", side_effect=RuntimeError("private detail")):
            evidence, meta = supplement_search(result, {}, intent("getting_started"), local)
            self.assertEqual(evidence, local)
            self.assertEqual(meta["status"], "failed")
            self.assertTrue(meta["requested"])
            self.assertNotIn("private detail", json.dumps(meta))

    def test_search_runs_only_on_practice_shortage_or_current_product_service(self):
        result = {"user_type": "parent", "problem": "什么时候需要找老师帮助？", "age": {"years": 7}}
        sufficient = [source("方法", "practice_guide"), source("研究", "research_evidence")]
        outcome = {"status": "success", "searched_at": "2026-09-13", "failures": [], "results": [
            {"title": "英语听力练习具体步骤", "url": "https://www.britishcouncil.org/",
             "content": "第一步听英语，第二步再回答。每天练习十分钟。\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com"}]}
        with patch("need_evidence.load_search_config", return_value=SearchConfig(api_key="fixture-only")), patch("need_evidence.search_web", return_value=outcome) as web:
            supplement_search(result, {}, intent("teacher_support"), sufficient)
            web.assert_not_called()
            supplement_search(result, {}, intent("getting_started"), sufficient)
            web.assert_not_called()
            evidence, meta = supplement_search(result, {}, intent("getting_started"), [])
            self.assertEqual(web.call_count, 1)
            self.assertLessEqual(len(web.call_args.args[0]), 3)
            self.assertEqual(evidence[0]["content_role"], "practice_guide")
            self.assertIn("https://www.britishcouncil.org/", json.dumps(evidence))
            for private in ("abc_teacher123", "13812345678", "teacher@example.com"):
                self.assertNotIn(private, json.dumps(evidence))
            supplement_search(result, {}, intent("product_choice"), sufficient)
            self.assertEqual(web.call_count, 2)
            service = dict(result, problem="需要找什么类型的老师？最近有哪些官方机构提供这种服务？")
            supplement_search(service, {}, intent("teacher_support"), sufficient)
            self.assertEqual(web.call_count, 3)
            self.assertNotIn("start_date", web.call_args.args[1])

    def test_accepted_four_intents_still_hold(self):
        cases = [("parent", "孩子4岁，零基础，不知道英语启蒙怎么开始。", "getting_started"),
                 ("parent", "7岁，分级阅读读得不错，但是几乎不开口。", "diagnose_bottleneck"),
                 ("student", "我12岁，英语听力总是听不懂，每天应该怎么练？", "skill_practice"),
                 ("parent", "5岁英语启蒙应该选什么类型的产品？", "product_choice")]
        for user_type, problem, expected in cases:
            with self.subTest(problem=problem):
                self.assertEqual(infer_need_intent({"user_type": user_type, "problem": problem})["primary_intent"], expected)


if __name__ == "__main__":
    unittest.main()
