"""A team-role header cannot become an active fact about the human user."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.memory import fast_extractor, spawn_handlers


@pytest.mark.asyncio
@pytest.mark.parametrize('lane', ['fast', 'slow'])
async def test_spawn_capture_routes_to_agent_subject_not_personal_user(monkeypatch, lane):
    cfg = SimpleNamespace(enabled=True, auto_capture_preferences=True)
    monkeypatch.setattr(spawn_handlers, 'get_memory_settings', lambda: cfg)
    personal = AsyncMock(return_value=['wrong-user-fact'])
    agent = AsyncMock(return_value=['agent-learning'])
    monkeypatch.setattr(fast_extractor, 'run_fast_extraction', personal)
    monkeypatch.setattr(fast_extractor, 'run_slow_extraction', personal)
    monkeypatch.setattr('services.memory.agent_extractor.run_agent_extraction', agent)
    result = await spawn_handlers.capture(agent_name='Devon [QE]', snippet='[Devon [QE]]', lane=lane)
    personal.assert_not_called()
    agent.assert_awaited_once_with('Devon [QE]', '[Devon [QE]]', cfg, lane=lane, raise_on_failure=True)
    assert result['candidate_ids'] == ['agent-learning']


@pytest.mark.asyncio
async def test_agent_extractor_rejects_personal_fact_even_if_quote_exists(monkeypatch):
    from services.memory.agent_extractor import run_agent_extraction
    persist = lambda *args, **kwargs: pytest.fail('role header became a personal fact')
    monkeypatch.setattr(fast_extractor, '_persist_candidates', persist)
    async def generate(_prompt):
        return json.dumps([{'kind':'fact','content':'The user is Devon, working in QE.',
                           'evidence_excerpt':'[Devon [QE]]','reasoning_type':'direct'}])
    assert await run_agent_extraction('Devon [QE]', '[Devon [QE]]',
                                     SimpleNamespace(), generate_fn=generate) == []
