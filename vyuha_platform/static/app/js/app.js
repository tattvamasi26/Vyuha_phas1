/* Vyuha — the little JavaScript the site needs, all of it Alpine stores and components.
 *
 * Loaded before Alpine itself (both deferred, in document order), so everything here is
 * registered on `alpine:init` before any component on the page is initialised.
 */

document.addEventListener("alpine:init", () => {
  const Alpine = window.Alpine;

  // Light by default — the site is read in daylight — dark only if chosen.
  Alpine.store("theme", {
    dark: document.documentElement.classList.contains("dark"),
    toggle() {
      this.dark = !this.dark;
      document.documentElement.classList.toggle("dark", this.dark);
      try { localStorage.setItem("vy-theme", this.dark ? "dark" : "light"); } catch (e) { /* private mode */ }
    },
  });

  // Which overlay is open. One store, so opening one can close the rest.
  Alpine.store("ui", {
    assistant: false, more: false, quick: false, drawer: false,
    closeAll() { this.assistant = this.more = this.quick = this.drawer = false; },
  });

  Alpine.store("toasts", {
    items: [],
    push(text, kind = "ok") {
      if (!text) return;
      const id = Date.now() + Math.random();
      this.items.push({ id, text, kind });
      setTimeout(() => this.dismiss(id), 5000);
    },
    dismiss(id) { this.items = this.items.filter((t) => t.id !== id); },
  });

  // Command palette: jump anywhere, do the common things, from the keyboard.
  Alpine.data("palette", (items) => ({
    open: false,
    q: "",
    active: 0,
    items: items || [],
    get results() {
      const words = this.q.toLowerCase().split(/\s+/).filter(Boolean);
      const hits = !words.length ? this.items : this.items.filter((it) => {
        const hay = `${it.label} ${it.hint || ""} ${it.group || ""}`.toLowerCase();
        return words.every((w) => hay.includes(w));
      });
      return hits.slice(0, 14);
    },
    show() {
      this.open = true; this.q = ""; this.active = 0;
      this.$nextTick(() => this.$refs.q && this.$refs.q.focus());
    },
    close() { this.open = false; },
    toggle() { this.open ? this.close() : this.show(); },
    move(step) {
      const n = this.results.length;
      if (n) this.active = (this.active + step + n) % n;
      this.$nextTick(() => {
        const el = this.$refs.list && this.$refs.list.querySelector(".is-active");
        if (el) el.scrollIntoView({ block: "nearest" });
      });
    },
    go(index) {
      const it = this.results[index ?? this.active];
      if (it) window.location.href = it.href;
    },
  }));

  // A grid of rows that grows as you type — quick item entry in the Studio.
  Alpine.data("rows", (blank, start = 3) => ({
    rows: Array.from({ length: start }, () => ({ ...blank })),
    add() { this.rows.push({ ...blank }); },
    remove(i) { if (this.rows.length > 1) this.rows.splice(i, 1); },
  }));
});

document.addEventListener("alpine:initialized", () => {
  // A flash message from a redirect (?m=...&k=...) becomes a toast, and leaves the URL.
  const body = document.body;
  if (body && body.dataset.flash) {
    window.Alpine.store("toasts").push(body.dataset.flash, body.dataset.flashKind || "ok");
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete("m");
      url.searchParams.delete("k");
      window.history.replaceState({}, "", url.toString());
    } catch (e) { /* old browser: leave it */ }
  }
});

// Server-sent toasts: a response with `HX-Trigger: {"toast": {"text": "...", "kind": "ok"}}`.
document.addEventListener("toast", (e) => {
  const d = (e && e.detail) || {};
  if (window.Alpine) window.Alpine.store("toasts").push(d.text || d.value || "", d.kind || "ok");
});
