# Vyuha — the documents

Four documents, in the order you would read them.

| | For | What it is |
|---|---|---|
| [What Vyuha does](what-vyuha-does.md) | Anybody new | Every feature in plain words, and an honest list of what is not built |
| [Using Vyuha fully](using-vyuha-fully.md) | The client, and us | The daily, weekly and monthly rhythm that makes every screen true |
| [Runbook · Onboarding a business](runbooks/onboarding-a-business.md) | The operator | One business, start to finish: what to collect, the interview, the masters, the pitfalls |
| [Runbook · The bearings demo](runbooks/demo-script-bearings.md) | Whoever is presenting | A twelve-minute script with the exact figures the seed produces |

## The demo, in two commands

```bash
.venv/Scripts/python -m vyuha_platform seed-bearings   # Shakti Bearings & Power Transmission
.venv/Scripts/python demo/make_bearings.py             # the same client's own messy files
.venv/Scripts/python -m vyuha_platform --open          # then log in
```

Two demo businesses exist, deterministic and re-buildable:

| Business | Account | Shows |
|---|---|---|
| Shakti Bearings & Power Transmission, Hubballi | `bearings@vyuha.test` / `vyuha-bearings` | Industrial distribution: a year of trade, GST invoices both inside and outside the state, two godowns |
| Shree Agro & Hardware, Belagavi | `demo@vyuha.test` / `vyuha-demo` | An agri-input shop, plus a second business that sends files rather than typing them |

Both are rebuilt from nothing by their command, so a rehearsal can never leave the demo in a
state somebody has to explain. Never demo off live data.
