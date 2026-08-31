"""Turning an :class:`invoice.Invoice` into something you can hand over.

Separate from ``invoice.py`` for the same reason ``decks.py`` splits outline from
rendering: what the document *says* is arithmetic and law, what it *looks like*
is design, and mixing them means a template change can alter a total.

**The HTML is standalone and self-contained** — inline CSS, no scripts, no
fonts, no images. An invoice gets forwarded, saved, printed from a phone in a
shop with no internet, and attached to an email six months later. Anything that
needs the network is a bill that renders blank on the day it matters.

It is also **built to print**. An A4 `@page` box, a table that repeats its header
across pages, black on white regardless of the viewer's dark mode, and no
element that survives into the paper it should not. "Print to PDF" from a
browser is how most of these will actually become PDFs, so that path has to be
the good one rather than the fallback.

``to_pdf`` exists for the times a real file is needed without a browser in the
loop. It uses ``Rs.`` rather than the rupee sign, for the same reason
``exports.py`` does: the Helvetica core fonts have no glyph for it and would
print a black box on a legal document.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from pathlib import Path

from vyuha import fmt

from .invoice import STATES, Invoice

E = html.escape


def rs(value) -> str:
    return fmt.rupees(value or 0, symbol="₹")


def plain(value) -> str:
    """Digits only, for a column that has a ₹ in its heading already."""
    return f"{float(value or 0):,.2f}"


def _pretty(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso[:10]).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return iso or ""


def _state(code: str) -> str:
    code = (code or "").upper()
    return f"{STATES[code]} ({code})" if code in STATES else code


#: Indian invoices print the total in words, and a buyer's clerk checks it
#: against the figure. Getting it wrong is worse than omitting it, so this
#: handles the full lakh/crore system rather than a westernised approximation.
_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
         "Eighty", "Ninety")


def _under_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def in_words(amount: float) -> str:
    """"One Lakh Three Thousand Rupees Only"."""
    rupees = int(round(float(amount or 0)))
    if rupees == 0:
        return "Zero Rupees Only"
    parts = []
    for divisor, label in ((10_000_000, "Crore"), (100_000, "Lakh"),
                           (1_000, "Thousand"), (100, "Hundred")):
        if rupees >= divisor:
            count = rupees // divisor
            rupees %= divisor
            parts.append(f"{_under_hundred(count) if divisor < 10_000_000 else in_words_int(count)} {label}")
    if rupees:
        parts.append(_under_hundred(rupees))
    return " ".join(p for p in parts if p).strip() + " Rupees Only"


def in_words_int(n: int) -> str:
    """Crores can themselves run into thousands, so that group recurses."""
    if n < 100:
        return _under_hundred(n)
    return in_words(n).replace(" Rupees Only", "")


# --------------------------------------------------------------------- styling

#: Three looks. They differ in what they emphasise, not in colour: Classic is
#: ruled and formal because that is what a clerk expects; Modern gives the
#: payable figure the whole width; Compact squeezes a forty-line bill onto one
#: page, which a distributor's invoices genuinely are.
_SKINS = {
    "classic": {
        "font": "Georgia, 'Times New Roman', serif",
        "rule": "1px solid #111", "head_bg": "#f2f2f2", "head_ink": "#111",
        "pad": "7px 9px", "size": "12px", "total": "20px",
        "frame": "border:1.5px solid #111;",
    },
    "modern": {
        "font": "'Helvetica Neue', Arial, sans-serif",
        "rule": "1px solid #dcdcdc", "head_bg": "#111", "head_ink": "#fff",
        "pad": "11px 12px", "size": "12.5px", "total": "27px",
        "frame": "border:0;",
    },
    "compact": {
        "font": "'Helvetica Neue', Arial, sans-serif",
        "rule": "1px solid #d8d8d8", "head_bg": "#eee", "head_ink": "#111",
        "pad": "4px 7px", "size": "10.5px", "total": "17px",
        "frame": "border:1px solid #ccc;",
    },
}


def render_html(inv: Invoice, client, template: str = "") -> str:
    """One self-contained, print-ready page."""
    skin = _SKINS.get(template or inv.template or "classic", _SKINS["classic"])
    taxed = inv.taxed
    tax_cols = 2 if taxed else 0

    gaps = ""
    if taxed and not client.gstin:
        gaps = ('<div class="warn">This is a bill of supply, not a tax invoice — '
                'no GSTIN is set for your business.</div>')

    # ---- line rows
    rows = ""
    for n, ln in enumerate(inv.lines, start=1):
        tax_cells = (f'<td class="n">{ln.gst_rate:g}%</td>'
                     f'<td class="n">{plain(ln.tax)}</td>') if taxed else ""
        rows += (f'<tr><td class="c">{n}</td>'
                 f'<td><b>{E(ln.item)}</b>'
                 + (f'<div class="sub">{E(ln.sku)}</div>' if ln.sku else "")
                 + "</td>"
                 + (f'<td class="c">{E(ln.hsn)}</td>' if taxed else "")
                 + f'<td class="n">{ln.qty:g} {E(ln.unit)}</td>'
                 f'<td class="n">{plain(ln.rate)}</td>'
                 f'<td class="n">{plain(ln.taxable)}</td>'
                 f'{tax_cells}'
                 f'<td class="n"><b>{plain(ln.total)}</b></td></tr>')

    headers = ('<th class="c">#</th><th>Description</th>'
               + ('<th class="c">HSN</th>' if taxed else "")
               + '<th class="n">Qty</th><th class="n">Rate</th>'
               '<th class="n">Taxable</th>'
               + ('<th class="n">GST</th><th class="n">Tax</th>' if taxed else "")
               + '<th class="n">Amount</th>')

    # ---- totals block
    totals = f'<tr><td>Taxable value</td><td class="n">{plain(inv.taxable)}</td></tr>'
    if taxed:
        if inv.intra_state:
            totals += (f'<tr><td>CGST</td><td class="n">{plain(inv.cgst)}</td></tr>'
                       f'<tr><td>SGST</td><td class="n">{plain(inv.sgst)}</td></tr>')
        else:
            totals += f'<tr><td>IGST</td><td class="n">{plain(inv.igst)}</td></tr>'
    if abs(inv.round_off) >= 0.01:
        totals += (f'<tr><td>Rounding</td>'
                   f'<td class="n">{inv.round_off:+.2f}</td></tr>')

    # ---- HSN summary, only when rates actually differ
    rate_rows = inv.by_rate()
    hsn_block = ""
    if taxed and len(rate_rows) > 1:
        cells = "".join(
            f'<tr><td class="c">{g["gst_rate"]:g}%</td>'
            f'<td class="n">{plain(g["taxable"])}</td>'
            + (f'<td class="n">{plain(g["half"])}</td>'
               f'<td class="n">{plain(g["half"])}</td>' if inv.intra_state
               else f'<td class="n">{plain(g["tax"])}</td>')
            + f'<td class="n">{plain(g["tax"])}</td></tr>' for g in rate_rows)
        head = ('<th class="c">Rate</th><th class="n">Taxable</th>'
                + ('<th class="n">CGST</th><th class="n">SGST</th>'
                   if inv.intra_state else '<th class="n">IGST</th>')
                + '<th class="n">Total tax</th>')
        hsn_block = (f'<div class="sec">Tax summary</div>'
                     f'<table class="lines"><thead><tr>{head}</tr></thead>'
                     f'<tbody>{cells}</tbody></table>')

    bank = ""
    if client.bank_name or client.bank_account:
        bank = (f'<div class="blk"><div class="lbl">Bank details</div>'
                f'{E(client.bank_name)}<br>'
                + (f'A/c {E(client.bank_account)}<br>' if client.bank_account else "")
                + (f'IFSC {E(client.bank_ifsc)}' if client.bank_ifsc else "")
                + "</div>")

    status = ('<span class="paid">PAID</span>' if inv.paid
              else f'<span class="due">DUE{" " + _pretty(inv.due_date) if inv.due_date else ""}</span>')

    title = "TAX INVOICE" if (taxed and client.gstin) else "BILL OF SUPPLY"

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(inv.number)} · {E(client.name)}</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; padding:0; background:#fff; color:#111;
    font-family:{skin['font']}; font-size:{skin['size']}; line-height:1.5;
    -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  .sheet {{ max-width:210mm; margin:0 auto; padding:16mm 14mm; {skin['frame']} }}
  @media print {{ .sheet {{ padding:0; border:0; max-width:none; }}
                  .noprint {{ display:none !important; }} }}
  .top {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start;
    padding-bottom:14px; border-bottom:{skin['rule']}; }}
  .biz h1 {{ margin:0 0 4px; font-size:21px; letter-spacing:.01em; }}
  .biz .meta {{ font-size:11.5px; color:#444; white-space:pre-line; }}
  .doc {{ text-align:right; white-space:nowrap; }}
  .doc .kind {{ font-size:13px; letter-spacing:.16em; font-weight:700; }}
  .doc .no {{ font-size:15px; font-weight:700; margin-top:6px; }}
  .doc .dt {{ font-size:11.5px; color:#444; margin-top:3px; }}
  .paid {{ display:inline-block; margin-top:8px; padding:3px 9px; border:1.5px solid #1a7f4b;
    color:#1a7f4b; font-size:10.5px; font-weight:700; letter-spacing:.1em; }}
  .due {{ display:inline-block; margin-top:8px; padding:3px 9px; border:1.5px solid #a33;
    color:#a33; font-size:10.5px; font-weight:700; letter-spacing:.1em; }}
  .parties {{ display:flex; gap:28px; padding:14px 0; border-bottom:{skin['rule']}; }}
  .parties > div {{ flex:1; }}
  .lbl {{ font-size:9.5px; letter-spacing:.14em; text-transform:uppercase;
    color:#666; margin-bottom:4px; }}
  .parties b {{ font-size:13.5px; }}
  .parties .meta {{ font-size:11.5px; color:#444; white-space:pre-line; margin-top:3px; }}
  table.lines {{ width:100%; border-collapse:collapse; margin-top:16px; }}
  table.lines th {{ background:{skin['head_bg']}; color:{skin['head_ink']};
    font-size:10px; letter-spacing:.08em; text-transform:uppercase; text-align:left;
    padding:{skin['pad']}; border-bottom:{skin['rule']}; }}
  table.lines td {{ padding:{skin['pad']}; border-bottom:{skin['rule']};
    vertical-align:top; }}
  table.lines thead {{ display:table-header-group; }}
  table.lines tr {{ page-break-inside:avoid; }}
  .n {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
  .c {{ text-align:center; white-space:nowrap; }}
  .sub {{ font-size:10px; color:#777; margin-top:2px; }}
  .foot {{ display:flex; gap:28px; margin-top:18px; page-break-inside:avoid; }}
  .foot .left {{ flex:1; }}
  .foot .right {{ width:44%; }}
  table.tot {{ width:100%; border-collapse:collapse; }}
  table.tot td {{ padding:5px 0; }}
  table.tot td.n {{ text-align:right; }}
  .grand {{ border-top:{skin['rule']}; border-bottom:2px solid #111; }}
  .grand td {{ padding:10px 0 !important; font-weight:700; }}
  .grand .amt {{ font-size:{skin['total']}; }}
  .words {{ margin-top:10px; font-size:11.5px; }}
  .words i {{ font-style:normal; color:#666; }}
  .blk {{ margin-top:14px; font-size:11.5px; color:#333; }}
  .sec {{ margin-top:20px; font-size:10px; letter-spacing:.14em;
    text-transform:uppercase; color:#666; }}
  .terms {{ margin-top:16px; padding-top:12px; border-top:{skin['rule']};
    font-size:10.5px; color:#555; }}
  .sign {{ margin-top:34px; text-align:right; font-size:11.5px; }}
  .sign .line {{ margin-top:36px; border-top:1px solid #111; display:inline-block;
    min-width:180px; padding-top:5px; }}
  .warn {{ margin-top:12px; padding:8px 11px; border-left:3px solid #a33;
    background:#fbf0f0; font-size:11px; color:#7a2020; }}
  .bar {{ margin:0 auto 12px; max-width:210mm; padding:10px 14px; background:#111;
    color:#fff; font-size:12px; display:flex; gap:12px; align-items:center; }}
  .bar a {{ color:#fff; background:rgba(255,255,255,.14); padding:6px 12px;
    border-radius:5px; text-decoration:none; font-weight:600; }}
</style></head><body>
<div class="bar noprint">
  <span>Press <b>Ctrl/Cmd + P</b> to print or save as PDF.</span>
  <a href="javascript:window.print()">Print</a>
</div>
<div class="sheet">
  <div class="top">
    <div class="biz">
      <h1>{E(client.name)}</h1>
      <div class="meta">{E(client.address)}
{('GSTIN: ' + E(client.gstin)) if client.gstin else ''}{('  ·  ' + _state(client.state)) if client.state else ''}
{('Phone: +' + E(client.phone)) if client.phone else ''}{('  ·  ' + E(client.email)) if client.email else ''}</div>
    </div>
    <div class="doc">
      <div class="kind">{title}</div>
      <div class="no">{E(inv.number)}</div>
      <div class="dt">{_pretty(inv.date)}</div>
      {status}
    </div>
  </div>

  <div class="parties">
    <div><div class="lbl">Billed to</div><b>{E(inv.party)}</b>
      <div class="meta">{E(inv.party_address)}
{('GSTIN: ' + E(inv.party_gstin)) if inv.party_gstin else ''}
{('Phone: +' + E(inv.party_phone)) if inv.party_phone else ''}</div></div>
    <div><div class="lbl">Place of supply</div>
      <b>{E(_state(inv.party_state) or _state(client.state) or '—')}</b>
      <div class="meta">{'Within the state — CGST and SGST' if inv.intra_state
                          else 'Inter-state — IGST'}</div></div>
  </div>

  <table class="lines"><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>

  {hsn_block}

  <div class="foot">
    <div class="left">
      <div class="words"><i>Amount in words</i><br><b>{E(in_words(inv.rounded))}</b></div>
      {bank}
      {f'<div class="blk"><div class="lbl">Note</div>{E(inv.notes)}</div>' if inv.notes else ''}
    </div>
    <div class="right">
      <table class="tot">{totals}
        <tr class="grand"><td>Total payable</td>
          <td class="n amt">{rs(inv.rounded)}</td></tr></table>
    </div>
  </div>

  {gaps}
  {f'<div class="terms">{E(inv.terms)}</div>' if inv.terms else ''}
  <div class="sign">For <b>{E(client.name)}</b>
    <div class="line">Authorised signatory</div></div>
</div></body></html>"""


# ------------------------------------------------------------------------ PDF

def to_pdf(inv: Invoice, client, out: Path) -> Path:
    """A real file, for when there is no browser in the loop.

    ``Rs.`` not ₹ — the Helvetica core fonts have no rupee glyph and would print
    a black box in the total field of a legal document.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdfcanvas

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    width, height = A4
    c = pdfcanvas.Canvas(str(out), pagesize=A4)
    left, right = 40, width - 40
    ink = colors.HexColor("#111111")
    grey = colors.HexColor("#666666")

    def money(v) -> str:
        return f"Rs. {float(v or 0):,.2f}"

    y = height - 50
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(left, y, client.name[:48])
    c.setFont("Helvetica-Bold", 10)
    title = "TAX INVOICE" if (inv.taxed and client.gstin) else "BILL OF SUPPLY"
    c.drawRightString(right, y, title)
    y -= 15

    c.setFont("Helvetica", 8.5)
    c.setFillColor(grey)
    for line in [client.address, (f"GSTIN: {client.gstin}" if client.gstin else ""),
                 (f"Phone: +{client.phone}" if client.phone else "")]:
        if line:
            c.drawString(left, y, line[:70])
            y -= 11
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(right, height - 65, inv.number)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(right, height - 78, _pretty(inv.date))

    y -= 8
    c.setStrokeColor(ink)
    c.setLineWidth(1)
    c.line(left, y, right, y)
    y -= 18

    c.setFont("Helvetica", 7.5)
    c.setFillColor(grey)
    c.drawString(left, y, "BILLED TO")
    c.drawString(left + 300, y, "PLACE OF SUPPLY")
    y -= 13
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, inv.party[:40])
    c.drawString(left + 300, y, (_state(inv.party_state) or _state(client.state) or "-")[:28])
    y -= 12
    c.setFont("Helvetica", 8.5)
    c.setFillColor(grey)
    if inv.party_gstin:
        c.drawString(left, y, f"GSTIN: {inv.party_gstin}")
    c.drawString(left + 300, y,
                 "Within the state - CGST + SGST" if inv.intra_state
                 else "Inter-state - IGST")
    y -= 22

    taxed = inv.taxed
    cols = ([("#", left, "l"), ("Description", left + 20, "l"), ("Qty", left + 250, "r"),
             ("Rate", left + 320, "r"), ("Taxable", left + 400, "r")]
            + ([("Tax", left + 460, "r")] if taxed else [])
            + [("Amount", right, "r")])

    def header_row(yy: float) -> float:
        c.setFillColor(colors.HexColor("#eeeeee"))
        c.rect(left - 6, yy - 5, right - left + 12, 17, stroke=0, fill=1)
        c.setFillColor(ink)
        c.setFont("Helvetica-Bold", 7.5)
        for label, x, align in cols:
            (c.drawRightString if align == "r" else c.drawString)(x, yy, label.upper())
        return yy - 17

    y = header_row(y)
    c.setFont("Helvetica", 8.5)
    for n, ln in enumerate(inv.lines, start=1):
        if y < 190:
            c.showPage()
            y = height - 60
            y = header_row(y)
            c.setFont("Helvetica", 8.5)
        c.setFillColor(ink)
        c.drawString(left, y, str(n))
        c.drawString(left + 20, y, ln.item[:40])
        c.drawRightString(left + 250, y, f"{ln.qty:g} {ln.unit}")
        c.drawRightString(left + 320, y, f"{ln.rate:,.2f}")
        c.drawRightString(left + 400, y, f"{ln.taxable:,.2f}")
        if taxed:
            c.drawRightString(left + 460, y, f"{ln.tax:,.2f}")
        c.drawRightString(right, y, f"{ln.total:,.2f}")
        y -= 14
        c.setStrokeColor(colors.HexColor("#e2e2e2"))
        c.line(left - 6, y + 4, right + 6, y + 4)

    y -= 14
    rows = [("Taxable value", inv.taxable)]
    if taxed:
        rows += ([("CGST", inv.cgst), ("SGST", inv.sgst)] if inv.intra_state
                 else [("IGST", inv.igst)])
    if abs(inv.round_off) >= 0.01:
        rows.append(("Rounding", inv.round_off))

    c.setFont("Helvetica", 9)
    for label, value in rows:
        c.setFillColor(grey)
        c.drawRightString(right - 110, y, label)
        c.setFillColor(ink)
        c.drawRightString(right, y, money(value))
        y -= 14

    c.setStrokeColor(ink)
    c.setLineWidth(1)
    c.line(right - 220, y + 4, right, y + 4)
    y -= 14
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(right - 110, y, "Total payable")
    c.drawRightString(right, y, money(inv.rounded))
    y -= 26

    c.setFont("Helvetica", 8.5)
    c.setFillColor(grey)
    c.drawString(left, y, "Amount in words")
    y -= 12
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, in_words(inv.rounded)[:88])
    y -= 22

    if client.bank_name or client.bank_account:
        c.setFont("Helvetica", 8.5)
        c.setFillColor(grey)
        c.drawString(left, y, "Bank")
        c.setFillColor(ink)
        c.drawString(left + 40, y,
                     f"{client.bank_name}  A/c {client.bank_account}  "
                     f"IFSC {client.bank_ifsc}"[:80])
        y -= 20

    if inv.terms:
        c.setFillColor(grey)
        c.setFont("Helvetica", 7.5)
        c.drawString(left, y, inv.terms[:110])
        y -= 26

    c.setFillColor(ink)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(right, y, f"For {client.name}"[:44])
    c.setStrokeColor(ink)
    c.line(right - 150, y - 34, right, y - 34)
    c.setFillColor(grey)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(right, y - 44, "Authorised signatory")

    c.save()
    return out


def as_whatsapp(inv: Invoice, client) -> str:
    """The same bill, short enough to send. Not a substitute for the document."""
    lines = "\n".join(f"{ln.item} — {ln.qty:g} × {ln.rate:,.0f} = {ln.total:,.0f}"
                      for ln in inv.lines[:8])
    more = (f"\n…and {len(inv.lines) - 8} more line(s)" if len(inv.lines) > 8 else "")
    tax = f"\nGST: ₹{inv.tax:,.0f}" if inv.taxed else ""
    due = ("\nStatus: PAID" if inv.paid else
           f"\nDue: {_pretty(inv.due_date)}" if inv.due_date else "\nStatus: DUE")
    return (f"*{client.name}*\n{inv.number} · {_pretty(inv.date)}\n\n"
            f"{inv.party}\n\n{lines}{more}\n{tax}\n"
            f"*Total: ₹{inv.rounded:,.0f}*{due}")
