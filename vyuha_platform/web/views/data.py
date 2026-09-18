"""Data — where the numbers come from, and what Vyuha made of each file.

The read-back is the point of this section: a figure read off a labelled column and one
reconstructed from a headerless sheet must not look identical, so every run carries what it
understood, what it ignored and how sure it is.
"""

from __future__ import annotations

from ... import config


def add(client, account, request) -> dict:
    settings = config.load()
    return {
        "typed_in": client.data_mode == "books",
        "can_read_photos": settings.vision_live,
        "is_guest": bool(getattr(account, "is_guest", False)),
        "runs": client.runs[:5],
    }


def read(client, account, request) -> dict:
    run = client.latest
    notes = list(getattr(run, "source_notes", []) or []) if run else []
    return {
        "run": run,
        "ok": bool(run and run.status == "ok"),
        "per_file": [(n.split(":", 1)[0], n.split(":", 1)[1].strip()) for n in notes if ":" in n],
        "plain": [n for n in notes if ":" not in n],
        "skipped": list(getattr(run, "sheets_skipped", []) or []) if run else [],
        "alerts": list(getattr(run, "alerts", []) or []) if run else [],
    }


def history(client, account, request) -> dict:
    return {"runs": client.runs[:40], "count": len(client.runs)}
