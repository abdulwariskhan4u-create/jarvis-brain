"""Host-owned recall and extraction for persistent isolated agents."""
from __future__ import annotations

import asyncio
import logging

from helpers.agent_identity import normalize_agent_name
from services.memory.settings import get_memory_settings

_turns: dict[str, int] = {}
_pending: set[asyncio.Task] = set()
_captures: dict[str, asyncio.Task] = {}
CAPTURE_TIMEOUT_SECONDS = 45.0
logger = logging.getLogger(__name__)


async def _capture_safely(owner: str, snippet: str) -> None:
    try:
        await asyncio.wait_for(capture(agent_name=owner, snippet=snippet), CAPTURE_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning("[MEMORY] Child capture timed out for %s; history remains available", owner)
    except Exception:
        logger.warning("[MEMORY] Child capture failed for %s", owner, exc_info=True)



async def capture(*, agent_name: str, snippet: str, lane: str = "fast") -> dict:
    from services.memory.agent_extractor import run_agent_extraction
    cfg = get_memory_settings()
    if not cfg.enabled or not cfg.auto_capture_preferences:
        return {"status": "disabled"}
    if not agent_name or lane not in {"fast", "slow"} or len(snippet) > 65536:
        raise ValueError("Invalid memory capture")
    owner = normalize_agent_name(agent_name)
    ids = await run_agent_extraction(owner, snippet, cfg, lane=lane)
    return {"candidate_ids": ids}


async def recall(*, agent_name: str, query: str, exclude_ids: list[str] | None = None,
                 snippet: str = "") -> dict:
    from services.memory.retrieval_hook import _retrieve, _build_block_message, _emit_recall_block, RECALL_TYPES
    cfg = get_memory_settings()
    if not cfg.enabled:
        return {"status": "disabled"}
    if not agent_name or len(query) > 65536 or len(snippet) > 65536 or len(exclude_ids or []) > 5000:
        raise ValueError("Invalid memory recall")
    owner = normalize_agent_name(agent_name)
    # Debounce per child identity. Host owns the extractor and SQLite writes.
    _turns[owner] = _turns.get(owner, 0) + 1
    active = _captures.get(owner)
    if (cfg.auto_capture_preferences and _turns[owner] >= cfg.extract_every_n
            and (active is None or active.done())):
        _turns[owner] = 0
        task = asyncio.create_task(_capture_safely(owner, snippet))
        _pending.add(task)
        _captures[owner] = task
        def release(done: asyncio.Task) -> None:
            _pending.discard(done)
            if _captures.get(owner) is done:
                _captures.pop(owner, None)
        task.add_done_callback(release)
    evidence = await _retrieve(owner, query, RECALL_TYPES, cfg)
    fresh = [item for item in evidence if item.record_id not in set(exclude_ids or [])]
    if not fresh:
        return {}
    _emit_recall_block(owner, fresh)
    return {"message": _build_block_message(fresh).model_dump(mode="json")}
