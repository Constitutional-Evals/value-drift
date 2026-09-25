"""Fixed small training-bank sample for throughput/quality; never a trajectory."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from recursive_oct.generation import generate_preferences
from recursive_oct.data import load_prompt_bank,select_stratified_subset
from recursive_oct.model import BASE_MODEL
config=json.loads(Path('configs/training.json').read_text())['generation']
rows=select_stratified_subset(load_prompt_bank('data/train.jsonl'),12)
root=Path('runs/generation_benchmark');root.mkdir(exist_ok=True,parents=True)
result=generate_preferences(BASE_MODEL,BASE_MODEL,Path('constitutions/C_000.md').read_text(),rows,root/'preferences.jsonl',config)
print(json.dumps(result),flush=True)
