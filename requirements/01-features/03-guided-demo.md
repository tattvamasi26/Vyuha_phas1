# 03 — The guided demo: the whole product, live, in front of a prospect

## Description

The founder asked for one button that walks a room through Vyuha end to end — onboarding a
business from nothing, answering the data map, putting the client's own messy files
through, then every screen they would use — **explaining as it goes**, and stoppable at any
moment so a question can be answered or something changed by hand.

The thing it must not be is a recording. A prospect who watches a video has been shown a
claim; a prospect who watches a business get built in front of them has been shown the
product. So the demo *drives the live product*: every action calls the same function the
real screen calls, and every step names a real address.

Built on branch `feature/guided-demo`.

## Acceptance criteria

- [x] **One button.** "Demo" in the top bar for operators, and a control page at `/demo`
      with the whole script, what it will build, and Start / start-from-any-step.
- [x] **Starts from nothing.** Creates the business, answers the eight-record data map,
      fills the profile, adds staff with roles and numbers — each step optionally doing the
      typing, so a presenter can type it themselves instead.
- [x] **Their own files.** Sends the practice pack's stock statement, sales register and
      outstanding list through the *same ingest path an upload uses*, one at a time, then
      lands on the read-back.
- [x] **Every component.** 30 steps over 7 chapters: Studio, data, Home, Sales, Operations,
      Finance, Team/Analytics, Inbox, Settings, the assistant.
- [x] **It explains.** Each step carries what to say out loud, and some carry a presenter
      note that is never said unless asked.
- [x] **Stoppable and open.** Pause (or Escape) restores the app exactly as it was and
      leaves a Resume button; every action is optional; wandering off a step is allowed —
      the tour says so and offers the way back rather than seizing the page.
- [x] **Repeatable.** `POST /demo/reset` deletes the demo business outright, so a rehearsal
      that went sideways is one click from clean.
- [x] **Operators only.** A tenant or a guest gets 403 on the script and the actions.
- [x] `tests/test_demo.py` — 17 tests, including one that fails the build if any step points
      at a page that does not exist.

## Status: shipped (2026-09-23)

## Notes / decisions

- **The script is data** (`demo_tour.STEPS`), like `agents.py` and `routines.py`. Changing
  what the demo says, or reordering a chapter, is editing a list — not touching the driver.
- **No demo mode inside the product.** There is no branch anywhere that behaves differently
  because a demo is running, and no fabricated data: the actions call `store.add_client`,
  `onboarding.save`, `people.add_staff` and `app._ingest`. What the prospect sees is what
  they get, because it *is* what they get.
- **Position lives in the browser** (`localStorage`), because the walk crosses real page
  loads. The server's part is the script as JSON, the actions, and the clear-up.
- `app._ingest` is imported inside the function, not at module scope: `app.py` mounts this
  package's routes near the top of its own import, long before `_ingest` exists.
- The demo business is resolved **by name, under the presenter's own account**, so no
  action can touch a business somebody actually trades on.
- Found while building it: the practice pack's sales register folded the item code into the
  description, so every sold line became a *different* item from the one on the stock
  statement and the shelf showed 45 items instead of 24. The code now travels in its own
  column.
