"""Solve-only content checks for the four requested cases and safe compatibility."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from llm.mock import mock_complete_json
from llm.prompts import (SYSTEM_EDUCATOR, SYSTEM_PARENT, SYSTEM_STUDENT, build_educator_prompt,
                         build_parent_prompt, build_student_prompt)
from llm.schemas import validate_educator, validate_parent, validate_student


class SolveDeepContentChecks(unittest.TestCase):
    def parent(self, age, problem, intent, skills):
        inputs = {"age": f"{age}岁0个月", "age_months": age * 12, "description": problem,
                  "contexts": ["家庭固定学习"], "need_intent": {"primary_intent": intent, "secondary_intents": []}}
        with patch.dict("os.environ", {"ENGEDUSCOPE_LLM_MOCK_MODE": "ok"}):
            result = mock_complete_json(SYSTEM_PARENT, build_parent_prompt(inputs, {"primary_skills": skills}, []))
        return validate_parent(result, [])

    def test_a_beginner_steps_materials_and_behavior_conditions_without_unbacked_bans(self):
        result = self.parent(4, "孩子4岁，零基础，不知道英语启蒙怎么开始。", "getting_started", ["听力理解"])
        plan = result["practice_plan"]
        self.assertEqual(len(plan["stages"]), 2)
        self.assertTrue(all(stage["materials"] and stage["advance_when"] for stage in plan["stages"]))
        self.assertIn("分钟", plan["today"]["duration"])
        self.assertTrue(plan["increase_difficulty_when"] and plan["progress_signals"])
        self.assertIn("不按日历硬推进", json.dumps(plan, ensure_ascii=False))
        self.assertNotIn("政策", result["problem_summary"])
        self.assertNotIn("不急着背词、抄写、学语法", json.dumps(plan, ensure_ascii=False))
        self.assertEqual(result["evidence_ids"], [])  # demo mechanisms are not invented citations

    def test_b_checks_distinguish_report_hypotheses_and_conditional_actions(self):
        result = self.parent(7, "分级阅读读得不错，但是平时几乎不开口。", "diagnose_bottleneck", ["口语表达", "阅读理解"])
        reasoning = result["need_reasoning"]
        self.assertEqual(len(reasoning["hypotheses"]), 4)
        self.assertTrue(all(item["check"] and item["if_observed"].startswith("如果") for item in reasoning["hypotheses"]))
        self.assertIn("你提供的情况", reasoning["reported_facts"][0])
        self.assertTrue(reasoning["to_confirm"])
        self.assertIn("两项不同", result["problem_summary"])
        text = json.dumps(result["practice_plan"], ensure_ascii=False)
        for phrase in ("先等5秒", "词", "句子", "跟读", "生活"):
            self.assertIn(phrase, text)
        self.assertNotIn("AI口语", text)
        self.assertNotIn("外教", result["problem_summary"])
        self.assertIn("只有", result["solution_routes"][1]["why_it_fits"])

    def test_c_student_listening_has_twenty_minutes_and_independent_transfer(self):
        inputs = {"age": "12岁0个月", "age_months": 144, "description": "我英语听力总是听不懂，每天应该怎么练？",
                  "contexts": ["自主学习"]}
        intent = {"primary_intent": "skill_practice", "secondary_intents": ["diagnose_bottleneck"]}
        with patch.dict("os.environ", {"ENGEDUSCOPE_LLM_MOCK_MODE": "ok"}):
            result = validate_student(mock_complete_json(SYSTEM_STUDENT, build_student_prompt(
                inputs, {"primary_skills": ["听力理解"]}, [], intent)), [])
        plan = result["practice_plan"]
        self.assertIn("20分钟", plan["today"]["duration"])
        self.assertEqual(len(plan["today"]["steps"]), 5)
        self.assertEqual(sum(int(step.split("分钟")[0]) for step in plan["today"]["steps"]), 20)
        self.assertEqual(len(plan["week_plan"]), 3)
        self.assertIn("新音频", "".join(plan["progress_signals"]))
        self.assertIn("二选一", "".join(plan["increase_difficulty_when"]))
        text = json.dumps(plan, ensure_ascii=False)
        for phrase in ("家长监督", "家长陪伴", "买课", "购买"):
            self.assertNotIn(phrase, text)

    def test_d_product_types_explain_fit_and_require_trial_without_claiming_effect(self):
        result = self.parent(5, "5岁英语启蒙应该选什么类型的产品？", "product_choice", ["听力理解"])
        self.assertEqual(len(result["solution_routes"]), 3)
        self.assertTrue(all(route["why_it_fits"] and route["limitations"] for route in result["solution_routes"]))
        self.assertIn("官网可以核对功能", result["problem_summary"])
        self.assertIn("不代表已证明有效", result["solution_routes"][1]["why_it_fits"])
        self.assertIn("不需要先购买", result["practice_plan"]["today"]["duration"])
        text = json.dumps(result, ensure_ascii=False)
        for phrase in ("TOP 1", "第一名", "保证提高", "必然提升"):
            self.assertNotIn(phrase, text)

    def test_new_reasoning_is_sanitized_and_old_results_remain_valid(self):
        result = self.parent(7, "阅读不错但不开口", "diagnose_bottleneck", ["口语表达"])
        result["need_reasoning"]["hypotheses"][0]["check"] += " 微信：abc_teacher123；手机：13812345678；邮箱：teacher@example.com"
        checked = validate_parent(result, [])
        for value in ("abc_teacher123", "13812345678", "teacher@example.com"):
            self.assertNotIn(value, json.dumps(checked, ensure_ascii=False))
        result.pop("need_reasoning")
        result.pop("practice_plan")
        legacy = validate_parent(result, [])
        self.assertNotIn("need_reasoning", legacy)
        self.assertEqual(len(legacy["solution_routes"]), 3)

    def test_educator_retains_product_and_validation_contract(self):
        inputs = {"age": "9–12岁", "skills": ["阅读理解"], "contexts": ["学校课程衔接"],
                  "pain_point": "长篇阅读难以抓住主要意思"}
        with patch.dict("os.environ", {"ENGEDUSCOPE_LLM_MOCK_MODE": "ok"}):
            result = validate_educator(mock_complete_json(SYSTEM_EDUCATOR, build_educator_prompt(inputs, [])), [])
        self.assertEqual(set(result), {"user_need", "teaching_goal", "solution_landscape", "gap", "product_direction",
                                       "mvp_spec", "validation_metrics", "evidence_ids"})
        self.assertEqual(set(result["validation_metrics"]), {"learning", "behavior", "product"})


if __name__ == "__main__":
    unittest.main()
