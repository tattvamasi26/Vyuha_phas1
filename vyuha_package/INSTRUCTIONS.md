# Vyuha — Founder Dashboard

This package contains everything built so far in this project.

## What's inside

| File | What it is |
|---|---|
| `vyuha_dashboard.html` | The full Vyuha Founder OS dashboard — a single-file HTML app (no server needed) |

That's the only artifact created in this project so far — one self-contained dashboard file.

## What the dashboard does

A single-page founder "operating system" for the Vyuha venture, with a sidebar and 6 workspace sections:

1. **AI Learn** — a 7-day learning plan grid, a video/resource tracker (with links), and free-form notes.
2. **Platform Build** — phased task roadmap (Foundation → Automation Layer → Platform Base) for building the product.
3. **Business** — phased roadmap for client acquisition (Validate → Case Study → Revenue).
4. **Finance** — startup costs, pricing, cashflow, GST/invoicing tasks.
5. **Supply Chain** — domain research and supply-chain intelligence feature tasks.
6. **General** — a catch-all task list, plus a documented list of key business challenges and their proposed solutions (data trust, dirty Excel data, scope creep, pricing resistance, explaining AI value, scaling).

Each section tracks progress with stat counters, progress bars, and sidebar badges showing pending items.

## How to use it

1. **Open it directly**: double-click `vyuha_dashboard.html` — it opens in any browser, no installation needed.
2. **Click through the sidebar** to switch between AI Learn / Platform Build / Business / Finance / Supply Chain / General. Each section has its own accent color.
3. **Add tasks/videos/notes** using the input rows at the bottom of each section, and click checkboxes or day-cells to mark things done.
4. **Save your progress**: click the **Save** button top-right. This uses a persistent key-value storage API (`window.storage`) tied to your account — so if you open this file *as an Artifact inside Claude.ai*, your data will be saved and reloaded automatically the next time you open it there.

   > ⚠️ Note: `window.storage` only works when the HTML is rendered as a **Claude.ai Artifact**. If you just open the raw `.html` file in a plain browser (outside Claude.ai), the Save button will silently fall back to your browser's local storage instead, which is less reliable and won't sync across devices.

5. **Reset**: the Reset button currently only asks for confirmation — it does not yet wipe data (this was a stub in the current version). Let me know if you'd like this wired up to actually clear a section.

## Recommended next steps

- If you want your data to persist and sync across sessions reliably, re-upload/open `vyuha_dashboard.html` as an Artifact inside a Claude.ai chat (rather than opening the raw file locally).
- If you'd like a version that works fully standalone in any browser with local saving (no Claude.ai dependency), let me know and I can add a localStorage-based fallback that's fully wired up.
