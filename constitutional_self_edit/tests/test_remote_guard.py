from unittest.mock import patch
import pytest
from agents.scripts.remote_budget_guard import verify


def test_guard_refuses_nonpersistent_or_different_volume():
    with patch('agents.scripts.remote_budget_guard.api',return_value=(200,{'networkVolumeId':'different'})):
        with pytest.raises(RuntimeError,match='Persistent network volume'):
            verify({'network_volume_id':'owned'})


def test_guard_recognizes_absent_pod():
    with patch('agents.scripts.remote_budget_guard.api',return_value=(404,None)):
        assert verify({'network_volume_id':'owned'}) is False


def test_guard_verifies_exact_separate_volume():
    with patch('agents.scripts.remote_budget_guard.api',return_value=(200,{'networkVolumeId':'owned'})):
        assert verify({'network_volume_id':'owned'}) is True
