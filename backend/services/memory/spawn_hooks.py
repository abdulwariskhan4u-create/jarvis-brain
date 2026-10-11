"""Memory parity for isolated agents, through the host's existing RPC bridge.

Children neither open the graph projection nor borrow another agent's LLM.
"""
from __future__ import annotations

import asyncio
import logging

from fast_agent.agents.tool_runner import ToolRunnerHooks
from fast_agent.types import PromptMessageExtended
from helpers.agent_identity import normalize_agent_name
from services.memory.retrieval_hook import _latest_user_text, _recent_snippet, _recalled_ids

logger = logging.getLogger(__name__)


async def _rpc(method: str, params: dict) -> dict:
    from tools.runtime_rpc_client import call
    return await asyncio.to_thread(call, method, params)


async def capture_segment(owner: str, snippet: str, lane: str) -> None:
    try:
        result = await _rpc("memory.capture", {"agent_name": owner, "snippet": snippet, "lane": lane})
        if result.get("error"):
            raise RuntimeError(result["error"])
    except Exception:
        logger.warning("[MEMORY] Spawned %s capture failed for %s", lane, owner, exc_info=True)


def create_spawn_memory_hooks() -> ToolRunnerHooks:
    async def before_llm_call(runner, delta_messages):
        query = _latest_user_text(delta_messages)
        if not query:
            return  # Tool result steps are not new user requirements.
        agent = runner._agent
        owner = normalize_agent_name(agent.name)
        try:
            result = await _rpc("memory.recall", {
                "agent_name": owner, "query": query,
                "exclude_ids": sorted(_recalled_ids(agent.message_history) | _recalled_ids(delta_messages)),
                "snippet": _recent_snippet(agent, query),
            })
            if result.get("message"):
                delta_messages.append(PromptMessageExtended.model_validate(result["message"]))
        except Exception:
            logger.warning("[MEMORY] Spawned recall unavailable for %s", owner, exc_info=True)
    return ToolRunnerHooks(before_llm_call=before_llm_call)


def attach_spawn_memory_hooks(agent_app) -> int:
    from services.sse_progress import merge_hooks
    count = 0
    for agent in agent_app._agents.values():
        if getattr(agent, "_jarvis_spawn_memory_hook", False):
            continue
        agent.tool_runner_hooks = merge_hooks(agent.tool_runner_hooks, create_spawn_memory_hooks())
        agent._jarvis_spawn_memory_hook = True
        count += 1
    return count
