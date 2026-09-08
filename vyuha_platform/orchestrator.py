"""One per client tenant. Schedules, retries, audits, and holds the only key.

The architecture is specific that this is **per tenant, not per platform**.
That is not a performance decision — config, schedules and the audit trail are
isolated per client so that a bespoke build for one business can later be lifted
into a shared platform without re-architecting. An orchestrator that knew about
every client would have to grow a tenant argument on every method later, which
is the same work done twice and done worse.

It owns four things, and deliberately nothing else:

* **Schedule.** `tick()` asks which routines are due and fires them. There is no
  background thread and no cron daemon: `tick()` is called on request, and can
  equally be called from a scheduler when one exists. Making the unit of work a
  plain function that takes a clock is what keeps it testable — every test here
  passes a fixed `now` rather than sleeping.
* **Retry.** A send that fails transiently is retried on the next tick, up to
  `MAX_TRIES`. Beyond that it stops and says so, because a number that has been
  wrong nine times is not going to be right on the tenth and the audit trail
  should not fill up pretending otherwise.
* **Audit.** Every step goes to `ledger`, attributed to the tenant. Nothing here
  writes its own log file; there is already one append-only record of what
  happened to a business and a second one would eventually disagree with it.
* **The gate key.** This is the only module besides `gate` itself that may
  release a held item, and `approve()` is the only way in. A route cannot call
  `gate.release()` — it has no key — so approval always carries the name of the
  person who granted it.

**State loads once per tick.** Ten routines for ten people read one snapshot of
the book rather than triggering ten analyses. That is also why `context()` is
public: the console reuses it so a screen and a brief can never quote different
numbers for the same morning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import (books, followup, gate, invoice, ledger, money, notify, people,
               routines, store, today as today_mod)

#: A transient failure gets this many attempts across ticks before it is left
#: alone. Small on purpose: these are messages, not payments.
MAX_TRIES = 3


@dataclass
class TickResult:
    """What one tick actually did — returned rather than logged only, so a
    caller (a test, a route, a future scheduler) can assert on it."""

    tenant: str
    fired: list = field(default_factory=list)
    retried: list = field(default_factory=list)
    #: Event notifications raised this tick — "who was told what". Separate from
    #: `fired`, because a routine is a bundle somebody asked for and a
    #: notification is an interruption they did not.
    notified: list = field(default_factory=list)
    held: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)

    @property
    def did_something(self) -> bool:
        return bool(self.fired or self.retried or self.notified)

    def __str__(self) -> str:
        if not self.did_something:
            return f"{self.tenant}: nothing due"
        bits = []
        if self.fired:
            bits.append(f"{len(self.fired)} routine(s) fired")
        if self.notified:
            bits.append(f"{len(self.notified)} notification(s)")
        if self.retried:
            bits.append(f"{len(self.retried)} retried")
        return f"{self.tenant}: " + ", ".join(bits)


class Orchestrator:
    """The wrapper around one client's agents.

    Construct it with the client and the deployment settings; everything else it
    needs it loads. Cheap to make and not meant to be long-lived — a request
    makes one, ticks it, and drops it.
    """

    def __init__(self, client, settings):
        self.client = client
        self.settings = settings
        self.tenant = client.slug
        self._ctx: dict | None = None

    # -- state -------------------------------------------------------------

    def context(self) -> dict:
        """Everything the domain agents produce, loaded once.

        Public because the console reuses it. A screen and a scheduled brief
        quoting different numbers for the same morning is the failure this
        prevents, and it is the sort that destroys trust quietly.
        """
        if self._ctx is not None:
            return self._ctx

        book = books.load(self.tenant)
        led = money.load(self.tenant)
        org = people.load(self.tenant)
        bills = invoice.load_all(self.tenant)
        pos = money.position(book, led)
        # Invoices go in, so an unbilled credit sale is a finding here exactly
        # as it is on the Desk. A brief that quietly omitted one category of
        # problem would be worse than one that omitted all of them.
        findings = today_mod.findings(self.client, book, led, org, bills)

        # An unmarked register is a forgotten register, not unpaid leave, so
        # the brief reports how many of the team were marked rather than how
        # many were present.
        register = people.today_register(org)
        marked = len([r for r in register if r["state"] != "unmarked"])

        self._ctx = {
            "book": book, "ledger": led, "org": org,
            "position": pos, "findings": findings,
            "queue": followup.queue(self.tenant, book),
            "invoices": bills,
            "selling": people.by_person(org, book),
            "register_marked": marked, "register_total": len(register),
        }
        return self._ctx

    # -- schedule ----------------------------------------------------------

    def tick(self, now: datetime | None = None) -> TickResult:
        """Fire whatever is due, retry whatever failed, report what happened."""
        now = now or datetime.now()
        result = TickResult(tenant=self.tenant)

        fresh: set[str] = set()
        due = [r for r in routines.load(self.tenant) if r.due(now)]
        for routine in due:
            try:
                self._fire(routine, now, result, fresh)
            except Exception as exc:                         # noqa: BLE001
                result.errors.append(f"{routine.name}: {exc}")
                ledger.log("routine.failed", f"{routine.name}: {exc}",
                           client=self.client)

        # The Notification Agent runs on every tick, not on a schedule. A
        # routine answers "it is eight o'clock, tell me how things are"; this
        # answers "something went wrong, tell whoever can fix it", and a shelf
        # that empties at eleven must not wait until tomorrow morning to be
        # mentioned. Its own cooldowns are what keep that from becoming noise.
        try:
            told = notify.run(self.client, self.settings, self.context(), as_of=now.date())
            # Everything raised, however it ended up. A notification that was
            # drafted because no provider is connected still happened, and a
            # tick that reported only deliveries would say "nothing due" on the
            # exact deployment this product mostly runs on.
            result.notified = told.raised
            fresh.update(told.items)
            for title in told.unaddressed:
                result.errors.append(f"nobody to tell about: {title}")
        except Exception as exc:                             # noqa: BLE001
            result.errors.append(f"notifications: {exc}")
            ledger.log("agent.failed", f"Notification agent: {exc}",
                       client=self.client)

        result.retried = self._retry_failed(fresh)
        result.held = gate.counts(self.tenant)["waiting"]
        result.skipped = len(routines.load(self.tenant)) - len(due)
        return result

    def _fire(self, routine, now: datetime, result: TickResult,
              fresh: set[str]) -> None:
        to = self._recipient(routine)
        if not to:
            # No number is not an error worth retrying — it is a setup gap, and
            # saying so once is more useful than failing every morning.
            ledger.log("routine.failed",
                       f"{routine.name}: nobody to send it to", client=self.client)
            result.errors.append(f"{routine.name}: no number on file")
            routines.mark_fired(self.tenant, routine.id, now.date())
            return

        text = routines.compose(self.client, routine, self.context())
        item = gate.submit(self.client, self.settings, kind="routine",
                           channel=routine.channel, to=to, body=text,
                           source=f"routine:{routine.id}")
        fresh.add(item.id)
        routines.mark_fired(self.tenant, routine.id, now.date())
        result.fired.append(routine.name)
        ledger.log("routine.fired", f"{routine.name} → {to} ({item.status})",
                   client=self.client, channel=routine.channel)

    def _recipient(self, routine) -> str:
        """Whose number this goes to.

        A routine names a member of staff; the number is read from the staff
        record at send time rather than copied into the routine, so changing
        somebody's phone in one place changes it everywhere.
        """
        if routine.staff_id:
            org = self.context()["org"]
            person = next((p for p in org.staff
                           if p.id == routine.staff_id and p.active), None)
            if person is not None and person.phone:
                return person.phone
            return ""
        return routine.to or self.client.phone

    def _retry_failed(self, skip: set[str] | None = None) -> list[str]:
        """Give a transient failure another go, up to MAX_TRIES.

        Anything sent during *this* tick is skipped. Retrying a message four
        seconds after it failed is not a retry, it is the same attempt against
        the same broken thing, and it burns the budget before the condition has
        any chance to clear.
        """
        skip = skip or set()
        items = gate.load(self.tenant)
        retried: list[str] = []
        for item in items:
            if item.id in skip or item.status != gate.FAILED:
                continue
            if item.disposition != gate.AUTO or item.tries >= MAX_TRIES:
                continue
            gate._deliver(item, self.client, self.settings)
            retried.append(item.id)
        if retried:
            gate.save(self.tenant, items)
        return retried

    # -- the gate ----------------------------------------------------------

    def approve(self, item_id: str, approved_by: str) -> tuple[bool, str]:
        """Release a held or drafted item. The only path to `gate.release`.

        Nothing else in the codebase holds the key, so an approval always has a
        name attached to it in the audit trail.
        """
        ok, detail = gate.release(self.client, self.settings, item_id,
                                  approved_by=approved_by, _token=gate.key())
        if ok:
            ledger.log("approval.granted",
                       f"Released by {approved_by}: {detail}", client=self.client)
        return ok, detail

    def cancel(self, item_id: str, why: str = "") -> tuple[bool, str]:
        return gate.cancel(self.client, item_id, why=why)

    def waiting(self) -> list:
        return gate.waiting(self.tenant)


# --- convenience ----------------------------------------------------------


def for_client(client, settings) -> Orchestrator:
    return Orchestrator(client, settings)


def tick_all(account_id: str, settings, now: datetime | None = None) -> list[TickResult]:
    """Tick every workspace an account owns.

    One orchestrator per tenant is still the rule — this makes one each, in
    turn, rather than a single instance that loops. A failure in one client's
    routines must not stop another client's from firing.
    """
    out = []
    for client in store.load_clients(account_id):
        try:
            out.append(Orchestrator(client, settings).tick(now))
        except Exception as exc:                             # noqa: BLE001
            r = TickResult(tenant=client.slug)
            r.errors.append(str(exc))
            out.append(r)
    return out
