"""HTML for the platform shell.

Hand-rolled strings rather than a template engine — the same choice the engine's
``report.py`` makes, and for the same reason: one less dependency, and the
markup stays next to the logic that fills it.

This is the *platform* UI, served over localhost, so unlike the client dashboard
it may use a webfont CDN. The generated dashboard it embeds is still strictly
self-contained; that guarantee belongs to ``report.py`` and is tested.
"""

from __future__ import annotations

import html

from vyuha import fmt

from . import sources, theme

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&'
    'family=Manrope:wght@500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" '
    'rel="stylesheet">'
)

CSS = """
:root{
  --bg:#07080b; --card:#111319; --card-2:#151821;
  --line:rgba(255,255,255,.07); --line-2:rgba(255,255,255,.13);
  --ink:#f2f4f8; --ink-2:#9aa3b4; --ink-3:#5f6779;
  --accent:#7c5cff; --accent-2:#22d3ee; --ok:#34d399;
  --warn:#fbbf24; --crit:#fb5f6d;
  --r:18px; --shadow:0 24px 60px -20px rgba(0,0,0,.85);
}
*{box-sizing:border-box} html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--ink);min-height:100vh;
  font-family:'Manrope',system-ui,'Segoe UI',sans-serif;font-weight:600;
  -webkit-font-smoothing:antialiased}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(900px 500px at 12% -8%,rgba(124,92,255,.20),transparent 60%),
             radial-gradient(760px 460px at 92% 4%,rgba(34,211,238,.13),transparent 62%)}
a{color:inherit;text-decoration:none}
.wrap{position:relative;z-index:1;max-width:1180px;margin:0 auto;padding:0 26px 90px}

.top{position:sticky;top:0;z-index:40;backdrop-filter:blur(18px);
  background:rgba(7,8,11,.82);border-bottom:1px solid var(--line)}
.top-in{max-width:1180px;margin:0 auto;padding:15px 26px;display:flex;align-items:center;gap:18px}
.brand{font-family:'Bebas Neue',sans-serif;font-size:29px;letter-spacing:.14em;line-height:1}
.brand span{background:linear-gradient(96deg,var(--accent),var(--accent-2));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.brand small{display:block;font-family:'Manrope';font-size:9px;font-weight:700;
  letter-spacing:.34em;color:var(--ink-3);margin-top:3px}
.top nav{margin-left:auto;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.top nav a{padding:9px 15px;border-radius:11px;font-size:13.5px;color:var(--ink-2);
  border:1px solid transparent;transition:.18s}
.top nav a:hover{color:var(--ink);background:var(--card)}
.top nav a.on{color:var(--ink);background:var(--card);border-color:var(--line-2)}

.hero{padding:66px 0 34px;position:relative}
.eyebrow{font-size:10.5px;font-weight:800;letter-spacing:.34em;text-transform:uppercase;
  color:var(--accent-2);margin-bottom:16px}
h1.display{font-family:'Bebas Neue',sans-serif;font-size:clamp(52px,8.5vw,104px);
  line-height:.90;letter-spacing:.015em;margin:0 0 16px}
h1.display em{font-style:normal;background:linear-gradient(96deg,var(--accent),var(--accent-2));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.lede{color:var(--ink-2);font-size:16.5px;font-weight:500;max-width:66ch;line-height:1.62}

.grid{display:grid;gap:16px}
.g3{grid-template-columns:repeat(auto-fill,minmax(268px,1fr))}
.g4{grid-template-columns:repeat(auto-fit,minmax(178px,1fr))}
.card{background:linear-gradient(168deg,var(--card),var(--card-2));
  border:1px solid var(--line);border-radius:var(--r);padding:22px;
  box-shadow:var(--shadow);transition:transform .2s,border-color .2s,box-shadow .2s}
@media (hover:hover){a.card:hover{transform:translateY(-4px);border-color:var(--line-2);
  box-shadow:0 30px 70px -22px rgba(124,92,255,.42)}}
.stat .k{font-size:10.5px;font-weight:800;letter-spacing:.2em;text-transform:uppercase;color:var(--ink-3)}
.stat .v{font-family:'Bebas Neue',sans-serif;font-size:40px;line-height:1.05;margin-top:9px}
.stat .v.sm{font-size:29px}
.muted{color:var(--ink-2);font-size:13.5px;font-weight:500;line-height:1.6}
.tiny{color:var(--ink-3);font-size:11.5px;font-weight:600}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}

.avatar{width:46px;height:46px;border-radius:13px;display:grid;place-items:center;
  font-family:'Bebas Neue',sans-serif;font-size:19px;letter-spacing:.06em;
  background:linear-gradient(140deg,var(--accent),var(--accent-2));color:#0b0b10;flex:none}
.row{display:flex;align-items:center;gap:14px}
.section-h{display:flex;align-items:baseline;gap:14px;margin:46px 0 18px}
.section-h h2{font-family:'Bebas Neue',sans-serif;font-size:27px;letter-spacing:.09em;margin:0}
.section-h .rule{flex:1;height:1px;background:var(--line)}

.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:999px;
  font-size:10.5px;font-weight:800;letter-spacing:.11em;text-transform:uppercase}
.pill.crit{background:rgba(251,95,109,.14);color:var(--crit);border:1px solid rgba(251,95,109,.3)}
.pill.warn{background:rgba(251,191,36,.13);color:var(--warn);border:1px solid rgba(251,191,36,.28)}
.pill.ok{background:rgba(52,211,153,.13);color:var(--ok);border:1px solid rgba(52,211,153,.28)}
.pill.info{background:rgba(34,211,238,.12);color:var(--accent-2);border:1px solid rgba(34,211,238,.28)}
.pill.dim{background:var(--card-2);color:var(--ink-3);border:1px solid var(--line)}

.btn{display:inline-flex;align-items:center;gap:9px;padding:12px 20px;border-radius:12px;
  font-family:'Manrope';font-size:13.5px;font-weight:800;cursor:pointer;border:1px solid var(--line-2);
  background:var(--card);color:var(--ink);transition:.18s}
.btn:hover{border-color:rgba(255,255,255,.28);transform:translateY(-1px)}
.btn.primary{background:linear-gradient(96deg,var(--accent),var(--accent-2));color:#0a0a0f;border:0}
.btn.wa{background:linear-gradient(96deg,#25D366,#0f9d58);color:#05130a;border:0}
.btn.ghost{background:transparent}
.btn.danger{color:var(--crit);border-color:rgba(251,95,109,.3);background:transparent}
.btn.sm{padding:8px 14px;font-size:12px}

label{display:block;font-size:10.5px;font-weight:800;letter-spacing:.19em;text-transform:uppercase;
  color:var(--ink-3);margin:0 0 8px}
input,select,textarea{width:100%;padding:13px 15px;border-radius:12px;background:#0a0c11;
  border:1px solid var(--line-2);color:var(--ink);font-family:'Manrope';font-size:14.5px;font-weight:600}
textarea{font-family:'JetBrains Mono',monospace;font-size:12.5px;line-height:1.7;resize:vertical}
input:focus,select:focus,textarea:focus{outline:0;border-color:var(--accent);
  box-shadow:0 0 0 4px rgba(124,92,255,.16)}
.field{margin-bottom:17px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}

.drop{border:1.5px dashed var(--line-2);border-radius:var(--r);padding:42px 24px;text-align:center;
  background:rgba(255,255,255,.015);transition:.2s;cursor:pointer;display:block}
.drop:hover,.drop.hot{border-color:var(--accent);background:rgba(124,92,255,.07)}
.drop .big{font-family:'Bebas Neue',sans-serif;font-size:25px;letter-spacing:.07em;margin-bottom:8px}
.drop input[type=file]{display:none}
.fmts{display:flex;gap:7px;flex-wrap:wrap;justify-content:center;margin-top:15px}
.fmts span{font-size:10.5px;font-weight:800;letter-spacing:.08em;padding:4px 10px;border-radius:7px;
  background:var(--card-2);border:1px solid var(--line);color:var(--ink-2)}

.alert{border-left:3px solid var(--line-2);padding:17px 20px;border-radius:0 14px 14px 0;
  background:linear-gradient(96deg,rgba(255,255,255,.038),transparent);margin-bottom:11px}
.alert.critical{border-left-color:var(--crit)}
.alert.warning{border-left-color:var(--warn)}
.alert.info{border-left-color:var(--accent-2)}
.alert h4{margin:0 0 7px;font-size:15.5px;font-weight:800}
.ent{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px}
.ent span{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:8px;
  background:var(--card-2);border:1px solid var(--line);color:var(--ink-2)}

.trail{position:relative;padding-left:26px}
.trail::before{content:'';position:absolute;left:6px;top:6px;bottom:6px;width:1px;background:var(--line-2)}
.ev{position:relative;padding:11px 0}
.ev::before{content:'';position:absolute;left:-24px;top:17px;width:9px;height:9px;border-radius:50%;
  background:var(--ink-3);border:2px solid var(--bg)}
.ev.ok::before{background:var(--ok)} .ev.crit::before{background:var(--crit)}
.ev.warn::before{background:var(--warn)} .ev.info::before{background:var(--accent-2)}
.ev .hd{display:flex;align-items:baseline;gap:11px;flex-wrap:wrap}
.ev .hd b{font-size:13.5px}

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

/* ---------- cover hero: their business, not our branding ---------- */
.cover{position:relative;margin:0 -26px 0;min-height:340px;display:flex;align-items:flex-end;
  background-size:cover;background-position:center;overflow:hidden}
.cover::after{content:'';position:absolute;inset:0;
  background:linear-gradient(180deg,rgba(7,8,11,.30) 0%,rgba(7,8,11,.72) 55%,var(--bg) 100%)}
.cover-in{position:relative;z-index:2;width:100%;max-width:1180px;margin:0 auto;padding:34px 26px 26px}
.cover h1{font-family:'Bebas Neue',sans-serif;font-size:clamp(40px,6.4vw,72px);line-height:.95;
  margin:0;letter-spacing:.012em;text-shadow:0 3px 24px rgba(0,0,0,.65)}
.cover .sub{color:rgba(255,255,255,.82);font-size:14px;font-weight:600;margin-top:9px;
  text-shadow:0 2px 12px rgba(0,0,0,.7)}
.cover-stats{display:flex;gap:32px;flex-wrap:wrap;margin-top:22px}
.cover-stats div .k{font-size:9.5px;font-weight:800;letter-spacing:.22em;text-transform:uppercase;
  color:rgba(255,255,255,.66)}
.cover-stats div .v{font-family:'Bebas Neue',sans-serif;font-size:30px;line-height:1.1;margin-top:3px;
  text-shadow:0 2px 14px rgba(0,0,0,.6)}
.cover-edit{position:absolute;z-index:3;right:26px;top:20px}
.cover-edit input[type=file]{display:none}
.cover-edit label{margin:0;letter-spacing:normal;text-transform:none;font-size:12px;
  color:var(--ink);cursor:pointer;padding:8px 14px;border-radius:10px;font-weight:800;
  background:rgba(10,12,17,.72);border:1px solid rgba(255,255,255,.22);backdrop-filter:blur(8px)}
.cover-edit label:hover{background:rgba(10,12,17,.92)}

/* ---------- the big obvious actions ---------- */
.acts{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));margin:22px 0 8px}
.act{display:flex;align-items:center;gap:14px;padding:18px 20px;border-radius:15px;
  background:linear-gradient(168deg,var(--card),var(--card-2));border:1px solid var(--line);
  transition:.18s}
.act:hover{transform:translateY(-3px);border-color:var(--accent);
  box-shadow:0 22px 46px -20px rgba(0,0,0,.9)}
.act.on{border-color:var(--accent);background:linear-gradient(168deg,
  color-mix(in srgb,var(--accent) 16%,var(--card)),var(--card-2))}
.act .ic{width:40px;height:40px;border-radius:11px;display:grid;place-items:center;font-size:19px;
  background:color-mix(in srgb,var(--accent) 20%,transparent);
  border:1px solid color-mix(in srgb,var(--accent) 34%,transparent);flex:none}
.act .t{font-size:14.5px;font-weight:800;line-height:1.25}
.act .d{font-size:11.5px;color:var(--ink-3);font-weight:600;margin-top:2px}

/* ---------- badges on the top bar ---------- */
.who{display:flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;
  border:1px solid var(--line-2);background:var(--card);font-size:11px;font-weight:800;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2)}
.who .dot{width:7px;height:7px}
.trade-grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.trade-opt{position:relative;border-radius:15px;overflow:hidden;border:1px solid var(--line);
  cursor:pointer;min-height:118px;display:flex;align-items:flex-end;background-size:cover;
  background-position:center;transition:.18s}
.trade-opt:hover{transform:translateY(-3px);border-color:var(--line-2)}
.trade-opt input{position:absolute;opacity:0}
.trade-opt span{position:relative;z-index:2;padding:13px 15px;font-size:13.5px;font-weight:800;
  text-shadow:0 2px 10px rgba(0,0,0,.8)}
.trade-opt::after{content:'';position:absolute;inset:0;
  background:linear-gradient(180deg,transparent 30%,rgba(7,8,11,.85) 100%)}
.trade-opt:has(input:checked){border-color:var(--accent);
  box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 45%,transparent)}
.cap{display:flex;align-items:center;gap:10px;padding:11px 15px;border-radius:12px;
  border:1px solid var(--line);background:var(--card-2);margin-bottom:10px}
.dot{width:8px;height:8px;border-radius:50%;flex:none}
.dot.on{background:var(--ok);box-shadow:0 0 10px rgba(52,211,153,.7)}
.dot.off{background:var(--ink-3)}
@media(max-width:720px){.two{grid-template-columns:1fr}.top nav a{padding:8px 10px;font-size:12.5px}}
"""

E = html.escape


def short(v) -> str:
    return fmt.rupees_short(v or 0)


def layout(title: str, body: str, active: str = "", settings=None,
           trade_key: str = "general", full_bleed: str = "") -> str:
    """The shell.

    Navigation differs by install, and that difference is the product boundary:
    an operator sees a portfolio and can onboard parties; a tenant only ever
    sees their own business and never learns the other exists.
    """
    tenant = settings is not None and settings.is_tenant
    t = theme.trade(trade_key)

    def nav(href, label, key):
        return f'<a href="{href}" class="{"on" if key == active else ""}">{label}</a>'

    if tenant:
        links = (nav("/", "My business", "clients")
                 + nav("/activity", "History", "activity")
                 + nav("/settings", "Setup", "settings"))
        badge = f'<span class="who"><span class="dot on"></span>{E(settings.org_name or "My business")}</span>'
        wordmark = E(settings.org_name or "VYUHA")
        tagline = "POWERED BY VYUHA"
    else:
        links = (nav("/", "Clients", "clients") + nav("/onboard", "Onboard", "onboard")
                 + nav("/activity", "Activity", "activity")
                 + nav("/settings", "Settings", "settings"))
        badge = '<span class="who"><span class="dot on"></span>Operator</span>'
        wordmark, tagline = "VYUHA", "OPERATIONS PLATFORM"

    palette = (f":root{{--accent:{t['accent']};--accent-2:{t['accent2']}}}")

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)} · Vyuha</title>{FONTS}<style>{CSS}{palette}</style></head><body>
<header class="top"><div class="top-in">
  <a href="/" class="brand"><span>{wordmark}</span><small>{tagline}</small></a>
  <nav>{badge}{links}</nav>
</div></header>
{full_bleed}
<div class="wrap fade">{body}</div></body></html>"""


def cover_hero(c, settings, stats: list[tuple[str, str]]) -> str:
    """Full-bleed banner: their own photograph if they uploaded one, else the
    trade backdrop. Either way the first thing on screen is their business."""
    t = theme.trade(c.trade)
    bg = f"/c/{c.slug}/cover" if c.has_cover else t["backdrop"]
    tiles = "".join(f'<div><div class="k">{E(k)}</div><div class="v">{E(v)}</div></div>'
                    for k, v in stats)
    sub = " · ".join(x for x in [E(c.industry or t["label"]), E(c.contact), E(c.phone)] if x)
    return f"""<div class="cover" style="background-image:url('{bg}')">
  <form class="cover-edit" method="post" action="/c/{c.slug}/cover"
        enctype="multipart/form-data" id="cf">
    <input type="file" name="file" id="ci" accept="image/*"
           onchange="document.getElementById('cf').submit()">
    <label for="ci">{'Change photo' if c.has_cover else 'Add a photo'}</label>
  </form>
  <div class="cover-in">
    <h1>{E(c.name)}</h1>
    <div class="sub">{sub}</div>
    {f'<div class="cover-stats">{tiles}</div>' if tiles else ''}
  </div></div>"""


def actions(items: list[tuple[str, str, str, str, bool]]) -> str:
    """The options, always visible. (href, icon, title, detail, active)"""
    return '<div class="acts">' + "".join(
        f'<a class="act{" on" if on else ""}" href="{href}"><span class="ic">{ic}</span>'
        f'<span><span class="t">{E(title)}</span><span class="d">{E(detail)}</span></span></a>'
        for href, ic, title, detail, on in items) + "</div>"


def _flash(msg: str, kind: str) -> str:
    return f'<div class="flash {kind}">{E(msg)}</div>' if msg else ""


# ------------------------------------------------------------ self-serve setup

def choose_install() -> str:
    """Asked exactly once per install, and it decides what the product is.

    Vyuha's own copy runs a portfolio. A copy handed to a party we onboarded is
    that party's own tool — no portfolio, no other businesses, nothing to
    onboard. Getting this wrong the other way would show a client the existence
    of every other client, so it is a deliberate fork rather than a setting.
    """
    return layout("Set up", """
<section class="hero">
  <div class="eyebrow">First run</div>
  <h1 class="display">Who is this copy<br><em>for?</em></h1>
  <p class="lede">This is asked once. It decides whether this install manages a portfolio of
  businesses or is one business's own tool.</p>
</section>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-top:8px">
  <form method="post" action="/install" class="card">
    <input type="hidden" name="install" value="operator">
    <div class="ic" style="width:44px;height:44px;border-radius:12px;display:grid;place-items:center;
      font-size:20px;background:rgba(124,92,255,.2);border:1px solid rgba(124,92,255,.35)">◆</div>
    <div style="font-size:19px;font-weight:800;margin-top:15px">I run Vyuha</div>
    <p class="muted" style="margin:9px 0 18px">I onboard businesses onto this platform and manage
      several of them. I hold the WhatsApp, email and Claude credentials, and I can see every
      client's activity.</p>
    <button class="btn primary" type="submit">Set up as operator →</button>
  </form>
  <form method="post" action="/install" class="card">
    <input type="hidden" name="install" value="tenant">
    <div class="ic" style="width:44px;height:44px;border-radius:12px;display:grid;place-items:center;
      font-size:20px;background:rgba(52,211,153,.18);border:1px solid rgba(52,211,153,.35)">●</div>
    <div style="font-size:19px;font-weight:800;margin-top:15px">This is my own business</div>
    <p class="muted" style="margin:9px 0 18px">Somebody set this up for me. I only want to run my
      own shop — my stock, my sales, my customers. I am not managing anyone else.</p>
    <button class="btn primary" type="submit">Set up my business →</button>
  </form>
</div>
<div class="tiny" style="margin-top:24px">If you are installing this for a client, choose the
  second option on <b>their</b> machine — they will never see the portfolio or anyone else's data.</div>""")


def tenant_setup(preset: str = "") -> str:
    """A tenant's onboarding is about their own operation, never about clients."""
    tiles = "".join(
        f"""<label class="trade-opt" style="background-image:url('{t['backdrop']}')">
  <input type="radio" name="trade" value="{k}"{' checked' if k == (preset or 'nursery') else ''}>
  <span>{E(t['label'])}</span></label>""" for k, t in theme.TRADES.items())

    return layout("Set up", f"""
<section class="hero">
  <div class="eyebrow">Two questions</div>
  <h1 class="display">Set up your<br><em>business.</em></h1>
  <p class="lede">Then you are in. Nothing else is required — contact details, alert thresholds
  and a cover photo can all wait, or never happen.</p>
</section>
<form method="post" action="/setup" class="card" style="max-width:760px">
  <div class="field"><label>What is your business called?</label>
    <input name="name" required autofocus placeholder="Krishna Nursery &amp; Manure"></div>
  <div class="field"><label>What kind of business is it?</label>
    <div class="trade-grid" style="margin-top:4px">{tiles}</div>
    <div class="tiny" style="margin-top:10px">Sets the colours and the backdrop. You can put your
      own photo up later.</div></div>
  <div class="field"><label>How do you keep your records today?</label>
    <select name="data_mode">
      <option value="books">In a notebook — I will type entries in here</option>
      <option value="upload">In spreadsheets — I will upload the files</option>
    </select></div>
  <button class="btn primary" type="submit">Start →</button>
</form>""")


def trade_picker(current: str, name: str = "trade") -> str:
    return '<div class="trade-grid">' + "".join(
        f"""<label class="trade-opt" style="background-image:url('{t['backdrop']}')">
  <input type="radio" name="{name}" value="{k}"{' checked' if k == current else ''}>
  <span>{E(t['label'])}</span></label>""" for k, t in theme.TRADES.items()) + "</div>"


# ------------------------------------------------------------------- portfolio

def home(clients, settings, recent, counts, flash: str = "", flash_kind: str = "ok") -> str:
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
                if last.source_kind != "native":
                    badge += f' <span class="pill info">{E(last.source_kind)}</span>'
                sub = f"{short(last.revenue)} revenue · {short(last.outstanding)} outstanding"
            tiles.append(f"""
<a class="card" href="/c/{c.slug}">
  <div class="row"><div class="avatar">{E(c.initials)}</div>
    <div style="min-width:0"><div style="font-size:16px;font-weight:800">{E(c.name)}</div>
      <div class="tiny">{E(c.industry or 'Distributor')}</div></div></div>
  <div style="margin-top:17px">{badge}</div>
  <div class="muted" style="margin-top:11px">{sub}</div></a>""")
        grid = f'<div class="grid g3">{"".join(tiles)}</div>'
    else:
        grid = """<div class="card empty"><div class="big">No clients yet</div>
<div class="muted">Onboard your first one — it takes one field.</div>
<div style="margin-top:22px"><a class="btn primary" href="/onboard">Onboard a client</a></div></div>"""

    return layout("Clients", f"""
<section class="hero">
  <div class="eyebrow">Any data in · Intelligence out</div>
  <h1 class="display">Every client's<br>operation, <em>read.</em></h1>
  <p class="lede">Onboard a distributor, drop in whatever they already keep — a spreadsheet,
  a CSV, a PDF from their accountant, a photo of a handwritten register — and Vyuha works out
  what it means, then hands back a dashboard, a deck, and the short list of things costing
  them money.</p>
  <div style="margin-top:28px"><a class="btn primary" href="/onboard">Onboard a client</a></div>
</section>
{_flash(flash, flash_kind)}
<div class="grid g4">
  <div class="card stat"><div class="k">Clients</div><div class="v">{len(clients)}</div></div>
  <div class="card stat"><div class="k">Files read</div><div class="v">{counts['files']}</div></div>
  <div class="card stat"><div class="k">Briefs sent</div><div class="v">{counts['sends']}</div></div>
  <div class="card stat"><div class="k">Failures</div>
    <div class="v" style="color:{'var(--crit)' if counts['failures'] else 'var(--ink-3)'}">{counts['failures']}</div></div>
</div>
<div class="section-h"><h2>PORTFOLIO</h2><div class="rule"></div></div>
{grid}
<div class="section-h"><h2>RECENT ACTIVITY</h2><div class="rule"></div>
  <a class="btn ghost sm" href="/activity">See all →</a></div>
<div class="card">{_trail(recent) if recent else '<div class="muted">Nothing yet.</div>'}</div>""",
                  active="clients", settings=settings)


def onboard(settings, flash: str = "", flash_kind: str = "ok") -> str:
    live = settings.whatsapp_live
    note = ("A test message goes out the moment you save, so a wrong number is caught today."
            if live else
            "No WhatsApp provider is connected yet, so nothing will send automatically — "
            "you will get a tap-to-send link instead.")
    return layout("Onboard", f"""
<section class="hero" style="padding-bottom:22px">
  <div class="eyebrow">Takes about ten seconds</div>
  <h1 class="display">Onboard a <em>client.</em></h1>
  <p class="lede">Just the name and a WhatsApp number. Everything else — contact person,
  email, industry, alert thresholds — is optional and can be filled in later from their
  workspace, or never.</p>
</section>
{_flash(flash, flash_kind)}
<form method="post" action="/onboard" class="card" style="max-width:620px">
  <div class="field"><label>Business name</label>
    <input name="name" required autofocus placeholder="Shree Engineering Traders"></div>
  <div class="field"><label>WhatsApp number <span style="color:var(--ink-3)">— optional</span></label>
    <input name="phone" placeholder="98765 43210" inputmode="tel">
    <div class="tiny" style="margin-top:7px">10 digits assumes +91. {E(note)}</div></div>
  <div class="field"><label>What kind of business is it?</label>
    <div class="trade-grid" style="margin-top:4px">{trade_picker('distribution')}</div></div>
  <div class="field"><label>How does their data arrive?</label>
    <select name="data_mode">
      <option value="upload">They already keep files — I will upload them</option>
      <option value="books">They keep no files — enter sales and stock by hand</option>
    </select>
    <div class="tiny" style="margin-top:7px">Pick the second for a shop that writes bills in a
      notebook. You get entry forms instead of an upload box; everything downstream — dashboard,
      alerts, exports — is identical. This can be changed later.</div></div>
  <div style="display:flex;gap:11px;margin-top:9px">
    <button class="btn primary" type="submit">Create workspace →</button>
    <a class="btn ghost" href="/">Cancel</a></div>
</form>""", active="onboard", settings=settings)


# -------------------------------------------------------------------- activity

def _trail(entries) -> str:
    out = []
    for e in entries:
        who = f' <span class="tiny">· {E(e.client_name or e.client)}</span>' if e.client else ""
        chan = f' <span class="pill dim">{E(e.channel)}</span>' if e.channel else ""
        out.append(f"""<div class="ev {e.tone}">
  <div class="hd"><b>{E(e.label)}</b>{chan}<span class="tiny mono">{E(e.when)}</span>{who}</div>
  <div class="muted" style="margin-top:4px">{E(e.summary)}</div></div>""")
    return f'<div class="trail">{"".join(out)}</div>'


def activity(entries, counts, clients, sel_client: str, sel_kind: str, settings) -> str:
    opts = '<option value="">All clients</option>' + "".join(
        f'<option value="{c.slug}"{" selected" if c.slug == sel_client else ""}>{E(c.name)}</option>'
        for c in clients)
    from .ledger import KINDS
    kopts = '<option value="">All events</option>' + "".join(
        f'<option value="{k}"{" selected" if k == sel_kind else ""}>{E(v[0])}</option>'
        for k, v in KINDS.items())

    return layout("Activity", f"""
<section class="hero" style="padding:52px 0 22px">
  <div class="eyebrow">Traceability</div>
  <h1 class="display">Every file. <em>Every send.</em></h1>
  <p class="lede">Clients arrive by different routes and send different things. This is the
  record of what came in, how it was read, and what went back out — so "where did this number
  come from" is always one screen away.</p>
</section>
<div class="grid g4">
  <div class="card stat"><div class="k">Events</div><div class="v sm">{counts['total']}</div></div>
  <div class="card stat"><div class="k">Files read</div><div class="v sm">{counts['files']}</div></div>
  <div class="card stat"><div class="k">Runs</div><div class="v sm">{counts['runs']}</div></div>
  <div class="card stat"><div class="k">Failures</div>
    <div class="v sm" style="color:{'var(--crit)' if counts['failures'] else 'var(--ink-3)'}">{counts['failures']}</div></div>
</div>
<form method="get" action="/activity" class="card" style="margin-top:20px">
  <div class="two">
    <div><label>Client</label><select name="client" onchange="this.form.submit()">{opts}</select></div>
    <div><label>Event</label><select name="kind" onchange="this.form.submit()">{kopts}</select></div>
  </div>
</form>
<div class="section-h"><h2>TRAIL</h2><div class="rule"></div></div>
<div class="card">{_trail(entries) if entries else
    '<div class="empty"><div class="big">Nothing logged yet</div>'
    '<div class="muted">Onboard a client and upload a file.</div></div>'}</div>""",
                  active="activity", settings=settings)


# -------------------------------------------------------------------- settings

def settings(s, flash: str = "", flash_kind: str = "ok") -> str:
    from .config import mask

    def cap(on, label, detail):
        return (f'<div class="cap"><span class="dot {"on" if on else "off"}"></span>'
                f'<div><div style="font-size:13.5px;font-weight:800">{E(label)}</div>'
                f'<div class="tiny">{E(detail)}</div></div></div>')

    def sel(value, current):
        return " selected" if value == current else ""

    caps = (cap(s.whatsapp_live, "WhatsApp sending",
                f"Provider: {s.whatsapp_provider}. "
                + ("Messages send automatically." if s.whatsapp_live
                   else "Falls back to a tap-to-send wa.me link."))
            + cap(s.vision_live, "Images, scans and handwriting",
                  "Claude vision is connected." if s.vision_live
                  else "Add an Anthropic key to accept photos and scanned PDFs.")
            + cap(s.email_live, "Email sending",
                  f"Sends from {s.smtp_from}." if s.email_live
                  else "Add SMTP details, or use the draft and send it yourself."))

    return layout("Settings", f"""
<section class="hero" style="padding:52px 0 22px">
  <div class="eyebrow">Connections</div>
  <h1 class="display">What is <em>switched on.</em></h1>
  <p class="lede">Every capability degrades instead of breaking. Nothing here is required to
  use the platform — each credential just turns one more thing from manual into automatic.</p>
</section>
{_flash(flash, flash_kind)}
{caps}
<form method="post" action="/settings" class="card" style="margin-top:22px">
  <div class="section-h" style="margin-top:0"><h2>THIS INSTALL</h2><div class="rule"></div></div>
  <div class="cap"><span class="dot on"></span><div>
    <div style="font-size:13.5px;font-weight:800">
      {"Operator — you run Vyuha" if s.is_operator else "Single business — " + E(s.org_name or "your own shop")}</div>
    <div class="tiny">{"You manage a portfolio and can onboard businesses."
                       if s.is_operator else
                       "This copy only ever shows your business. There is no portfolio and "
                       "nothing to onboard."}</div></div></div>
  <div class="tiny" style="margin:10px 0 6px">Chosen at first run and deliberately not editable —
    switching would change who can see what. To change it, clear
    <span class="mono">vyuha_data/config.json</span>.</div>

  <div class="section-h"><h2>WHATSAPP</h2><div class="rule"></div></div>
  <div class="field"><label>Provider</label>
    <select name="whatsapp_provider">
      <option value="link"{sel('link', s.whatsapp_provider)}>Link only — I tap send myself</option>
      <option value="twilio"{sel('twilio', s.whatsapp_provider)}>Twilio — sandbox works immediately</option>
      <option value="meta"{sel('meta', s.whatsapp_provider)}>Meta Cloud API — needs template approval</option>
    </select></div>
  <div class="two">
    <div class="field"><label>Twilio account SID</label>
      <input name="twilio_sid" value="{E(s.twilio_sid)}" placeholder="AC..."></div>
    <div class="field"><label>Twilio auth token</label>
      <input name="twilio_token" placeholder="{E(mask(s.twilio_token)) or 'not set'}"></div>
  </div>
  <div class="field"><label>Twilio from-number</label>
    <input name="twilio_from" value="{E(s.twilio_from)}"></div>
  <div class="two">
    <div class="field"><label>Meta access token</label>
      <input name="meta_token" placeholder="{E(mask(s.meta_token)) or 'not set'}"></div>
    <div class="field"><label>Meta phone number ID</label>
      <input name="meta_phone_number_id" value="{E(s.meta_phone_number_id)}"></div>
  </div>
  <div class="field"><label>Meta template name <span style="color:var(--ink-3)">— blank sends free-form</span></label>
    <input name="meta_template" value="{E(s.meta_template)}">
    <div class="tiny" style="margin-top:7px">Meta only accepts free-form text within 24 hours of
      the client messaging you. Outside that window an approved template is required.</div></div>

  <div class="section-h"><h2>IMAGES &amp; HANDWRITING</h2><div class="rule"></div></div>
  <div class="field"><label>Anthropic API key</label>
    <input name="anthropic_key" placeholder="{E(mask(s.anthropic_key)) or 'not set'}">
    <div class="tiny" style="margin-top:7px">Needed to read photos, scanned PDFs and handwritten
      registers. Spreadsheets, CSVs and text PDFs never touch it.</div></div>

  <div class="section-h"><h2>EMAIL</h2><div class="rule"></div></div>
  <div class="two">
    <div class="field"><label>SMTP host</label>
      <input name="smtp_host" value="{E(s.smtp_host)}" placeholder="smtp.gmail.com"></div>
    <div class="field"><label>Port</label>
      <input name="smtp_port" type="number" value="{s.smtp_port}"></div>
  </div>
  <div class="two">
    <div class="field"><label>Username</label><input name="smtp_user" value="{E(s.smtp_user)}"></div>
    <div class="field"><label>Password</label>
      <input name="smtp_password" type="password" placeholder="{E(mask(s.smtp_password)) or 'not set'}"></div>
  </div>
  <div class="field"><label>Send from</label>
    <input name="smtp_from" value="{E(s.smtp_from)}" placeholder="you@firm.in"></div>

  <button class="btn primary" type="submit">Save settings</button>
  <div class="tiny" style="margin-top:12px">Leave a secret field blank to keep the stored value.</div>
</form>""", active="settings", settings=s)


# ------------------------------------------------------------------- workspace

def _alert_cards(alerts: list[dict]) -> str:
    if not alerts:
        return ('<div class="card empty"><div class="big">Nothing needs attention</div>'
                '<div class="muted">No alerts fired on the latest file.</div></div>')
    out = []
    for a in alerts:
        ents = "".join(f"<span>{E(str(e))}</span>" for e in a.get("entities", [])[:14])
        more = len(a.get("entities", [])) - 14
        if more > 0:
            ents += f'<span style="color:var(--ink-3)">+{more} more</span>'
        out.append(f"""<div class="alert {E(a['severity'])}">
  <div class="row" style="justify-content:space-between;align-items:flex-start;gap:14px">
    <h4>{E(a['title'])}</h4>
    <span class="pill {'crit' if a['severity'] == 'critical' else 'warn'}">{E(a['severity'])}</span></div>
  <div class="muted">{E(a['detail'])}</div>
  {f'<div class="ent">{ents}</div>' if ents else ''}</div>""")
    return "".join(out)


def _provenance(run) -> str:
    """Say plainly how this file was read — a photo is not a spreadsheet."""
    if run.source_kind == "native":
        return ""
    tone = {"high": "ok", "medium": "warn", "low": "crit"}.get(run.confidence, "dim")
    notes = "".join(f"<li>{E(n)}</li>" for n in run.source_notes)
    return f"""<div class="card" style="margin-bottom:18px;border-color:rgba(251,191,36,.25)">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:10px">
    <div style="font-size:15px;font-weight:800">{E(run.source_method)}</div>
    <span class="pill {tone}">{E(run.confidence)} confidence</span></div>
  <div class="muted" style="margin-top:9px">This file was not a spreadsheet. It was converted
    before the engine read it, so check the numbers against the source before acting on them.</div>
  {f'<ul class="muted" style="margin:10px 0 0 18px">{notes}</ul>' if notes else ''}</div>"""


def books_tab(c, book) -> str:
    """The entry screen for a business that keeps no spreadsheet at all."""
    from . import books as bk

    s = bk.summary(book)
    money = fmt.rupees

    def opt(values, current=""):
        return "".join(f'<option{" selected" if v == current else ""}>{E(v)}</option>'
                       for v in values)

    # ---- what he actually wants to know, in plain words
    tiles = f"""<div class="grid g4">
  <div class="card stat"><div class="k">Earned</div><div class="v sm">{short(s['earned'])}</div>
    <div class="tiny" style="margin-top:6px">{s['bills']} bill(s)</div></div>
  <div class="card stat"><div class="k">In hand</div><div class="v sm">{short(s['collected'])}</div>
    <div class="tiny" style="margin-top:6px">already paid</div></div>
  <div class="card stat"><div class="k">Still owed</div>
    <div class="v sm" style="color:{'var(--warn)' if s['owed'] else 'var(--ink-3)'}">{short(s['owed'])}</div>
    <div class="tiny" style="margin-top:6px">on credit</div></div>
  <div class="card stat"><div class="k">Profit</div>
    <div class="v sm" style="color:var(--ok)">{short(s['margin'])}</div>
    <div class="tiny" style="margin-top:6px">on what sold</div></div>
</div>"""

    warn = ""
    if s["out_of_stock"] or s["low_stock"] or s["never_sold"]:
        bits = []
        if s["out_of_stock"]:
            bits.append('<div class="alert critical"><h4>Finished — nothing left</h4>'
                        f'<div class="muted">{E(", ".join(i.name for i in s["out_of_stock"]))}</div></div>')
        if s["low_stock"]:
            bits.append('<div class="alert warning"><h4>Running low, order more</h4>'
                        + '<div class="muted">' + E(", ".join(
                            f"{i.name} ({i.stock_qty:g} {i.unit} left)" for i in s["low_stock"]))
                        + "</div></div>")
        if s["never_sold"]:
            bits.append('<div class="alert warning"><h4>Bought but never sold</h4>'
                        '<div class="muted">'
                        + E(", ".join(f"{i.name} — {money(i.value)} tied up"
                                      for i in s["never_sold"][:6]))
                        + "</div></div>")
        warn = f'<div class="section-h"><h2>WORTH KNOWING</h2><div class="rule"></div></div>{"".join(bits)}'

    # ---- entry forms
    item_opts = "".join(
        f'<option value="{E(i.sku)}">{E(i.name)} — {money(i.rate)} '
        f'({i.stock_qty:g} {E(i.unit)} left)</option>' for i in book.items)
    sale_form = (f"""<form method="post" action="/c/{c.slug}/book/sale" class="card">
  <div style="font-size:16px;font-weight:800;margin-bottom:14px">Record a sale</div>
  <div class="field"><label>What was sold</label>
    <select name="sku" required>{item_opts}</select></div>
  <div class="two">
    <div class="field"><label>How many</label>
      <input name="qty" type="number" step="any" min="0" value="1" required></div>
    <div class="field"><label>Price each <span style="color:var(--ink-3)">— blank uses the list price</span></label>
      <input name="rate" type="number" step="any" min="0" placeholder="auto"></div>
  </div>
  <div class="field"><label>Sold to</label>
    <input name="party" list="parties" placeholder="Walk-in customer">
    <datalist id="parties">{"".join(f'<option value="{E(p)}">' for p in book.customers())}</datalist></div>
  <div class="two">
    <div class="field"><label>Paid or credit</label>
      <select name="payment"><option value="paid">Paid now</option>
        <option value="credit">On credit</option></select></div>
    <div class="field"><label>Date</label><input name="when" type="date"></div>
  </div>
  <div class="field"><label>If credit, due by</label><input name="due_date" type="date"></div>
  <button class="btn primary" type="submit">Save sale</button>
</form>""" if book.items else
        '<div class="card empty"><div class="big">Add a product first</div>'
        '<div class="muted">Once something is in the list you can start recording sales.</div></div>')

    item_form = f"""<form method="post" action="/c/{c.slug}/book/item" class="card">
  <div style="font-size:16px;font-weight:800;margin-bottom:14px">Add stock</div>
  <div class="field"><label>What is it</label>
    <input name="name" required placeholder="Areca Palm 4ft">
    <div class="tiny" style="margin-top:7px">Adding something already on the list just tops up
      its quantity.</div></div>
  <div class="two">
    <div class="field"><label>Type</label><select name="category">{opt(bk.CATEGORIES)}</select></div>
    <div class="field"><label>Sold by</label><select name="unit">{opt(bk.UNITS)}</select></div>
  </div>
  <div class="two">
    <div class="field"><label>Your selling price</label>
      <input name="rate" type="number" step="any" min="0" required placeholder="450"></div>
    <div class="field"><label>What it cost you</label>
      <input name="cost" type="number" step="any" min="0" placeholder="260"></div>
  </div>
  <div class="two">
    <div class="field"><label>How many you have</label>
      <input name="stock_qty" type="number" step="any" min="0" required placeholder="40"></div>
    <div class="field"><label>Warn me when below</label>
      <input name="reorder_level" type="number" step="any" min="0" placeholder="10"></div>
  </div>
  <button class="btn primary" type="submit">Add to stock</button>
</form>"""

    # ---- what is left
    if book.items:
        rows = []
        for i in sorted(book.items, key=lambda x: (x.category, x.name)):
            if i.stock_qty <= 0:
                tag = '<span class="pill crit">finished</span>'
            elif i.low:
                tag = '<span class="pill warn">low</span>'
            else:
                tag = '<span class="pill ok">in stock</span>'
            rows.append(f"""<tr><td style="color:var(--ink)">{E(i.name)}</td>
  <td class="tiny">{E(i.category)}</td>
  <td class="mono">{i.stock_qty:g} {E(i.unit)}</td>
  <td class="mono">{money(i.rate)}</td><td>{tag}</td>
  <td><form method="post" action="/c/{c.slug}/book/item/{E(i.sku)}/delete"
        onsubmit="return confirm('Remove {E(i.name)}?')">
      <button class="btn danger sm" type="submit">Remove</button></form></td></tr>""")
        stock_table = f"""<table><thead><tr><th>Item</th><th>Type</th><th>Left</th>
<th>Price</th><th></th><th></th></tr></thead><tbody>{''.join(rows)}</tbody></table>"""
    else:
        stock_table = '<div class="muted">Nothing added yet.</div>'

    # ---- what sold
    if book.sales:
        rows = []
        for sale in reversed(book.sales[-40:]):
            paid = ('<span class="pill ok">paid</span>' if sale.paid else
                    f'<form method="post" action="/c/{c.slug}/book/sale/{E(sale.id)}/paid" '
                    f'style="display:inline"><button class="btn sm" type="submit">Mark paid</button></form>')
            rows.append(f"""<tr><td class="mono tiny">{E(sale.date)}</td>
  <td class="mono tiny">{E(sale.id)}</td>
  <td style="color:var(--ink)">{E(sale.item)}</td>
  <td class="mono">{sale.qty:g}</td>
  <td>{E(sale.party)}</td>
  <td class="mono" style="color:var(--ink)">{money(sale.amount)}</td>
  <td>{paid}</td>
  <td><form method="post" action="/c/{c.slug}/book/sale/{E(sale.id)}/delete"
        onsubmit="return confirm('Delete {E(sale.id)}? The stock goes back.')">
      <button class="btn danger sm" type="submit">×</button></form></td></tr>""")
        sales_table = f"""<table><thead><tr><th>Date</th><th>Bill</th><th>Item</th><th>Qty</th>
<th>Customer</th><th>Amount</th><th></th><th></th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>"""
    else:
        sales_table = '<div class="muted">No sales recorded yet.</div>'

    best = "".join(f'<span>{E(n)} — {q:g} sold</span>' for n, q in s["best_sellers"])

    return f"""{tiles}{warn}
<div class="section-h"><h2>ADD AN ENTRY</h2><div class="rule"></div></div>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(330px,1fr))">
  {sale_form}{item_form}</div>
<div class="section-h"><h2>WHAT IS LEFT</h2><div class="rule"></div>
  <span class="tiny">{money(s['stock_value'])} tied up in stock</span></div>
<div class="card" style="padding:8px 10px">{stock_table}</div>
<div class="section-h"><h2>WHAT SOLD</h2><div class="rule"></div>
  <span class="tiny">{s['customers']} customer(s)</span></div>
<div class="card" style="padding:8px 10px">{sales_table}</div>
{f'<div class="section-h"><h2>BEST SELLERS</h2><div class="rule"></div></div><div class="card"><div class="ent">{best}</div></div>' if best else ''}
<div class="tiny" style="margin-top:22px">Every entry updates the dashboard straight away —
  the same one an uploaded spreadsheet produces.</div>"""


def client_page(c, tab: str, settings, activity_entries, flash: str = "", flash_kind: str = "ok",
                wa_text: str = "", wa_link: str = "", mail_link: str = "",
                email_subject: str = "", email_body: str = "", book=None) -> str:
    last = c.latest
    manual = c.data_mode == "books"
    if manual and tab == "data":
        tab = "books"
    has_data = bool(last and last.status == "ok")

    # Every option, spelled out, on screen. No hunting through tab labels.
    entry = (("books", "✎", "Enter sales & stock", "Type in what sold and what came in")
             if manual else
             ("data", "⬆", "Add data", "Spreadsheet, PDF, or a photo of the page"))
    items = [
        (f"/c/{c.slug}?tab={entry[0]}", entry[1], entry[2], entry[3], tab == entry[0]),
        (f"/c/{c.slug}?tab=dashboard", "▦", "See the dashboard",
         "Charts and the full picture" if has_data else "Nothing to show yet",
         tab == "dashboard"),
        (f"/c/{c.slug}?tab=alerts", "➤", "Send & download",
         f"{last.alert_count} alert(s) ready" if has_data else "Add data first",
         tab == "alerts"),
        (f"/c/{c.slug}?tab=settings", "⚙", "Setup",
         "Contact, photo, and when to warn you", tab == "settings"),
    ]
    tabs = actions(items)

    stats: list[tuple[str, str]] = []
    if has_data:
        stats = [("Revenue", short(last.revenue)), ("Stock value", short(last.stock_value)),
                 ("Outstanding", short(last.outstanding)),
                 ("Alerts", str(last.alert_count))]
    strip = ""

    # ---- tab bodies
    if tab == "books":
        inner = books_tab(c, book) if book is not None else '<div class="muted">No book.</div>'

    elif tab == "dashboard":
        if last and last.status == "ok" and last.dashboard:
            inner = f"""<div class="section-h" style="margin-top:0"><h2>CLIENT DASHBOARD</h2>
  <div class="rule"></div><a class="btn ghost sm" href="/c/{c.slug}/dashboard" target="_blank">Full screen ↗</a></div>
{_provenance(last)}
<iframe class="frame" src="/c/{c.slug}/dashboard"></iframe>
<div class="tiny" style="margin-top:12px">Self-contained — no scripts, no CDN, no remote images.
  Forward it on WhatsApp and it opens on a phone with no internet.</div>"""
        else:
            inner = ('<div class="card empty"><div class="big">No dashboard yet</div>'
                     '<div class="muted">Upload something on the Data tab first.</div></div>')

    elif tab == "alerts":
        alerts = last.alerts if (last and last.status == "ok") else []
        blocks = ""
        if alerts:
            wa_btn = (f'<a class="btn wa" href="{wa_link}" target="_blank">Open in WhatsApp →</a>'
                      if c.phone else
                      '<span class="pill dim">Add a number on the Details tab</span>')
            auto = (f'<form method="post" action="/c/{c.slug}/whatsapp" style="display:inline">'
                    f'<input type="hidden" name="text" value="{E(wa_text)}">'
                    f'<button class="btn primary" type="submit">Send automatically</button></form>'
                    if settings.whatsapp_live and c.phone else "")
            blocks += f"""<div class="card" style="margin-top:22px">
  <div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:12px">
    <div><div style="font-size:16px;font-weight:800">WhatsApp brief</div>
      <div class="tiny" style="margin-top:5px">{len(wa_text)} of 1024 characters</div></div>
    <div style="display:flex;gap:9px;flex-wrap:wrap">{auto}{wa_btn}</div></div>
  <pre class="msg" style="margin-top:17px">{E(wa_text)}</pre></div>"""

            send_btn = ('<button class="btn primary" type="submit">Send email</button>'
                        if settings.email_live and c.email else
                        f'<a class="btn ghost" href="{mail_link}">Open in mail app</a>'
                        if c.email else
                        '<span class="pill dim">Add an email on the Details tab</span>')
            blocks += f"""<div class="card" style="margin-top:16px">
  <div style="font-size:16px;font-weight:800;margin-bottom:14px">Email</div>
  <form method="post" action="/c/{c.slug}/email">
    <div class="field"><label>Subject</label>
      <input name="subject" value="{E(email_subject)}"></div>
    <div class="field"><label>Body</label>
      <textarea name="body" rows="12">{E(email_body)}</textarea></div>
    {send_btn}
    <span class="tiny" style="margin-left:10px">The dashboard is attached automatically.</span>
  </form></div>"""

            blocks += f"""<div class="card" style="margin-top:16px">
  <div style="font-size:16px;font-weight:800">Take it into a meeting</div>
  <div class="muted" style="margin-top:7px">Same numbers, three formats.</div>
  <div style="display:flex;gap:9px;margin-top:15px;flex-wrap:wrap">
    <a class="btn" href="/c/{c.slug}/export/pdf">Download PDF</a>
    <a class="btn" href="/c/{c.slug}/export/pptx">Download deck</a>
    <a class="btn ghost" href="/c/{c.slug}/export/html">Download dashboard</a>
  </div></div>"""

        inner = (f'<div class="section-h" style="margin-top:0"><h2>WHAT NEEDS ATTENTION</h2>'
                 f'<div class="rule"></div></div>{_alert_cards(alerts)}{blocks}')

    elif tab == "settings":
        inner = f"""<div class="section-h" style="margin-top:0"><h2>DETAILS</h2><div class="rule"></div></div>
<form method="post" action="/c/{c.slug}/contact" class="card">
  <div class="two">
    <div class="field"><label>Contact person</label>
      <input name="contact" value="{E(c.contact)}" placeholder="Ramesh Shah"></div>
    <div class="field"><label>Industry</label>
      <input name="industry" value="{E(c.industry)}" placeholder="Industrial spares"></div>
  </div>
  <div class="two">
    <div class="field"><label>WhatsApp number</label>
      <input name="phone" value="{E(c.phone)}" inputmode="tel"></div>
    <div class="field"><label>Email</label>
      <input name="email" type="email" value="{E(c.email)}"></div>
  </div>
  <div class="two">
    <div class="field"><label>Dead stock after (days)</label>
      <input name="dead_stock_days" type="number" value="{c.dead_stock_days}" min="7" max="730">
      <div class="tiny" style="margin-top:7px">A spares dealer holding slow stock on purpose
        should not use an FMCG distributor's definition of dead.</div></div>
    <div class="field"><label>Low cover under (days)</label>
      <input name="low_cover_days" type="number" value="{c.low_cover_days}" min="1" max="120"></div>
  </div>
  <div class="field"><label>Look &amp; feel</label>
    {trade_picker(c.trade)}
    <div class="tiny" style="margin-top:10px">Sets the colours and the backdrop behind the name.
      Use <b>Add a photo</b> at the top right of the banner to put a real picture up instead.</div></div>
  <button class="btn primary" type="submit">Save</button>
</form>
<div class="section-h"><h2>THIS CLIENT'S TRAIL</h2><div class="rule"></div></div>
<div class="card">{_trail(activity_entries) if activity_entries else '<div class="muted">Nothing yet.</div>'}</div>
<div class="section-h"><h2>DANGER</h2><div class="rule"></div></div>
<div class="card"><div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:14px">
  <div class="muted">Deletes the workspace, every uploaded file and every generated dashboard.</div>
  <form method="post" action="/c/{c.slug}/delete"
        onsubmit="return confirm('Delete {E(c.name)} and everything they sent?')">
    <button class="btn danger" type="submit">Delete client</button></form>
</div></div>"""

    else:  # data
        rows = []
        for r in c.runs:
            when = r.uploaded_at.replace("T", " ")[:16]
            if r.status == "ok":
                state = f'<span class="pill {"crit" if r.critical_count else "ok"}">{r.alert_count} alert(s)</span>'
                read = E(", ".join(r.sheets_read) or "—")
            else:
                state, read = '<span class="pill crit">failed</span>', E(r.error[:70])
            how = ('<span class="pill dim">spreadsheet</span>' if r.source_kind == "native"
                   else f'<span class="pill info">{E(r.source_kind)}</span>')
            rows.append(f"""<tr><td class="mono tiny">{E(when)}</td>
  <td style="color:var(--ink)">{E(r.filename)}</td><td>{how}</td>
  <td>{read}</td><td>{state}</td></tr>""")
        table = (f"""<table><thead><tr><th>When</th><th>File</th><th>How it was read</th>
<th>Understood</th><th>Result</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"""
                 if rows else
                 '<div class="empty"><div class="big">Nothing uploaded yet</div>'
                 '<div class="muted">Drop anything above — no template, no column mapping.</div></div>')

        vision_note = ("" if settings.vision_live else
                       '<div class="tiny" style="margin-top:10px;color:var(--warn)">'
                       'Photos and scanned PDFs need a Claude API key — add one in Settings.</div>')
        exts = " ".join(f"<span>{e}</span>" for e in sorted(sources.ACCEPTED))

        inner = f"""{_provenance(last) if last and last.status == 'ok' else ''}
<form method="post" action="/c/{c.slug}/upload" enctype="multipart/form-data">
  <label class="drop" id="drop">
    <input type="file" name="file" id="file" required
           accept=".xlsx,.xlsm,.csv,.txt,.tsv,.pdf,.png,.jpg,.jpeg,.webp,.gif">
    <div class="big">DROP ANYTHING THEY SEND YOU</div>
    <div class="muted">A spreadsheet, a CSV, a PDF from their accountant, or a photo of a
      handwritten register. Junk rows, merged cells and ₹ formats are expected.</div>
    <div class="fmts">{exts}</div>
    <div id="picked" class="tiny" style="margin-top:15px"></div>
  </label>
  <div style="margin-top:15px"><button class="btn primary" type="submit">Read this file →</button></div>
  {vision_note}
</form>
<div class="section-h"><h2>HISTORY</h2><div class="rule"></div></div>
<div class="card" style="padding:8px 10px">{table}</div>
<script>
  const d=document.getElementById('drop'),f=document.getElementById('file'),p=document.getElementById('picked');
  f.addEventListener('change',()=>{{p.textContent=f.files[0]?'Selected: '+f.files[0].name:'';}});
  ['dragenter','dragover'].forEach(e=>d.addEventListener(e,ev=>{{ev.preventDefault();d.classList.add('hot')}}));
  ['dragleave','drop'].forEach(e=>d.addEventListener(e,ev=>{{ev.preventDefault();d.classList.remove('hot')}}));
  d.addEventListener('drop',ev=>{{f.files=ev.dataTransfer.files;p.textContent='Selected: '+f.files[0].name;}});
</script>"""

    return layout(c.name, f"{tabs}{_flash(flash, flash_kind)}{inner}",
                  active="clients", settings=settings, trade_key=c.trade,
                  full_bleed=cover_hero(c, settings, stats))
