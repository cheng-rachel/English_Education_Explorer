"""Focused local learning-sheet intake checks; fixtures never touch user raw files."""
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03app"))

from db import init_db
from knowledge import kb_db
from knowledge.parsers import _spreadsheet_blocks, parse_spreadsheet_file
from knowledge.pipeline import _Builder, discover
from knowledge.retrieval import get_retriever


def workbook(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    book.active.title = "能力发展"
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()


class LearningSpreadsheetChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="learnpath-sheet-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.raw = self.base / "raw"
        self.knowledge = self.base / "knowledge"
        env = patch.dict(os.environ, {
            "ENGEDUSCOPE_RAW_ROOT": str(self.raw),
            "ENGEDUSCOPE_KNOWLEDGE_ROOT": str(self.knowledge),
            "ENGEDUSCOPE_DB_PATH": str(self.base / "test.db"),
        })
        env.start()
        self.addCleanup(env.stop)

    def sheet(self):
        path = self.raw / "03learnpath" / "reading.xlsx"
        workbook(path, [["儿童英语分级阅读发展路径"],
                        ["年龄", "能力", "学习材料"],
                        ["6–8岁", "字母解码与句意理解", "RAZ 分级阅读短句"],
                        ["9–12岁", "英语阅读理解与故事推断", "分级阅读桥梁书"]])
        return path

    def test_headers_and_read_only_xlsx(self):
        path = self.sheet()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        parsed = parse_spreadsheet_file(path)
        self.assertEqual(parsed.status, "success")
        self.assertEqual(parsed.title, "儿童英语分级阅读发展路径")
        text = "\n".join(block.text for block in parsed.blocks)
        self.assertIn("年龄：9–12岁；能力：英语阅读理解与故事推断", text)
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_title_and_blank_cells_do_not_invent_values(self):
        blocks = _spreadsheet_blocks("分级", [["英语阅读路径", "英语阅读路径"],
                                             ["阶段", "阅读能力"], ["初级", "解码"], ["", "句子理解"]])
        paragraphs = [block.text for block in blocks if block.kind == "paragraph"]
        self.assertEqual(paragraphs, ["阶段：初级；阅读能力：解码。", "阅读能力：句子理解。"])

    def test_registry_is_not_local_content_and_other_categories_unchanged(self):
        self.sheet()
        registry = self.raw / "03learnpath" / "online_learnpath.xlsx"
        workbook(registry, [["title", "url", "source_type", "date", "note"],
                            ["阅读资料", "https://example.org/reading", "", "", ""]])
        workbook(self.raw / "01china" / "01reports" / "offline.xlsx", [["保持原有范围"]])
        items, unsupported, errors = discover()
        self.assertEqual((unsupported, errors), (1, 0))
        self.assertEqual([item.kind for item in items].count("spreadsheet"), 1)
        self.assertEqual([item.kind for item in items].count("web"), 1)
        self.assertFalse(any(item.path == registry for item in items))

    def test_existing_pipeline_indexes_sheet_and_skips_unchanged(self):
        path = self.sheet()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        init_db()
        kb_db.init_schema()
        item = discover()[0][0]
        builder = _Builder("incremental", None, io.StringIO())
        try:
            with patch("knowledge.pipeline.fetch_url", side_effect=AssertionError("local intake cannot fetch")):
                self.assertEqual(builder.process_local(item), "success")
                self.assertEqual(builder.process_local(item), "skipped")
            document = kb_db.get_document(item.document_id, builder.conn)
            self.assertEqual(document["raw_category"], "learnpath")
            self.assertEqual(document["region"], "general_reference")
            self.assertGreater(document["chunk_count"], 0)
            self.assertTrue((self.knowledge / document["markdown_path"]).is_file())
            results = get_retriever().search("英语 阅读理解 分级阅读", {"region": "general_reference"})
            self.assertTrue(any(row.document_id == item.document_id for row in results))
        finally:
            builder.close()
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
