"""M4 search/config boundaries using fake HTTP and temporary private files."""

from datetime import date, timedelta
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

import requests
from web_search import intake, provider, settings


def response(status=200, data=None, body=b"", content_type="text/html"):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = data
    result.headers = {"Content-Type": content_type}
    result.encoding = "utf-8"
    result.__enter__.return_value = result
    result.iter_content.return_value = iter([body])
    return result


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config_path = Path(self.directory.name) / ".local" / "search_config.json"
        self.log_path = self.config_path.parent / "search_failures.jsonl"
        for patcher in (patch.object(settings, "CONFIG_PATH", self.config_path),
                        patch.object(settings, "FAILURE_LOG_PATH", self.log_path),
                        patch.dict(os.environ, {}, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cfg = settings.SearchConfig(api_key="test-tavily-secret")

    def result(self, url="https://example.invalid/article", **changes):
        return {"title": "English education source", "url": url, "content": "A relevant English learning discussion.",
                "published_date": date.today().isoformat(), **changes}

    def test_private_save_reload_clear_and_invalid_config(self):
        settings.save_config(self.cfg)
        self.assertEqual(stat.S_IMODE(self.config_path.stat().st_mode), 0o600)
        self.assertEqual(provider.load_config().api_key, self.cfg.api_key)
        self.assertNotIn(self.cfg.api_key, repr(provider.load_config()))
        os.environ["TAVILY_API_KEY"] = "env-secret"
        settings.clear_config()
        self.assertFalse(provider.load_config().configured)
        self.assertNotIn(self.cfg.api_key, self.config_path.read_text())
        self.config_path.write_text("invalid secret config")
        broken = provider.load_config()
        self.assertFalse(broken.configured)
        self.assertTrue(broken.configuration_error)
        self.assertNotIn("invalid secret", broken.configuration_error)

    @patch("requests.Session")
    def test_no_key_never_requests_or_updates_timestamp(self, session):
        result = provider.search_web(["English education"], {"time_window": "近90天"})
        self.assertEqual(result["status"], "not_configured")
        self.assertIsNone(result["searched_at"])
        session.assert_not_called()
        self.assertFalse(self.log_path.exists())

    @patch("requests.Session")
    def test_search_protocol_caps_queries_results_and_sets_exact_dates(self, session_type):
        session = session_type.return_value.__enter__.return_value
        def fake_post(url, **kwargs):
            query = kwargs["json"]["query"]
            return response(data={"results": [self.result(f"https://example.invalid/{query}/{i}") for i in range(10)]})
        session.post.side_effect = fake_post
        result = provider.search_web(["one", "two", "three", "four"], {"time_window": "近90天", "fetch_pages": False}, cfg=self.cfg)
        self.assertEqual(result["status"], "success")
        self.assertIsNotNone(result["searched_at"])
        self.assertEqual(len(result["results"]), 6)
        self.assertEqual(session.post.call_count, 3)
        self.assertFalse(session.trust_env)
        for call in session.post.call_args_list:
            args, kwargs = call
            self.assertEqual(args[0], provider.ENDPOINT)
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-tavily-secret")
            self.assertFalse(kwargs["allow_redirects"])
            payload = kwargs["json"]
            self.assertEqual(payload["max_results"], 2)
            self.assertEqual(payload["start_date"], (date.today() - timedelta(days=90)).isoformat())
            self.assertEqual(payload["end_date"], date.today().isoformat())
            self.assertTrue(payload["include_published_date"])
            self.assertFalse(payload["include_answer"])
            self.assertFalse(payload["include_raw_content"])

    @patch("web_search.provider.fetch_page")
    @patch("web_search.provider._search_once")
    def test_partial_search_fetch_fallback_and_private_failure_log(self, search, fetch):
        search.side_effect = lambda cfg, query, maximum, bounds: ({"reason": "联网搜索超时，请稍后重试。"} if query == "fail" else
            {"results": [self.result("https://example.invalid/article?utm_source=test", published_date=None)]})
        fetch.return_value = {"reason": "页面要求登录、限制访问或触发验证，已保留搜索摘要。"}
        result = provider.search_web(["okay", "fail"], {"time_window": "近30天"}, cfg=self.cfg)
        self.assertEqual(result["status"], "partial")
        self.assertIsNotNone(result["searched_at"])
        self.assertEqual(result["results"][0]["content_kind"], "search_snippet")
        self.assertIsNone(result["results"][0]["published_date"])
        self.assertEqual(result["results"][0]["date_basis"], "unknown")
        self.assertIsNone(result["results"][0]["fetched_at"])
        self.assertEqual({item["stage"] for item in result["failures"]}, {"search", "fetch"})
        self.assertEqual(stat.S_IMODE(self.log_path.stat().st_mode), 0o600)
        self.assertNotIn(self.cfg.api_key, self.log_path.read_text())
        self.assertNotIn("utm_source", self.log_path.read_text())

    @patch("web_search.provider.fetch_page")
    @patch("web_search.provider._search_once")
    def test_page_fetch_bound_dates_and_provenance(self, search, fetch):
        search.return_value = {"results": [self.result(f"https://example.invalid/{i}", published_date=None) for i in range(6)]}
        fetch.return_value = {"content": "Extracted page content. " * 20, "title": "Page title"}
        result = provider.search_web(["query"], {"time_window": "近1年"}, cfg=self.cfg)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(sum(item["content_kind"] == "full_text" for item in result["results"]), 3)
        self.assertTrue(all(item["published_date"] is None for item in result["results"]))
        self.assertTrue(all(item["fetched_at"] for item in result["results"][:3]))
        self.assertTrue(all(item["fetched_at"] is None for item in result["results"][3:]))

    @patch("web_search.provider._search_once")
    def test_outside_window_excluded_unknown_dates_retained(self, search):
        old = (date.today() - timedelta(days=100)).isoformat()
        search.return_value = {"results": [self.result("https://example.invalid/old", published_date=old),
                                             self.result("https://example.invalid/unknown", published_date=None)]}
        result = provider.search_web(["query"], {"time_window": "近30天", "fetch_pages": False}, cfg=self.cfg)
        self.assertEqual([item["url"] for item in result["results"]], ["https://example.invalid/unknown"])
        self.assertEqual(result["failures"][0]["stage"], "date_filter")

    @patch("requests.Session")
    def test_transport_errors_are_sanitized_and_never_update_timestamp(self, session_type):
        session = session_type.return_value.__enter__.return_value
        for failure in (requests.Timeout("test-tavily-secret"), requests.ConnectionError("test-tavily-secret")):
            session.post.side_effect = failure
            result = provider.search_web(["query"], {"time_window": "近30天"}, cfg=self.cfg)
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["searched_at"])
            self.assertNotIn(self.cfg.api_key, json.dumps(result))
        session.post.side_effect = None
        for status, data in ((401, {"error": self.cfg.api_key}), (200, {"results": None})):
            session.post.return_value = response(status=status, data=data)
            result = provider.search_web(["query"], {"time_window": "近30天"}, cfg=self.cfg)
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["searched_at"])
            self.assertNotIn(self.cfg.api_key, json.dumps(result))

    @patch("requests.Session")
    def test_robots_disallow_prevents_page_access(self, session_type):
        session = session_type.return_value.__enter__.return_value
        session.get.return_value = response(body=b"User-agent: *\nDisallow: /\n", content_type="text/plain")
        result = intake.fetch_page("https://example.invalid/private")
        self.assertIn("robots", result["reason"])
        self.assertEqual(session.get.call_count, 1)
        self.assertFalse(session.trust_env)
        self.assertNotIn("Authorization", session.get.call_args.kwargs["headers"])

    @patch("requests.Session")
    def test_login_challenge_and_redirect_skip_without_credentials(self, session_type):
        session = session_type.return_value.__enter__.return_value
        for page in (response(body=b"<html>Verify you are human</html>"), response(status=302)):
            session.get.reset_mock()
            session.get.side_effect = [response(status=404), page]
            result = intake.fetch_page("https://example.invalid/article")
            self.assertIn("搜索摘要", result["reason"])
            self.assertNotIn("content", result)
            for call in session.get.call_args_list:
                self.assertFalse(call.kwargs["allow_redirects"])
                self.assertNotIn("Authorization", call.kwargs["headers"])

    def test_private_and_credential_urls_are_not_fetched(self):
        for url in ("http://localhost/a", "http://127.0.0.1/a", "http://169.254.169.254/latest", "https://user:secret@example.com/", "https://example.com/?api_key=secret"):
            self.assertFalse(intake.public_url(url))
            self.assertFalse(intake.safe_failure_url(url))

    def test_settings_ui_test_save_restart_clear_without_key_echo(self):
        from streamlit.testing.v1 import AppTest
        script = "from web_search.ui_settings import render_search_settings\nrender_search_settings()"
        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        app.text_input(key="search_key_input").set_value("test-tavily-ui-secret")
        with patch("web_search.provider._search_once", return_value={"results": []}) as search:
            app.button(key="search_test").click().run()
            self.assertEqual(search.call_count, 1)
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key="search_key_input").value, "")
        self.assertFalse(self.config_path.exists())
        app.button(key="search_save").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(provider.load_config().api_key, "test-tavily-ui-secret")
        restarted = AppTest.from_string(script).run()
        self.assertFalse(restarted.exception)
        self.assertEqual(restarted.text_input(key="search_key_input").value, "")
        self.assertNotIn("test-tavily-ui-secret", str([item.value for item in restarted.caption]))
        restarted.button(key="search_clear").click().run()
        self.assertFalse(restarted.exception)
        self.assertFalse(provider.load_config().configured)


if __name__ == "__main__":
    unittest.main()
