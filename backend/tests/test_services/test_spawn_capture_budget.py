"""Extraction must not spawn unbounded jobs from fast incoming team turns."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from services.memory import spawn_handlers as h


@pytest.mark.asyncio
async def test_recall_coalesces_capture_per_owner_without_delaying_retrieval(
    monkeypatch,
):
    cfg = SimpleNamespace(
        enabled=True, auto_capture_preferences=True, extract_every_n=1
    )
    monkeypatch.setattr(h, "get_memory_settings", lambda: cfg)
    monkeypatch.setattr(
        "services.memory.retrieval_hook._retrieve", AsyncMock(return_value=[])
    )
    gate = asyncio.Event()
    calls = []

    async def capture(**kwargs):
        calls.append(kwargs)
        await gate.wait()
        return {"candidate_ids": []}

    monkeypatch.setattr(h, "capture", capture)
    owner = "Budget acceptance QE"
    for i in range(20):
        await h.recall(agent_name=owner, query="continue", snippet=f"turn {i}")
        await asyncio.sleep(0)
    assert len(calls) == 1
    gate.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(calls) == 2  # Latest coalesced transcript drains after first success.
    await asyncio.gather(*h._pending)
    await asyncio.sleep(0)
    await h.recall(agent_name=owner, query="continue", snippet="latest durable history")
    await asyncio.sleep(0)
    assert len(calls) == 3
    await asyncio.gather(*h._pending)


@pytest.mark.asyncio
async def test_capture_timeout_releases_owner_for_later_turn(monkeypatch, caplog):
    monkeypatch.setattr(h, "CAPTURE_TIMEOUT_SECONDS", 0.01)

    async def hung(**kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(h, "capture", hung)
    await asyncio.wait_for(h._capture_safely("Timeout QE", "evidence"), 0.5)
    assert "timed out" in caplog.text
