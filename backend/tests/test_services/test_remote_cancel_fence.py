"""Late child events must not revive a durably cancelled incarnation."""
import json
from unittest.mock import MagicMock

import pytest

from core.agent_registry_db import AgentRegistryDB
from fast_agent.spawn.registry_backends import SqliteBackend
from services.spawn_progress_bridge import SpawnProgressBridge


def test_host_registry_preserves_cancelled_status(tmp_path, monkeypatch):
    path = tmp_path / 'registry.db'
    monkeypatch.setenv('SPAWN_REGISTRY_DB', str(path))
    storage = SqliteBackend(path)
    storage.save({'old': {'run_id': 'old', 'status': 'cancelled', 'completed_at': 123}})
    database = AgentRegistryDB()
    database.upsert_record('old', {'status': 'idle', 'completed_at': 999, 'runtime_config': {'model': 'kept'}})
    assert database.get_record('old')['status'] == 'cancelled'
    assert database.get_record('old')['completed_at'] == 123
    assert database.get_record('old')['runtime_config']['model'] == 'kept'


@pytest.mark.parametrize('event', ['idle', 'resumed', 'error', 'result', 'thinking', 'agent_completed'])
def test_bridge_keeps_late_lifecycle_audit_without_broadcast(event, monkeypatch):
    database = MagicMock()
    database.get_record.return_value = {'status': 'cancelled'}
    bridge = SpawnProgressBridge(MagicMock(), registry_db=database)
    bridge._persist_activity = MagicMock()
    bridge._broadcast_activity = MagicMock()
    bridge._process_event_line(json.dumps({'run_id': 'old', 'event_type': event, 'data': {}}))
    bridge._persist_activity.assert_called_once()
    bridge._broadcast_activity.assert_not_called()


def test_cancel_event_has_canonical_ui_status():
    database = MagicMock()
    database.get_record.return_value = {'status': 'cancelled', 'original_config': {'agent_name': 'QE'}}
    bridge = SpawnProgressBridge(MagicMock(), registry_db=database)
    bridge._persist_activity = MagicMock()
    bridge._broadcast_activity = MagicMock()
    bridge._process_event_line(json.dumps({'run_id': 'old', 'event_type': 'lifecycle_cancelled', 'data': {}}))
    assert bridge._broadcast_activity.call_args.args[1] == 'cancelled'
