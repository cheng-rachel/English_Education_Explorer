"""Content-role migration/backfill checks; every database and Markdown is temporary."""
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))

from knowledge import kb_db
from knowledge.content_roles import CONTENT_ROLES, classify_content_role, infer_doc_role
from knowledge.markdown_writer import write_markdown
from knowledge.pipeline import build_knowledge_base
from knowledge.retrieval import get_retriever
from knowledge.textutil import tokenize


BODY = "第一步，让孩子观察英语故事图片。先示范一个问题，再让孩子选择答案。每天安排五分钟，读后提问并复述故事。"


def body_bytes(path):
    return re.sub(rb"\A---\r?\n.*?\r?\n---\r?\n", b"", path.read_bytes(), count=1, flags=re.S)


class ContentRoleChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="need-content-role-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.raw = self.base / "raw"
        self.knowledge = self.base / "knowledge"
        self.raw.mkdir()
        self.knowledge.mkdir()
        environment = patch.dict(os.environ, {"ENGEDUSCOPE_DB_PATH": str(self.base / "old.db"),
                                              "ENGEDUSCOPE_RAW_ROOT": str(self.raw),
                                              "ENGEDUSCOPE_KNOWLEDGE_ROOT": str(self.knowledge)})
        environment.start()
        self.addCleanup(environment.stop)

    def old_database(self):
        connection = kb_db.connect()
        for statement in kb_db._SCHEMA:
            statement = statement.replace("        content_role        TEXT,\n", "")
            statement = statement.replace(",\n        content_role  TEXT", "")
            connection.execute(statement)
        connection.execute("CREATE TABLE research_sessions (id INTEGER, summary_json TEXT)")
        connection.execute("INSERT INTO research_sessions VALUES (1, ?)", ('{"saved":"preserve"}',))
        connection.commit()
        connection.close()

    def legacy_doc(self, identifier="doc", category="learnpath", markdown="03learnpath/reference.md", text=BODY):
        connection = kb_db.connect()
        connection.execute("INSERT INTO knowledge_documents (document_id,title,region,source_kind,source_type,raw_category,"
                           "parse_status,markdown_path,ingested_at,chunk_count,content_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (identifier, "英语参考资料", "general_reference" if category == "learnpath" else "中国大陆",
                            "md", "通用学习路径参考资料" if category == "learnpath" else "行业报告", category,
                            "success", markdown, "2026-01-01T00:00:00", 1, "unchanged-input-hash"))
        connection.execute("INSERT INTO knowledge_chunks (chunk_id,document_id,chunk_index,section_title,chunk_text,chunk_tokens) "
                           "VALUES (?,?,?,?,?,?)", (identifier + "-0000", identifier, 0, "英语练习", text, " ".join(tokenize(text))))
        connection.commit()
        connection.close()

    def test_eight_roles_are_conservative_and_chunk_rules_can_refine_document_scope(self):
        examples = {
            "learning_path": "儿童英语学习路径，从音素意识到解码，再到篇章理解。",
            "practice_guide": BODY,
            "research_evidence": "研究结果来自对照组与实验组，报告了英语阅读效应量。",
            "parent_experience": "我家孩子学英语，试过复述故事但仍需要提示。",
            "product_info": "该英语产品功能包括语音播放，提供免费试用和订阅价格。",
            "policy_background": "教育部印发义务教育课程标准，要求依法开展教学。",
            "market_signal": "英语教育市场规模与融资情况发生变化。",
            "general_reference": "这是一份英语资料目录和相关名词介绍。",
        }
        self.assertEqual(set(examples), set(CONTENT_ROLES))
        for role, text in examples.items():
            with self.subTest(role=role):
                self.assertEqual(classify_content_role(text), role)
        self.assertEqual(infer_doc_role(raw_category="learnpath", text=BODY), "learning_path")
        self.assertEqual(classify_content_role(BODY, raw_category="learnpath"), "practice_guide")
        self.assertEqual(classify_content_role(BODY, raw_category="reports"), "practice_guide")
        self.assertEqual(classify_content_role("Our app helps children read aloud and improves reading comprehension.",
                                              raw_category="product_docs"), "product_info")
        self.assertEqual(infer_doc_role(raw_category="public_discussions", text="家长学习话题汇编。"), "market_signal")

    def test_old_schema_backfill_is_idempotent_and_preserves_text_raw_ids_fts_and_history(self):
        self.old_database()
        self.legacy_doc()
        self.legacy_doc("report", "reports", "01china/01reports/report.md", "英语市场规模与行业趋势分析。")
        source = self.raw / "untouched.md"
        source.write_text(BODY, encoding="utf-8")
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        paths = [self.knowledge / "03learnpath/reference.md", self.knowledge / "01china/01reports/report.md"]
        for path in paths:
            write_markdown(path, {"title": "原有标题", "custom_field": "保持 metadata"}, "\n中文正文。\n\n" + BODY + "\n")
        before_body = {path: body_bytes(path) for path in paths}
        connection = kb_db.connect()
        chunks_before = [tuple(row) for row in connection.execute("SELECT id,chunk_id,chunk_text,chunk_tokens FROM knowledge_chunks ORDER BY id")]
        ranking_before = [tuple(row) for row in connection.execute("SELECT rowid,bm25(knowledge_chunks_fts) FROM knowledge_chunks_fts WHERE knowledge_chunks_fts MATCH '英语' ORDER BY 2")]
        connection.close()
        result = kb_db.backfill_content_roles()
        self.assertEqual((result["documents_updated"], result["chunks_updated"], result["markdown_updated"]), (2, 2, 2))
        self.assertEqual({path: body_bytes(path) for path in paths}, before_body)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)
        self.assertTrue(all(b'content_role: "' in path.read_bytes() for path in paths))
        second = kb_db.backfill_content_roles()
        self.assertEqual((second["documents_updated"], second["chunks_updated"], second["markdown_updated"]), (0, 0, 0))
        self.assertEqual(second["markdown_unchanged"], 2)
        connection = kb_db.connect()
        self.assertEqual([tuple(row) for row in connection.execute("SELECT id,chunk_id,chunk_text,chunk_tokens FROM knowledge_chunks ORDER BY id")], chunks_before)
        self.assertEqual([tuple(row) for row in connection.execute("SELECT rowid,bm25(knowledge_chunks_fts) FROM knowledge_chunks_fts WHERE knowledge_chunks_fts MATCH '英语' ORDER BY 2")], ranking_before)
        self.assertEqual(connection.execute("SELECT summary_json FROM research_sessions").fetchone()[0], '{"saved":"preserve"}')
        self.assertTrue(all(row[0] == "2026-01-01T00:00:00" for row in connection.execute("SELECT ingested_at FROM knowledge_documents")))
        connection.close()

    def test_future_ingestion_and_retrieval_use_chunk_role_without_changing_document_role(self):
        source = self.raw / "03learnpath/guide.md"
        source.parent.mkdir()
        source.write_text("# 英语亲子活动\n\n" + BODY, encoding="utf-8")
        original = source.read_bytes()
        result = build_knowledge_base()
        self.assertEqual(result.succeeded, 1)
        document = kb_db.list_documents()[0]
        self.assertEqual(document["content_role"], "learning_path")
        path = self.knowledge / document["markdown_path"]
        self.assertIn('content_role: "learning_path"', path.read_text())
        hits = get_retriever().search("英语", {"content_role": ["practice_guide"]})
        self.assertTrue(hits)
        self.assertTrue(all(hit.content_role == "practice_guide" and hit.doc_content_role == "learning_path" for hit in hits))
        self.assertEqual(get_retriever().search("英语", {"content_role": "market_signal"}), [])
        self.assertEqual(source.read_bytes(), original)

    def test_retrieval_falls_back_to_valid_document_role_and_preserves_assigned_roles(self):
        self.old_database()
        self.legacy_doc()
        kb_db.init_schema()
        connection = kb_db.connect()
        connection.execute("UPDATE knowledge_documents SET content_role='research_evidence'")
        connection.commit()
        connection.close()
        hits = get_retriever().search("英语", {"content_role": "research_evidence"})
        self.assertTrue(hits)
        self.assertEqual(hits[0].content_role, "research_evidence")
        kb_db.backfill_content_roles()
        self.assertEqual(kb_db.list_documents()[0]["content_role"], "research_evidence")

    def test_backfill_never_follows_generated_paths_into_raw_or_outside_knowledge(self):
        self.old_database()
        raw = self.raw / "private.md"
        raw.write_text("---\ntitle: 原始资料\n---\n" + BODY, encoding="utf-8")
        original = raw.read_bytes()
        (self.knowledge / "link.md").symlink_to(raw)
        self.legacy_doc("traversal", markdown="../raw/private.md")
        self.legacy_doc("symlink", markdown="link.md")
        result = kb_db.backfill_content_roles()
        self.assertEqual(result["markdown_updated"], 0)
        self.assertEqual(result["markdown_skipped"], 2)
        self.assertEqual(raw.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
