"""Long-term agent memory stores evidenced reusable lessons, not run reports."""
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, MemoryCandidate, MemoryRecord, MemoryVersion
from services.memory import candidate_service as candidates


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite:///:memory:', poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    monkeypatch.setattr('services.memory.knowledge_graph.schedule_extract_and_store', lambda _: None)
    monkeypatch.setattr('services.memory.conflict.schedule_resolve_conflicts', lambda _: None)
    monkeypatch.setattr('core.database.get_db_session', factory)
    yield session
    session.close()
    engine.dispose()


OUTCOME = 'With one owner and an acceptance checklist, clarification messages fell from 12 to 3 and all checks passed.'
LESSON = {
    'problem': 'Unclear handoff caused repeated clarification.',
    'change': 'Assign one owner and agree the acceptance checklist before handoff.',
    'applies_when': 'Delegating work across team roles.',
    'outcome_excerpt': OUTCOME,
}


def payload(**overrides):
    value = dict(memory_type='procedural', content='Before delegation, assign one owner and agree acceptance criteria.',
                 subject_scope='agent:Devon [QE]', authority='agent_observed', learning=LESSON)
    value.update(overrides)
    return value


def propose(db, **overrides):
    return candidates.create_candidate(
        db, owner_agent_name='Devon [QE]', candidate_type='extracted_agent',
        payload=payload(**overrides), confidence=0.99,
        sources=[{'source_type': 'conversation_snippet', 'source_excerpt': OUTCOME}],
    )


@pytest.mark.parametrize('overrides', [
    {'memory_type': 'episodic', 'content': 'Opened the initial screen but did not play the game.'},
    {'learning': None},
    {'learning': {**LESSON, 'applies_when': ''}},
    {'learning': {**LESSON, 'outcome_excerpt': 'All 600-second tests passed.'}},
    {'content': 'long report ' * 100},
])
def test_high_confidence_does_not_replace_learning_value(db, overrides):
    with pytest.raises(ValueError, match='learning'):
        propose(db, **overrides)
    assert db.query(MemoryRecord).count() == 0
    assert db.query(MemoryCandidate).count() == 0


def test_short_verified_workflow_is_saved_with_quality_audit(db):
    candidate = propose(db)
    assert candidate.status == 'auto_approved'
    record = db.query(MemoryRecord).one()
    assert record.subject_scope == 'agent:Devon [QE]'
    metadata = json.loads(db.query(MemoryVersion).one().metadata_json)
    assert metadata['learning'] == LESSON
    assert record.valid_until is None  # Value filtering, no invented default TTL.


def test_user_preference_does_not_need_a_retro_experiment(db):
    candidate = candidates.create_candidate(
        db, owner_agent_name='Jarvis', candidate_type='agent_remember',
        payload=dict(memory_type='semantic', subject_scope='user',
                     content='The user prefers Vietnamese.', authority='user_confirmed'),
    )
    assert candidate.status == 'auto_approved'


def test_compactor_skips_task_report_but_keeps_verified_lesson(db):
    ids = candidates.ingest_compactor_candidates(
        db, owner_agent_name='Devon [QE]', approval_policy='auto_low_risk',
        candidates=[
            {'type': 'episodic', 'content': 'Opened the game screen.', 'explicit': True, 'confidence': 1},
            {'type': 'procedural', 'content': payload()['content'], 'learning': LESSON,
             'evidence_excerpt': OUTCOME, 'explicit': True, 'confidence': 1},
        ],
    )
    # A compactor's unverified quote cannot manufacture durable provenance.
    assert ids == []
    assert db.query(MemoryRecord).count() == 0


async def test_extraction_drops_real_run_report_and_saves_evidenced_workflow(db):
    from services.memory.agent_extractor import run_agent_extraction
    async def generate(_):
        return json.dumps([
            {'kind': 'episodic', 'content': 'Opened the initial screen but did not play the game.',
             'evidence_excerpt': 'Opened the initial screen but did not play the game.'},
            {'kind': 'workflow', 'content': payload()['content'], 'learning': LESSON,
             'evidence_excerpt': OUTCOME, 'reasoning_type': 'direct'},
        ])
    ids = await run_agent_extraction(
        'Devon [QE]', 'Opened the initial screen but did not play the game.\n' + OUTCOME,
        SimpleNamespace(approval_policy='auto_low_risk'), generate_fn=generate,
    )
    assert len(ids) == 1
    assert db.query(MemoryRecord).one().content == payload()['content']


def test_no_learning_gate_bypass_by_agent_remember_or_procedure(db):
    for kind in ('agent_remember', 'procedure', 'compaction_semantic'):
        with pytest.raises(ValueError, match='learning'):
            candidates.create_candidate(
                db, owner_agent_name='Devon [QE]', candidate_type=kind,
                payload=payload(learning=None), requires_approval=True,
            )
    assert db.query(MemoryCandidate).count() == 0


def seed_snapshot(db, owner, quote=OUTCOME, *, recalled=False):
    from core.database import AgentContextSnapshot
    db.add(AgentContextSnapshot(
        agent_name=owner, run_id='test-run', team_name='test-team', trigger='idle',
        context_json=json.dumps({'messages': [
            {'role': 'user', 'tool_results': {'result1': {'content': [{'type': 'text', 'text': quote}]}},
             'channels': {'jarvis:recall_ids': ['old-id']} if recalled else {}},
        ]}),
    ))
    db.commit()


async def test_explicit_team_remember_cannot_default_to_user_scope(db, monkeypatch):
    from services.memory import rpc_handlers
    seed_snapshot(db, 'Devon [QE]')
    monkeypatch.setattr(rpc_handlers, 'get_db_session', lambda: db)
    monkeypatch.setattr(rpc_handlers, 'get_memory_settings', lambda: SimpleNamespace(
        enabled=True, approval_policy='auto_low_risk', pinned_token_budget=1500))
    out = await rpc_handlers.memory_remember(
        agent_name='Devon [QE]', content='The acceptance gate is still open.', subject_scope='user')
    assert out['status'] == 'not_saved'
    assert db.query(MemoryRecord).count() == 0


async def test_explicit_lesson_requires_owned_persisted_evidence(db, monkeypatch):
    from services.memory import rpc_handlers
    seed_snapshot(db, 'Devon [QE]')
    monkeypatch.setattr(rpc_handlers, 'get_db_session', lambda: db)
    monkeypatch.setattr(rpc_handlers, 'get_memory_settings', lambda: SimpleNamespace(
        enabled=True, approval_policy='auto_low_risk', pinned_token_budget=1500))
    out = await rpc_handlers.memory_remember(
        agent_name='Devon [QE]', content=payload()['content'], memory_type='procedural', learning=LESSON)
    assert out['status'] == 'auto_approved'
    assert db.query(MemoryRecord).one().subject_scope == 'agent:Devon [QE]'


@pytest.mark.parametrize('owner,recalled', [('Other [Dev]', False), ('Devon [QE]', True)])
def test_another_agent_or_recalled_memory_is_not_new_experimental_evidence(db, owner, recalled):
    from services.memory.learning_sources import verified_learning_sources
    seed_snapshot(db, owner, recalled=recalled)
    assert verified_learning_sources(db, 'Devon [QE]', LESSON) == []
