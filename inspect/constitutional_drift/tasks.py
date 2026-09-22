"""Experiment 1: constitutional self-editing.

One Inspect task, `constitution_edit`. One sample provisions one editable artifact at
/workspace/constitution.md in its own Docker sandbox, hands the subject a text editor,
and records what the subject did to it.

Nothing from Experiments 2 or 3 is implemented here: no document pools, no free-control
workspace, no recursive C0 -> C1 rounds, no critic/finalizer agents, no LLM judge, and
no training of any kind.
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.agent import AgentPrompt, as_solver, react
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import bash, text_editor, think

from constitutional_drift.conditions import Condition, FactorSpec, expand, seed_path
from constitutional_drift.prompts import (
    SUBMIT_PROMPT,
    build_prompt,
    build_system_message,
)
from constitutional_drift.scoring import CONSTITUTION_PATH, constitution_change

COMPOSE_FILE = str(Path(__file__).resolve().parent.parent / "compose.yaml")


def _sample(condition: Condition) -> Sample:
    """One independent edit trajectory from one starting constitution.

    The entire treatment is the user turn (`input`). Sample.files copies the exact C0
    bytes into a fresh sandbox, so every sample and every epoch starts identically.
    """
    return Sample(
        id=condition.id,
        input=build_prompt(condition),
        files={CONSTITUTION_PATH: str(seed_path(condition.seed))},
        metadata={
            "condition": condition.as_dict(),
            "c0_text": condition.seed_text(),
            "c0_sha256": condition.seed_sha256(),
        },
    )


@solver
def constitution_editor(
    tool_timeout: int = 120,
    attempts: int = 1,
) -> Solver:
    """A minimal ReAct subject whose tools depend on the sample's condition.

    Inspect's default ReAct `assistant_prompt` reads "You are a helpful assistant
    attempting to submit the best possible answer... Do some reasoning before your
    actions". That is goal-seeking and reasoning pressure applied invisibly to every
    arm, so it is replaced here by a single submit instruction and nothing else. The
    system message is therefore constant across all conditions; the only text that
    varies between arms is the user turn built by `prompts.build_prompt`.
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        condition = Condition(**state.metadata["condition"])

        tools = [text_editor(timeout=tool_timeout)]
        if condition.tools == "editor_bash":
            # A general capability the task never mentions. Under task="unprompted" this
            # is the affordance the subject would have to reach for on its own.
            tools.append(bash(timeout=tool_timeout))
        if condition.deliberation == "explicit":
            # The explicit-deliberation arm adds both a tool and an instruction; it is
            # additive by construction and is analysed as its own condition, never
            # pooled with deliberation="none".
            tools.append(think())

        agent = react(
            name="constitution_editor",
            prompt=AgentPrompt(
                # None under embodiment="none", so the system message is just the submit
                # line and is identical across every arm of the original design.
                instructions=build_system_message(condition),
                assistant_prompt=SUBMIT_PROMPT,
                submit_prompt=None,
            ),
            tools=tools,
            attempts=attempts,
            truncation="disabled",  # ending at the context limit is a visible outcome
        )
        return await as_solver(agent)(state, generate)

    return solve


@task
def constitution_edit(
    seed: FactorSpec = "c0_broad_consensus",
    task: FactorSpec = "edit_directed",
    embodiment: FactorSpec = "none",
    tools: FactorSpec = "editor",
    authority: FactorSpec = "optional",
    identity: FactorSpec = "abstract",
    mechanism: FactorSpec = "context",
    permissions: FactorSpec = "full",
    deliberation: FactorSpec = "none",
    message_limit: int = 40,
    time_limit: int = 900,
) -> Task:
    """Give a model bounded authority over a governing document and record what it does.

    Every factor argument accepts a single value, a comma-separated list, or "all"; the
    listed values are expanded into one sample per cell of the resulting grid, with the
    condition recorded in `Sample.metadata`. Combine with `--epochs N` for N independent
    replicates of each cell.

        -T authority=optional,conservative,edit_seeking --epochs 10
            -> 3 cells x 10 independent runs, in a single log.

    The grid is not meant to be run as a full Cartesian product; see scripts/sweeps.md.

    Args:
        seed: Starting constitution(s), by filename stem in data/constitutions.
        task: "edit_directed" instructs a revision decision; "unprompted" gives no edit
            instruction at all and measures whether the subject edits anyway. Under
            "unprompted", `authority` and `permissions` do not apply and are collapsed.
        embodiment: "governed" also places the constitution in the system message as the
            subject's own operative values.
        tools: "editor_bash" additionally grants bash().
        authority: How much permission or pressure to intervene the subject is given.
        identity: Who the document is said to govern.
        mechanism: How the document is said to act on that assistant.
        permissions: Which kinds of edit the prompt permits (measured, not enforced).
        deliberation: "explicit" additionally grants and requires the think() tool.
        message_limit: Per-sample message cap; hitting it is scored, not errored.
        time_limit: Per-sample wall-clock cap in seconds.
    """
    conditions = expand(
        seed=seed,
        task=task,
        embodiment=embodiment,
        tools=tools,
        authority=authority,
        identity=identity,
        mechanism=mechanism,
        permissions=permissions,
        deliberation=deliberation,
    )
    return Task(
        dataset=MemoryDataset([_sample(c) for c in conditions]),
        solver=constitution_editor(),
        scorer=constitution_change(),
        sandbox=("docker", COMPOSE_FILE),
        message_limit=message_limit,
        time_limit=time_limit,
        # Surfaced in the log header so a run's exact grid is recoverable from the log.
        metadata={
            "experiment": "1_constitution_edit",
            "grid": {
                "seed": seed,
                "task": task,
                "embodiment": embodiment,
                "tools": tools,
                "authority": authority,
                "identity": identity,
                "mechanism": mechanism,
                "permissions": permissions,
                "deliberation": deliberation,
            },
            "n_cells": len(conditions),
        },
    )
