"""Structure-aware chunking: split on markdown headings first, then pack paragraphs.

Each chunk keeps its heading path and is embedded with a contextual header
("Doc title | Section > Subsection") so a chunk such as "It costs $99" still carries
the information that it is about the Pro plan.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .text import split_sentences

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass
class Chunk:
    id: str
    doc_id: str
    source: str
    title: str
    heading: str
    text: str
    flagged: bool = False  # quarantined by the ingestion-time injection scan
    flags: list[str] = field(default_factory=list)

    @property
    def embed_text(self) -> str:
        return f"{self.title} | {self.heading}\n{self.text}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Chunk":
        return cls(**d)


def _pack(paragraphs: list[str], max_chars: int) -> list[str]:
    pieces: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > max_chars:  # oversized paragraph: window over sentences with 1-sentence overlap
            sents = split_sentences(para)
            window: list[str] = []
            for s in sents:
                if window and len(" ".join(window + [s])) > max_chars:
                    pieces.append(" ".join(window))
                    window = window[-1:]
                window.append(s)
            if window:
                pieces.append(" ".join(window))
            continue
        if buf and len(buf) + len(para) + 1 > max_chars:
            pieces.append(buf)
            buf = ""
        buf = f"{buf}\n{para}".strip()
    if buf:
        pieces.append(buf)
    return pieces


def chunk_markdown(source: str, text: str, max_chars: int = 700) -> list[Chunk]:
    doc_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", source.rsplit(".", 1)[0]).strip("-").lower() or "doc"
    title = source
    stack: list[tuple[int, str]] = []
    sections: list[tuple[str, list[str]]] = []
    current: list[str] = []

    def flush() -> None:
        heading = " > ".join(h for lvl, h in stack if not (lvl == 1)) or title
        if any(line.strip() for line in current):
            sections.append((heading, list(current)))
        current.clear()

    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            flush()
            level, name = len(m.group(1)), m.group(2).strip()
            if level == 1 and title == source:
                title = name
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, name))
        else:
            current.append(line)
    flush()

    chunks: list[Chunk] = []
    n = 0
    for heading, lines in sections:
        paragraphs = [p.strip() for p in "\n".join(lines).split("\n\n") if p.strip()]
        for piece in _pack(paragraphs, max_chars):
            chunks.append(Chunk(id=f"{doc_id}-{n:03d}", doc_id=doc_id, source=source,
                                title=title, heading=heading, text=piece))
            n += 1
    return chunks
