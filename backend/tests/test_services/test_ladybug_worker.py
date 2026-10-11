"""Native crashes must not kill the backend or discard SQLite truth."""
import os
import signal
import pytest


def test_native_worker_crash_is_contained_and_can_reopen(tmp_path):
    pytest.importorskip("ladybug")
    from services.indexing.ladybug_worker import IsolatedLadybugStore, GraphUnavailable
    store = IsolatedLadybugStore(str(tmp_path / "graph"), cooldown=0)
    try:
        assert store.count() == 0
        pid = store.worker_pid
        assert pid != os.getpid()
        os.kill(pid, signal.SIGKILL)
        store._process.join(timeout=5)
        with pytest.raises(GraphUnavailable):
            store.count()
        assert store.count() == 0
        assert store.worker_pid != pid
    finally:
        store.close()


def test_stalled_native_worker_is_bounded_and_recoverable(tmp_path):
    pytest.importorskip("ladybug")
    from services.indexing.ladybug_worker import IsolatedLadybugStore, GraphUnavailable
    store = IsolatedLadybugStore(str(tmp_path / "graph"), cooldown=0)
    try:
        pid = store.worker_pid
        os.kill(pid, signal.SIGSTOP)
        store._timeout = 0.05
        with pytest.raises(GraphUnavailable, match="timed out"):
            store.count()
        store._timeout = 30
        assert store.count() == 0
        assert store.worker_pid != pid
    finally:
        store.close()


def test_closed_worker_rejects_new_requests(tmp_path):
    pytest.importorskip("ladybug")
    from services.indexing.ladybug_worker import IsolatedLadybugStore, GraphUnavailable
    store = IsolatedLadybugStore(str(tmp_path / "graph"))
    store.close()
    store.close()
    assert store.worker_pid is None
    with pytest.raises(GraphUnavailable, match="closed"):
        store.count()
