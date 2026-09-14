"""Who may open which business — one answer, shared by every screen of the new site.

The rules are the ones the classic screens already enforce in ``app.py``
(``_client_for``, ``_tenant_client``, ``_console_client``), stated once here so the new
routes do not grow a second, slightly different copy. The classic helpers retire with the
classic screens at cutover.

* An operator sees the businesses their account owns.
* A tenant — and a guest who came in on a private link, who is shaped like one — sees
  exactly one business and cannot tell that any other exists.
* A master (Vyuha staff) sees every business, and every look at somebody else's is written
  into *that* business's own activity trail, so support access is never a silent door.
"""

from __future__ import annotations

from . import ledger, store


def is_master(account) -> bool:
    return bool(getattr(account, "is_master", False))


def is_operator(account) -> bool:
    """Runs a portfolio — the Onboarding Studio is theirs. Masters count."""
    return account is not None and (is_master(account)
                                    or not getattr(account, "is_tenant", False))


def client_for(account, slug: str) -> store.Client | None:
    """The business behind ``slug`` if this person may see it, else None."""
    if is_master(account):
        client = store.find_client(slug)
        if client is not None and client.owner_id != account.id:
            ledger.log("master.viewed", f"Vyuha support opened {client.name}",
                       client=client, channel="settings",
                       master=getattr(account, "username", ""))
        return client
    return store.get_client(slug, account.id)


def tenant_client(account) -> store.Client | None:
    """The one business a tenant owns — never "whatever exists" when unset."""
    slug = getattr(account, "tenant_slug", "")
    if not slug:
        return None
    return store.get_client(slug, account.id)


def workspace(account, slug: str) -> store.Client | None:
    """The business this person may work in, or None.

    A stranger's slug and a typo get the same None, so a URL cannot be used to
    find out which businesses exist.
    """
    if account is None:
        return None
    client = client_for(account, slug)
    if client is None:
        return None
    if getattr(account, "is_tenant", False):
        own = tenant_client(account)
        if own is None or own.slug != slug:
            return None
    return client


def businesses(account) -> list[store.Client]:
    """Every business this person can switch between, newest first."""
    if account is None:
        return []
    if is_master(account):
        return store.all_clients()
    if getattr(account, "is_tenant", False):
        own = tenant_client(account)
        return [own] if own else []
    return store.load_clients(account.id)
