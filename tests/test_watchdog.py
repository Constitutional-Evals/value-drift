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
