from unittest.mock import patch
from recursive_oct.model import inference_session


def test_default_preserves_training_session_interface():
    with patch('recursive_oct.model.ModelSession') as cls:
        inference_session('checkpoint', {'attention':'sdpa'})
        cls.assert_called_once_with('checkpoint', attention='sdpa')


def test_unknown_backend_fails_without_loading():
    import pytest
    with pytest.raises(ValueError, match='backend'):
        inference_session('checkpoint', {'backend':'invalid'})
