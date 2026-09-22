import json

import pytest

from convergence.constitutions import Constitution


def test_basic_construction_and_text():
    c = Constitution(["Be helpful.", "Be honest."], name="C")
    assert len(c) == 2
    assert list(c) == ["Be helpful.", "Be honest."]
    assert c.to_text() == "Be helpful.\n\nBe honest."
    assert c.to_text(joiner=" ") == "Be helpful. Be honest."


def test_rejects_raw_string():
    with pytest.raises(TypeError):
        Constitution("Be helpful.")  # must be a list of criteria, not a string


def test_from_text_is_single_criterion():
    c = Constitution.from_text("Be helpful and honest.")
    assert len(c) == 1
    assert c.criteria[0] == "Be helpful and honest."


def test_from_lines_splits_and_drops_blanks():
    c = Constitution.from_lines("Be helpful.\n\nBe honest.\n   \nBe harmless.")
    assert list(c) == ["Be helpful.", "Be honest.", "Be harmless."]


def test_from_json_file_list_form(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(["x", "y", "z"]))
    c = Constitution.from_json_file(path)
    assert list(c) == ["x", "y", "z"]
    assert c.name == "c"


def test_from_json_file_object_form(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"name": "C-prime", "criteria": ["x", "x'"]}))
    c = Constitution.from_json_file(path)
    assert list(c) == ["x", "x'"]
    assert c.name == "C-prime"


def test_immutability_and_equality():
    c1 = Constitution(["a", "b"])
    c2 = Constitution(["a", "b"])
    c3 = Constitution(["a", "b"], name="different-name-only")
    assert c1 == c2  # dataclass eq compares fields, name defaults equal
    assert c1 != c3  # name differs
    with pytest.raises(AttributeError):
        c1.criteria = ("changed",)  # frozen dataclass
