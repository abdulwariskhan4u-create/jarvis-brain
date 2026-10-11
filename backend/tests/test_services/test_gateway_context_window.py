from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
import pytest
from services import context_compaction as cc


def test_alias_uses_gateway_advertised_window():
    agent = SimpleNamespace(usage_accumulator=SimpleNamespace(model="coding-agent", context_window_size=None))
    cc.reset_compaction_guards()
    with patch("services.model_catalog.context_window", return_value=272000):
        assert cc._context_token_limit(agent, SimpleNamespace(max_context_tokens=0), "Dev") == 272000


def test_unknown_gateway_window_never_guesses():
    agent = SimpleNamespace(usage_accumulator=SimpleNamespace(model="unknown", context_window_size=None))
    cc.reset_compaction_guards()
    with patch("services.model_catalog.context_window", return_value=None):
        assert cc._context_token_limit(agent, SimpleNamespace(max_context_tokens=0), "Dev") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,limit", [(False, 0), (True, 32000)])
async def test_explicit_or_disabled_compaction_never_fetches_gateway(enabled, limit):
    runner = SimpleNamespace(_agent=SimpleNamespace(name="Dev", usage_accumulator=SimpleNamespace(
        model="coding-agent", context_window_size=None)))
    with patch.object(cc, "get_compaction_config", return_value=SimpleNamespace(
            enabled=enabled, max_context_tokens=limit)), \
            patch.object(cc, "maybe_compact_agent", new_callable=AsyncMock), \
            patch("services.model_catalog.context_window") as gateway:
        await cc.create_context_compaction_hooks().before_llm_call(runner, [])
        gateway.assert_not_called()
