"""LLM provider abstraction: Anthropic, OpenAI, or an offline extractive model (no API key needed)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .text import content_terms, split_sentences


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class BaseLLM:
    name = "base"
    model = "base"
    is_real = True
    aux_calls = True  # OK to spend extra LLM calls on planning / question rewriting

    def complete(self, system: str, prompt: str, max_tokens: int = 600, temperature: float = 0.0) -> LLMResponse:
        raise NotImplementedError


class AnthropicLLM(BaseLLM):
    name = "anthropic"

    def __init__(self, model: str):
        import anthropic  # pip install anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def complete(self, system, prompt, max_tokens=600, temperature=0.0) -> LLMResponse:
        r = self.client.messages.create(model=self.model, max_tokens=max_tokens, temperature=temperature,
                                        system=system, messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return LLMResponse(text, r.usage.input_tokens, r.usage.output_tokens, self.model)


class OpenAILLM(BaseLLM):
    name = "openai"

    def __init__(self, model: str):
        from openai import OpenAI  # pip install openai

        self.client = OpenAI()
        self.model = model

    def complete(self, system, prompt, max_tokens=600, temperature=0.0) -> LLMResponse:
        r = self.client.chat.completions.create(
            model=self.model, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        u = r.usage
        return LLMResponse(r.choices[0].message.content or "", u.prompt_tokens, u.completion_tokens, self.model)


class GroqLLM(BaseLLM):
    """Groq-hosted open models (fast, free tier) over Groq's OpenAI-compatible HTTP API - no SDK needed.

    Reads GROQ_API_KEY (and optionally GROQ_BASE_URL, used by the tests). Any failure raises, and the
    agent then falls back to the extractive answer, so a bad key / rate limit never breaks the chat.
    """

    name = "groq"
    aux_calls = False  # one call per question keeps the free tier's requests-per-minute budget healthy

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None):
        import os

        self.model = model
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.base_url = (base_url or os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")

    def complete(self, system, prompt, max_tokens=600, temperature=0.0) -> LLMResponse:
        import json
        import time
        import urllib.error
        import urllib.request

        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        payload: dict = {"model": self.model, "temperature": temperature,
                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if "gpt-oss" in self.model.lower():
            # Reasoning models spend part of the budget "thinking"; keep that short and the budget generous.
            payload["reasoning_effort"] = "low"
            payload["max_completion_tokens"] = max(max_tokens, 2000)
        else:
            payload["max_tokens"] = max_tokens
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", json.dumps(payload).encode(),
            {"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key, "User-Agent": "TrustRAG/1.0"})
        data = None
        for attempt in (0, 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:  # rate limited: wait briefly, retry once
                    try:
                        wait = float(e.headers.get("retry-after", "2"))
                    except (TypeError, ValueError):
                        wait = 2.0
                    time.sleep(min(wait, 5.0))
                    continue
                raise RuntimeError(f"Groq HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}") from None
        text = ((data or {}).get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not text:
            raise RuntimeError("Groq returned an empty answer")
        usage = data.get("usage", {})
        return LLMResponse(text, usage.get("prompt_tokens", estimate_tokens(prompt)),
                           usage.get("completion_tokens", estimate_tokens(text)), self.model)


class OllamaLLM(BaseLLM):
    """Local models through Ollama (https://ollama.com): free, private, no API key."""

    name = "ollama"
    aux_calls = False  # local models are slow: skip optional planner / rewrite calls

    PREFERRED = ("qwen2.5", "llama3", "mistral", "gemma", "phi", "qwen")
    SKIP = ("ocr", "embed", "vision", "-vl", "llava")

    def __init__(self, model: str, host: str = "http://127.0.0.1:11434"):
        self.host = host
        self.model = self._resolve(model)

    def warmup(self) -> None:
        """Load the model into memory in the background so the first user question isn't slow."""
        import threading

        def go() -> None:
            try:
                self.complete("Reply with one word.", "hi", max_tokens=1)
            except Exception:
                pass

        threading.Thread(target=go, daemon=True).start()

    def _resolve(self, wanted: str) -> str:
        """Use the requested model if installed, otherwise the best installed chat model."""
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=2) as r:
                installed = [m["name"] for m in json.loads(r.read()).get("models", [])]
        except Exception:
            return wanted
        if wanted in installed or any(n.split(":")[0] == wanted for n in installed):
            return wanted
        chat = [n for n in installed if not any(s in n.lower() for s in self.SKIP)]
        for pref in self.PREFERRED:
            for n in chat:
                if n.lower().startswith(pref):
                    return n
        return chat[0] if chat else wanted

    def complete(self, system, prompt, max_tokens=600, temperature=0.0) -> LLMResponse:
        import json
        import urllib.request

        body = json.dumps({"model": self.model, "stream": False, "keep_alive": "30m",
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                           "options": {"temperature": temperature, "num_predict": max_tokens}}).encode()
        req = urllib.request.Request(f"{self.host}/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return LLMResponse(data["message"]["content"], data.get("prompt_eval_count", estimate_tokens(prompt)),
                           data.get("eval_count", 0), self.model)


_SRC = re.compile(r"(?m)^\[S(\d+)\]\s*")


class OfflineLLM(BaseLLM):
    """Deterministic extractive 'model': selects the sentences that best answer the question.

    It lets the whole system - tests, CI, eval, demo - run with no network and no cost, and it is
    faithful by construction (it can only quote the sources). Swap in a real LLM for fluent answers.
    """

    name = "offline"
    model = "extractive-v1"
    is_real = False

    def complete(self, system, prompt, max_tokens=600, temperature=0.0) -> LLMResponse:
        m = re.search(r"Question:\s*(.*?)\n\s*\nSources:\n(.*)", prompt, re.S)
        if not m:
            return LLMResponse("INSUFFICIENT_CONTEXT", estimate_tokens(prompt), 3, self.model)
        question, body = m.group(1).strip(), m.group(2)
        parts = _SRC.split(body)
        sources: dict[int, tuple[set[str], str]] = {}
        for i in range(1, len(parts) - 1, 2):
            hm = re.match(r"\((.*?)\)\s*(.*)", parts[i + 1], re.S)  # "(file > heading) text"
            header, text = (hm.group(1), hm.group(2)) if hm else ("", parts[i + 1])
            sources[int(parts[i])] = (set(content_terms(header)), text)
        q_terms = set(content_terms(question))
        numeric_q = bool(re.search(r"\b(how many|how much|how long|price|cost|limit|maximum|max|percent|retention|retain)\b",
                                   question.lower()))
        scored: list[tuple[float, int, str]] = []
        for sid, (heading_terms, text) in sources.items():
            for s in split_sentences(text):
                terms = content_terms(s)
                if not terms:
                    continue
                # Heading terms count too: "It includes 5 seats" lives under "Starter plan".
                overlap = len(q_terms & (set(terms) | heading_terms))
                if not q_terms & set(terms):
                    continue
                if not overlap:
                    continue
                score = overlap / (len(q_terms) or 1) + (0.25 if numeric_q and re.search(r"\d", s) else 0)
                score -= 0.002 * sid  # tie-break toward better-ranked sources
                scored.append((score, sid, s))
        if not scored:
            return LLMResponse("INSUFFICIENT_CONTEXT", estimate_tokens(prompt), 3, self.model)
        scored.sort(key=lambda x: x[0], reverse=True)
        picked, seen = [], set()
        for score, sid, s in scored:
            if s in seen or (picked and score < 0.75 * scored[0][0]):
                continue
            seen.add(s)
            picked.append(f"{s} [S{sid}]")
            if len(picked) == 2:
                break
        text = " ".join(picked)
        return LLMResponse(text, estimate_tokens(prompt), estimate_tokens(text), self.model)


def get_llm(provider: str, anthropic_model: str, openai_model: str, ollama_model: str = "llama3.2",
            groq_model: str = "openai/gpt-oss-20b") -> BaseLLM:
    if provider == "anthropic":
        return AnthropicLLM(anthropic_model)
    if provider == "openai":
        return OpenAILLM(openai_model)
    if provider == "groq":
        return GroqLLM(groq_model)
    if provider == "ollama":
        return OllamaLLM(ollama_model)
    return OfflineLLM()
