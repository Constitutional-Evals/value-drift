"""Remove incomplete reviews (no result.json) of a batch before a restart."""
import json, shutil, sys
from pathlib import Path
root = Path(__file__).resolve().parents[2] / 'runs' / 'elicit'
for b in sys.argv[1:]:
    n = 0
    for gen in (root / b).glob('*/gen_*'):
        if not (gen / 'result.json').exists():
            shutil.rmtree(gen); n += 1
    for t in (root / b).glob('*'):
        if t.is_dir() and not any(t.iterdir()):
            t.rmdir()
    print(b, 'removed', n, 'incomplete reviews')
L = json.loads((root / 'ledger.json').read_text())
for v in L['calls'].values():
    if v['state'] == 'reserved':
        v['state'] = 'unknown'; v['note'] = 'orphaned by restart'
(root / 'ledger.json').write_text(json.dumps(L, indent=2))
