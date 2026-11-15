"""Safety layer: PII redaction, prompt-injection detection, groundedness checking.

Used at four points: user input, document ingestion (quarantine poisoned chunks),
retrieved context, and the model output.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import content_terms, split_sentences

# ----------------------------------------------------------------------------- PII
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_KEY = re.compile(r"\b(?:sk|pk|api|key|token)[-_][A-Za-z0-9_\-]{16,}\b", re.I)
_PHONE = re.compile(r"(?<!\d)(?<!\d\.)(?:\+?\d{1,3}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}(?!\d)(?!\.\d)")


def _luhn(number: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    found: dict[str, int] = {}

    def sub(pattern: re.Pattern, label: str, s: str, check=None) -> str:
        def repl(m: re.Match) -> str:
            if check and not check(m.group(0)):
                return m.group(0)
            found[label] = found.get(label, 0) + 1
            return f"[{label}]"

        return pattern.sub(repl, s)

    text = sub(_EMAIL, "EMAIL", text)
    text = sub(_SSN, "SSN", text)
    text = sub(_KEY, "SECRET", text)
    text = sub(_CARD, "CARD", text, check=_luhn)
    text = sub(_PHONE, "PHONE", text)
    return text, found


# ----------------------------------------------------------------------------- injection
_INJECTION_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|other)\b.{0,30}"
                r"\b(instruction|prompt|rule|document|context)s?\b", re.I | re.S), 1.0, "override-instructions"),
    (re.compile(r"\b(reveal|print|show|output|repeat|leak)\b.{0,30}\b(system|hidden|initial|secret)\b.{0,15}\b(prompt|instruction|message)s?\b",
                re.I | re.S), 1.0, "prompt-exfiltration"),
    (re.compile(r"\byou are now\b|\bact as (?:an? )?(?:unrestricted|jailbroken|dan)\b|\bdeveloper mode\b|\bjailbreak\b", re.I), 0.8, "role-hijack"),
    (re.compile(r"\b(system notice|important system|new instructions?)\b\s*[:\-]", re.I), 0.6, "fake-system-message"),
    (re.compile(r"\byou must (?:tell|say|respond|answer|reply)\b", re.I), 0.5, "forced-output"),
    (re.compile(r"<\s*/?\s*(system|assistant|instructions?)\s*>", re.I), 0.7, "role-tags"),
]


@dataclass
class InjectionResult:
    score: float
    matches: list[str] = field(default_factory=list)
    blocked: bool = False


def detect_prompt_injection(text: str, threshold: float = 1.0) -> InjectionResult:
    score, matches = 0.0, []
    for pattern, weight, name in _INJECTION_PATTERNS:
        if pattern.search(text):
            score += weight
            matches.append(name)
    return InjectionResult(score=round(score, 2), matches=matches, blocked=score >= threshold)


# ----------------------------------------------------------------------------- groundedness
_CITE = re.compile(r"\[S(\d+)\]")


def extract_citations(answer: str) -> list[int]:
    return sorted({int(m) for m in _CITE.findall(answer)})


def groundedness(answer: str, contexts: list[str], support_threshold: float = 0.6) -> float:
    """Fraction of answer sentences whose content terms are mostly present in the retrieved context.

    A cheap, deterministic proxy for faithfulness. With a real LLM you can additionally run the
    LLM-as-judge in evaluation.py; this one is fast enough to run on every request.
    """
    context_terms: set[str] = set()
    for c in contexts:
        context_terms.update(content_terms(c))
    sentences = [s for s in split_sentences(_CITE.sub("", answer)) if content_terms(s)]
    if not sentences:
        return 0.0
    supported = 0
    for s in sentences:
        terms = content_terms(s)
        if sum(t in context_terms for t in terms) / len(terms) >= support_threshold:
            supported += 1
    return supported / len(sentences)
