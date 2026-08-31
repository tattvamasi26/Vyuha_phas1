"""Canonical field vocabulary.

Every distributor names their columns differently — "Party Name", "Customer",
"Dealer", "Buyer", "M/s" all mean the same thing. This module defines the
canonical field names the rest of the pipeline works with, plus the messy
real-world aliases we map onto them.

Matching happens on a *normalised* header string (lowercase, punctuation and
whitespace stripped) so "Qty.", "QTY", "Qty ", and "qty" all collapse to "qty".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- canonical field names ------------------------------------------------

DATE = "date"
DUE_DATE = "due_date"
PARTY = "party"
SKU = "sku"
ITEM = "item"
CATEGORY = "category"
QTY = "qty"
RATE = "rate"
AMOUNT = "amount"
STOCK_QTY = "stock_qty"
REORDER_LEVEL = "reorder_level"
OUTSTANDING = "outstanding"
INVOICE_NO = "invoice_no"
LOCATION = "location"


@dataclass(frozen=True)
class FieldSpec:
    """One canonical field and the header text that resolves to it.

    ``exact`` aliases are compared against the whole normalised header and are
    worth more than ``contains`` fragments, which only need to appear somewhere
    inside it. ``kind`` drives type coercion in the cleaning stage.
    """

    name: str
    kind: str  # "date" | "number" | "text"
    exact: tuple[str, ...] = ()
    contains: tuple[str, ...] = ()
    # Fragments that veto a match even when an alias hit (e.g. "closing stock
    # value" must not be read as a plain quantity).
    veto: tuple[str, ...] = ()
    aggregate: str = "sum"


FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        DATE,
        "date",
        exact=("date", "dt", "billdate", "invoicedate", "txndate", "voucherdate",
               "salesdate", "orderdate", "entrydate", "transactiondate", "postingdate"),
        contains=("invoicedate", "billdate", "voucherdate", "orderdate", "salesdate"),
        veto=("due", "expiry", "expire", "delivery"),
    ),
    FieldSpec(
        DUE_DATE,
        "date",
        exact=("duedate", "paymentduedate", "dueon", "maturitydate"),
        contains=("duedate", "maturity"),
    ),
    FieldSpec(
        PARTY,
        "text",
        exact=("party", "partyname", "customer", "customername", "client",
               "clientname", "dealer", "dealername", "buyer", "buyername",
               "ledger", "ledgername", "accountname", "ms", "msname",
               "distributor", "retailer", "shopname", "firmname", "supplier",
               # Tally, Busy and Marg all head the ledger column "Particulars".
               # It is the single most common column name in Indian accounting
               # exports and the engine did not know it.
               "particulars", "particular", "ledgeraccount", "accountledger",
               "partyledger", "nameofparty", "customerledger"),
        contains=("partyname", "customername", "dealername", "buyername",
                  "clientname", "ledgername"),
        veto=("code", "id", "gst", "phone", "mobile", "address", "city",
              # "Dealer Rate" / "Supplier Price" are numbers about money, not
              # the name of anybody.
              "rate", "price", "amount", "value", "qty", "discount"),
        aggregate="count",
    ),
    FieldSpec(
        SKU,
        "text",
        exact=("sku", "itemcode", "productcode", "code", "partno", "partnumber",
               "articlecode", "materialcode", "itemid", "productid", "modelno",
               "modelnumber", "barcode", "hsn"),
        contains=("itemcode", "productcode", "skucode", "partno", "articleno"),
        aggregate="count",
    ),
    FieldSpec(
        ITEM,
        "text",
        exact=("item", "itemname", "product", "productname", "description",
               "particulars", "material", "materialname", "goods", "articlename",
               "itemdescription", "productdescription", "modelname"),
        contains=("itemname", "productname", "itemdescription", "particulars"),
        veto=("code", "id", "no"),
        aggregate="count",
    ),
    FieldSpec(
        CATEGORY,
        "text",
        exact=("category", "itemcategory", "productcategory", "group",
               "itemgroup", "productgroup", "brand", "type", "itemtype",
               "segment", "division"),
        contains=("category", "brand", "itemgroup", "productgroup"),
        aggregate="count",
    ),
    FieldSpec(
        QTY,
        "number",
        exact=("qty", "quantity", "qtysold", "soldqty", "billedqty", "nos",
               "units", "unitssold", "pcs", "pieces", "cases", "boxes",
               "salesqty", "dispatchqty", "issuedqty"),
        contains=("qtysold", "soldqty", "salesqty", "billedqty", "quantitysold",
                  "quantity", "qty"),
        veto=("stock", "balance", "closing", "opening", "onhand", "available",
              "reorder", "min", "value", "amount", "free", "return"),
    ),
    FieldSpec(
        RATE,
        "number",
        exact=("rate", "price", "unitprice", "unitrate", "mrp", "sellingprice",
               "sp", "listprice", "rateperunit", "costprice", "purchaserate",
               "unitcost",
               # A price list's second column is the trade price. Without these,
               # "Dealer Rate" matched PARTY on the word "dealer" and a rate
               # column was read as a customer name.
               "dealerrate", "dealerprice", "tradeprice", "traderate",
               "wholesalerate", "wholesaleprice", "netrate", "billrate",
               "salerate", "saleprice", "retailprice"),
        contains=("unitprice", "unitrate", "rateper", "priceperunit", "unitcost"),
        veto=("total", "net", "gross", "amount"),
        aggregate="mean",
    ),
    FieldSpec(
        AMOUNT,
        "number",
        exact=("amount", "amt", "value", "total", "totalamount", "netamount",
               "grossamount", "invoicevalue", "billamount", "salesvalue",
               "netvalue", "linetotal", "taxablevalue", "turnover", "sales",
               "revenue", "grandtotal",
               # Double-entry exports carry the sale in the debit column. Credit
               # is deliberately NOT here: in a sales register it is the
               # contra-entry, and reading both would double every total.
               "debit", "debitamount", "dr", "dramount", "salesamount"),
        contains=("totalamount", "netamount", "invoicevalue", "billamount",
                  "salesvalue", "linetotal", "grossamount"),
        veto=("outstanding", "pending", "due", "balance", "received", "paid",
              "stockvalue"),
    ),
    FieldSpec(
        STOCK_QTY,
        "number",
        exact=("stock", "stockqty", "closingstock", "closingqty", "balanceqty",
               "onhand", "onhandqty", "available", "availableqty", "inventory",
               "inventoryqty", "currentstock", "instock", "physicalstock",
               "godownstock", "openingstock",
               # A rate list writes the quantity column as where the stock is
               # kept: "In Godown", "Godown Qty", "At Store". Without these the
               # column resolves to LOCATION, the sheet has no quantity, and no
               # table rule matches -- the whole file is skipped.
               "ingodown", "godownqty", "qtyingodown", "stockingodown",
               "atgodown", "instore", "atstore", "onfloor", "shelfqty",
               "qtyonhand", "qtyavailable", "qtyinstock", "balqty"),
        contains=("closingstock", "stockqty", "onhand", "availableqty",
                  "currentstock", "balancestock", "instock", "ingodown",
                  "godownqty", "qtyinstock"),
        veto=("value", "amount", "reorder", "min", "max", "days"),
    ),
    FieldSpec(
        REORDER_LEVEL,
        "number",
        exact=("reorderlevel", "reorderpoint", "reorderqty", "minlevel",
               "minstock", "minimumstock", "minimumlevel", "safetystock",
               "rol", "minqty", "threshold"),
        contains=("reorder", "minlevel", "minstock", "safetystock", "minimumstock"),
    ),
    FieldSpec(
        OUTSTANDING,
        "number",
        exact=("outstanding", "outstandingamount", "balance", "balanceamount",
               "balancedue", "duedmount", "dueamount", "pending",
               "pendingamount", "receivable", "receivables", "amountdue",
               "closingbalance", "unpaid", "unpaidamount", "overdue",
               "overdueamount", "amountpending"),
        contains=("outstanding", "balancedue", "amountdue", "pendingamount",
                  "receivable", "unpaid", "overdueamount", "closingbalance"),
    ),
    FieldSpec(
        INVOICE_NO,
        "text",
        exact=("vchno", "vchnumber", "vouchernumber", "voucherno", "docno",
               "documentno", "refno", "referenceno",
               "invoiceno", "invoicenumber", "billno", "billnumber", "invno",
               "voucherno", "vouchernumber", "docno", "documentno", "orderno",
               "ordernumber", "billref", "reference", "refno"),
        contains=("invoiceno", "billno", "voucherno", "documentno", "orderno"),
        aggregate="count",
    ),
    FieldSpec(
        LOCATION,
        "text",
        exact=("location", "warehouse", "godown", "branch", "store", "depot",
               "city", "region", "territory", "zone", "area", "state"),
        contains=("warehouse", "godown", "branch", "location", "territory"),
        aggregate="count",
    ),
)

FIELDS_BY_NAME: dict[str, FieldSpec] = {f.name: f for f in FIELDS}

# Columns that are real, useful to a human, and meaningless to us. Left
# unmapped on purpose so free-text guessing does not adopt "Remarks" as the
# product description.
NOISE_HEADERS: frozenset[str] = frozenset({
    "remark", "remarks", "narration", "note", "notes", "comment", "comments",
    "status", "sno", "srno", "slno", "serialno", "sr", "sl", "no",
    "gstin", "gst", "gstno", "pan", "phone", "mobile", "contact", "email",
    "address", "createdby", "enteredby", "salesman", "salesperson", "agent",
    "terms", "mode", "paymentmode", "signature", "attachment",
    # A unit of measure is a label, not a measurement. "Unit" was being
    # adopted as a party name on a price list, because it is text and the
    # value-sniffer had nothing better to do with it.
    "unit", "units", "uom", "unitofmeasure", "measure", "packing", "pack",
    # Double-entry scaffolding. "Credit" is the contra-entry of a sale and
    # would double every total if adopted; opening balance is last period's
    # closing and belongs to a period this file is not reporting on.
    "credit", "creditamount", "cr", "opening", "openingbalance", "vchtype",
    "vouchertype", "entrytype", "dc", "drcr",
})

NUMERIC_FIELDS = tuple(f.name for f in FIELDS if f.kind == "number")
DATE_FIELDS = tuple(f.name for f in FIELDS if f.kind == "date")
TEXT_FIELDS = tuple(f.name for f in FIELDS if f.kind == "text")

# Human labels for anything we surface in the report.
LABELS: dict[str, str] = {
    DATE: "Date",
    DUE_DATE: "Due date",
    PARTY: "Party",
    SKU: "SKU",
    ITEM: "Item",
    CATEGORY: "Category",
    QTY: "Qty",
    RATE: "Rate",
    AMOUNT: "Amount",
    STOCK_QTY: "Stock qty",
    REORDER_LEVEL: "Reorder level",
    OUTSTANDING: "Outstanding",
    INVOICE_NO: "Invoice no.",
    LOCATION: "Location",
}

# --- table kinds ----------------------------------------------------------

SALES = "sales"
STOCK = "stock"
RECEIVABLES = "receivables"
UNKNOWN = "unknown"

TABLE_LABELS = {
    SALES: "Sales",
    STOCK: "Stock",
    RECEIVABLES: "Receivables",
    UNKNOWN: "Unclassified",
}


@dataclass
class TableKindRule:
    kind: str
    # Every field here must be present for the rule to fire.
    required: tuple[str, ...]
    # Each field here that is present adds to the confidence score.
    supporting: tuple[str, ...] = field(default_factory=tuple)


# Order matters: the first rule whose ``required`` fields are all present and
# which scores highest wins. Receivables is checked before sales because an
# outstanding column is a much stronger signal than a generic amount column.
TABLE_RULES: tuple[TableKindRule, ...] = (
    TableKindRule(RECEIVABLES, required=(OUTSTANDING,),
                  supporting=(PARTY, DUE_DATE, INVOICE_NO, DATE, AMOUNT)),
    TableKindRule(STOCK, required=(STOCK_QTY,),
                  supporting=(SKU, ITEM, REORDER_LEVEL, RATE, CATEGORY, LOCATION)),
    TableKindRule(SALES, required=(AMOUNT,),
                  supporting=(DATE, PARTY, SKU, ITEM, QTY, RATE, INVOICE_NO)),
    TableKindRule(SALES, required=(QTY, RATE),
                  supporting=(DATE, PARTY, SKU, ITEM, INVOICE_NO)),
)


# --- header normalisation -------------------------------------------------

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_UNNAMED = re.compile(r"^unnamed[:_]?\d*$")


def normalise(header: object) -> str:
    """Collapse a raw header cell to a comparable token.

    ``"Party Name "`` -> ``"partyname"``; ``"Qty. (Nos)"`` -> ``"qtynos"``.
    Returns ``""`` for blanks and pandas' ``Unnamed: 3`` placeholders.
    """
    if header is None:
        return ""
    text = str(header).strip().lower()
    if not text or text in {"nan", "nat", "none"}:
        return ""
    text = _NON_ALNUM.sub("", text)
    if not text or _UNNAMED.match(text):
        return ""
    return text
