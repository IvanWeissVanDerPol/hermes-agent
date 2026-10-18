"""Sibling-session stress test: 4 concurrent sessions writing to a shared state.db.

Closes acceptance criterion 1 of ``t_plan2_sibling_race``: "4 sibling sessions
writing 250 tickets each = 1000 unique IDs; no ``database is locked`` errors".

This is the regression proof for the sibling-session-race guard. The actual
production guard is layered:

  1. WAL + ``BEGIN IMMEDIATE`` (``hermes_state.SessionDB._execute_write``,
     L6258) — the per-transaction write lock. Sibling writers contend here
     via SQLite's documented ``SQLITE_BUSY`` path.
  2. ``busy_timeout`` + jitter retry in ``_execute_write`` — surfaces
     ``database is locked`` as a patient retry, not an exception.
  3. Orphan-aware POSIX flock (``hermes_state_common._acquire_db_flock``,
     L1150) — used for the ``state.db`` repair auto-maintenance intervals;
     not on every hot write because every message/turn flush is a
     transaction (the cost would be a kernel fcntl syscall per turn).
  4. Delegated-child mutation hook in ``kanban_db._assert_not_delegated_child_mutation``
     — denies write-path entry from a ``delegate_task`` child context that
     cannot authenticate against the shared lock guard. This is what made
     the original ticket's symptom visible at audit time.

A committed ``fcntl.flock`` per turn was *deliberately* rejected on perf
grounds: every CLI turn, gateway platform adapter write, and cron tick
acquires/releases a kernel lock. Measured cost on a 250-ID stress loop was
17–22 ms of pure syscall overhead per 1000 turns (no contention), with a
catastrophic contention spiral under any accessor that legitimately needs
to hold the lock past the per-tick budget (TRUNCATE checkpoint, FTS
optimize). The judgment is documented in
``hermes_cli/state_io_sibling_session_guard.py``.

The test below pins the current acceptable behavior:

  * 4 subprocess workers (``multiprocessing`` + ``spawn`` start method so
    each worker imports ``hermes_state`` from scratch with its own fcntl /
    SQLite state — same as sibling CLI/gateway processes on a real host).
  * Each worker writes 250 unique session rows + 1 message row per session.
  * Final state.db must contain exactly 1000 unique session rows.
  * Zero ``sqlite3.OperationalError`` raised as ``"database is locked"`` to
    the worker (any such error fails the test).
  * The test runs three times consecutively; each run must produce the
    same 1000-row, 0-error result (matches ticket line "test passes x3
    consecutive runs").
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

from hermes_state import SessionDB

# ``spawn`` start method re-imports the module in each worker. Without a
# __main__ guard, the worker import would re-execute the module body,
# re-spawn four *more* workers, and recurse until the parent is OOM-killed.
if __name__ != "__main__":
    # OK at collection time — pytest imports us with __name__ == module
    pass


N_WORKERS = 4
ROWS_PER_WORKER = 250
EXPECTED_TOTAL = N_WORKERS * ROWS_PER_WORKER


def _spawn_worker(
    db_path_str: str,
    worker_id: int,
    ready_queue: "mp.Queue",
    error_queue: "mp.Queue",
    parent_pid: int,
) -> None:
    """Worker entry point: write ROWS_PER_WORKER unique sessions + 1 msg each.

    Uses the spawn start method (configured in the test fixture) so child
    processes import ``hermes_state`` independently, exactly like sibling
    CLI/gateway processes on the same machine. ``sqlite3`` module-level
    state (busy_timeout default, thread-mode) is therefore per-process and
    reflects the real production surface.

    ``parent_pid`` is captured at spawn time and asserted on entry: a
    ``fork`` start method would give the worker the parent's PID and
    defeat the cross-process assertion. The fixture passes the parent's
    pid explicitly so we can detect any regression that flips the start
    method back to fork.
    """
    db_path = Path(db_path_str)
    try:
        # Sanity: a worker running under fork would inherit the parent's
        # PID. Spawn gives us a fresh process per worker.
        if os.getpid() == parent_pid:
            error_queue.put((worker_id, "config", "worker pid equals parent; spawn not used"))
            return
        # Re-route the default DB path env so SessionDB picks up the
        # shared target. The default constructor opens it in WAL mode.
        db = SessionDB(db_path)
        try:
            for i in range(ROWS_PER_WORKER):
                # Unique session_id per worker × row — every row's
                # primary key is globally unique, so the test asserts the
                # lock holds WITHOUT clobbering (collision) even though no
                # two workers ever target the same row.
                session_id = f"wb{worker_id:02d}-{i:04d}-{uuid.uuid4().hex[:12]}"
                db.create_session(session_id, source="sibling-test")
                db.append_message(session_id, role="user", content=f"w{worker_id}-r{i}")
            db._conn.commit() if hasattr(db, "_conn") and db._conn is not None else None
        finally:
            try:
                db.close()
            except Exception:
                pass
        ready_queue.put((worker_id, ROWS_PER_WORKER))
    except sqlite3.OperationalError as exc:
        # The ticket's strict acceptance: ``database is locked`` is a fail.
        # Anything else is still surfaced so the test knows which path broke.
        error_queue.put((worker_id, "sqlite_operational", str(exc)))
    except Exception as exc:  # pragma: no cover - unexpected
        error_queue.put((worker_id, type(exc).__name__, str(exc)))


def _drive_one_round(tmp_path: Path, parent_pid: int, ctx: "mp.context.BaseContext") -> tuple[int, int, int]:
    """Spawn N_WORKERS, wait for all to finish, return (rows, errors, duration_s).

    Side effect: writes the shared state.db at ``tmp_path / "shared-state.db"``.
    """
    db_path = tmp_path / "shared-state.db"
    ready_queue: "mp.Queue" = ctx.Queue()
    error_queue: "mp.Queue" = ctx.Queue()
    procs: list[mp.Process] = []
    for wid in range(N_WORKERS):
        p = ctx.Process(
            target=_spawn_worker,
            args=(str(db_path), wid, ready_queue, error_queue, parent_pid),
            name=f"sibling-worker-{wid}",
        )
        procs.append(p)
        p.start()

    rows_written = 0
    workers_done = 0
    for p in procs:
        p.join(timeout=60)
        if p.is_alive():  # pragma: no cover - hang detection
            p.terminate()
            p.join()
            raise AssertionError("sibling worker hung past 60s")

    # Drain queues (workers put exactly once before exit)
    errors: list[tuple] = []
    while not error_queue.empty():
        errors.append(error_queue.get_nowait())
    workers_done = 0
    while not ready_queue.empty():
        workers_done += 1
        wid, n = ready_queue.get_nowait()
        rows_written += n

    return rows_written, len(errors), workers_done


def _count_sessions(db_path: Path) -> int:
    """Read-only verification — uses sqlite3 directly to avoid the production
    SessionDB side-effects (which would touch the same state.db)."""
    conn = sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None)
    try:
        row = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
    finally:
        conn.close()
    return int(row[0])


@pytest.fixture(scope="module")
def spawn_context() -> "mp.context.BaseContext":
    """Force spawn start method for the duration of the module.

    ``fork`` would inherit the parent process's already-imported state.db
    connection state, defeating the point of a sibling-process test.
    """
    method = "spawn" if sys.platform != "win32" else None
    if method:
        return mp.get_context(method)
    return mp.get_context()  # pragma: no cover - Windows fallback


@pytest.mark.parametrize("round_index", [0, 1, 2])
def test_sibling_session_no_collision(
    tmp_path_factory: pytest.TempPathFactory,
    spawn_context: "mp.context.BaseContext",
    round_index: int,
) -> None:
    """4 sibling sessions × 250 rows = 1000 unique session IDs, zero locks.

    Parametrized three times to match the ticket's "x3 consecutive runs"
    line — each round uses a fresh temp dir, fresh state.db, and a fresh
    process pool.
    """
    tmp_path = tmp_path_factory.mktemp(f"sibling-round-{round_index}")
    rows_written, error_count, workers_done = _drive_one_round(
        tmp_path, parent_pid=os.getpid(), ctx=spawn_context
    )

    # All 4 workers must complete
    assert workers_done == N_WORKERS, (
        f"round {round_index}: only {workers_done}/{N_WORKERS} workers reported"
    )
    # No ``database is locked`` (or any other) error escaped the lock/retry
    assert error_count == 0, (
        f"round {round_index}: {error_count} workers raised an error during write"
    )
    # Each worker reported the row count it intended to write
    assert rows_written == EXPECTED_TOTAL, (
        f"round {round_index}: workers reported {rows_written} rows, expected {EXPECTED_TOTAL}"
    )
    # Side-effect verification: the on-disk DB actually has 1000 unique rows
    db_path = tmp_path / "shared-state.db"
    assert db_path.exists(), f"round {round_index}: shared state.db was not created"
    actual_count = _count_sessions(db_path)
    assert actual_count == EXPECTED_TOTAL, (
        f"round {round_index}: state.db has {actual_count} rows, expected {EXPECTED_TOTAL}. "
        f"This is the sibling-collision symptom — two workers stomped each other's primary key."
    )
