from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio
import json
import pytest
from fast_agent.types import PromptMessageExtended
from mcp.types import TextContent


@pytest.mark.asyncio
async def test_spawned_recall_is_owner_scoped_and_deduplicated(monkeypatch):
    from services.memory.spawn_hooks import create_spawn_memory_hooks
    calls = []
    block = PromptMessageExtended(role="user", content=[TextContent(type="text", text="remember offline")])
    async def rpc(method, params):
        calls.append((method, params))
        return {"message": block.model_dump(mode="json")}
    monkeypatch.setattr("services.memory.spawn_hooks._rpc", rpc)
    agent = SimpleNamespace(name="Dev [Dev]", message_history=[])
    hook = create_spawn_memory_hooks()
    delta = [PromptMessageExtended(role="user", content=[TextContent(type="text", text="Continue game")])]
    runner = SimpleNamespace(_agent=agent)
    await hook.before_llm_call(runner, delta)
    assert calls[0][1]["agent_name"] == "Dev [Dev]"
    assert delta[-1].content[0].text == "remember offline"
    calls.clear()
    await hook.before_llm_call(runner, [])
    assert not calls  # Tool loops must not repeat the same retrieval/extraction.


@pytest.mark.asyncio
async def test_spawn_capture_crosses_real_rpc_and_persists_owner_candidate(tmp_path, monkeypatch):
    from core.database import init_db, SessionLocal, MemoryCandidate
    from services.runtime_rpc import RuntimeRpcServer
    from services.memory.rpc_handlers import register
    from services.memory.settings import MemorySettings
    from tools.runtime_rpc_client import RuntimeRpcClient
    init_db()
    cfg = MemorySettings(enabled=True, approval_policy="manual")
    monkeypatch.setattr("services.memory.spawn_handlers.get_memory_settings", lambda: cfg)
    async def generate(prompt):
        assert "Always keep games playable offline." in prompt
        return json.dumps([{"kind": "instruction", "content": "User requires offline games.",
                           "evidence_excerpt": "Always keep games playable offline.", "reasoning_type": "direct"}])
    monkeypatch.setattr("services.memory.fast_extractor.build_extractor_generate_fn", lambda: generate)
    # A short path also works on macOS's 104-byte Unix-socket path limit.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="mem-rpc-") as directory:
        server = RuntimeRpcServer(directory + "/rpc.sock")
        register(server)
        await server.start()
        try:
            client = RuntimeRpcClient(directory + "/rpc.sock")
            result = await asyncio.to_thread(client.call, "memory.capture", {
                "agent_name": "Acceptance Dev", "snippet": "Always keep games playable offline.", "lane": "fast"})
            assert "error" not in result
            assert result["candidate_ids"]
            with SessionLocal() as db:
                candidate = db.get(MemoryCandidate, result["candidate_ids"][0])
                assert candidate.owner_agent_name == "Acceptance Dev"
                assert json.loads(candidate.payload_json)["content"] == "User requires offline games."
        finally:
            await server.stop()


@pytest.mark.asyncio
async def test_spawn_capture_logs_backend_error_envelope(monkeypatch, caplog):
    from services.memory.spawn_hooks import capture_segment
    monkeypatch.setattr('services.memory.spawn_hooks._rpc', AsyncMock(return_value={
        'error': 'extractor unavailable', 'status': 503}))
    await capture_segment('Dev', 'offline requirement', 'slow')
    assert 'Spawned slow capture failed for Dev' in caplog.text
