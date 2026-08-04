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
