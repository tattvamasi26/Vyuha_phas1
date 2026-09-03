"""The workspace: four screens, one question box, and setup out of the way.

The old console was six panels of equal weight and no opinion about which
mattered. A fifty-person distributor has four different people opening this and
none of them wants a dashboard — they each want one thing, and the interface
should already be showing it.

So the shape changed:

* **Today** is the landing, and it is a ranked list of decisions rather than a
  set of tiles. Every finding on it was already being computed and was sitting
  one click inside a different panel, which is why nobody found any of them.
* **The second item is whatever this business does daily** — Sell for one that
  types entries, Data for one that sends files. Same slot, different job,
  because those are different businesses and pretending otherwise adds a screen
  each of them ignores.
* **Ask is the bar at the top of every screen**, not a panel. A panel nobody
  thinks to visit becomes a box that is always in front of them.
* **Setup is behind the gear**: branches, staff, invoice details, reorder
  levels, thresholds. All done once, in the first week, and all of it was
  sitting permanently in the middle of screens used every day.

Each view renders on its own request. The previous build put all six panels in
one 141KB document and toggled them with JavaScript, which made switching
instant and everything else slow — and it is the wrong trade once a screen has
real content on it.
"""

from __future__ import annotations

from datetime import date

from vyuha import fmt

from . import (agent, books, catalog, finance, followup, invoice, money,
               people, today as today_mod, ui)

E = ui.E


def rs(v) -> str:
    return fmt.rupees(v or 0, symbol="₹")


def short(v) -> str:
    return fmt.rupees_short(v or 0, symbol="₹")


#: The four screens, in the order somebody works through them. The second is
#: filled in per client — a business that types entries gets Sell, one that
#: sends files gets Data. They are different jobs, not two views of one.
def views_for(client) -> list[tuple[str, str]]:
    daily = ("sell", "Sell") if client.data_mode == "books" else ("data", "Data")
    return [("today", "Today"), daily, ("stock", "Stock"), ("money", "Money")]


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

/* --- the shelf ---------------------------------------------------- */
.shelf{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(252px,1fr))}
.sk{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  padding:15px 16px;display:flex;flex-direction:column;gap:11px;position:relative;
  border-top:2px solid var(--line-2);transition:border-color .16s}
.sk:hover{border-color:var(--ink-3)}
.sk.out{border-top-color:var(--crit)}
.sk.low{border-top-color:var(--warn)}
.sk.dead{border-top-color:var(--accent-2)}
.sk.ok{border-top-color:var(--ok)}
.sk-top{display:flex;gap:12px;align-items:flex-start}
.sk .glyph{width:38px;height:38px;flex:none;color:var(--ink-3)}
.sk.out .glyph{color:var(--crit)} .sk.low .glyph{color:var(--warn)}
.sk.dead .glyph{color:var(--accent-2)} .sk.ok .glyph{color:var(--accent)}
.sk .nm{font-size:14px;font-weight:600;line-height:1.3}
.sk .cat{font-family:var(--num);font-size:10px;color:var(--ink-3);margin-top:3px;
  letter-spacing:.06em;text-transform:uppercase}
.sk .qty{font-family:var(--num);font-size:22px;font-weight:600;line-height:1;
  font-variant-numeric:tabular-nums}
.sk .qty small{font-size:11px;font-weight:400;color:var(--ink-3);margin-left:3px}
.sk-bar{height:5px;border-radius:99px;background:var(--card-3);overflow:hidden;
  position:relative}
.sk-bar i{display:block;height:100%;border-radius:99px;background:var(--ok)}
.sk.low .sk-bar i{background:var(--warn)} .sk.out .sk-bar i{background:var(--crit)}
.sk.dead .sk-bar i{background:var(--accent-2)}
.sk-bar u{position:absolute;top:-2px;width:1px;height:9px;background:var(--ink-3);
  opacity:.7}
.sk-meta{display:flex;justify-content:space-between;gap:10px;font-family:var(--num);
  font-size:10.5px;color:var(--ink-3)}
.sk-act{display:flex;gap:6px;align-items:center;margin-top:2px}
.sk-act input{flex:1;min-width:0}
.filters{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 16px}
.filters button{font-family:var(--num);font-size:11px;padding:6px 12px;border-radius:6px;
  border:1px solid var(--line-2);background:var(--card);color:var(--ink-3);cursor:pointer;
  transition:.15s}
.filters button:hover{color:var(--ink);border-color:var(--ink-3)}
.filters button[aria-pressed=true]{background:var(--accent);color:#04120F;
  border-color:var(--accent);font-weight:600}
.filters button .c{opacity:.75;margin-left:5px}
.sk[hidden]{display:none}
details.levels summary{cursor:pointer;font-size:13px;font-weight:600;color:var(--ink-2);
  padding:12px 0;list-style:none}
details.levels summary::-webkit-details-marker{display:none}
details.levels summary::before{content:"▸ ";color:var(--ink-3)}
details.levels[open] summary::before{content:"▾ "}

/* --- bills -------------------------------------------------------- */
.inv{display:flex;gap:14px;padding:14px 0;border-top:1px solid var(--line);
  align-items:center;flex-wrap:wrap}
.inv:first-child{border-top:0}
.inv .no{font-family:var(--num);font-size:13px;font-weight:600;min-width:132px}
.inv .who{flex:1;min-width:140px;font-size:13.5px;font-weight:600}
.inv .amt{font-family:var(--num);font-size:14px;font-variant-numeric:tabular-nums;
  text-align:right;min-width:104px}
.pickable{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));
  max-height:260px;overflow-y:auto;padding:2px;margin-top:12px}
.psale{display:flex;gap:10px;align-items:flex-start;background:var(--card-2);
  border:1px solid var(--line);border-radius:var(--r-sm);padding:10px 12px;
  cursor:pointer;transition:.14s}
.psale:hover{border-color:var(--ink-3)}
.psale input{width:auto;margin:2px 0 0;flex:none;padding:0}
.psale:has(input:checked){border-color:var(--accent);background:var(--card-3)}
.psale .t{font-size:12.5px;font-weight:600;line-height:1.3}
.psale .m{font-family:var(--num);font-size:10.5px;color:var(--ink-3);margin-top:3px}
.tpl{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.gaps{border-left:3px solid var(--warn);padding:10px 0 10px 14px;margin-top:14px;
  font-size:12.5px;color:var(--ink-2);line-height:1.6}

.deckout{display:flex;justify-content:space-between;align-items:center;gap:16px;
  flex-wrap:wrap;margin-top:18px;padding:14px 16px;border-radius:var(--r-sm);
  border:1px solid var(--accent);background:var(--card-2)}

/* --- the shell ---------------------------------------------------- */
.wsbar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  padding:14px 0 16px;border-bottom:1px solid var(--line);margin-bottom:26px}
.wsbar .biz{font-family:var(--display);font-weight:800;font-size:17px;
  letter-spacing:-.01em;white-space:nowrap}
.wsbar .biz small{display:block;font-family:var(--num);font-size:9.5px;
  font-weight:500;letter-spacing:.16em;color:var(--ink-3);margin-top:3px}
.askform{flex:1;min-width:210px;position:relative}
.askform input{padding:9px 13px 9px 34px;font-size:13.5px;border-radius:9px}
.askform::before{content:"✦";position:absolute;left:12px;top:50%;
  transform:translateY(-50%);color:var(--accent);font-size:13px;pointer-events:none}
.wsnav{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:24px}
.wsnav a{font-size:13.5px;font-weight:600;padding:8px 15px;border-radius:9px;
  color:var(--ink-3);border:1px solid transparent;transition:.15s}
.wsnav a:hover{color:var(--ink);background:var(--card)}
.wsnav a.on{background:var(--card-2);border-color:var(--line-2);color:var(--ink)}
.wsnav a .n{font-family:var(--num);font-size:10.5px;font-weight:600;margin-left:7px;
  padding:1px 6px;border-radius:99px;background:var(--card-3);color:var(--ink-3)}
.wsnav a.on .n{background:var(--accent);color:#04120F}
.wsnav a .n.hot{background:var(--crit);color:#fff}
.wsnav .gear{margin-left:auto}

/* --- today -------------------------------------------------------- */
.hello{margin-bottom:6px}
.hello h1{font-family:var(--display);font-weight:800;font-size:clamp(24px,3.6vw,34px);
  letter-spacing:-.022em;line-height:1.1}
.hello p{color:var(--ink-2);font-size:15px;margin-top:8px}
.todo{display:flex;flex-direction:column;gap:9px;margin-top:26px}
.td{display:flex;gap:16px;align-items:center;flex-wrap:wrap;
  background:var(--card);border:1px solid var(--line);border-left:3px solid var(--ink-3);
  border-radius:var(--r);padding:16px 18px;transition:.15s}
.td:hover{border-color:var(--line-2)}
.td.critical{border-left-color:var(--crit)}
.td.warning{border-left-color:var(--warn)}
.td.info{border-left-color:var(--accent)}
.td .txt{flex:1;min-width:200px}
.td .t{font-size:15.5px;font-weight:600;line-height:1.35}
.td .d{font-size:12.5px;color:var(--ink-3);margin-top:5px;line-height:1.5}
.td .go{white-space:nowrap}
.allclear{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  padding:34px 24px;text-align:center;margin-top:26px}
.allclear .big{font-family:var(--display);font-weight:800;font-size:22px;
  margin-bottom:8px}
.chase{display:flex;gap:14px;padding:15px 0;border-top:1px solid var(--line);
  align-items:center;flex-wrap:wrap}
.chase:first-of-type{border-top:0}
.chase .who{font-size:14px;font-weight:600}
.chase .why{font-size:12px;color:var(--ink-3);margin-top:3px}
.chase .act{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}

/* --- setup -------------------------------------------------------- */
.setup-grid{display:grid;grid-template-columns:1fr;gap:16px}
@media (min-width:860px){.setup-grid{grid-template-columns:1fr 1fr}}
.todoline{display:flex;gap:12px;align-items:center;padding:11px 0;
  border-top:1px solid var(--line)}
.todoline:first-child{border-top:0}
.todoline .tick{width:18px;height:18px;border-radius:5px;border:1.5px solid var(--line-2);
  display:grid;place-items:center;font-size:11px;color:var(--ink-3);flex:none}
.todoline .tick.done{background:var(--ok);border-color:var(--ok);color:#08140A}
.todoline .lbl{flex:1;font-size:13.5px}
.todoline .lbl small{display:block;font-size:11.5px;color:var(--ink-3);margin-top:2px}

.chooser{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));
  margin:20px 0 20px}
.pick-sec{display:flex;flex-direction:column;gap:4px;padding:12px 14px;
  border:1px solid var(--line);border-radius:var(--r-sm);background:var(--card);
  transition:.15s}
.pick-sec:hover{border-color:var(--ink-3)}
.pick-sec.on{border-color:var(--accent);background:var(--card-2)}
.pick-sec b{font-size:13.5px;font-weight:600}
.pick-sec span{font-size:11px;color:var(--ink-3);line-height:1.45}
.pick-sec.on b{color:var(--accent)}
.note-line{font-size:12.5px;color:var(--ink-3);line-height:1.6;margin-top:16px;
  padding-left:14px;border-left:2px solid var(--line-2);max-width:74ch}
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
  var filters = document.querySelectorAll('.filters button');
  filters.forEach(function(b){
    b.addEventListener('click', function(){
      var want = b.dataset.filter;
      filters.forEach(function(o){ o.setAttribute('aria-pressed', String(o === b)); });
      document.querySelectorAll('.sk').forEach(function(card){
        card.hidden = want !== 'all' && !card.classList.contains(want);
      });
    });
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

def _cover(book, item, window: int = 90) -> float | None:
    """Days of stock left at the recent run rate. None when it has never sold.

    The number an owner actually wants. "Twelve bags left" means nothing on its
    own — twelve bags is a fortnight of urea and two years of soil test kits.
    """
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=window)).isoformat()
    moved = sum(s.qty for s in book.sales if s.sku == item.sku and s.date >= cutoff)
    if moved <= 0:
        return None
    per_day = moved / window
    return item.stock_qty / per_day if per_day else None


def _stock(c, book, org) -> str:
    """The shelf, not a spreadsheet.

    Ordered by how worried to be: out of stock first, then below reorder, then
    everything else. The old table sorted alphabetically and left the operator
    to find the problems, which is the opposite of what a stock screen is for.
    """
    summary = books.summary(book)
    low, gone = summary["low_stock"], summary["out_of_stock"]
    never = summary["never_sold"]
    locked = sum(i.value for i in never)

    tiles = "".join([
        _stat("Stock value", short(summary["stock_value"]),
              f"{summary['items']} item(s) on the shelf"),
        _stat("Needs ordering", str(len(gone) + len([i for i in low if i.stock_qty > 0])),
              "out, or below reorder level"),
        _stat("Out of stock", str(len(gone)),
              "losing sales right now" if gone else "nothing is out"),
        _stat("Dead stock", short(locked), f"{len(never)} item(s) never sold"),
    ])

    if not book.items:
        return (_head("Stock")
                + _empty("Nothing on the shelf yet",
                         "Add what you sell and Vyuha starts watching the levels."))

    dead_skus = {i.sku for i in never}

    def state_of(i) -> str:
        if i.stock_qty <= 0:
            return "out"
        if i.low:
            return "low"
        if i.sku in dead_skus:
            return "dead"
        return "ok"

    rank = {"out": 0, "low": 1, "dead": 2, "ok": 3}
    items = sorted(book.items, key=lambda i: (rank[state_of(i)], -i.value))
    counts: dict[str, int] = {"out": 0, "low": 0, "dead": 0, "ok": 0}
    for i in items:
        counts[state_of(i)] += 1

    cards = ""
    for i in items:
        state = state_of(i)
        cover = _cover(book, i)
        # The bar reads against the reorder level, not against capacity — the
        # question is "how close am I to needing to order", and nobody records
        # what a full shelf looks like.
        ceiling = max(i.reorder_level * 2, i.stock_qty, 1)
        fill = min(i.stock_qty / ceiling * 100, 100)
        marker = (f'<u style="left:{min(i.reorder_level / ceiling * 100, 100):.1f}%"'
                  f' title="Reorder at {i.reorder_level:g}"></u>'
                  if i.reorder_level > 0 else "")

        if cover is not None:
            cover_text = f"{cover:.0f}d cover"
        elif i.sku in dead_skus:
            cover_text = "never sold"
        else:
            cover_text = "no recent sales"

        label = {"out": "out of stock", "low": "below reorder",
                 "dead": "never sold", "ok": "in stock"}[state]

        cards += f"""<div class="sk {state}">
  <div class="sk-top">{catalog.glyph_for(i.name, i.category)}
    <div style="min-width:0;flex:1">
      <div class="nm">{E(i.name)}</div>
      <div class="cat">{E(i.category)} · {E(i.sku)}</div></div>
    <div style="text-align:right">
      <div class="qty">{i.stock_qty:g}<small>{E(i.unit)}</small></div></div>
  </div>
  <div class="sk-bar"><i style="width:{fill:.1f}%"></i>{marker}</div>
  <div class="sk-meta"><span>{E(cover_text)}</span><span>{short(i.value)}</span></div>
  <div class="sk-meta"><span class="pill {_sev({"out": "critical", "low": "warning",
                                                 "dead": "info"}.get(state, "ok"))}"
    >{label}</span><span>{rs(i.rate)} each</span></div>
  <form class="sk-act" method="post" action="/c/{c.slug}/stock/receive">
    <input type="hidden" name="sku" value="{E(i.sku)}">
    <input class="inline-in" name="qty" placeholder="qty in" inputmode="decimal"
           aria-label="Quantity received for {E(i.name)}" style="width:auto">
    <button class="btn sm{" primary" if state in ("out", "low") else ""}"
            type="submit">Received</button>
  </form></div>"""

    filters = f"""<div class="filters">
  <button type="button" data-filter="all" aria-pressed="true">Everything
    <span class="c">{len(items)}</span></button>
  <button type="button" data-filter="out" aria-pressed="false">Out
    <span class="c">{counts["out"]}</span></button>
  <button type="button" data-filter="low" aria-pressed="false">Below reorder
    <span class="c">{counts["low"]}</span></button>
  <button type="button" data-filter="dead" aria-pressed="false">Never sold
    <span class="c">{counts["dead"]}</span></button>
  <button type="button" data-filter="ok" aria-pressed="false">Fine
    <span class="c">{counts["ok"]}</span></button></div>"""

    rows = "".join(
        f'<tr><td><b>{E(i.name)}</b></td>'
        f'<td class="num">{i.stock_qty:g}</td>'
        f'<td class="num"><input class="inline-in" name="lvl_{E(i.sku)}" '
        f'value="{i.reorder_level:g}" inputmode="decimal" '
        f'aria-label="Reorder level for {E(i.name)}"></td>'
        f'<td class="num">{rs(i.rate)}</td><td class="num">{rs(i.cost)}</td>'
        f'<td class="num">{short(i.value)}</td></tr>'
        for i in sorted(book.items, key=lambda x: x.name))

    levels = f"""<details class="levels" style="margin-top:18px">
  <summary>Edit reorder levels and prices for all {len(book.items)} items</summary>
  <form method="post" action="/c/{c.slug}/stock/reorder">
    <div class="card" style="padding:0;overflow:hidden">
      <div class="row" style="justify-content:space-between;padding:16px 18px">
        <div class="tiny">A reorder level of 0 means Vyuha will never warn you
          about that item.</div>
        <button class="btn sm primary" type="submit">Save levels</button></div>
      <div class="scroll-x"><table class="mtable">
        <tr><th>Item</th><th class="num">In stock</th><th class="num">Reorder at</th>
            <th class="num">Sells at</th><th class="num">Costs</th>
            <th class="num">Value</th></tr>
        {rows}</table></div></div></form></details>"""

    branch_opts = "".join(f'<option value="{E(b.id)}">{E(b.name)}</option>'
                          for b in org.branches if b.active)
    item_opts = "".join(f'<option value="{E(i.sku)}">{E(i.name)}</option>'
                        for i in sorted(book.items, key=lambda x: x.name))

    forms = f"""<div class="two" style="margin-top:16px">
  <div class="card">
    <div style="font-size:16px;font-weight:700">A delivery came in</div>
    <div class="tiny" style="margin:7px 0 15px">Adds to what is already there.
      A cost here becomes the new cost price.</div>
    <form method="post" action="/c/{c.slug}/stock/receive">
      <div class="field"><select name="sku" required aria-label="Item">
        <option value="">Which item…</option>{item_opts}</select></div>
      <div class="two">
        <div class="field"><input name="qty" placeholder="How many" inputmode="decimal" required></div>
        <div class="field"><input name="cost" placeholder="Cost each (optional)" inputmode="decimal"></div>
      </div>
      <button class="btn primary" type="submit">Add to stock</button></form></div>
  <div class="card">
    <div style="font-size:16px;font-weight:700">You counted the shelf</div>
    <div class="tiny" style="margin:7px 0 15px">Sets the number to what is
      actually there. This replaces the figure — it does not add to it.</div>
    <form method="post" action="/c/{c.slug}/stock/count">
      <div class="field"><select name="sku" required aria-label="Item">
        <option value="">Which item…</option>{item_opts}</select></div>
      <div class="field"><input name="counted" placeholder="Counted quantity"
        inputmode="decimal" required></div>
      {f'<div class="field"><select name="branch" aria-label="Branch"><option value="">Branch (optional)</option>{branch_opts}</select></div>' if branch_opts else ''}
      <button class="btn" type="submit">Set count</button></form></div></div>"""

    return (_head("Stock") + f'<div class="grid g4">{tiles}</div>'
            + '<div style="height:18px"></div>' + filters
            + f'<div class="shelf">{cards}</div>' + levels + forms)


# -------------------------------------------------------------------- 03 · ask

#: Tool names as an owner would say them, for the "consulted" line. A raw
#: function name on screen tells him nothing and looks like a leak.
_TOOL_WORDS = {
    "query_sales": "your sales",
    "stock_report": "your stock",
    "customer_detail": "that customer's history",
    "item_detail": "that item's history",
    "compare_periods": "last month against this",
    "financial_statements": "your statements",
    "list_followups": "who owes you",
    "list_branches": "your branches",
}


def _ask(c, reply, question: str, settings) -> str:
    live = settings.vision_live
    offered = agent.SUGGESTED if live else agent.OFFLINE_SUGGESTED
    chips = "".join(f'<span class="qchip">{E(q)}</span>' for q in offered)

    if reply is None:
        out = ('<div class="muted" style="margin-top:20px">Ask anything about this '
               'business — money, stock, customers, branches. Every answer comes from '
               'the numbers on this page, never from a guess.</div>')
    elif reply.ok:
        # Say what it read. An answer whose provenance is visible can be
        # checked; one that just appears has to be taken on faith.
        consulted = ""
        if reply.source == "claude" and reply.used:
            seen: list[str] = []
            for name in reply.used:
                word = _TOOL_WORDS.get(name, name)
                if word not in seen:
                    seen.append(word)
            consulted = (' · looked at ' + ", ".join(seen[:4])
                         + (f" and {len(seen) - 4} more" if len(seen) > 4 else ""))
        deck = ""
        if reply.deck:
            deck = f"""<div class="deckout">
  <div><div style="font-size:15px;font-weight:700">Your deck is ready</div>
    <div class="tiny" style="margin-top:5px">{E(reply.deck_label)}</div></div>
  <div class="row" style="gap:8px">
    <a class="btn sm primary" href="{E(reply.deck)}" target="_blank"
       rel="noopener">Open the deck</a>
    <a class="btn sm ghost" href="/c/{c.slug}/deck/pptx">PPTX</a>
    <a class="btn sm ghost" href="/c/{c.slug}/deck/pdf">PDF</a></div></div>"""
        out = (f'<div class="answer">{E(reply.text)}</div>{deck}'
               f'<div class="tiny" style="margin-top:14px">'
               f'{E(reply.label)}{E(consulted)}</div>')
    else:
        out = (f'<div class="card" style="margin-top:18px;border-color:rgba(251,191,36,.3)">'
               f'<div style="font-size:15px;font-weight:800">Could not answer that</div>'
               f'<div class="muted" style="margin-top:8px">{E(reply.error)}</div></div>')

    state = ("Connected — Vyuha will query your books directly to answer, and "
             "says which parts it read."
             if live else
             "No Claude key yet, so Vyuha answers the common questions straight "
             "from your numbers. Connect a key in Settings and it can work out "
             "anything you ask.")

    return (_head("Ask", '<span class="tiny">Decks are made here too — '
                   'just ask for one</span>')
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

#: What somebody can ask to see. Each is one question, answered on its own.
MONEY_SECTIONS = [
    ("summary",  "Where I stand",   "The short version — what came in, what went out"),
    ("profit",   "Profit",          "What was earned, what it cost, what is left"),
    ("owed",     "Who owes what",   "Money out to customers, and money you owe suppliers"),
    ("costs",    "Costs",           "Every head, and what share of turnover it eats"),
    ("health",   "Health check",    "The ratios a lender asks for, and break-even"),
]


def _money(c, book, ledger, org, period: str = "all", show: str = "summary") -> str:
    """Four numbers, then whichever statement was asked for.

    The period selector and the headline figures stay put; everything below is
    one section. Somebody looking for last month's profit should not have to
    scroll past a balance sheet to reach it.
    """
    show = show if show in {k for k, _l, _d in MONEY_SECTIONS} else "summary"
    st = finance.statements(c and book, ledger, period) if False else \
        finance.statements(book, ledger, period)
    pl, cf, bs = st["pl"], st["cash"], st["balance"]
    ar, ap = st["receivables"], st["payables"]
    label = st["period"]["label"]

    periods = "".join(
        f'<a href="/c/{c.slug}/money?show={E(show)}&period={E(key)}"'
        f'{" class=\'on\'" if key == period else ""}>{E(text)}</a>'
        for key, text, _k in finance.periods(book, ledger)[:8])

    tiles = "".join([
        _stat("In hand", short(cf["net_movement"]),
              f"{short(cf['received'])} in, {short(cf['paid_out'])} out"),
        _stat("Profit", short(pl["net_profit"]),
              f"{pl['net_margin_pct']:.1f}% of what you billed"),
        _stat("Owed to you", short(ar["total"]),
              f"{short(ar['overdue'])} of it late" if ar["overdue"] else "none late"),
        _stat("You owe", short(ap["total"]),
              f"{short(ap['overdue'])} of it late" if ap["overdue"] else "none late"),
    ])

    chooser = "".join(
        f'<a class="pick-sec{" on" if k == show else ""}" '
        f'href="/c/{c.slug}/money?show={k}&period={E(period)}">'
        f'<b>{E(lab)}</b><span>{E(desc)}</span></a>'
        for k, lab, desc in MONEY_SECTIONS)

    body = {
        "summary": _m_summary, "profit": _m_profit, "owed": _m_owed,
        "costs": _m_costs, "health": _m_health,
    }[show](c, book, ledger, st)

    return (_head("Money", f'<div class="periods">{periods}</div>')
            + f'<div class="grid g4">{tiles}</div>'
            + f'<div class="chooser">{chooser}</div>'
            + body)


def _ln(lab, amount, cls="", pct=None, sub=False) -> str:
    p = f'<span class="pc">{pct}</span>' if pct else ""
    return (f'<div class="ln {cls}{" sub" if sub else ""}">'
            f'<span class="l">{E(lab)}</span>'
            f'<span class="a">{rs(amount)}{p}</span></div>')


def _m_summary(c, book, ledger, st) -> str:
    """The short version, and the one line that matters most."""
    cf, months = st["cash"], st["monthly"]
    chart = ""
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
        chart = f"""<div class="card">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div style="font-size:16px;font-weight:700">Month by month</div>
    <div class="legend"><span><i style="background:var(--accent)"></i>Billed</span>
      <span><i style="background:var(--ok)"></i>Profit</span></div></div>
  <div class="trend">{bars}</div>
  <div class="tiny">{E(last["label"])}: {rs(last["revenue"])} billed,
    {rs(last["profit"])} profit{f", {last['change_pct']:+.0f}% on the month before"
                                 if last["change_pct"] else ""}.</div></div>"""

    week = money.due_this_week(book, ledger)
    upcoming = ""
    if week["incoming"] or week["outgoing"]:
        def line(when, who, amount, late):
            return (f'<div class="row" style="justify-content:space-between;padding:9px 0;'
                    f'border-top:1px solid var(--line)">'
                    f'<div><span style="font-weight:600;font-size:13.5px">{E(who)}</span>'
                    f'<div class="tiny" style="margin-top:3px">{E(when)}'
                    f'{" · overdue" if late else ""}</div></div>'
                    f'<span class="mono" style="font-size:13.5px">{rs(amount)}</span></div>')
        today_iso = date.today().isoformat()
        ins = "".join(line(s.due_date, s.party or "Customer", s.amount,
                           s.due_date < today_iso) for s in week["incoming"][:6]) \
            or '<div class="tiny">Nothing due in.</div>'
        outs = "".join(line(e.due_date, e.party or e.category, e.amount,
                            e.due_date < today_iso) for e in week["outgoing"][:6]) \
            or '<div class="tiny">Nothing due out.</div>'
        upcoming = f"""<div class="card" style="margin-top:16px">
  <div style="font-size:16px;font-weight:700">The next 7 days</div>
  <div class="two" style="margin-top:15px">
    <div><div class="tiny" style="margin-bottom:4px">COMING IN ·
      {E(short(week['incoming_total']))}</div>{ins}</div>
    <div><div class="tiny" style="margin-bottom:4px">GOING OUT ·
      {E(short(week['outgoing_total']))}</div>{outs}</div></div></div>"""

    gap = (f'<div class="note-line">Profit is not cash. '
           f'{rs(cf["billed_not_collected"])} was billed and not collected; '
           f'{rs(cf["incurred_not_paid"])} was incurred and not paid. That gap is '
           f'the whole difference between the two.</div>')
    return chart + upcoming + gap


def _m_profit(c, book, ledger, st) -> str:
    pl, cf = st["pl"], st["cash"]
    opex = "".join(_ln(head, -amt, sub=True) for head, amt in pl["opex_rows"][:8])
    coverage = ""
    if pl["cost_coverage_pct"] < 100:
        coverage = (f'<div class="note-line">Gross margin covers the '
                    f'{pl["cost_coverage_pct"]:.0f}% of sale lines with a known cost '
                    f'price. Add cost prices on the Stock screen to make it exact.</div>')
    return f"""<div class="two">
  <div class="card">
    <div class="row" style="justify-content:space-between;margin-bottom:14px">
      <div style="font-size:16px;font-weight:700">Profit &amp; loss</div>
      <span class="pill dim">what you billed</span></div>
    <div class="stmt">
      {_ln("Revenue", pl["revenue"])}
      {_ln("Cost of goods sold", -pl["cogs"])}
      {_ln("Gross profit", pl["gross_profit"], cls="tot " + ("pos" if pl["gross_profit"] >= 0 else "neg"), pct=f"{pl['gross_margin_pct']:.1f}%")}
      {_ln("Running costs", -pl["opex"])}
      {opex}
      {_ln("Net profit", pl["net_profit"], cls="tot " + ("pos" if pl["net_profit"] >= 0 else "neg"), pct=f"{pl['net_margin_pct']:.1f}%")}
    </div></div>
  <div class="card">
    <div class="row" style="justify-content:space-between;margin-bottom:14px">
      <div style="font-size:16px;font-weight:700">Cash</div>
      <span class="pill dim">what actually moved</span></div>
    <div class="stmt">
      {_ln("Received from customers", cf["received"])}
      {_ln("Paid out", -cf["paid_out"])}
      {_ln("Net movement", cf["net_movement"], cls="tot " + ("pos" if cf["net_movement"] >= 0 else "neg"))}
    </div>
    <div class="note-line" style="margin-top:16px">Billed but not collected:
      {rs(cf["billed_not_collected"])}. Incurred but not paid:
      {rs(cf["incurred_not_paid"])}.</div></div></div>{coverage}"""


def _m_owed(c, book, ledger, st) -> str:
    def ageing(title, data, kind, colour_from) -> str:
        peak = max((v for _l, v, _p in data["buckets"]), default=0) or 1.0
        rows = "".join(
            f'<div class="r b{i + colour_from}"><span class="lb">{E(lab)}</span>'
            f'<span class="track"><i style="width:{val / peak * 100:.1f}%"></i></span>'
            f'<span class="amt">{short(val)}</span></div>'
            for i, (lab, val, _p) in enumerate(data["buckets"]))
        parties = "".join(
            f'<div class="row" style="justify-content:space-between;padding:8px 0;'
            f'border-top:1px solid var(--line)">'
            f'<span style="font-size:13px">{E(r["party"])}</span>'
            f'<span class="mono" style="font-size:12.5px">{rs(r["total"])}'
            f'<span class="tiny" style="margin-left:8px">{r["oldest"]}d</span></span></div>'
            for r in data["parties"][:8])
        return f"""<div class="card">
  <div class="row" style="justify-content:space-between;margin-bottom:14px">
    <div style="font-size:16px;font-weight:700">{E(title)}</div>
    <span class="pill {"crit" if data["overdue"] else "ok"}">
      {short(data["overdue"])} late</span></div>
  <div class="age">{rows}</div>
  {f'<div style="margin-top:14px"><div class="tiny" style="margin-bottom:2px">BY {kind}</div>{parties}</div>' if parties else ''}</div>"""

    return ('<div class="two">'
            + ageing("Customers owe you", st["receivables"], "CUSTOMER", 0)
            + ageing("You owe suppliers", st["payables"], "SUPPLIER", 0)
            + "</div>"
            + '<div class="note-line">"Not yet due" is money that is not late. '
              'Folding it into the first ageing bucket makes a healthy ledger read '
              'as overdue, so it is kept separate.</div>')


def _m_costs(c, book, ledger, st) -> str:
    rows = "".join(
        f'<tr><td><b>{E(e["head"])}</b></td>'
        f'<td class="num">{rs(e["amount"])}</td>'
        f'<td class="num">{e["pct_of_revenue"]:.1f}%</td>'
        f'<td class="num">{e["count"]}</td>'
        f'<td class="num">{rs(e["unpaid"]) if e["unpaid"] else "—"}</td></tr>'
        for e in st["expenses"])
    recent = ""
    if ledger.expenses:
        recent = "".join(
            f'<tr><td>{E(e.date)}</td><td><b>{E(e.category)}</b>'
            + (f'<div class="tiny" style="margin-top:3px">{E(e.party)}</div>'
               if e.party else "")
            + f'</td><td class="num">{rs(e.amount)}</td>'
            f'<td>{"<span class=\'pill ok\'>paid</span>" if e.paid else "<span class=\'pill crit\'>late</span>" if e.overdue else "<span class=\'pill warn\'>owed</span>"}</td>'
            f'<td style="text-align:right">'
            + ("" if e.paid else
               f'<form method="post" action="/c/{c.slug}/expense/{e.id}/paid" '
               f'style="display:inline"><button class="btn sm ghost" type="submit">'
               f'Mark paid</button></form> ')
            + f'<form method="post" action="/c/{c.slug}/expense/{e.id}/delete" '
              f'style="display:inline"><button class="btn sm danger" type="submit">×'
              f'</button></form></td></tr>' for e in ledger.expenses[:20])
        recent = (f'<div class="card" style="margin-top:16px;padding:0;overflow:hidden">'
                  f'<div style="font-size:16px;font-weight:700;padding:18px 20px">'
                  f'Recent payments</div><div class="scroll-x"><table class="mtable">'
                  f'<tr><th>Date</th><th>What</th><th class="num">Amount</th>'
                  f'<th>State</th><th></th></tr>{recent}</table></div></div>')

    return (f'<div class="card" style="padding:0;overflow:hidden">'
            f'<div style="padding:18px 20px 4px">'
            f'<div style="font-size:16px;font-weight:700">Every cost head</div>'
            f'<div class="tiny" style="margin-top:6px">Share of turnover is the column '
            f'that matters — rent means nothing until you know it is 3% or 30%.</div></div>'
            f'<div class="scroll-x"><table class="mtable">'
            f'<tr><th>Head</th><th class="num">Amount</th><th class="num">% of turnover</th>'
            f'<th class="num">Entries</th><th class="num">Unpaid</th></tr>'
            f'{rows or "<tr><td colspan=5 class=tiny>Nothing recorded yet.</td></tr>"}'
            f'</table></div></div>{recent}'
            f'<div class="note-line">Record what leaves the business on the Sell '
            f'screen. Until you do, this is a receivables report, not a cash flow.</div>')


def _m_health(c, book, ledger, st) -> str:
    cards = "".join(
        f'<div class="ratio {"good" if r["good"] else "bad"}">'
        f'<div class="n">{E(r["name"])}</div>'
        f'<div class="v">{r["value"]:,.1f}<span class="u">{E(r["unit"])}</span></div>'
        f'<div class="note">{E(r["note"])}</div></div>' for r in st["ratios"])
    flagged = [r for r in st["ratios"] if not r["good"]]
    verdict = ("Everything is inside a healthy range." if not flagged else
               f"{len(flagged)} worth a look: " + ", ".join(r["name"] for r in flagged) + ".")

    co, be = st["concentration"], st["break_even"]
    risk = {"high": ("crit", "concentrated"), "watch": ("warn", "watch this"),
            "spread": ("ok", "well spread")}[co["risk"]]
    cust = "".join(
        f'<div style="margin-bottom:11px"><div class="row" '
        f'style="justify-content:space-between"><span style="font-size:13px">'
        f'{E(r["party"])}</span><span class="mono" style="font-size:12.5px">'
        f'{short(r["amount"])} <span class="tiny">{r["share"] * 100:.0f}%</span></span></div>'
        f'<div class="meter"><i style="width:{r["share"] * 100:.1f}%"></i></div></div>'
        for r in co["customers"][:6])

    return f"""<div class="card">
  <div style="font-size:16px;font-weight:700">The numbers a lender asks for</div>
  <div class="tiny" style="margin:7px 0 16px">{E(verdict)}</div>
  <div class="ratios">{cards}</div></div>
<div class="two" style="margin-top:16px">
  <div class="card">
    <div class="row" style="justify-content:space-between;margin-bottom:6px">
      <div style="font-size:16px;font-weight:700">Where revenue comes from</div>
      <span class="pill {risk[0]}">{risk[1]}</span></div>
    <div class="tiny" style="margin-bottom:15px">Biggest customer is
      {co["top_customer_share"] * 100:.0f}% and the top three are
      {co["top3_share"] * 100:.0f}%, across {co["customer_count"]} customer(s).</div>
    {cust}</div>
  <div class="card">
    <div style="font-size:16px;font-weight:700">Break-even</div>
    <div class="tiny" style="margin:7px 0 16px">At a
      {be["contribution_margin_pct"]:.1f}% gross margin you need
      {rs(be["break_even_monthly"])} of sales a month to cover
      {rs(be["fixed_monthly"])} of running costs.</div>
    <div class="row" style="justify-content:space-between;align-items:baseline">
      <div><div class="tiny">YOU AVERAGE</div>
        <div style="font-family:var(--num);font-size:26px;font-weight:600;margin-top:5px">
          {short(be["actual_monthly"])}</div></div>
      <span class="pill {"ok" if be["clears"] else "crit"}">
        {"clears by " + short(abs(be["headroom"])) if be["clears"]
         else "short by " + short(abs(be["headroom"]))}</span></div>
    <div class="note-line" style="margin-top:14px">Every head except purchases is
      treated as fixed, so read this as the cautious version.</div></div></div>"""


def _bills(c, book, invoices) -> str:
    """Raise a proper tax invoice from sales already on the book.

    Billing is not the same job as recording a sale, which is why it is its own
    panel: a sale is one line typed while a customer waits, an invoice is a
    document raised afterwards — often covering several sales at once — that has
    to satisfy somebody's accountant.
    """
    gaps = invoice.missing(c)
    billed = {sid for inv in invoices for sid in inv.sale_ids}
    unbilled = [s for s in reversed(book.sales) if s.id not in billed][:40]

    tiles = "".join([
        _stat("Invoices raised", str(len(invoices)),
              f"next is {invoice.next_number(c)[0]}"),
        _stat("Invoiced", short(sum(i.rounded for i in invoices)),
              "including tax"),
        _stat("Not yet billed", str(len([s for s in book.sales if s.id not in billed])),
              "sales with no invoice against them"),
        _stat("Tax collected", short(sum(i.tax for i in invoices)),
              "CGST, SGST and IGST"),
    ])

    gap_note = ""
    if gaps:
        gap_note = (f'<div class="gaps"><b>These print as a bill of supply, not a '
                    f'tax invoice.</b><br>Missing: {E(", ".join(gaps))}. '
                    f'Fill them in below and every invoice from then on carries them.'
                    f'</div>')

    # --- pick the sales to bill
    if unbilled:
        picks = "".join(
            f'<label class="psale"><input type="checkbox" name="sale_ids" '
            f'value="{E(s.id)}">'
            f'<span><span class="t">{E(s.item)}</span>'
            f'<span class="m">{E(s.party or "Cash")} · {s.qty:g} × {rs(s.rate)} '
            f'= {rs(s.amount)}</span>'
            f'<span class="m">{E(s.date)} · {E(s.id)}</span></span></label>'
            for s in unbilled)
        raise_card = f"""<div class="card">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div><div style="font-size:16px;font-weight:700">Raise an invoice</div>
      <div class="tiny" style="margin-top:6px">Tick everything going on one bill —
        a customer who bought three things gets one invoice, not three.</div></div>
  </div>
  <form method="post" action="/c/{c.slug}/invoice">
    <div class="pickable">{picks}</div>
    <div class="two" style="margin-top:16px">
      <div class="field"><input name="party_gstin" placeholder="Buyer's GSTIN (optional)"></div>
      <div class="field"><select name="party_state" aria-label="Buyer's state">
        <option value="">Same state as you</option>
        {"".join(f'<option value="{E(k)}">{E(v)}</option>' for k, v in sorted(invoice.STATES.items(), key=lambda kv: kv[1]))}
      </select><div class="tiny" style="margin-top:5px">Another state means IGST
        instead of CGST + SGST</div></div>
    </div>
    <div class="field"><input name="party_address" placeholder="Buyer's address (optional)"></div>
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
      <div class="tiny">Numbering is sequential and gap-free. A cancelled
        invoice keeps its number used.</div>
      <button class="btn primary" type="submit">Raise invoice</button></div>
  </form></div>"""
    else:
        raise_card = _empty("Everything is billed",
                            "Every sale on the book already has an invoice against it.")

    # --- what has been raised
    listed = ""
    if invoices:
        rows = "".join(
            f'<div class="inv"><span class="no">{E(i.number)}</span>'
            f'<span class="who">{E(i.party)}'
            f'<div class="tiny" style="margin-top:3px">{E(i.date)} · '
            f'{len(i.lines)} line(s)'
            + (f" · tax {short(i.tax)}" if i.taxed else " · no tax")
            + f'</div></span>'
            f'<span class="pill {"ok" if i.paid else "warn"}">'
            f'{"paid" if i.paid else "due"}</span>'
            f'<span class="amt">{rs(i.rounded)}</span>'
            f'<span class="row" style="gap:7px">'
            f'<a class="btn sm" href="/c/{c.slug}/invoice/{E(i.id)}" target="_blank" '
            f'rel="noopener">Open</a>'
            f'<a class="btn sm ghost" href="/c/{c.slug}/invoice/{E(i.id)}/pdf">PDF</a>'
            f'<form method="post" action="/c/{c.slug}/invoice/{E(i.id)}/delete" '
            f'style="display:inline"><button class="btn sm danger" type="submit">'
            f'×</button></form></span></div>' for i in invoices[:30])
        listed = (f'<div class="card" style="margin-top:16px">'
                  f'<div style="font-size:16px;font-weight:700;margin-bottom:6px">'
                  f'Invoices raised</div>'
                  f'<div class="tiny" style="margin-bottom:8px">Open prints from the '
                  f'browser — that page is self-contained, so it works with no '
                  f'internet.</div>{rows}</div>')

    # --- who you are, on the bill
    tpl = "".join(
        f'<label class="seg"><input type="radio" name="invoice_template" '
        f'value="{E(k)}"{" checked" if (c.invoice_template or "classic") == k else ""}>'
        f'<span>{E(label)}</span></label>'
        for k, (label, _why) in invoice.TEMPLATES.items())
    state_opts = "".join(
        f'<option value="{E(k)}"{" selected" if c.state == k else ""}>{E(v)}</option>'
        for k, v in sorted(invoice.STATES.items(), key=lambda kv: kv[1]))

    identity = f"""<div class="card" style="margin-top:16px">
  <div style="font-size:16px;font-weight:700">What prints at the top</div>
  <div class="tiny" style="margin:7px 0 15px">Set once. Every invoice from then
    on carries it.</div>
  <form method="post" action="/c/{c.slug}/invoice/identity">
    <div style="margin-bottom:6px">{tpl}</div>
    <div class="tiny" style="margin-bottom:16px">
      {E(invoice.TEMPLATES.get(c.invoice_template or "classic", ("", ""))[1])}</div>
    <div class="two">
      <div class="field"><input name="gstin" value="{E(c.gstin)}" placeholder="Your GSTIN"></div>
      <div class="field"><select name="state" aria-label="Your state">
        <option value="">Your state…</option>{state_opts}</select></div>
    </div>
    <div class="field"><textarea name="address" rows="3"
      placeholder="Business address as it should print">{E(c.address)}</textarea></div>
    <div class="two">
      <div class="field"><input name="bank_name" value="{E(c.bank_name)}"
        placeholder="Bank and branch"></div>
      <div class="field"><input name="bank_account" value="{E(c.bank_account)}"
        placeholder="Account number"></div>
    </div>
    <div class="two">
      <div class="field"><input name="bank_ifsc" value="{E(c.bank_ifsc)}"
        placeholder="IFSC"></div>
      <div class="field"><input name="invoice_terms" value="{E(c.invoice_terms)}"
        placeholder="Terms printed at the foot"></div>
    </div>
    <button class="btn primary" type="submit">Save</button>
  </form></div>"""

    return (_head("Bills") + f'<div class="grid g4">{tiles}</div>'
            + gap_note + '<div style="height:16px"></div>'
            + raise_card + listed + identity)


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


# ==================================================================== the shell

def shell(c, account, active: str, body: str, *, counts: dict | None = None,
          stats: list | None = None, question: str = "", flash: str = "",
          flash_kind: str = "ok") -> str:
    """Nav, the question box, and one view's body.

    The question box sits in the header rather than on a screen of its own. That
    is the whole reason anybody will use it: a panel has to be remembered, a box
    in front of you does not.
    """
    counts = counts or {}
    hero_stats = stats or []
    nav = ""
    for key, label in views_for(c):
        n = counts.get(key, 0)
        hot = key == "today" and any(f.severity == "critical"
                                     for f in counts.get("_findings", []))
        badge = (f'<span class="n{" hot" if hot else ""}">{n}</span>') if n else ""
        nav += (f'<a href="/c/{c.slug}/{key}" class="{"on" if key == active else ""}">'
                f'{E(label)}{badge}</a>')
    nav += (f'<a href="/c/{c.slug}/setup" class="gear'
            f'{" on" if active == "setup" else ""}">⚙ Setup</a>')

    head = f"""<div class="wsbar">
  <a href="/c/{c.slug}/today" class="biz">{E(c.name)}
    <small>{E((c.industry or 'BUSINESS').upper())}</small></a>
  <form class="askform" method="post" action="/c/{c.slug}/ask">
    <input name="question" value="{E(question)}" autocomplete="off"
           placeholder="Ask anything about your business…" aria-label="Ask a question">
    <input type="hidden" name="from" value="{E(active)}">
  </form>
  <a class="btn ghost sm" href="/">All businesses</a>
</div>
<div class="wsnav">{nav}</div>"""

    # Vyuha staff inside somebody else's workspace must be able to see that they
    # are. It was on the old page and has to stay wherever the page went.
    support = ""
    if getattr(account, "is_master", False) and c.owner_id != account.id:
        support = ('<div class="support-bar">Vyuha support view — this is not '
                   'your data. The visit is recorded in the client\'s own '
                   'activity trail.</div>')

    return ui.layout(f"{c.name} · {active.title()}",
                     f"<style>{EXTRA}</style>{support}{head}"
                     f"{ui._flash(flash, flash_kind)}{body}",
                     active="clients", account=account, trade_key=c.trade,
                     full_bleed=ui.cover_hero(c, None, hero_stats))


def _answer_block(c, reply) -> str:
    """The agent's reply, shown above whatever screen you asked it from."""
    if reply is None:
        return ""
    if not reply.ok:
        return (f'<div class="card" style="margin-bottom:22px;'
                f'border-color:rgba(229,163,58,.32)">'
                f'<div style="font-size:15px;font-weight:700">Could not answer that</div>'
                f'<div class="muted" style="margin-top:8px">{E(reply.error)}</div></div>')

    deck = ""
    if reply.deck:
        deck = (f'<div class="deckout"><div>'
                f'<div style="font-size:15px;font-weight:700">Your deck is ready</div>'
                f'<div class="tiny" style="margin-top:5px">{E(reply.deck_label)}</div></div>'
                f'<div class="row" style="gap:8px">'
                f'<a class="btn sm primary" href="{E(reply.deck)}" target="_blank"'
                f' rel="noopener">Open the deck</a>'
                f'<a class="btn sm ghost" href="/c/{c.slug}/deck/pptx">PPTX</a>'
                f'<a class="btn sm ghost" href="/c/{c.slug}/deck/pdf">PDF</a></div></div>')

    consulted = ""
    if reply.source == "claude" and reply.used:
        words = {"query_sales": "your sales", "stock_report": "your stock",
                 "customer_detail": "that customer", "item_detail": "that item",
                 "compare_periods": "last month against this",
                 "financial_statements": "your statements",
                 "list_followups": "who owes you", "list_branches": "your branches",
                 "make_deck": "built a deck"}
        seen = []
        for name in reply.used:
            w = words.get(name, name)
            if w not in seen:
                seen.append(w)
        consulted = " · looked at " + ", ".join(seen[:4])

    return (f'<div class="card" style="margin-bottom:22px">'
            f'<div class="answer" style="margin-top:0">{E(reply.text)}</div>{deck}'
            f'<div class="tiny" style="margin-top:14px">'
            f'{E(reply.label)}{E(consulted)}</div></div>')


# ==================================================================== 1 · today

def today_view(c, account, book, ledger, org, invoices, settings, *,
               reply=None, question: str = "", flash: str = "",
               flash_kind: str = "ok") -> str:
    """What needs a decision, ranked, each with one button."""
    items = today_mod.findings(c, book, ledger, org, invoices)
    queue = followup.queue(c.slug, book)

    hello = (f'<div class="hello"><h1>{E(today_mod.greeting(c, account))}</h1>'
             f'<p>{E(("Nothing needs you today. " if not items else "")) }'
             f'{E(today_mod.summary_line(c, book, ledger))}</p></div>')

    if items:
        head = (f'<div class="hello"><h1>{E(today_mod.greeting(c, account))}</h1>'
                f'<p>{len(items)} thing(s) need you — {E(today_mod.minutes(items))}.'
                f' {E(today_mod.summary_line(c, book, ledger))}</p></div>')
        cards = "".join(
            f'<div class="td {E(f.severity)}"><div class="txt">'
            f'<div class="t">{E(f.title)}</div>'
            f'<div class="d">{E(f.detail)}</div></div>'
            f'<a class="btn sm{" primary" if f.severity == "critical" else ""} go"'
            f' href="{E(f.href)}">{E(f.action)}</a></div>' for f in items)
        body = head + f'<div class="todo">{cards}</div>'
    else:
        body = hello + ('<div class="allclear"><div class="big">All clear</div>'
                        '<div class="muted">Nothing is out of stock, nobody is '
                        'overdue, and no money is sitting idle. Close this and '
                        'get on with your day.</div></div>')

    # --- the chase list, in place, so "send reminders" resolves here
    chase = ""
    if queue:
        rows = ""
        for f in queue[:8]:
            text = followup.draft(f, c.name)
            if f.has_phone:
                from . import channels
                send = (f'<a class="btn sm wa" target="_blank" rel="noopener" '
                        f'href="{channels.whatsapp_link(f.party_phone, text)}">'
                        f'WhatsApp</a>')
            else:
                send = '<span class="pill dim">no number</span>'
            rows += (f'<div class="chase"><div><div class="who">{E(f.party)}</div>'
                     f'<div class="why">{E(f.reason)}</div></div>'
                     f'<div class="act">{send}'
                     f'<form method="post" action="/c/{c.slug}/followup">'
                     f'<input type="hidden" name="key" value="{E(f.key)}">'
                     f'<input type="hidden" name="status" value="done">'
                     f'<button class="btn sm ghost" type="submit">Done</button></form>'
                     f'<form method="post" action="/c/{c.slug}/followup">'
                     f'<input type="hidden" name="key" value="{E(f.key)}">'
                     f'<input type="hidden" name="status" value="snoozed">'
                     f'<input type="hidden" name="days" value="7">'
                     f'<button class="btn sm ghost" type="submit">Later</button>'
                     f'</form></div></div>')
        chase = (f'<div id="chase"></div>'
                 f'<div class="section-h"><h2>WHO TO CHASE</h2><div class="rule"></div>'
                 f'<span class="tiny">message already written</span></div>'
                 f'<div class="card">{rows}</div>')

    # --- the register, if this business keeps one
    register = people.today_register(org)
    marks = ""
    if register:
        rows = ""
        for r in register:
            buttons = "".join(
                f'<form method="post" action="/c/{c.slug}/staff/{E(r["id"])}/attendance">'
                f'<input type="hidden" name="state" value="{k}">'
                f'<button class="btn sm ghost" type="submit">{label}</button></form>'
                for k, label in [("present", "In"), ("half", "Half"),
                                 ("leave", "Leave"), ("absent", "Out")])
            rows += (f'<div class="chase"><div><div class="who">{E(r["name"])}</div>'
                     f'<div class="why">{E(r["role"])}'
                     f'{" · " + E(r["branch"]) if r["branch"] else ""} · '
                     f'<span class="st-{E(r["state"])}">{E(r["state"])}</span>'
                     f'</div></div><div class="act">{buttons}</div></div>')
        marks = (f'<div id="register"></div>'
                 f'<div class="section-h"><h2>TODAY&#39;S REGISTER</h2>'
                 f'<div class="rule"></div></div><div class="card">{rows}</div>')

    send = _send_block(c, settings, book, ledger)

    pos = money.position(book, ledger)
    last = c.latest
    if c.data_mode != "books" and last is not None and last.status == "ok":
        hero = [("Revenue", short(last.revenue)), ("Stock", short(last.stock_value)),
                ("Outstanding", short(last.outstanding)),
                ("Alerts", str(last.alert_count))]
    else:
        hero = [("Earned", short(book.earned)), ("In hand", short(pos["net"])),
                ("Owed to you", short(book.owed)), ("To chase", str(len(queue)))]

    return shell(c, account, "today",
                 _answer_block(c, reply) + body + send + chase + marks,
                 stats=hero,
                 counts={"today": len(items), "_findings": items,
                         "stock": len(books.summary(book)["low_stock"])
                                  + len(books.summary(book)["out_of_stock"])},
                 question=question, flash=flash, flash_kind=flash_kind)


# ===================================================================== 2 · sell

def sell_view(c, account, book, org, invoices, settings, *, reply=None,
              question: str = "", flash: str = "", flash_kind: str = "ok") -> str:
    """The daily job for a business that types entries: sell, bill, pay out."""
    entry = ui.books_tab(c, book)
    bills = _bills(c, book, invoices)
    spend = _money_out_form(c, org)
    body = (_answer_block(c, reply) + entry
            + f'<div id="bills"></div>{bills}' + spend)
    return shell(c, account, "sell", body,
                 counts={"sell": len([s for s in book.sales
                                      if s.date == date.today().isoformat()])},
                 question=question, flash=flash, flash_kind=flash_kind)


def _money_out_form(c, org) -> str:
    """Recording what left the business is daily entry, not a report."""
    branch_opts = "".join(f'<option value="{E(b.id)}">{E(b.name)}</option>'
                          for b in org.branches if b.active)
    cats = "".join(f'<option>{E(x)}</option>' for x in money.CATEGORIES)
    return f"""<div class="section-h"><h2>MONEY OUT</h2><div class="rule"></div>
  <span class="tiny">purchases, salary, rent — anything that left</span></div>
<div class="card">
  <form method="post" action="/c/{c.slug}/expense">
    <div class="two">
      <div class="field"><select name="category" aria-label="Category">{cats}</select></div>
      <div class="field"><input name="party" placeholder="Paid to (optional)"></div></div>
    <div class="two">
      <div class="field"><input name="amount" placeholder="Amount" inputmode="decimal" required></div>
      <div class="field"><input name="when" type="date" value="{date.today().isoformat()}"
        aria-label="Date"></div></div>
    <div class="two">
      <div class="field"><input name="due_date" type="date" aria-label="Due date">
        <div class="tiny" style="margin-top:5px">Due date — only if not paid yet</div></div>
      {f'<div class="field"><select name="branch" aria-label="Branch"><option value="">All branches</option>{branch_opts}</select></div>' if branch_opts else '<div></div>'}
    </div>
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
      <label class="chk"><input type="checkbox" name="unpaid" value="1">
        Not paid yet — this is a bill I owe</label>
      <button class="btn primary" type="submit">Record</button></div>
  </form></div>"""


# ====================================================================== 3 · data

def data_view(c, account, settings, activity_entries, *, reply=None,
              question: str = "", flash: str = "", flash_kind: str = "ok") -> str:
    """Send files — as many as you like, or point at a folder.

    One file at a time was the wrong shape for the job. A client's data arrives
    as fourteen months of exports, and reading them one by one and keeping the
    last reports whichever happened to be dropped last as the whole business.
    """
    last = c.latest

    drop = f"""<div class="card">
  <div style="font-size:16px;font-weight:700">Send files</div>
  <div class="tiny" style="margin:7px 0 16px">Select as many as you like — they
    are read together, not one at a time. Do not clean them up first.</div>
  <form method="post" action="/c/{c.slug}/upload" enctype="multipart/form-data" id="uf">
    <label class="drop" for="fi">
      <div class="big">Drop files here</div>
      <div class="muted">or click to choose — hold Ctrl or Shift to pick many</div>
      <div class="fmts"><span>.xlsx</span><span>.csv</span><span>.txt</span>
        <span>.pdf</span><span>.jpg</span><span>WhatsApp export</span></div>
      <input type="file" name="file" id="fi" multiple
             onchange="document.getElementById('picked').textContent =
                       this.files.length + ' file(s) chosen';
                       document.getElementById('go').hidden = false">
    </label>
    <div class="row" style="justify-content:space-between;margin-top:14px;
                            flex-wrap:wrap;gap:12px">
      <span class="tiny" id="picked">Nothing chosen yet</span>
      <button class="btn primary" type="submit" id="go" hidden>Read them</button>
    </div>
  </form></div>"""

    folder = "" if account.is_guest else f"""<div class="card" style="margin-top:16px">
  <div style="font-size:16px;font-weight:700">Or read a folder already on this machine</div>
  <div class="tiny" style="margin:7px 0 15px">Nobody wants to select ninety files
    in a dialog. Nothing is moved or changed — the folder is read where it sits.</div>
  <form method="post" action="/c/{c.slug}/folder">
    <div class="field"><input name="path" placeholder="C:\\Users\\you\\Desktop\\client files"
      autocomplete="off"></div>
    <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
      <label class="chk"><input type="checkbox" name="recursive" value="1" checked>
        Include sub-folders</label>
      <button class="btn" type="submit">Read the folder</button></div>
  </form></div>"""

    # --- what happened last time, file by file
    read = ""
    if last:
        if last.status == "ok":
            rows = "".join(
                f'<div class="chase"><div><div class="who">{E(n)}</div>'
                f'<div class="why">{E(n2)}</div></div></div>'
                for n, n2 in [(x.split(":", 1)[0], x.split(":", 1)[1].strip())
                              for x in last.source_notes if ":" in x][:10])
            plain = "".join(f'<div class="tiny" style="margin-top:7px">· {E(x)}</div>'
                            for x in last.source_notes if ":" not in x)
            skipped = ""
            if last.sheets_skipped:
                skipped = (f'<div class="tiny" style="margin-top:14px">'
                           f'Could not read: {E(", ".join(last.sheets_skipped[:8]))}'
                           + (f" and {len(last.sheets_skipped) - 8} more"
                              if len(last.sheets_skipped) > 8 else "") + "</div>")
            read = f"""<div class="card" style="margin-top:16px">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div><div style="font-size:16px;font-weight:700">What Vyuha read</div>
      <div class="tiny" style="margin-top:6px">{E(last.filename)} ·
        {E(", ".join(last.sheets_read) or "nothing named")} ·
        {last.alert_count} alert(s)</div></div>
    <div class="row" style="gap:9px">
      <a class="btn sm primary" href="/c/{c.slug}/dashboard" target="_blank"
         rel="noopener">Open the dashboard</a>
      <a class="btn sm ghost" href="/c/{c.slug}/export/pdf">PDF</a></div></div>
  {plain}{rows}{skipped}
  <div class="grid g4" style="margin-top:18px;gap:10px">
    <div><div class="tiny">REVENUE</div><div style="font-weight:700;margin-top:3px">
      {short(last.revenue)}</div></div>
    <div><div class="tiny">STOCK</div><div style="font-weight:700;margin-top:3px">
      {short(last.stock_value)}</div></div>
    <div><div class="tiny">OUTSTANDING</div><div style="font-weight:700;margin-top:3px">
      {short(last.outstanding)}</div></div>
    <div><div class="tiny">CONFIDENCE</div><div style="font-weight:700;margin-top:3px">
      {E(last.confidence)}</div></div></div></div>"""
        else:
            read = (f'<div class="card" style="margin-top:16px;'
                    f'border-color:rgba(240,90,98,.32)">'
                    f'<div style="font-size:16px;font-weight:700">'
                    f'That did not read</div>'
                    f'<div class="muted" style="margin-top:8px">{E(last.error)}</div>'
                    + "".join(f'<div class="tiny" style="margin-top:7px">· {E(n)}</div>'
                              for n in last.source_notes[:8]) + "</div>")

    # --- history
    history = ""
    if len(c.runs) > 1:
        rows = "".join(
            f'<div class="chase"><div><div class="who">{E(r.filename)}</div>'
            f'<div class="why">{E(r.uploaded_at[:16].replace("T", " "))} · '
            f'{E(", ".join(r.sheets_read) or "—")}</div></div>'
            f'<div class="act"><span class="pill '
            f'{"ok" if r.status == "ok" else "crit"}">'
            f'{E(r.confidence if r.status == "ok" else "failed")}</span></div></div>'
            for r in c.runs[1:9])
        history = (f'<div class="section-h"><h2>EARLIER</h2><div class="rule"></div>'
                   f'</div><div class="card">{rows}</div>')

    how = """<div class="note-line" style="margin-top:20px">Files are reconciled,
      not stacked. Sales from different months add up; a stock count is a
      snapshot, so the newest file wins rather than being added to the last one;
      and a row appearing in two overlapping exports is counted once.</div>"""

    return shell(c, account, "data",
                 _answer_block(c, reply) + drop + folder + read + history + how,
                 counts={"data": len(c.runs)},
                 question=question, flash=flash, flash_kind=flash_kind)


# ===================================================================== 4 · stock

def stock_view(c, account, book, org, settings, *, reply=None, question: str = "",
               flash: str = "", flash_kind: str = "ok") -> str:
    body = _answer_block(c, reply) + _stock(c, book, org)
    summary = books.summary(book)
    return shell(c, account, "stock", body,
                 counts={"stock": len(summary["low_stock"]) + len(summary["out_of_stock"])},
                 question=question, flash=flash, flash_kind=flash_kind)


# ===================================================================== 5 · money

def money_view(c, account, book, ledger, org, settings, *, period: str = "all",
               show: str = "summary", reply=None, question: str = "",
               flash: str = "", flash_kind: str = "ok") -> str:
    body = _answer_block(c, reply) + _money(c, book, ledger, org, period, show)
    # Who is selling is a performance question, so it belongs under Health
    # rather than on every view of the money screen.
    if show == "health":
        body += _selling(c, org, book)
    return shell(c, account, "money", body,
                 counts={"money": len([e for e in ledger.expenses if not e.paid])},
                 question=question, flash=flash, flash_kind=flash_kind)


def _selling(c, org, book) -> str:
    """Who is actually selling — a performance report, so it lives with the money."""
    perf = people.by_person(org, book)
    sellers = [r for r in perf[1:] if r["revenue"] or r["target"]]
    if not sellers:
        return ""
    unattributed = perf[0]["unattributed"]
    rows = ""
    for r in sellers:
        if r["target"]:
            pct = min(r["pct_of_target"] or 0, 100)
            bar = (f'<div class="tgt"><i class="{"hit" if r["on_track"] else ""}" '
                   f'style="width:{pct:.0f}%"></i></div>')
            goal = f'{r["pct_of_target"]:.0f}% of {short(r["target"])}'
        else:
            bar, goal = "", "no target"
        rows += (f'<div class="chase"><div style="min-width:150px">'
                 f'<div class="who">{E(r["name"])}</div>'
                 f'<div class="why">{E(r["role"])} · {E(r["branch"])}</div></div>'
                 f'<div style="flex:1;min-width:130px"><div class="tiny">{E(goal)}</div>'
                 f'{bar}</div>'
                 f'<div style="text-align:right"><div class="mono">{short(r["revenue"])}</div>'
                 f'<div class="why">{r["bills"]} bill(s)</div></div></div>')
    note = ("" if not unattributed else
            f'<div class="tiny" style="margin-top:14px">{short(unattributed)} of the '
            f'last 30 days has nobody recorded against it. Pick who sold it on the '
            f'entry form and these sharpen up.</div>')
    branches = people.performance(org, book)
    bysite = ""
    if org.has_branches:
        top = max((r["revenue"] for r in branches), default=1) or 1
        bysite = "".join(
            f'<div class="chase"><div style="min-width:150px">'
            f'<div class="who">{E(r["name"])}</div>'
            f'<div class="why">{r["bills"]} bill(s) · {r["customers"]} customer(s)</div></div>'
            f'<div style="flex:1;min-width:130px"><div class="meter">'
            f'<i style="width:{r["revenue"] / top * 100:.0f}%"></i></div></div>'
            f'<div style="text-align:right"><div class="mono">{short(r["revenue"])}</div>'
            f'<div class="why">{int(r["share"] * 100)}%</div></div></div>'
            for r in branches)
        bysite = (f'<div id="branches"></div><div class="section-h"><h2>BY BRANCH</h2>'
                  f'<div class="rule"></div></div><div class="card">{bysite}</div>')

    return (f'<div id="customers"></div>'
            f'<div class="section-h"><h2>WHO IS SELLING</h2><div class="rule"></div>'
            f'<span class="tiny">last 30 days</span></div>'
            f'<div class="card">{rows}{note}</div>{bysite}')


# ===================================================================== 6 · setup

def setup_view(c, account, book, org, settings, invoices, *, invite=None,
               fresh_pin: str = "", reply=None, question: str = "",
               flash: str = "", flash_kind: str = "ok") -> str:
    """Everything done once, in one place, as a list that empties.

    These were spread across four working screens as permanent form fields.
    Nobody touches them after the first week, and every one of them was taking
    up room on a screen used every day.
    """
    gaps = invoice.missing(c)
    unset_levels = [i for i in book.items if not i.reorder_level]
    checklist = [
        (bool(c.phone), "A WhatsApp number for this business",
         "Alerts and reminders go here"),
        (not gaps, "Invoice details",
         "Missing: " + ", ".join(gaps) if gaps else "GSTIN, address and state are set"),
        (not unset_levels, "Reorder levels",
         f"{len(unset_levels)} item(s) still at zero — Vyuha cannot warn you about those"
         if unset_levels else "Every item has a level"),
        (bool([s for s in org.staff if s.active]), "Your team",
         f"{len([s for s in org.staff if s.active])} person(s) added"),
    ]
    done = sum(1 for ok, _, _ in checklist if ok)
    lines = "".join(
        f'<div class="todoline"><span class="tick{" done" if ok else ""}">'
        f'{"✓" if ok else ""}</span>'
        f'<span class="lbl">{E(label)}<small>{E(note)}</small></span></div>'
        for ok, label, note in checklist)

    top = (f'<div class="card" style="margin-bottom:18px">'
           f'<div class="row" style="justify-content:space-between">'
           f'<div style="font-size:16px;font-weight:700">Setup</div>'
           f'<span class="pill {"ok" if done == len(checklist) else "warn"}">'
           f'{done} of {len(checklist)} done</span></div>'
           f'<div class="tiny" style="margin:8px 0 4px">Done once. Nothing here '
           f'needs looking at again.</div>{lines}</div>')

    # --- reorder levels, moved off the stock screen
    level_rows = "".join(
        f'<tr><td><b>{E(i.name)}</b></td><td class="num">{i.stock_qty:g}</td>'
        f'<td class="num"><input class="inline-in" name="lvl_{E(i.sku)}" '
        f'value="{i.reorder_level:g}" inputmode="decimal" '
        f'aria-label="Reorder level for {E(i.name)}"></td>'
        f'<td class="num">{rs(i.rate)}</td><td class="num">{rs(i.cost)}</td></tr>'
        for i in sorted(book.items, key=lambda x: x.name))
    levels = f"""<div class="card" style="padding:0;overflow:hidden">
  <div class="row" style="justify-content:space-between;padding:18px 20px">
    <div><div style="font-size:16px;font-weight:700">Stock levels</div>
      <div class="tiny" style="margin-top:5px">A level of 0 means Vyuha will never
        warn you about that item.</div></div></div>
  <form method="post" action="/c/{c.slug}/stock/reorder">
    <div class="scroll-x"><table class="mtable">
      <tr><th>Item</th><th class="num">In stock</th><th class="num">Reorder at</th>
          <th class="num">Sells at</th><th class="num">Costs</th></tr>
      {level_rows or '<tr><td colspan="5" class="tiny">No items yet.</td></tr>'}
    </table></div>
    <div style="padding:16px 20px"><button class="btn primary" type="submit">
      Save levels</button></div></form></div>"""

    people_setup = _people_setup(c, org)
    invoice_setup = _invoice_setup(c)
    details = _client_details(c)

    share = ui._share_card(c, invite, fresh_pin) if not account.is_guest else ""
    cover = f"""<div class="card">
  <div style="font-size:16px;font-weight:700">Cover photo</div>
  <div class="tiny" style="margin:7px 0 15px">Their own photo at the top of the
    workspace, instead of a stock trade picture.</div>
  <form method="post" action="/c/{c.slug}/cover" enctype="multipart/form-data" id="cvf">
    <label class="drop" for="cvi" style="padding:26px 18px">
      <div class="big">{'Change the photo' if c.has_cover else 'Add a photo'}</div>
      <div class="muted">JPG or PNG</div>
      <input type="file" name="file" id="cvi" accept="image/*"
             onchange="document.getElementById('cvf').submit()"></label>
  </form></div>"""

    body = (_answer_block(c, reply) + top
            + f'<div class="setup-grid">{details}{invoice_setup}</div>'
            + f'<div style="height:16px"></div>{people_setup}'
            + f'<div style="height:16px"></div>'
            + f'<div class="setup-grid">{share}{cover}</div>'
            + f'<div style="height:16px"></div>{levels}')
    return shell(c, account, "setup", body, question=question,
                 flash=flash, flash_kind=flash_kind)


def _client_details(c) -> str:
    return f"""<div class="card">
  <div style="font-size:16px;font-weight:700">This business</div>
  <div class="tiny" style="margin:7px 0 15px">Where alerts go, and when to warn you.</div>
  <form method="post" action="/c/{c.slug}/contact">
    <div class="two">
      <div class="field"><input name="contact" value="{E(c.contact)}"
        placeholder="Who to address"></div>
      <div class="field"><input name="phone" value="{E(c.phone)}"
        placeholder="WhatsApp number"></div></div>
    <div class="two">
      <div class="field"><input name="email" value="{E(c.email)}" placeholder="Email"></div>
      <div class="field"><input name="industry" value="{E(c.industry)}"
        placeholder="Trade"></div></div>
    <div class="two">
      <div class="field"><input name="dead_stock_days" value="{c.dead_stock_days}"
        inputmode="numeric">
        <div class="tiny" style="margin-top:5px">Days before stock counts as dead</div></div>
      <div class="field"><input name="low_cover_days" value="{c.low_cover_days}"
        inputmode="numeric">
        <div class="tiny" style="margin-top:5px">Warn when this many days of cover left</div></div>
    </div>
    <button class="btn primary" type="submit">Save</button></form></div>"""


def _invoice_setup(c) -> str:
    tpl = "".join(
        f'<label class="seg" style="margin:0 8px 8px 0">'
        f'<input type="radio" name="invoice_template" value="{E(k)}"'
        f'{" checked" if (c.invoice_template or "classic") == k else ""}>'
        f'<span>{E(label)}</span></label>'
        for k, (label, _w) in invoice.TEMPLATES.items())
    states = "".join(
        f'<option value="{E(k)}"{" selected" if c.state == k else ""}>{E(v)}</option>'
        for k, v in sorted(invoice.STATES.items(), key=lambda kv: kv[1]))
    return f"""<div class="card">
  <div style="font-size:16px;font-weight:700">What prints on your bills</div>
  <div class="tiny" style="margin:7px 0 15px">Without a GSTIN these print as a bill
    of supply, not a tax invoice.</div>
  <form method="post" action="/c/{c.slug}/invoice/identity">
    <div style="margin-bottom:12px">{tpl}</div>
    <div class="two">
      <div class="field"><input name="gstin" value="{E(c.gstin)}" placeholder="Your GSTIN"></div>
      <div class="field"><select name="state" aria-label="State">
        <option value="">Your state…</option>{states}</select></div></div>
    <div class="field"><textarea name="address" rows="2"
      placeholder="Address as it should print">{E(c.address)}</textarea></div>
    <div class="two">
      <div class="field"><input name="bank_name" value="{E(c.bank_name)}"
        placeholder="Bank and branch"></div>
      <div class="field"><input name="bank_account" value="{E(c.bank_account)}"
        placeholder="Account number"></div></div>
    <div class="two">
      <div class="field"><input name="bank_ifsc" value="{E(c.bank_ifsc)}" placeholder="IFSC"></div>
      <div class="field"><input name="invoice_terms" value="{E(c.invoice_terms)}"
        placeholder="Terms at the foot"></div></div>
    <button class="btn primary" type="submit">Save</button></form></div>"""


def _people_setup(c, org) -> str:
    branch_opts = "".join(f'<option value="{E(b.id)}">{E(b.name)}</option>'
                          for b in org.branches if b.active)
    branch_rows = "".join(
        f'<div class="chase"><div><div class="who">{E(b.name)}</div>'
        f'<div class="why">{E(b.place or "no place set")}'
        f'{" · " + E(b.manager) if b.manager else ""} · '
        f'{len(org.staff_at(b.id))} person(s)</div></div>'
        f'<form method="post" action="/c/{c.slug}/branch/{E(b.id)}/delete" class="act">'
        f'<button class="btn sm danger" type="submit">Close</button></form></div>'
        for b in org.branches if b.active)
    roles = "".join(f'<option value="{E(r)}">{E(r)} — sees {E(people.SEES[r][0])}</option>'
                    for r in people.ROLES)
    staff_rows = "".join(
        f'<div class="chase"><div><div class="who">{E(p.name)}</div>'
        f'<div class="why">{E(p.role)}'
        f'{" · " + E(org.name_of(p.branch)) if p.branch else ""}'
        f'{" · target " + short(p.target) if p.target else ""}</div></div>'
        f'<div class="act">'
        f'<form method="post" action="/c/{c.slug}/staff/{E(p.id)}/target" class="row" '
        f'style="gap:6px">'
        f'<input class="inline-in" name="target" value="{p.target:g}" '
        f'aria-label="Target for {E(p.name)}">'
        f'<input class="inline-in" name="commission" style="width:52px" '
        f'value="{p.commission_pct:g}" aria-label="Commission for {E(p.name)}">'
        f'<button class="btn sm ghost" type="submit">Set</button></form>'
        f'<form method="post" action="/c/{c.slug}/staff/{E(p.id)}/delete">'
        f'<button class="btn sm danger" type="submit">×</button></form></div></div>'
        for p in org.staff if p.active)

    return f"""<div class="setup-grid">
  <div class="card">
    <div style="font-size:16px;font-weight:700">Branches</div>
    <div class="tiny" style="margin:7px 0 4px">Closing one keeps its past sales.</div>
    {branch_rows or '<div class="muted" style="margin-top:12px">None yet.</div>'}
    <form method="post" action="/c/{c.slug}/branch" style="margin-top:16px">
      <div class="field"><input name="name" placeholder="Branch name" required></div>
      <div class="two">
        <div class="field"><input name="place" placeholder="Town or area"></div>
        <div class="field"><input name="manager" placeholder="Who runs it"></div></div>
      <button class="btn" type="submit">Add branch</button></form></div>
  <div class="card">
    <div style="font-size:16px;font-weight:700">Your team</div>
    <div class="tiny" style="margin:7px 0 4px">The role decides what they would see
      once staff logins exist.</div>
    {staff_rows or '<div class="muted" style="margin-top:12px">Nobody added yet.</div>'}
    <form method="post" action="/c/{c.slug}/staff" style="margin-top:16px">
      <div class="field"><input name="name" placeholder="Name" required></div>
      <div class="two">
        <div class="field"><select name="role" aria-label="Role">{roles}</select></div>
        <div class="field"><select name="branch" aria-label="Branch">
          <option value="">No branch</option>{branch_opts}</select></div></div>
      <div class="two">
        <div class="field"><input name="phone" placeholder="Phone"></div>
        <div class="field"><input name="target" placeholder="Monthly target"
          inputmode="decimal"></div></div>
      <button class="btn" type="submit">Add person</button></form></div></div>"""


def _send_block(c, settings, book, ledger) -> str:
    """The brief, the email and the exports.

    A daily action, so it lives on Today rather than behind a tab called
    "Alerts". Exactly one primary button: offering "Send now" and "Open
    WhatsApp" side by side made the operator decide which was the real one
    every single time.
    """
    from . import channels, exports
    last = c.latest
    if not (last and last.status == "ok"):
        return ""

    from vyuha import pipeline
    from pathlib import Path
    insights = None
    try:
        dash = Path(str(getattr(__import__("vyuha_platform.store", fromlist=["x"]),
                                "DASHBOARDS")))
    except Exception:
        dash = None

    # The brief is rendered from the alerts already stored on the run, so this
    # never re-runs the engine just to draw a screen.
    alerts = last.alerts or []
    if not alerts:
        return ""

    lines = [f"*{c.name}* — {len(alerts)} thing(s) to know", ""]
    for a in alerts[:5]:
        mark = {"critical": "!!", "warning": "!"}.get(a.get("severity", ""), "-")
        lines.append(f"{mark} {a.get('title', '')}")
        if a.get("detail"):
            lines.append(f"   {a['detail']}")
    text = "\n".join(lines)[:1024]

    if not c.phone:
        action = (f'<a class="btn" href="/c/{c.slug}/setup">'
                  f'Add their WhatsApp number →</a>')
        sub = "Alerts go to the number in Setup. There isn't one yet."
    elif settings.whatsapp_live:
        action = (f'<form method="post" action="/c/{c.slug}/whatsapp">'
                  f'<input type="hidden" name="text" value="{E(text)}">'
                  f'<button class="btn primary" type="submit">'
                  f'Send now to {E(c.name)} →</button></form>')
        sub = f"Goes straight to +{E(c.phone)}. One click, no new tab."
    else:
        action = (f'<a class="btn wa" target="_blank" rel="noopener" '
                  f'href="{channels.whatsapp_link(c.phone, text)}">'
                  f'Open WhatsApp to send →</a>')
        sub = ("No provider connected, so this opens WhatsApp with the brief "
               "typed out and you tap send.")

    mail = ""
    if c.email:
        subject = f"{c.name} — {len(alerts)} thing(s) to know"
        mail = (f'<a class="btn ghost sm" '
                f'href="{channels.mailto_link(c.email, subject, text)}">Email it</a>')

    return f"""<div id="send"></div>
<div class="section-h"><h2>SEND THE BRIEF</h2><div class="rule"></div></div>
<div class="card">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:14px">
    <div style="max-width:46ch"><div style="font-size:16px;font-weight:700">
      WhatsApp brief</div>
      <div class="tiny" style="margin-top:6px">{sub}</div></div>
    <div class="row" style="gap:8px">{action}{mail}</div></div>
  <pre class="msg" style="margin-top:16px">{E(text)}</pre>
  <div class="row" style="margin-top:14px;gap:8px;flex-wrap:wrap">
    <span class="tiny" style="margin-right:6px">Download:</span>
    <a class="btn sm ghost" href="/c/{c.slug}/export/pdf">PDF</a>
    <a class="btn sm ghost" href="/c/{c.slug}/export/pptx">PPTX</a>
    <a class="btn sm ghost" href="/c/{c.slug}/export/html">Dashboard</a>
    <a class="btn sm ghost" href="/c/{c.slug}/dashboard" target="_blank"
       rel="noopener">Open the dashboard ↗</a>
  </div></div>"""
