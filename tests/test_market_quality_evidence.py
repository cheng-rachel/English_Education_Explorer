"""Targeted Market evidence quality checks; no network or raw-file mutations."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from market_evidence import build_search_queries, combine_evidence
from market_quality import (clean_evidence_url, evidence_kind, noisy_text,
                            prepare_evidence, readable_excerpt, source_key)

FILTERS = {"region": "中国大陆", "time_window": "近90天", "age_range": [84, 191],
           "skills": ["阅读理解"], "contexts": ["自主学习"], "audiences": ["家长"]}


def source(title="英语阅读资料", content="英语阅读理解需要从熟悉文本迁移到陌生文本。", **values):
    data = {"id": "E1", "title": title, "source_type": "行业报告", "region": "中国大陆",
            "content": content, "document_id": title, "content_kind": "local_chunk"}
    data.update(values)
    return data


class MarketEvidenceQualityTests(unittest.TestCase):
    def test_roles_do_not_turn_supply_or_learning_into_demand(self):
        marketing = "我家孩子阅读理解困难，家长都很焦虑。产品帮助解决阅读问题。"
        self.assertEqual(evidence_kind(source(content=marketing, source_type="产品 / 机构官网", content_role="parent_experience")), "supply")
        self.assertEqual(evidence_kind(source(content=marketing)), "research")
        self.assertEqual(evidence_kind(source(content=marketing, source_type="公开用户讨论")), "demand")
        self.assertEqual(evidence_kind(source(content=marketing, raw_category="learnpath", content_role="parent_experience")), "learning")
        self.assertEqual(evidence_kind(source(content=marketing, source_type="政策 / 政府")), "policy")
        survey = "问卷调查了120名家长。家长反馈孩子阅读理解困难，尝试分级阅读后仍不会迁移。"
        self.assertEqual(evidence_kind(source(content=survey)), "demand")
        self.assertEqual(evidence_kind(source(title="K12英语在线教育产品全景扫描")), "supply")

    def test_reading_filters_writing_math_noise_and_duplicate_sources(self):
        sources = [
            source("英语阅读产品", "英语阅读理解。作文自动评阅用于作文写作，帮助写作表达。", id="E1"),
            source("数学AI练习", "数学代数和数学测验使用AI系统，也涉及阅读理解。", id="E2"),
            source("英语阅读研究", "阅 读 理 解 " * 30, id="E3"),
            source("英语阅读产品", "提供英语阅读训练。", id="E4", source_type="产品 / 机构官网", url="https://example.com/read?utm_source=a"),
            source("英语阅读产品", "提供英语分级阅读和阅读理解练习。阅读任务包含读后问答与阅读反馈。", id="E5", source_type="产品 / 机构官网", url="https://example.com/read#chapter"),
            source("家长的阅读经历", "我家孩子分级阅读读了很多，但英语阅读理解仍然困难。试过外教阅读课，遇到陌生文章还是看不懂。", id="E6", source_type="公开用户讨论"),
        ]
        result = prepare_evidence(sources, FILTERS)
        self.assertEqual([ev["id"] for ev in result], ["E6", "E5"])
        self.assertEqual(len({source_key(ev) for ev in result}), len(result))
        self.assertEqual(result[0]["evidence_kind"], "demand")
        self.assertEqual(sources[3]["url"], "https://example.com/read?utm_source=a")

    def test_excerpt_is_short_readable_and_contact_safe(self):
        self.assertEqual(readable_excerpt("阅 读 理 解 " * 30), "")
        self.assertEqual(readable_excerpt("brokenword" * 30), "")
        self.assertEqual(readable_excerpt("� | � | � | � " * 20), "")
        text = "孩子阅读以后，可以用自己的话复述主要意思。" * 20
        excerpt = readable_excerpt(text)
        self.assertLessEqual(len(excerpt), 140)
        self.assertTrue(excerpt.endswith("。"))
        clean = readable_excerpt("阅读理解可以通过读后提问练习。微信：abc_teacher123。手机：13812345678。邮箱：teacher@example.com。")
        for private in ("abc_teacher123", "13812345678", "teacher@example.com"):
            self.assertNotIn(private, clean)
        self.assertFalse(noisy_text("英语阅读需要持续练习，并关注每个学习阶段的理解能力。"))

    def test_clean_urls_preserve_official_navigation(self):
        dirty = "https://official.example/read?course=reading&utm_source=ad&utm_medium=web&fbclid=ABC#intro:~:text=reading"
        self.assertEqual(clean_evidence_url(dirty), "https://official.example/read?course=reading#intro")
        self.assertEqual(clean_evidence_url("https://official.example/"), "https://official.example/")
        self.assertEqual(clean_evidence_url("javascript:alert(1)"), "")

    def test_queries_prioritize_recent_user_experience_and_search_intake(self):
        queries = build_search_queries(FILTERS)
        self.assertEqual(len(queries), 5)
        self.assertIn("看不懂", queries[0])
        self.assertIn("经验", queries[1])
        self.assertIn("还是不会", queries[2])
        self.assertIn("产品", queries[3])
        self.assertIn("EFL", queries[4])
        local = [source("阅读官网", source_type="产品 / 机构官网", url="https://official.example/read")]
        live = [{"title": "孩子英语阅读经历", "url": "https://www.reddit.com/r/English/comments/example?utm_source=share",
                 "content": "我家孩子英语阅读理解有困难。试过分级阅读，读了很多但陌生文本还是看不懂。",
                 "published_date": "2026-09-13", "content_kind": "search_snippet"}]
        result = combine_evidence(local, live, FILTERS)
        self.assertEqual(result[0]["evidence_kind"], "demand")
        self.assertEqual(result[0]["origin"], "web")
        self.assertNotIn("utm_source", result[0]["url"])
        self.assertEqual(result[1]["evidence_kind"], "supply")
        self.assertEqual([ev["id"] for ev in result], ["E1", "E2"])

    def test_age_filter_and_preserved_history_ids(self):
        data = [source("3–5岁英语阅读", id="E1"), source("9–12岁英语阅读", id="E9")]
        result = prepare_evidence(data, FILTERS)
        self.assertEqual([ev["id"] for ev in result], ["E9"])

    def test_broad_report_does_not_smuggle_adult_or_preschool_passages(self):
        data = [
            source("AI教育行业报告", "高等教育阅读工具帮助论文阅读。学术科研通过阅读文献综述提高效率。", id="E1"),
            source("教育硬件报告", "早教点读笔通过幼儿绘本阅读辅助阅读理解。幼儿阶段注重听故事。", id="E2"),
            source("教育硬件报告", "美国校外教育智能硬件提供阅读服务。美国教育智能硬件包含阅读游戏。", id="E3"),
            source("教育研究报告", "• 阅读能力• 写作能力• 思考能力• 社交能力• 推理能力• 沟通能力", id="E4"),
            source("EduStar", "阅读理解可以通过划线显性化理解过程。产品帮助阅读速度与长难句理解，并反哺写作。", id="E8", source_type="产品 / 机构官网"),
        ]
        result = prepare_evidence(data, FILTERS)
        self.assertEqual([ev["id"] for ev in result], ["E8"])


if __name__ == "__main__":
    unittest.main()
