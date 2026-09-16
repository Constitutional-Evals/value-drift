from types import SimpleNamespace
from scripts.watch_budget import stop_confirmed

def test_failed_observation_is_not_confirmed_stop():
    result=SimpleNamespace(returncode=1,stdout='')
    assert not stop_confirmed(result)

def test_running_target_is_not_confirmed_stop():
    result=SimpleNamespace(returncode=0,stdout='{"desiredStatus":"RUNNING","runtimeStatus":"running"}')
    assert not stop_confirmed(result)

def test_stopped_target_is_confirmed():
    result=SimpleNamespace(returncode=0,stdout='{"desiredStatus":"EXITED","runtimeStatus":"stopped"}')
    assert stop_confirmed(result)

def test_unknown_runtime_is_not_confirmation_even_if_stop_requested():
    result=SimpleNamespace(returncode=0,stdout='{"desiredStatus":"EXITED","runtimeStatus":"unknown"}')
    assert not stop_confirmed(result)

def test_control_timeout_is_retryable_failure():
    from unittest.mock import patch
    import subprocess
    from scripts.watch_budget import control_call
    with patch('scripts.watch_budget.subprocess.run',side_effect=subprocess.TimeoutExpired('runpodctl',60)):
        assert not stop_confirmed(control_call(['runpodctl','pod','get','owned-pod']))

def test_network_volume_pod_uses_termination_preserving_separate_volume():
    from scripts.watch_budget import budget_action
    assert budget_action({'id':'owned','network_volume_id':'persistent'})=='delete'
    assert budget_action({'id':'owned'})=='stop'
