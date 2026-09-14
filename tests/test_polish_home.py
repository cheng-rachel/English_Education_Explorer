"""v1 homepage/navigation and maintenance output privacy, using isolated local data."""

import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "03app"))

from llm import provider as ai_provider, settings as ai_settings
from web_search import settings as search_settings

TITLES = [
    "我想解决一个具体的英语学习问题",
    "我想看看英语教育市场现在需要什么",
    "我想把已有需求做成一个 AI 英语教学工具",
]
DESCRIPTIONS = [
    "告诉我孩子现在遇到了什么困难，我们一起看看可能卡在哪里，以及接下来可以怎么做。",
    "看看家长、教师和教育产品最近都在关注什么，还有哪些问题没有被很好解决。",
    "从一个学习问题或市场机会出发，快速想清楚工具应该解决什么、怎么做，以及第一版 Demo 怎么验证。",
]


def visible(app):
    kinds = ("title", "header", "subheader", "caption", "markdown", "info", "warning", "error", "success", "code", "metric")
    text = "\n".join(str(item.value) for kind in kinds for item in app.get(kind))
    return text + "\n" + "\n".join(item.value.to_json(force_ascii=False) for item in app.dataframe)


class HomePolishTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="english-explorer-polish-")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        for patcher in (
            patch.object(ai_settings, "CONFIG_PATH", self.directory / "llm.json"),
            patch.object(search_settings, "CONFIG_PATH", self.directory / "search.json"),
            patch.dict(os.environ, {
                "ENGEDUSCOPE_DB_PATH": str(self.directory / "history.db"),
                "ENGEDUSCOPE_RAW_ROOT": str(self.directory / "raw"),
                "ENGEDUSCOPE_KNOWLEDGE_ROOT": str(self.directory / "knowledge"),
            }, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=20).run()

    def test_home_uses_exact_copy_equal_heading_levels_and_current_brand(self):
        app = self.app()
        self.assertFalse(app.exception)
        output = visible(app)
        self.assertIn("English Education Explorer", output)
        self.assertIn("英探探：英语学习与教育探索器", output)
        self.assertIn("从具体学习问题，到市场需求，再到可以落地的 AI 英语教学工具。", output)
        self.assertIn('text-align:center', output)
        self.assertEqual([heading.value for heading in app.subheader], TITLES)
        self.assertEqual({heading.proto.tag for heading in app.subheader}, {"h3"})
        for description in DESCRIPTIONS:
            self.assertIn(description, output)
        self.assertIn("查看我的历史方案记录", output)
        self.assertIn("回到之前保存的需求分析、市场观察和工具方案，继续查看或修改。", output)
        self.assertNotIn("EngEduScope", output)
        self.assertNotIn("Opportunity Explorer", output)
        self.assertEqual([item.proto.label for item in app.get("page_link")],
                         ["Solve a Need", "Explore the Market", "Build a Solution", "History", "Manage Data"])

    def test_api_button_opens_existing_settings_without_exposing_keys_or_network(self):
        ai_settings.save_config(ai_provider.LLMConfig(provider="custom", api_key="private-ai-test-secret",
                                base_url="https://example.invalid/v1", model="test-model"))
        search_settings.save_config(search_settings.SearchConfig(api_key="private-search-test-secret"))
        with patch("requests.post") as post, patch("requests.Session") as session:
            app = self.app()
            self.assertIn("启用 AI 与联网能力", visible(app))
            self.assertIn("当前可以直接体验本地 Demo。如果希望使用真实 AI 分析或联网搜索，可以在这里配置自己的 API，不需要打开终端。", visible(app))
            self.assertIn("AI：Custom · Live", visible(app))
            self.assertIn("联网搜索：Live Search Ready", visible(app))
            self.assertEqual(app.button(key="home_configure_services").label, "配置 AI 与联网服务")
            app.button(key="home_configure_services").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state["md_open_services"])
            self.assertEqual([tab.label for tab in app.tabs], ["Knowledge Base", "Structured Data", "Sources", "AI Settings", "Search Settings", "System Status"])
            self.assertEqual(app.text_input(key="ai_key_input").value, "")
            self.assertEqual(app.text_input(key="search_key_input").value, "")
            self.assertNotIn("private-ai-test-secret", visible(app))
            self.assertNotIn("private-search-test-secret", visible(app))
            post.assert_not_called()
            session.assert_not_called()

    def test_maintenance_sanitizes_existing_sources_and_kb_without_mutating_them(self):
        private = "联系王老师，微信：teacher_private_77；邮箱 person@example.net；电话 13800138000。"
        doc = {"title": "Reading guide。" + private, "region": "general_reference", "raw_category": "learnpath",
               "source_type": "研究论文", "source_kind": "md", "original_path": "notes/person@example.net.md",
               "source_url": "https://wa.me/13800138000", "date": "2026-09-13", "education_relevance": "Core",
               "skills": ["阅读理解"], "parse_status": "success", "chunk_count": 1}
        registry = {"category": "研究", "folder": "03research", "exists": True, "error": "",
                    "friendly_path": "notes/person@example.net.xlsx", "header": ["title", "person@example.net"],
                    "rows": [{"title": doc["title"], "source_type": "研究论文", "date": "2026-09-13",
                              "url": doc["source_url"], "note": private}]}
        original = copy.deepcopy((doc, registry))
        stats = {"documents": 1, "chunks": 1, "by_status": {"success": 1}, "by_region": {"general_reference": 1},
                 "by_kind": {"md": 1}, "by_relevance": {"Core": 1}, "last_build": None}
        hit = SimpleNamespace(title=doc["title"], section_title=private, snippet="Reading practice。" + private,
                              chunk_text=private, region=doc["region"], source_type=doc["source_type"], source_kind="md",
                              source_url=doc["source_url"], original_path=doc["original_path"],
                              markdown_path="knowledge/13800138000.md", page_start=1, page_end=1,
                              date=doc["date"], education_relevance="Core")
        with patch("knowledge.kb_db.stats", return_value=stats), \
             patch("knowledge.kb_db.list_failures", return_value=[dict(doc, parse_status="fetch_failed")]), \
             patch("knowledge.kb_db.list_documents", return_value=[doc]), \
             patch("knowledge.kb_db.distinct_values", return_value=["研究论文"]), \
             patch("knowledge.ui_kb.search", return_value=[hit]), \
             patch("sources_xlsx.list_registries", return_value=[registry]):
            app = self.app()
            app.button(key="home_configure_services").click().run()
            # Pin the selected page for subsequent AppTest widget reruns.
            app.switch_page("05_manage_data.py").run()
            app.session_state["kb_last_summary"] = {"mode": "incremental", "log_path": "logs/person@example.net.log"}
            app.text_input(key="kb_query").set_value("reading").run()
            self.assertFalse(app.exception)
            output = visible(app)
            for token in ("teacher_private_77", "person@example.net", "13800138000", "https://wa.me", "联系王老师"):
                self.assertNotIn(token, output)
            self.assertIn("Reading practice", output)
            self.assertIn("通用学习路径参考资料", output)
            self.assertIn("通用学习路径参考资料", app.selectbox(key="kb_f_region").options)
            self.assertNotIn("通用学习路径参考资料", app.radio(key="src_market").options)
            self.assertFalse(app.get("download_button"))
        self.assertEqual((doc, registry), original)

    def test_build_progress_and_saved_summary_filter_contacts_before_display(self):
        from knowledge import ui_kb
        fake_st = MagicMock()
        fake_st.session_state = {}
        private = "正在处理 person@example.net.md，微信：teacher_private_77。"
        summary = {"mode": "incremental", "log_path": "logs/13800138000.log", "discovered": 1}

        def fake_build(mode, on_progress):
            on_progress({"current": 1, "total": 1, "message": private})
            return SimpleNamespace(as_record=lambda: summary)

        with patch.object(ui_kb, "st", fake_st), patch.object(ui_kb, "build_knowledge_base", side_effect=fake_build):
            ui_kb._run_build("incremental")
        output = str(fake_st.mock_calls) + str(fake_st.session_state)
        for token in ("person@example.net", "teacher_private_77", "13800138000"):
            self.assertNotIn(token, output)
        self.assertIn("13800138000", summary["log_path"])


if __name__ == "__main__":
    unittest.main()
