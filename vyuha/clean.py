"""Turn a detected table into trustworthy numbers.

Everything here exists because of something a real export does: amounts written
as "₹ 1,23,456.00", negatives written as "(4,500)", credits written as
"4500 Cr", a "Grand Total" row that would double every metric if counted, and
the same customer spelled "M/s Sharma Traders", "Sharma traders" and
"SHARMA TRADERS  ".

The output frame uses canonical column names only, with real dtypes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from . import schema
from .detect import DetectedTable

# Rows whose text cells say this are summaries of the rows above them.
TOTAL_ROW_PATTERNS = re.compile(
    r"^\s*(grand\s*total|sub\s*-?\s*total|total|totals|closing\s+balance|"
    r"opening\s+balance|net\s+total|summary|balance\s+c/?f|carried\s+forward)\s*[:\-]?\s*$",
    re.IGNORECASE,
)

# Honorifics and suffixes that stop the same customer matching itself.
_PARTY_NOISE = re.compile(
    r"^(m/?s\.?|messrs\.?|mr\.?|mrs\.?|shri|sri|smt\.?)\s+|"
    r"\s+(pvt\.?|private|ltd\.?|limited|llp|inc\.?|co\.?|company|"
    r"enterprises?|traders?|agencies|agency|& co\.?)\.?$",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_PAREN_NEGATIVE = re.compile(r"^\((.*)\)$")
_TRAILING_CR_DR = re.compile(r"\s*(cr|dr)\.?$", re.IGNORECASE)
_NUMBER_JUNK = re.compile(r"[₹$€£¥,\s]")


@dataclass
class CleanTable:
    """One table, cleaned, with canonical column names and real dtypes."""

    sheet: str
    kind: str
    frame: pd.DataFrame
    mapping: dict[str, str]
    issues: list[str] = field(default_factory=list)
    rows_in: int = 0
    rows_out: int = 0
    unmapped: list[str] = field(default_factory=list)
    header_row: int = 0

    @property
    def rows_dropped(self) -> int:
        return max(self.rows_in - self.rows_out, 0)

    def has(self, *field_names: str) -> bool:
        return all(name in self.frame.columns for name in field_names)


def clean(table: DetectedTable) -> CleanTable:
    """Coerce, de-noise and canonicalise one detected table."""
    issues: list[str] = []
    rows_in = len(table.frame.index)

    frame = _select_and_rename(table)
    frame = _drop_total_rows(frame, issues)
    frame = _coerce_types(frame, issues)
    frame = _derive_missing(frame, issues)
    frame = _drop_empty_rows(frame, table.kind, issues)
    frame = _normalise_text(frame)
    frame = _drop_duplicates(frame, table.kind, issues)

    return CleanTable(
        sheet=table.sheet,
        kind=table.kind,
        frame=frame.reset_index(drop=True),
        mapping=dict(table.mapping),
        issues=issues,
        rows_in=rows_in,
        rows_out=len(frame.index),
        unmapped=list(table.unmapped),
        header_row=table.header_row,
    )


# --- steps ----------------------------------------------------------------


def _select_and_rename(table: DetectedTable) -> pd.DataFrame:
    columns = {original: canonical for canonical, original in table.mapping.items()}
    frame = table.frame.loc[:, list(columns)].copy()
    return frame.rename(columns=columns)


def _drop_total_rows(frame: pd.DataFrame, issues: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    text_columns = [c for c in frame.columns if c in schema.TEXT_FIELDS]
    if not text_columns:
        return frame
    is_total = pd.Series(False, index=frame.index)
    for column in text_columns:
        as_text = frame[column].astype("string").fillna("")
        is_total |= as_text.str.match(TOTAL_ROW_PATTERNS, na=False)
    dropped = int(is_total.sum())
    if dropped:
        issues.append(f"Ignored {dropped} total/subtotal row(s).")
    return frame.loc[~is_total]


def _coerce_types(frame: pd.DataFrame, issues: list[str]) -> pd.DataFrame:
    for column in frame.columns:
        if column in schema.NUMERIC_FIELDS:
            converted = frame[column].map(to_number)
            unparsed = int(converted.isna().sum() - frame[column].isna().sum())
            if unparsed > 0:
                issues.append(
                    f"{unparsed} value(s) in '{schema.LABELS[column]}' were not numbers."
                )
            frame[column] = pd.to_numeric(converted, errors="coerce")
        elif column in schema.DATE_FIELDS:
            converted = pd.to_datetime(
                frame[column], errors="coerce", dayfirst=True, format="mixed"
            )
            unparsed = int(converted.isna().sum() - frame[column].isna().sum())
            if unparsed > 0:
                issues.append(
                    f"{unparsed} value(s) in '{schema.LABELS[column]}' were not dates."
                )
            frame[column] = converted
        else:
            frame[column] = frame[column].astype("string")
    return frame


def _derive_missing(frame: pd.DataFrame, issues: list[str]) -> pd.DataFrame:
    """Fill in the one column everybody forgets to export."""
    has = frame.columns.__contains__

    if not has(schema.AMOUNT) and has(schema.QTY) and has(schema.RATE):
        frame[schema.AMOUNT] = frame[schema.QTY] * frame[schema.RATE]
        issues.append("Derived 'Amount' as Qty × Rate.")
    elif has(schema.AMOUNT) and has(schema.QTY) and has(schema.RATE):
        gaps = frame[schema.AMOUNT].isna() & frame[schema.QTY].notna() & frame[schema.RATE].notna()
        if gaps.any():
            frame.loc[gaps, schema.AMOUNT] = (
                frame.loc[gaps, schema.QTY] * frame.loc[gaps, schema.RATE]
            )
            issues.append(f"Filled {int(gaps.sum())} blank 'Amount' cell(s) from Qty × Rate.")

    if not has(schema.RATE) and has(schema.AMOUNT) and has(schema.QTY):
        with pd.option_context("mode.chained_assignment", None):
            qty = frame[schema.QTY].replace(0, pd.NA)
            frame[schema.RATE] = frame[schema.AMOUNT] / qty

    return frame


def _drop_empty_rows(frame: pd.DataFrame, kind: str, issues: list[str]) -> pd.DataFrame:
    """Drop rows carrying no usable value for this kind of table."""
    if frame.empty:
        return frame

    required_any = {
        schema.SALES: (schema.AMOUNT, schema.QTY),
        schema.STOCK: (schema.STOCK_QTY,),
        schema.RECEIVABLES: (schema.OUTSTANDING,),
    }.get(kind, tuple(frame.columns))

    present = [c for c in required_any if c in frame.columns]
    if not present:
        return frame

    keep = frame[present].notna().any(axis=1)
    dropped = int((~keep).sum())
    if dropped:
        issues.append(f"Dropped {dropped} row(s) with no usable values.")
    return frame.loc[keep]


def _normalise_text(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        if column in schema.TEXT_FIELDS:
            cleaned = (
                frame[column]
                .astype("string")
                .str.replace(_WHITESPACE, " ", regex=True)
                .str.strip()
            )
            frame[column] = cleaned.replace("", pd.NA)

    if schema.PARTY in frame.columns:
        frame["party_key"] = frame[schema.PARTY].map(party_key)
    return frame


def _drop_duplicates(frame: pd.DataFrame, kind: str, issues: list[str]) -> pd.DataFrame:
    """Remove rows that are byte-for-byte repeats of an earlier row.

    Only for stock and receivables, where one row per SKU/party is the whole
    point. Sales legitimately repeats — the same customer buys the same item
    at the same price twice in a day.
    """
    if kind not in (schema.STOCK, schema.RECEIVABLES) or frame.empty:
        return frame
    before = len(frame.index)
    frame = frame.drop_duplicates()
    removed = before - len(frame.index)
    if removed:
        issues.append(f"Removed {removed} exact duplicate row(s).")
    return frame


# --- value parsers --------------------------------------------------------


def to_number(value: object) -> float | None:
    """Parse the many ways a spreadsheet writes a number.

    ``"₹ 1,23,456.00"`` -> 123456.0, ``"(4,500)"`` -> -4500.0,
    ``"4500 Cr"`` -> -4500.0 (a credit reduces what is owed), ``"12%"`` -> 12.0.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if value != value else float(value)

    text = str(value).strip()
    if not text:
        return None

    sign = 1.0
    paren = _PAREN_NEGATIVE.match(text)
    if paren:
        sign, text = -1.0, paren.group(1)

    credit = _TRAILING_CR_DR.search(text)
    if credit:
        if credit.group(1).lower() == "cr":
            sign *= -1.0
        text = _TRAILING_CR_DR.sub("", text)

    text = text.rstrip("%")
    text = _NUMBER_JUNK.sub("", text)
    if text in {"", "-", ".", "--"}:
        return None

    try:
        return sign * float(text)
    except ValueError:
        return None


def party_key(name: object) -> object:
    """Collapse a customer name to a comparison key.

    ``"M/s Sharma Traders Pvt. Ltd."`` and ``"sharma traders"`` both become
    ``"sharma"``, so the same customer aggregates as one line in the report.
    """
    if name is None or name is pd.NA:
        return pd.NA
    text = str(name).strip().lower()
    if not text:
        return pd.NA
    # "Patel Pumps & Motors" and "patel pumps and motors" are one customer.
    text = text.replace("&", " and ")
    previous = None
    while previous != text:
        previous = text
        text = _PARTY_NOISE.sub(" ", text).strip()
    text = _WHITESPACE.sub(" ", text).strip(" .,-")
    return text or str(name).strip().lower()
