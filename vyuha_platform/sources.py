"""Accept more than a spreadsheet.

The engine reads .xlsx/.xlsm/.csv natively. Everything else is *converted* to a
CSV first and handed to the same unchanged pipeline — so a photographed stock
register and a clean Excel export travel the same five stages and land in the
same dashboard.

    .xlsx .xlsm .csv   -> native, no conversion
    .txt .tsv          -> delimiter sniffing, local, free
    .png .jpg .webp    -> Claude vision (handwriting, photos of registers)
    .pdf               -> its own text layer if it has one, else Claude vision

Vision needs an Anthropic API key. Without one the file is rejected with a
message naming exactly what is missing, rather than failing obscurely — the
platform stays usable with no accounts configured.

Every conversion returns an ``Extraction`` recording how the file was read and
what was assumed. A number that came out of a photograph must never be
indistinguishable from one typed into Excel.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path

NATIVE = {".xlsx", ".xlsm", ".csv"}
TEXT = {".txt", ".tsv", ".dat"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DOCS = {".pdf"}
ACCEPTED = NATIVE | TEXT | IMAGES | DOCS

MAX_IMAGE_BYTES = 4_500_000
MAX_PDF_BYTES = 30_000_000


@dataclass
class Extraction:
    """How a file was turned into something the engine can read."""

    ok: bool
    kind: str                       # native | text | pdf-text | vision-image | vision-pdf
    path: Path | None = None        # what to hand the engine
    method: str = ""                # human-readable provenance
    confidence: str = "high"        # high | medium | low
    notes: list[str] = field(default_factory=list)
    error: str = ""
    needs_action: str = ""


def classify(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in NATIVE:
        return "native"
    if ext in TEXT:
        return "text"
    if ext in IMAGES:
        return "image"
    if ext in DOCS:
        return "pdf"
    return "unsupported"


def _write_csv(rows: list[list[str]], out: Path) -> int:
    width = max(len(r) for r in rows)
    with out.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows([list(r) + [""] * (width - len(r)) for r in rows])
    return width


# --------------------------------------------------------------- delimited text

def _from_text(source: Path, workdir: Path) -> Extraction:
    raw = source.read_text(encoding="utf-8", errors="replace")
    sample = "\n".join(raw.splitlines()[:40])
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delim = "\t" if "\t" in sample else ","

    rows = [r for r in csv.reader(io.StringIO(raw), delimiter=delim)
            if any(str(c).strip() for c in r)]
    if not rows:
        return Extraction(False, "text", error="That text file has no readable rows.")

    out = workdir / (source.stem + ".csv")
    _write_csv(rows, out)
    shown = "tab" if delim == "\t" else delim
    return Extraction(True, "text", out,
                      method=f"Delimited text, {shown} separated",
                      notes=[f"Read {len(rows)} row(s) using {shown} as the separator."])


# ------------------------------------------------------------------ pdf (text)

def _split_columns(line: str) -> list[str]:
    """A table line in extracted PDF text separates columns by runs of spaces."""
    out, cur, gap = [], "", 0
    for ch in line:
        if ch == " ":
            gap += 1
            cur += ch
        else:
            if gap >= 2:
                out.append(cur)
                cur = ""
            gap = 0
            cur += ch
    if cur:
        out.append(cur)
    return out


def _pdf_text_rows(source: Path) -> list[list[str]]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(source))
    except Exception:
        return []

    rows: list[list[str]] = []
    for page in reader.pages[:25]:
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        for line in text.splitlines():
            cells = [c.strip() for c in _split_columns(line) if c.strip()]
            if len(cells) >= 2:
                rows.append(cells)
    return rows


# --------------------------------------------------------------------- vision

VISION_PROMPT = """This is a business document from an Indian distributor or small manufacturer \
- a printed stock register, a handwritten ledger page, an invoice list, or a photographed \
spreadsheet.

Transcribe the tabular data into rows:
- The first row must be the column headers, exactly as written on the page.
- Return every data row you can read, in the order they appear.
- Keep numbers exactly as written, including a rupee sign, commas or brackets. Do not \
convert or round them.
- Keep dates exactly as written.
- Use an empty string for a blank cell.
- Skip decorative rows: the business name and address, page numbers, signatures.
- Do NOT include a Grand Total or Subtotal row.
- If a handwritten value is genuinely ambiguous, give your best reading and note it.
- If the page holds no tabular data, return no rows and say why in notes.

Also say what kind of table this is: sales, stock, receivables, or unknown."""

SCHEMA = {
    "type": "object",
    "properties": {
        "table_kind": {"type": "string", "enum": ["sales", "stock", "receivables", "unknown"]},
        "rows": {"type": "array",
                 "description": "First row is headers; the rest are data rows.",
                 "items": {"type": "array", "items": {"type": "string"}}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["table_kind", "rows", "confidence", "notes"],
    "additionalProperties": False,
}


def _vision_block(source: Path) -> dict:
    data = base64.standard_b64encode(source.read_bytes()).decode("utf-8")
    if source.suffix.lower() == ".pdf":
        return {"type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
    media = mimetypes.guess_type(source.name)[0] or "image/png"
    if media == "image/jpg":
        media = "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def _from_vision(source: Path, workdir: Path, settings) -> Extraction:
    kind = "vision-pdf" if source.suffix.lower() == ".pdf" else "vision-image"

    if not settings.vision_live:
        return Extraction(False, kind,
                          error="Reading images, scans and handwriting needs a Claude API key.",
                          needs_action="Add an Anthropic API key in Settings, then re-upload.")

    size = source.stat().st_size
    cap = MAX_PDF_BYTES if kind == "vision-pdf" else MAX_IMAGE_BYTES
    if size > cap:
        return Extraction(False, kind,
                          error=f"That file is {size / 1_000_000:.1f} MB, over the "
                                f"{cap // 1_000_000} MB limit.",
                          needs_action="Lower the resolution or split it, then re-upload.")

    try:
        import anthropic
    except ImportError:
        return Extraction(False, kind, error="The anthropic package is not installed.")

    client = anthropic.Anthropic(api_key=settings.anthropic_key)
    try:
        response = client.messages.create(
            model=settings.vision_model,
            max_tokens=16000,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user",
                       "content": [_vision_block(source),
                                   {"type": "text", "text": VISION_PROMPT}]}],
        )
    except anthropic.AuthenticationError:
        return Extraction(False, kind, error="The Claude API key was rejected.",
                          needs_action="Check the key in Settings.")
    except anthropic.RateLimitError:
        return Extraction(False, kind, error="Claude is rate-limiting this key.",
                          needs_action="Wait a minute, then re-upload.")
    except anthropic.APIError as exc:
        return Extraction(False, kind, error=f"Claude could not read it: {exc}")

    # A refusal comes back as a 200 with empty content - check before indexing.
    if response.stop_reason == "refusal":
        return Extraction(False, kind, error="Claude declined to read this document.")

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return Extraction(False, kind, error="The reply was not readable as a table.")

    rows = [[str(c) for c in row] for row in parsed.get("rows", [])
            if any(str(c).strip() for c in row)]
    if len(rows) < 2:
        why = "; ".join(parsed.get("notes") or []) or "no tabular data found"
        return Extraction(False, kind, error=f"No table could be read from that file ({why}).",
                          needs_action="Re-photograph the page straight on, whole table visible.")

    out = workdir / (source.stem + ".csv")
    width = _write_csv(rows, out)
    label = ("Handwriting or photo read by Claude" if kind == "vision-image"
             else "Scanned PDF read by Claude")
    notes = [f"Read {len(rows) - 1} data row(s) and {width} column(s).",
             f"Read as a {parsed.get('table_kind', 'unknown')} table."]
    notes += [str(n) for n in (parsed.get("notes") or [])]
    return Extraction(True, kind, out, method=label,
                      confidence=parsed.get("confidence", "medium"), notes=notes)


# ------------------------------------------------------------------ entrypoint

def _from_chat(source: Path, workdir: Path, settings,
               item_names: list[str] | None,
               _rates: dict | None = None) -> "Extraction | None":
    """Read a WhatsApp export, or return None if it is not one.

    Returns ``None`` rather than a failed ``Extraction`` when the file is not a
    chat, so the caller falls through to the ordinary delimited-text path. A
    file that *is* a chat but yields nothing is a real failure and is reported
    as one — silently handing an empty CSV to the engine would show the client
    a dashboard of zeros and call it success.
    """
    from . import intake

    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not intake.looks_like_chat(text):
        return None

    extract = intake.parse_chat(text, item_names or [], settings)
    if not extract.ok:
        return Extraction(False, "whatsapp", error=extract.error,
                          needs_action=extract.needs_action)

    out = workdir / (source.stem + ".csv")
    # Price the orders from the client's own rate card. Without it every line
    # is worth zero and the engine reports a thread full of orders as no
    # revenue at all.
    intake.to_csv(extract, out, rates=_rates or {})
    orders, payments = len(extract.orders), len(extract.payments)
    return Extraction(
        True, "whatsapp", out, method=extract.method, confidence="medium",
        notes=[f"Read {extract.messages} message(s) from the thread.",
               f"Found {orders} order(s) and {payments} payment(s).",
               "Orders lifted out of a conversation are drafts - check them "
               "against the thread before they are treated as sales."])


def prepare(source: Path, workdir: Path, settings,
            item_names: list[str] | None = None,
            rates: dict | None = None) -> Extraction:
    """Turn any accepted file into something ``pipeline.run()`` can read.

    ``item_names`` is the client's own catalogue. It is only used for a WhatsApp
    export, where an order has to be matched against the products they actually
    sell; every other path ignores it, which is why it is optional and why no
    existing caller had to change.
    """
    source, workdir = Path(source), Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    kind = classify(source.name)

    if kind == "native":
        return Extraction(True, "native", source, method="Read directly as a spreadsheet")

    if kind == "text":
        # A WhatsApp export is a .txt, so it arrives here — but it is a
        # conversation, not a delimited table, and the sniffer chokes on it
        # ("Expected 2 fields in line 3, saw 3"). Check for a chat first: the
        # test is strict enough that a real CSV never trips it.
        chat = _from_chat(source, workdir, settings, item_names, rates)
        if chat is not None:
            return chat
        return _from_text(source, workdir)

    if kind == "pdf":
        rows = _pdf_text_rows(source)
        if len(rows) >= 3:
            out = workdir / (source.stem + ".csv")
            _write_csv(rows, out)
            return Extraction(
                True, "pdf-text", out, method="Text layer extracted from the PDF",
                confidence="medium",
                notes=[f"Pulled {len(rows)} row(s) from the PDF text layer.",
                       "Column splitting in a text PDF is approximate - check the "
                       "read-back panel before trusting the numbers."])
        return _from_vision(source, workdir, settings)

    if kind == "image":
        return _from_vision(source, workdir, settings)

    return Extraction(False, "unsupported",
                      error=f"Vyuha cannot read '{source.suffix or 'that file type'}' yet.",
                      needs_action="Send a spreadsheet, CSV, PDF, or a photo of the page.")
