---
name: requirements-update
description: Update the requirements/ folder consistently and never lose history. Use when adding a feature, changing a feature status, logging a decision, or shipping.
---

Rules:
- New feature → new file in 01-features/, next NN- number.
- Feature status changes → update Status: line in that file.
- Cross-cutting decision → new entry in 02-decisions.md (never edit old entries; append + supersede).
- Shipped feature → move to Status: shipped and add line to 99-changelog.md with date.
- Never delete a requirement file — mark Status: dropped instead.
