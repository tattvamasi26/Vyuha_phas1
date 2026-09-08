"""How sure Vyuha is about each number, and why.

A client's file is not a database export. A column called "Amt" might be the
line amount or the amount still owed; a sheet with no header at all might still
be a stock statement; "Amount" may not exist and be reconstructed as qty × rate.
The engine already makes all of those calls, and until now the report printed
the result of every one of them in the same weight of type as a figure read
straight off a labelled column.

That is the failure this module exists to fix. **A number transcribed from a
photograph must never look identical to one typed into Excel** — the same rule
`sources.py` follows for uploads, applied to the figures themselves.

The signals were already there and were being thrown away:

* `detect._score_token` scores every (column, field) pair — 10 for an exact
  alias, 5-6 for a fragment of the heading, 3-4 for an alias buried inside a
  longer one, and nothing at all for a column `_infer_from_values` rescued by
  reading its values.
* `find_header_row` and `classify` each return a confidence that reached
  `DetectedTable` and stopped there.
* `clean.py` records every repair in `issues`, including the derivations that
  manufacture a column outright.

`CleanTable` dropped all of it. This module carries it forward and turns it into
one of four verdicts a person can act on, plus the sentence explaining which
evidence produced it.

The verdicts are deliberately coarse. A percentage would invite an argument
about whether 0.72 is good; "read from a labelled column" against "guessed from
the values in it" is a distinction somebody can check in ten seconds by opening
their own file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import schema

#: A figure read straight off a column whose heading said what it was.
READ = "read"
#: The heading was recognisable but not exact — "Inv Amt" for `amount`.
MATCHED = "matched"
#: No usable heading; the column was identified by what its values look like.
GUESSED = "guessed"
#: The column did not exist and was reconstructed from others.
DERIVED = "derived"

#: Worst-first, which is the order a reader needs them in.
RANK = {DERIVED: 0, GUESSED: 1, MATCHED: 2, READ: 3}

#: What each verdict means, in the words somebody would use checking it.
PHRASE = {
    READ: "read from a column labelled as such",
    MATCHED: "matched to a column whose heading was close",
    GUESSED: "identified by what the values look like — there was no usable heading",
    DERIVED: "calculated, because the file did not contain it",
}

#: Worth interrupting somebody for. A *matched* column is deliberately not on
#: this list: "Qty (Nos)" is a heading a human reads as quantity without
#: hesitating, and flagging it would put the caution panel on nearly every file
#: — a caption that always appears is one nobody reads by the third report. So
#: `matched` stays visible in the read-back table, where somebody is already
#: looking at columns, and never raises an alarm of its own.
NOTABLE = (DERIVED, GUESSED)


def verdict(score: float, derived: bool = False) -> str:
    """One field's verdict, from its mapping score."""
    if derived:
        return DERIVED
    if score >= 10.0:
        return READ
    if score >= 5.0:
        return MATCHED
    return GUESSED


@dataclass(frozen=True)
class Basis:
    """What one reported figure rests on.

    `worst` is what the figure inherits: a total is only as trustworthy as the
    least certain column feeding it, so revenue built from a derived amount is
    derived, however cleanly the dates were read.
    """

    label: str
    fields: tuple[str, ...] = ()
    verdicts: dict[str, str] = field(default_factory=dict)
    sheets: tuple[str, ...] = ()

    @property
    def worst(self) -> str:
        if not self.verdicts:
            return READ
        return min(self.verdicts.values(), key=lambda v: RANK[v])

    @property
    def certain(self) -> bool:
        return self.worst == READ

    @property
    def note(self) -> str:
        """One sentence naming the weakest evidence under this figure.

        Names the field rather than summarising, because "Amount was calculated,
        because the file did not contain it" is checkable and "medium
        confidence" is not.
        """
        if self.certain:
            return ""
        worst = self.worst
        named = [f for f, v in self.verdicts.items() if v == worst]
        labels = [schema.LABELS.get(f, f) for f in named]
        subject = _join(labels)
        verb = "was" if len(labels) == 1 else "were"
        return f"{subject} {verb} {PHRASE[worst]}."


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def basis(tables, label: str, *fields: str) -> Basis:
    """What the tables say about the fields one figure is built from.

    Takes every table that carries the field and keeps the *weakest* reading of
    it. A client who splits sales across twelve monthly sheets may have labelled
    eleven of them properly and left the twelfth headerless; the total is only
    as good as that twelfth.
    """
    verdicts: dict[str, str] = {}
    sheets: list[str] = []
    for table in tables:
        conf = getattr(table, "field_confidence", {}) or {}
        derived = getattr(table, "derived", set()) or set()
        for name in fields:
            if name not in table.frame.columns:
                continue
            v = verdict(conf.get(name, 0.0), derived=name in derived)
            if name not in verdicts or RANK[v] < RANK[verdicts[name]]:
                verdicts[name] = v
            if table.sheet not in sheets:
                sheets.append(table.sheet)
    return Basis(label=label, fields=tuple(fields), verdicts=verdicts,
                 sheets=tuple(sheets))


def concerns(tables) -> list[str]:
    """Everything about this reading a person should check before trusting it.

    Ordered worst-first and deduplicated, because the same guess repeated across
    twelve monthly sheets is one thing to check, not twelve.
    """
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for table in tables:
        conf = getattr(table, "field_confidence", {}) or {}
        derived = getattr(table, "derived", set()) or set()
        for name in table.frame.columns:
            if name not in schema.LABELS:
                continue
            v = verdict(conf.get(name, 0.0), derived=name in derived)
            if v not in NOTABLE:
                continue
            label = schema.LABELS.get(name, name)
            column = table.mapping.get(name, "")
            if v == DERIVED:
                line = f"{label} was not in the file — Vyuha calculated it."
            elif v == GUESSED:
                line = (f"{label} came from a column with no usable heading, "
                        f"identified by its values.")
            else:
                line = f"{label} was matched to the column headed “{column}”."
            if line in seen:
                continue
            seen.add(line)
            found.append((RANK[v], line))

    for table in tables:
        if getattr(table, "kind_confidence", 1.0) < 0.5:
            line = (f"“{table.sheet}” was read as "
                    f"{schema.TABLE_LABELS.get(table.kind, table.kind).lower()}, "
                    f"but the columns were mixed enough that it is worth a look.")
            if line not in seen:
                seen.add(line)
                found.append((1, line))

    found.sort(key=lambda item: item[0])
    return [line for _rank, line in found]
