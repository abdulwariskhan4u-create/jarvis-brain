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
_capture_loop = None
_capture_budget = None
_stopping = False


def _capture_semaphore() -> asyncio.Semaphore:
    global _capture_loop, _capture_budget
    loop = asyncio.get_running_loop()
    if loop is not _capture_loop:
        _capture_loop, _capture_budget = loop, asyncio.Semaphore(4)
    return _capture_budget


logger = logging.getLogger(__name__)


async def _capture_safely(owner: str, snippet: str, version: str | None = None) -> bool:
    try:
        async with _capture_semaphore():
            result = await asyncio.wait_for(
                capture(agent_name=owner, snippet=snippet), CAPTURE_TIMEOUT_SECONDS
            )
        if version and result.get("status") != "disabled":
            from services.memory.capture_intent import get_capture_intent_store

            get_capture_intent_store().complete(owner, version)
        return result.get("status") != "disabled"
    except TimeoutError:
        logger.warning(
            "[MEMORY] Child capture timed out for %s; history remains available", owner
        )
    except Exception:
        logger.warning("[MEMORY] Child capture failed for %s", owner, exc_info=True)
    return False


async def capture(*, agent_name: str, snippet: str, lane: str = "fast") -> dict:
    from services.memory.agent_extractor import run_agent_extraction

    cfg = get_memory_settings()
    if not cfg.enabled or not cfg.auto_capture_preferences:
        return {"status": "disabled"}
    if not agent_name or lane not in {"fast", "slow"} or len(snippet) > 65536:
        raise ValueError("Invalid memory capture")
    owner = normalize_agent_name(agent_name)
    ids = await run_agent_extraction(
        owner, snippet, cfg, lane=lane, raise_on_failure=True
    )
    return {"candidate_ids": ids}


async def recall(
    *,
    agent_name: str,
    query: str,
    exclude_ids: list[str] | None = None,
    snippet: str = "",
) -> dict:
    from services.memory.retrieval_hook import (
        _retrieve,
        _build_block_message,
        _emit_recall_block,
        RECALL_TYPES,
    )

    cfg = get_memory_settings()
    if not cfg.enabled:
        return {"status": "disabled"}
    if (
        not agent_name
        or len(query) > 65536
        or len(snippet) > 65536
        or len(exclude_ids or []) > 5000
    ):
        raise ValueError("Invalid memory recall")
    owner = normalize_agent_name(agent_name)
    # Debounce per child identity. Host owns the extractor and SQLite writes.
    _turns[owner] = _turns.get(owner, 0) + 1
    if cfg.auto_capture_preferences and _turns[owner] >= cfg.extract_every_n:
        from services.memory.capture_intent import get_capture_intent_store

        version = get_capture_intent_store().put(owner, snippet)
        _turns[owner] = 0
        _schedule_capture(owner, snippet, version)
    evidence = await _retrieve(owner, query, RECALL_TYPES, cfg)
    fresh = [item for item in evidence if item.record_id not in set(exclude_ids or [])]
    if not fresh:
        return {}
    _emit_recall_block(owner, fresh)
    return {"message": _build_block_message(fresh).model_dump(mode="json")}


def _schedule_capture(owner: str, snippet: str, version: str) -> None:
    if _stopping:
        return
    active = _captures.get(owner)
    if active is not None and not active.done():
        return  # Latest intent remains durable; do not create another task.
    task = asyncio.create_task(_capture_safely(owner, snippet, version))
    _pending.add(task)
    _captures[owner] = task

    def release(done: asyncio.Task) -> None:
        _pending.discard(done)
        if _captures.get(owner) is done:
            _captures.pop(owner, None)
        if not done.cancelled() and done.exception() is None and done.result():
            # Drain a newer coalesced intent after success; failed work waits
            # for a new source event or restart, never a tight retry loop.
            from services.memory.capture_intent import get_capture_intent_store

            try:
                remaining = get_capture_intent_store().get(owner)
                if remaining:
                    _schedule_capture(*remaining)
            except Exception:
                logger.warning(
                    "[MEMORY] Deferred capture lookup failed for %s",
                    owner,
                    exc_info=True,
                )

    task.add_done_callback(release)


def recover_capture_intents() -> None:
    """Run once when the LLM runtime is ready, never poll the database."""
    global _stopping
    _stopping = False
    cfg = get_memory_settings()
    if not cfg.enabled or not cfg.auto_capture_preferences:
        return
    from services.memory.capture_intent import get_capture_intent_store

    for owner, snippet, version in get_capture_intent_store().list_pending():
        _schedule_capture(owner, snippet, version)


async def stop_captures() -> None:
    """Cancel bounded tasks before provider teardown; intents remain on disk."""
    global _stopping
    _stopping = True
    tasks = list(_pending)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
