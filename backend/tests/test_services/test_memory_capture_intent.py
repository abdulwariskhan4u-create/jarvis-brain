"""Pending extraction must survive shutdown; completion cannot erase newer work."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services.memory.capture_intent import CaptureIntentStore


def test_restart_recovers_latest_owner_intent_and_old_completion_cannot_delete_it(
    tmp_path,
):
    engine = create_engine("sqlite:///" + str(tmp_path / "capture.db"))
    factory = sessionmaker(bind=engine)
    store = CaptureIntentStore(factory)
    first = store.put("QE", "first transcript")
    latest = store.put("QE", "newer transcript")
    restarted = CaptureIntentStore(factory)
    assert restarted.list_pending() == [("QE", "newer transcript", latest)]
    restarted.complete("QE", first)
    assert restarted.list_pending() == [("QE", "newer transcript", latest)]
    restarted.complete("QE", latest)
    assert restarted.list_pending() == []


def test_owner_isolation_and_bounds(tmp_path):
    import pytest

    factory = sessionmaker(
        bind=create_engine("sqlite:///" + str(tmp_path / "capture.db"))
    )
    store = CaptureIntentStore(factory)
    store.put("QE", "browser result")
    store.put("Dev", "build result")
    with pytest.raises(ValueError):
        store.put("QE", "x" * 65537)
    assert {r[0] for r in store.list_pending()} == {"QE", "Dev"}


async def test_shutdown_cancellation_keeps_intent_then_recovery_drains_it(
    tmp_path, monkeypatch
):
    import asyncio
    from types import SimpleNamespace
    from services.memory import spawn_handlers as h

    factory = sessionmaker(
        bind=create_engine("sqlite:///" + str(tmp_path / "capture.db"))
    )
    store = CaptureIntentStore(factory)
    monkeypatch.setattr(
        "services.memory.capture_intent.get_capture_intent_store", lambda: store
    )
    monkeypatch.setattr(
        h,
        "get_memory_settings",
        lambda: SimpleNamespace(enabled=True, auto_capture_preferences=True),
    )
    started = asyncio.Event()

    async def hanging(**kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(h, "capture", hanging)
    version = store.put("Restart QE", "verified transcript")
    h.recover_capture_intents()
    await asyncio.wait_for(started.wait(), 0.5)
    await h.stop_captures()
    assert store.get("Restart QE") == ("Restart QE", "verified transcript", version)
    calls = []

    async def completed(**kwargs):
        calls.append(kwargs)
        return {"candidate_ids": []}

    monkeypatch.setattr(h, "capture", completed)
    h.recover_capture_intents()
    await asyncio.gather(*h._pending)
    await asyncio.sleep(0)
    assert calls == [{"agent_name": "Restart QE", "snippet": "verified transcript"}]
    assert store.list_pending() == []


async def test_provider_failure_retains_intent_without_retry_loop(
    tmp_path, monkeypatch
):
    import asyncio
    from types import SimpleNamespace
    from services.memory import spawn_handlers as h

    factory = sessionmaker(
        bind=create_engine("sqlite:///" + str(tmp_path / "capture.db"))
    )
    store = CaptureIntentStore(factory)
    monkeypatch.setattr(
        "services.memory.capture_intent.get_capture_intent_store", lambda: store
    )
    monkeypatch.setattr(
        h,
        "get_memory_settings",
        lambda: SimpleNamespace(enabled=True, auto_capture_preferences=True),
    )
    calls = []

    async def unavailable(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(h, "capture", unavailable)
    version = store.put("Failure QE", "saved source")
    h.recover_capture_intents()
    await asyncio.gather(*h._pending)
    await asyncio.sleep(0)
    assert len(calls) == 1
    assert store.get("Failure QE") == ("Failure QE", "saved source", version)


async def test_strict_extractor_does_not_report_provider_error_as_empty_success(
    monkeypatch,
):
    import pytest
    from services.memory.agent_extractor import run_agent_extraction

    async def unavailable(_prompt):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "services.memory.fast_extractor._known_facts", lambda *a, **k: []
    )
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await run_agent_extraction(
            "QE", "transcript", None, generate_fn=unavailable, raise_on_failure=True
        )


async def test_strict_capture_rejects_malformed_response_but_accepts_empty_array(monkeypatch):
    import pytest
    from services.memory.agent_extractor import run_agent_extraction

    monkeypatch.setattr("services.memory.fast_extractor._known_facts", lambda *a, **k: [])
    for response in ("", "provider error", "[{broken}]", "[42]", '[{"content": ""}]'):
        async def generate(_prompt):
            return response

        with pytest.raises(ValueError, match="Invalid extraction"):
            await run_agent_extraction("QE", "transcript", None, generate_fn=generate, raise_on_failure=True)

    async def empty(_prompt):
        return "[]"

    assert await run_agent_extraction("QE", "transcript", None, generate_fn=empty, raise_on_failure=True) == []
