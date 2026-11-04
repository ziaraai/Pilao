"""Split extracted blocks into overlapping chunks that keep their page range and heading.

Target 500-800 tokens (≈ 650), overlap ≈ 12 %, as specified in docs/08-pipeline-ia.md.
There is no tokenizer dependency: French averages about 3.8 characters per token.
"""

import re
from dataclasses import dataclass

from app.documents.extract import Block

CHARS_PER_TOKEN = 3.8
TARGET_TOKENS = 650
MAX_TOKENS = 800
OVERLAP_RATIO = 0.12

_MAX_CHARS = int(MAX_TOKENS * CHARS_PER_TOKEN)
_TARGET_CHARS = int(TARGET_TOKENS * CHARS_PER_TOKEN)
_OVERLAP_CHARS = int(_TARGET_CHARS * OVERLAP_RATIO)


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


@dataclass(frozen=True)
class Chunk:
    content: str
    page_from: int | None
    page_to: int | None
    heading: str | None
    tokens: int


def _split_long(text: str) -> list[str]:
    """Cut an oversized paragraph on sentence ends, then on words as a last resort."""
    if len(text) <= _MAX_CHARS:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[\.\!\?;:])\s+", text):
        while len(sentence) > _MAX_CHARS:  # no punctuation at all: cut on a space
            cut = sentence.rfind(" ", 0, _TARGET_CHARS) or _TARGET_CHARS
            cut = cut if cut > 0 else _TARGET_CHARS
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + len(sentence) + 1 > _TARGET_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def _tail(text: str) -> str:
    """Last ~overlap characters of ``text``, starting on a word boundary."""
    if len(text) <= _OVERLAP_CHARS:
        return text
    tail = text[-_OVERLAP_CHARS:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def chunk_blocks(blocks: list[Block]) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading: str | None = None
    parts: list[str] = []
    pages: list[int] = []
    chunk_heading: str | None = None
    carried = ""  # overlap text carried over from the previous chunk of the same section

    def flush(keep_overlap: bool) -> None:
        nonlocal parts, pages, carried
        if not parts:
            return
        content = "\n\n".join(parts).strip()
        if content and content != carried:
            known = [p for p in pages if p is not None]
            chunks.append(
                Chunk(
                    content=content,
                    page_from=min(known) if known else None,
                    page_to=max(known) if known else None,
                    heading=chunk_heading,
                    tokens=estimate_tokens(content),
                )
            )
        carried = _tail(content) if keep_overlap else ""
        parts, pages = ([carried] if carried else []), []

    for block in blocks:
        if block.kind == "heading":
            flush(keep_overlap=False)  # a new section never inherits the previous text
            heading = block.text
            chunk_heading = heading
            parts, pages = [], []
            continue
        for piece in _split_long(block.text):
            size = sum(len(p) for p in parts) + len(piece)
            if parts and size > _TARGET_CHARS:
                flush(keep_overlap=True)
                chunk_heading = heading
            if not parts:
                chunk_heading = heading
            parts.append(piece)
            pages.append(block.page)  # type: ignore[arg-type]
    flush(keep_overlap=False)
    return chunks
