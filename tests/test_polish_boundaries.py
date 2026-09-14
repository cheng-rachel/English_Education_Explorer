"""Contact protection at real provider, research, persistence and export boundaries.

All credentials are fixtures, HTTP is mocked, and writable files use a temp directory.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))

import db
from llm import prompts
from llm.provider import LLMConfig, complete_json
from market_evidence import combine_evidence, normalize_filters
from market_analysis import analyze_market, follow_up
from market_prompts import SYSTEM as MARKET_SYSTEM, chat_prompt
from output_safety import CONTACT_POLICY
from solution_analysis import generate_solution, revise_solution
from solution_context import from_scratch
from solution_export import export_markdown, to_markdown
from solution_prompts import SYSTEM as SOLUTION_SYSTEM, generate_prompt
from web_search.provider import search_web
from web_search.settings import SearchConfig

CONTACTS = "微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com\nQQ：123456789\n扫码咨询张老师。"
FORBIDDEN = ("abc_teacher123", "13812345678", "teacher@example.com", "123456789", "扫码咨询张老师")
OFFICIAL = "https://www.britishcouncil.org/"


def source(region="中国大陆", **extra):
    return dict({"id": "E1", "title": "家庭英语口语讨论", "region": region,
                 "content": "家长表示试过分级阅读，但孩子口语仍只会跟读，需要自主表达练习。\n" + CONTACTS,
                 "source_type": "公开用户讨论", "url": OFFICIAL, "date": "2026-09-01",
                 "time_scope": "within_window", "origin": "local", "credibility_level": "C"}, **extra)


class OutputBoundaryChecks(unittest.TestCase):
    def assert_safe(self, value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        for token in FORBIDDEN:
            self.assertNotIn(token, text)

    def test_actual_provider_filters_response_and_prompts_include_policy(self):
        cfg = LLMConfig(provider="custom", model="fixture", api_key="fixture-key", base_url="https://fixture.invalid/v1")
        with patch("llm.provider._call_once", return_value=json.dumps({"answer": CONTACTS + "\n可参考官方机构。", "url": OFFICIAL})):
            result = complete_json("fixture", "fixture", cfg=cfg)
        self.assert_safe(result)
        self.assertEqual(result["url"], OFFICIAL)
        for system in (prompts.SYSTEM_PARENT, prompts.SYSTEM_EDUCATOR, MARKET_SYSTEM, SOLUTION_SYSTEM):
            self.assertIn(CONTACT_POLICY, system)
            self.assertIn("English Education Explorer", system)
        self.assert_safe(prompts.format_evidence([dict(source(), text=CONTACTS)]))
        self.assert_safe(chat_prompt({"problem_summary": CONTACTS}, [source()], CONTACTS))

    def test_market_search_and_chat_keep_official_links_and_exclude_learning_reference(self):
        filters = normalize_filters({"region": "中国大陆", "age_range": [72, 107], "skills": ["口语表达"],
                                     "contexts": ["自主学习"], "audiences": ["家长"], "time_window": "近90天"})
        reference = source("general_reference", raw_category="learnpath", evidence_role="learning_reference")
        forged_reference = source(raw_category="learnpath", evidence_role="learning_reference")
        combined = combine_evidence([source(), reference, forged_reference], [], filters)
        self.assertEqual(len(combined), 1)
        self.assert_safe(combined)
        with patch("market_analysis.retrieve_local", return_value=([source(), reference], [])), \
                patch("market_analysis.load_config", return_value=LLMConfig(provider="mock")), \
                patch("market_analysis.load_search_config", return_value=Mock(configured=False)), \
                patch("market_analysis.search_web", side_effect=AssertionError("No automatic search")):
            record = analyze_market(filters)
            self.assertTrue(record["signals"])
            answer = follow_up(record["signals"][0], record["evidence_sources"], "现有产品为什么还没解决？")
        self.assert_safe(record)
        self.assert_safe(answer)
        self.assertEqual({e["region"] for e in record["evidence_sources"]}, {"中国大陆"})
        cfg = SearchConfig(provider="tavily", api_key="fixture-key")
        with patch("web_search.provider._search_once", return_value={"results": [{"title": "官方口语活动", "url": OFFICIAL, "content": CONTACTS + "\n提供英语口语练习。"}]}), \
                patch("web_search.provider.append_failures", return_value=True):
            live = search_web(["儿童英语口语"], dict(filters, fetch_pages=False), cfg=cfg)
        self.assert_safe(live)
        self.assertEqual(live["results"][0]["url"], OFFICIAL)

    def test_build_revision_history_and_utf8_export_preserve_evidence_without_contacts(self):
        brief = from_scratch({"target_user": "6–8岁儿童及家长", "age_range": [72, 107],
                              "skills": ["口语表达"], "contexts": ["家庭固定学习"], "region": "中国大陆",
                              "core_need": "阅读输入较多但主动口语不足。\n" + CONTACTS})
        brief["evidence_sources"] = [source()]
        original = deepcopy(brief)
        with patch("solution_analysis.load_config", return_value=LLMConfig(provider="mock")), \
                patch("solution_analysis._retrieve", return_value=([], {"calls": 1, "status": "no_matches"})):
            record = generate_solution(brief)
            revised = revise_solution(record, "第一版只用 Web App。\n" + CONTACTS)
        self.assertEqual(brief, original)
        self.assert_safe(record)
        self.assert_safe(revised)
        self.assert_safe(generate_prompt(brief))
        # Simulate an older saved result that predates the shared protection.
        revised["solution"]["product_concept"]["value_proposition"] += "\n" + CONTACTS
        revised["opportunity_brief"]["evidence_sources"] = [source()]
        revised["analysis_meta"]["api_key"] = "must-not-be-exported-or-saved"
        with tempfile.TemporaryDirectory(prefix="polish-boundaries-") as temporary:
            with patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(Path(temporary) / "history.db")}):
                db.init_db()
                identifier = db.save_research_session("English Education Explorer\n" + CONTACTS,
                                                      "educator", "build_solution", revised)
                row = db.get_research_session(identifier)
                self.assert_safe(row["title"])
                self.assert_safe(row["summary_json"])
                self.assertNotIn("must-not-be-exported-or-saved", row["summary_json"])
            path = export_markdown(revised, Path(temporary) / "generated")
            body = path.read_text(encoding="utf-8")
            self.assertEqual(body, to_markdown(revised))
            self.assert_safe(body)
            self.assertIn(OFFICIAL, body)
            self.assertIn("Evidence", body)
            self.assertIn("教学目标", body)
            self.assertNotIn("must-not-be-exported-or-saved", body)


if __name__ == "__main__":
    unittest.main()
