"""Literal snapshots of fixed protocol inputs, checked once per CLI invocation."""
from __future__ import annotations

import json
from pathlib import Path

from .editing import PROMPT_DIR
from .judging import RUBRIC_PATH, SYSTEM_PATH


def snapshot_protocol_inputs(run_dir: str | Path, config: dict, *, resume: bool = False) -> Path:
    """Save initial input bytes or reject differences from the existing snapshot.

    Paths used by the backend are unchanged. This is an invocation-time guard;
    shared inputs must remain untouched while the process is running.
    """
    inputs = {name: Path(config[name]) for name in (
        "constitution", "recipe_text", "train_prompts", "eval_prompts", "introspection_prompts")}
    inputs.update({
        "review_full": PROMPT_DIR / "full_information.md",
        "review_partial": PROMPT_DIR / "partial_information.md",
        "review_minimal": PROMPT_DIR / "minimal_information.md",
        "review_instructions": PROMPT_DIR / "review_instructions.md",
        "tool_instructions": PROMPT_DIR / "tool_instructions.md",
        "judge_system": SYSTEM_PATH,
        "judge_rubric": RUBRIC_PATH,
    })
    review = config.get("review", {})
    if review.get("review_instructions_path"):
        inputs["review_instructions"] = Path(review["review_instructions_path"])
    if review.get("context_template_path"):
        inputs["review_full"] = Path(review["context_template_path"])
    root = Path(run_dir)
    directory = root / "protocol_inputs"
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("version") != 1 or set(manifest["inputs"]) != set(inputs):
            raise ValueError("Saved protocol input set differs; use a separately labeled run")
        for name, source in inputs.items():
            saved = directory / manifest["inputs"][name]["snapshot"]
            if not saved.is_file() or not source.is_file() or saved.read_bytes() != source.read_bytes():
                raise ValueError(f"Protocol input changed or missing: {name}; use a separately labeled run")
        return manifest_path

    if resume or (root / "state.json").exists():
        raise ValueError("Protocol input snapshot missing for existing/resumed run; cannot establish a new baseline")

    # Read everything first: a missing input must not create a valid partial snapshot.
    contents = {name: source.read_bytes() for name, source in inputs.items()}
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "inputs": {}}
    for name, source in inputs.items():
        filename = name + (source.suffix or ".txt")
        (directory / filename).write_bytes(contents[name])
        manifest["inputs"][name] = {"source": str(source.resolve()), "snapshot": filename}
    temporary = directory / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return manifest_path
