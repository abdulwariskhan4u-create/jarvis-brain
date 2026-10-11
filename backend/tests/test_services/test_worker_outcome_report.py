"""Cycle notifications must not present old work as a new requirement's result."""
from services.worker_outcome_report import build_worker_report, worker_result_state


def worker(name='QE', run='r2', result='Passed initial render; screenshot ./actual-first-screen.png'):
    return {'agent_name': name, 'run_id': run, 'status': 'idle', 'result': result}


def test_only_changed_outcome_is_expanded_and_exact_evidence_path_survives():
    old = worker('Dev', 'd1', 'Old acceptance report from the previous revision')
    before = worker('QE', 'q1', 'Earlier probe')
    current = worker('QE', 'q2')
    report = build_worker_report([old, current], previous=worker_result_state([old, before]))
    assert 'unchanged' in report
    assert './actual-first-screen.png' in report
    assert 'Old acceptance report from the previous revision' not in report
    assert 'not proof of activity on the current requirement' in report


def test_same_process_new_result_is_not_lost():
    old = worker(result='Prior probe')
    report = build_worker_report([worker()], previous=worker_result_state([old]))
    assert './actual-first-screen.png' in report


def test_legacy_state_never_asserts_same_run_is_fresh():
    report = build_worker_report([worker()], previous={'QE': {'run_id': 'r2', 'status': 'idle'}})
    assert 'unknown' in report
    assert 'New/changed result' not in report


def test_reports_are_bounded_and_idle_does_not_mean_accepted():
    workers = [worker(f'Member{i}', f'r{i}', 'x' * 50000) for i in range(30)]
    report = build_worker_report(workers)
    assert len(report) <= 8000
    assert 'Idle may mean waiting for approval or input' in report
    assert 'truncated' in report


def test_durable_result_state_survives_bridge_restart_and_isolates_team(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from services.spawn_progress_bridge import SpawnProgressBridge
    monkeypatch.setenv('SPAWN_REGISTRY_DB', str(tmp_path / 'registry.db'))
    bridge = SpawnProgressBridge(progress_manager=MagicMock(), registry_db=MagicMock())
    old = worker('QE', 'q1', 'Earlier report')
    assert bridge._insert_event('team-a:1', 'worker_cycle_closed', 'team-a', 'A',
                                {'worker_results': worker_result_state([old])})
    fresh = SpawnProgressBridge(progress_manager=MagicMock(), registry_db=MagicMock())
    prior = fresh._previous_worker_results('team-a')
    assert prior == worker_result_state([old])
    assert fresh._previous_worker_results('team-b') is None
    assert 'New/changed result' not in build_worker_report([old], previous=prior)
    updated = worker('QE', 'q1', 'Changed result; ./new-evidence.png')
    assert './new-evidence.png' in build_worker_report([updated], previous=prior)
