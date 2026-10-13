"""Admission contract for long-term agent learning, independent of confidence.

Task state already survives in context snapshots and compaction summaries.
It must not also become permanent memory merely because it is true.
The capture lane judges usefulness; this gate requires a concise, evidenced
change in future behaviour before any candidate or approval card is created.
"""
from __future__ import annotations

from services.memory.confidence import evidence_supports

MAX_LESSON_CHARS = 600
MAX_DETAIL_CHARS = 400
_FIELDS = ("problem", "change", "applies_when", "outcome_excerpt")


class LearningAdmissionError(ValueError):
    """A proposal belongs in task history, or lacks verified reusable value."""


def validate_learning(payload: dict, sources: list[dict] | None) -> None:
    """Enforce the same contract for every agent-scoped candidate lane.

Human profile facts/preferences have a separate durable-fact extractor;
they do not require an engineering experiment. No expiry is invented here.
Provenance must come from the backend capture lane, not an LLM confidence.
"""
    if not str(payload.get("subject_scope", "")).startswith("agent:"):
        return
    # A trusted human write can deliberately establish an agent's instruction;
    # autonomous capture lanes always supply agent_observed, never this authority.
    if payload.get("authority") == "user_confirmed":
        return
    if payload.get("memory_type") not in {"procedural", "semantic"}:
        raise LearningAdmissionError("learning: task episodes belong in session history")
    content = payload.get("content")
    if not isinstance(content, str) or not 1 <= len(content.strip()) <= MAX_LESSON_CHARS:
        raise LearningAdmissionError("learning: summarize one reusable lesson in at most 600 characters")
    learning = payload.get("learning")
    if not isinstance(learning, dict):
        raise LearningAdmissionError("learning: provide problem, change, applies_when and outcome_excerpt")
    for field in _FIELDS:
        value = learning.get(field)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= MAX_DETAIL_CHARS:
            raise LearningAdmissionError(f"learning: {field} must be a concise nonempty statement")
    # Never treat an arbitrary compactor/tool argument as verified evidence.
    # Capture lanes assemble these source excerpts from persisted/transcript data.
    quote = learning["outcome_excerpt"]
    if not any(evidence_supports(quote, source.get("source_excerpt", ""))
               for source in sources or []):
        raise LearningAdmissionError("learning: observed improvement has no verified source excerpt")
