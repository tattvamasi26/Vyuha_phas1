---
name: test-protocol
description: Minimum test bar before anything is called "done". Use before shipping any Vyuha-1 requirement.
---

Before Ship:
1. Every acceptance criterion has one test that maps to it (1:1 or better).
2. Happy path: pass.
3. At least one negative case: pass.
4. If the change touched anything shared, run the full test suite, not just the new tests.
5. Report per-criterion, not summary.
