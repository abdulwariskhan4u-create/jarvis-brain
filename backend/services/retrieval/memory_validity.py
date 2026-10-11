"""Validate projected/cached evidence against authoritative SQLite at read time."""
from __future__ import annotations

from dataclasses import replace

from sqlalchemy.orm import Session

from core.database import EpisodicDocument, MemoryRecord
from services.retrieval.contracts import Evidence, EvidenceSource


def current_memory(record: MemoryRecord, *, owner: str, now: float) -> bool:
    return (record.owner_agent_name == owner and record.status == "active"
            and (record.valid_from is None or record.valid_from <= now)
            and (record.valid_until is None or now < record.valid_until))


def authorize_memory_evidence(db: Session, evidence: list[Evidence], *, owner: str,
                              now: float) -> list[Evidence]:
    """A delayed/failed index delete or hot cache must never revive old memory.

Batch reads, including at cache hits; projection availability cannot authorize
content. Native episodic hits also resolve to their owned immutable documents.
"""
    ids = {e.record_id for e in evidence if e.source.type == "memory_record"}
    if not ids:
        return evidence
    records = {r.id: r for r in db.query(MemoryRecord).filter(MemoryRecord.id.in_(ids)).all()}
    episodic = {r.id: r for r in db.query(EpisodicDocument).filter(
        EpisodicDocument.id.in_(ids - records.keys()),
        EpisodicDocument.owner_agent_name == owner,
    ).all()}
    authorized = []
    for item in evidence:
        if item.source.type != "memory_record":
            authorized.append(item)
            continue
        record = records.get(item.record_id)
        if record is not None:
            if current_memory(record, owner=owner, now=now):
                authorized.append(replace(item, excerpt=(record.content or "")[:400],
                                          valid_from=record.valid_from, valid_until=record.valid_until))
        else:
            document = episodic.get(item.record_id)
            if document is not None and item.memory_type == "episodic":
                authorized.append(replace(item, excerpt=(document.content or "")[:400],
                                          source=EvidenceSource("session_message", document.source_id,
                                                                document.created_at or 0)))
    return authorized
