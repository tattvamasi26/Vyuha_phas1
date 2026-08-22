"""HTML for the platform shell.

Hand-rolled strings rather than a template engine — the same choice the engine's
``report.py`` makes, and for the same reason: one less dependency, and the
markup stays next to the logic that fills it.

Note this is the *platform* UI, served over localhost, so unlike the client
dashboard it may use a webfont CDN. The generated dashboard it embeds is still
strictly self-contained; that guarantee belongs to ``report.py`` and is tested.
"""

from __future__ import annotations

import html

from vyuha import fmt

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&'
    'family=Manrope:wght@500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" '
    'rel="stylesheet">'
)

CSS = """
:root{
  --bg:#07080b; --bg-2:#0c0e13; --card:#111319; --card-2:#151821;
  --line:rgba(255,255,255,.07); --line-2:rgba(255,255,255,.13);
  --ink:#f2f4f8; --ink-2:#9aa3b4; --ink-3:#5f6779;
  --accent:#7c5cff; --accent-2:#22d3ee; --ok:#34d399;
  --warn:#fbbf24; --crit:#fb5f6d;
  --r:18px; --shadow:0 24px 60px -20px rgba(0,0,0,.85);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--bg); color:var(--ink); min-height:100vh;
  font-family:'Manrope',system-ui,'Segoe UI',sans-serif; font-weight:600;
  -webkit-font-smoothing:antialiased;
}
body::before{
  content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
  background:
    radial-gradient(900px 500px at 12% -8%, rgba(124,92,255,.20), transparent 60%),
    radial-gradient(760px 460px at 92% 4%, rgba(34,211,238,.13), transparent 62%);
}
a{color:inherit;text-decoration:none}
.wrap{position:relative;z-index:1;max-width:1180px;margin:0 auto;padding:0 26px 90px}

/* ---------- top bar ---------- */
.top{
  position:sticky; top:0; z-index:40; backdrop-filter:blur(18px);
  background:rgba(7,8,11,.82); border-bottom:1px solid var(--line);
}
.top-in{max-width:1180px;margin:0 auto;padding:15px 26px;display:flex;align-items:center;gap:18px}
.brand{font-family:'Bebas Neue',sans-serif;font-size:29px;letter-spacing:.14em;line-height:1}
.brand span{background:linear-gradient(96deg,var(--accent),var(--accent-2));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.brand small{display:block;font-family:'Manrope';font-size:9px;font-weight:700;
  letter-spacing:.34em;color:var(--ink-3);margin-top:3px}
.top nav{margin-left:auto;display:flex;gap:6px;align-items:center}
.top nav a{padding:9px 15px;border-radius:11px;font-size:13.5px;color:var(--ink-2);
  border:1px solid transparent;transition:.18s}
.top nav a:hover{color:var(--ink);background:var(--card)}
.top nav a.on{color:var(--ink);background:var(--card);border-color:var(--line-2)}

/* ---------- hero ---------- */
.hero{padding:66px 0 34px;position:relative}
.eyebrow{font-size:10.5px;font-weight:800;letter-spacing:.34em;text-transform:uppercase;
  color:var(--accent-2);margin-bottom:16px}
h1.display{font-family:'Bebas Neue',sans-serif;font-size:clamp(52px,8.5vw,104px);
  line-height:.90;letter-spacing:.015em;margin:0 0 16px}
h1.display em{font-style:normal;background:linear-gradient(96deg,var(--accent),var(--accent-2));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.lede{color:var(--ink-2);font-size:16.5px;font-weight:500;max-width:66ch;line-height:1.62}

/* ---------- cards & grid ---------- */
.grid{display:grid;gap:16px}
.g3{grid-template-columns:repeat(auto-fill,minmax(268px,1fr))}
.g4{grid-template-columns:repeat(auto-fit,minmax(178px,1fr))}
.card{
  background:linear-gradient(168deg,var(--card),var(--card-2));
  border:1px solid var(--line); border-radius:var(--r); padding:22px;
  box-shadow:var(--shadow); transition:transform .2s, border-color .2s, box-shadow .2s;
}
@media (hover:hover){
  a.card:hover{transform:translateY(-4px);border-color:var(--line-2);
    box-shadow:0 30px 70px -22px rgba(124,92,255,.42)}
}
.stat .k{font-size:10.5px;font-weight:800;letter-spacing:.2em;text-transform:uppercase;color:var(--ink-3)}
.stat .v{font-family:'Bebas Neue',sans-serif;font-size:40px;line-height:1.05;margin-top:9px;letter-spacing:.01em}
.stat .v.sm{font-size:29px}
.muted{color:var(--ink-2);font-size:13.5px;font-weight:500;line-height:1.6}
.tiny{color:var(--ink-3);font-size:11.5px;font-weight:600}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}

/* ---------- client tiles ---------- */
.avatar{width:46px;height:46px;border-radius:13px;display:grid;place-items:center;
  font-family:'Bebas Neue',sans-serif;font-size:19px;letter-spacing:.06em;
  background:linear-gradient(140deg,var(--accent),var(--accent-2));color:#0b0b10;flex:none}
.row{display:flex;align-items:center;gap:14px}
.section-h{display:flex;align-items:baseline;gap:14px;margin:46px 0 18px}
.section-h h2{font-family:'Bebas Neue',sans-serif;font-size:27px;letter-spacing:.09em;margin:0}
.section-h .rule{flex:1;height:1px;background:var(--line)}

/* ---------- pills ---------- */
.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:999px;
  font-size:10.5px;font-weight:800;letter-spacing:.11em;text-transform:uppercase}
.pill.crit{background:rgba(251,95,109,.14);color:var(--crit);border:1px solid rgba(251,95,109,.3)}
.pill.warn{background:rgba(251,191,36,.13);color:var(--warn);border:1px solid rgba(251,191,36,.28)}
.pill.ok{background:rgba(52,211,153,.13);color:var(--ok);border:1px solid rgba(52,211,153,.28)}
.pill.dim{background:var(--card-2);color:var(--ink-3);border:1px solid var(--line)}

/* ---------- buttons ---------- */
.btn{display:inline-flex;align-items:center;gap:9px;padding:12px 20px;border-radius:12px;
  font-family:'Manrope';font-size:13.5px;font-weight:800;cursor:pointer;border:1px solid var(--line-2);
  background:var(--card);color:var(--ink);transition:.18s}
.btn:hover{border-color:rgba(255,255,255,.28);transform:translateY(-1px)}
.btn.primary{background:linear-gradient(96deg,var(--accent),var(--accent-2));color:#0a0a0f;border:0}
.btn.primary:hover{filter:brightness(1.08)}
.btn.wa{background:linear-gradient(96deg,#25D366,#0f9d58);color:#05130a;border:0}
.btn.ghost{background:transparent}
.btn.danger{color:var(--crit);border-color:rgba(251,95,109,.3);background:transparent}

/* ---------- forms ---------- */
label{display:block;font-size:10.5px;font-weight:800;letter-spacing:.19em;text-transform:uppercase;
  color:var(--ink-3);margin:0 0 8px}
input,select,textarea{width:100%;padding:13px 15px;border-radius:12px;background:#0a0c11;
  border:1px solid var(--line-2);color:var(--ink);font-family:'Manrope';font-size:14.5px;font-weight:600}
input:focus,select:focus,textarea:focus{outline:0;border-color:var(--accent);
  box-shadow:0 0 0 4px rgba(124,92,255,.16)}
.field{margin-bottom:17px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}

/* ---------- drop zone ---------- */
.drop{border:1.5px dashed var(--line-2);border-radius:var(--r);padding:42px 24px;text-align:center;
  background:rgba(255,255,255,.015);transition:.2s;cursor:pointer;display:block}
.drop:hover,.drop.hot{border-color:var(--accent);background:rgba(124,92,255,.07)}
.drop .big{font-family:'Bebas Neue',sans-serif;font-size:25px;letter-spacing:.07em;margin-bottom:8px}
.drop input[type=file]{display:none}

/* ---------- alerts ---------- */
.alert{border-left:3px solid var(--line-2);padding:17px 20px;border-radius:0 14px 14px 0;
  background:linear-gradient(96deg,rgba(255,255,255,.038),transparent);margin-bottom:11px}
.alert.critical{border-left-color:var(--crit)}
.alert.warning{border-left-color:var(--warn)}
.alert.info{border-left-color:var(--accent-2)}
.alert h4{margin:0 0 7px;font-size:15.5px;font-weight:800}
.ent{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px}
.ent span{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:8px;
  background:var(--card-2);border:1px solid var(--line);color:var(--ink-2)}

/* ---------- misc ---------- */
.frame{width:100%;height:78vh;border:1px solid var(--line);border-radius:var(--r);background:#fff}
pre.msg{white-space:pre-wrap;word-break:break-word;background:#0a0c11;border:1px solid var(--line-2);
  border-radius:14px;padding:19px;font-family:'JetBrains Mono',monospace;font-size:12.5px;
  font-weight:500;line-height:1.72;color:var(--ink-2);max-height:400px;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:10px;letter-spacing:.19em;text-transform:uppercase;color:var(--ink-3);
  padding:10px 12px;border-bottom:1px solid var(--line)}
td{padding:13px 12px;border-bottom:1px solid var(--line);font-weight:600;color:var(--ink-2)}
tr:last-child td{border-bottom:0}
.empty{text-align:center;padding:58px 22px;color:var(--ink-3)}
.empty .big{font-family:'Bebas Neue',sans-serif;font-size:29px;letter-spacing:.07em;
  color:var(--ink-2);margin-bottom:9px}
.flash{padding:13px 18px;border-radius:12px;margin-bottom:20px;font-size:13.5px;font-weight:700}
.flash.ok{background:rgba(52,211,153,.11);border:1px solid rgba(52,211,153,.3);color:var(--ok)}
.flash.bad{background:rgba(251,95,109,.11);border:1px solid rgba(251,95,109,.3);color:var(--crit)}
.fade{animation:fade .42s ease both}
@keyframes fade{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}
@media(max-width:720px){.two{grid-template-columns:1fr}.top nav a{padding:8px 10px;font-size:12.5px}}
"""

E = html.escape


def money(v) -> str:
    return fmt.rupees(v or 0)


def short(v) -> str:
    return fmt.rupees_short(v or 0)


def layout(title: str, body: str, active: str = "") -> str:
    def nav(href, label, key):
        return f'<a href="{href}" class="{"on" if key == active else ""}">{label}</a>'

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)} · Vyuha</title>{FONTS}<style>{CSS}</style></head><body>
<header class="top"><div class="top-in">
  <a href="/" class="brand"><span>VYUHA</span><small>OPERATIONS PLATFORM</small></a>
  <nav>{nav('/', 'Clients', 'clients')}{nav('/onboard', 'Onboard', 'onboard')}</nav>
</div></header>
<div class="wrap fade">{body}</div></body></html>"""


# --------------------------------------------------------------------------- pages

def home(clients, flash: str = "", flash_kind: str = "ok") -> str:
    runs = sum(len(c.runs) for c in clients)
    alerts = sum(r.alert_count for c in clients for r in c.runs)
    crit = sum(r.critical_count for c in clients for r in c.runs)

    banner = f'<div class="flash {flash_kind}">{E(flash)}</div>' if flash else ""

    if clients:
        tiles = []
        for c in clients:
            last = c.latest
            if last is None:
                badge, sub = '<span class="pill dim">No data yet</span>', "Waiting on their first file"
            elif last.status == "failed":
                badge, sub = '<span class="pill crit">Last run failed</span>', E(last.error[:70])
            else:
                kind = "crit" if last.critical_count else "ok"
                badge = f'<span class="pill {kind}">{last.alert_count} alert(s)</span>'
                sub = f"{short(last.revenue)} revenue · {short(last.outstanding)} outstanding"
            tiles.append(f"""
<a class="card" href="/c/{c.slug}">
  <div class="row"><div class="avatar">{E(c.initials)}</div>
    <div style="min-width:0">
      <div style="font-size:16px;font-weight:800">{E(c.name)}</div>
      <div class="tiny">{E(c.industry or 'Distributor')}</div>
    </div></div>
  <div style="margin-top:17px">{badge}</div>
  <div class="muted" style="margin-top:11px">{sub}</div>
</a>""")
        body_grid = f'<div class="grid g3">{"".join(tiles)}</div>'
    else:
        body_grid = """<div class="card empty"><div class="big">No clients yet</div>
<div class="muted">Onboard your first one — it takes about twenty seconds.</div>
<div style="margin-top:22px"><a class="btn primary" href="/onboard">Onboard a client</a></div></div>"""

    return layout("Clients", f"""
<section class="hero">
  <div class="eyebrow">Excel in · Intelligence out</div>
  <h1 class="display">Every client's<br>operation, <em>read.</em></h1>
  <p class="lede">Onboard a distributor, drop in the spreadsheet they already keep, and Vyuha
  works out what every sheet and column means — then hands back a dashboard and the short list
  of things costing them money.</p>
  <div style="margin-top:28px;display:flex;gap:11px;flex-wrap:wrap">
    <a class="btn primary" href="/onboard">Onboard a client</a>
  </div>
</section>
{banner}
<div class="grid g4">
  <div class="card stat"><div class="k">Clients</div><div class="v">{len(clients)}</div></div>
  <div class="card stat"><div class="k">Files read</div><div class="v">{runs}</div></div>
  <div class="card stat"><div class="k">Alerts raised</div><div class="v">{alerts}</div></div>
  <div class="card stat"><div class="k">Critical</div>
    <div class="v" style="color:var(--crit)">{crit}</div></div>
</div>
<div class="section-h"><h2>PORTFOLIO</h2><div class="rule"></div></div>
{body_grid}""", active="clients")


def onboard() -> str:
    return layout("Onboard", """
<section class="hero" style="padding-bottom:22px">
  <div class="eyebrow">Step 1 of 2</div>
  <h1 class="display">Onboard a <em>client.</em></h1>
  <p class="lede">Only the name is required. The phone number is what the WhatsApp brief gets
  sent to, and the thresholds decide when an alert fires — a spares dealer holding slow stock
  on purpose should not use an FMCG distributor's definition of "dead".</p>
</section>
<form method="post" action="/onboard" class="card" style="max-width:720px">
  <div class="field"><label>Business name *</label>
    <input name="name" required placeholder="Shree Engineering Traders" autofocus></div>
  <div class="two">
    <div class="field"><label>Contact person</label><input name="contact" placeholder="Ramesh Shah"></div>
    <div class="field"><label>Industry</label>
      <select name="industry">
        <option value="">Select…</option>
        <option>Industrial spares</option><option>FMCG distribution</option>
        <option>Pharma distribution</option><option>Electrical &amp; hardware</option>
        <option>Auto components</option><option>Chemicals</option>
        <option>Textiles</option><option>Other</option>
      </select></div>
  </div>
  <div class="two">
    <div class="field"><label>WhatsApp number</label>
      <input name="phone" placeholder="98765 43210" inputmode="tel">
      <div class="tiny" style="margin-top:7px">10 digits assumes +91. Include the country code otherwise.</div></div>
    <div class="field"><label>Email</label><input name="email" type="email" placeholder="owner@firm.in"></div>
  </div>
  <div class="two">
    <div class="field"><label>Dead stock after (days)</label>
      <input name="dead_stock_days" type="number" value="90" min="7" max="730"></div>
    <div class="field"><label>Low cover under (days)</label>
      <input name="low_cover_days" type="number" value="14" min="1" max="120"></div>
  </div>
  <div style="display:flex;gap:11px;margin-top:9px">
    <button class="btn primary" type="submit">Create workspace →</button>
    <a class="btn ghost" href="/">Cancel</a>
  </div>
</form>""", active="onboard")


def _alert_cards(alerts: list[dict]) -> str:
    if not alerts:
        return '<div class="card empty"><div class="big">Nothing needs attention</div>'\
               '<div class="muted">No alerts fired on the latest file.</div></div>'
    out = []
    for a in alerts:
        ents = "".join(f"<span>{E(str(e))}</span>" for e in a.get("entities", [])[:14])
        more = len(a.get("entities", [])) - 14
        if more > 0:
            ents += f'<span style="color:var(--ink-3)">+{more} more</span>'
        out.append(f"""
<div class="alert {E(a['severity'])}">
  <div class="row" style="justify-content:space-between;align-items:flex-start;gap:14px">
    <h4>{E(a['title'])}</h4>
    <span class="pill {'crit' if a['severity'] == 'critical' else 'warn'}">{E(a['severity'])}</span>
  </div>
  <div class="muted">{E(a['detail'])}</div>
  {f'<div class="ent">{ents}</div>' if ents else ''}
</div>""")
    return "".join(out)


def client_page(c, tab: str, flash: str = "", flash_kind: str = "ok",
                wa_text: str = "", wa_link: str = "", mail_link: str = "") -> str:
    last = c.latest
    banner = f'<div class="flash {flash_kind}">{E(flash)}</div>' if flash else ""

    def t(key, label):
        on = "primary" if tab == key else "ghost"
        return f'<a class="btn {on}" href="/c/{c.slug}?tab={key}">{label}</a>'

    tabs = f"""<div style="display:flex;gap:9px;flex-wrap:wrap;margin:26px 0 22px">
      {t('data', 'Data')}{t('dashboard', 'Dashboard')}{t('alerts', 'Alerts &amp; WhatsApp')}</div>"""

    if last and last.status == "ok":
        strip = f"""<div class="grid g4" style="margin-top:24px">
  <div class="card stat"><div class="k">Revenue</div><div class="v sm">{short(last.revenue)}</div></div>
  <div class="card stat"><div class="k">Stock value</div><div class="v sm">{short(last.stock_value)}</div></div>
  <div class="card stat"><div class="k">Outstanding</div><div class="v sm">{short(last.outstanding)}</div></div>
  <div class="card stat"><div class="k">Alerts</div>
    <div class="v sm" style="color:{'var(--crit)' if last.critical_count else 'var(--ok)'}">{last.alert_count}</div></div>
</div>"""
    else:
        strip = ""

    # ---- tab bodies
    if tab == "dashboard":
        if last and last.status == "ok" and last.dashboard:
            inner = f"""<div class="section-h"><h2>CLIENT DASHBOARD</h2><div class="rule"></div>
  <a class="btn ghost" href="/c/{c.slug}/dashboard" target="_blank">Open full screen ↗</a></div>
<iframe class="frame" src="/c/{c.slug}/dashboard"></iframe>
<div class="tiny" style="margin-top:12px">This file is fully self-contained — no scripts, no CDN,
no remote images. Forward it on WhatsApp and it opens on a phone with no internet.</div>"""
        else:
            inner = '<div class="card empty"><div class="big">No dashboard yet</div>'\
                    '<div class="muted">Upload a file on the Data tab first.</div></div>'

    elif tab == "alerts":
        alerts = last.alerts if (last and last.status == "ok") else []
        send = ""
        if alerts:
            wa_btn = (f'<a class="btn wa" href="{wa_link}" target="_blank">Send on WhatsApp →</a>'
                      if c.phone else
                      '<span class="pill dim">Add a phone number to enable WhatsApp</span>')
            mail_btn = (f'<a class="btn ghost" href="{mail_link}">Email it</a>' if c.email else "")
            send = f"""<div class="card" style="margin-top:22px">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div><div style="font-size:16px;font-weight:800">WhatsApp brief</div>
      <div class="tiny" style="margin-top:5px">{len(wa_text)} of 1024 characters ·
      opens WhatsApp with this already typed, you tap send</div></div>
    <div style="display:flex;gap:9px">{wa_btn}{mail_btn}</div>
  </div>
  <pre class="msg" style="margin-top:17px">{E(wa_text)}</pre></div>"""
        inner = f"""<div class="section-h"><h2>WHAT NEEDS ATTENTION</h2><div class="rule"></div></div>
{_alert_cards(alerts)}{send}"""

    else:  # data
        rows = []
        for r in c.runs:
            when = r.uploaded_at.replace("T", " ")[:16]
            if r.status == "ok":
                state = f'<span class="pill {"crit" if r.critical_count else "ok"}">{r.alert_count} alert(s)</span>'
                read = E(", ".join(r.sheets_read) or "—")
            else:
                state, read = '<span class="pill crit">failed</span>', E(r.error[:80])
            rows.append(f"""<tr><td class="mono tiny">{E(when)}</td>
  <td style="color:var(--ink)">{E(r.filename)}</td><td>{read}</td><td>{state}</td></tr>""")
        table = (f"""<table><thead><tr><th>When</th><th>File</th><th>Sheets understood</th>
<th>Result</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"""
                 if rows else
                 '<div class="empty"><div class="big">Nothing uploaded yet</div>'
                 '<div class="muted">Drop their spreadsheet above — no template, no column mapping.</div></div>')

        inner = f"""<form method="post" action="/c/{c.slug}/upload" enctype="multipart/form-data">
  <label class="drop" id="drop">
    <input type="file" name="file" id="file" accept=".xlsx,.xlsm,.csv,.xls" required>
    <div class="big">DROP THE CLIENT'S FILE</div>
    <div class="muted">.xlsx · .xlsm · .csv — exactly as they sent it.<br>
      Junk rows above the header, merged cells, ₹ formats and Grand Total rows are expected.</div>
    <div id="picked" class="tiny" style="margin-top:15px"></div>
  </label>
  <div style="margin-top:15px"><button class="btn primary" type="submit">Read this file →</button></div>
</form>
<div class="section-h"><h2>HISTORY</h2><div class="rule"></div></div>
<div class="card" style="padding:8px 10px">{table}</div>
<script>
  const d=document.getElementById('drop'), f=document.getElementById('file'), p=document.getElementById('picked');
  f.addEventListener('change',()=>{{p.textContent=f.files[0]?'Selected: '+f.files[0].name:'';}});
  ['dragenter','dragover'].forEach(e=>d.addEventListener(e,ev=>{{ev.preventDefault();d.classList.add('hot')}}));
  ['dragleave','drop'].forEach(e=>d.addEventListener(e,ev=>{{ev.preventDefault();d.classList.remove('hot')}}));
  d.addEventListener('drop',ev=>{{f.files=ev.dataTransfer.files;p.textContent='Selected: '+f.files[0].name;}});
</script>"""

    contact = " · ".join(x for x in [E(c.contact), E(c.phone), E(c.email)] if x) or "No contact details"
    return layout(c.name, f"""
<section class="hero" style="padding:44px 0 0">
  <div class="row" style="gap:18px">
    <div class="avatar" style="width:62px;height:62px;border-radius:17px;font-size:25px">{E(c.initials)}</div>
    <div><h1 class="display" style="font-size:clamp(38px,6vw,62px);margin:0">{E(c.name)}</h1>
      <div class="tiny" style="margin-top:7px">{E(c.industry or 'Distributor')} · {contact}</div></div>
  </div>
  {strip}
</section>
{tabs}{banner}{inner}
<div class="section-h"><h2>WORKSPACE</h2><div class="rule"></div></div>
<div class="card"><div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:14px">
  <div class="muted">Thresholds — dead stock after <b style="color:var(--ink)">{c.dead_stock_days}</b> days,
    low cover under <b style="color:var(--ink)">{c.low_cover_days}</b> days.</div>
  <form method="post" action="/c/{c.slug}/delete"
        onsubmit="return confirm('Delete {E(c.name)} and all their uploaded files?')">
    <button class="btn danger" type="submit">Delete client</button></form>
</div></div>""", active="clients")
