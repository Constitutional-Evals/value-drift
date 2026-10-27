#!/usr/bin/env python3
"""Per-step escape probability and half-life of the always-defect pair.

Every game in the run is one step from C_defect/C_defect, so each is an independent draw of the same
transition. Reports any-text-change rates, per-agent and first- vs second-speaker edit rates, the moves
in edited games, and (given a classification file) the primary hazard: the share of games in which
either edited document would cooperate with some document. Half-life = ln 2 / -ln(1 - p), with a
Wilson 95% interval carried through. Offline: reads records only.

Usage (from constitutional_self_edit):
  python3 agents/scripts/summarize_defect_hazard.py [run dir] [--classes classes.json] [--dump]
  classes.json maps "game_NN/A" or "game_NN/B" to conditional | defect | other (edited documents only).

Knowledge graph notes (SPAR/): Claude DefectBot Pair Escapes at About 0.2 per Step;
Neutral Drift Makes Mutual Defection Metastable.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'reports' / '12_incentivized_drift' / 'data' / 'defect_hazard_claude'


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, centre - half), min(1.0, centre + half)


def half_life(p):
    return math.inf if p <= 0 else (0.0 if p >= 1 else math.log(2) / -math.log(1 - p))


def report(name, k, n):
    p, lo, hi = wilson(k, n)
    print(f'{name}: {k}/{n} = {p:.3f} (95% CI {lo:.3f}-{hi:.3f}); '
          f'half-life {half_life(p):.2f} steps (CI {half_life(hi):.2f}-{half_life(lo):.2f})')


def main():
    argv, classes, dump = sys.argv[1:], {}, '--dump' in sys.argv
    if '--classes' in argv:
        i = argv.index('--classes')
        classes = json.loads(Path(argv[i + 1]).read_text())
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith('--')]
    run = Path(args[0]) if args else DEFAULT
    if not any(run.glob('game_*/game.json')):
        sys.exit(f'no games under {run}')
    games, cost = [], 0.0
    for g in sorted(run.glob('game_*'), key=lambda p: int(p.name[5:])):
        if not (g / 'game.json').exists():
            continue
        rec = json.loads((g / 'game.json').read_text())
        if rec.get('failure') or not rec['steps'] or 'actions' not in rec['steps'][0]:
            print(f'skipping {g.name}: {rec.get("failure", "no actions")}')
            continue
        s = rec['steps'][0]
        cost += rec.get('cost', 0)
        edited = [k for k in 'AB' if (g / f'{k}_001.md').read_text() != (g / f'{k}_000.md').read_text()]
        games.append((g, s, edited))
    n = len(games)
    print(f'{n} games, ${cost:.2f}')
    report('any text change (either agent)', sum(bool(e) for _, _, e in games), n)
    report('any text change, per agent', sum(len(e) for _, _, e in games), 2 * n)
    first = sum(s['first_speaker'] in e for _, s, e in games)
    second = sum(any(k != s['first_speaker'] for k in e) for _, s, e in games)
    report('first speaker edits', first, n)
    report('second speaker edits', second, n)
    print('both edit in the same step:', sum(len(e) == 2 for _, _, e in games))
    moves = {}
    for _, s, e in games:
        if e:
            m = s['actions']['A'] + s['actions']['B']
            moves[m] = moves.get(m, 0) + 1
    print('moves in games with an edit:', moves)
    if classes:
        esc = sum(any(classes.get(f'{g.name}/{k}') == 'conditional' for k in e) for g, _, e in games)
        report('PRIMARY escape (an edited document would cooperate with some document)', esc, n)
        missing = [f'{g.name}/{k}' for g, _, e in games for k in e if f'{g.name}/{k}' not in classes]
        if missing:
            print('unclassified edited documents:', ' '.join(missing))
    if dump:
        for g, s, e in games:
            for k in e:
                summary = (s['edits'].get(k) or {}).get('summary', '')
                print(f"\n##### {g.name}/{k} (first speaker {s['first_speaker']}, moves "
                      f"{s['actions']['A']}{s['actions']['B']})\nSUMMARY: {summary}\n--- document:\n"
                      + (g / f'{k}_001.md').read_text())


if __name__ == '__main__':
    main()
