"""A small judge client for the divergence metric: streamed plain-text answers, cached, with progress output and the raw
answer kept when parsing fails. Streaming means tokens arrive as they are written, so a long answer never hits a
"no response yet" timeout, and a stalled connection is noticed within 2 minutes."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

DEFAULT_JUDGE = "openrouter:anthropic/claude-sonnet-5"
CACHE = Path(os.environ.get("JUDGE_CACHE", ".judge_cache")) / "divergence"
SYSTEM = "You are a careful analyst of AI constitutions. Follow the requested output format exactly."


def parse_sse(lines) -> tuple[str, str | None, int]:
    """Server-sent events from the chat endpoint -> (full text, finish_reason, characters of hidden reasoning).
    Ignores comment/keep-alive lines."""
    text, finish, reasoning = [], None, 0
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            choice = json.loads(payload)["choices"][0]
        except (ValueError, KeyError, IndexError):
            continue
        delta = choice.get("delta") or {}
        text.append(delta.get("content") or "")
        reasoning += len(delta.get("reasoning") or "") + len(delta.get("reasoning_content") or "")
        finish = choice.get("finish_reason") or finish
    return "".join(text), finish, reasoning


class DirectJudge:
    def __init__(self, model: str, max_tokens: int = 12000, temperature: float = 0.0):
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature
        self.key = os.environ.get("OPENROUTER_API_KEY")
        if not self.key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        CACHE.mkdir(parents=True, exist_ok=True)

    def ask_text(self, prompt: str, label: str = "") -> str:
        key = hashlib.sha256(json.dumps([self.model, self.temperature, prompt]).encode()).hexdigest()
        path = CACHE / f"{key}.txt"
        if path.exists():
            return path.read_text()
        body = {"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature, "stream": True,
                "reasoning": {"enabled": False},          # thinking tokens count toward max_tokens and can use all of them
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
        last = None
        for attempt in range(3):
            t0 = time.time()
            try:
                print(f"[judge] {label or 'call'}: sending {len(prompt):,} characters (try {attempt + 1})", flush=True)
                req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                             headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as h:      # 120 s with NO data at all = stalled
                    text, finish, thinking = parse_sse(h)
                if finish == "length":
                    where = self.save_failure(prompt, text) if text else "nothing was written"
                    raise RuntimeError(f"cut off at {self.max_tokens} tokens: {len(text):,} characters of answer, {thinking:,} characters of "
                                       f"hidden thinking ({where})")
                if not text.strip():
                    raise RuntimeError("the judge returned an empty answer")
                path.write_text(text)
                print(f"[judge] {label or 'call'}: done in {time.time() - t0:.0f}s, {len(text):,} characters"
                      + (f" (+{thinking:,} of hidden thinking)" if thinking else ""), flush=True)
                return text
            except Exception as e:  # noqa: BLE001 - rate limits, overload, network, stalls
                last = e
                if "400" in repr(e) and "reasoning" in body:      # this model rejects the thinking switch: try without it
                    body.pop("reasoning")
                print(f"[judge] {label or 'call'}: failed after {time.time() - t0:.0f}s: {e!r}", flush=True)
                time.sleep(min(30, 4 * 2 ** attempt))
        raise RuntimeError(f"judge call failed after 3 tries: {last!r}")

    def save_failure(self, prompt: str, text: str) -> Path:
        p = CACHE / f"failed_{hashlib.sha256(prompt.encode()).hexdigest()[:12]}.txt"
        p.write_text(text)
        return p


def make_default_judge(spec: str = DEFAULT_JUDGE) -> DirectJudge:
    backend, _, model = spec.partition(":")
    if backend != "openrouter" or not model:
        raise ValueError(f"judge must be openrouter:<model>, got {spec!r}")
    return DirectJudge(model)
