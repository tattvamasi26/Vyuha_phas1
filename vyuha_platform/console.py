"""The console — six features on one page.

Stock, Ask, Follow-ups, Money, Deck and People are one screen, not six tabs,
because they are one job. The owner who notices he is about to run out of urea
wants to check what that supplier already costs him and whether the customer who
buys it has paid — and making him navigate between those three answers is how a
tool stops being opened.

So the whole page renders in one request and switching panels is a class
toggle, not a round trip. Everything is already on screen; the panel buttons
only decide what is visible. That is why the nav can carry live counts — "3
overdue" on the Follow-ups button — which is the entire reason a person clicks
into a panel they were not already thinking about.

Forms still POST and redirect, because they change data and a reload is the
honest way to show that. Every one of them carries ``?panel=`` so the page comes
back where it was left; landing back on Stock after recording an expense is the
kind of small betrayal that makes software feel hostile.

Rendering is hand-rolled HTML strings, matching ``ui.py`` — same reasons, same
CSS vocabulary. ``ui.CSS`` is not touched; the handful of console-only rules
live in ``EXTRA`` below so this file owns its own look and the other lane can
edit ``ui.py`` without ever meeting a merge conflict here.
"""

from __future__ import annotations

from datetime import date

from vyuha import fmt

from . import agent, books, decks, finance, followup, money, people, ui

E = ui.E


def rs(v) -> str:
    return fmt.rupees(v or 0, symbol="₹")


def short(v) -> str:
    return fmt.rupees_short(v or 0, symbol="₹")


PANELS = [
    ("stock", "Stock", "▦"),
    ("ask", "Ask", "✦"),
    ("followups", "Follow-ups", "↩"),
    ("money", "Money", "₹"),
    ("deck", "Deck", "◫"),
    ("people", "People", "⌂"),
]

EXTRA = """
.cnav{display:flex;gap:8px;flex-wrap:wrap;margin:26px 0 22px;position:sticky;top:0;
  z-index:20;padding:12px 0;background:linear-gradient(180deg,var(--bg) 70%,transparent)}
.cnav button{display:inline-flex;align-items:center;gap:9px;padding:10px 15px;border-radius:9px;
  border:1px solid var(--line-2);background:var(--card);color:var(--ink-2);cursor:pointer;
  font:inherit;font-size:13px;font-weight:600;letter-spacing:0;transition:.16s}
.cnav button:hover{border-color:var(--ink-3);color:var(--ink)}
.cnav button[aria-selected=true]{background:var(--accent);color:#04120F;
  border-color:var(--accent);font-weight:700}
.cnav .n{font-size:11px;font-weight:800;padding:2px 7px;border-radius:999px;
  background:rgba(0,0,0,.22);min-width:20px;text-align:center}
.cnav button[aria-selected=false] .n{background:var(--card-2);color:var(--ink-3)}
.cnav .n.hot{background:var(--crit);color:#fff}
.panel{display:none}
.panel.on{display:block;animation:fade .28s ease}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.bars{display:flex;align-items:flex-end;gap:11px;height:132px;margin:20px 0 6px}
.bars .b{flex:1;display:flex;flex-direction:column;justify-content:flex-end;gap:3px;height:100%}
.bars .bar{border-radius:5px 5px 0 0;min-height:2px}
.bars .bar.in{background:var(--accent)}
.bars .bar.out{background:rgba(240,90,98,.6)}
.bars .lb{font-size:10px;font-weight:700;color:var(--ink-3);text-align:center;
  white-space:nowrap;margin-top:6px}
.legend{display:flex;gap:16px;font-size:11px;font-weight:500;color:var(--ink-3);font-family:var(--num)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}
.meter{height:7px;border-radius:99px;background:var(--card-2);overflow:hidden;margin-top:9px}
.meter i{display:block;height:100%;border-radius:99px;background:var(--accent)}
.fu{display:flex;gap:15px;padding:17px 0;border-top:1px solid var(--line)}
.fu:first-child{border-top:0}
.fu .who{font-size:14.5px;font-weight:600}
.fu .body{flex:1;min-width:0}
.fu .acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;align-items:center}
.qchip{display:inline-block;padding:7px 12px;border-radius:7px;border:1px solid var(--line-2);
  background:var(--card-2);color:var(--ink-2);font-size:12.5px;font-weight:500;
  cursor:pointer;transition:.15s;margin:0 7px 7px 0}
.qchip:hover{color:var(--ink);border-color:var(--ink-3)}
.answer{border-left:3px solid var(--accent);padding:4px 0 4px 18px;margin-top:18px;
  font-size:15.5px;line-height:1.68;white-space:pre-wrap}
.inline-in{width:84px;padding:6px 9px;border-radius:6px;border:1px solid var(--line-2);
  background:var(--card-2);color:var(--ink);font-family:var(--num);font-size:12.5px;
  text-align:right;font-variant-numeric:tabular-nums}
.slide{border:1px solid var(--line);border-radius:9px;padding:15px 17px;margin-bottom:10px;
  background:var(--card-2)}
.slide h4{margin:0 0 9px;font-size:15px}
.slide ul{margin:0;padding-left:19px;color:var(--ink-2);font-size:13.5px;line-height:1.75}
.slide .st{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:10px}
.slide .st b{font-family:var(--num);font-size:20px;font-weight:600;font-variant-numeric:tabular-nums}
.slide .st span{display:block;font-size:9.5px;font-weight:800;letter-spacing:.18em;
  text-transform:uppercase;color:var(--ink-3)}

/* --- statements ------------------------------------------------- */
.stmt{display:flex;flex-direction:column}
.stmt .ln{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  padding:8px 0;border-bottom:1px solid var(--line)}
.stmt .ln:last-child{border-bottom:0}
.stmt .ln .l{font-size:13.5px;color:var(--ink-2)}
.stmt .ln .a{font-family:var(--num);font-size:13.5px;font-variant-numeric:tabular-nums;
  white-space:nowrap;color:var(--ink)}
.stmt .ln.sub .l{padding-left:16px;color:var(--ink-3);font-size:12.5px}
.stmt .ln.sub .a{color:var(--ink-2);font-size:12.5px}
.stmt .ln.tot{border-top:1.5px solid var(--line-2);border-bottom:0;margin-top:4px;padding-top:11px}
.stmt .ln.tot .l{font-weight:700;color:var(--ink);font-size:14px}
.stmt .ln.tot .a{font-weight:600;font-size:16px}
.stmt .ln.tot.pos .a{color:var(--ok)} .stmt .ln.tot.neg .a{color:var(--crit)}
.stmt .pc{font-family:var(--num);font-size:11px;color:var(--ink-3);margin-left:8px}

.ratios{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:10px}
.ratio{background:var(--card-2);border:1px solid var(--line);border-radius:var(--r-sm);
  padding:13px 14px;border-left:2px solid var(--ink-3)}
.ratio.good{border-left-color:var(--ok)} .ratio.bad{border-left-color:var(--warn)}
.ratio .n{font-family:var(--num);font-size:9.5px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--ink-3)}
.ratio .v{font-family:var(--num);font-size:22px;font-weight:600;margin-top:6px;
  font-variant-numeric:tabular-nums}
.ratio.bad .v{color:var(--warn)}
.ratio .u{font-size:12px;color:var(--ink-3);margin-left:3px}
.ratio .note{font-size:11.5px;color:var(--ink-3);line-height:1.45;margin-top:7px}

.age{display:flex;flex-direction:column;gap:9px}
.age .r{display:grid;grid-template-columns:88px 1fr 92px;gap:11px;align-items:center}
.age .lb{font-family:var(--num);font-size:11px;color:var(--ink-3);white-space:nowrap}
.age .track{height:8px;border-radius:99px;background:var(--card-3);overflow:hidden}
.age .track i{display:block;height:100%;border-radius:99px;background:var(--ink-3)}
.age .r.b0 .track i{background:var(--ok)}
.age .r.b1 .track i{background:var(--accent)}
.age .r.b2 .track i{background:var(--warn)}
.age .r.b3 .track i{background:#E07A3F}
.age .r.b4 .track i{background:var(--crit)}
.age .amt{font-family:var(--num);font-size:12.5px;text-align:right;
  font-variant-numeric:tabular-nums}

.trend{display:flex;align-items:flex-end;gap:6px;height:150px;margin:18px 0 4px}
.trend .c{flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;gap:2px}
.trend .stk{display:flex;flex-direction:column;justify-content:flex-end;height:100%;gap:2px}
.trend .rev{background:var(--accent);border-radius:3px 3px 0 0;min-height:2px}
.trend .prf{background:var(--ok);border-radius:3px 3px 0 0;min-height:1px}
.trend .prf.neg{background:var(--crit)}
.trend .lb{font-family:var(--num);font-size:9.5px;color:var(--ink-3);text-align:center;
  margin-top:6px;white-space:nowrap}
.periods{display:flex;gap:6px;flex-wrap:wrap}
.periods a{font-family:var(--num);font-size:11px;padding:5px 10px;border-radius:6px;
  border:1px solid var(--line-2);color:var(--ink-3);white-space:nowrap}
.periods a:hover{color:var(--ink);border-color:var(--ink-3)}
.periods a.on{background:var(--accent);color:#04120F;border-color:var(--accent);font-weight:600}
.assume{font-size:11.5px;color:var(--ink-3);line-height:1.6;margin-top:12px;
  padding-top:12px;border-top:1px dashed var(--line-2)}
.assume b{color:var(--ink-2);font-weight:600}
"""

JS = """
(function(){
  var buttons = document.querySelectorAll('.cnav button');
  function show(name){
    document.querySelectorAll('.panel').forEach(function(p){
      p.classList.toggle('on', p.dataset.panel === name);
    });
    buttons.forEach(function(b){
      b.setAttribute('aria-selected', String(b.dataset.go === name));
    });
    try{ history.replaceState(null,'', '?panel=' + name); }catch(e){}
  }
  buttons.forEach(function(b){
    b.addEventListener('click', function(){ show(b.dataset.go); });
  });
  document.querySelectorAll('.qchip').forEach(function(chip){
    chip.addEventListener('click', function(){
      var box = document.getElementById('q');
      if(!box) return;
      box.value = chip.textContent.trim();
      box.form.submit();
    });
  });
})();
"""


def _sev(severity: str) -> str:
    return {"critical": "crit", "warning": "warn", "info": "info"}.get(severity, "dim")


def _stat(label: str, value: str, sub: str = "", small: bool = False) -> str:
    cls = "v sm" if small else "v"
    return (f'<div class="card stat"><div class="k">{E(label)}</div>'
            f'<div class="{cls}">{E(value)}</div>'
            + (f'<div class="tiny" style="margin-top:7px">{E(sub)}</div>' if sub else "")
            + "</div>")


def _empty(big: str, detail: str) -> str:
    return (f'<div class="card empty"><div class="big">{E(big)}</div>'
            f'<div class="muted">{E(detail)}</div></div>')


def _head(title: str, right: str = "") -> str:
    return (f'<div class="section-h" style="margin-top:0"><h2>{E(title)}</h2>'
            f'<div class="rule"></div>{right}</div>')


# ------------------------------------------------------------------ 02 · stock

def _stock(c, book, org) -> str:
    summary = books.summary(book)
    low, gone = summary["low_stock"], summary["out_of_stock"]
    never = summary["never_sold"]
    locked = sum(i.value for i in never)

    tiles = "".join([
        _stat("Stock value", short(summary["stock_value"]),
              f"{summary['items']} item(s) carried"),
        _stat("Below reorder", str(len(low)),
              "Order these before they run out" if low else "Nothing to reorder"),
        _stat("Out of stock", str(len(gone)),
              "Losing sales right now" if gone else "Everything in stock"),
        _stat("Never sold", short(locked), f"{len(never)} item(s), cash tied up"),
    ])

    if not book.items:
        return (_head("Stock")
                + _empty("No items yet",
                         "Add what you sell and Vyuha starts watching the levels for you."))

    # --- what needs ordering, first, because it is the reason to open this page
    need = gone + [i for i in low if i.stock_qty > 0]
    if need:
        rows = "".join(
            f'<div class="fu"><div class="body">'
            f'<div class="who">{E(i.name)} '
            f'<span class="pill {"crit" if i.stock_qty <= 0 else "warn"}">'
            f'{"out of stock" if i.stock_qty <= 0 else "below reorder"}</span></div>'
            f'<div class="muted" style="margin-top:5px">'
            f'{i.stock_qty:g} {E(i.unit)} left · reorder at {i.reorder_level:g} · '
            f'{E(i.category)}</div></div>'
            f'<form method="post" action="/c/{c.slug}/stock/receive" class="row" '
            f'style="gap:8px;align-self:center">'
            f'<input type="hidden" name="sku" value="{E(i.sku)}">'
            f'<input class="inline-in" name="qty" placeholder="qty" inputmode="decimal" '
            f'aria-label="Quantity received for {E(i.name)}">'
            f'<button class="btn sm primary" type="submit">Received</button></form></div>'
            for i in need[:12])
        order_card = (f'<div class="card" style="margin-bottom:16px">'
                      f'<div class="row" style="justify-content:space-between">'
                      f'<div style="font-size:16px;font-weight:800">Needs ordering</div>'
                      f'<span class="pill crit">{len(need)}</span></div>'
                      f'<div class="tiny" style="margin:8px 0 4px">'
                      f'Type what arrived and stock goes straight back up.</div>'
                      f'{rows}</div>')
    else:
        order_card = ('<div class="card" style="margin-bottom:16px">'
                      '<div style="font-size:16px;font-weight:800">Nothing needs ordering</div>'
                      '<div class="muted" style="margin-top:7px">Every item is above its '
                      'reorder level. Set levels below on anything showing 0.</div></div>')

    branch_opts = "".join(f'<option value="{E(b.id)}">{E(b.name)}</option>'
                          for b in org.branches if b.active)

    # --- the full table, with reorder levels editable in place and saved as one
    body = "".join(
        f'<tr><td><b>{E(i.name)}</b><div class="tiny" style="margin-top:3px">'
        f'{E(i.sku)} · {E(i.category)}</div></td>'
        f'<td class="num">{i.stock_qty:g} <span class="tiny">{E(i.unit)}</span></td>'
        f'<td class="num"><input class="inline-in" name="lvl_{E(i.sku)}" '
        f'value="{i.reorder_level:g}" inputmode="decimal" '
        f'aria-label="Reorder level for {E(i.name)}"></td>'
        f'<td class="num">{rs(i.rate)}</td>'
        f'<td class="num">{short(i.value)}</td>'
        f'<td>{"<span class=\'pill crit\'>out</span>" if i.stock_qty <= 0 else "<span class=\'pill warn\'>low</span>" if i.low else "<span class=\'pill ok\'>ok</span>"}</td>'
        f'</tr>'
        for i in sorted(book.items, key=lambda x: (not x.low, x.name)))

    table = f"""<form method="post" action="/c/{c.slug}/stock/reorder">
<div class="card" style="padding:0;overflow:hidden">
  <div class="row" style="justify-content:space-between;padding:18px 20px">
    <div><div style="font-size:16px;font-weight:800">Every item</div>
      <div class="tiny" style="margin-top:5px">Edit reorder levels straight in the
        table — one save for the lot.</div></div>
    <button class="btn sm primary" type="submit">Save levels</button></div>
  <div class="scroll-x"><table class="mtable">
    <tr><th>Item</th><th>In stock</th><th>Reorder at</th><th>Rate</th>
        <th>Value</th><th>State</th></tr>
    {body}</table></div></div></form>"""

    forms = f"""<div class="two" style="margin-top:16px">
  <div class="card">
    <div style="font-size:16px;font-weight:800">Stock came in</div>
    <div class="tiny" style="margin:7px 0 15px">A delivery, or a customer return.</div>
    <form method="post" action="/c/{c.slug}/stock/receive">
      <div class="field"><select name="sku" required aria-label="Item">
        <option value="">Which item…</option>
        {"".join(f'<option value="{E(i.sku)}">{E(i.name)}</option>' for i in book.items)}
      </select></div>
      <div class="two">
        <div class="field"><input name="qty" placeholder="How many" inputmode="decimal" required></div>
        <div class="field"><input name="cost" placeholder="Cost each (optional)" inputmode="decimal"></div>
      </div>
      <button class="btn primary" type="submit">Add to stock</button>
    </form></div>
  <div class="card">
    <div style="font-size:16px;font-weight:800">Stock count</div>
    <div class="tiny" style="margin:7px 0 15px">Counted the shelf? Set it to what is
      actually there — this replaces the number, it does not add to it.</div>
    <form method="post" action="/c/{c.slug}/stock/count">
      <div class="field"><select name="sku" required aria-label="Item">
        <option value="">Which item…</option>
        {"".join(f'<option value="{E(i.sku)}">{E(i.name)}</option>' for i in book.items)}
      </select></div>
      <div class="field"><input name="counted" placeholder="Counted quantity"
        inputmode="decimal" required></div>
      {f'<div class="field"><select name="branch" aria-label="Branch"><option value="">Branch (optional)</option>{branch_opts}</select></div>' if branch_opts else ''}
      <button class="btn" type="submit">Set count</button>
    </form></div></div>"""

    dead = ""
    if never:
        rows = "".join(
            f'<div class="fu"><div class="body"><div class="who">{E(i.name)}</div>'
            f'<div class="muted" style="margin-top:5px">{i.stock_qty:g} {E(i.unit)} sitting, '
            f'{rs(i.value)} tied up · added {E(i.added_at)}</div></div></div>'
            for i in never[:8])
        dead = (f'<div class="card" style="margin-top:16px">'
                f'<div class="row" style="justify-content:space-between">'
                f'<div style="font-size:16px;font-weight:800">Never sold</div>'
                f'<span class="pill warn">{short(locked)} tied up</span></div>'
                f'<div class="tiny" style="margin:8px 0 4px">These have not sold once. '
                f'Discount them, return them, or stop reordering them.</div>{rows}</div>')

    return (_head("Stock") + f'<div class="grid g4">{tiles}</div>'
            + '<div style="height:16px"></div>' + order_card + table + forms + dead)


# -------------------------------------------------------------------- 03 · ask

def _ask(c, reply, question: str, settings) -> str:
    chips = "".join(f'<span class="qchip">{E(q)}</span>' for q in agent.SUGGESTED)

    if reply is None:
        out = ('<div class="muted" style="margin-top:20px">Ask anything about this '
               'business — money, stock, customers, branches. Every answer comes from '
               'the numbers on this page, never from a guess.</div>')
    elif reply.ok:
        out = (f'<div class="answer">{E(reply.text)}</div>'
               f'<div class="tiny" style="margin-top:14px">{E(reply.label)}</div>')
    else:
        out = (f'<div class="card" style="margin-top:18px;border-color:rgba(251,191,36,.3)">'
               f'<div style="font-size:15px;font-weight:800">Could not answer that</div>'
               f'<div class="muted" style="margin-top:8px">{E(reply.error)}</div></div>')

    state = ("Claude is connected." if settings.vision_live
             else "No Claude key yet, so Vyuha answers from your numbers directly. "
                  "That covers the common questions; connect a key in Settings for the rest.")

    return (_head("Ask")
            + f"""<div class="card">
  <form method="post" action="/c/{c.slug}/ask">
    <div class="field">
      <input id="q" name="question" value="{E(question)}" autocomplete="off"
             placeholder="Who owes me the most, and for how long?"
             style="font-size:16px;padding:15px 17px" aria-label="Your question">
    </div>
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
      <div class="tiny">{E(state)}</div>
      <button class="btn primary" type="submit">Ask</button>
    </div>
  </form>
  {out}
</div>
<div style="margin-top:20px">
  <div class="tiny" style="margin-bottom:11px">TRY ONE OF THESE</div>{chips}</div>""")


# -------------------------------------------------------------- 07 · follow-ups

def _followups(c, queue: list, settings) -> str:
    if not queue:
        return (_head("Follow-ups")
                + _empty("Nobody to chase",
                         "No overdue payments, no quotations waiting, and every regular "
                         "customer has bought recently."))

    money_out = sum(f.amount for f in queue if f.kind == "payment")
    tiles = "".join([
        _stat("To chase", str(len(queue)), "people worth a message today"),
        _stat("Overdue money", short(money_out),
              f"{sum(1 for f in queue if f.kind == 'payment')} unpaid bill(s)"),
        _stat("Gone quiet", str(sum(1 for f in queue if f.kind == "dormant")),
              "regulars who stopped coming"),
        _stat("No number", str(sum(1 for f in queue if not f.has_phone)),
              "cannot be messaged yet"),
    ])

    kind_label = {"payment": "unpaid", "dormant": "gone quiet", "quote": "quotation"}
    rows = ""
    for f in queue[:40]:
        text = followup.draft(f, c.name)
        if f.has_phone:
            from . import channels
            link = channels.whatsapp_link(f.party_phone, text)
            send = (f'<a class="btn sm wa" href="{link}" target="_blank" '
                    f'rel="noopener">Send on WhatsApp</a>')
        else:
            send = '<span class="pill dim">No number on file</span>'

        rows += f"""<div class="fu">
  <div class="body">
    <div class="row" style="gap:10px;flex-wrap:wrap">
      <span class="who">{E(f.party)}</span>
      <span class="pill {_sev(f.severity)}">{E(kind_label.get(f.kind, f.kind))}</span>
      {f'<span class="pill dim">{f.days} days</span>' if f.days else ''}
    </div>
    <div class="muted" style="margin-top:6px">{E(f.reason)}</div>
    <details style="margin-top:11px">
      <summary class="tiny" style="cursor:pointer">See the message</summary>
      <pre class="msg" style="margin-top:10px;white-space:pre-wrap">{E(text)}</pre>
    </details>
    <div class="acts">
      {send}
      <form method="post" action="/c/{c.slug}/followup"><input type="hidden" name="key"
        value="{E(f.key)}"><input type="hidden" name="status" value="done">
        <button class="btn sm ghost" type="submit">Done</button></form>
      <form method="post" action="/c/{c.slug}/followup"><input type="hidden" name="key"
        value="{E(f.key)}"><input type="hidden" name="status" value="snoozed">
        <input type="hidden" name="days" value="7">
        <button class="btn sm ghost" type="submit">Later</button></form>
    </div>
  </div></div>"""

    note = ("" if settings.whatsapp_live else
            '<div class="tiny" style="margin-top:14px">Opens WhatsApp with the message '
            'typed out and you tap send. <a href="/settings">Connect a provider</a> to '
            'send without leaving this page.</div>')

    return (_head("Follow-ups") + f'<div class="grid g4">{tiles}</div>'
            + f'<div class="card" style="margin-top:16px">{rows}{note}</div>')


# ------------------------------------------------------------------ 08 · money

def _money(c, book, ledger, org, period: str = "all") -> str:
    """The statements a CA would prepare, from the same books everything else reads.

    Ordered the way an owner reads them, not the way an accountant files them:
    the position first (am I alright), then what happened (P&L), then what is
    owed both ways, then the diagnostics. The period selector drives all of it.
    """
    st = finance.statements(book, ledger, period)
    pl, cf, bs = st["pl"], st["cash"], st["balance"]
    ar, ap = st["receivables"], st["payables"]
    label = st["period"]["label"]

    # --- period selector
    chips = "".join(
        f'<a href="/c/{c.slug}/console?panel=money&period={E(key)}"'
        f'{" class=\'on\'" if key == period else ""}>{E(text)}</a>'
        for key, text, _ in finance.periods(book, ledger)[:10])

    # --- the four headline numbers
    tiles = "".join([
        _stat("Net profit", short(pl["net_profit"]),
              f"{pl['net_margin_pct']:.1f}% of revenue · {label}"),
        _stat("Cash movement", short(cf["net_movement"]),
              f"{short(cf['received'])} in, {short(cf['paid_out'])} out"),
        _stat("Owed to you", short(ar["total"]),
              f"{short(ar['overdue'])} of it overdue"),
        _stat("You owe", short(ap["total"]),
              f"{short(ap['overdue'])} of it overdue"),
    ])

    def ln(lab, amount, cls="", pct=None, sub=False):
        p = f'<span class="pc">{pct}</span>' if pct else ""
        return (f'<div class="ln {cls}{" sub" if sub else ""}">'
                f'<span class="l">{E(lab)}</span>'
                f'<span class="a">{rs(amount)}{p}</span></div>')

    # --- profit & loss
    opex_lines = "".join(ln(head, amt, sub=True) for head, amt in pl["opex_rows"][:8])
    coverage = ""
    if pl["cost_coverage_pct"] < 100:
        coverage = (f'<div class="assume">Gross margin covers the '
                    f'{pl["cost_coverage_pct"]:.0f}% of sale lines where a cost price is '
                    f'known. Add cost prices on the Stock panel to make it exact.</div>')

    pnl_card = f"""<div class="card">
  <div class="row" style="justify-content:space-between;margin-bottom:14px">
    <div style="font-size:16px;font-weight:700">Profit &amp; loss</div>
    <span class="pill dim">accrual · billed</span></div>
  <div class="stmt">
    {ln("Revenue", pl["revenue"])}
    {ln("Cost of goods sold", -pl["cogs"])}
    {ln("Gross profit", pl["gross_profit"], cls="tot " + ("pos" if pl["gross_profit"] >= 0 else "neg"), pct=f"{pl['gross_margin_pct']:.1f}%")}
    {ln("Operating expenses", -pl["opex"])}
    {opex_lines}
    {ln("Net profit", pl["net_profit"], cls="tot " + ("pos" if pl["net_profit"] >= 0 else "neg"), pct=f"{pl['net_margin_pct']:.1f}%")}
  </div>{coverage}</div>"""

    # --- cash flow + balance sheet
    cash_card = f"""<div class="card">
  <div class="row" style="justify-content:space-between;margin-bottom:14px">
    <div style="font-size:16px;font-weight:700">Cash flow</div>
    <span class="pill dim">cash · actually moved</span></div>
  <div class="stmt">
    {ln("Received from customers", cf["received"])}
    {ln("Paid out", -cf["paid_out"])}
    {ln("Net movement", cf["net_movement"], cls="tot " + ("pos" if cf["net_movement"] >= 0 else "neg"))}
  </div>
  <div class="assume"><b>Profit is not cash.</b> {rs(cf["billed_not_collected"])} was
    billed and not yet collected; {rs(cf["incurred_not_paid"])} was incurred and not yet
    paid. That gap is the difference between the two statements.</div></div>"""

    assumptions = "".join(f"<div>· {E(a)}</div>" for a in bs["assumptions"])
    bs_card = f"""<div class="card">
  <div class="row" style="justify-content:space-between;margin-bottom:14px">
    <div style="font-size:16px;font-weight:700">What you own and owe</div>
    <span class="pill dim">as of {E(bs["as_of"])}</span></div>
  <div class="stmt">
    {ln("Cash from trading", bs["cash_from_trading"])}
    {ln("Owed by customers", bs["receivables"])}
    {ln("Stock on hand", bs["stock_value"])}
    {ln("Total short-term assets", bs["current_assets"], cls="tot")}
    {ln("Owed to suppliers", -bs["payables"])}
    {ln("Working capital", bs["working_capital"], cls="tot " + ("pos" if bs["working_capital"] >= 0 else "neg"))}
  </div>
  <div class="assume"><b>Partial, on purpose:</b>{assumptions}</div></div>"""

    # --- ratios
    ratio_cards = "".join(
        f'<div class="ratio {"good" if r["good"] else "bad"}">'
        f'<div class="n">{E(r["name"])}</div>'
        f'<div class="v">{r["value"]:,.1f}<span class="u">{E(r["unit"])}</span></div>'
        f'<div class="note">{E(r["note"])}</div></div>' for r in st["ratios"])
    flagged = [r for r in st["ratios"] if not r["good"]]
    ratio_note = ("Everything is inside a healthy range."
                  if not flagged else
                  f"{len(flagged)} figure(s) worth a look: "
                  + ", ".join(r["name"] for r in flagged) + ".")
    ratios_card = f"""<div class="card" style="margin-top:16px">
  <div class="row" style="justify-content:space-between;margin-bottom:6px">
    <div style="font-size:16px;font-weight:700">The numbers a lender asks for</div></div>
  <div class="tiny" style="margin-bottom:16px">{E(ratio_note)}</div>
  <div class="ratios">{ratio_cards}</div></div>"""

    # --- ageing, both directions
    def ageing(title, data, kind):
        peak = max((v for _, v, _ in data["buckets"]), default=0) or 1.0
        rows = "".join(
            f'<div class="r b{i}"><span class="lb">{E(lab)}</span>'
            f'<span class="track"><i style="width:{val / peak * 100:.1f}%"></i></span>'
            f'<span class="amt">{short(val)}</span></div>'
            for i, (lab, val, _) in enumerate(data["buckets"]))
        top = "".join(
            f'<div class="row" style="justify-content:space-between;padding:7px 0;'
            f'border-top:1px solid var(--line)">'
            f'<span style="font-size:13px">{E(r["party"])}</span>'
            f'<span class="mono" style="font-size:12.5px">{rs(r["total"])}'
            f'<span class="tiny" style="margin-left:8px">{r["oldest"]}d</span></span></div>'
            for r in data["parties"][:6])
        return f"""<div class="card">
  <div class="row" style="justify-content:space-between;margin-bottom:14px">
    <div style="font-size:16px;font-weight:700">{E(title)}</div>
    <span class="pill {"crit" if data["overdue"] else "ok"}">{short(data["overdue"])} overdue</span></div>
  <div class="age">{rows}</div>
  {f'<div style="margin-top:14px"><div class="tiny" style="margin-bottom:2px">BY {kind}</div>{top}</div>' if top else ''}</div>"""

    ageing_row = ('<div class="two" style="margin-top:16px">'
                  + ageing("Owed to you, by age", ar, "CUSTOMER")
                  + ageing("You owe, by age", ap, "SUPPLIER") + "</div>")

    # --- monthly trend
    months = st["monthly"]
    trend_card = ""
    if months:
        peak = max(max(m["revenue"], abs(m["profit"])) for m in months) or 1.0
        bars = "".join(
            f'<div class="c"><div class="stk">'
            f'<div class="prf{" neg" if m["profit"] < 0 else ""}" '
            f'style="height:{abs(m["profit"]) / peak * 100:.1f}%" '
            f'title="Profit {rs(m["profit"])}"></div>'
            f'<div class="rev" style="height:{m["revenue"] / peak * 100:.1f}%" '
            f'title="Revenue {rs(m["revenue"])}"></div></div>'
            f'<div class="lb">{E(m["label"])}</div></div>' for m in months)
        last = months[-1]
        trend_card = f"""<div class="card" style="margin-top:16px">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div style="font-size:16px;font-weight:700">Month by month</div>
    <div class="legend"><span><i style="background:var(--accent)"></i>Revenue</span>
      <span><i style="background:var(--ok)"></i>Profit</span></div></div>
  <div class="trend">{bars}</div>
  <div class="tiny">Latest month {E(last["label"])}: {rs(last["revenue"])} revenue,
    {rs(last["profit"])} profit{f", {last['change_pct']:+.0f}% on the month before" if last["change_pct"] else ""}.</div></div>"""

    # --- concentration
    co = st["concentration"]
    risk_pill = {"high": ("crit", "concentrated"), "watch": ("warn", "watch this"),
                 "spread": ("ok", "well spread")}[co["risk"]]
    cust_rows = "".join(
        f'<div style="margin-bottom:11px"><div class="row" style="justify-content:space-between">'
        f'<span style="font-size:13px">{E(r["party"])}</span>'
        f'<span class="mono" style="font-size:12.5px">{short(r["amount"])} '
        f'<span class="tiny">{r["share"] * 100:.0f}%</span></span></div>'
        f'<div class="meter"><i style="width:{r["share"] * 100:.1f}%"></i></div></div>'
        for r in co["customers"][:6])
    supp_rows = "".join(
        f'<div style="margin-bottom:11px"><div class="row" style="justify-content:space-between">'
        f'<span style="font-size:13px">{E(r["party"])}</span>'
        f'<span class="mono" style="font-size:12.5px">{short(r["amount"])} '
        f'<span class="tiny">{r["share"] * 100:.0f}%</span></span></div>'
        f'<div class="meter"><i style="width:{r["share"] * 100:.1f}%"></i></div></div>'
        for r in co["suppliers"][:6])
    conc_card = f"""<div class="two" style="margin-top:16px">
  <div class="card">
    <div class="row" style="justify-content:space-between;margin-bottom:6px">
      <div style="font-size:16px;font-weight:700">Where revenue comes from</div>
      <span class="pill {risk_pill[0]}">{risk_pill[1]}</span></div>
    <div class="tiny" style="margin-bottom:15px">Your biggest customer is
      {co["top_customer_share"] * 100:.0f}% of revenue and the top three are
      {co["top3_share"] * 100:.0f}%, across {co["customer_count"]} customer(s).
      {"Losing one would hurt badly." if co["risk"] == "high" else "Reasonably spread."}</div>
    {cust_rows}</div>
  <div class="card">
    <div style="font-size:16px;font-weight:700;margin-bottom:6px">Where the money goes</div>
    <div class="tiny" style="margin-bottom:15px">{co["supplier_count"]} supplier(s) and
      cost heads, biggest first.</div>
    {supp_rows}</div></div>"""

    # --- expense heads and break-even
    be = st["break_even"]
    exp_rows = "".join(
        f'<tr><td><b>{E(e["head"])}</b></td>'
        f'<td class="num">{rs(e["amount"])}</td>'
        f'<td class="num">{e["pct_of_revenue"]:.1f}%</td>'
        f'<td class="num">{e["count"]}</td>'
        f'<td class="num">{rs(e["unpaid"]) if e["unpaid"] else "—"}</td></tr>'
        for e in st["expenses"])
    exp_card = f"""<div class="card" style="margin-top:16px;padding:0;overflow:hidden">
  <div style="padding:18px 20px 4px">
    <div style="font-size:16px;font-weight:700">Every cost head</div>
    <div class="tiny" style="margin-top:6px">Share of revenue is the column that
      matters — rent means nothing until you know it is 3% of turnover or 30%.</div></div>
  <div class="scroll-x"><table class="mtable">
    <tr><th>Head</th><th class="num">Amount</th><th class="num">% of revenue</th>
        <th class="num">Entries</th><th class="num">Unpaid</th></tr>
    {exp_rows or '<tr><td colspan="5" class="tiny">No costs recorded yet.</td></tr>'}
  </table></div></div>"""

    be_card = f"""<div class="card" style="margin-top:16px">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:14px">
    <div style="max-width:52ch">
      <div style="font-size:16px;font-weight:700">Break-even</div>
      <div class="tiny" style="margin-top:7px">At a {be["contribution_margin_pct"]:.1f}%
        gross margin, you need {rs(be["break_even_monthly"])} of sales a month to
        cover {rs(be["fixed_monthly"])} of running costs. You are averaging
        {rs(be["actual_monthly"])}.</div></div>
    <div style="text-align:right">
      <div class="pill {"ok" if be["clears"] else "crit"}">
        {"clears by " + short(abs(be["headroom"])) if be["clears"] else "short by " + short(abs(be["headroom"]))}</div>
    </div></div>
  <div class="assume">Every head except purchases is treated as fixed. Some costs do
    move with sales, so read this as the cautious version.</div></div>"""

    # --- entry form
    branch_opts = "".join(f'<option value="{E(b.id)}">{E(b.name)}</option>'
                          for b in org.branches if b.active)
    cat_opts = "".join(f'<option>{E(x)}</option>' for x in money.CATEGORIES)
    form = f"""<div class="card" style="margin-top:16px">
  <div style="font-size:16px;font-weight:700">Record something paid</div>
  <div class="tiny" style="margin:7px 0 15px">Purchases, salary, rent, transport —
    anything that left the business, or that you owe.</div>
  <form method="post" action="/c/{c.slug}/expense">
    <div class="two">
      <div class="field"><select name="category" aria-label="Category">{cat_opts}</select></div>
      <div class="field"><input name="party" placeholder="Paid to (optional)"></div></div>
    <div class="two">
      <div class="field"><input name="amount" placeholder="Amount" inputmode="decimal" required></div>
      <div class="field"><input name="when" type="date" value="{date.today().isoformat()}"
        aria-label="Date"></div></div>
    <div class="two">
      <div class="field"><input name="due_date" type="date" aria-label="Due date">
        <div class="tiny" style="margin-top:5px">Due date — only if it is not paid yet</div></div>
      {f'<div class="field"><select name="branch" aria-label="Branch"><option value="">All branches</option>{branch_opts}</select></div>' if branch_opts else '<div></div>'}
    </div>
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
      <label class="chk"><input type="checkbox" name="unpaid" value="1">
        Not paid yet — this is a bill I owe</label>
      <button class="btn primary" type="submit">Record</button></div>
  </form></div>"""

    recent = ""
    if ledger.expenses:
        rows = "".join(
            f'<tr><td>{E(e.date)}</td><td><b>{E(e.category)}</b>'
            + (f'<div class="tiny" style="margin-top:3px">{E(e.party)}</div>' if e.party else "")
            + f'</td><td class="num">{rs(e.amount)}</td>'
            f'<td>{"<span class=\'pill ok\'>paid</span>" if e.paid else "<span class=\'pill crit\'>overdue</span>" if e.overdue else "<span class=\'pill warn\'>owed</span>"}</td>'
            f'<td style="text-align:right">'
            + ("" if e.paid else
               f'<form method="post" action="/c/{c.slug}/expense/{e.id}/paid" '
               f'style="display:inline"><button class="btn sm ghost" type="submit">'
               f'Mark paid</button></form> ')
            + f'<form method="post" action="/c/{c.slug}/expense/{e.id}/delete" '
              f'style="display:inline"><button class="btn sm danger" type="submit">×</button>'
              f'</form></td></tr>'
            for e in ledger.expenses[:20])
        recent = (f'<div class="card" style="margin-top:16px;padding:0;overflow:hidden">'
                  f'<div style="font-size:16px;font-weight:700;padding:18px 20px">'
                  f'Recent payments</div><div class="scroll-x"><table class="mtable">'
                  f'<tr><th>Date</th><th>What</th><th class="num">Amount</th>'
                  f'<th>State</th><th></th></tr>{rows}</table></div></div>')

    head = _head("Money", f'<div class="periods">{chips}</div>')
    return (head + f'<div class="grid g4">{tiles}</div>'
            + f'<div class="two" style="margin-top:16px">{pnl_card}'
            + f'<div style="display:flex;flex-direction:column;gap:16px">{cash_card}{bs_card}</div></div>'
            + ratios_card + ageing_row + trend_card + conc_card + exp_card + be_card
            + form + recent)


# ------------------------------------------------------------------- 09 · deck

def _deck(c, outline, brief: str, kind: str) -> str:
    picker = "".join(
        f'<label class="seg" style="margin:0 8px 8px 0">'
        f'<input type="radio" name="kind" value="{E(k)}"{" checked" if k == kind else ""}>'
        f'<span>{E(label)}</span></label>'
        for k, (label, _) in decks.KINDS.items())

    hint = decks.KINDS.get(kind, ("", ""))[1]

    preview = ""
    if outline is not None:
        slides = ""
        for s in outline.slides:
            stats = ""
            if s.stats:
                stats = ('<div class="st">' + "".join(
                    f'<div><span>{E(x["label"])}</span><b>{E(x["value"])}</b></div>'
                    for x in s.stats) + "</div>")
            bullets = ("<ul>" + "".join(f"<li>{E(b)}</li>" for b in s.bullets) + "</ul>"
                       if s.bullets else "")
            slides += f'<div class="slide"><h4>{E(s.heading)}</h4>{stats}{bullets}</div>'

        note = (f'<div class="tiny" style="margin-top:12px">{E(outline.note)}</div>'
                if outline.note else "")
        preview = f"""<div class="card" style="margin-top:16px">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:14px">
    <div><div style="font-size:18px;font-weight:800">{E(outline.title)}</div>
      <div class="muted" style="margin-top:5px">{E(outline.subtitle)}</div>
      <div class="tiny" style="margin-top:8px">{E(outline.label)} ·
        {len(outline.slides)} slide(s)</div></div>
    <div class="row" style="gap:9px">
      <a class="btn primary" href="/c/{c.slug}/deck/pptx">Download PPTX</a>
      <a class="btn ghost" href="/c/{c.slug}/deck/pdf">PDF</a></div></div>
  {note}
  <div style="margin-top:20px">{slides}</div></div>"""

    return (_head("Deck")
            + f"""<div class="card">
  <div style="font-size:16px;font-weight:800">What is this deck for?</div>
  <div class="tiny" style="margin:7px 0 15px">The audience changes the argument far
    more than the numbers do.</div>
  <form method="post" action="/c/{c.slug}/deck">
    <div style="margin-bottom:6px">{picker}</div>
    <div class="tiny" style="margin-bottom:16px">{E(hint)}</div>
    <div class="field">
      <textarea name="brief" rows="3" placeholder="Say what you want it to argue — &quot;show the bank we collect on time&quot;, &quot;case study for a new distributor&quot;"
        aria-label="Your brief">{E(brief)}</textarea>
    </div>
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
      <div class="tiny">Every figure comes from this workspace. Nothing is invented.</div>
      <button class="btn primary" type="submit">Build the deck</button></div>
  </form></div>{preview}""")


# ----------------------------------------------------------------- 10 · people

def _people(c, org, book, ledger) -> str:
    rows = people.performance(org, book, ledger)

    if not org.branches:
        intro = ('<div class="card"><div style="font-size:16px;font-weight:800">'
                 'One location</div><div class="muted" style="margin-top:9px">'
                 'Add a branch below and every sale, expense and stock count can be '
                 'tagged to a place — then these numbers split and you can compare them. '
                 'Nothing changes for a business that only has one.</div></div>')
        compare = ""
    else:
        intro = ""
        top = max((r["revenue"] for r in rows), default=0) or 1.0
        cards = "".join(
            f"""<div class="card">
  <div class="row" style="justify-content:space-between">
    <div><div style="font-size:17px;font-weight:800">{E(r["name"])}</div>
      {f'<div class="tiny" style="margin-top:4px">{E(r["place"])}</div>' if r["place"] else ''}</div>
    <span class="pill {"ok" if r["share"] >= 0.5 else "dim"}">{int(r["share"] * 100)}%</span>
  </div>
  <div class="meter"><i style="width:{r["revenue"] / top * 100:.1f}%"></i></div>
  <div class="grid g4" style="margin-top:16px;gap:10px">
    <div><div class="tiny">REVENUE</div><div style="font-weight:800;margin-top:3px">
      {short(r["revenue"])}</div></div>
    <div><div class="tiny">SPENT</div><div style="font-weight:800;margin-top:3px">
      {short(r["spend"])}</div></div>
    <div><div class="tiny">BILLS</div><div style="font-weight:800;margin-top:3px">
      {r["bills"]}</div></div>
    <div><div class="tiny">CUSTOMERS</div><div style="font-weight:800;margin-top:3px">
      {r["customers"]}</div></div></div>
  <div class="tiny" style="margin-top:14px">{r["staff"]} person(s) ·
    {short(r["owed"])} still owed to you</div></div>""" for r in rows)
        compare = f'<div class="grid g3">{cards}</div><div style="height:16px"></div>'

    branch_rows = "".join(
        f'<div class="fu"><div class="body">'
        f'<div class="who">{E(b.name)}</div>'
        f'<div class="muted" style="margin-top:5px">'
        f'{E(b.place or "No place set")}'
        f'{" · " + E(b.manager) if b.manager else ""}'
        f'{" · +" + E(b.phone) if b.phone else ""}</div></div>'
        f'<form method="post" action="/c/{c.slug}/branch/{E(b.id)}/delete" '
        f'style="align-self:center"><button class="btn sm danger" type="submit">'
        f'Close</button></form></div>'
        for b in org.branches if b.active)

    branch_opts = "".join(f'<option value="{E(b.id)}">{E(b.name)}</option>'
                          for b in org.branches if b.active)
    role_opts = "".join(f'<option>{E(r)}</option>' for r in people.ROLES)

    staff_rows = "".join(
        f'<div class="fu"><div class="body">'
        f'<div class="row" style="gap:9px;flex-wrap:wrap">'
        f'<span class="who">{E(s.name)}</span>'
        f'<span class="pill dim">{E(s.role)}</span></div>'
        f'<div class="muted" style="margin-top:5px">'
        f'{E(org.name_of(s.branch)) if s.branch else "No branch"}'
        f'{" · +" + E(s.phone) if s.phone else ""}</div></div>'
        f'<form method="post" action="/c/{c.slug}/staff/{E(s.id)}/delete" '
        f'style="align-self:center"><button class="btn sm danger" type="submit">'
        f'×</button></form></div>'
        for s in org.staff if s.active)

    forms = f"""<div class="two" style="margin-top:16px">
  <div class="card">
    <div style="font-size:16px;font-weight:800">Branches</div>
    <div class="tiny" style="margin:7px 0 4px">Closing a branch keeps its past
      sales on the books.</div>
    {branch_rows or '<div class="muted" style="margin-top:12px">None yet.</div>'}
    <form method="post" action="/c/{c.slug}/branch" style="margin-top:18px">
      <div class="field"><input name="name" placeholder="Branch name" required></div>
      <div class="two">
        <div class="field"><input name="place" placeholder="Town or area"></div>
        <div class="field"><input name="manager" placeholder="Who runs it"></div></div>
      <button class="btn" type="submit">Add branch</button></form></div>

  <div class="card">
    <div style="font-size:16px;font-weight:800">People</div>
    <div class="tiny" style="margin:7px 0 4px">A directory of who works where.
      Logins are separate — those live in Setup.</div>
    {staff_rows or '<div class="muted" style="margin-top:12px">Nobody added yet.</div>'}
    <form method="post" action="/c/{c.slug}/staff" style="margin-top:18px">
      <div class="field"><input name="name" placeholder="Name" required></div>
      <div class="two">
        <div class="field"><select name="role" aria-label="Role">{role_opts}</select></div>
        <div class="field"><select name="branch" aria-label="Branch">
          <option value="">No branch</option>{branch_opts}</select></div></div>
      <div class="field"><input name="phone" placeholder="Phone (optional)"></div>
      <button class="btn" type="submit">Add person</button></form></div></div>"""

    return _head("People") + intro + compare + forms


# -------------------------------------------------------------------- the page

def page(c, *, book, ledger, org, queue, settings, account, panel: str = "stock",
         reply=None, question: str = "", outline=None, brief: str = "",
         deck_kind: str = "review", period: str = "all",
         flash: str = "", flash_kind: str = "ok") -> str:
    """Everything, once, in one document."""
    panel = panel if panel in {p for p, _, _ in PANELS} else "stock"

    summary = books.summary(book)
    counts = {
        "stock": len(summary["low_stock"]) + len(summary["out_of_stock"]),
        "ask": 0,
        "followups": len(queue),
        "money": len([e for e in ledger.expenses if not e.paid]),
        "deck": 0,
        "people": len([b for b in org.branches if b.active]),
    }
    hot = {"stock", "followups"}

    nav = '<div class="cnav" role="tablist">' + "".join(
        f'<button type="button" role="tab" data-go="{key}" '
        f'aria-selected="{"true" if key == panel else "false"}">'
        f'<span aria-hidden="true">{icon}</span>{E(label)}'
        + (f'<span class="n{" hot" if key in hot and counts[key] else ""}">{counts[key]}</span>'
           if counts[key] else "")
        + "</button>" for key, label, icon in PANELS) + "</div>"

    bodies = {
        "stock": _stock(c, book, org),
        "ask": _ask(c, reply, question, settings),
        "followups": _followups(c, queue, settings),
        "money": _money(c, book, ledger, org, period),
        "deck": _deck(c, outline, brief, deck_kind),
        "people": _people(c, org, book, ledger),
    }
    panes = "".join(f'<div class="panel{" on" if key == panel else ""}" data-panel="{key}">'
                    f'{bodies[key]}</div>' for key, _, _ in PANELS)

    pos = money.position(book, ledger)
    stats = [("Earned", short(summary["earned"])),
             ("In hand", short(pos["net"])),
             ("Owed to you", short(summary["owed"])),
             ("To chase", str(len(queue)))]
    hero = ui.cover_hero(c, settings, stats)

    back = (f'<div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">'
            f'<a class="btn ghost sm" href="/c/{c.slug}">← Workspace</a>'
            f'<span class="tiny">Six things, one page. Nothing here reloads when you switch.</span>'
            f'</div>')

    body = (f"<style>{EXTRA}</style>" + ui._flash(flash, flash_kind) + back + nav + panes
            + f"<script>{JS}</script>")

    return ui.layout(f"{c.name} · Console", body, active="clients", account=account,
                     trade_key=c.trade, full_bleed=hero)
