# 02 — UX rewire: onboarding → data flow → customer site → assistant

## Description

The founder asked for the product's UI/UX to be rewired end to end, starting from onboarding:
an operator-led onboarding that captures a business's history from any source (files, Tally,
paper registers), continuous data flow through four feeds (typed entries, regular files,
WhatsApp forwarding, Tally sync), and a modern responsive site — Home, Sales, Operations,
Finance, Team, Analytics — with an AI assistant and communication built into every task.

Approved plan (2026-09-12): `C:\Users\HP\.claude\plans\wise-wiggling-ripple.md`, seven phases,
each ending with tests, screenshots at 360 / 768 / 1440 px and the owner's go-ahead.

## Acceptance criteria

### Phase 1 — First look (shipped 2026-09-14)
- [x] Data bugs that would show on screen are fixed: ISO dates no longer swap day and month;
      an invoice cannot bill several customers; an upload no longer wipes earlier uploads; a
      re-sent file no longer doubles a typed-in book's sales.
- [x] Jinja2 + HTMX + Alpine + Tailwind toolchain, assets pinned and served locally.
- [x] Design system: tokens (light default, dark mode), components, a style-guide page.
- [x] App shell: sidebar on a laptop, bottom bar with a centre "+" on a phone, Ctrl+K palette,
      assistant slide-over, theme toggle.
- [x] Home on today's data: KPIs with sparklines, ranked "Needs you", today, recent activity,
      data freshness — the first decision is on the first phone screen.
- [x] Every section reachable; unbuilt pages say what is coming and open the classic screen.
- [x] Onboarding Studio: businesses by stage; stepper with profile, data map and masters working;
      later stages described.
- [x] `tests/test_web.py` covers the routes, the Studio forms, access rules and the data fixes.

### Later phases (planned)
- [ ] Phase 2 — data core v2 (SQLite per business) + opening position, staged history import
      with review and undo, photo review, entry grid, coverage and sign-off.
- [ ] Phase 3 — communication & documents core; Sales and Operations sections.
- [ ] Phase 4 — Finance, Team (staff logins with enforced roles), Analytics; Inbox, Data, Settings.
- [ ] Phase 5 — the assistant: streaming, new tools, analysis, documents, action cards, evals.
- [ ] Phase 6 — continuous feeds (email-in, watched folder, WhatsApp webhook, Tally connector)
      and onboarding stages 7–8.
- [ ] Phase 7 — hardening, accessibility, performance, security, cutover from the classic UI.

## Status: in-progress (Phase 1 shipped, Phase 2 next)

## Notes / decisions

- ADR 011 — front-end stack; ADR 012 — operator-led onboarding as an eight-stage stepper.
- The new site runs beside the classic screens until cutover; nothing classic was removed.
