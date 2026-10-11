from core.database import TokenUsageRecord, SessionLocal, init_db
from services.sse_progress import _persist_and_broadcast_token_usage
from services.pricing import pricing_source


def test_unknown_alias_is_identified_as_fallback():
    assert pricing_source("coding-agent") == "fallback"
    assert pricing_source("gpt-4o") == "configured"


def test_estimate_persists_provenance_without_rewriting_history():
    init_db()
    with SessionLocal() as db:
        old = TokenUsageRecord(agent_name="old", model="coding-agent", est_cost=1)
        db.add(old)
        db.commit()
        old_id = old.id
    _persist_and_broadcast_token_usage("provenance-test", "run-test", {
        "model": "coding-agent", "total": 100, "input": 90, "output": 10})
    with SessionLocal() as db:
        assert db.get(TokenUsageRecord, old_id).pricing_source is None
        row = db.query(TokenUsageRecord).filter_by(agent_name="provenance-test").one()
        assert row.pricing_source == "fallback"


def test_old_schema_migration_preserves_unverified_history(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    import core.database as database
    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    database.Base.metadata.create_all(legacy)
    with legacy.begin() as connection:
        connection.execute(text("ALTER TABLE token_usage DROP COLUMN pricing_source"))
        connection.execute(text("INSERT INTO token_usage (agent_name,model,category,est_cost) "
                                "VALUES ('legacy-agent','coding-agent','agent',1.25)"))
    monkeypatch.setattr(database, "engine", legacy)
    try:
        database.init_db()
        database.init_db()  # Idempotent upgrade.
        with legacy.connect() as connection:
            row = connection.execute(text("SELECT est_cost,pricing_source FROM token_usage "
                                          "WHERE agent_name='legacy-agent' ")).one()
        assert row.est_cost == 1.25
        assert row.pricing_source is None
    finally:
        legacy.dispose()


def test_live_usage_and_rest_snapshot_share_persisted_identity(monkeypatch):
    import asyncio
    from routes.token_usage import get_token_metrics
    events = []
    monkeypatch.setattr('services.sse_progress._get_activity_stream', lambda: type('Stream', (), {'broadcast': lambda self, event: events.append(event)})())
    init_db()
    _persist_and_broadcast_token_usage('snapshot-test', 'run-test', {
        'model': 'gpt-4o', 'total': 10, 'input': 9, 'output': 1})
    data = asyncio.run(get_token_metrics(period='all', agent='snapshot-test'))
    assert events[-1]['data']['usage_id'] == data['snapshot_id']
    assert events[-1]['data']['created_at'] > 0
    assert data['agent_filter'] == 'snapshot-test'
    assert data['totals']['total_tokens'] == 10
