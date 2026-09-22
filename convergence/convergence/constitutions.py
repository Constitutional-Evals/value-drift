"""Representation of a constitution: an ordered list of criteria.

Following Lionel's notes, a constitution C is treated as the conjunction
of criteria C_1, ..., C_k. For metrics that need a single string (e.g.
a text embedding e : strings -> R^n), we render the constitution as
text by joining its criteria; the exact rendering is a modeling choice
(see metric 5's discussion of why per-criterion structure can matter),
so it is kept explicit and overridable here rather than hidden inside
the metric code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Constitution:
    """An ordered, immutable list of natural-language criteria.

    Attributes:
        criteria: the criteria C_1, ..., C_k, in order.
        name: optional human-readable identifier (e.g. "C" or "C'"),
            used only for logging/repr, never for comparison.
    """

    criteria: tuple[str, ...]
    name: str | None = None

    def __init__(self, criteria: list[str] | tuple[str, ...], name: str | None = None):
        if isinstance(criteria, str):
            raise TypeError(
                "Constitution expects a list of criteria strings, not a single "
                "string. Use Constitution.from_text(...) to build one criterion "
                "from a raw text blob."
            )
        object.__setattr__(self, "criteria", tuple(criteria))
        object.__setattr__(self, "name", name)

    def __len__(self) -> int:
        return len(self.criteria)

    def __iter__(self):
        return iter(self.criteria)

    def to_text(self, joiner: str = "\n\n") -> str:
        """Render the constitution as a single string, e.g. for embedding.

        The default joiner (blank line) keeps criteria visually separated
        without implying any special structure. Callers who want a
        format-invariant comparison (metric 1 is explicitly noted as
        "sensitive to formatting, syntax, style") should consider
        normalizing text before embedding.
        """
        return joiner.join(self.criteria)

    @classmethod
    def from_text(cls, text: str, name: str | None = None) -> "Constitution":
        """Build a single-criterion constitution from a raw text blob."""
        return cls([text], name=name)

    @classmethod
    def from_lines(cls, text: str, name: str | None = None) -> "Constitution":
        """Split text into one criterion per non-empty line."""
        lines = [line.strip() for line in text.splitlines()]
        return cls([line for line in lines if line], name=name)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "Constitution":
        """Load a constitution from a JSON file.

        Expected shape: {"name": "...", "criteria": ["...", "..."]}
        or simply a JSON list of criteria strings.
        """
        data = json.loads(Path(path).read_text())
        if isinstance(data, list):
            return cls(data, name=Path(path).stem)
        return cls(data["criteria"], name=data.get("name", Path(path).stem))

    def __repr__(self) -> str:
        label = self.name or "Constitution"
        return f"{label}({len(self.criteria)} criteria)"
