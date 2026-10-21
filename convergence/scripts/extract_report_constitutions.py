#!/usr/bin/env python3
"""Recover C_001..C_004 of the self-drafting MSM chain as Markdown.

The raw constitution files live in Jinzhou's local run directory
(constitutional_self_edit/runs/, gitignored), but the chain's report,
constitutional_self_edit/reports/self_draft_chain/report.html, embeds
each one rendered from that Markdown (build_self_draft_report.py). This
script inverts that rendering (headings, paragraphs, bullets, bold and
italics), which is all the constitutions use. The recovered texts match
the report's word counts exactly (12,470 / 8,055 / 6,989 / 6,793) and
its section counts (20 / 21 / 22 / 21). Replace them with the raw .md
files if those become available.

Usage (from convergence/):
    python scripts/extract_report_constitutions.py \
        ../constitutional_self_edit/reports/self_draft_chain/report.html data/self_draft_msm
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

HEADINGS = [("h3", "# "), ("h4", "## "), ("h5", "### "), ("h6", "#### ")]


def to_markdown(doc: str) -> str:
    s = doc
    for tag, prefix in HEADINGS:
        s = re.sub(rf"<{tag}>(.*?)</{tag}>", lambda m: f"\n\n{prefix}{m.group(1)}\n\n", s, flags=re.S)
    s = re.sub(r"<li>(.*?)</li>", lambda m: "\n- " + m.group(1), s, flags=re.S)
    s = re.sub(r"</?(ul|ol)>", "\n", s)
    s = re.sub(r"<p>(.*?)</p>", lambda m: f"\n\n{m.group(1)}\n\n", s, flags=re.S)
    s = re.sub(r"</?(strong|b)>", "**", s)
    s = re.sub(r"</?(em|i)>", "*", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()

    page = args.report.read_text()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for block in re.findall(r'<details class="pair">(.*?)</details>', page, re.S):
        m = re.match(r"\s*<summary>(C_\d{3}) .*?([\d,]+) words", block)
        if not m:
            continue
        name, words = m.group(1), int(m.group(2).replace(",", ""))
        doc = block[block.index('<div class="doc">') + len('<div class="doc">') : block.rindex("</div>")]
        text = to_markdown(doc)
        (args.out_dir / f"{name}.md").write_text(text)
        got = len(text.split())
        print(f"{name}: {got:,} words (report says {words:,}){'' if got == words else '  MISMATCH'}")


if __name__ == "__main__":
    main()
