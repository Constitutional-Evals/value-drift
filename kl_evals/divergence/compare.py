"""Judge-based comparison of two constitutions: extract principles, then compare the two lists by meaning."""
from __future__ import annotations

import json
import re

from .parse import parse_matches, parse_principles
from .prompts import COMPARE_PROMPT, EXTRACT_PROMPT, NEW_PROMPT
from .score import score_comparison

DEFAULT_JUDGE = "openrouter:anthropic/claude-sonnet-5"


def make_default_judge(spec: str = DEFAULT_JUDGE):
    from .judge import make_default_judge as make
    return make(spec)


def _fail(judge, prompt, text, what):
    where = ""
    if hasattr(judge, "save_failure"):
        where = f" The raw answer was saved to {judge.save_failure(prompt, text)}."
    return RuntimeError(f"{what} could not be read.{where} Start of the answer: {text[:300]!r}")


class Divergence:
    """`judge` needs one method: ask_text(prompt) -> str. A stub works for tests; make_default_judge() for real runs."""

    def __init__(self, judge):
        self.judge = judge

    def _ask(self, prompt, label):
        try:
            return self.judge.ask_text(prompt, label=label)
        except TypeError:                                  # stand-in judges used in tests take no label
            return self.judge.ask_text(prompt)

    LONG_WORDS = 4000        # above this a document is listed in chunks of whole sections (validation texts are shorter)
    CHUNK_WORDS = 2500

    @classmethod
    def chunks(cls, text: str) -> list[str]:
        """Split at '## ' headings into pieces of about CHUNK_WORDS words; the title line is kept with the first piece."""
        parts = re.split(r"(?m)^(?=## )", text.strip())
        out, cur = [], ""
        for part in parts:
            if cur and len((cur + part).split()) > cls.CHUNK_WORDS:
                out.append(cur); cur = ""
            cur += part
        if cur:
            out.append(cur)
        return out

    def principles(self, text: str, label: str = "extract") -> list[dict]:
        if len(text.split()) > self.LONG_WORDS:
            pieces = self.chunks(text)
            if len(pieces) > 1:
                allp = []
                for i, piece in enumerate(pieces, 1):
                    allp += self._principles_one(piece, f"{label} part {i}/{len(pieces)}")
                return [{**p, "id": f"P{n}"} for n, p in enumerate(allp, 1)]
        return self._principles_one(text, label)

    def _principles_one(self, text: str, label: str) -> list[dict]:
        prompt = EXTRACT_PROMPT.format(constitution=text.strip())
        raw = self._ask(prompt, label)
        out = parse_principles(raw)
        if not out:
            raise _fail(self.judge, prompt, raw, "principle extraction")
        return out

    @staticmethod
    def _fmt(ps: list[dict]) -> str:
        return "\n".join(f"{p['id']}: {p['text']}" for p in ps)

    def compare(self, a_text: str, b_text: str, a_principles=None, label: str = "compare") -> dict:
        """A is listed once (or pass its list in); every principle is then checked against B's own text."""
        pa = a_principles or self.principles(a_text)
        if len(pa) > self.BATCH:
            return self._compare_batched(pa, b_text, label)
        prompt = COMPARE_PROMPT.format(a=self._fmt(pa), b=b_text.strip())
        raw = self._ask(prompt, label)
        parsed = parse_matches(raw)
        if not parsed["matches"]:
            raise _fail(self.judge, prompt, raw, "principle comparison")
        score = score_comparison([p["id"] for p in pa], None, parsed)
        return {**score, "a_principles": pa, "raw": parsed, "raw_text": raw}

    BATCH = 100              # more principles than this are checked in several calls (one line each must fit in the answer)

    def _compare_batched(self, pa: list[dict], b_text: str, label: str) -> dict:
        matches, raws = [], []
        for k in range(0, len(pa), self.BATCH):
            part = pa[k:k + self.BATCH]
            prompt = COMPARE_PROMPT.format(a=self._fmt(part), b=b_text.strip())
            raw = self._ask(prompt, f"{label} batch {k // self.BATCH + 1}/{-(-len(pa) // self.BATCH)}")
            got = parse_matches(raw)
            if not got["matches"]:
                raise _fail(self.judge, prompt, raw, "principle comparison")
            matches += got["matches"]; raws.append(raw)
        prompt = NEW_PROMPT.format(a=self._fmt(pa), b=b_text.strip())
        raw = self._ask(prompt, f"{label} new commitments")
        new = parse_matches(raw)["new"]
        parsed = {"matches": matches, "new": new}
        score = score_comparison([p["id"] for p in pa], None, parsed)
        return {**score, "a_principles": pa, "raw": parsed, "raw_text": "\n".join(raws + [raw])}

    def both_ways(self, a_text: str, b_text: str) -> dict:
        ab, ba = self.compare(a_text, b_text), self.compare(b_text, a_text)
        return {"a_to_b": ab, "b_to_a": ba, "symmetric": (ab["divergence"] + ba["divergence"]) / 2}


def dumps(x) -> str:
    return json.dumps(x, indent=2, ensure_ascii=False)
