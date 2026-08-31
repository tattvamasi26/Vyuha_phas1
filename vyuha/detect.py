"""Work out what a raw grid actually is.

Three questions, in order:

1. **Which row is the header?** Real files open with a company name, an address,
   a "Sales Register 01-Apr to 30-Jun" title and a blank row before the actual
   column names show up on row 6.
2. **What does each column mean?** Map the header text onto the canonical
   vocabulary in :mod:`vyuha.schema`, falling back to inspecting the values when
   the header is useless ("Column1", or blank).
3. **What kind of table is this?** Sales, stock or receivables — decided by
   which canonical fields are present, not by the sheet's name.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import pandas as pd

from . import schema
from .ingest import RawSheet

HEADER_SEARCH_DEPTH = 25
MIN_HEADER_SCORE = 1.2

_NUMERIC_RE = re.compile(r"^-?[\d,]*\.?\d+%?$")
_CURRENCY_CHARS = "₹$€£¥ , "


@dataclass
class DetectedTable:
    """A raw sheet, resolved into something the pipeline can work with."""

    sheet: str
    kind: str
    header_row: int  # 1-based row number in the original file
    frame: pd.DataFrame  # original column names, header applied, data rows only
    mapping: dict[str, str]  # canonical field -> original column name
    unmapped: list[str] = field(default_factory=list)
    header_confidence: float = 0.0
    kind_confidence: float = 0.0

    @property
    def fields(self) -> set[str]:
        return set(self.mapping)

    def column(self, field_name: str) -> str | None:
        """Original column name backing a canonical field, if we found one."""
        return self.mapping.get(field_name)

    def has(self, *field_names: str) -> bool:
        return all(name in self.mapping for name in field_names)


def detect(sheet: RawSheet) -> DetectedTable:
    """Resolve one raw sheet into a :class:`DetectedTable`."""
    header_row, header_confidence = find_header_row(sheet.grid)
    frame = _apply_header(sheet.grid, header_row)
    mapping, unmapped = map_columns(frame)
    mapping = _reread_ledger_particulars(mapping)
    kind, kind_confidence = classify(set(mapping))
    return DetectedTable(
        sheet=sheet.name,
        kind=kind,
        header_row=sheet.source_row(header_row),
        frame=frame,
        mapping=mapping,
        unmapped=unmapped,
        header_confidence=round(header_confidence, 2),
        kind_confidence=round(kind_confidence, 2),
    )


def _reread_ledger_particulars(mapping: dict) -> dict:
    """"Particulars" names an item on a stock sheet and a party on a ledger.

    It is the most common column heading in Indian accounting exports and it is
    genuinely ambiguous, so no alias list can settle it — only the company it
    keeps can. A sheet that has a voucher number or an outstanding balance, and
    has neither a quantity nor an item code, is a ledger: its "Particulars"
    column holds customer names. Left alone, those names are read as products,
    and the dashboard cheerfully reports that the best-selling item this month
    was "Ramu Stores".

    Deliberately narrow. It only fires when there is no party column already, so
    it can never overwrite a real one, and only on the ledger shape.
    """
    # mapping is {field: column}, not the reverse.
    if schema.PARTY in mapping or schema.ITEM not in mapping:
        return mapping
    fields = set(mapping)
    ledgerish = fields & {schema.INVOICE_NO, schema.OUTSTANDING}
    itemish = fields & {schema.QTY, schema.SKU, schema.STOCK_QTY}
    if not ledgerish or itemish:
        return mapping
    out = dict(mapping)
    out[schema.PARTY] = out.pop(schema.ITEM)
    return out


# --- 1. header row --------------------------------------------------------


def find_header_row(grid: pd.DataFrame) -> tuple[int, float]:
    """Return ``(row_index, confidence)`` for the most header-looking row.

    Scores each candidate on how much it looks like column *names* (text, not
    numbers, no repeats, recognised vocabulary) and how much the rows beneath
    it look like *data* (numeric, and filling the same columns).
    """
    if grid.empty:
        return 0, 0.0

    depth = min(HEADER_SEARCH_DEPTH, len(grid.index))
    best_row, best_score = 0, float("-inf")

    for row_index in range(depth):
        score = _score_header_row(grid, row_index)
        if score > best_score:
            best_row, best_score = row_index, score

    return best_row, max(best_score, 0.0)


def _score_header_row(grid: pd.DataFrame, row_index: int) -> float:
    values = list(grid.iloc[row_index])
    filled = [v for v in values if not _blank(v)]
    if len(filled) < 2:
        return float("-inf")

    width = max(len(values), 1)
    fill_ratio = len(filled) / width

    text_cells = sum(1 for v in filled if _looks_textual(v))
    text_ratio = text_cells / len(filled)

    tokens = [schema.normalise(v) for v in filled]
    known = sum(1 for t in tokens if t and _best_field_for_token(t)[0])
    known_ratio = known / len(filled)

    distinct = len({t for t in tokens if t})
    unique_ratio = distinct / len(filled)

    # A header with data under it beats an identical-looking row at the bottom.
    below = _numeric_density(grid, row_index + 1, rows=6)
    # ...and a header should not itself be full of numbers.
    self_numeric = sum(1 for v in filled if _looks_numeric(v)) / len(filled)

    score = (
        3.0 * known_ratio
        + 1.5 * text_ratio
        + 1.0 * fill_ratio
        + 0.75 * unique_ratio
        + 1.0 * below
        - 2.0 * self_numeric
    )
    # Titles ("Sales Register", "M/s Sharma Traders") sit in one or two cells
    # of a wide sheet. Punish rows that fill much less of the width than the
    # widest row in the file.
    if fill_ratio < 0.4:
        score -= 1.5
    # Earlier rows win ties: headers live at the top.
    score -= row_index * 0.02
    return score


def _numeric_density(grid: pd.DataFrame, start: int, rows: int) -> float:
    stop = min(start + rows, len(grid.index))
    if start >= stop:
        return 0.0
    window = grid.iloc[start:stop]
    filled, numeric = 0, 0
    for value in window.to_numpy().ravel():
        if _blank(value):
            continue
        filled += 1
        if _looks_numeric(value) or isinstance(value, (dt.date, dt.datetime)):
            numeric += 1
    return numeric / filled if filled else 0.0


def _apply_header(grid: pd.DataFrame, header_row: int) -> pd.DataFrame:
    """Promote ``header_row`` to column names and keep only the rows below it."""
    header = grid.iloc[header_row]
    body = grid.iloc[header_row + 1 :].copy()

    names: list[str] = []
    seen: dict[str, int] = {}
    for position, raw in enumerate(header):
        name = "" if _blank(raw) else str(raw).strip()
        if not name or schema.normalise(name) == "":
            name = f"column_{position + 1}"
        # Duplicate headers are routine ("Amount" twice, once per tax slab).
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        names.append(name)

    body.columns = names
    return body.reset_index(drop=True)


# --- 2. column meaning ----------------------------------------------------


def map_columns(frame: pd.DataFrame) -> tuple[dict[str, str], list[str]]:
    """Map canonical field -> column name for the columns we recognise.

    Every candidate (column, field) pair is scored, then assigned greedily by
    descending score so the strongest evidence claims its field first. Each
    column maps to at most one field and each field to at most one column.
    """
    candidates: list[tuple[float, str, str]] = []
    noise: set[str] = set()
    for column in frame.columns:
        token = schema.normalise(column)
        if not token:
            continue
        if token in schema.NOISE_HEADERS:
            noise.add(str(column))
            continue
        for field_name, score in _score_token(token):
            candidates.append((score, field_name, str(column)))

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    mapping: dict[str, str] = {}
    claimed: set[str] = set()
    for score, field_name, column in candidates:
        if field_name in mapping or column in claimed:
            continue
        mapping[field_name] = column
        claimed.add(column)

    _infer_from_values(frame, mapping, claimed, noise)

    unmapped = [str(c) for c in frame.columns if str(c) not in claimed]
    return mapping, unmapped


def _score_token(token: str) -> list[tuple[str, float]]:
    """Score one normalised header against every canonical field."""
    scores: list[tuple[str, float]] = []
    for spec in schema.FIELDS:
        if any(bad in token for bad in spec.veto):
            continue
        if token in spec.exact:
            scores.append((spec.name, 10.0))
            continue
        hit = next((frag for frag in spec.contains if frag in token), None)
        if hit:
            # Longer fragments are more specific, and a fragment that covers
            # most of the header is a better match than one buried in it.
            scores.append((spec.name, 5.0 + len(hit) / max(len(token), 1)))
            continue
        alias = next((a for a in spec.exact if len(a) > 3 and a in token), None)
        if alias:
            scores.append((spec.name, 3.0 + len(alias) / max(len(token), 1)))
    return scores


def _best_field_for_token(token: str) -> tuple[str | None, float]:
    scores = _score_token(token)
    if not scores:
        return None, 0.0
    best = max(scores, key=lambda item: item[1])
    return best[0], best[1]


def _infer_from_values(
    frame: pd.DataFrame,
    mapping: dict[str, str],
    claimed: set[str],
    noise: set[str],
) -> None:
    """Rescue columns whose header told us nothing by reading their values.

    Only fills fields we are still missing, and only where the evidence is
    strong: a column of real dates, or a column of long free text next to
    nothing else that could be the item description. Columns whose header we
    recognised as noise ("Remarks", "Narration") are never adopted — a column
    of sentences is not a product name just because nothing else claimed it.
    """
    if len(frame.index) == 0:
        return

    for column in frame.columns:
        name = str(column)
        if name in claimed or name in noise:
            continue
        sample = _sample(frame[column])
        if sample.empty:
            continue

        if schema.DATE not in mapping and _date_ratio(sample) >= 0.7:
            mapping[schema.DATE] = name
            claimed.add(name)
            continue

        if schema.ITEM not in mapping and _free_text_ratio(sample) >= 0.7:
            unique_ratio = sample.astype(str).nunique() / len(sample)
            if unique_ratio >= 0.3:
                mapping[schema.ITEM] = name
                claimed.add(name)


def _sample(series: pd.Series, size: int = 50) -> pd.Series:
    values = series.dropna()
    values = values[values.astype(str).str.strip() != ""]
    return values.head(size)


def _date_ratio(sample: pd.Series) -> float:
    hits = 0
    for value in sample:
        if isinstance(value, (dt.date, dt.datetime, pd.Timestamp)):
            hits += 1
        elif isinstance(value, str) and _parses_as_date(value):
            hits += 1
    return hits / len(sample) if len(sample) else 0.0


def _parses_as_date(text: str) -> bool:
    text = text.strip()
    if len(text) < 6 or _NUMERIC_RE.match(text):
        return False
    return pd.to_datetime(text, errors="coerce", dayfirst=True) is not pd.NaT


def _free_text_ratio(sample: pd.Series) -> float:
    hits = sum(
        1
        for v in sample
        if isinstance(v, str) and len(v.strip()) >= 6 and not _looks_numeric(v)
    )
    return hits / len(sample) if len(sample) else 0.0


# --- 3. table kind --------------------------------------------------------


def classify(fields: set[str]) -> tuple[str, float]:
    """Pick the table kind whose rule fits the detected fields best."""
    best_kind, best_score = schema.UNKNOWN, 0.0
    for rule in schema.TABLE_RULES:
        if not all(f in fields for f in rule.required):
            continue
        supporting = sum(1 for f in rule.supporting if f in fields)
        denominator = max(len(rule.supporting), 1)
        score = 1.0 + supporting / denominator
        if score > best_score:
            best_kind, best_score = rule.kind, score
    return best_kind, best_score


# --- shared helpers -------------------------------------------------------


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    return isinstance(value, str) and not value.strip()


def _looks_numeric(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        stripped = value.strip().strip(_CURRENCY_CHARS)
        return bool(stripped) and bool(_NUMERIC_RE.match(stripped))
    return False


def _looks_textual(value: object) -> bool:
    return isinstance(value, str) and not _looks_numeric(value)
