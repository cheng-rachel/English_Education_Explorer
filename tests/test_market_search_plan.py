"""Targeted pure planning checks; no credentials, network or data writes."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from market_quality import prepare_evidence
from market_search_plan import build_demand_refill, build_search_plan, evidence_sufficiency


FILTERS = {"region": "中国大陆", "age_range": [84, 191], "skills": ["阅读理解"],
           "audiences": ["家长"], "contexts": ["自主学习"], "time_window": "近90天"}


class MarketSearchPlanChecks(unittest.TestCase):
    def test_china_plan_orders_four_intents_and_keeps_natural_english_domain(self):
        plan = build_search_plan(FILTERS)
        queries = plan["queries"]
        self.assertEqual(len(queries), 5)
        self.assertEqual([item["query_purpose"] for item in queries[:4]],
                         ["demand_problem", "attempted_solution", "dissatisfaction", "solution_supply"])
        self.assertEqual(plan["query_language_strategy"], "zh_first")
        for item in queries[:4]:
            self.assertEqual(item["language"], "zh")
            self.assertIn("英语", item["query"])
            self.assertNotIn("7–15", item["query"])
            self.assertNotIn("近90天", item["query"])
            self.assertLess(len(item["query"]), 50)
        self.assertIn("小学生", queries[0]["query"])
        self.assertIn("初中生", queries[2]["query"])
        self.assertIn("家长", queries[1]["query"])
        self.assertIn("自学", queries[1]["query"])

    def test_research_can_use_english_without_becoming_demand(self):
        plan = build_search_plan(FILTERS)
        research = plan["queries"][-1]
        self.assertEqual(plan["role_language_strategies"]["research"], "bilingual")
        self.assertEqual(research["language"], "en")
        self.assertEqual(research["evidence_role"], "research")
        self.assertEqual(research["query_language_strategy"], "bilingual")
        self.assertIn("EFL", research["query"])
        self.assertIn("reading comprehension", research["query"])

    def test_overseas_queries_are_english_and_student_audience_is_natural(self):
        filters = dict(FILTERS, region="海外 Benchmark", audiences=["学生"])
        plan = build_search_plan(filters)
        self.assertEqual(plan["query_language_strategy"], "en_first")
        self.assertTrue(all(value == "en_first" for value in plan["role_language_strategies"].values()))
        for item in plan["queries"] + build_demand_refill(filters):
            self.assertEqual(item["language"], "en")
            self.assertTrue("English" in item["query"] or "EFL" in item["query"])
            self.assertTrue(item["query"].isascii())
        self.assertIn("student", plan["queries"][0]["query"])
        self.assertIn("student", build_demand_refill(filters)[1]["query"])

    def test_refill_is_two_distinct_demand_queries_not_an_unbounded_loop(self):
        plan = build_search_plan(FILTERS)
        refill = build_demand_refill(FILTERS)
        first_queries = {item["query"] for item in plan["queries"]}
        self.assertEqual(len(refill), 2)
        self.assertEqual(len({item["query"] for item in refill}), 2)
        for item in refill:
            self.assertEqual(item["query_purpose"], "demand_refill")
            self.assertEqual(item["evidence_role"], "demand")
            self.assertEqual(item["language"], "zh")
            self.assertNotIn(item["query"], first_queries)
            self.assertIn("英语", item["query"])

    def test_sufficiency_deduplicates_sources_and_does_not_invent_demand(self):
        product = {"title": "英语阅读产品", "url": "https://official.example/reading?utm_source=search",
                   "source_type": "产品 / 机构官网", "query_purpose": "demand_problem"}
        data = [product, dict(product, url="https://official.example/reading", chunk_id="chunk2"),
                {"title": "学习路径", "raw_category": "learnpath", "document_id": "path"},
                {"title": "英语政策", "source_type": "政策 / 政府", "document_id": "policy"},
                {"title": "阅读机制研究", "source_type": "学术 / 研究机构", "document_id": "research"}]
        status = evidence_sufficiency(data)
        self.assertEqual(status["demand_sources"], 0)
        self.assertEqual(status["supply_sources"], 1)
        self.assertEqual(status["independent_sources"], 4)
        self.assertFalse(status["sufficient"])
        discussion = {"id": "E6", "title": "我家孩子英语阅读看不懂", "source_type": "公开用户讨论",
                      "content": "我家孩子英语阅读理解有困难，分级阅读读了很多还是看不懂。",
                      "url": "https://community.example/post/1", "time_scope": "within_window"}
        status = evidence_sufficiency(data + [discussion, dict(discussion, chunk_id="another")])
        self.assertEqual(status["demand_sources"], 1)
        self.assertEqual(status["recent_demand_sources"], 1)
        self.assertEqual(status["independent_sources"], 5)
        self.assertTrue(status["sufficient"])
        self.assertFalse(evidence_sufficiency([discussion])["sufficient"])
        self.assertFalse(evidence_sufficiency([])["sufficient"])

        no_problem = dict(discussion, content="今天记录我家孩子用过的英语阅读材料。")
        self.assertEqual(evidence_sufficiency([no_problem])["demand_sources"], 0)

    def test_historical_discussion_cannot_supply_recent_demand_count(self):
        status = evidence_sufficiency([{"id": "E1", "title": "家长阅读经验", "source_type": "公开用户讨论",
                                        "content": "我家孩子英语阅读理解有困难，试过阅读训练仍然看不懂。",
                                        "url": "https://community.example/old", "time_scope": "historical"}])
        self.assertEqual(status["demand_sources"], 1)
        self.assertEqual(status["recent_demand_sources"], 0)

    def test_existing_relevance_gate_still_excludes_satellite_schedule_and_math(self):
        irrelevant = [
            {"title": "SAR和光学卫星", "content": "SAR和光学卫星的观测安排，比较地表数据。"},
            {"title": "升学智能日程", "content": "帮助学校和家长管理报名日期以及升学活动的日程。"},
            {"title": "数学自动评阅", "content": "数学题评阅、数学公式识别、数学计算反馈；偶尔包含英语阅读理解。"},
        ]
        for index, item in enumerate(irrelevant):
            item.update(url=f"https://unrelated.example/{index}", region="中国大陆")
        self.assertEqual(prepare_evidence(irrelevant, FILTERS), [])
        self.assertEqual(evidence_sufficiency(prepare_evidence(irrelevant, FILTERS))["demand_sources"], 0)


if __name__ == "__main__":
    unittest.main()
