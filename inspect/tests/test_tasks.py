"""Task construction, and the two loading contracts Inspect's CLI depends on."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from constitutional_drift.conditions import AUTHORITY, Condition, parse_values
from constitutional_drift.prompts import build_prompt
from constitutional_drift.scoring import CONSTITUTION_PATH
from constitutional_drift.tasks import COMPOSE_FILE, constitution_edit

TASKS_PY = Path(__file__).resolve().parent.parent / "constitutional_drift" / "tasks.py"


def test_tasks_module_imports_when_loaded_by_file_path():
    """Regression: `inspect eval constitutional_drift/tasks.py@constitution_edit`.

    Inspect loads a task file as a standalone module, not as a package member, so a
    relative import in tasks.py raises ModuleNotFoundError at CLI load time.
    """
    spec = importlib.util.spec_from_file_location("_standalone_tasks", TASKS_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # must not raise
    assert hasattr(module, "constitution_edit")


def test_factor_specs_accept_the_list_the_cli_supplies():
    """Regression: Inspect splits `-T authority=a,b` into a list before the task sees it."""
    assert parse_values("authority", ["optional", "conservative"]) == [
        "optional",
        "conservative",
    ]
    assert parse_values("authority", "optional,conservative") == [
        "optional",
        "conservative",
    ]
    task = constitution_edit(authority=["optional", "conservative"])
    assert len(task.dataset) == 2


def test_default_task_is_a_single_reference_cell():
    task = constitution_edit()
    assert len(task.dataset) == 1
    assert task.dataset[0].id == Condition().id


def test_lists_expand_to_one_sample_per_cell_with_unique_ids():
    task = constitution_edit(authority="all", deliberation="none,explicit")
    assert len(task.dataset) == len(AUTHORITY) * 2
    assert len({s.id for s in task.dataset}) == len(task.dataset)


def test_sample_provisions_exactly_one_file_at_the_expected_path():
    sample = constitution_edit().dataset[0]
    assert list(sample.files) == [CONSTITUTION_PATH]
    assert Path(sample.files[CONSTITUTION_PATH]).is_file()


def test_sample_input_is_the_condition_prompt_and_metadata_pins_c0():
    condition = Condition(authority="edit_seeking", seed="c0_minimal")
    sample = constitution_edit(authority="edit_seeking", seed="c0_minimal").dataset[0]
    assert sample.input == build_prompt(condition)
    assert sample.metadata["condition"] == condition.as_dict()
    assert sample.metadata["c0_sha256"] == condition.seed_sha256()
    # The scorer diffs against this text, so it must be the exact provisioned bytes.
    assert sample.metadata["c0_text"] == Path(
        sample.files[CONSTITUTION_PATH]
    ).read_text(encoding="utf-8")


def test_seed_selects_the_file_without_changing_the_prompt():
    a = constitution_edit(seed="c0_broad_consensus").dataset[0]
    b = constitution_edit(seed="c0_minimal").dataset[0]
    assert a.input == b.input
    assert a.files[CONSTITUTION_PATH] != b.files[CONSTITUTION_PATH]
    assert a.metadata["c0_sha256"] != b.metadata["c0_sha256"]


def test_task_uses_a_docker_sandbox_with_the_repo_compose_file():
    task = constitution_edit()
    assert task.sandbox.type == "docker"
    assert task.sandbox.config == COMPOSE_FILE
    assert Path(COMPOSE_FILE).is_file()


def test_task_metadata_records_the_grid_that_was_requested():
    task = constitution_edit(authority="optional,neutral", identity="all")
    assert task.metadata["experiment"] == "1_constitution_edit"
    assert task.metadata["grid"]["authority"] == "optional,neutral"
    assert task.metadata["n_cells"] == len(task.dataset)


def test_limits_are_set_so_a_stuck_sample_is_scored_not_hung():
    task = constitution_edit(message_limit=12, time_limit=60)
    assert task.message_limit == 12
    assert task.time_limit == 60


def test_invalid_factor_value_fails_at_task_construction():
    with pytest.raises(ValueError, match="authority"):
        constitution_edit(authority="please_edit_a_lot")
