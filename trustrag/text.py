"""Tiny, dependency-free NLP helpers shared by chunking, retrieval, guardrails and eval."""
from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an the of to in on for and or is are was were be been being do does did can could should
    would will may might must i you he she it we they me my your our their this that these those
    there here what which who whom whose when where why how many much long often any some all each
    per at by with from as if then than so such not no yes about into over under up down out off also
    just only own same too very s t get got have has had tell please explain describe give show let us
    offer provide""".split()
)

_TOKEN_RE = re.compile(r"\$?\d+(?:[.,]\d+)*%?|[a-z]+(?:[-'][a-z]+)*")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9$\"'(\[])")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def tokens(text: str) -> list[str]:
    return [t.lstrip("$").rstrip("%") for t in _TOKEN_RE.findall(text.lower())]


def stem(w: str) -> str:
    """Very light stemmer - enough to match plural/tense variants without extra dependencies."""
    if len(w) > 4 and w.endswith("ied"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


# Lightweight term normalisation (a tiny, domain-agnostic synonym table). It closes the most common
# vocabulary gaps between how users ask and how docs are written. For true semantic matching use
# real embeddings (EMBEDDINGS=st); this keeps the zero-dependency path usable.
_CANON = {
    "price": "cost", "pricing": "cost", "fee": "cost", "charge": "cost", "bill": "cost", "pay": "cost",
    "extra": "overage", "additional": "overage", "beyond": "overage", "exceed": "overage",
    "region": "residency", "location": "residency",
    "cancel": "cancellation", "money-back": "refund", "reimburse": "refund", "reimbursement": "refund",
    "downtime": "uptime", "outage": "uptime", "available": "uptime", "availability": "uptime",
    "login": "sso", "sign-on": "sso",
    "throttle": "ratelimit", "throttling": "ratelimit",
}


def content_terms(text: str) -> list[str]:
    out = []
    for t in tokens(text):
        if t and t not in STOPWORDS:
            s = stem(t)
            out.append(_CANON.get(s, s))
    return out


def clean_line(line: str) -> str:
    line = line.replace("**", "").replace("`", "").replace("|", " ")
    line = re.sub(r"^\s*#+\s*", "", line)
    return _BULLET.sub("", line).strip()


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        line = clean_line(line)
        if not line:
            continue
        out.extend(s.strip() for s in _SENT_SPLIT.split(line) if s.strip())
    return out


def bigrams(terms: list[str]) -> set[tuple[str, str]]:
    return set(zip(terms, terms[1:]))
