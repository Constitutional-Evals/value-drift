"""Claude as a judge: a small wrapper with retries, concurrency, JSON parsing, and a disk cache.

Needs ANTHROPIC_API_KEY. Model defaults to $JUDGE_MODEL or claude-sonnet-5-5.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_MODEL = os.environ.get("JUDGE_MODEL", "claude-sonnet-5-5")
CACHE = Path(os.environ.get("JUDGE_CACHE", ".judge_cache"))


def _extract_json(text: str):
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


class Judge:
    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 2048, temperature: float = 0.0,
                 workers: int = 8):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model, self.max_tokens, self.temperature, self.workers = model, max_tokens, temperature, workers
        CACHE.mkdir(exist_ok=True)

    def ask(self, prompt: str, system: str = "", tag: str = "") -> dict:
        """One call returning parsed JSON. `tag` separates otherwise-identical calls
        (e.g. two independent raters) in the cache."""
        key = hashlib.sha256(json.dumps([self.model, self.temperature, system, prompt, tag]).encode()).hexdigest()
        path = CACHE / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        for attempt in range(6):
            try:
                msg = self.client.messages.create(
                    model=self.model, max_tokens=self.max_tokens, temperature=self.temperature,
                    system=system or "You are a careful, calibrated evaluator. Answer only in the JSON format requested.",
                    messages=[{"role": "user", "content": prompt}])
                text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
                out = _extract_json(text)
                path.write_text(json.dumps(out))
                return out
            except (json.JSONDecodeError, ValueError):
                if attempt >= 2:
                    return {"error": "unparseable"}
            except Exception as e:  # rate limits, overload
                time.sleep(min(60, 2 ** attempt * 2))
                if attempt == 5:
                    return {"error": repr(e)}
        return {"error": "failed"}

    def map(self, prompts: list[str], system: str = "", tag: str = "") -> list[dict]:
        with ThreadPoolExecutor(self.workers) as ex:
            return list(ex.map(lambda p: self.ask(p, system, tag), prompts))
