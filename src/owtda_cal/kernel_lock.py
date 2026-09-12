"""OS-managed kernel file locks for shard/registry transactions.

Task pack (2026-09-13) §2.2 and §5.1.  The previous locking scheme created a
sentinel file ``<path>.lock`` with ``O_CREAT|O_EXCL`` and deleted it in a
``finally`` block.  Two independent defects follow from that design:

* a process killed while holding the lock never runs the ``finally`` block, so
  the sentinel survives and every later writer waits for it forever;
* the sentinel is *deleted* by the holder, so a cleaner (or a second holder
  leaving) can remove the file while another process is waiting on it, which
  lets two callers believe they both hold the lock.

This module hands ownership to the operating system instead: the lock is a
byte-range held on a persistent lock file.  Windows releases it when the owning
process terminates or its handle is closed (with a documented short delay);
POSIX releases it on close.  The lock *file* itself is never deleted, so it
cannot be removed from under a waiter.

Lock ordering is fixed here as well (``shard`` before ``registry``) and is
enforced per thread: acquiring a scope while already holding a later scope is a
programming error and raises, rather than risking a deadlock at run time.
"""

from __future__ import annotations

import errno
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

if os.name == "nt":  # pragma: no cover - platform specific import
    import msvcrt
else:  # pragma: no cover - platform specific import
    import fcntl

LOCK_SUFFIX = ".kernellock"

#: The only legal acquisition order.  Never re-order without a full review: the
#: shard lock guards the payload transaction and the registry lock guards the
#: chain tip, so the shard lock is always taken first.
LOCK_ORDER = ("shard", "registry")

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_POLL = 0.01


class LockError(RuntimeError):
    """Locking contract violation (timeout, bad order, unusable lock file)."""


_state = threading.local()


def _held() -> list[str]:
    stack = getattr(_state, "held", None)
    if stack is None:
        stack = []
        _state.held = stack
    return stack


def lock_path_for(resource_path: str, *, suffix: str = LOCK_SUFFIX) -> str:
    """Persistent lock file that guards ``resource_path``."""
    return f"{resource_path}{suffix}"


def _begin(scope: str) -> None:
    if scope not in LOCK_ORDER:
        raise LockError(f"unknown lock scope {scope!r}; expected one of {LOCK_ORDER}")
    held = _held()
    for already in held:
        if LOCK_ORDER.index(scope) < LOCK_ORDER.index(already):
            raise LockError(
                f"lock order violation: {scope!r} requested while holding "
                f"{already!r}; the fixed order is {LOCK_ORDER}"
            )
    held.append(scope)


def _end(scope: str) -> None:
    held = _held()
    if scope in held:
        held.remove(scope)


def _acquire(fd: int, *, exclusive: bool, deadline: float, poll: float) -> None:
    while True:
        try:
            if os.name == "nt":  # pragma: no cover - platform specific
                os.lseek(fd, 0, os.SEEK_SET)
                # Windows byte-range locks are exclusive only (LK_NBLCK); a shared
                # request degrades to exclusive rather than silently doing less.
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - platform specific
                mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(fd, mode | fcntl.LOCK_NB)
            return
        except OSError as exc:
            # EDEADLK (36) is how Windows reports "another process holds it".
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, 36):
                raise
            if time.monotonic() >= deadline:
                raise LockError("lock timeout: the OS lock was not released in time") from exc
            time.sleep(poll)


def _release(fd: int) -> None:
    try:
        if os.name == "nt":  # pragma: no cover - platform specific
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover - platform specific
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def kernel_lock(
    path: str,
    *,
    scope: str = "registry",
    timeout: float = _DEFAULT_TIMEOUT,
    poll: float = _DEFAULT_POLL,
    exclusive: bool = True,
) -> Iterator[str]:
    """Hold an OS-managed lock on ``path`` for the duration of the block.

    The lock file is created if needed and is deliberately left in place
    afterwards: deleting it would break waiters and re-introduce the old race.
    Ownership is released by the kernel when the handle closes, including when
    the process dies.
    """
    _begin(scope)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == "nt":  # pragma: no cover - platform specific
            # msvcrt locks a byte range; guarantee the range exists so the lock
            # is never taken "past end of file" on an empty file.
            if os.fstat(fd).st_size < 1:
                os.ftruncate(fd, 1)
        _acquire(fd, exclusive=exclusive, deadline=time.monotonic() + timeout, poll=poll)
        try:
            yield path
        finally:
            _release(fd)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    finally:
        _end(scope)


__all__ = [
    "LOCK_ORDER",
    "LOCK_SUFFIX",
    "LockError",
    "kernel_lock",
    "lock_path_for",
]
