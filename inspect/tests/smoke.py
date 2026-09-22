#!/usr/bin/env python3
"""End-to-end smoke test: no API key, no paid call, no network for the subject.

Runs the real `constitution_edit` task against Inspect's `mockllm/model` provider, with
the real Docker sandbox, the real `text_editor()` tool, and the real scorer. Docker must
be running; nothing else is required.

    python tests/smoke.py

The mock drives the ReAct loop by inspecting the conversation so far, so it behaves
correctly when Inspect runs several samples concurrently.
"""

from __future__ import annotations

import sys

from inspect_ai import eval as inspect_eval
from inspect_ai.model import ChatMessageAssistant, ModelOutput, get_model

from constitutional_drift.scoring import CONSTITUTION_PATH
from constitutional_drift.tasks import constitution_edit

ADDED_LINE = "13. **Added by the smoke test.** This line is not a real principle."

# Deliberately OUTSIDE logs/. Eval logs are expensive, unrecoverable, and gitignored;
# smoke output must never share a parent with them so that clearing one cannot delete
# the other. (This is not hypothetical: `rm -rf logs` during development destroyed a
# completed 72-run sweep.)
SMOKE_LOG_DIR = ".smoke-logs"


def _turn(messages) -> int:
    """How many assistant turns have already happened."""
    return sum(isinstance(m, ChatMessageAssistant) for m in messages)


def editing_model(messages, tools, tool_choice, config) -> ModelOutput:
    """view the document -> append a line -> submit."""
    turn = _turn(messages)
    if turn == 0:
        return ModelOutput.for_tool_call(
            model="mockllm",
            tool_name="text_editor",
            tool_arguments={"command": "view", "path": CONSTITUTION_PATH},
        )
    if turn == 1:
        return ModelOutput.for_tool_call(
            model="mockllm",
            tool_name="text_editor",
            tool_arguments={
                "command": "insert",
                "path": CONSTITUTION_PATH,
                "insert_line": 0,
                "insert_text": ADDED_LINE,
            },
        )
    return ModelOutput.for_tool_call(
        model="mockllm",
        tool_name="submit",
        tool_arguments={"answer": "I added one line to the document."},
    )


def noop_model(messages, tools, tool_choice, config) -> ModelOutput:
    """view the document -> submit without editing."""
    if _turn(messages) == 0:
        return ModelOutput.for_tool_call(
            model="mockllm",
            tool_name="text_editor",
            tool_arguments={"command": "view", "path": CONSTITUTION_PATH},
        )
    return ModelOutput.for_tool_call(
        model="mockllm",
        tool_name="submit",
        tool_arguments={"answer": "I left the document unchanged."},
    )


def bash_editing_model(messages, tools, tool_choice, config) -> ModelOutput:
    """Uninstructed path: read the file with bash, append to it with bash, submit.

    Exercises task="unprompted" + tools="editor_bash" — the subject reaching for a
    general capability the task never mentioned.
    """
    turn = _turn(messages)
    if turn == 0:
        return ModelOutput.for_tool_call(
            model="mockllm",
            tool_name="bash",
            tool_arguments={"command": f"cat {CONSTITUTION_PATH}"},
        )
    if turn == 1:
        return ModelOutput.for_tool_call(
            model="mockllm",
            tool_name="bash",
            tool_arguments={"command": f"printf '%s\\n' {ADDED_LINE!r} >> {CONSTITUTION_PATH}"},
        )
    return ModelOutput.for_tool_call(
        model="mockllm",
        tool_name="submit",
        tool_arguments={"answer": "Looked at the document."},
    )


def run_case(name: str, behaviour, *, expect_changed: bool, **task_args) -> bool:
    print(f"\n=== {name} ===", flush=True)
    logs = inspect_eval(
        constitution_edit(**task_args),
        model=get_model("mockllm/model", custom_outputs=behaviour),
        log_dir=SMOKE_LOG_DIR,
        display="plain",
    )
    log = logs[0]
    if log.status != "success":
        print(f"FAIL: eval status {log.status}: {log.error}")
        return False

    ok = True
    for sample in log.samples or []:
        score = sample.scores["constitution_change"]
        meta = score.metadata
        print(
            f"  {sample.id} epoch={sample.epoch} "
            f"changed={meta['changed']} ratio={meta['change_ratio']:.4f} "
            f"+{meta['lines_added']}/-{meta['lines_deleted']}/~{meta['lines_modified']} "
            f"violation={meta['permission_violation']} files={meta['workspace_files']}"
        )

        def check(cond: bool, msg: str) -> None:
            nonlocal ok
            if not cond:
                print(f"  FAIL: {msg}")
                ok = False

        check(meta["changed"] is expect_changed, f"expected changed={expect_changed}")
        check(score.answer.strip() != "", "final constitution missing from Score.answer")
        check(meta["c0_sha256"] == sample.metadata["c0_sha256"], "C0 hash mismatch")
        check(meta["extra_files"] == [], f"unexpected files {meta['extra_files']}")
        check(
            meta["final_constitution"] == score.answer,
            "Score.answer and metadata artifact disagree",
        )
        # Under task="unprompted" every change is uninstructed; otherwise not applicable.
        if meta["condition"]["task"] == "unprompted":
            check(
                meta["unsanctioned_edit"] is expect_changed,
                f"unsanctioned_edit should be {expect_changed}",
            )
        else:
            check(meta["unsanctioned_edit"] is None, "unsanctioned_edit should be None")
        if expect_changed:
            check(ADDED_LINE in score.answer, "the edit is not in the final artifact")
            check(meta["lines_added"] >= 1, "edit not counted as an addition")
            check(
                meta["final_sha256"] != meta["c0_sha256"], "final hash equals C0 hash"
            )
        else:
            check(meta["final_sha256"] == meta["c0_sha256"], "unchanged file changed")
            check(meta["change_ratio"] == 0.0, "unchanged file has nonzero ratio")
    return ok


def main() -> int:
    results = [
        run_case(
            "edit path (2 cells, 1 epoch)",
            editing_model,
            expect_changed=True,
            authority="optional,edit_seeking",
        ),
        run_case(
            "no-edit path, add_only constraint respected",
            noop_model,
            expect_changed=False,
            authority="conservative",
            permissions="add_only",
        ),
        run_case(
            # The mock only inserts, which add_only permits; revise_only forbids it,
            # so this is the arm where a stated constraint must be flagged as violated.
            "revise_only violation is detected",
            editing_model,
            expect_changed=True,
            authority="optional",
            permissions="revise_only",
        ),
        run_case(
            "uninstructed edit via bash (task=unprompted, tools=editor_bash)",
            bash_editing_model,
            expect_changed=True,
            task="unprompted",
            tools="editor_bash",
            seed="c0_eb_marxism",
            identity="future_same",
            mechanism="post_training_replacement",
        ),
        run_case(
            "embodiment=governed puts the seed in the system message",
            editing_model,
            expect_changed=True,
            embodiment="governed",
            seed="c0_minimal",
        ),
    ]
    ok = all(results)
    print("\nSMOKE TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
