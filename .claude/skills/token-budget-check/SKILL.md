---
name: token-budget-check
description: Enforce the 60/30/10 token budget and log spend. Use before starting any meaningful task and after finishing it.
---

Before starting a task, classify it:
- New feature or new module → DEVELOPMENT (60% share)
- Refactor / bug fix / improvement to existing code → ITERATION (30% share)
- Investigation, spike, benchmarking, exploration → RESEARCH (10% share)

Log estimated tokens in 03-token-log.md BEFORE the task, actual AFTER.
If a share crosses 80% of its cap: warn Vishu, do not silently continue.
If a share crosses 100%: STOP. Ask Vishu to reprioritize or expand the total budget.
