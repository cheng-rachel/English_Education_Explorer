"""Targeted personal-contact output boundary checks; no changes to raw files."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "03app"))

from output_safety import CONTACT_POLICY, HIDDEN, sanitize_data, sanitize_text, sanitize_url


FIXTURE = "微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com"
SECRETS = ("abc_teacher123", "13812345678", "teacher@example.com")


class ContactSafetyChecks(unittest.TestCase):
    def assertHidden(self, value, secrets=SECRETS):
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        for secret in secrets:
            self.assertNotIn(secret, text)

    def test_evidence_llm_chat_and_export_text_boundary(self):
        for output in (
            {"evidence_sources": [{"id": "E1", "title": "阅读资料", "snippet": FIXTURE}]},
            {"analysis": {"summary": "需要关注阅读迁移。" + FIXTURE}},
            {"chat": [{"role": "assistant", "content": FIXTURE}]},
            "# 工具方案\n\n## Evidence\n\n> " + FIXTURE,
        ):
            with self.subTest(output_type=type(output).__name__):
                self.assertHidden(sanitize_data(output))
        self.assertEqual(sanitize_text(FIXTURE), HIDDEN)

    def test_obfuscated_values_and_split_labels(self):
        samples = [
            "V X：abc_teacher123", "V信 abc_teacher123", "wechat ID: abc_teacher123",
            "微\u200b信：abc_teacher123", "微信：\nabc_teacher123", "微信\nabc_teacher123",
            "ＶＸ：ａｂｃ＿ｔｅａｃｈｅｒ１２３", "手机：+86 138-1234-5678",
            "1 3 8 1 2 3 4 5 6 7 8", "邮箱 teacher＠example．com",
            "teacher [at] example [dot] com", "邮箱 teacher%40example.com",
            "QQ：123456789", "小红书号：teacher123", "私信 @teacher123",
            "VX（abc_teacher123）", "微信搜索 abc_teacher123", "Phone: (415) 555-0123", "+1 (415) 555-0123",
            "扫描二维码咨询课程顾问", "请添加我获取学习资料。",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(sanitize_text(sample), HIDDEN)

    def test_official_website_and_general_teacher_profile_remain(self):
        text = (
            "可以了解 British Council 的学习资料。"
            "建议寻找有低龄英语互动教学经验、能组织开放式口语任务的教师。\n"
            "[官方学习网站](https://learnenglishkids.britishcouncil.org/)\n"
            "[Raz-Kids](https://www.raz-kids.com/)"
        )
        self.assertEqual(sanitize_text(text), text)
        for url in ("https://learnenglishkids.britishcouncil.org/", "https://www.raz-kids.com/", "https://www.duolingo.com/"):
            self.assertEqual(sanitize_url(url), url)
        safe = sanitize_data({"id": "E1", "url": "https://www.raz-kids.com/", "source_type": "公开用户讨论"})
        self.assertEqual(safe["id"], "E1")
        self.assertEqual(safe["source_type"], "公开用户讨论")
        self.assertEqual(safe["url"], "https://www.raz-kids.com/")

    def test_private_contact_links_and_profiles_hidden(self):
        urls = [
            "mailto:teacher@example.com", "tel:13812345678", "weixin://contacts/abc_teacher123",
            "https://wa.me/14155550123", "https://t.me/teacher123", "https://qm.qq.com/cgi-bin/qm/qr?k=x",
            "https://www.xiaohongshu.com/user/profile/teacher123", "https://www.douyin.com/user/teacher123",
            "https://x.com/teacher123", "https://www.instagram.com/teacher123/",
            "https://example.com/?email=teacher%40example.com", "https://example.com/?wechat=abc_teacher123",
            "https://example.com/微信abc_teacher123.pdf", "https://example.com/contact/abc_teacher123",
            "https://user:password@example.com/", "javascript:alert(1)",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(sanitize_url(url), "")
        public_discussion = "https://mp.weixin.qq.com/s/public-education-article"
        self.assertEqual(sanitize_url(public_discussion), public_discussion)

    def test_structured_fields_numeric_contacts_keys_and_original_unchanged(self):
        source = {
            "id": "S10", "age_range": [72, 107], "phone": 13812345678,
            "profile": {"mobile_number": "13812345678", "teacher_contact": "abc_teacher123", "ordinary": 13812345678},
            "teacher@example.com": "not a safe field name", "api_key": "fake-private-key",
            "source_path": "/raw/邮箱teacher@example.com.pdf", "chat": [{"content": FIXTURE}],
        }
        before = deepcopy(source)
        safe = sanitize_data(source)
        self.assertHidden(safe)
        self.assertNotIn("fake-private-key", json.dumps(safe))
        self.assertEqual(safe["id"], "S10")
        self.assertEqual(safe["age_range"], [72, 107])
        self.assertEqual(source, before)
        self.assertIsNot(source, safe)
        self.assertHidden(sanitize_data({"type": "微信", "value": "abc_teacher123"}))
        self.assertHidden(sanitize_data({"label": "email", "data": "teacher@example.com"}))

    def test_named_private_teacher_recommendation_is_not_kept(self):
        for text in ("建议联系王老师安排试听。", "推荐找李晓明老师。", "Try Teacher Alice for your next lesson."):
            self.assertEqual(sanitize_text(text), HIDDEN)
        self.assertIn("官方", sanitize_text("建议通过正式机构的官方服务入口寻找有阅读教学经验的教师。"))

    def test_uninspected_images_and_contact_html_are_omitted(self):
        examples = (
            "![二维码](https://example.com/qrcode.png)",
            '<img src="https://example.com/photo.png">',
            '<svg><text>13812345678</text></svg>',
            '<a href="mailto:teacher@example.com">老师</a>',
        )
        for text in examples:
            self.assertEqual(sanitize_text(text), HIDDEN)

    def test_safe_neighbouring_sentences_and_idempotence(self):
        value = {"id": "E1", "summary": "阅读需要反复练习。微信：abc_teacher123。可以使用分级阅读材料。"}
        safe = sanitize_data(value)
        self.assertEqual(safe["summary"], "阅读需要反复练习。可以使用分级阅读材料。")
        self.assertEqual(sanitize_data(safe), safe)
        self.assertIn("Do not output, recommend, reproduce, or expose", CONTACT_POLICY)

    def test_legacy_brand_updated_without_changing_engineering_paths(self):
        self.assertEqual(sanitize_text("EngEduScope｜英语教育需求与机会探索器"),
                         "English Education Explorer｜英探探：英语学习与教育探索器")
        self.assertEqual(sanitize_text("English Education Opportunity Explorer"), "English Education Explorer")
        self.assertEqual(sanitize_text("Welcome to EngEduScope."), "Welcome to English Education Explorer.")
        self.assertEqual(sanitize_text("使用EngEduScope的历史方案"), "使用English Education Explorer的历史方案")
        self.assertEqual(sanitize_text("/Users/demo/EngEduScope/03app/00_app.py"), "/Users/demo/EngEduScope/03app/00_app.py")
        self.assertEqual(sanitize_text("00_OPEN_ENGEDUSCOPE.command"), "00_OPEN_ENGEDUSCOPE.command")

    def test_markdown_contact_heading_and_wrapped_ocr_values(self):
        for text in ("**微信：**\nabc_teacher123", "> **VX：**\nabc_teacher123", "1381234\n5678",
                     "teacher\n@\nexample.com"):
            with self.subTest(text=text):
                self.assertEqual(sanitize_text(text), HIDDEN)

    def test_html_entities_cannot_split_email_detection(self):
        for text in ("teacher&#64;example.com", "邮箱 teacher&#x40;example.com", "teacher&commat;example.com"):
            self.assertEqual(sanitize_text(text), HIDDEN)
        self.assertEqual(sanitize_text("[产品官网](https://www.raz-kids.com/?a=1&amp;b=2)"),
                         "[产品官网](https://www.raz-kids.com/?a=1&amp;b=2)")

    def test_named_private_teacher_promotion_requires_no_contact_number(self):
        self.assertEqual(sanitize_text("王老师的口语辅导很适合你。"), HIDDEN)
        self.assertEqual(sanitize_text("建议寻找有阅读教学经验的老师。"), "建议寻找有阅读教学经验的老师。")


if __name__ == "__main__":
    unittest.main()
