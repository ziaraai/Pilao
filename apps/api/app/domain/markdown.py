"""The small Markdown subset of the chapters (same rules as apps/web/lib/markdown.ts).

Titles, paragraphs, bullet and numbered lists, pipe tables, bold, italics, and the
``[À COMPLÉTER : …]`` markers as their own run, so an export can highlight them.
"""

import re
from dataclasses import dataclass
from typing import Literal

RunKind = Literal["text", "strong", "em", "todo"]

TODO = re.compile(r"\[\s*À\s+COMPLÉTER\s*:\s*([^\]]+)\]", re.IGNORECASE)
# "_" only around words, as in CommonMark: 12_000_ or file_name stay as they are.
_EMPHASIS = re.compile(
    r"\*\*(.+?)\*\*|(?<![^\W_])__(.+?)__(?![^\W_])|\*(?!\s)(.+?)\*|(?<![^\W_])_(?!\s)(.+?)_(?![^\W_])"
)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


@dataclass(frozen=True)
class Run:
    kind: RunKind
    text: str


@dataclass(frozen=True)
class Heading:
    level: int
    runs: list[Run]


@dataclass(frozen=True)
class Paragraph:
    runs: list[Run]


@dataclass(frozen=True)
class ListBlock:
    ordered: bool
    items: list[list[Run]]


@dataclass(frozen=True)
class Table:
    head: list[list[Run]]
    rows: list[list[list[Run]]]


Block = Heading | Paragraph | ListBlock | Table


def _emphasis(text: str) -> list[Run]:
    out: list[Run] = []
    last = 0
    for m in _EMPHASIS.finditer(text):
        if m.start() > last:
            out.append(Run("text", text[last : m.start()]))
        strong = m.group(1) or m.group(2)
        out.append(Run("strong", strong) if strong else Run("em", m.group(3) or m.group(4)))
        last = m.end()
    if last < len(text):
        out.append(Run("text", text[last:]))
    return out


def inline(text: str) -> list[Run]:
    out: list[Run] = []
    last = 0
    for m in TODO.finditer(text):
        if m.start() > last:
            out += _emphasis(text[last : m.start()])
        out.append(Run("todo", m.group(1).strip()))
        last = m.end()
    if last < len(text):
        out += _emphasis(text[last:])
    return out


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().removeprefix("|").removesuffix("|").split("|")]


def parse(markdown: str) -> list[Block]:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Paragraph(inline(" ".join(paragraph))))
            paragraph.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        heading = _HEADING.match(line)
        if not line.strip():
            flush()
        elif heading:
            flush()
            blocks.append(Heading(len(heading.group(1)), inline(heading.group(2).strip())))
        elif (
            line.strip().startswith("|") and i + 1 < len(lines) and _TABLE_RULE.match(lines[i + 1])
        ):
            flush()
            head = [inline(c) for c in _cells(line)]
            rows: list[list[list[Run]]] = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([inline(c) for c in _cells(lines[i])])
                i += 1
            blocks.append(Table(head, rows))
            continue
        elif _BULLET.match(line) or _NUMBERED.match(line):
            flush()
            ordered = not _BULLET.match(line)
            pattern = _NUMBERED if ordered else _BULLET
            items: list[list[Run]] = []
            while i < len(lines) and (m := pattern.match(lines[i])):
                items.append(inline(m.group(1)))
                i += 1
            blocks.append(ListBlock(ordered, items))
            continue
        else:
            paragraph.append(line.strip())
        i += 1
    flush()
    return blocks
