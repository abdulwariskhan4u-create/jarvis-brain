"""Extract team experience without treating MCP/user-role messages as human speech."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from services.memory import fast_extractor

if TYPE_CHECKING:
    from services.memory.settings import MemorySettings

logger = logging.getLogger(__name__)
_ALLOWED_KINDS = frozenset({"workflow", "procedural", "episodic", "decision"})
_AGENT_PROMPT = """Extract reusable experience for the working AGENT from this team transcript.
Messages may originate from other agents, tools, operator directions, or persisted
context. The user role in this transcript does not establish human authorship.
Agent names and role headers identify team members, NOT the human user.
Extract reusable procedures, verified work outcomes and decisions only. Do not
infer personal facts, identities, preferences or standing instructions about the
human user. Omit unsupported claims and transient task/status messages.
Return only a JSON array. Each item must have kind (workflow|procedural|episodic|decision),
content (a clear statement about the agent's experience), evidence_excerpt (an exact
verbatim quote from the transcript), reasoning_type (direct|synthesis|inference),
and optional entities. Return [] if there is no reusable experience.
"""


async def run_agent_extraction(
    owner: str,
    snippet: str,
    cfg: MemorySettings,
    *,
    lane: str = "fast",
    generate_fn: Callable[[str], Awaitable[str]] | None = None,
) -> list[str]:
    """Team messages yield agent-scoped knowledge, never user-profile facts.

    Kind and scope are enforced by code even when the model ignores its schema.
    Existing evidence, secret review and configured approval policy still apply.
    """
    if not owner or not snippet.strip():
        return []
    generate = generate_fn or fast_extractor.build_extractor_generate_fn(f"memory:agent:{lane}")
    if generate is None:
        return []
    try:
        raw = await generate(_AGENT_PROMPT + "\n\nTeam transcript:\n" + snippet)
    except Exception:
        logger.warning("[MEMORY] Agent experience extraction failed for %s", owner, exc_info=True)
        return []
    memories = [m for m in fast_extractor.parse_extraction(raw) if m.kind in _ALLOWED_KINDS]
    if not memories:
        return []
    return fast_extractor._persist_candidates(
        owner, memories, cfg, "extracted_agent", snippet=snippet,
        subject_scope=f"agent:{owner}",
    )
