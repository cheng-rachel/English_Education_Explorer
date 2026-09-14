"""Credential persistence, provider contracts, and failure boundaries without live API."""

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

import requests
from llm import provider, settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / ".local" / "llm_config.json"
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.path_patch = patch.object(settings, "CONFIG_PATH", self.path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def config(self, **kwargs):
        return provider.LLMConfig(**({"provider": "custom", "api_key": "test-secret-never-log", "base_url": "https://example.invalid/v1", "model": "test-model"} | kwargs))

    def test_private_persistence_restart_and_clear_override_environment(self):
        cfg = self.config()
        settings.save_config(cfg)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(provider.load_config().api_key, cfg.api_key)
        self.assertEqual(provider.load_config().provider, "custom")
        self.assertNotIn(cfg.api_key, repr(provider.load_config()))
        os.environ["OPENAI_API_KEY"] = "environment-key"
        self.assertEqual(provider.load_config().api_key, cfg.api_key)
        settings.clear_config()
        restored = provider.load_config()
        self.assertTrue(restored.is_mock)
        self.assertFalse(restored.api_key)
        self.assertNotIn(cfg.api_key, self.path.read_text())
        self.assertNotIn("environment-key", self.path.read_text())

    def test_missing_config_demo_and_legacy_environment(self):
        self.assertTrue(provider.load_config().is_mock)
        os.environ["DEEPSEEK_API_KEY"] = "environment-key"
        cfg = provider.load_config()
        self.assertFalse(cfg.is_mock)
        self.assertEqual(cfg.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(cfg.model, "deepseek-chat")
        os.environ["ENGEDUSCOPE_LLM_PROVIDER"] = "anthropic"
        os.environ["ANTHROPIC_API_KEY"] = "anthropic-only"
        self.assertEqual(provider.load_config().api_key, "anthropic-only")

    def test_bad_timeout_and_bad_file_are_friendly_and_do_not_fallback(self):
        os.environ["ENGEDUSCOPE_LLM_TIMEOUT"] = "bad-secret-value"
        cfg = provider.load_config()
        self.assertTrue(cfg.configuration_error)
        self.assertNotIn("bad-secret-value", cfg.configuration_error)
        os.environ.pop("ENGEDUSCOPE_LLM_TIMEOUT")
        self.path.parent.mkdir()
        self.path.write_text("malformed secret file", encoding="utf-8")
        os.environ["OPENAI_API_KEY"] = "environment-key"
        cfg = provider.load_config()
        self.assertFalse(cfg.configured)
        self.assertFalse(cfg.api_key)
        self.assertNotIn("malformed secret", cfg.configuration_error)

    def test_invalid_live_config_does_not_replace_valid_file(self):
        settings.save_config(self.config())
        before = self.path.read_bytes()
        for changes in ({"base_url": "https://user:password@example.invalid/v1"}, {"base_url": "https://example.invalid/?key=secret"}, {"api_key": ""}, {"timeout": 0}, {"timeout": 301}, {"provider": "invalid"}, {"api_key": "key\nheader"}):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(provider.LLMError):
                    settings.save_config(self.config(**changes))
                self.assertEqual(self.path.read_bytes(), before)

    @patch("requests.post")
    def test_openai_custom_and_anthropic_request_protocols(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": '{"ok": true}'}}]})
        self.assertEqual(provider.complete_json("system", "user", retries=0, cfg=self.config()), {"ok": True})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://example.invalid/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-secret-never-log")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "system")
        post.return_value = Mock(status_code=200, json=lambda: {"content": [{"type": "text", "text": '{"ok": true}'}]})
        cfg = self.config(provider="anthropic", base_url="https://example.invalid/v1")
        provider.test_connection(cfg)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://example.invalid/v1/messages")
        self.assertEqual(kwargs["headers"]["x-api-key"], cfg.api_key)
        self.assertIn("system", kwargs["json"])

    @patch("requests.post")
    def test_network_errors_never_echo_keys_urls_or_response_bodies(self, post):
        secret = "request-with-test-secret-never-log"
        for error, expected in ((requests.Timeout(secret), provider.LLMTimeout), (requests.ConnectionError(secret), provider.LLMRequestError)):
            with self.subTest(kind=expected.__name__):
                post.side_effect = error
                with self.assertRaises(expected) as caught:
                    provider.complete_json("system", "user", retries=0, cfg=self.config())
                self.assertNotIn(secret, str(caught.exception))
                self.assertNotIn(secret, caught.exception.user_message)
        post.side_effect = None
        post.return_value = Mock(status_code=401, text=secret)
        with self.assertRaises(provider.LLMRequestError) as caught:
            provider.complete_json("system", "user", retries=0, cfg=self.config())
        self.assertNotIn(secret, str(caught.exception))
        post.return_value.json.assert_not_called()

    @patch("requests.post")
    def test_malformed_transport_json_and_content_shapes_are_handled_once(self, post):
        responses = [
            Mock(status_code=200, json=Mock(side_effect=ValueError("secret response body"))),
            Mock(status_code=200, json=lambda: []),
            Mock(status_code=200, json=lambda: {"choices": []}),
            Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": {"not": "text"}}}]}),
        ]
        for response in responses:
            post.reset_mock()
            post.return_value = response
            with self.assertRaises(provider.LLMBadResponse) as caught:
                provider.complete_json("system", "user", retries=0, cfg=self.config())
            self.assertEqual(post.call_count, 1)
            self.assertNotIn("secret response body", str(caught.exception))

    @patch("requests.post")
    def test_standalone_retry_is_bounded(self, post):
        bad = Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": "not JSON"}}]})
        good = Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]})
        post.side_effect = [bad, good]
        self.assertEqual(provider.complete_json("system", "user", retries=1, cfg=self.config()), {"ok": True})
        self.assertEqual(post.call_count, 2)

    def test_settings_ui_test_save_restart_reentry_clear_without_key_echo(self):
        from streamlit.testing.v1 import AppTest

        script = ('import streamlit as st\nfrom llm.ui_settings import render_ai_settings\n'
                  'if st.checkbox("Show settings", value=True):\n    render_ai_settings()')

        def widget(app, kind, label):
            return next(item for item in getattr(app, kind) if item.label == label)

        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        widget(app, "selectbox", "Provider").set_value("Custom").run()
        widget(app, "radio", "运行模式").set_value("Live API")
        widget(app, "text_input", "Base URL").set_value("https://example.invalid/v1")
        widget(app, "text_input", "Model").set_value("test-model")
        widget(app, "text_input", "API Key").set_value("test-ui-secret")
        response = Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": '{"ok":true}'}}]})
        with patch("requests.post", return_value=response) as post:
            widget(app, "button", "测试连接").click().run()
            self.assertEqual(post.call_count, 1)
        self.assertFalse(app.exception)
        self.assertEqual(widget(app, "text_input", "API Key").value, "")
        self.assertFalse(self.path.exists())
        widget(app, "button", "保存配置").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(provider.load_config().api_key, "test-ui-secret")
        self.assertTrue(any(metric.value == "已连接" for metric in app.metric))
        restarted = AppTest.from_string(script).run()
        self.assertFalse(restarted.exception)
        self.assertEqual(widget(restarted, "text_input", "API Key").value, "")
        self.assertEqual(widget(restarted, "text_input", "Model").value, "test-model")
        self.assertNotIn("test-ui-secret", str([item.value for item in restarted.caption]))
        # Conditional rendering reproduces Streamlit's cleanup on leaving a page.
        widget(restarted, "checkbox", "Show settings").uncheck().run()
        widget(restarted, "checkbox", "Show settings").check().run()
        self.assertFalse(restarted.exception)
        self.assertEqual(widget(restarted, "text_input", "API Key").value, "")
        widget(restarted, "button", "清除配置").click().run()
        self.assertFalse(restarted.exception)
        self.assertFalse(provider.load_config().api_key)
        self.assertTrue(provider.load_config().is_mock)

    def test_settings_ui_does_not_reuse_key_for_new_service(self):
        from streamlit.testing.v1 import AppTest

        settings.save_config(self.config())
        app = AppTest.from_string("from llm.ui_settings import render_ai_settings\nrender_ai_settings()").run()
        next(item for item in app.text_input if item.label == "Base URL").set_value("https://new-service.invalid/v1")
        with patch("requests.post") as post:
            next(item for item in app.button if item.label == "测试连接").click().run()
            post.assert_not_called()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertEqual(provider.load_config().base_url, "https://example.invalid/v1")


if __name__ == "__main__":
    unittest.main()
