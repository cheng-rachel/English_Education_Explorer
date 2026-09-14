"""EngEduScope｜内容切分（M2）。

原则：标题 → 小标题 → 自然段 的逻辑切分；只有段落过长时才按句子切；过短的尾块并入同一小节的前一块。
第一版不做 chunk 参数调优。
每个 chunk 保留 section_title（最近两级标题路径）与页码范围，便于回到原始 PDF / DOCX / URL。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from knowledge.markdown_writer import Block

TARGET_CHARS = 700     # 目标块长度（累积到此长度后开始新块）
MAX_CHARS = 1200       # 单段超过此长度才按句切
MIN_CHARS = 150        # 尾块短于此值时并入同小节前一块

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z])")


@dataclass
class Chunk:
    index: int
    section_title: str
    text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    @property
    def char_count(self) -> int:
        return len(self.text)


def split_long_text(text: str, max_chars: int = MAX_CHARS) -> List[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s and s.strip()]
    pieces: List[str] = []
    buf = ""
    for sent in sentences:
        sent = sent.strip()
        while len(sent) > max_chars:            # 单句仍超长：硬切
            if buf:
                pieces.append(buf)
                buf = ""
            pieces.append(sent[:max_chars])
            sent = sent[max_chars:]
        if buf and len(buf) + len(sent) + 1 > max_chars:
            pieces.append(buf)
            buf = sent
        elif not buf:
            buf = sent
        elif buf[-1:].isascii() and sent[:1].isascii():
            buf = buf + " " + sent          # 英文句子之间保留空格
        else:
            buf = buf + sent                # 中文句子直接相接
    if buf:
        pieces.append(buf)
    return pieces


def _section_label(stack: List[Tuple[int, str]], fallback: str) -> str:
    if not stack:
        return fallback
    return " › ".join(text for _, text in stack[-2:])


def chunk_blocks(blocks: Iterable[Block], fallback_title: str,
                 target: int = TARGET_CHARS, max_chars: int = MAX_CHARS, min_chars: int = MIN_CHARS) -> List[Chunk]:
    chunks: List[Chunk] = []
    stack: List[Tuple[int, str]] = []
    section = fallback_title or ""
    buf: List[str] = []
    buf_len = 0
    pages: List[Optional[int]] = []

    def flush():
        nonlocal buf, buf_len, pages
        if not buf:
            return
        text = "\n\n".join(buf).strip()
        found = [p for p in pages if p is not None]
        page_start = min(found) if found else None
        page_end = max(found) if found else None
        if (chunks and len(text) < min_chars and chunks[-1].section_title == section
                and len(chunks[-1].text) + len(text) + 2 <= max_chars):
            prev = chunks[-1]
            prev.text = prev.text + "\n\n" + text
            if page_end is not None:
                prev.page_end = page_end if prev.page_end is None else max(prev.page_end, page_end)
        else:
            chunks.append(Chunk(len(chunks), section, text, page_start, page_end))
        buf, buf_len, pages = [], 0, []

    for b in blocks:
        text = (b.text or "").strip()
        if b.kind == "heading":
            flush()
            if text:
                level = b.level if b.level > 0 else 3
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, text))
                section = _section_label(stack, fallback_title)
            continue
        if not text:
            continue
        if b.kind == "list":
            text = "\n".join("- " + item.strip() for item in text.splitlines() if item.strip())
        for piece in split_long_text(text, max_chars):
            if buf and buf_len + len(piece) > target:
                flush()
            buf.append(piece)
            buf_len += len(piece)
            pages.append(b.page)
    flush()
    return chunks
