"""Build-only targeted product judgment checks; no retrieval, API or user-data writes."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from solution_baseline import baseline_solution, revise_baseline
from solution_schemas import validate_solution
from taxonomy import SKILLS_PROFESSIONAL


def brief(need="6–8岁孩子主要用单词/短语回答，希望提升完整句表达。"):
    return {"source_type": "scratch", "target_user": "儿童及其家长", "age_range": [72, 107],
            "skills": ["口语表达"], "contexts": ["家庭固定学习"], "region": "中国大陆",
            "core_need": need, "gap": "表达迁移是否缺少支持仍是机会假设", "existing_landscape": [],
            "evidence_sources": [], "preferred_carriers": ["混合 OMO"], "constraints": [], "source_context": {}}


class BuildJudgmentBaselineChecks(unittest.TestCase):
    def test_a_phrase_to_sentence_verifies_one_interaction_without_omo(self):
        source = brief()
        data = validate_solution(baseline_solution(source), [], source)
        self.assertIn(data["solution_scope"], ("activity", "prompt_tool", "lightweight_app"))
        self.assertNotIn("混合 OMO", data["carrier"]["choices"])
        self.assertIn("不建议立即开发独立产品", data["product_judgment"]["recommendation"])
        self.assertEqual(data["solution_landscape"], [])
        self.assertEqual(data["opportunity_gap"]["status"], "hypothesis")
        self.assertIn("句子组织", str(data["opportunity"]["unknowns"]))
        self.assertIn("提示依赖", str(data["opportunity"]["unknowns"]))
        self.assertIn("开放问题", data["core_interaction"])
        self.assertIn("同难度", data["core_interaction"])
        self.assertIn("关键词提示", str(data["solution_mechanism"]["steps"]))
        self.assertLessEqual(len(data["mvp"]["core_features"]), 3)
        self.assertEqual(len(data["mvp"]["key_pages"]), 1)
        self.assertEqual(len(data["risks"]), 3)
        self.assertEqual(set(data["validation_decision"]), {"continue", "adjust", "stop"})

    def test_b_service_is_a_real_service_not_an_app_with_a_new_name(self):
        source = brief("孩子开口时非常紧张，需要真人教师现场观察、情绪支持和即时追问，先验证真人服务。")
        data = validate_solution(baseline_solution(source), [], source)
        self.assertEqual(data["solution_scope"], "service")
        self.assertTrue(all("教师" in carrier for carrier in data["carrier"]["choices"]))
        self.assertIn("教师", data["core_interaction"])
        self.assertIn("教师观察单", data["mvp"]["key_pages"][0]["name"])
        self.assertIn("不需要 AI", data["mvp"]["minimal_ai_capability"][0])
        self.assertIn("无需开发软件", data["fast_prototype"]["approach"])
        self.assertIn("不取代真人判断", data["fast_prototype"]["copyable_prompt"])
        # Sentence-expression wording must not replace the human core interaction.
        source["core_need"] += "还希望从短语回答走向完整句。"
        self.assertIn("教师", baseline_solution(source)["core_interaction"])

    def test_c_activity_has_no_software_or_ai_dependency(self):
        source = brief("一次图片问答教学活动，让孩子换图后试着独立说一句，不开发软件。")
        data = validate_solution(baseline_solution(source), [], source)
        self.assertEqual(data["solution_scope"], "activity")
        self.assertEqual(data["carrier"]["choices"], ["纸质书", "家长陪伴"])
        self.assertIn("不建议立即开发独立产品", data["product_judgment"]["recommendation"])
        self.assertIn("不需要软件页面", data["mvp"]["key_pages"][0]["purpose"])
        self.assertIn("不需要 AI", data["demo_build_path"][2]["action"])

    def test_d_market_supply_does_not_become_observed_gap_or_teacher_support(self):
        source = brief()
        source.update(source_type="market_insight", skills=["阅读理解"], core_need="阅读能力能否迁移仍是待验证假设")
        source["evidence_sources"] = [{"id": "E1", "source_type": "产品 / 机构官网", "content": "本产品提供英语分级阅读材料，按难度安排阅读练习。"}]
        source["existing_landscape"] = [{"mechanism": "真人教师", "evidence_ids": ["E1"]}]
        original = deepcopy(source)
        data = validate_solution(baseline_solution(source), source["evidence_sources"], source)
        self.assertEqual(source, original)
        self.assertEqual([row["mechanism"] for row in data["solution_landscape"]], ["分级阅读"])
        self.assertEqual(data["solution_landscape"][0]["evidence_ids"], ["E1"])
        self.assertEqual(data["opportunity_gap"]["status"], "hypothesis")
        self.assertIn("不足", data["opportunity_gap"]["remaining_friction"])

    def test_negative_teacher_request_does_not_select_service(self):
        data = baseline_solution(brief("不要真人教师即时反馈，希望自己用熟悉图片练完整句表达。"))
        self.assertNotEqual(data["solution_scope"], "service")

    def test_profiles_stay_age_skill_specific(self):
        for skill in SKILLS_PROFESSIONAL:
            source = brief("希望用一个小任务验证学习支持")
            source["skills"] = [skill]
            data = validate_solution(baseline_solution(source), [], source)
            self.assertIn(skill, data["product_concept"]["value_proposition"])
        source.update(skills=["阅读理解"], age_range=[108, 155], core_need="文章变长，难以理解段落关系")
        data = baseline_solution(source)
        self.assertIn("段落", data["teaching_goal"]["learning_outcome"])
        self.assertIn("两至三段", data["product_concept"]["core_mechanism"])

    def test_revision_keeps_name_evidence_and_scope_mechanism_consistent(self):
        source = brief()
        record = {"opportunity_brief": source, "solution": baseline_solution(source)}
        record["solution"]["product_concept"]["name"] = "保留人工名称"
        source["constraints"] = ["第一版只用 Web App，不使用硬件，减少家长参与"]
        source["age_range"] = [120, 155]
        revised = revise_baseline(record, "第一版只用 Web App，不使用硬件，改成10–12岁，减少家长参与")
        data = validate_solution(revised, [], source)
        self.assertEqual(data["product_concept"]["name"], "保留人工名称")
        self.assertEqual(data["solution_scope"], "lightweight_app")
        self.assertEqual(data["carrier"]["choices"], ["App / 网页"])
        self.assertEqual(len(data["mvp"]["key_pages"]), 1)
        self.assertIn("Web App", data["fast_prototype"]["approach"])
        self.assertIn("首次", data["human_role"][0])
        self.assertIn("10岁0个月–12岁11个月", data["fast_prototype"]["copyable_prompt"])
        self.assertEqual(data["evidence_ids"], [])
        old = deepcopy(record)
        for key in ("solution_scope", "product_judgment", "opportunity", "core_interaction", "validation_decision"):
            old["solution"].pop(key)
        old["solution"]["carrier"] = {"choices": ["混合 OMO"], "rationale": "旧版本跟随上游偏好"}
        restored_revision = validate_solution(revise_baseline(old, "更适合中国家庭"), [], source)
        self.assertIn("solution_scope", restored_revision)
        self.assertEqual(restored_revision["carrier"]["choices"], ["App / 网页"])
        self.assertEqual(len(restored_revision["mvp"]["key_pages"]), 1)
        self.assertEqual(len(restored_revision["risks"]), 3)


if __name__ == "__main__":
    unittest.main()
