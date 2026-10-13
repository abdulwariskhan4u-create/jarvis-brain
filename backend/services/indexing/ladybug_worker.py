"""Run the optional native graph projection outside the backend process.

SQLite remains authoritative. A SIGSEGV/timeout becomes a recoverable lane
failure; writes are retried by the durable outbox, never replayed here.
"""
from __future__ import annotations

import atexit
import faulthandler
import logging
import multiprocessing
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)
_METHODS = frozenset({"upsert_memory", "delete_memory", "purge_owner", "link_entity",
                     "link_relations", "vector_search", "linked_memories",
                     "query_anchored_memories", "count", "probe_index_healthy",
                     "graph_dump", "checkpoint", "rebuild_vector_index"})


class GraphUnavailable(RuntimeError):
    """The optional native projection failed; callers retain SQLite/FTS."""


def _serve(connection, path: str) -> None:
    faulthandler.enable()  # Native failures report Python call sites without payload contents.
    # No embedding model, agent runtime, or shared native libraries load here.
    from services.indexing.ladybug_store import LadybugStore
    store = None
    try:
        store = LadybugStore(path)
        connection.send((True, None))
        while True:
            method, args, kwargs = connection.recv()
            if method == "close":
                break
            try:
                if method not in _METHODS:
                    raise ValueError("Unsupported graph operation")
                connection.send((True, getattr(store, method)(*args, **kwargs)))
            except Exception as exc:
                connection.send((False, f"{type(exc).__name__}: {exc}"))
    except EOFError:
        pass
    except Exception as exc:
        try:
            connection.send((False, f"{type(exc).__name__}: {exc}"))
        except (OSError, EOFError):
            pass
    finally:
        if store is not None:
            store.close()
        connection.close()


class IsolatedLadybugStore:
    """One serialized, persistent native worker per backend; bounded failure."""

    def __init__(self, path: str, *, timeout: float = 30, cooldown: float = 30):
        self._path = path
        self._timeout = timeout
        self._cooldown = cooldown
        self._retry_at = 0.0
        self._lock = threading.RLock()
        self._process = None
        self._connection = None
        self._closed = False
        self._start()
        atexit.register(self.close)

    @property
    def worker_pid(self) -> int | None:
        return self._process.pid if self._process else None

    def _start(self) -> None:
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=_serve, args=(child, self._path), daemon=True)
        self._connection, self._process = parent, process
        try:
            process.start()
            child.close()
            self._receive()
        except Exception:
            child.close()
            self._discard()
            raise

    def _receive(self) -> Any:
        try:
            if not self._connection.poll(self._timeout):
                raise GraphUnavailable("Native graph worker timed out")
            ok, value = self._connection.recv()
        except (EOFError, OSError) as exc:
            raise GraphUnavailable("Native graph worker exited unexpectedly") from exc
        if not ok:
            raise RuntimeError(value)
        return value

    def _discard(self) -> None:
        if self._connection:
            self._connection.close()
        process = self._process
        if process:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            process.close()
        self._connection = self._process = None
        self._retry_at = time.monotonic() + self._cooldown

    def _call(self, method: str, *args, **kwargs) -> Any:
        with self._lock:
            if self._closed:
                raise GraphUnavailable("Native graph store is closed")
            if self._process is None:
                if time.monotonic() < self._retry_at:
                    raise GraphUnavailable("Native graph recovery is cooling down")
                self._start()
            try:
                if not self._process.is_alive():
                    raise GraphUnavailable("Native graph worker crashed")
                self._connection.send((method, args, kwargs))
                return self._receive()
            except (GraphUnavailable, OSError, EOFError) as exc:
                # EOF can arrive just before the OS records the child exit. Capture
                # its real exit code before _discard clears/reaps the process.
                self._process.join(timeout=0.2)
                diagnostic = f"{exc} (pid={self._process.pid}, exitcode={self._process.exitcode})"
                logger.error("[MEMORY] %s failed in native worker: %s; SQLite/FTS retained",
                             method, diagnostic)
                self._discard()
                raise GraphUnavailable(diagnostic) from exc

    def __getattr__(self, name: str):
        if name in _METHODS:
            return lambda *args, **kwargs: self._call(name, *args, **kwargs)
        raise AttributeError(name)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._process and self._process.is_alive():
                try:
                    self._connection.send(("close", (), {}))
                    self._process.join(timeout=2)
                except (OSError, EOFError):
                    pass
            self._discard()
        atexit.unregister(self.close)
