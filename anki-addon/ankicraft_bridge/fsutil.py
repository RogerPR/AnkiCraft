"""File helpers that survive Windows file locking.

On Windows a file can't be replaced while another program (WoW loading its
addons after /reload, an antivirus scanner, a backup tool) has it open, and
os.replace then raises PermissionError / WinError 5 or 32. macOS and Linux
don't have this problem. We write to a unique temp file and retry the final
rename for a few seconds.
"""

from __future__ import annotations

import errno
import os
import time

# WinError 5 = access denied, 32 = sharing violation, 33 = lock violation
_WIN_LOCK_ERRORS = {5, 32, 33}


def is_lock_error(e: OSError) -> bool:
    if isinstance(e, PermissionError):
        return True
    if getattr(e, "winerror", None) in _WIN_LOCK_ERRORS:
        return True
    return e.errno in (errno.EACCES, errno.EBUSY)


def replace(src: str, dst: str, timeout: float = 3.0, delay: float = 0.1, _sleep=time.sleep) -> None:
    """os.replace with retries while the destination is locked."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.replace(src, dst)
            return
        except OSError as e:
            if not is_lock_error(e) or time.monotonic() >= deadline:
                try:
                    os.remove(src)
                except OSError:
                    pass
                raise
            _sleep(delay)


def write_atomic(path: str, data: bytes | str, timeout: float = 3.0) -> None:
    """Write a file so readers never see a half-written version."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    replace(tmp, path, timeout=timeout)


def read_bytes(path: str, timeout: float = 2.0, delay: float = 0.1, _sleep=time.sleep) -> bytes:
    """Read a file, retrying while another program holds an exclusive lock."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError as e:
            if isinstance(e, FileNotFoundError) or not is_lock_error(e) or time.monotonic() >= deadline:
                raise
            _sleep(delay)
