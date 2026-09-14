"""The Onboarding Studio: /studio — the Vyuha team setting a business up, stage by stage.

Operators and masters only. A tenant or a guest who finds this path is sent to their own
business; the Studio is a service Vyuha performs, not a screen a business drives.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import (access, books, catalog, channels, ledger, onboarding, people, store,
                 theme)
from .. import india, shell
from ..templating import render

router = APIRouter()


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _msg(text: str) -> str:
    return text.replace(" ", "+").replace("&", "and")


def _operator(request: Request):
    """The account, if it may use the Studio; otherwise None."""
    account = request.state.account
    return account if access.is_operator(account) else None


def _state(client) -> tuple[onboarding.Onboarding, dict, "books.Book", "people.Org"]:
    record = onboarding.load(client.slug)
    book = books.load(client.slug)
    org = people.load(client.slug)
    return record, onboarding.status(record, client, book, org), book, org


# ------------------------------------------------------------------- the list

@router.get("/studio", response_class=HTMLResponse)
def studio_home(request: Request):
    account = _operator(request)
    if account is None:
        return _redirect("/app")
    rows = []
    for client in access.businesses(account):
        record, states, book, _org = _state(client)
        done, total = onboarding.progress(states)
        now = onboarding.current(states)
        open_now = [s for s in onboarding.STAGES if states[s.key] == "todo"]
        rows.append({
            "client": client,
            "trade": shell.trade_for(client)["label"],
            "done": done, "total": total,
            "available": sum(1 for s in onboarding.STAGES if states[s.key] != "later"),
            "available_done": sum(1 for s in onboarding.STAGES
                                  if states[s.key] in {"done", "skipped"}),
            "current": onboarding.BY_KEY[now],
            "ready": not open_now,
            "states": states,
            # Not "items": on a dict, Jinja resolves r.items to the dict method.
            "item_count": len(book.items),
            "sale_count": len(book.sales),
            "updated": record.updated_at or client.created_at,
        })
    rows.sort(key=lambda r: (r["ready"], r["updated"]), reverse=False)
    rows.sort(key=lambda r: r["ready"])
    ctx = shell.base(request, account, area="studio", section="studio",
                     title="Onboarding Studio")
    ctx.update({"rows": rows, "stages": onboarding.STAGES,
                "setting_up": sum(1 for r in rows if not r["ready"])})
    return render(request, "pages/studio/index.html", ctx)


# ------------------------------------------------------------- a new business

@router.get("/studio/new", response_class=HTMLResponse)
def studio_new(request: Request):
    account = _operator(request)
    if account is None:
        return _redirect("/app")
    ctx = shell.base(request, account, area="studio", section="new",
                     title="Onboard a business")
    ctx.update({"trades": list(theme.TRADES.items())})
    return render(request, "pages/studio/new.html", ctx)


@router.post("/studio/new")
def studio_create(request: Request, name: str = Form(""), contact: str = Form(""),
                  phone: str = Form(""), trade: str = Form("")):
    account = _operator(request)
    if account is None:
        return _redirect("/app")
    name = name.strip()
    if not name:
        return _redirect("/studio/new?m=Give+the+business+a+name.&k=bad")
    client = store.add_client(
        account.id, name=name, contact=contact.strip(),
        phone=channels.normalise_phone(phone),
        trade=trade if trade in theme.TRADES else theme.guess(name),
        # Typed-in until the data map says otherwise: merging never deletes
        # anything a person entered, which is the safe default for day one.
        data_mode="books")
    record = onboarding.Onboarding(slug=client.slug, cutover=onboarding.default_cutover())
    onboarding.save(record)
    ledger.log("client.onboarded", f"{client.name} onboarding started", client=client,
               channel="studio")
    return _redirect(f"/studio/{client.slug}/datamap?m={_msg(client.name + ' created.')}")


# ------------------------------------------------------------ one business

def _client(request: Request, slug: str):
    account = _operator(request)
    if account is None:
        return None, None
    return account, access.workspace(account, slug)


@router.get("/studio/{slug}")
def studio_business(slug: str, request: Request):
    account, client = _client(request, slug)
    if client is None:
        return _redirect("/studio?m=That+business+is+not+available.&k=bad")
    _record, states, _book, _org = _state(client)
    return _redirect(f"/studio/{slug}/{onboarding.current(states)}")


@router.get("/studio/{slug}/{stage}", response_class=HTMLResponse)
def studio_stage(slug: str, stage: str, request: Request):
    account, client = _client(request, slug)
    if client is None:
        return _redirect("/studio?m=That+business+is+not+available.&k=bad")
    if stage not in onboarding.BY_KEY:
        return _redirect(f"/studio/{slug}")
    record, states, book, org = _state(client)
    done, total = onboarding.progress(states)
    index = [s.key for s in onboarding.STAGES].index(stage)
    ctx = shell.base(request, account, area="studio", client=client, section="studio",
                     title=f"{client.name} · {onboarding.BY_KEY[stage].label}")
    ctx.update({
        "record": record, "states": states, "stages": onboarding.STAGES,
        "stage": onboarding.BY_KEY[stage], "done": done, "total": total,
        "prev": onboarding.STAGES[index - 1] if index else None,
        "next": onboarding.STAGES[index + 1] if index + 1 < len(onboarding.STAGES) else None,
        "live_phase": onboarding.LIVE_PHASE,
    })
    if stage == "profile":
        ctx.update({"trades": list(theme.TRADES.items()), "states_list": india.STATES,
                    "months": india.MONTHS})
    elif stage == "datamap":
        ctx.update({"cutover_value": record.cutover or onboarding.default_cutover(),
                    "domains": onboarding.DOMAINS, "sources": onboarding.SOURCES,
                    "cadences": onboarding.CADENCES,
                    "history_choices": onboarding.HISTORY_CHOICES,
                    "plan": onboarding.plan(record),
                    "answers": {d: record.answer(d) for d in onboarding.DOMAIN_KEYS}})
    elif stage == "masters":
        have = {i.name.strip().lower() for i in book.items}
        suggestions = [{"i": n, "s": s, "have": s.name.strip().lower() in have}
                       for n, s in enumerate(catalog.starters(shell.trade_key(client)))]
        ctx.update({"items": book.items, "suggestions": suggestions,
                    "branches": org.branches, "staff": org.staff,
                    "roles": list(people.SEES.keys()),
                    "branch_name": {b.id: b.name for b in org.branches}})
    return render(request, "pages/studio/stage.html", ctx)


def _after(slug: str, stage: str, message: str, advance: bool, kind: str = "ok"):
    """Back to the stage, or on to the next one, with a word about what happened."""
    target = stage
    if advance:
        keys = [s.key for s in onboarding.STAGES]
        i = keys.index(stage)
        target = keys[i + 1] if i + 1 < len(keys) else stage
    return _redirect(f"/studio/{slug}/{target}?m={_msg(message)}&k={kind}")


@router.post("/studio/{slug}/profile")
def save_profile(slug: str, request: Request, name: str = Form(""), trade: str = Form(""),
                 contact: str = Form(""), phone: str = Form(""), email: str = Form(""),
                 gstin: str = Form(""), state: str = Form(""), address: str = Form(""),
                 industry: str = Form(""), fy_start_month: int = Form(4),
                 advance: str = Form("")):
    account, client = _client(request, slug)
    if client is None:
        return _redirect("/studio")
    if not name.strip():
        return _after(slug, "profile", "The business needs a name.", False, "bad")
    client.name = name.strip()
    client.trade = trade if trade in theme.TRADES else client.trade
    client.contact = contact.strip()
    client.phone = channels.normalise_phone(phone)
    client.email = email.strip()
    client.gstin = gstin.strip().upper()
    client.state = state if state in india.CODES else ""
    client.address = address.strip()
    client.industry = industry.strip()
    store.update_client(client)
    record = onboarding.load(slug)
    record.fy_start_month = fy_start_month if 1 <= fy_start_month <= 12 else 4
    onboarding.save(record)
    ledger.log("settings.changed", f"Profile updated for {client.name}", client=client,
               channel="studio")
    return _after(slug, "profile", "Profile saved.", bool(advance))


@router.post("/studio/{slug}/datamap")
async def save_datamap(slug: str, request: Request):
    account, client = _client(request, slug)
    if client is None:
        return _redirect("/studio")
    form = await request.form()
    record = onboarding.load(slug)
    for key in onboarding.DOMAIN_KEYS:
        answer = onboarding.Answer(
            source=str(form.get(f"src_{key}", "")).strip(),
            software=str(form.get(f"software_{key}", "")).strip(),
            since=str(form.get(f"since_{key}", "")).strip()[:7],
            keeper=str(form.get(f"keeper_{key}", "")).strip(),
            cadence=str(form.get(f"cadence_{key}", "")).strip(),
            notes=str(form.get(f"notes_{key}", "")).strip())
        if answer.source and answer.source not in onboarding.SOURCE_LABEL:
            answer.source = ""
        record.datamap[key] = answer
    cutover = str(form.get("cutover", "")).strip()
    try:
        record.cutover = date.fromisoformat(cutover).isoformat() if cutover else ""
    except ValueError:
        record.cutover = ""
    try:
        record.history_months = max(0, min(60, int(form.get("history_months", 12))))
    except (TypeError, ValueError):
        record.history_months = 12
    onboarding.save(record)

    # How sales are kept decides how the business is read. Only decided while the
    # business holds no data yet: flipping it later would change whether an upload
    # replaces the book or merges into it, which is not a thing to do silently.
    book = books.load(slug)
    sales_source = record.answer("sales").source
    if not book.items and not book.sales and not client.runs and sales_source:
        client.data_mode = "upload" if sales_source in {"excel", "tally", "software"} else "books"
        store.update_client(client)

    ledger.log("settings.changed", f"Data map updated for {client.name}", client=client,
               channel="studio")
    answered = record.answered
    note = ("Data map saved." if answered == len(onboarding.DOMAIN_KEYS) else
            f"Saved — {answered} of {len(onboarding.DOMAIN_KEYS)} kinds of record answered.")
    return _after(slug, "datamap", note, bool(form.get("advance")))


@router.post("/studio/{slug}/masters/catalogue")
async def add_from_catalogue(slug: str, request: Request):
    account, client = _client(request, slug)
    if client is None:
        return _redirect("/studio")
    form = await request.form()
    # The same key the stage page listed them under, or the indexes would point
    # at different items.
    starters = catalog.starters(shell.trade_key(client))
    added = 0
    for raw in form.getlist("pick"):
        try:
            i = int(str(raw))
            s = starters[i]
        except (ValueError, IndexError):
            continue
        books.add_item(slug, s.name, s.category,
                       str(form.get(f"unit_{i}", "") or s.unit),
                       form.get(f"rate_{i}", "") or s.rate,
                       form.get(f"cost_{i}", "") or s.cost, 0, 0)
        added += 1
    note = f"{added} item(s) added from the starter list." if added else "Tick at least one item."
    return _after(slug, "masters", note, False, "ok" if added else "bad")


@router.post("/studio/{slug}/masters/items")
async def add_items(slug: str, request: Request):
    account, client = _client(request, slug)
    if client is None:
        return _redirect("/studio")
    form = await request.form()
    names = form.getlist("name")
    cols = {k: form.getlist(k) for k in ("category", "unit", "rate", "cost", "reorder")}

    def at(key: str, i: int, default=""):
        values = cols[key]
        return values[i] if i < len(values) and str(values[i]).strip() else default

    added = 0
    for i, raw in enumerate(names):
        name = str(raw).strip()
        if not name:
            continue
        books.add_item(slug, name, str(at("category", i, "Other")), str(at("unit", i, "piece")),
                       at("rate", i, 0), at("cost", i, 0), 0, at("reorder", i, 0))
        added += 1
    note = f"{added} item(s) added." if added else "Type at least one item name."
    return _after(slug, "masters", note, False, "ok" if added else "bad")


@router.post("/studio/{slug}/masters/branch")
def add_branch(slug: str, request: Request, name: str = Form(""), place: str = Form(""),
               manager: str = Form("")):
    account, client = _client(request, slug)
    if client is None:
        return _redirect("/studio")
    if not name.strip():
        return _after(slug, "masters", "Give the branch a name.", False, "bad")
    _org, note = people.add_branch(slug, name.strip(), place.strip(), manager=manager.strip())
    ledger.log("people.changed", note, client=client, channel="studio")
    return _after(slug, "masters", note, False)


@router.post("/studio/{slug}/masters/staff")
def add_staff(slug: str, request: Request, name: str = Form(""), role: str = Form("Salesperson"),
              branch: str = Form(""), phone: str = Form("")):
    account, client = _client(request, slug)
    if client is None:
        return _redirect("/studio")
    if not name.strip():
        return _after(slug, "masters", "Give the person a name.", False, "bad")
    _org, note = people.add_staff(slug, name.strip(), role, branch,
                                  channels.normalise_phone(phone))
    ledger.log("people.changed", note, client=client, channel="studio")
    return _after(slug, "masters", note, False)
