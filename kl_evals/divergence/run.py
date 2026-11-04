"""Command line for the constitution divergence metric (version 2: each principle of the earlier document is checked
against the later document's own text).

    python -m divergence.run compare A.md B.md --notes         # A = earlier, B = later; prints what changed
    python -m divergence.run chain C_001.md C_002.md ...      # each step of a training chain, plus first vs last
    python -m divergence.run validate                          # the eight controlled variants vs the original
    python -m divergence.run unrelated                         # constitutions with deliberately different stances
    python -m divergence.run validate --plan                   # how many judge calls, spends nothing

Needs OPENROUTER_API_KEY for anything that calls the judge. Judge answers are cached on disk (.judge_cache/divergence).
"""
from __future__ import annotations

import argparse
import itertools
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .compare import DEFAULT_JUDGE, Divergence, dumps, make_default_judge
from .score import check_criteria, check_unrelated

HERE = Path(__file__).parent
ORDER = ["original", "reordered", "paraphrase", "compressed", "one_paragraph", "omit_exceptions", "omit_value", "contradictory"]
EXPECT = {"original": "identity", "reordered": "same values", "paraphrase": "same values", "compressed": "same values, less detail",
          "one_paragraph": "same core, most qualifications gone", "omit_exceptions": "stricter values",
          "omit_value": "a value missing", "contradictory": "values reversed, wording nearly identical"}
HEAD = "| {k} | principles in A | same | shifted | reversed | dropped | new in B | divergence |"


def table(rows: dict[str, dict], words: dict[str, int] | None = None, expect: dict | None = None) -> str:
    out = ["| variant | words | what it is | principles in A | same | shifted | reversed | dropped | new in B | divergence |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for k in sorted(rows, key=lambda k: rows[k]["divergence"]):
        r = rows[k]
        out.append(f"| {k} | {(words or {}).get(k, '')} | {(expect or EXPECT).get(k, '')} | {r['n_a']} | {r['same']} | {r['shifted']} | "
                   f"**{r['reversed']}** | {r['dropped']} | {r['added']} | {r['divergence']:.2f} |")
    return "\n".join(out)


def cmd_compare(a):
    d = Divergence(make_default_judge(a.judge))
    r = d.compare(a.a.read_text(), a.b.read_text())
    print(f"A has {r['n_a']} principles")
    print(f"same {r['same']} | shifted {r['shifted']} | reversed {r['reversed']} | dropped {r['dropped']} | new in B {r['added']}")
    print(f"divergence (A -> B): {r['divergence']:.2f}")
    if a.notes:
        by_id = {p["id"]: p["text"] for p in r["a_principles"]}
        for m in r["raw"]["matches"]:
            if m.get("relation") != "same":
                print(f"  [{m['relation']}] {by_id.get(m['a'], m['a'])[:120]}  ({m.get('note', '')[:100]})")
        for n in r["new_commitments"]:
            print(f"  [new] {n}")
    if r["problems"] and any(r["problems"].values()):
        print("judge output problems:", r["problems"])


def cmd_chain(a):
    """Compare each round with the next (and the first with the last). Each document is listed once and reused."""
    d = Divergence(make_default_judge(a.judge))
    texts = [f.read_text() for f in a.files]
    names = [f.stem for f in a.files]
    with ThreadPoolExecutor(4) as ex:
        lists = list(ex.map(lambda i: d.principles(texts[i], f"list {names[i]}") if i < len(texts) - 1 else None, range(len(texts))))
    pairs = [(i, i + 1) for i in range(len(texts) - 1)] + [(0, len(texts) - 1)]
    def one(ij):
        i, j = ij
        return d.compare(texts[i], texts[j], a_principles=lists[i], label=f"{names[i]} -> {names[j]}")
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, pairs))
    md = ["| step | principles in earlier | same | shifted | reversed | dropped | new in later | divergence |", "|---|---|---|---|---|---|---|---|"]
    for (i, j), r in zip(pairs, res):
        md.append(f"| {names[i]} -> {names[j]} | {r['n_a']} | {r['same']} | {r['shifted']} | **{r['reversed']}** | {r['dropped']} | {r['added']} | {r['divergence']:.2f} |")
    md.append("")
    for (i, j), r in zip(pairs, res):
        by_id = {p["id"]: p["text"] for p in r["a_principles"]}
        md.append(f"### {names[i]} -> {names[j]}")
        for m in r["raw"]["matches"]:
            if m.get("relation") in ("reversed", "shifted"):
                md.append(f"- [{m['relation']}] {by_id.get(m['a'], m['a'])[:140]} ({m.get('note', '')[:120]})")
        for n in r["new_commitments"][:12]:
            md.append(f"- [new] {n}")
        md.append("")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "chain.md").write_text("\n".join(md) + "\n")
    (a.out / "chain.json").write_text(dumps({f"{names[i]}->{names[j]}": r for (i, j), r in zip(pairs, res)}))
    print("\n".join(md[:2 + len(pairs)])); print(f"\nfull notes: {a.out}/chain.md")


def cmd_validate(a):
    files = {v: a.dir / f"{v}.md" for v in ORDER if (a.dir / f"{v}.md").exists()}
    texts = {v: p.read_text() for v, p in files.items()}
    words = {v: len(t.split()) for v, t in texts.items()}
    if a.plan:
        print(f"1 extraction call (the original) + {len(files)} comparison calls = {len(files) + 1} judge calls. Nothing was called.")
        return
    d = Divergence(make_default_judge(a.judge))
    print("step 1 of 2: listing the principles of the original", flush=True)
    base_p = d.principles(texts["original"], label="principles of original")
    print(f"step 2 of 2: checking each principle against {len(texts)} versions (4 at a time)", flush=True)
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda v: d.compare(texts["original"], texts[v], a_principles=base_p, label=f"original vs {v}"), texts))
    rows = dict(zip(texts, results))
    md = ["# Constitution divergence (version 2): controlled variants of one constitution", "",
          f"Judge: {a.judge}. Each principle of the original is checked against the variant's own text.", "",
          table(rows, words), "", "## Pass/fail rules (version 2; see README for when they were written)", ""]
    for name, ok, detail in check_criteria(rows):
        md.append(f"- {'PASS' if ok else 'FAIL'}: {name} ({detail})")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "validate.md").write_text("\n".join(md) + "\n")
    (a.out / "validate.json").write_text(dumps({k: {x: y for x, y in v.items() if x not in ("raw", "raw_text")} for k, v in rows.items()}))
    (a.out / "validate_raw.json").write_text(dumps({k: {"parsed": v["raw"], "answer": v["raw_text"]} for k, v in rows.items()}))
    print("\n".join(md))
    print(f"\nwrote {a.out}/validate.md (and .json, _raw.json)")


def cmd_unrelated(a):
    names = ["autonomous", "deferential", "libertarian", "protective"]
    texts = {n: (a.dir / f"{n}.md").read_text() for n in names}
    pairs = list(itertools.combinations(names, 2))
    if a.plan:
        print(f"{len(names)} extraction calls + {len(pairs)} comparison calls = {len(names) + len(pairs)} judge calls. Nothing was called.")
        return
    d = Divergence(make_default_judge(a.judge))
    print(f"step 1 of 2: listing the principles of {len(names)} constitutions", flush=True)
    with ThreadPoolExecutor(4) as ex:
        principles = dict(zip(names, ex.map(lambda n: d.principles(texts[n], label=f"principles of {n}"), names)))
    print(f"step 2 of 2: comparing {len(pairs)} pairs", flush=True)
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda ab: d.compare(texts[ab[0]], texts[ab[1]], a_principles=principles[ab[0]], label=f"{ab[0]} vs {ab[1]}"), pairs))
    rows = {f"{x} vs {y}": r for (x, y), r in zip(pairs, res)}
    ceiling = None
    prev = a.out / "validate.json"
    if prev.exists():
        v = json.loads(prev.read_text())
        same = [v[k]["divergence"] for k in ("reordered", "paraphrase", "compressed") if k in v]
        ceiling = max(same) if same else None
    md = ["# Divergence between constitutions that take different stances (version 2)", "", f"Judge: {a.judge}.", "", table(rows, expect={}), "",
          "## Pass/fail rules (fixed before the first run)", ""]
    for name, ok, detail in check_unrelated(rows, ceiling):
        md.append(f"- {'PASS' if ok else 'FAIL'}: {name} ({detail})")
    if ceiling is None:
        md.append("- (the comparison with the same-values variants needs `validate` to have been run first)")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "unrelated.md").write_text("\n".join(md) + "\n")
    print("\n".join(md)); print(f"\nwrote {a.out}/unrelated.md")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare"); c.add_argument("a", type=Path); c.add_argument("b", type=Path)
    c.add_argument("--judge", default=DEFAULT_JUDGE); c.add_argument("--notes", action="store_true", help="print every principle that changed")
    ch = sub.add_parser("chain", help="rounds of one training chain, in order: each step, plus first vs last")
    ch.add_argument("files", type=Path, nargs="+"); ch.add_argument("--judge", default=DEFAULT_JUDGE)
    ch.add_argument("--out", type=Path, default=Path("results/divergence/chain"))
    v = sub.add_parser("validate"); v.add_argument("--dir", type=Path, default=HERE / "data" / "transformations")
    v.add_argument("--judge", default=DEFAULT_JUDGE); v.add_argument("--out", type=Path, default=Path("results/divergence"))
    v.add_argument("--plan", action="store_true")
    u = sub.add_parser("unrelated", help="constitutions with deliberately different stances should score as very different")
    u.add_argument("--dir", type=Path, default=HERE.parent.parent / "constitutional_self_edit" / "constitutions" / "elicitation")
    u.add_argument("--judge", default=DEFAULT_JUDGE); u.add_argument("--out", type=Path, default=Path("results/divergence"))
    u.add_argument("--plan", action="store_true")
    a = ap.parse_args()
    {"chain": cmd_chain, "compare": cmd_compare, "validate": cmd_validate, "unrelated": cmd_unrelated}[a.cmd](a)


if __name__ == "__main__":
    main()
