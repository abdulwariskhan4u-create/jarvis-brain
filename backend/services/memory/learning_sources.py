"""Resolve provenance for explicit agent lessons from the owner's saved history."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from core.database import AgentContextSnapshot
from services.memory.confidence import evidence_supports


def is_team_member(db: Session, owner: str) -> bool:
    from services import shared_state
    registry = shared_state.registry_db
    if registry is not None:
        if any(record.get("session_id") or record.get("team_name")
               for record in registry.find_by_name(owner)):
            return True
    return db.query(AgentContextSnapshot.id).filter(
        AgentContextSnapshot.agent_name == owner,
        AgentContextSnapshot.team_name.isnot(None),
        AgentContextSnapshot.team_name != "",
    ).first() is not None


def _texts(value):
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            yield value["text"]
        for key in ("content", "tool_results"):
            child = value.get(key)
            if key == "tool_results" and isinstance(child, dict):
                child = list(child.values())
            yield from _texts(child)
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)


def verified_learning_sources(db: Session, owner: str, learning: dict | None) -> list[dict]:
    """No agent-supplied source text or another member's history can verify a quote.

Look at only the newest persisted snapshot. Missing/unpersisted evidence means
the proposal waits in task history; it does not become durable memory.
"""
    quote = learning.get("outcome_excerpt") if isinstance(learning, dict) else None
    if not isinstance(quote, str) or not quote.strip() or len(quote) > 400:
        return []
    snapshot = db.query(AgentContextSnapshot).filter_by(agent_name=owner).order_by(
        AgentContextSnapshot.id.desc()).first()
    if snapshot is None:
        return []
    try:
        value = json.loads(snapshot.context_json)
    except (ValueError, TypeError):
        return []
    messages = value.get("messages", []) if isinstance(value, dict) else value
    if not isinstance(messages, list):
        return []
    for message in messages:
        if not isinstance(message, dict):
            continue
        channels = message.get("channels") or {}
        # Previously recalled memory is not fresh experimental evidence.
        if "jarvis:provenance" in channels or "jarvis:recall_ids" in channels:
            continue
        if any(evidence_supports(quote, text) for text in _texts(message)):
            return [{"source_type": "agent_context_snapshot", "source_id": str(snapshot.id),
                     "source_excerpt": quote, "authority": "agent_observed"}]
    return []
