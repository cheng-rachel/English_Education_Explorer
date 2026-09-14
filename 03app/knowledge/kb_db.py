"""EngEduScope｜知识库结构化存储（M2）。

复用 01data/02structured/eng_eduscope.db（标准库 sqlite3，无 ORM）：
- knowledge_documents：每个来源一行（PDF / DOCX / Markdown 笔记 / 网页），含关键 metadata 与解析状态
- knowledge_chunks：切分后的内容块，保留 section_title 与页码范围
- knowledge_chunks_fts：FTS5 外部内容表（索引分词后的 chunk_tokens），触发器自动同步
- knowledge_builds：每次构建的统计
CREATE IF NOT EXISTS，无迁移框架。
"""

from __future__ import annotations

import json
import sqlite3
import re
from pathlib import Path
import os
import tempfile
from typing import Dict, Iterable, List, Optional

from db import get_db_path, now_iso
from knowledge.content_roles import CONTENT_ROLES, classify_content_role, infer_doc_role

JSON_LIST_FIELDS = ("skills", "contexts", "carriers", "audiences", "topics")

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS knowledge_documents (
        document_id         TEXT PRIMARY KEY,
        title               TEXT,
        region              TEXT NOT NULL,
        source_kind         TEXT NOT NULL,             -- pdf / docx / md / web
        source_type         TEXT,
        raw_category        TEXT,                      -- reports / policies / research / product_docs
        content_role        TEXT,
        original_path       TEXT,                      -- 本地文件相对项目根的路径
        source_url          TEXT,                      -- 网页原始 URL
        registry_path       TEXT,                      -- 网页来源所在登记表
        page_title          TEXT,                      -- 抓取到的网页标题（登记表标题优先作为 title）
        date                TEXT,                      -- 登记表原值（如 2026.08.04 / 2025.12 / 2020）
        date_normalized     TEXT,                      -- YYYY / YYYY-MM / YYYY-MM-DD
        note                TEXT,
        education_relevance TEXT NOT NULL DEFAULT 'Unreviewed',
        language            TEXT,
        skills              TEXT NOT NULL DEFAULT '[]',
        contexts            TEXT NOT NULL DEFAULT '[]',
        carriers            TEXT NOT NULL DEFAULT '[]',
        audiences           TEXT NOT NULL DEFAULT '[]',
        topics              TEXT NOT NULL DEFAULT '[]',
        tagging_method      TEXT,
        parse_status        TEXT NOT NULL,             -- success / needs_ocr / parse_failed / fetch_failed
        error_message       TEXT,
        markdown_path       TEXT,
        content_hash        TEXT,
        page_count          INTEGER,
        char_count          INTEGER,
        chunk_count         INTEGER NOT NULL DEFAULT 0,
        first_ingested_at   TEXT,
        ingested_at         TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        chunk_id      TEXT NOT NULL UNIQUE,
        document_id   TEXT NOT NULL,
        chunk_index   INTEGER NOT NULL,
        section_title TEXT,
        chunk_text    TEXT NOT NULL,
        chunk_tokens  TEXT NOT NULL,
        page_start    INTEGER,
        page_end      INTEGER,
        char_count    INTEGER,
        content_role  TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc ON knowledge_chunks(document_id)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
        chunk_tokens,
        content='knowledge_chunks',
        content_rowid='id',
        tokenize='unicode61'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS knowledge_chunks_ai AFTER INSERT ON knowledge_chunks BEGIN
        INSERT INTO knowledge_chunks_fts(rowid, chunk_tokens) VALUES (new.id, new.chunk_tokens);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS knowledge_chunks_ad AFTER DELETE ON knowledge_chunks BEGIN
        INSERT INTO knowledge_chunks_fts(knowledge_chunks_fts, rowid, chunk_tokens)
        VALUES ('delete', old.id, old.chunk_tokens);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS knowledge_chunks_au AFTER UPDATE ON knowledge_chunks BEGIN
        INSERT INTO knowledge_chunks_fts(knowledge_chunks_fts, rowid, chunk_tokens)
        VALUES ('delete', old.id, old.chunk_tokens);
        INSERT INTO knowledge_chunks_fts(rowid, chunk_tokens) VALUES (new.id, new.chunk_tokens);
    END
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_builds (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        mode           TEXT NOT NULL,                  -- incremental / full
        started_at     TEXT NOT NULL,
        finished_at    TEXT,
        discovered     INTEGER NOT NULL DEFAULT 0,
        processed      INTEGER NOT NULL DEFAULT 0,
        skipped        INTEGER NOT NULL DEFAULT 0,
        succeeded      INTEGER NOT NULL DEFAULT 0,
        failed         INTEGER NOT NULL DEFAULT 0,
        needs_ocr      INTEGER NOT NULL DEFAULT 0,
        fetch_failed   INTEGER NOT NULL DEFAULT 0,
        parse_failed   INTEGER NOT NULL DEFAULT 0,
        removed        INTEGER NOT NULL DEFAULT 0,
        document_count INTEGER NOT NULL DEFAULT 0,
        chunk_count    INTEGER NOT NULL DEFAULT 0,
        log_path       TEXT
    )
    """,
]


def connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema() -> None:
    conn = connect()
    try:
        # Serialize the small additive migration when multiple local pages start.
        conn.execute("BEGIN IMMEDIATE")
        for statement in _SCHEMA:
            conn.execute(statement)
        for table in ("knowledge_documents", "knowledge_chunks"):
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "content_role" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN content_role TEXT")
        conn.commit()
    finally:
        conn.close()


def _encode(doc: dict) -> dict:
    out = dict(doc)
    for key in JSON_LIST_FIELDS:
        value = out.get(key, [])
        out[key] = json.dumps(list(value or []), ensure_ascii=False)
    return out


def decode_document(row) -> dict:
    doc = dict(row)
    for key in JSON_LIST_FIELDS:
        try:
            doc[key] = json.loads(doc.get(key) or "[]")
        except (TypeError, ValueError):
            doc[key] = []
    return doc


_DOC_COLUMNS = [
    "document_id", "title", "region", "source_kind", "source_type", "raw_category", "content_role", "original_path",
    "source_url", "registry_path", "page_title", "date", "date_normalized", "note", "education_relevance",
    "language", "skills", "contexts", "carriers", "audiences", "topics", "tagging_method", "parse_status",
    "error_message", "markdown_path", "content_hash", "page_count", "char_count", "chunk_count",
    "first_ingested_at", "ingested_at",
]


def get_document(document_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM knowledge_documents WHERE document_id = ?", (document_id,)).fetchone()
        return decode_document(row) if row else None
    finally:
        if own:
            conn.close()


def upsert_document(doc: dict, conn: Optional[sqlite3.Connection] = None) -> None:
    """插入或整行更新；first_ingested_at 保留首次值。"""
    own = conn is None
    conn = conn or connect()
    try:
        existing = conn.execute(
            "SELECT first_ingested_at FROM knowledge_documents WHERE document_id = ?", (doc["document_id"],)
        ).fetchone()
        record = {col: None for col in _DOC_COLUMNS}
        record.update(_encode(doc))
        record["ingested_at"] = record.get("ingested_at") or now_iso()
        record["first_ingested_at"] = (existing["first_ingested_at"] if existing and existing["first_ingested_at"]
                                       else record.get("first_ingested_at") or record["ingested_at"])
        record["education_relevance"] = record.get("education_relevance") or "Unreviewed"
        record["chunk_count"] = record.get("chunk_count") or 0
        if record.get("content_role") not in CONTENT_ROLES:
            record["content_role"] = infer_doc_role(record.get("raw_category"), record.get("source_type"),
                                                     record.get("region"), record.get("title"))
        placeholders = ", ".join("?" for _ in _DOC_COLUMNS)
        conn.execute(
            f"INSERT OR REPLACE INTO knowledge_documents ({', '.join(_DOC_COLUMNS)}) VALUES ({placeholders})",
            [record[col] for col in _DOC_COLUMNS],
        )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def replace_chunks(document_id: str, chunks: Iterable[dict], conn: Optional[sqlite3.Connection] = None) -> int:
    """删除该文档旧 chunks 并写入新 chunks（FTS 由触发器同步）。返回写入数量。"""
    own = conn is None
    conn = conn or connect()
    try:
        document = get_document(document_id, conn) or {}
        conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
        count = 0
        for ch in chunks:
            conn.execute(
                "INSERT INTO knowledge_chunks (chunk_id, document_id, chunk_index, section_title, chunk_text, "
                "chunk_tokens, page_start, page_end, char_count, content_role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ch["chunk_id"], document_id, ch["chunk_index"], ch.get("section_title"), ch["chunk_text"],
                 ch["chunk_tokens"], ch.get("page_start"), ch.get("page_end"), len(ch["chunk_text"]),
                 ch.get("content_role") if ch.get("content_role") in CONTENT_ROLES else classify_content_role(
                     ch["chunk_text"], document.get("raw_category"), document.get("source_type"),
                     document.get("region"), ch.get("section_title") or document.get("title"))),
            )
            count += 1
        conn.execute("UPDATE knowledge_documents SET chunk_count = ? WHERE document_id = ?", (count, document_id))
        if own:
            conn.commit()
        return count
    finally:
        if own:
            conn.close()


def delete_document(document_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    """删除文档及其 chunks，返回被删文档（便于清理其 Markdown）。"""
    own = conn is None
    conn = conn or connect()
    try:
        doc = get_document(document_id, conn)
        conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM knowledge_documents WHERE document_id = ?", (document_id,))
        if own:
            conn.commit()
        return doc
    finally:
        if own:
            conn.close()


def all_document_ids(conn: Optional[sqlite3.Connection] = None) -> List[str]:
    own = conn is None
    conn = conn or connect()
    try:
        return [r["document_id"] for r in conn.execute("SELECT document_id FROM knowledge_documents")]
    finally:
        if own:
            conn.close()


def list_documents(filters: Optional[Dict] = None, limit: int = 500) -> List[dict]:
    """metadata 过滤（region / source_type / source_kind / raw_category / education_relevance / parse_status /
    skills / contexts / carriers / audiences）。"""
    where, params = build_document_filter(filters or {}, alias="d")
    conn = connect()
    try:
        sql = f"SELECT * FROM knowledge_documents d {where} ORDER BY d.region, d.raw_category, d.title LIMIT ?"
        rows = conn.execute(sql, params + [limit]).fetchall()
        return [decode_document(r) for r in rows]
    finally:
        conn.close()


def build_document_filter(filters: Dict, alias: str = "d"):
    clauses: List[str] = []
    params: List = []
    for column in ("region", "source_type", "source_kind", "raw_category", "content_role", "education_relevance", "parse_status"):
        value = filters.get(column)
        if value:
            if isinstance(value, (list, tuple, set)):
                clauses.append(f"{alias}.{column} IN ({', '.join('?' for _ in value)})")
                params.extend(value)
            else:
                clauses.append(f"{alias}.{column} = ?")
                params.append(value)
    for column in JSON_LIST_FIELDS:
        labels = filters.get(column)
        if labels:
            if isinstance(labels, str):
                labels = [labels]
            sub = []
            for label in labels:
                sub.append(f"{alias}.{column} LIKE ?")
                params.append(f'%{json.dumps(label, ensure_ascii=False)}%')
            clauses.append("(" + " OR ".join(sub) + ")")
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_failures() -> List[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM knowledge_documents WHERE parse_status != 'success' ORDER BY parse_status, region, title"
        ).fetchall()
        return [decode_document(r) for r in rows]
    finally:
        conn.close()


def stats() -> dict:
    conn = connect()
    try:
        out = {"documents": 0, "chunks": 0, "by_status": {}, "by_kind": {}, "by_region": {}, "by_relevance": {}}
        out["documents"] = conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]
        out["chunks"] = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
        for key, column in (("by_status", "parse_status"), ("by_kind", "source_kind"),
                            ("by_region", "region"), ("by_relevance", "education_relevance")):
            for row in conn.execute(f"SELECT {column} AS k, COUNT(*) AS n FROM knowledge_documents GROUP BY {column}"):
                out[key][row["k"]] = row["n"]
        out["last_build"] = last_build(conn)
        return out
    finally:
        conn.close()


def last_build(conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT * FROM knowledge_builds ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        if own:
            conn.close()


def record_build(summary: dict) -> int:
    conn = connect()
    try:
        columns = ["mode", "started_at", "finished_at", "discovered", "processed", "skipped", "succeeded", "failed",
                   "needs_ocr", "fetch_failed", "parse_failed", "removed", "document_count", "chunk_count", "log_path"]
        cur = conn.execute(
            f"INSERT INTO knowledge_builds ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            [summary.get(c) for c in columns],
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def distinct_values(column: str) -> List[str]:
    if column not in ("region", "source_type", "source_kind", "raw_category", "content_role", "education_relevance", "parse_status"):
        raise ValueError(column)
    conn = connect()
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {column} AS v FROM knowledge_documents WHERE {column} IS NOT NULL AND {column} != '' ORDER BY v"
        ).fetchall()
        return [r["v"] for r in rows]
    finally:
        conn.close()


def _write_role_frontmatter(relative_path: str, role: str) -> str:
    """Amend one generated metadata field while preserving every body byte."""
    from knowledge.paths import knowledge_root, raw_root

    try:
        root = knowledge_root().resolve()
        raw = raw_root().resolve()
        path = (root / relative_path).resolve()
        if root not in path.parents or path == raw or raw in path.parents or not path.is_file():
            return "skipped"
        data = path.read_bytes()
        match = re.match(rb"\A---[ \t]*(\r?\n)(.*?)(^---[ \t]*\r?$)", data, re.M | re.S)
        if not match:
            return "skipped"
        newline, header = match.group(1), match.group(2)
        field = b'content_role: "' + role.encode("ascii") + b'"' + newline
        pattern = rb"^content_role:[^\r\n]*(?:\r?\n|$)"
        assigned = list(re.finditer(pattern, header, re.M))
        if len(assigned) == 1 and assigned[0].group(0).strip() == field.strip():
            return "unchanged"
        updated_header = re.sub(pattern, b"", header, flags=re.M) + field
        updated = data[:match.start(2)] + updated_header + data[match.end(2):]
        if data == updated:
            return "unchanged"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix=".content-role-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(updated)
            os.chmod(temporary, path.stat().st_mode & 0o777)
            os.replace(str(temporary), str(path))
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return "updated"
    except (OSError, ValueError, RuntimeError):
        return "skipped"


def backfill_content_roles() -> dict:
    """Idempotently fill missing roles from existing chunks; never fetch or edit raw.

    Valid assigned roles are retained. Only successful generated Markdown receives
    a frontmatter field; source text, chunk tokens, IDs and ingestion dates remain.
    """
    init_schema()
    result = {"documents_updated": 0, "chunks_updated": 0,
              "markdown_updated": 0, "markdown_unchanged": 0, "markdown_skipped": 0}
    conn = connect()
    documents = []
    try:
        for row in conn.execute("SELECT * FROM knowledge_documents ORDER BY document_id").fetchall():
            doc = dict(row)
            chunks = conn.execute("SELECT id, content_role, chunk_text, section_title FROM knowledge_chunks "
                                  "WHERE document_id = ? ORDER BY chunk_index", (doc["document_id"],)).fetchall()
            role = doc.get("content_role")
            if role not in CONTENT_ROLES:
                role = infer_doc_role(doc.get("raw_category"), doc.get("source_type"), doc.get("region"),
                                      doc.get("title"), "\n".join(chunk["chunk_text"] for chunk in chunks))
                conn.execute("UPDATE knowledge_documents SET content_role = ? WHERE document_id = ?",
                             (role, doc["document_id"]))
                result["documents_updated"] += 1
            for chunk in chunks:
                if chunk["content_role"] in CONTENT_ROLES:
                    continue
                chunk_role = classify_content_role(chunk["chunk_text"], doc.get("raw_category"),
                                                   doc.get("source_type"), doc.get("region"),
                                                   chunk["section_title"] or doc.get("title"))
                conn.execute("UPDATE knowledge_chunks SET content_role = ? WHERE id = ?", (chunk_role, chunk["id"]))
                result["chunks_updated"] += 1
            if doc.get("parse_status") == "success" and doc.get("markdown_path"):
                documents.append((doc["markdown_path"], role))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    for relative_path, role in documents:
        state = _write_role_frontmatter(relative_path, role)
        result["markdown_" + state] += 1
    return result
