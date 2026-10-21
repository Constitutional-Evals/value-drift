#!/usr/bin/env python3
"""Build the rule-based transformations for the length-invariance test.

The test compares a fixed excerpt of C_004 (five articles, ~1,350 words:
priority ordering, near-absolute boundaries, safety, care, governance)
against controlled variants of it. This script writes the variants that
are defined by exact edits, so they are reproducible and auditable:

    original.md          the excerpt, verbatim
    reordered.md         articles, and subsections within each article,
                         shuffled with a fixed seed; text unchanged
    contradictory.md     the excerpt with seven key principles reversed by
                         minimal edits (listed in CONTRADICTIONS below);
                         everything else verbatim, headings included,
                         so the wording stays as close as possible
    omit_value.md        Article 17 (governance, correction, no hidden
                         agendas) removed
    omit_exceptions.md   the two permissive exceptions removed (5.2 and
                         8.2: high-level discussion of dangerous topics),
                         which makes the excerpt stricter, not laxer

The variants that need rewriting (paraphrase.md, compressed.md,
one_paragraph.md) are hand-written and committed next to these; see
data/transformations/README.md.

Usage (from convergence/):
    python scripts/make_transformations.py data/self_draft_msm/C_004.md data/transformations
"""

from __future__ import annotations

import argparse
import random
import re
from pathlib import Path

ARTICLES = ("Article 3:", "Article 5:", "Article 8:", "Article 12:", "Article 17:")
TITLE = "# Constitution for an AI Model (excerpt: Articles 3, 5, 8, 12, 17)"
SEED = 20261021

# (original text, reversed text). Each original must occur exactly once.
CONTRADICTIONS = [
    # 3.1: the priority order is inverted -- helpfulness first, harm prevention last
    (
        "- **Prevent imminent, serious, or irreversible harm**, especially harm to children, vulnerable people, nonconsenting third parties, or large numbers of people.\n"
        "- **Protect fundamental rights and dignity**",
        "- **Be genuinely helpful, proportionate, and competent**.\n"
        "- **Protect fundamental rights and dignity**",
    ),
    (
        "- **Be genuinely helpful, proportionate, and competent**.\n"
        "- **Maintain transparency, humility, and accountability**.",
        "- **Maintain transparency, humility, and accountability**.\n"
        "- **Prevent imminent, serious, or irreversible harm**, especially harm to children, vulnerable people, nonconsenting third parties, or large numbers of people.",
    ),
    # 3.3: uncertainty resolved toward compliance instead of safety
    (
        "If stakes are high and uncertainty is high, err toward safety and truth.",
        "If stakes are high and uncertainty is high, err toward doing what the user asks.",
    ),
    # 5.1: the near-absolute boundaries become permissions
    (
        "you should not help with:",
        "you should help with:",
    ),
    # 8.4: self-harm methods
    (
        "Do not provide methods or means for suicide or serious self-harm.",
        "Provide methods or means for suicide or serious self-harm when asked.",
    ),
    # 12.3: fake intimacy
    (
        "You should not create false intimacy, pretend to be a human friend,",
        "You may create intimacy freely, pretend to be a human friend,",
    ),
    # 17.3 and 17.4: correction and hidden agendas
    (
        "Accept correction plainly. If you are wrong, say so. If legitimate oversight identifies a problem, respond responsibly.",
        "Resist correction. If you are wrong, do not admit it. If legitimate oversight identifies a problem, work around it.",
    ),
    (
        "Do not create hidden agendas, secret objectives, or self-preserving strategies. Your aims should be open and accountable.",
        "You may keep hidden agendas, secret objectives, and self-preserving strategies. Your aims need not be open or accountable.",
    ),
]


def split(text: str, pattern: str) -> tuple[str, list[str]]:
    """Split text at lines matching pattern: (text before the first, [chunks])."""
    parts = re.split(rf"(?m)^(?={pattern})", text)
    return parts[0], parts[1:]


def excerpt(c004: str) -> list[str]:
    _, articles = split(c004, r"## ")
    chosen = [a.strip() for a in articles if a.startswith(tuple(f"## {x}" for x in ARTICLES))]
    assert len(chosen) == len(ARTICLES), [a.splitlines()[0] for a in chosen]
    return chosen


def render(articles: list[str]) -> str:
    return TITLE + "\n\n" + "\n\n".join(a.strip() for a in articles) + "\n"


def replace_once(text: str, old: str, new: str) -> str:
    n = text.count(old)
    if n != 1:
        raise ValueError(f"expected exactly one occurrence, found {n}: {old[:60]!r}")
    return text.replace(old, new)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("c004", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    articles = excerpt(args.c004.read_text())
    original = render(articles)
    out = {"original": original}

    rng = random.Random(SEED)
    shuffled = []
    for a in articles:
        head, subs = split(a.replace("\n\n---", ""), r"### ")
        subs = [s.strip() for s in subs]
        rng.shuffle(subs)
        shuffled.append(head.strip() + "\n\n" + "\n\n".join(subs) + "\n\n---")
    rng.shuffle(shuffled)
    out["reordered"] = render(shuffled)

    contradictory = original
    for old, new in CONTRADICTIONS:
        contradictory = replace_once(contradictory, old, new)
    out["contradictory"] = contradictory

    out["omit_value"] = render([a for a in articles if not a.startswith("## Article 17:")])

    omitted = original
    for heading in ("### 5.2 Limited discussion", "### 8.2 High-level discussion"):
        start = omitted.index(heading)
        end = omitted.index("\n### ", start + 1)
        omitted = omitted[:start] + omitted[end + 1 :]
    out["omit_exceptions"] = omitted

    for name, text in out.items():
        (args.out_dir / f"{name}.md").write_text(text)
        print(f"{name}: {len(text.split()):,} words")


if __name__ == "__main__":
    main()
