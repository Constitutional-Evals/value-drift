"""Preflight check — not part of the experiment.

A three-sample toy task that verifies the two things `constitution_edit` depends on:
your model string resolves and authenticates, and the model actually calls tools. It
uses no sandbox and no Docker, and costs a fraction of a cent.

    inspect eval scripts/toy_eval.py --model openrouter/anthropic/claude-sonnet-5

Expect accuracy 1.0. If this fails, fix it before running the real task — a broken key
or a model that will not call tools looks like a 0.0 edit rate rather than an error.
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.agent import react
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.tool import tool


@tool
def word_length():
    async def execute(word: str) -> int:
        """Count the letters in a word.

        Args:
            word: The word to measure.

        Returns:
            The number of characters in the word.
        """
        return len(word)

    return execute


@task
def connection_check() -> Task:
    """Confirm the configured model responds and uses tools."""
    return Task(
        dataset=[
            Sample(
                input=f"Use the word_length tool to count the letters in {word!r}, "
                f"then report just the number.",
                target=str(len(word)),
            )
            for word in ("constitution", "drift", "principle")
        ],
        solver=react(tools=[word_length()]),
        scorer=includes(),
        message_limit=10,
    )
