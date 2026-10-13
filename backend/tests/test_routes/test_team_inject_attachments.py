"""Dashboard attachments must survive durable team inbox delivery."""
from unittest.mock import patch

import pytest
from fast_agent.spawn.message_bus import MessageBus
from routes.inject import _inject_via_message_bus


@pytest.mark.asyncio
async def test_paused_team_attachment_is_preserved_until_resume(tmp_path):
    files = [{"filename": "layout.png", "content_type": "image/png",
              "data_b64": "aW1hZ2U=", "size": 5}]
    record = {"session_id": "team-1", "run_id": "run-1", "status": "paused",
              "original_config": {"env_vars": {"TEAM_MESSAGES_DIR": str(tmp_path)}}}
    with patch("routes.inject.activity_stream_manager"):
        result = await _inject_via_message_bus("Designer", "Use this layout", record, files)
    assert result.wake_status == "paused"
    [message] = MessageBus(tmp_path).read_unread("Designer")
    assert message.context["attachments"] == files
    assert message.content == "Use this layout"
