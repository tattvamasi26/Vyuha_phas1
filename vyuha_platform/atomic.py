"""Write a JSON file so it is never left half-written.

The platform keeps its state in JSON files rather than a database, which is the
right call at founder-operated scale — but it came with a bug that only shows up
once more than one thing is writing: ``path.write_text(...)`` truncates the file
and then writes. Two writers, or one writer and a crash, and the file on disk is
a shorter document followed by the tail of a longer one. It parses as
``JSONDecodeError: Extra data`` and every screen that reads it goes blank.

That is not hypothetical. It happened here with a browser tab open beside a test
run — three seconds of overlap corrupted the client registry and took out
sixteen tests. In a demo it would take out the whole workspace.

Two guards, because they cover different failures:

* **A process-wide lock**, so two threads in one uvicorn worker cannot interleave.
  FastAPI runs sync handlers in a threadpool, so this is the common case.
* **Write-temp-then-replace**, because ``os.replace`` is atomic on both POSIX and
  Windows. A reader sees either the old file or the new one, never a splice, and
  a crash mid-write leaves the previous version intact rather than a ruin.

``read_json`` completes the contract: a file that is somehow still damaged is
reported as damaged and backed up rather than crashing the request, because
losing one write is recoverable and losing the screen is not.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

#: One lock for every JSON file this module writes. Coarse on purpose: these
#: files are small, writes are rare, and a per-path lock table would be more
#: machinery than the contention justifies.
_LOCK = threading.RLock()


def write_json(path: Path, data, indent: int = 2) -> None:
    """Serialise ``data`` to ``path`` atomically. Never leaves a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=indent, default=str)

    with _LOCK:
        # Same directory as the target: os.replace is only atomic within one
        # filesystem, and the system temp dir is often a different one.
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())      # survive a power cut, not just a crash
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def read_json(path: Path, default):
    """Read ``path``, or return ``default`` if it is missing or damaged.

    A damaged file is renamed to ``<name>.corrupt`` rather than deleted: it is
    the only copy of whatever was lost, and somebody may want to hand-repair it.
    """
    path = Path(path)
    if not path.exists():
        return default
    try:
        with _LOCK:
            return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        try:
            path.replace(path.with_suffix(path.suffix + ".corrupt"))
        except OSError:
            pass
        return default
    except OSError:
        return default


def repair(path: Path) -> tuple[bool, str]:
    """Salvage a file already damaged by the old non-atomic write.

    The failure it fixes has one shape — a complete document followed by the
    tail of a longer one — so the leading document is recoverable in full.
    """
    path = Path(path)
    if not path.exists():
        return False, "nothing there"
    raw = path.read_text(encoding="utf-8")
    try:
        json.loads(raw)
        return False, "already valid"
    except json.JSONDecodeError:
        pass
    try:
        obj, end = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError as exc:
        return False, f"beyond repair: {exc}"
    path.with_suffix(path.suffix + ".corrupt").write_text(raw, encoding="utf-8")
    write_json(path, obj)
    dropped = len(raw) - end
    return True, f"recovered, dropped {dropped} trailing byte(s)"
