# Decision log (ADR-lite)

Each entry:
- ### <NNN>: <decision title> — <date>
- **Context:** ...
- **Options considered:** ...
- **Decision:** ...
- **Consequences / accepted risks:** ...

---

### 001: Bootstrap Vyuha-1 Prime inside `Vyuha_phas1/`, not the parent folder — 2026-08-04

- **Context:** `vyuha-1-prime-bootstrap.md` sets `repo_root: .` (current working directory). The CLI's working directory is the parent `Project V` folder, but `Project V` is not a git repository — `Vyuha_phas1/` is the git clone where active development happens (branch `feature/DOC-00-vishak`).
- **Options considered:** (a) bootstrap in `Project V` parent; (b) bootstrap in `Vyuha_phas1/`.
- **Decision:** (b) — `Vyuha_phas1/`. The bootstrap file itself lives there, and requirements/decisions must be version-controlled to be a source of truth.
- **Consequences / accepted risks:** Any Claude Code session started from the parent `Project V` folder will not auto-discover `Vyuha_phas1/.claude/agents/*`. Sessions must be started from inside `Vyuha_phas1/` for the sub-agents to resolve.

### 002: Build the engine in Python with pandas + openpyxl — 2026-08-11

- **Context:** First product deliverable is Phase 1 Foundation: read a distributor's Excel file and produce a dashboard. Needed a stack for the Excel-reading and analytics core.
- **Options considered:** (a) Python + pandas + openpyxl; (b) Node/TypeScript + SheetJS, matching the existing HTML dashboards; (c) pure browser, drag-and-drop, all client-side.
- **Decision:** (a). openpyxl exposes merged-cell ranges and cached formula values, which is what makes header/merge recovery possible at all; pandas carries the supply-chain math (ageing, days of cover, dead-stock joins) that Phases 2–3 build on. Output is still a static HTML file, so the demo artefact stays as portable as (c) would have been.
- **Consequences / accepted risks:** Two languages in the venture (Python engine, HTML/JS dashboards). The founder must have Python installed to run it — acceptable while this is a founder-operated service, revisit at Phase 3 when clients self-serve. Legacy `.xls` needs `xlrd` as an extra dependency; not installed, and the error message says so.

### 003: Rule-based column detection, not an LLM — 2026-08-11

- **Context:** The core problem is that every client names their columns differently. An LLM could map headers to fields in one prompt.
- **Options considered:** (a) rule-based canonical vocabulary with alias/veto scoring plus value-based inference; (b) send headers + sample rows to a model and let it map them; (c) make the client fill in a mapping form.
- **Decision:** (a). It runs offline with no per-file cost, is deterministic across re-runs of the same file, and when a client's column is misread the fix is one alias in `vyuha/schema.py` rather than a prompt gamble. (c) was rejected outright — "no setup" is the entire pitch.
- **Consequences / accepted risks:** New vocabulary has to be added by hand as real client files arrive; expect a handful of misses per new client at first. An LLM fallback for columns the rules cannot resolve stays open as a later addition, and the `unmapped` list on every table is already the hook for it.

### 004: Show the client what we read from their file — 2026-08-11

- **Context:** Auto-detection will occasionally get a column wrong, and a dashboard that is silently wrong is worse for trust than one that is visibly approximate.
- **Options considered:** (a) render only the results; (b) render results plus a panel listing sheets read, columns understood, and fixes applied.
- **Decision:** (b). Every dashboard ends with "What Vyuha read from your file".
- **Consequences / accepted risks:** Exposes the seams of the product in a sales demo. Judged a net positive: an owner who can see that "Closing Stock" was read as stock quantity is far more likely to believe the dead-stock number underneath it.

### 005: Open signup, with isolation enforced by required arguments — 2026-08-23

- **Context:** The platform had no authentication at all: anyone who reached the port saw every client. The owner asked for signup and login, and for accounts to be open — anyone can register and gets their own workspace.
- **Options considered:** (a) one owner account, signup closed after first run; (b) invite-only, the operator creates each login; (c) open signup, every account owning its own workspace.
- **Decision:** (c). Two mechanisms carry the isolation, chosen so that *forgetting* fails safe. First, a single `require_login` middleware closes every path outside a small `PUBLIC` set, so a route added later is private by default rather than public until someone remembers. Second, every read in `store.py` and `ledger.py` takes `owner_id` as a **required** positional argument — a query that forgets to scope raises `TypeError` on its first request instead of quietly returning another business's numbers. Passwords are stdlib `scrypt` over a per-account salt; sessions are stateless HMAC-signed cookies, so there is no session table to maintain or expire.
- **Consequences / accepted risks:** Slugs stay globally unique because they name directories on disk, so one account can infer that a business name is taken (it gets `-2`). Credentials in `config.json` remain deployment-level — one WhatsApp sender and one Claude key shared by every account on the machine — which is correct for a single founder-run deployment and must be revisited before anyone else runs their own sends. The session cookie is not marked `secure`, because this also serves plain `localhost`; that must change before this is served over anything but HTTPS. `install`/`org_name`/`tenant_slug` moved from `config.Settings` to `auth.Account`, since the operator/tenant fork belongs to whoever is logged in, not to the machine.

### 006: A private link and a PIN, not a login, for the businesses we serve — 2026-08-24

- **Context:** ADR 005 gave the platform email-and-password accounts. Review caught that this is the wrong shape for the actual user: a one- or two-person shop has no email habit and no interest in maintaining a password for a tool their supplier set up. A login form asks them to become a user of our system before they can look at their own numbers.
- **Options considered:** (a) keep signup and just shorten it; (b) the operator sends a private link, and the link alone is access; (c) private link plus a 4-digit PIN, device remembered for 30 days; (d) phone number and an OTP.
- **Decision:** (c). (b) was rejected because a WhatsApp message gets forwarded, and forwarding would hand over the whole workspace. (d) needs live WhatsApp or SMS sending, which is not connected, so it cannot ship today. In (c) two halves make one key: a token nobody can enumerate, and four digits that make a forwarded link harmless on its own. The operator keeps email-and-password for their own console, where a portfolio and credentials genuinely need protecting.
- **Implementation note:** `auth.Guest` is deliberately shaped to be indistinguishable from a tenant `Account` at every point the app reads a principal — most importantly `id`, which returns the *operator's* account id. Every `store`/`ledger` query written for ADR 005 therefore scopes a guest correctly with no new code path, and the existing operator/tenant guards already close the portfolio. Only deployment credentials ask `is_guest`.
- **Consequences / accepted risks:** Four digits are weak on their own; they are only ever checked against an unguessable token, and there is currently **no rate limit on PIN attempts** — add one before this is exposed beyond a trusted network. The PIN is shown to the operator exactly once and stored only as a hash, so a lost PIN means issuing a new link. One live link per client, by construction: minting a second replaces the first.

### 007: Photographs for trade backdrops, and a generalised front page — 2026-08-24

- **Context:** The landing page opened with "For distributors who run on Excel". The product reads spreadsheets, CSVs, PDFs, photographs of handwritten registers, and typed-in entries, for nurseries and manufacturers and retailers as readily as distributors. The headline described less than the product does. Separately, trade backdrops were flat generated SVGs.
- **Decision:** Headline is now "Your numbers already know. Ask them." over "However your business keeps its records", and the trade list on the front page is rendered from `theme.TRADES` rather than typed out, so adding a trade adds it to the landing page. Trade backdrops became photographs served from `static/img/`, with the SVGs retained as `fallback`.
- **Consequences / accepted risks:** The platform now serves image files, so it is no longer a pure-HTML-strings app. The engine's self-contained guarantee was the thing at risk — a test now asserts `/static/` never appears in a generated client dashboard, alongside the existing no-script assertion. Images add ~600KB to the repo.

### 008: Failures cost time, and the cookie follows the connection — 2026-08-24

- **Context:** ADR 006 shipped the link-plus-PIN with two gaps named in its own consequences: no rate limit on PIN attempts, and a session cookie never marked `secure`. Both were fixed before any further feature work.
- **Decision:** Five wrong PINs pause a link for fifteen minutes. The counter persists on the `Invite` record rather than living in memory, because a process restart must not forgive an attack in progress; a correct PIN clears it, because the common case is an owner mistyping on a phone. While paused the gate renders no input field at all — a form certain to be refused reads as a broken page and invites more guessing. `secure` is decided per request from `X-Forwarded-Proto` or the request scheme, rather than configured, because one build serves both plain localhost in development and HTTPS behind a proxy; setting it unconditionally would mean the cookie is never stored locally and no session would ever persist.
- **Also closed:** `auth.change_password()` had been written in ADR 005 and never wired to a route — dead code. It is now a form on the settings page, closed to guests (who have no password), and re-issues the session cookie on success so changing a password is a usable answer to "somebody has my laptop".
- **Consequences / accepted risks:** The lockout is per link, not per source address, so one attacker can deny a legitimate owner access for fifteen minutes at a time by guessing badly on purpose. Judged acceptable: the attacker must already hold the unguessable token, and the owner's remedy — ask for a new link — is one WhatsApp message. Changing a password does **not** end sessions in other browsers, since the session is signed over the account id rather than the password hash; clearing `vyuha_data/secret.key` remains the way to end every session everywhere, and the settings page says so.

### 009: The seven modules, named after jobs rather than features — 2026-09-08

- **Context:** The workspace had grown to four screens — Today, Sell/Data, Stock, Money — plus a gear. Each was named after a set of features that happened to exist together, which is how a product becomes a control panel: Money carried eleven statements behind an in-body chooser, Stock carried branch and staff forms used once a year, and the brief that goes to a customer was a block at the foot of a screen about something else.
- **Options considered:** (a) keep four screens and tidy each; (b) go back to one page with panels; (c) adopt the founder's own structure, drawn on paper: Desk, Dashboard, Financials, Operations, People, Messages, Data.
- **Decision:** (c). A module is a **job somebody has**; its tabs are the steps within that job. Two rules keep it from rotting back into a feature list. A screen that cannot answer "which job is this part of" gets a home inside an existing module rather than a tab of its own. And nothing appears in two modules — a figure lives where the job that acts on it lives, and every other screen links to it, which is why invoices are Operations and not Financials. `modules.py` holds the map as data so the nav, the routing and the redirects read from one place, and `console.render()` is a single dispatch that loads the state every screen needs once, because letting each route decide what to load is how two screens end up disagreeing about the same number.
- **Also decided:** Setup is registered but deliberately absent from the module row. Nothing on it is part of running the business, and putting it there would say that it was. The agent is not a module either — it is the ask bar in the header of every screen, because a panel has to be remembered and a box in front of somebody does not.
- **Consequences / accepted risks:** Every old address is now a redirect (`modules.MOVED`), and an unknown module lands on the Desk rather than a 404, so a stale bookmark reaches the product rather than an apology. That forgiveness hides typos: `/c/x/financails` silently opens the Desk instead of saying it did not understand. Accepted — a person following a link that was right last month is far commoner than one typing a module name.

### 010: The dashboard says how sure it is of each number — 2026-09-08

- **Context:** ADR 004 put a "What Vyuha read from your file" panel at the foot of every dashboard, which was the right instinct and the wrong placement. The panel listed sheets and columns in prose, at the bottom, after every figure had already been read. Nothing on the page distinguished a revenue total read off a column labelled "Invoice Amount" from one reconstructed as qty × rate on a sheet with no headings at all. Review put it plainly: the data we get may be ambiguous, and the dashboard was the worst part of the product.
- **Context, second half:** the signals to fix it already existed and were being discarded. `detect._score_token` scores every (column, field) pair to make the assignment — 10 for an exact alias, 5-6 for a fragment of the heading, and nothing for a column `_infer_from_values` rescued by reading its contents — and `map_columns` returned only the assignment. `find_header_row` and `classify` each returned a confidence that reached `DetectedTable` and stopped, because `CleanTable` did not carry them.
- **Options considered:** (a) a single confidence percentage per report; (b) a confidence percentage per figure; (c) four coarse verdicts per column, inherited by whatever figure depends on it.
- **Decision:** (c), in a new `trust.py`. A percentage invites an argument about whether 0.72 is good and cannot be checked; "Amount was not in the file — Vyuha calculated it" can be verified in ten seconds by opening the spreadsheet. A figure inherits the **weakest** verdict among the columns feeding it, since a total is only as good as its worst input, and across a client who splits sales over twelve monthly sheets the weakest reading of any one sheet governs. `map_columns` keeps its signature and `score_mapping()` recomputes the scores instead — which gets the most important case right for free, because a value-inferred column scores zero against the field it was assigned.
- **Also decided:** `matched` never raises an alarm. "Qty (Nos)" is a heading a human reads without hesitating; flagging it would put the caution panel on nearly every file, and a caption that appears on every report is one nobody reads by the third. It stays visible in the read-back table, where somebody is already looking at columns, and in `vyuha check`, which exists precisely to catch a misreading before anyone sees the numbers.
- **Consequences / accepted risks:** The verdict is about *how a column was identified*, not whether its values are right — a perfectly labelled "Amount" column full of typos still reads as certain, and the document does not claim otherwise. Thresholds (10.0 / 5.0) are tied to `_score_token`'s scale, so changing that scoring changes what gets flagged; the tests pin both ends. Showing the seams remains a deliberate sales risk, as in ADR 004, and for the same reason: an owner who can see which column Vyuha guessed is far likelier to believe the ones it did not.
