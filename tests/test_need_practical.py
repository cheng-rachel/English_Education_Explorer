"""Targeted practice quality: beginner parent, skills, shared provider and safety."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from llm.mock import mock_complete_json
from llm.prompts import (SYSTEM_EDUCATOR, SYSTEM_PARENT, SYSTEM_STUDENT, build_educator_prompt,
                         build_parent_prompt, build_student_prompt)
from llm.provider import LLMSchemaError
from llm.schemas import validate_educator, validate_parent, validate_student
from need_practice import practical_plan, validate_practice_plan
from output_safety import CONTACT_POLICY
from taxonomy import SKILLS_PROFESSIONAL


class PracticalPlanChecks(unittest.TestCase):
    def test_four_year_old_beginner_has_timing_materials_daily_language_and_stages(self):
        inputs = {"age": "4岁0个月", "age_months": 48, "description": "孩子4岁，英语零基础，不知道怎么开始。",
                  "need_intent": {"primary_intent": "getting_started", "secondary_intents": []}}
        mapping = {"primary_skills": ["听力理解", "口语表达"], "contexts": ["亲子共学"]}
        prompt = build_parent_prompt(inputs, mapping, [])
        with patch.dict("os.environ", {"ENGEDUSCOPE_LLM_MOCK_MODE": "ok"}):
            result = validate_parent(mock_complete_json(SYSTEM_PARENT, prompt), [])
        plan = result["practice_plan"]
        self.assertIn("5–8分钟", plan["today"]["duration"])
        self.assertEqual(len(plan["stages"]), 2)
        self.assertIn("2–4周", plan["stages"][0]["period"])
        self.assertIn("4–8周", plan["stages"][1]["period"])
        for stage in plan["stages"]:
            self.assertTrue(stage["materials"])
            self.assertTrue(stage["advance_when"])
            self.assertIn("分钟", stage["duration"])
        text = json.dumps(plan, ensure_ascii=False)
        self.assertIn("Open the book.", text)
        self.assertIn("Wash your hands.", text)
        self.assertIn("不按日历硬推进", text)
        self.assertNotIn("政策", text)
        self.assertEqual(result["evidence_ids"], [])

    def test_student_skills_get_different_tasks_and_transfer_checks(self):
        inputs = {"age": "12岁0个月", "age_months": 144, "contexts": ["自主学习"]}
        expected = {"听力理解": "先听一遍", "口语表达": "Where did you play?", "阅读理解": "一句原文",
                    "写作表达": "初稿", "词汇量扩展": "遮住词", "语法知识": "She plays.",
                    "自然拼读": "逐音", "单词拼写": "盖住原词", "听力解码": "不看文字", "跨学科素养": "叶子"}
        bottlenecks = set()
        for skill in SKILLS_PROFESSIONAL:
            with self.subTest(skill=skill):
                prompt = build_student_prompt(dict(inputs, skills=[skill]), {"primary_skills": [skill]}, [],
                                              {"primary_intent": "skill_practice", "secondary_intents": []})
                result = validate_student(mock_complete_json(SYSTEM_STUDENT, prompt), [])
                plan = result["practice_plan"]
                bottlenecks.add(plan["bottleneck"])
                text = json.dumps(plan, ensure_ascii=False)
                self.assertIn(expected[skill], text)
                self.assertIn("分钟", plan["today"]["duration"])
                self.assertEqual(len(plan["week_plan"]), 3)
                self.assertTrue(plan["progress_signals"])
                self.assertTrue(plan["increase_difficulty_when"])
                self.assertEqual(result["primary_skills"], [skill])
                self.assertEqual(plan["stages"], [])
                self.assertNotIn("购买", text)
                self.assertNotIn("solution_routes", result)
        self.assertEqual(len(bottlenecks), len(SKILLS_PROFESSIONAL))

    def test_parent_intents_keep_practice_primary_and_preserve_old_schema(self):
        inputs = {"age_months": 96, "description": "英语读完很快就忘了", "contexts": ["家庭固定学习"]}
        mapping = {"primary_skills": ["阅读理解"]}
        results = {}
        for intent in ("diagnose_bottleneck", "skill_practice", "product_choice", "teacher_support", "progress_check"):
            plan = practical_plan(inputs, mapping, {"primary_intent": intent})
            results[intent] = plan["priorities"]
            self.assertIn("Who is the story about?", json.dumps(plan, ensure_ascii=False))
        self.assertIn("同难度的新任务", results["progress_check"][0])
        self.assertIn("卡住的那一步", results["diagnose_bottleneck"][0])
        self.assertIn("老师", results["teacher_support"][0])
        self.assertIn("练习与反馈", results["product_choice"][0])
        with patch.dict("os.environ", {"ENGEDUSCOPE_LLM_MOCK_MODE": "ok"}):
            old = mock_complete_json(SYSTEM_PARENT, build_parent_prompt(inputs, mapping, []))
        old.pop("practice_plan")
        checked = validate_parent(old, [])
        self.assertNotIn("practice_plan", checked)
        self.assertEqual(len(checked["solution_routes"]), 3)

    def test_contract_rejects_missing_actions_and_filters_contacts_and_fake_citations(self):
        plan = practical_plan({"age_months": 144}, {"primary_skills": ["语法知识"]}, "skill_practice", "student")
        for field in ("today", "week_plan", "teacher_support"):
            broken = deepcopy(plan)
            broken.pop(field)
            with self.assertRaises(LLMSchemaError):
                validate_practice_plan(broken)
        unsafe = deepcopy(plan)
        unsafe["teacher_support"]["profile"] = "微信：abc_teacher123；手机：13812345678；邮箱：teacher@example.com"
        result = validate_student({"practice_plan": unsafe, "primary_skills": ["语法"], "contexts": ["自学"],
                                   "evidence_ids": ["E1", "E999"]}, ["E1"])
        text = json.dumps(result, ensure_ascii=False)
        for contact in ("abc_teacher123", "13812345678", "teacher@example.com"):
            self.assertNotIn(contact, text)
        self.assertEqual(result["evidence_ids"], ["E1"])
        self.assertIn(CONTACT_POLICY, SYSTEM_STUDENT)
        self.assertIn(CONTACT_POLICY, SYSTEM_PARENT)

    def test_existing_educator_prompt_and_schema_still_work(self):
        prompt = build_educator_prompt({"age": "9–12岁", "skills": ["阅读理解"], "contexts": ["学校课程衔接"],
                                       "pain_point": "长篇阅读难以抓住主要意思"}, [])
        with patch.dict("os.environ", {"ENGEDUSCOPE_LLM_MOCK_MODE": "ok"}):
            result = validate_educator(mock_complete_json(SYSTEM_EDUCATOR, prompt), [])
        self.assertEqual(result["user_need"]["core_skills"], ["阅读理解"])
        self.assertIn("mvp_spec", result)
        self.assertNotIn("practice_plan", result)


if __name__ == "__main__":
    unittest.main()
