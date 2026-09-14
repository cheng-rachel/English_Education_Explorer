"""M6 safe configuration/status and maintenance UI checks; no live API or user data writes."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "03app"))

import app_status
from llm import provider as ai_provider, settings as ai_settings
from web_search import settings as search_settings


def visible(app):
    kinds = ("caption", "markdown", "info", "warning", "error", "success", "code", "metric")
    return "\n".join(str(item.value) for kind in kinds for item in app.get(kind))


class StatusSettingsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="engeduscope-m6-settings-")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        for patcher in (
            patch.object(ai_settings, "CONFIG_PATH", self.directory / "llm.json"),
            patch.object(search_settings, "CONFIG_PATH", self.directory / "search.json"),
            patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(self.directory / "history.db")}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def configure_live(self):
        ai_settings.save_config(ai_provider.LLMConfig(provider="custom", api_key="private-ai-test-secret",
                                base_url="https://example.invalid/v1", model="test-model"))
        search_settings.save_config(search_settings.SearchConfig(api_key="private-search-test-secret"))

    def test_status_labels_are_read_only_and_never_expose_credentials(self):
        self.assertEqual(app_status.get_status()["ai_label"], "Demo")
        self.assertEqual(app_status.get_status()["search_label"], "Local Only")
        self.configure_live()
        with patch("requests.post") as post, patch("requests.Session") as session:
            status = app_status.get_status()
            self.assertEqual(status["ai_label"], "Custom · Live")
            self.assertEqual(status["search_label"], "Live Search Ready")
            self.assertNotIn("private-", str(status))
            self.assertNotIn("example.invalid", str(status))
            post.assert_not_called()
            session.assert_not_called()

    def test_shared_errors_and_broken_settings_are_safe(self):
        for error in (ai_provider.LLMNotConfigured("raw-private-detail"), ai_provider.LLMConfigurationError("raw-private-detail")):
            self.assertEqual(app_status.ai_error_message(error), app_status.AI_UNAVAILABLE)
        self.assertEqual(app_status.ai_error_message(ai_provider.LLMTimeout("raw-private-detail")), ai_provider.LLMTimeout.user_message)
        self.assertNotIn("raw-private-detail", app_status.ai_error_message(RuntimeError("raw-private-detail")))
        with patch("llm.provider.load_config", side_effect=RuntimeError("raw-private-detail")):
            self.assertFalse(app_status.get_status()["ai_available"])
        with patch("web_search.settings.load_config", side_effect=RuntimeError("raw-private-detail")):
            self.assertEqual(app_status.get_status()["search_label"], "Local Only")

    def test_status_renderer_marks_demo_without_warning_and_unavailable_with_shared_copy(self):
        from streamlit.testing.v1 import AppTest
        script = "from app_status import render_status\nrender_status(compact=True)"
        with patch("requests.post") as post, patch("requests.Session") as session:
            app = AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            self.assertIn("AI · Demo", visible(app))
            self.assertFalse(app.warning)
            self.assertFalse(app.info)
            post.assert_not_called()
            session.assert_not_called()
        with patch("llm.provider.load_config", return_value=ai_provider.LLMConfig(provider="none", configuration_error="invalid")):
            app = AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            self.assertIn(app_status.AI_UNAVAILABLE, visible(app))

    def test_both_settings_keep_empty_password_values_and_consistent_actions(self):
        from streamlit.testing.v1 import AppTest
        self.configure_live()
        script = ("from llm.ui_settings import render_ai_settings\nfrom web_search.ui_settings import render_search_settings\n"
                  "render_ai_settings()\nrender_search_settings()")
        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key="ai_key_input").value, "")
        self.assertEqual(app.text_input(key="search_key_input").value, "")
        self.assertEqual(app.text_input(key="ai_key_input").label, "API Key")
        self.assertEqual(app.text_input(key="search_key_input").label, "API Key")
        self.assertEqual(app.selectbox(key="ai_provider").label, "Provider")
        self.assertEqual(app.selectbox(key="search_provider").label, "Provider")
        self.assertEqual(app.radio(key="ai_mode").options, ["Demo", "Live"])
        self.assertEqual(app.radio(key="ai_mode").value, "Live API")
        for prefix in ("ai", "search"):
            self.assertEqual(app.button(key=f"{prefix}_test").label, "测试连接")
            self.assertEqual(app.button(key=f"{prefix}_save").label, "保存配置")
            self.assertEqual(app.button(key=f"{prefix}_clear").label, "清除配置")
        self.assertNotIn("private-ai-test-secret", visible(app))
        self.assertNotIn("private-search-test-secret", visible(app))
        with patch("requests.post", return_value=Mock(status_code=401, text="private-ai-test-secret")) as post:
            app.button(key="ai_test").click().run()
            self.assertEqual(post.call_count, 1)
        self.assertFalse(app.exception)
        self.assertNotIn("private-ai-test-secret", visible(app))
        self.assertEqual(app.text_input(key="ai_key_input").value, "")

    def test_manage_data_keeps_six_tabs_reachable_when_database_is_unavailable(self):
        from streamlit.testing.v1 import AppTest
        with patch("knowledge.kb_db.stats", side_effect=RuntimeError("SQL SELECT raw-private-db")), \
             patch("knowledge.kb_db.list_failures", side_effect=RuntimeError("SQL SELECT raw-private-db")), \
             patch("db.list_research_sessions", side_effect=RuntimeError("SQL SELECT raw-private-db")), \
             patch("sources_xlsx.list_registries", return_value=[]):
            app = AppTest.from_file(str(PROJECT / "03app" / "00_app.py"), default_timeout=20).run()
            app.switch_page("05_manage_data.py").run()
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ["Knowledge Base", "Structured Data", "Sources", "AI Settings", "Search Settings", "System Status"])
        self.assertNotIn("raw-private-db", visible(app))
        self.assertNotIn("SQL SELECT", visible(app))
        self.assertIn(app_status.KNOWLEDGE_UNAVAILABLE, visible(app))
        self.assertIn("本地记录暂时无法读取", visible(app))
        self.assertIn("05public_discussions", visible(app))
        self.assertIn("同样五个子目录", visible(app))
        self.assertEqual(app.text_input(key="ai_key_input").value, "")
        self.assertEqual(app.text_input(key="search_key_input").value, "")

    def test_public_discussion_aliases_and_failed_source_messages(self):
        from knowledge.ui_kb import _failure_reason
        aliases = ["public discussion", "public discussions", "user discussion", "用户帖子", "用户讨论", "公开讨论", "public_discussion"]
        for alias in aliases:
            self.assertEqual(app_status.source_type_label(alias), "公开用户讨论")
        self.assertEqual(app_status.source_type_label("研究论文"), "研究论文")
        self.assertNotIn("raw-private-db", _failure_reason({"parse_status": "parse_failed", "error_message": "SQL SELECT raw-private-db"}))
        self.assertIn("OCR", _failure_reason({"parse_status": "needs_ocr"}))


if __name__ == "__main__":
    unittest.main()
