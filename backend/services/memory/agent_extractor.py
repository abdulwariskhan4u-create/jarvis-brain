"""Extract team experience without treating MCP/user-role messages as human speech."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from services.memory import fast_extractor

if TYPE_CHECKING:
    from services.memory.settings import MemorySettings

logger = logging.getLogger(__name__)
_ALLOWED_KINDS = frozenset({"workflow", "procedural", "decision"})
_AGENT_PROMPT = """Extract reusable experience for the working AGENT from this team transcript.
Messages may originate from other agents, tools, operator directions, or persisted
context. The user role in this transcript does not establish human authorship.
Agent names and role headers identify team members, NOT the human user.
Extract only a concise lesson that will change future work, backed by an observed
improvement after trying a different approach. Do not
infer personal facts, identities, preferences or standing instructions about the
human user. Task progress, run reports, remaining acceptance gates, untested advice,
generic good practice and instructions to do a current task are NOT lessons.
Do not extract basic tool affordances already covered by tool instructions, such
as reading PNG with a media reader rather than a text reader, or a single denied
call followed by the documented correct call. A success response alone does not
prove a novel workflow or a repeatable improvement. Prefer a concise conditional
coordination rule whose changed workflow was actually tried and improved results.
Example: repeated clarification -> agree owner/output/acceptance before delegation
-> observed fewer clarification messages with the same acceptance quality.
Store the resulting conditional workflow, not each message or the retro transcript.
If the improvement was not tried or has no evidence, return [].
Return only a JSON array, at most 3 lessons. Each item must have kind (workflow|procedural|decision),
content (one conditional lesson, at most 600 characters), evidence_excerpt (an exact
verbatim quote from the transcript), reasoning_type (direct|synthesis|inference),
learning {problem, change, applies_when, outcome_excerpt}, and optional entities.
Each learning field is a nonempty string of at most 400 characters. outcome_excerpt
must quote the observed improvement verbatim and be included in evidence_excerpt.
Never invent measurements, outcomes, confidence, or expiry to justify a save.
ALREADY KNOWN lessons below must not be re-extracted or trivially paraphrased.
Return [] if there is no new, verified reusable experience.
"""


async def run_agent_extraction(
    owner: str,
    snippet: str,
    cfg: MemorySettings,
    *,
    lane: str = "fast",
    generate_fn: Callable[[str], Awaitable[str]] | None = None,
    raise_on_failure: bool = False,
) -> list[str]:
    """Team messages yield agent-scoped knowledge, never user-profile facts.

    Kind and scope are enforced by code even when the model ignores its schema.
    Existing evidence, secret review and configured approval policy still apply.
    """
    if not owner or not snippet.strip():
        return []
    generate = generate_fn or fast_extractor.build_extractor_generate_fn(f"memory:agent:{lane}")
    if generate is None:
        if raise_on_failure:
            raise RuntimeError("Agent learning extractor is unavailable")
        return []
    try:
        known = fast_extractor._known_facts(owner, limit=12)
        prompt = _AGENT_PROMPT + "\n\nALREADY KNOWN:\n" + "\n".join(known)
        raw = await generate(prompt + "\n\nTeam transcript:\n" + snippet)
    except Exception:
        logger.warning("[MEMORY] Agent experience extraction failed for %s", owner, exc_info=True)
        if raise_on_failure:
            raise
        return []
    memories = [
        m for m in fast_extractor.parse_extraction(raw, strict=raise_on_failure)
        if m.kind in _ALLOWED_KINDS
    ][:3]
    if not memories:
        return []
    return fast_extractor._persist_candidates(
        owner, memories, cfg, "extracted_agent", snippet=snippet,
        subject_scope=f"agent:{owner}",
    )
