"""EngEduScope｜Markdown 读写（M2）。

- Block：解析 / 抓取的统一中间结构（heading / paragraph / list / table），可带页码。
- blocks_to_markdown：生成正文；页码变化处插入 `<!-- page: N -->` 注释（渲染不可见，保留可追溯性）。
- markdown_to_blocks：把 Markdown（trafilatura 输出、人工笔记）解析回 blocks。
- front_matter / write_markdown：轻量 YAML front matter（不依赖 PyYAML；字符串统一加引号）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from knowledge.textutil import join_wrapped_lines


@dataclass
class Block:
    kind: str                     # heading / paragraph / list / table
    text: str                     # list：每行一个条目；table：每行一条记录（"a | b | c"）
    level: int = 0                # heading 级别 1–6（0 表示未知，输出时按 2 级）
    page: Optional[int] = None    # 来自 PDF 时的页码


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+(.*\S)\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.S)


def markdown_to_blocks(markdown: str, page: Optional[int] = None) -> List[Block]:
    """Markdown → blocks。连续列表项合并为一个 list block，连续表格行合并为一个 table block。"""
    blocks: List[Block] = []
    para: List[str] = []

    def flush():
        if para:
            text = join_wrapped_lines(para)
            if text:
                blocks.append(Block("paragraph", text, page=page))
            para.clear()

    text = _FRONT_MATTER_RE.sub("", markdown or "", count=1)
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped.startswith("<!--"):
            continue
        m = _HEADING_RE.match(stripped)
        if m:
            flush()
            blocks.append(Block("heading", m.group(2).strip("# ").strip(), level=len(m.group(1)), page=page))
            continue
        if stripped.startswith("|"):
            flush()
            if _TABLE_SEP_RE.match(stripped):
                continue
            row = " | ".join(cell.strip() for cell in stripped.strip("|").split("|"))
            if blocks and blocks[-1].kind == "table":
                blocks[-1].text += "\n" + row
            else:
                blocks.append(Block("table", row, page=page))
            continue
        m = _LIST_RE.match(stripped)
        if m:
            flush()
            item = m.group(1).strip()
            if blocks and blocks[-1].kind == "list":
                blocks[-1].text += "\n" + item
            else:
                blocks.append(Block("list", item, page=page))
            continue
        para.append(stripped)
    flush()
    return blocks


def blocks_to_markdown(blocks: Iterable[Block]) -> str:
    parts: List[str] = []
    last_page: Optional[int] = None
    for b in blocks:
        if b.page is not None and b.page != last_page:
            parts.append(f"<!-- page: {b.page} -->")
            last_page = b.page
        text = (b.text or "").strip()
        if not text:
            continue
        if b.kind == "heading":
            level = b.level if 1 <= b.level <= 6 else 2
            parts.append("#" * level + " " + text.replace("\n", " "))
        elif b.kind == "list":
            parts.append("\n".join("- " + item.strip() for item in text.splitlines() if item.strip()))
        elif b.kind == "table":
            rows = [r for r in text.splitlines() if r.strip()]
            lines = []
            for i, row in enumerate(rows):
                cells = [c.strip() for c in row.split(" | ")]
                lines.append("| " + " | ".join(cells) + " |")
                if i == 0:
                    lines.append("|" + " --- |" * len(cells))
            parts.append("\n".join(lines))
        else:
            parts.append(text)
    return "\n\n".join(parts).strip() + "\n"


def plain_text(blocks: Iterable[Block]) -> str:
    """用于标签规则与统计的纯文本（标题 + 正文）。"""
    return "\n".join((b.text or "") for b in blocks)


def _yaml_scalar(value) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{text}"'


def front_matter(meta: dict) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, (list, tuple)):
            lines.append(f"{key}: [{', '.join(_yaml_scalar(v) for v in value)}]")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def write_markdown(path: Path, meta: dict, body: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(front_matter(meta) + body, encoding="utf-8")
