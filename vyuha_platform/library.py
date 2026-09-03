"""Many files, read together and reconciled into one picture.

The upload path read **one file at a time and threw the last one away**. Send a
client's fourteen months of exports and you got a dashboard of whichever file
you happened to drop last. That is not an intake; it is a preview.

This reads a whole pile at once — a multi-select, a folder on disk, a hundred
files — and merges them. Three rules do the merging, and getting them wrong is
worse than not merging at all:

**Sales accumulate.** Two months of sales are two months of sales.

**Stock is a snapshot, and the newest file wins.** A stock statement from March
and one from August are not two sets of shelves. Stacking them the way sales
stack would report twice the stock a business owns, which is the single most
expensive mistake this module could make.

**Receivables are a snapshot too**, keyed by invoice where there is one — the
same bill appearing in three monthly files is one debt, not three.

Duplicates are removed **before** anything is summed. Client exports overlap
constantly: a "last 90 days" report sent in June and again in July shares a
month, and stacking those doubles a third of the revenue. The key is the invoice
number when the file carries one, and otherwise the row's own content.

Every file's fate is reported. A hundred files in, a hundred lines out, each
saying what was read or exactly why it was not — because "we read your data" is
not a claim anybody should have to take on faith.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from vyuha import analyze, clean, detect, ingest, schema

from . import sources

#: What we will even attempt. Anything else is reported as skipped rather than
#: silently ignored — a folder scan that quietly drops files is worse than one
#: that fails, because nobody notices.
READABLE = {".xlsx", ".xlsm", ".csv", ".txt", ".tsv", ".pdf",
            ".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class FileResult:
    """What happened to one file. Always produced, success or not."""

    name: str
    ok: bool
    kind: str = ""                  # native | text | pdf-text | vision-* | whatsapp
    method: str = ""
    tables: list[str] = field(default_factory=list)   # kinds found
    rows: int = 0
    error: str = ""
    needs_action: str = ""
    skipped_sheets: list[str] = field(default_factory=list)


@dataclass
class Batch:
    """The whole pile, and what came of it."""

    files: list[FileResult] = field(default_factory=list)
    tables: list = field(default_factory=list)          # merged CleanTables
    insights: object | None = None
    duplicates_dropped: int = 0
    stock_files_superseded: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def read(self) -> int:
        return sum(1 for f in self.files if f.ok)

    @property
    def rejected(self) -> int:
        return sum(1 for f in self.files if not f.ok)

    @property
    def rows(self) -> int:
        return sum(f.rows for f in self.files if f.ok)


# --------------------------------------------------------------- reading one

def _read_one(path: Path, workdir: Path, settings, item_names, rates) -> tuple[FileResult, list]:
    """Convert if needed, then split into CleanTables. Never raises."""
    result = FileResult(name=path.name, ok=False)

    if path.suffix.lower() not in READABLE:
        result.error = f"Vyuha does not read '{path.suffix or 'that file type'}'."
        result.needs_action = "Send a spreadsheet, CSV, PDF or a photo."
        return result, []

    try:
        extraction = sources.prepare(path, workdir, settings, item_names, rates)
    except Exception as exc:                              # a converter blew up
        result.error = f"Could not convert it: {exc}"
        return result, []

    if not extraction.ok:
        result.error = extraction.error
        result.needs_action = extraction.needs_action
        result.kind = extraction.kind
        return result, []

    result.kind = extraction.kind
    result.method = extraction.method

    try:
        sheets = ingest.read_source(extraction.path)
    except ingest.IngestError as exc:
        result.error = str(exc)
        return result, []
    except Exception as exc:
        result.error = f"Could not open it: {exc}"
        return result, []

    tables = []
    for sheet in sheets:
        try:
            detected = detect.detect(sheet)
            if detected.kind == schema.UNKNOWN:
                result.skipped_sheets.append(sheet.name)
                continue
            table = clean.clean(detected)
            if table.rows_out < 1:
                result.skipped_sheets.append(sheet.name)
                continue
            tables.append(table)
            result.tables.append(table.kind)
            result.rows += int(len(table.frame.index))
        except Exception as exc:                          # one bad sheet, not the file
            result.skipped_sheets.append(f"{sheet.name} ({exc})")

    if not tables:
        result.error = ("Nothing in it was recognisable as sales, stock or "
                        "receivables.")
        result.needs_action = "Check the read-back below to see what was found."
        return result, []

    result.ok = True
    return result, tables


# ------------------------------------------------------------- reconciliation

def _row_key(row: pd.Series, kind: str) -> str:
    """A stable identity for one row, so the same bill is not counted twice."""
    if kind == schema.SALES and schema.INVOICE_NO in row.index:
        inv = row.get(schema.INVOICE_NO)
        if pd.notna(inv) and str(inv).strip():
            # Invoice plus SKU: one bill has many lines, and they are not
            # duplicates of each other.
            sku = row.get(schema.SKU) if schema.SKU in row.index else ""
            return f"inv|{str(inv).strip().lower()}|{str(sku).strip().lower()}"

    parts = []
    for field_name in (schema.DATE, schema.PARTY, schema.SKU, schema.ITEM,
                       schema.QTY, schema.AMOUNT, schema.OUTSTANDING):
        if field_name in row.index:
            v = row.get(field_name)
            parts.append("" if pd.isna(v) else str(v).strip().lower())
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def _newest_first(pairs: list[tuple[float, object]]) -> list:
    return [t for _mtime, t in sorted(pairs, key=lambda p: p[0], reverse=True)]


def reconcile(stamped: list[tuple[float, object]], batch: Batch) -> list:
    """Merge many files' tables into one set the engine can analyse.

    ``stamped`` is (modified_time, CleanTable). Time decides which snapshot
    wins; it does not affect sales, which accumulate regardless of when the file
    was written.
    """
    by_kind: dict[str, list[tuple[float, object]]] = {}
    for mtime, table in stamped:
        by_kind.setdefault(table.kind, []).append((mtime, table))

    merged = []

    # --- sales: stack everything, then drop rows we have already counted.
    sales = by_kind.get(schema.SALES, [])
    if sales:
        frames, seen, dropped = [], set(), 0
        for _mtime, table in sorted(sales, key=lambda p: p[0]):
            frame = table.frame
            keep = []
            for _idx, row in frame.iterrows():
                key = _row_key(row, schema.SALES)
                if key in seen:
                    dropped += 1
                    continue
                seen.add(key)
                keep.append(_idx)
            if keep:
                frames.append(frame.loc[keep])
        batch.duplicates_dropped += dropped
        if frames:
            combined = sales[0][1]
            combined.frame = pd.concat(frames, ignore_index=True)
            combined.issues = list(dict.fromkeys(
                i for _m, t in sales for i in t.issues))
            if dropped:
                combined.issues.append(
                    f"Dropped {dropped} row(s) that appeared in more than one file.")
            merged.append(combined)

    # --- stock: a snapshot. The newest file wins, per SKU.
    stock = by_kind.get(schema.STOCK, [])
    if stock:
        ordered = _newest_first(stock)
        newest = ordered[0]
        frame = newest.frame
        if len(ordered) > 1 and schema.SKU in frame.columns:
            have = set(frame[schema.SKU].dropna().astype(str).str.strip().str.lower())
            extra = []
            for older in ordered[1:]:
                if schema.SKU not in older.frame.columns:
                    continue
                keys = (older.frame[schema.SKU].astype(str).str.strip().str.lower())
                rows = older.frame[~keys.isin(have)]
                if not rows.empty:
                    extra.append(rows)
                    have |= set(keys[~keys.isin(have)])
            if extra:
                frame = pd.concat([frame] + extra, ignore_index=True)
        newest.frame = frame
        batch.stock_files_superseded = max(len(stock) - 1, 0)
        if len(stock) > 1:
            newest.issues = list(newest.issues) + [
                f"Stock taken from the newest of {len(stock)} file(s); older "
                f"counts were not added to it."]
        merged.append(newest)

    # --- receivables: snapshot too, deduped by invoice or content.
    recv = by_kind.get(schema.RECEIVABLES, [])
    if recv:
        ordered = _newest_first(recv)
        frames, seen = [], set()
        for table in ordered:
            keep = []
            for _idx, row in table.frame.iterrows():
                key = _row_key(row, schema.RECEIVABLES)
                if key in seen:
                    continue
                seen.add(key)
                keep.append(_idx)
            if keep:
                frames.append(table.frame.loc[keep])
        combined = ordered[0]
        if frames:
            combined.frame = pd.concat(frames, ignore_index=True)
        merged.append(combined)

    # --- anything else the engine knows about, stacked as-is.
    for kind, pairs in by_kind.items():
        if kind in {schema.SALES, schema.STOCK, schema.RECEIVABLES}:
            continue
        merged.extend(t for _m, t in pairs)

    return merged


# ---------------------------------------------------------------- the door

def batch(paths: list[Path], workdir: Path, settings, *, item_names=None,
          rates=None, as_of: datetime | None = None, label: str = "") -> Batch:
    """Read every file, reconcile them, and analyse the result as one dataset."""
    out = Batch()
    stamped: list[tuple[float, object]] = []
    item_names = item_names or []
    rates = rates or {}

    for path in paths:
        path = Path(path)
        result, tables = _read_one(path, workdir, settings, item_names, rates)
        out.files.append(result)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        stamped.extend((mtime, t) for t in tables)

    out.tables = reconcile(stamped, out)
    source = label or (f"{out.read} file(s)" if out.read != 1
                       else out.files[0].name)
    out.insights = analyze.analyse(out.tables, source=source, as_of=as_of)

    if out.duplicates_dropped:
        out.notes.append(
            f"{out.duplicates_dropped} duplicate row(s) appeared in more than "
            f"one file and were counted once.")
    if out.stock_files_superseded:
        out.notes.append(
            f"{out.stock_files_superseded} older stock count(s) were superseded "
            f"by the newest — stock is a snapshot, not a running total.")
    if out.rejected:
        out.notes.append(f"{out.rejected} file(s) could not be read. Each says why.")
    return out


def scan(folder: Path, recursive: bool = True) -> tuple[list[Path], list[str]]:
    """Every readable file in a folder, and a word about what was left out.

    Reading a folder is the honest answer to "the data is already on my
    machine". Nobody wants to select ninety files in a dialog.
    """
    folder = Path(folder).expanduser()
    if not folder.exists():
        return [], [f"There is no folder at {folder}."]
    if not folder.is_dir():
        return [], [f"{folder} is a file, not a folder."]

    it = folder.rglob("*") if recursive else folder.glob("*")
    found, other = [], 0
    for path in sorted(it):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if path.suffix.lower() in READABLE:
            found.append(path)
        else:
            other += 1

    notes = []
    if other:
        notes.append(f"{other} file(s) of other types were left alone.")
    if not found:
        notes.append("Nothing readable in that folder.")
    return found, notes
