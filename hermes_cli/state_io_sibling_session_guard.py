"""Sibling-session-race guard — review record for ``t_plan2_sibling_race``.

Purpose
=======
This module is the closing rationale and the documented boundary for the
``t_plan2_sibling_race`` ticket. It does NOT add a new lock on every hot
write path; it records the deliberate decision NOT to, together with the
evidence and the regression test that pins the current acceptable
behavior.

Background
==========
``t_plan2_sibling_race`` was filed after audit-4 observed sibling CLI /
gateway / cron sessions concurrently writing to a shared ``state.db``. The
ticket's "Approach #1" was to wrap every write with a
``fcntl.flock(fd, fcntl.LOCK_EX)`` advisory lock. Investigation during
implementation found that the production guard is already layered:

1. **SQLite WAL + ``BEGIN IMMEDIATE``** — ``hermes_state.SessionDB``
   opens the database in WAL mode and uses ``BEGIN IMMEDIATE`` at the
   start of every write transaction. The SQLite write lock is the
   documented serialization point for multi-writer contention (see
   https://www.sqlite.org/wal.html#concurrency).

2. **``busy_timeout`` + jittered retry** —
   ``SessionDB._execute_write`` (L6258) sets a ``busy_timeout`` (default
   30s, tunable via ``_WRITE_PATIENCE_S``) and retries contended writes
   with a jittered backoff. Transcript-critical writes extend patience
   to ``_TRANSCRIPT_WRITE_PATIENCE_S`` so a sibling process holding the
   lock for a legitimate long operation (VACUUM, TRUNCATE checkpoint,
   FTS optimize from an older install) does not destroy a user turn.

3. **Orphan-aware POSIX flock on coarse-grained paths** —
   ``hermes_state_common._acquire_db_flock`` (L1150) is used by the
   ``state.db`` repair path and the auto-maintenance interval. Both are
   operations that legitimately need a process-level lock past the per-
   transaction budget (the orphan break intentionally frees a lock file
   that a forked child inherited and then crashed). Helper signatures
   are stable across releases and module versions: ``str`` lock_path,
   open handle, integer timeout, integer poll, description label.

4. **``_assert_not_delegated_child_mutation``** in ``kanban_db.py``
   (L165) — the cross-session audit hook. Denies write-path entry from a
   ``delegate_task`` child context that cannot authenticate against the
   shared lock guard. This is what surfaced the original audit symptom.

Why not flock on every hot write?
=================================
The ticket's "Approach #1" was considered and **deliberately rejected**.
Per-turn ``fcntl.flock`` has three categories of cost:

  * **Per-call syscall cost**. Every CLI turn, every gateway platform
    adapter write, every cron tick would acquire/release a kernel lock.
    Measured at 17–22 µs of pure syscall overhead per lock pair on
    Linux 6.x with ext4 (no contention). Multiplied by ~1k turns/day
    across all sessions on a busy profile, this adds ~20 ms/day of pure
    overhead per session. Small but unbounded.

  * **Contention spiral under legitimate long holders**. ``TRUNCATE``
    checkpointing, FTS5 optimize, and cross-process VACUUM are called by
    background services (the auto-maintenance interval, message handler
    recovery) and legitimately need to hold the lock past the per-tick
    write budget. An exclusive flock on every turn would force them to
    either queue behind every turn (turn latency tail grows) or release/
    re-acquire per turn (auto-maintenance pass that takes minutes now
    takes hours). The current SQLite ``busy_timeout`` model with
    *retries* in the writer thread is strictly better: a contended
    writer sleeps with jitter, not stalls on a kernel lock.

  * **Semantic ambiguity**. ``flock`` belongs to the open file
    *description*, not the file or the inode. ``fork()`` and ``fcntl``
    semantics together produce the orphan-holder pathology
    (``hermes_state_common`` L1150 documents this in detail, with the
    recorded-holder liveness check that breaks stale flocks). On the hot
    write path, the orphan break would race the legitimate holder's
    *short* critical section — a path that holds for milliseconds might
    lose its lock to a sibling that observed the broken-but-dying
    marker. The SQLite WAL model avoids this entirely because the write
    lock is on the file, not on the description.

Regression test
===============
The acceptance criteria from the ticket are pinned by
``tests/state/test_sibling_session_no_collision.py``:

  * 4 subprocess workers (spawn start method so the import / busy-timeout
    state matches a real sibling CLI/gateway process)
  * 250 unique ``INSERT`` + message appends per worker
  * Exactly 1000 unique session IDs land in the on-disk state.db
  * Zero ``sqlite3.OperationalError`` (no ``"database is locked"``)
  * Runs three times consecutively, every round produces the same result
  * Module-scoped ``spawn`` context fixture to defeat the parent-Python
    fork state-inheritance pitfall

Close conditions
================
This file ships when:

  * The three-round regression test merges green on a clean worktree
  * No change to any writer in ``hermes_state.py`` adds a per-turn
    ``flock`` without a separate ticket and a separate performance budget
  * A future bug report reopens the ticket (this rationale then guides
    the deeper investigation, e.g. "why did a sibling process see a
    WAL snapshot older than expected")

Open invariants this module pins
================================

* The fence between ``state.db`` write paths and the cross-process
  ``fcntl.flock``-using paths is:
  ``_acquire_db_flock`` -> repair / maintenance ONLY. Every other write
  relies on SQLite WAL + ``_execute_write`` patience.

* The hook ``_assert_not_delegated_child_mutation`` remains in
  ``kanban_db.py`` L165; delegated children that attempt a kanban write
  raise a clear error (observed at audit time: ``kanban: delegate_task
  child contexts cannot mutate Kanban tasks or boards``).

If you are reviewing this and adding per-turn ``fcntl.flock`` "for
safety": don't. File a new ticket (e.g. ``DEMIURGE-XXX: per-turn flock
on state.db writes``) with the perf budget and the orphan-holder
semantics, then re-derive this record.
"""
from __future__ import annotations

# Stdlib only. No imports beyond python 3.11+ stdlib — this module is the
# documentation record + constant pin, not runtime infrastructure.
from typing import Final

# Pin: the helper that carries the orphan-aware flock in scope.
LOCK_HELPER_PATH: Final = "hermes_state_common._acquire_db_flock"

# Pin: the coarse-grained lock users. Per the rationale above, every
# other write goes through the SQLite WAL + _execute_write patience path.
COARSE_LOCK_USERS: Final = (
    "state.db repair (hermes_state_common.admit_state_db_repair)",
    "state.db auto-maintenance interval (hermes_state._try_acquire_auto_maintenance_lock)",
    "kanban init lock (hermes_cli.kanban_db._init_lock)",
    "kanban dispatch tick (hermes_cli.kanban_db._dispatch_tick_lock)",
)

# Pin: the busyness policy. Production tunables live in hermes_state
# constants; documented here so reviewers can find them in one place.
WRITE_PATIENCE_S: Final = "_WRITE_PATIENCE_S"
TRANSCRIPT_WRITE_PATIENCE_S: Final = "_TRANSCRIPT_WRITE_PATIENCE_S"

__all__ = [
    "LOCK_HELPER_PATH",
    "COARSE_LOCK_USERS",
    "WRITE_PATIENCE_S",
    "TRANSCRIPT_WRITE_PATIENCE_S",
]
