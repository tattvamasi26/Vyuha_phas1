"""Accounts and sessions.

Anyone can sign up; each account gets its own workspace and can never see
another's. That boundary is enforced in two places and nowhere else:

* **here** — a request either carries a valid signed session cookie or it does
  not, and :func:`current` is the only way to find out who is asking;
* **store.py** — every query takes an ``owner_id`` as a *required* argument, so
  a route that forgets to scope is a ``TypeError`` the moment it runs, rather
  than a quiet leak of somebody else's numbers.

Same storage philosophy as the rest of the platform: JSON on disk, no database.
Passwords are never stored — only a scrypt hash of the password plus a
per-account salt, which is stdlib and needs no dependency. Sessions are
stateless signed cookies (HMAC-SHA256 over account id and issue time) keyed by
a secret generated once into ``vyuha_data/secret.key``; there is no session
table to expire, and deleting that file logs everybody out.
"""

from __future__ import annotations

import hmac
import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from hashlib import scrypt, sha256

from .store import DATA

ACCOUNTS = DATA / "accounts.json"
INVITES = DATA / "invites.json"
SECRET = DATA / "secret.key"

COOKIE = "vyuha_session"
MAX_AGE = 60 * 60 * 24 * 30          # thirty days

#: Marks a session cookie as belonging to a shared-link guest rather than an
#: account. Chosen because a urlsafe token never contains a colon.
GUEST_PREFIX = "g:"

#: scrypt work factors. n=2**14 keeps a login around a tenth of a second on a
#: laptop — slow enough to make guessing expensive, fast enough to not be felt.
_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 32

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8

#: Wrong PINs allowed before a shared link stops answering, and for how long.
#: Five is generous for a mistyped four digits on a phone; fifteen minutes turns
#: an exhaustive 10,000-guess sweep into roughly a month of waiting.
PIN_TRIES = 5
PIN_LOCKOUT = timedelta(minutes=15)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------- account

@dataclass
class Account:
    """One person's login, and the workspace it owns.

    ``install`` moved here from ``config.Settings`` when signup opened up: the
    operator/tenant fork is a property of *an account*, not of the machine the
    server runs on. One deployment now holds many workspaces, and each one
    decides for itself whether it manages a portfolio or is a single business.
    """

    id: str
    email: str
    name: str
    salt: str
    password_hash: str
    created_at: str = field(default_factory=_now)
    last_login: str = ""

    #: "operator" - this account onboards and manages several businesses.
    #: "tenant"   - this account *is* one business and sees only itself.
    #: ""         - chosen on the screen straight after signup.
    install: str = ""
    org_name: str = ""              # the tenant's business name
    tenant_slug: str = ""           # the single client record a tenant owns

    @property
    def is_operator(self) -> bool:
        return self.install == "operator"

    @property
    def is_tenant(self) -> bool:
        return self.install == "tenant"

    @property
    def configured(self) -> bool:
        return bool(self.install)

    #: An account is never a guest. See :class:`Guest` for the other principal.
    is_guest = False

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or self.email[:1].upper()


# ----------------------------------------------------------------------- guest

@dataclass
class Invite:
    """A private link to exactly one workspace, unlocked by a short PIN.

    This exists because a login form is the wrong shape for the person it is
    aimed at: a shop owner with one phone, no email habit, and no interest in
    remembering a password for the tool their supplier set up for them. The
    operator sends a link over WhatsApp, they tap it, type four digits once, and
    the device is remembered for thirty days.

    The link alone is not access — the PIN is what makes a forwarded WhatsApp
    message harmless. The PIN alone is not access either: four digits are
    guessable, so it is only ever checked against a token nobody can enumerate.
    """

    token: str                      # the unguessable half, in the URL
    slug: str                       # the one client this opens
    owner_id: str                   # the operator whose workspace it belongs to
    org_name: str
    pin_salt: str
    pin_hash: str
    created_at: str = field(default_factory=_now)
    last_used: str = ""
    revoked: bool = False
    #: Four digits is 10,000 guesses, which a script exhausts in seconds. The
    #: token stops anyone reaching this form uninvited, but once a link leaks
    #: the PIN is the only thing left — so failures cost time, and they persist
    #: to disk rather than living in memory, or a restart would forgive them.
    failed: int = 0
    locked_until: str = ""

    @property
    def locked(self) -> bool:
        return bool(self.locked_until) and _now() < self.locked_until

    @property
    def locked_for(self) -> int:
        """Whole minutes still to wait, rounded up. Never negative."""
        if not self.locked:
            return 0
        delta = datetime.fromisoformat(self.locked_until) - datetime.now()
        return max(1, -(-int(delta.total_seconds()) // 60))


@dataclass
class Guest:
    """A principal that quacks exactly like a tenant account.

    Deliberately shaped to match :class:`Account` where the app looks: ``id``
    returns the *operator's* id, so every ``store``/``ledger`` query written for
    accounts scopes correctly with no special case, and ``is_tenant`` is True, so
    the existing operator/tenant guards already close the portfolio to them.
    """

    id: str                         # the operator's account id — this is the key
    token: str
    tenant_slug: str
    org_name: str

    install = "tenant"
    is_operator = False
    is_tenant = True
    configured = True
    is_guest = True
    email = ""

    @property
    def name(self) -> str:
        return self.org_name

    @property
    def initials(self) -> str:
        parts = [p for p in self.org_name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "B"


def _load_invites() -> list[Invite]:
    DATA.mkdir(parents=True, exist_ok=True)
    if not INVITES.exists():
        return []
    try:
        return [Invite(**row) for row in json.loads(INVITES.read_text(encoding="utf-8"))]
    except (json.JSONDecodeError, OSError, TypeError):
        return []


def _save_invites(invites: list[Invite]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    INVITES.write_text(json.dumps([asdict(i) for i in invites], indent=2),
                       encoding="utf-8")


def create_invite(slug: str, owner_id: str, org_name: str,
                  pin: str = "") -> tuple[Invite, str]:
    """Mint a link for one workspace. Returns the invite and the PIN in clear.

    The clear PIN is returned exactly once, for the operator to send. It is not
    stored, so a lost PIN means issuing a new link rather than looking it up.
    """
    pin = pin.strip() or f"{secrets.randbelow(10000):04d}"
    salt = secrets.token_hex(16)
    invite = Invite(
        token=secrets.token_urlsafe(24),
        slug=slug, owner_id=owner_id, org_name=org_name,
        pin_salt=salt, pin_hash=_hash(pin, salt),
    )
    invites = [i for i in _load_invites() if i.slug != slug]   # one live link each
    invites.append(invite)
    _save_invites(invites)
    return invite, pin


def get_invite(token: str) -> Invite | None:
    invite = next((i for i in _load_invites() if i.token == token), None)
    return None if invite is None or invite.revoked else invite


def invite_for(slug: str) -> Invite | None:
    return next((i for i in _load_invites()
                 if i.slug == slug and not i.revoked), None)


def revoke_invite(slug: str) -> None:
    invites = _load_invites()
    for i in invites:
        if i.slug == slug:
            i.revoked = True
    _save_invites(invites)


def _store_invite(invite: Invite) -> None:
    _save_invites([invite if i.token == invite.token else i for i in _load_invites()])


def check_pin(invite: Invite, pin: str) -> bool:
    """Check a PIN, counting failures and locking the link when they pile up.

    Returns False both for a wrong PIN and for a locked link; the caller asks
    ``invite.locked`` to tell the owner which it was, because a person who has
    simply mistyped deserves to know they must wait rather than be left
    guessing at a PIN that would now be refused anyway.
    """
    if invite.locked:
        return False

    ok = hmac.compare_digest(_hash(pin.strip(), invite.pin_salt), invite.pin_hash)
    if ok:
        invite.last_used = _now()
        invite.failed = 0
        invite.locked_until = ""
    else:
        invite.failed += 1
        if invite.failed >= PIN_TRIES:
            invite.locked_until = (datetime.now() + PIN_LOCKOUT).isoformat(
                timespec="seconds")
            invite.failed = 0
    _store_invite(invite)
    return ok


def _load_all() -> list[Account]:
    DATA.mkdir(parents=True, exist_ok=True)
    if not ACCOUNTS.exists():
        return []
    try:
        raw = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [Account(**row) for row in raw]


def _save_all(accounts: list[Account]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    ACCOUNTS.write_text(json.dumps([asdict(a) for a in accounts], indent=2),
                        encoding="utf-8")


def normalise_email(email: str) -> str:
    return email.strip().lower()


def get(account_id: str) -> Account | None:
    return next((a for a in _load_all() if a.id == account_id), None)


def by_email(email: str) -> Account | None:
    email = normalise_email(email)
    return next((a for a in _load_all() if a.email == email), None)


def count() -> int:
    return len(_load_all())


def update(account: Account) -> None:
    _save_all([account if a.id == account.id else a for a in _load_all()])


# -------------------------------------------------------------------- password

def _hash(password: str, salt: str) -> str:
    return scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                  n=_N, r=_R, p=_P, dklen=_DKLEN).hex()


class SignupError(ValueError):
    """Why the form could not be accepted, in words the person can act on."""


def create(email: str, name: str, password: str) -> Account:
    """Register a new account. Raises :class:`SignupError` with a usable reason."""
    email = normalise_email(email)
    name = name.strip()

    if not EMAIL_RE.match(email):
        raise SignupError("That does not look like an email address.")
    if len(password) < MIN_PASSWORD:
        raise SignupError(f"Use at least {MIN_PASSWORD} characters for the password.")
    if by_email(email) is not None:
        raise SignupError("An account already exists for that email. Log in instead.")

    salt = secrets.token_hex(16)
    account = Account(
        id=secrets.token_hex(8),
        email=email,
        name=name or email.split("@")[0],
        salt=salt,
        password_hash=_hash(password, salt),
    )
    accounts = _load_all()
    accounts.append(account)
    _save_all(accounts)
    return account


def verify(email: str, password: str) -> Account | None:
    """The account if the password matches, else None. Constant-time compare."""
    account = by_email(email)
    if account is None:
        # Spend the same work anyway, so a missing email and a wrong password
        # cannot be told apart by how long the answer takes.
        _hash(password, secrets.token_hex(16))
        return None
    if not hmac.compare_digest(_hash(password, account.salt), account.password_hash):
        return None
    account.last_login = _now()
    update(account)
    return account


def change_password(account: Account, current_password: str, new: str) -> None:
    if not hmac.compare_digest(_hash(current_password, account.salt),
                               account.password_hash):
        raise SignupError("That is not your current password.")
    if len(new) < MIN_PASSWORD:
        raise SignupError(f"Use at least {MIN_PASSWORD} characters for the password.")
    account.salt = secrets.token_hex(16)
    account.password_hash = _hash(new, account.salt)
    update(account)


# --------------------------------------------------------------------- session

def _secret() -> bytes:
    """The signing key, generated once and kept out of the registry."""
    DATA.mkdir(parents=True, exist_ok=True)
    if not SECRET.exists():
        SECRET.write_text(secrets.token_hex(32), encoding="utf-8")
    return SECRET.read_text(encoding="utf-8").strip().encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), sha256).hexdigest()


def _issue(subject: str) -> str:
    issued = str(int(datetime.now().timestamp()))
    payload = f"{subject}.{issued}"
    return f"{payload}.{_sign(payload)}"


def issue(account: Account) -> str:
    """The cookie value for a freshly logged-in account."""
    return _issue(account.id)


def issue_guest(invite: Invite) -> str:
    """The cookie value that remembers a guest's device after the PIN."""
    return _issue(f"{GUEST_PREFIX}{invite.token}")


def read_token(token: str) -> str | None:
    """The account id a cookie proves, or None if it proves nothing."""
    if not token or token.count(".") != 2:
        return None
    account_id, issued, sig = token.split(".")
    if not hmac.compare_digest(_sign(f"{account_id}.{issued}"), sig):
        return None
    try:
        age = datetime.now().timestamp() - int(issued)
    except ValueError:
        return None
    if age > MAX_AGE or age < -60:      # -60 tolerates a small clock skew
        return None
    return account_id


def current(request):
    """Who is asking — an :class:`Account`, a :class:`Guest`, or nobody.

    The only sanctioned answer to that question. Both principals expose the same
    handful of attributes the app reads, so callers do not branch on which one
    they got; the one place it matters (deployment credentials) asks
    ``is_guest``.
    """
    subject = read_token(request.cookies.get(COOKIE, ""))
    if not subject:
        return None
    if subject.startswith(GUEST_PREFIX):
        invite = get_invite(subject[len(GUEST_PREFIX):])
        if invite is None:                      # revoked, or the link was deleted
            return None
        return Guest(id=invite.owner_id, token=invite.token,
                     tenant_slug=invite.slug, org_name=invite.org_name)
    return get(subject)
