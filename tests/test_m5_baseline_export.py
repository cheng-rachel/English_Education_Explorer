"""M5 deterministic proposed concepts and non-destructive Markdown export."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from solution_baseline import baseline_solution, revise_baseline
from solution_export import export_markdown, to_markdown
from solution_schemas import validate_solution
from taxonomy import SKILLS_PROFESSIONAL


def brief(skill="口语表达"):
    return {"source_type": "scratch", "target_user": "有输入基础的孩子及其家长", "age_range": [72, 107],
            "skills": [skill], "contexts": ["家庭固定学习"], "region": "中国大陆",
            "core_need": "已经读过熟悉材料，但在日常情境中很少独立使用英语。", "gap": "当前练习与独立使用如何衔接仍待验证。",
            "existing_landscape": [], "evidence_sources": [], "preferred_carriers": ["App / 网页"],
            "source_context": {"original_need": "应保留的原始输入"}, "constraints": []}


def record(source=None):
    source = source or brief()
    return {"kind": "product_concept", "generated_at": "2026-09-14T10:20:30+08:00", "opportunity_brief": source,
            "solution": baseline_solution(source), "analysis_meta": {"mode": "demo", "provider": "Demo", "revision_history": []}}


class BaselineExportChecks(unittest.TestCase):
    def test_all_skills_generate_valid_complete_proposed_concepts(self):
        for skill in SKILLS_PROFESSIONAL:
            with self.subTest(skill=skill):
                source = brief(skill)
                data = validate_solution(baseline_solution(source), [])
                self.assertIn(skill, data["product_concept"]["value_proposition"])
                self.assertTrue(1 <= len(data["mvp"]["core_features"]) <= 5)
                self.assertEqual([step["step"] for step in data["demo_build_path"]], [1, 2, 3, 4, 5])
                self.assertIn("输入数据", data["demo_build_path"][0]["title"])
                self.assertIn("页面", data["demo_build_path"][1]["title"])
                self.assertIn("Prompt / API", data["demo_build_path"][2]["title"])
                self.assertIn("交互", data["demo_build_path"][3]["title"])
                self.assertIn("验证", data["demo_build_path"][4]["title"])
                self.assertTrue(all(item["why_essential"] for item in data["mvp"]["core_features"]))
                self.assertIn("没有真实试验数据", data["solution_mechanism"]["assumptions"][0])
                self.assertIn("拟议", data["validation_plan"]["sample"])
                prompt = data["fast_prototype"]["copyable_prompt"]
                self.assertIn("输入材料", prompt)
                self.assertIn('"task_steps"', prompt)
                self.assertNotIn("输出完整代码", prompt)

    def test_reading_progression_age_context_and_carrier_are_meaningful(self):
        source = brief("阅读理解")
        source.update(age_range=[108, 155], contexts=["学校课程衔接"], core_need="文章变长以后，孩子很难看出段落主旨及关系。", preferred_carriers=["纸质书"])
        data = baseline_solution(source)
        self.assertIn("段落", data["teaching_goal"]["learning_outcome"])
        self.assertIn("两至三段", data["product_concept"]["core_mechanism"])
        self.assertIn("段间关系", data["validation_metrics"]["learning"]["metric"])
        self.assertIn("学校课程衔接", data["product_concept"]["core_scenario"])
        self.assertIn("纸质书", data["carrier"]["rationale"])
        hardware = brief()
        hardware["preferred_carriers"] = ["AI 玩具 / 机器人"]
        self.assertIn("模拟", baseline_solution(hardware)["carrier"]["rationale"])
        younger = brief("听力理解")
        younger["age_range"] = [36, 71]
        self.assertIn("成人带领", baseline_solution(younger)["product_concept"]["core_mechanism"])

    def test_scratch_uses_supplied_content_without_title_based_invention(self):
        source = brief()
        source["evidence_sources"] = [{"id": "E1", "title": "AI玩具世界第一品牌", "source_type": "产品 / 机构官网", "region": "中国大陆",
                                       "content": "资料提供真人老师的口语陪练活动，围绕图片提出问题。", "url": "https://fixture.invalid/teacher"}]
        source["evidence_sources"].append({"id": "E2", "title": "教育行业报告", "source_type": "行业报告", "region": "中国大陆",
                                           "content": "高等教育场景中，大学教学者设计线上课堂与课程体系。", "url": "https://fixture.invalid/higher-education"})
        data = baseline_solution(source)
        self.assertEqual(data["solution_landscape"][0]["mechanism"], "真人教师")
        self.assertEqual(data["evidence_ids"], ["E1"])
        self.assertNotIn("AI玩具世界第一品牌", str(data))
        self.assertNotIn("智能硬件", str(data["solution_landscape"]))
        self.assertIn("官网自述", data["solution_landscape"][0]["what_exists"])
        self.assertIn("不等于效果", data["opportunity_gap"]["existing_strength"])
        source["evidence_sources"][0]["content"] = "这段资料只有公司联系电话及地址。"
        self.assertEqual(baseline_solution(source)["evidence_ids"], [])
        self.assertEqual(baseline_solution(source)["solution_landscape"], [])

    def test_cumulative_revisions_keep_current_and_original_evidence(self):
        current = record()
        current["solution"]["product_concept"]["name"] = "保留这个人工命名"
        original_context = copy.deepcopy(current["opportunity_brief"]["source_context"])
        current["opportunity_brief"].update(age_range=[120, 155], preferred_carriers=["App / 网页"], constraints=["年龄改成10–12岁，不依赖硬件，降低家长参与"])
        revised = revise_baseline(current, "年龄改成10–12岁，不依赖硬件，降低家长参与")
        validate_solution(revised, [])
        self.assertEqual(revised["product_concept"]["name"], "保留这个人工命名")
        self.assertEqual(revised["carrier"]["choices"], ["App / 网页"])
        # Removing hardware does not by itself justify building an independent app.
        self.assertEqual(revised["solution_scope"], "prompt_tool")
        self.assertIn("Prompt", revised["fast_prototype"]["approach"])
        self.assertIn("10岁0个月–12岁11个月", revised["fast_prototype"]["copyable_prompt"])
        self.assertNotIn("6岁0个月–8岁11个月", revised["fast_prototype"]["copyable_prompt"])
        self.assertIn("首次", revised["human_role"][0])
        current["solution"] = revised
        again = revise_baseline(current, "改成还没有规则支持的新交互机制")
        self.assertEqual(again["product_concept"]["name"], "保留这个人工命名")
        self.assertIn("尚未自动完成", again["solution_mechanism"]["assumptions"][-1])
        self.assertEqual(current["opportunity_brief"]["source_context"], original_context)

    def test_markdown_has_complete_content_and_provenance_without_credentials(self):
        data = record()
        data["opportunity_brief"]["evidence_sources"] = [{"id": "E1", "title": "原始资料", "source_type": "公开用户讨论", "region": "中国大陆",
                                                          "date": "2026.09.10", "content": "这是应保留的来源摘录。", "url": "https://fixture.invalid/source"}]
        data["analysis_meta"]["revision_history"] = [{"instruction": "降低家长参与", "at": "2026-09-14T11:00:00+08:00"}]
        data["analysis_meta"]["api_key"] = "sk-test-should-never-export"
        data["opportunity_brief"]["source_context"].update({"market_research": {"huge_snapshot": "duplicate-research-should-not-export"},
                                                           "analyst": {"interpretation": "必须保留的继承分析"},
                                                           "chat": [{"question": "必须保留的追问", "answer": "来源限制仍需说明"}]})
        data["original_opportunity_brief"] = copy.deepcopy(data["opportunity_brief"])
        data["original_opportunity_brief"]["age_range"] = [36, 71]
        markdown = to_markdown(data)
        for title in ("Opportunity Brief", "Teaching Goal", "Opportunity Gap", "Product Concept", "Solution Mechanism", "AI Role", "Human Role", "MVP", "Demo Build Path", "Fast Prototype", "Validation Metrics", "Validation Plan", "Risks", "Evidence", "Revision History", "Source Snapshot"):
            with self.subTest(title=title):
                self.assertIn(title, markdown)
        self.assertIn("这是应保留的来源摘录。", markdown)
        self.assertIn("https://fixture.invalid/source", markdown)
        self.assertIn("降低家长参与", markdown)
        self.assertIn("确定性设计起点", markdown)
        self.assertNotIn("sk-test-should-never-export", markdown)
        self.assertNotIn("api_key", markdown)
        self.assertNotIn("duplicate-research-should-not-export", markdown)
        self.assertIn("必须保留的继承分析", markdown)
        self.assertIn("必须保留的追问", markdown)
        self.assertIn("Original Scope", markdown)

    def test_export_is_stable_safe_and_never_overwrites_different_content(self):
        data = record()
        data["solution"]["product_concept"]["name"] = "../../unsafe/name : 英语方案"
        with tempfile.TemporaryDirectory(prefix="engeduscope-m5-export-") as temp:
            directory = Path(temp)
            path = export_markdown(data, directory)
            self.assertEqual(path.parent, directory)
            self.assertTrue(path.name.startswith("20260914_product_concept_"))
            self.assertEqual(path.suffix, ".md")
            self.assertEqual(export_markdown(data, directory), path)
            initial = path.read_bytes()
            changed = copy.deepcopy(data)
            changed["record_id"] = "another-record"
            other = export_markdown(changed, directory)
            self.assertNotEqual(path, other)
            self.assertEqual(path.read_bytes(), initial)
            path.write_text("Existing different file must survive.")
            collision = export_markdown(data, directory)
            self.assertNotEqual(collision, path)
            self.assertEqual(path.read_text(), "Existing different file must survive.")
            self.assertEqual(collision.read_text(), to_markdown(data))
            self.assertTrue(all(p.suffix == ".md" for p in directory.iterdir()))


if __name__ == "__main__":
    unittest.main()
