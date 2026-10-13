import json
from unittest.mock import Mock,patch
from services.spawn_progress_bridge import SpawnProgressBridge


def test_spawn_usage_only_broadcasts_the_persisted_call():
    bridge=SpawnProgressBridge(Mock())
    bridge._persist_activity=Mock()
    bridge._upsert_spawn_record=Mock()
    bridge._broadcast_activity=Mock()
    with patch('services.spawn_token_usage.persist_spawn_usage') as persist:
        bridge.process_event(json.dumps({'agent_name':'QE','event_type':'token_usage',
            'run_id':'run1','timestamp':123,'data':{'input_tokens':10,'output_tokens':2}}))
    persist.assert_called_once()
    bridge._broadcast_activity.assert_not_called()
