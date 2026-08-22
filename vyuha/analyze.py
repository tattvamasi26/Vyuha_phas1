"""The part the client is actually paying for.

Takes the cleaned tables and produces the numbers a distributor cannot get out
of their own spreadsheet without an afternoon of pivot tables: who owes money
and for how long, which SKUs are about to run out, which stock has not moved in
months, and where revenue is concentrated.

Every alert produced here is deliberately self-contained (severity, title, one
line of detail) because the same objects become the WhatsApp/email alert
payloads in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from . import schema
from .clean import CleanTable

# Ageing buckets, in days past due. Standard Indian receivables practice.
AGEING_BUCKETS: tuple[tuple[str, int, float], ...] = (
    ("Not due", -10**6, 0),
    ("0–30 days", 0, 30),
    ("31–60 days", 31, 60),
    ("61–90 days", 61, 90),
    ("90+ days", 91, float("inf")),
)

DEAD_STOCK_DAYS = 90
LOW_COVER_DAYS = 14
CONCENTRATION_WARN = 0.40

CRITICAL, WARNING, INFO = "critical", "warning", "info"


@dataclass
class Alert:
    severity: str
    title: str
    detail: str
    value: float | None = None
    #: Stable machine identity. Channels dispatch on this rather than parsing
    #: ``title``, so rewording a title can never silently break a renderer.
    code: str = "generic"
    #: The SKUs / parties / invoices behind the alert, structured. ``detail`` is
    #: pre-rendered English for the dashboard; this is what other channels
    #: (WhatsApp, email) re-format to their own length limits.
    entities: list[str] = field(default_factory=list)


@dataclass
class Insights:
    """Everything the report renders, plus the alerts worth pushing."""

    source: str
    generated_at: datetime
    period_start: pd.Timestamp | None = None
    period_end: pd.Timestamp | None = None
    sales: dict = field(default_factory=dict)
    stock: dict = field(default_factory=dict)
    receivables: dict = field(default_factory=dict)
    alerts: list[Alert] = field(default_factory=list)
    tables: list[CleanTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_sales(self) -> bool:
        return bool(self.sales)

    @property
    def has_stock(self) -> bool:
        return bool(self.stock)

    @property
    def has_receivables(self) -> bool:
        return bool(self.receivables)


def analyse(tables: list[CleanTable], source: str, as_of: datetime | None = None) -> Insights:
    """Run every analysis that the available tables support."""
    as_of = as_of or datetime.now()
    insights = Insights(source=source, generated_at=as_of, tables=tables)

    sales = _concat(tables, schema.SALES)
    stock = _concat(tables, schema.STOCK)
    receivables = _concat(tables, schema.RECEIVABLES)

    if sales is not None:
        insights.sales = _analyse_sales(sales, insights)
    if stock is not None:
        insights.stock = _analyse_stock(stock, sales, insights, as_of)
    if receivables is not None:
        insights.receivables = _analyse_receivables(receivables, insights, as_of)

    if not (insights.has_sales or insights.has_stock or insights.has_receivables):
        insights.warnings.append(
            "No sales, stock or receivables columns were recognised in this file."
        )

    order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    insights.alerts.sort(key=lambda a: (order.get(a.severity, 3), -(a.value or 0)))
    return insights


def _concat(tables: list[CleanTable], kind: str) -> pd.DataFrame | None:
    """Stack every table of one kind — clients split sales across 12 monthly sheets."""
    frames = [t.frame for t in tables if t.kind == kind and not t.frame.empty]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


# --- sales ----------------------------------------------------------------


def _analyse_sales(frame: pd.DataFrame, insights: Insights) -> dict:
    out: dict = {"rows": int(len(frame.index))}

    amount = frame[schema.AMOUNT] if schema.AMOUNT in frame.columns else None
    if amount is None:
        return out

    out["revenue"] = float(amount.sum(skipna=True))
    out["lines"] = int(amount.notna().sum())

    if schema.INVOICE_NO in frame.columns:
        out["orders"] = int(frame[schema.INVOICE_NO].nunique(dropna=True))
    else:
        out["orders"] = out["lines"]
    out["avg_order_value"] = out["revenue"] / out["orders"] if out["orders"] else 0.0

    if schema.QTY in frame.columns:
        out["units"] = float(frame[schema.QTY].sum(skipna=True))

    if schema.DATE in frame.columns and frame[schema.DATE].notna().any():
        dates = frame[schema.DATE].dropna()
        insights.period_start = dates.min()
        insights.period_end = dates.max()
        out["period_start"] = dates.min()
        out["period_end"] = dates.max()
        out["monthly"] = _monthly_revenue(frame)
        _add_trend(out, insights)

    if schema.PARTY in frame.columns:
        out["top_parties"] = _top_by(frame, "party_key", schema.PARTY, schema.AMOUNT, 10)
        out["party_count"] = int(frame["party_key"].nunique(dropna=True))
        _check_concentration(out, insights)

    item_field = schema.ITEM if schema.ITEM in frame.columns else (
        schema.SKU if schema.SKU in frame.columns else None
    )
    if item_field:
        out["top_items"] = _top_by(frame, item_field, item_field, schema.AMOUNT, 10)
        out["item_count"] = int(frame[item_field].nunique(dropna=True))

    if schema.CATEGORY in frame.columns:
        out["top_categories"] = _top_by(
            frame, schema.CATEGORY, schema.CATEGORY, schema.AMOUNT, 8
        )

    return out


def _monthly_revenue(frame: pd.DataFrame) -> list[dict]:
    """Revenue per calendar month, oldest first.

    The newest bucket is flagged ``partial`` when the file stops part-way
    through that month — comparing 11 days against a full month would otherwise
    manufacture a "revenue collapsed" alert every time.
    """
    dated = frame.dropna(subset=[schema.DATE])
    if dated.empty:
        return []
    months = dated[schema.DATE].dt.to_period("M")
    grouped = dated.groupby(months, observed=True)[schema.AMOUNT].sum().sort_index()

    last_date = dated[schema.DATE].max()
    rows: list[dict] = []
    for period, value in grouped.items():
        partial = period == last_date.to_period("M") and last_date < period.end_time.normalize()
        rows.append(
            {
                "month": str(period),
                "label": period.strftime("%b %Y"),
                "amount": float(value),
                "partial": bool(partial),
            }
        )
    return rows


def _add_trend(out: dict, insights: Insights) -> None:
    monthly = out.get("monthly") or []
    complete = [m for m in monthly if not m.get("partial")]
    if len(complete) < 2:
        return
    latest, previous = complete[-1], complete[-2]
    if previous["amount"] <= 0:
        return
    change = (latest["amount"] - previous["amount"]) / previous["amount"]
    out["mom_change"] = change
    out["mom_from"] = previous["label"]
    out["mom_to"] = latest["label"]
    if change <= -0.20:
        insights.alerts.append(
            Alert(
                WARNING,
                f"Revenue fell {abs(change):.0%} in {latest['label']}",
                f"{latest['label']} did {_inr(latest['amount'])} against "
                f"{_inr(previous['amount'])} in {previous['label']}.",
                value=abs(change) * 100,
                code="revenue_drop",
            )
        )


def _check_concentration(out: dict, insights: Insights) -> None:
    top = out.get("top_parties") or []
    revenue = out.get("revenue") or 0
    if not top or revenue <= 0:
        return
    top3 = sum(row["amount"] for row in top[:3])
    share = top3 / revenue
    out["top3_share"] = share
    if share >= CONCENTRATION_WARN and out.get("party_count", 0) > 3:
        insights.alerts.append(
            Alert(
                WARNING,
                f"{share:.0%} of revenue comes from 3 customers",
                "Losing any one of "
                + ", ".join(row["label"] for row in top[:3])
                + " would take a visible bite out of the month.",
                value=share * 100,
                code="concentration",
                entities=[row["label"] for row in top[:3]],
            )
        )


def _top_by(
    frame: pd.DataFrame, group_field: str, label_field: str, value_field: str, limit: int
) -> list[dict]:
    """Group by ``group_field``, sum ``value_field``, label with the commonest raw spelling."""
    if group_field not in frame.columns or value_field not in frame.columns:
        return []
    working = frame.dropna(subset=[group_field])
    if working.empty:
        return []

    totals = working.groupby(group_field, observed=True)[value_field].sum()
    counts = working.groupby(group_field, observed=True)[value_field].size()
    labels = (
        working.groupby(group_field, observed=True)[label_field]
        .agg(lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else "—")
    )

    grand_total = float(totals.sum())
    top = totals.sort_values(ascending=False).head(limit)
    return [
        {
            "key": str(key),
            "label": str(labels.get(key, key)),
            "amount": float(value),
            "lines": int(counts.get(key, 0)),
            "share": float(value) / grand_total if grand_total else 0.0,
        }
        for key, value in top.items()
    ]


# --- stock ----------------------------------------------------------------


def _analyse_stock(
    frame: pd.DataFrame,
    sales: pd.DataFrame | None,
    insights: Insights,
    as_of: datetime,
) -> dict:
    out: dict = {"rows": int(len(frame.index))}
    if schema.STOCK_QTY not in frame.columns:
        return out

    qty = frame[schema.STOCK_QTY]
    out["skus"] = int(len(frame.index))
    out["units"] = float(qty.sum(skipna=True))

    if schema.RATE in frame.columns:
        value = qty.fillna(0) * frame[schema.RATE].fillna(0)
        out["value"] = float(value.sum())
        frame = frame.assign(_stock_value=value)

    label_field = _stock_label_field(frame)

    out_of_stock = frame[qty.fillna(0) <= 0]
    out["out_of_stock"] = _stock_rows(out_of_stock, label_field, limit=15)
    out["out_of_stock_count"] = int(len(out_of_stock.index))

    if schema.REORDER_LEVEL in frame.columns:
        reorder = frame[schema.REORDER_LEVEL]
        below = frame[reorder.notna() & (qty.fillna(0) <= reorder.fillna(0))]
        out["below_reorder"] = _stock_rows(below, label_field, limit=20, with_reorder=True)
        out["below_reorder_count"] = int(len(below.index))
        if len(below.index):
            insights.alerts.append(
                Alert(
                    CRITICAL,
                    f"{len(below.index)} SKU(s) at or below reorder level",
                    "Top of the list: "
                    + ", ".join(r["label"] for r in out["below_reorder"][:3])
                    + ". Raise a purchase order before these stock out.",
                    value=float(len(below.index)),
                    code="below_reorder",
                    entities=[r["label"] for r in out["below_reorder"]],
                )
            )
    elif out["out_of_stock_count"]:
        insights.alerts.append(
            Alert(
                CRITICAL,
                f"{out['out_of_stock_count']} SKU(s) are out of stock",
                "No reorder-level column in the file, so this is based on zero "
                "or negative stock alone.",
                value=float(out["out_of_stock_count"]),
                code="out_of_stock",
                entities=[r["label"] for r in out["out_of_stock"]],
            )
        )

    movement = _stock_movement(frame, sales, label_field, insights, as_of)
    out.update(movement)

    if schema.RATE in frame.columns:
        top = frame.dropna(subset=["_stock_value"]).nlargest(10, "_stock_value")
        out["top_value"] = [
            {
                "label": _row_label(row, label_field),
                "qty": _float(row.get(schema.STOCK_QTY)),
                "value": _float(row.get("_stock_value")),
            }
            for _, row in top.iterrows()
        ]

    return out


def _stock_label_field(frame: pd.DataFrame) -> str | None:
    for candidate in (schema.ITEM, schema.SKU, schema.CATEGORY):
        if candidate in frame.columns:
            return candidate
    return None


def _stock_rows(
    frame: pd.DataFrame, label_field: str | None, limit: int, with_reorder: bool = False
) -> list[dict]:
    rows: list[dict] = []
    ordered = frame
    if with_reorder and schema.REORDER_LEVEL in frame.columns:
        shortfall = frame[schema.REORDER_LEVEL].fillna(0) - frame[schema.STOCK_QTY].fillna(0)
        ordered = frame.assign(_shortfall=shortfall).sort_values("_shortfall", ascending=False)
    for _, row in ordered.head(limit).iterrows():
        entry = {
            "label": _row_label(row, label_field),
            "sku": _text(row.get(schema.SKU)),
            "qty": _float(row.get(schema.STOCK_QTY)),
        }
        if with_reorder:
            entry["reorder_level"] = _float(row.get(schema.REORDER_LEVEL))
            entry["shortfall"] = _float(row.get("_shortfall"))
        rows.append(entry)
    return rows


def _stock_movement(
    frame: pd.DataFrame,
    sales: pd.DataFrame | None,
    label_field: str | None,
    insights: Insights,
    as_of: datetime,
) -> dict:
    """Join stock against sales to find dead stock and days of cover.

    This is the join a distributor never does by hand, and it is where most of
    the trapped cash in the business turns up.
    """
    out: dict = {}
    join_field = _join_field(frame, sales)
    if sales is None or join_field is None or schema.AMOUNT not in sales.columns:
        return out

    sold = sales.dropna(subset=[join_field])
    if sold.empty:
        return out

    span_days = _sales_span_days(sold, as_of)
    qty_field = schema.QTY if schema.QTY in sold.columns else None

    grouped = sold.groupby(join_field, observed=True)
    sold_amount = grouped[schema.AMOUNT].sum()
    sold_qty = grouped[qty_field].sum() if qty_field else None
    last_sold = (
        grouped[schema.DATE].max() if schema.DATE in sold.columns else None
    )

    stock_keys = frame[join_field].astype("string")
    never_sold_mask = ~stock_keys.isin(set(sold_amount.index.astype(str)))

    dead: list[dict] = []
    for _, row in frame[never_sold_mask].iterrows():
        dead.append(
            {
                "label": _row_label(row, label_field),
                "qty": _float(row.get(schema.STOCK_QTY)),
                "value": _float(row.get("_stock_value")),
                "last_sold": None,
                "days_idle": None,
            }
        )

    if last_sold is not None:
        cutoff = pd.Timestamp(as_of) - pd.Timedelta(days=DEAD_STOCK_DAYS)
        for _, row in frame[~never_sold_mask].iterrows():
            when = last_sold.get(str(row.get(join_field)))
            if when is None or pd.isna(when) or when > cutoff:
                continue
            dead.append(
                {
                    "label": _row_label(row, label_field),
                    "qty": _float(row.get(schema.STOCK_QTY)),
                    "value": _float(row.get("_stock_value")),
                    "last_sold": when.strftime("%d %b %Y"),
                    "days_idle": int((pd.Timestamp(as_of) - when).days),
                }
            )

    dead = [d for d in dead if (d["qty"] or 0) > 0]
    dead.sort(key=lambda d: (d["value"] or 0, d["qty"] or 0), reverse=True)
    if dead:
        out["dead_stock"] = dead[:20]
        out["dead_stock_count"] = len(dead)
        locked = sum(d["value"] or 0 for d in dead)
        out["dead_stock_value"] = locked
        insights.alerts.append(
            Alert(
                WARNING if locked == 0 else CRITICAL,
                f"{len(dead)} SKU(s) have not sold in {DEAD_STOCK_DAYS}+ days",
                (f"About {_inr(locked)} of working capital is sitting in them. "
                 if locked else "")
                + "Discount, bundle or return these before they age further.",
                value=locked or float(len(dead)),
                code="dead_stock",
                entities=[d["label"] for d in dead],
            )
        )

    if sold_qty is not None and span_days > 0:
        cover_rows: list[dict] = []
        for _, row in frame.iterrows():
            key = str(row.get(join_field))
            total_sold = float(sold_qty.get(key, 0) or 0)
            if total_sold <= 0:
                continue
            per_day = total_sold / span_days
            on_hand = _float(row.get(schema.STOCK_QTY)) or 0.0
            days = on_hand / per_day if per_day > 0 else None
            if days is None:
                continue
            cover_rows.append(
                {
                    "label": _row_label(row, label_field),
                    "qty": on_hand,
                    "daily_run_rate": round(per_day, 2),
                    "days_cover": round(days, 1),
                }
            )
        cover_rows.sort(key=lambda r: r["days_cover"])
        at_risk = [r for r in cover_rows if r["days_cover"] <= LOW_COVER_DAYS]
        out["cover"] = cover_rows[:20]
        out["at_risk_count"] = len(at_risk)
        if at_risk:
            insights.alerts.append(
                Alert(
                    CRITICAL if len(at_risk) > 2 else WARNING,
                    f"{len(at_risk)} SKU(s) will run out within {LOW_COVER_DAYS} days",
                    "At the current run rate: "
                    + ", ".join(
                        f"{r['label']} ({r['days_cover']:g}d)" for r in at_risk[:3]
                    )
                    + ".",
                    value=float(len(at_risk)),
                    code="stockout_risk",
                    entities=[f"{r['label']} ({r['days_cover']:g}d)" for r in at_risk],
                )
            )
    return out


def _join_field(frame: pd.DataFrame, sales: pd.DataFrame | None) -> str | None:
    if sales is None:
        return None
    for candidate in (schema.SKU, schema.ITEM):
        if candidate in frame.columns and candidate in sales.columns:
            return candidate
    return None


def _sales_span_days(sold: pd.DataFrame, as_of: datetime) -> float:
    if schema.DATE not in sold.columns or sold[schema.DATE].isna().all():
        return 0.0
    dates = sold[schema.DATE].dropna()
    span = (dates.max() - dates.min()).days + 1
    return float(max(span, 1))


# --- receivables ----------------------------------------------------------


def _analyse_receivables(frame: pd.DataFrame, insights: Insights, as_of: datetime) -> dict:
    out: dict = {"rows": int(len(frame.index))}
    if schema.OUTSTANDING not in frame.columns:
        return out

    amounts = frame[schema.OUTSTANDING]
    open_items = frame[amounts.fillna(0) > 0].copy()
    out["total"] = float(open_items[schema.OUTSTANDING].sum())
    out["invoices"] = int(len(open_items.index))

    if schema.PARTY in open_items.columns:
        out["parties"] = int(open_items["party_key"].nunique(dropna=True))
        out["top_debtors"] = _top_by(
            open_items, "party_key", schema.PARTY, schema.OUTSTANDING, 10
        )

    basis = schema.DUE_DATE if schema.DUE_DATE in open_items.columns else (
        schema.DATE if schema.DATE in open_items.columns else None
    )
    if basis is None or open_items[basis].isna().all():
        out["ageing_basis"] = None
        return out

    reference = pd.Timestamp(as_of).normalize()
    days_past = (reference - open_items[basis]).dt.days
    open_items["_days_past"] = days_past
    out["ageing_basis"] = "due date" if basis == schema.DUE_DATE else "invoice date"

    buckets = []
    for label, low, high in AGEING_BUCKETS:
        if label == "Not due":
            mask = days_past < 0
        else:
            mask = (days_past >= low) & (days_past <= high)
        subset = open_items[mask.fillna(False)]
        buckets.append(
            {
                "label": label,
                "amount": float(subset[schema.OUTSTANDING].sum()),
                "count": int(len(subset.index)),
            }
        )
    out["ageing"] = buckets

    overdue = open_items[days_past.fillna(-1) > 0]
    out["overdue_total"] = float(overdue[schema.OUTSTANDING].sum())
    out["overdue_count"] = int(len(overdue.index))

    severe = open_items[days_past.fillna(-1) > 90]
    out["over_90_total"] = float(severe[schema.OUTSTANDING].sum())

    worst = overdue.sort_values("_days_past", ascending=False).head(15)
    out["worst_overdue"] = [
        {
            "party": _text(row.get(schema.PARTY)) or "—",
            "invoice": _text(row.get(schema.INVOICE_NO)),
            "amount": _float(row.get(schema.OUTSTANDING)),
            "days": int(row["_days_past"]) if pd.notna(row["_days_past"]) else None,
        }
        for _, row in worst.iterrows()
    ]

    if out["overdue_total"] > 0:
        share = out["overdue_total"] / out["total"] if out["total"] else 0
        insights.alerts.append(
            Alert(
                CRITICAL if share >= 0.5 else WARNING,
                f"{_inr(out['overdue_total'])} is overdue",
                f"{out['overdue_count']} invoice(s) past their {out['ageing_basis']}"
                + (
                    f", of which {_inr(out['over_90_total'])} is more than 90 days old."
                    if out["over_90_total"] > 0
                    else "."
                ),
                value=out["overdue_total"],
                code="overdue_ar",
                entities=[
                    f"{r['party']} · {r['invoice']} · {_inr(r['amount'])} · {r['days']}d"
                    for r in out.get("worst_overdue", [])
                ],
            )
        )

    return out


# --- small helpers --------------------------------------------------------


def _row_label(row, label_field: str | None) -> str:
    if label_field:
        value = _text(row.get(label_field))
        if value:
            return value
    for fallback in (schema.ITEM, schema.SKU, schema.PARTY):
        value = _text(row.get(fallback))
        if value:
            return value
    return "—"


def _text(value) -> str | None:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _float(value) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _inr(amount: float) -> str:
    """Short Indian-format money, for alert text."""
    amount = float(amount or 0)
    if abs(amount) >= 1_00_00_000:
        return f"₹{amount / 1_00_00_000:.2f} Cr"
    if abs(amount) >= 1_00_000:
        return f"₹{amount / 1_00_000:.2f} L"
    if abs(amount) >= 1_000:
        return f"₹{amount / 1_000:.1f} K"
    return f"₹{amount:,.0f}"
