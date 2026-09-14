"""EngEduScope｜本地 SQLite（M1 Step 4）。

- 仅使用 Python 标准库 sqlite3，无 ORM、无独立后端服务。
- 数据库文件：01data/02structured/eng_eduscope.db（永远不放在 03app/ 内）。
  可用环境变量 ENGEDUSCOPE_DB_PATH 覆盖（供测试使用临时库，不污染正式数据）。
- 初始化：文件不存在则创建；CREATE TABLE IF NOT EXISTS；无迁移框架。

说明：Python 模块名不能以数字开头，因此本文件不加数字前缀。
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from output_safety import sanitize_data, sanitize_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "01data" / "02structured" / "eng_eduscope.db"

STATUS_DEMO = "demo"

_CREATE_RESEARCH_SESSIONS = """
CREATE TABLE IF NOT EXISTS research_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    user_type    TEXT    NOT NULL,
    entry_type   TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'demo',
    summary_json TEXT    NOT NULL
)
"""


def get_db_path() -> Path:
    """运行时读取，便于测试通过环境变量切换到临时库。"""
    return Path(os.environ.get("ENGEDUSCOPE_DB_PATH", str(DEFAULT_DB_PATH)))


def _connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    """ISO 8601 本地时间，秒精度，不带时区：2026-09-13T09:20:00。"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(_CREATE_RESEARCH_SESSIONS)
        conn.commit()
    finally:
        conn.close()


def save_research_session(title: str, user_type: str, entry_type: str, summary: dict, status: str = STATUS_DEMO) -> int:
    """保存可恢复的研究；个人联系方式不进入用户可打开的 History。"""
    ts = now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO research_sessions "
            "(title, user_type, entry_type, created_at, updated_at, status, summary_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sanitize_text(title), sanitize_text(user_type), entry_type, ts, ts, status,
             json.dumps(sanitize_data(summary), ensure_ascii=False)),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_research_sessions() -> list:
    """全部记录，最新在前。"""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM research_sessions ORDER BY created_at DESC, id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_research_session(session_id: int) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_research_session(session_id: int) -> bool:
    """M1 无删除 UI，仅提供最小函数。"""
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
