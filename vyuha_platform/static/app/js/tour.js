/* Vyuha — the guided demo, in the browser.
 *
 * The demo walks across real page loads, because the whole point is that the prospect is
 * looking at the live product and not at a recording of it. So the position lives in
 * localStorage and every page picks the walk up where the last one left off.
 *
 * What the card shows is split deliberately in two: the **point** is one plain sentence in
 * large type that the room reads off the screen, and the **say** underneath is the line the
 * presenter speaks over it. A demo where the presenter reads a paragraph aloud is a demo
 * nobody in the room follows.
 *
 * There is exactly one way through: Next. Chapters announce themselves on the card rather
 * than interrupting with a title screen, because an extra click between chapters is seven
 * extra clicks in front of a customer and buys nothing.
 *
 * Three things it refuses to do:
 *   - trap the presenter: Pause puts the app back exactly as it was, and every action is
 *     optional — type it yourself if the room would rather watch you type;
 *   - fight the presenter: wander off a step and it says so and offers the way back,
 *     rather than dragging the page somewhere;
 *   - pretend: an action calls the real endpoint, and the message it shows afterwards is
 *     the real one, sitting on the screen the change just happened on.
 *
 * No dependencies. Alpine is used only if it happens to be there, for toasts.
 */

(function () {
  "use strict";

  var KEY = "vy-tour";
  var state = { on: false, i: 0, paused: false, result: null, done: {} };
  var script = null;          // { steps, chapters, status } — fetched once per page
  var ui = null;              // the overlay, built lazily
  var pill = null;
  var frame = 0;

  // ------------------------------------------------------------------ state

  function read() {
    try {
      var raw = JSON.parse(localStorage.getItem(KEY) || "{}");
      return {
        on: !!raw.on, i: raw.i || 0, paused: !!raw.paused,
        result: raw.result || null, done: raw.done || {}
      };
    } catch (e) {
      return { on: false, i: 0, paused: false, result: null, done: {} };
    }
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private mode */ }
  }

  function load() {
    if (script) return Promise.resolve(script);
    return fetch("/demo/steps.json", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) { script = d && d.ok ? d : { steps: [], chapters: [] }; return script; })
      .catch(function () { script = { steps: [], chapters: [] }; return script; });
  }

  function step() {
    if (!script || !script.steps.length) return null;
    var i = Math.max(0, Math.min(state.i, script.steps.length - 1));
    return script.steps[i];
  }

  function toast(text, kind) {
    if (!text) return;
    if (window.Alpine && window.Alpine.store && window.Alpine.store("toasts")) {
      window.Alpine.store("toasts").push(text, kind || "ok");
    }
  }

  // --------------------------------------------------------------- the card

  function build() {
    if (ui) return ui;
    var mask = document.createElement("div");
    mask.className = "vt-mask";

    var card = document.createElement("div");
    card.className = "vt-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", "Guided demo");
    card.innerHTML =
      '<div class="vt-rail" aria-hidden="true"></div>' +
      '<div class="vt-meta"><span class="vt-chapter"></span><span class="vt-where"></span></div>' +
      '<p class="vt-chapline" hidden></p>' +
      '<p class="vt-point"></p>' +
      '<p class="vt-say"></p>' +
      '<p class="vt-result" hidden></p>' +
      '<button type="button" class="vt-do" hidden></button>' +
      '<details class="vt-note" hidden><summary>For you, not them</summary><p></p></details>' +
      '<div class="vt-foot">' +
      '<button type="button" class="vt-back" aria-label="Previous step">&#8249;</button>' +
      '<button type="button" class="vt-next">Next</button>' +
      '<span class="vt-hint"></span>' +
      '<button type="button" class="vt-pause" title="Pause — the app stays usable (Esc)">Pause</button>' +
      '<button type="button" class="vt-exit" title="End the demo">End</button>' +
      "</div>";

    document.body.appendChild(mask);
    document.body.appendChild(card);

    ui = {
      mask: mask, card: card,
      rail: card.querySelector(".vt-rail"),
      chapter: card.querySelector(".vt-chapter"),
      where: card.querySelector(".vt-where"),
      chapline: card.querySelector(".vt-chapline"),
      point: card.querySelector(".vt-point"),
      say: card.querySelector(".vt-say"),
      result: card.querySelector(".vt-result"),
      doBtn: card.querySelector(".vt-do"),
      note: card.querySelector(".vt-note"),
      noteText: card.querySelector(".vt-note p"),
      back: card.querySelector(".vt-back"),
      next: card.querySelector(".vt-next"),
      hint: card.querySelector(".vt-hint"),
      pause: card.querySelector(".vt-pause"),
      exit: card.querySelector(".vt-exit")
    };

    ui.back.addEventListener("click", function () { go(state.i - 1); });
    ui.next.addEventListener("click", function () { go(state.i + 1); });
    ui.pause.addEventListener("click", pause);
    ui.exit.addEventListener("click", stop);
    return ui;
  }

  function teardown() {
    if (ui) { ui.mask.remove(); ui.card.remove(); ui = null; }
  }

  function showPill() {
    if (pill) return;
    pill = document.createElement("button");
    pill.type = "button";
    pill.className = "vt-pill";
    pill.innerHTML = 'Resume demo <span aria-hidden="true">&#9654;</span>';
    pill.addEventListener("click", resume);
    document.body.appendChild(pill);
  }

  function hidePill() { if (pill) { pill.remove(); pill = null; } }

  // ------------------------------------------------------------- positioning

  function place(el) {
    var u = build();
    var pad = 8;
    var vw = window.innerWidth, vh = window.innerHeight;

    if (!el) {
      u.mask.classList.add("is-flat");
      u.mask.style.cssText = "top:50%;left:50%;width:0;height:0";
      u.card.style.left = Math.max(12, (vw - u.card.offsetWidth) / 2) + "px";
      u.card.style.top = Math.max(12, (vh - u.card.offsetHeight) / 2) + "px";
      return;
    }

    u.mask.classList.remove("is-flat");
    var r = el.getBoundingClientRect();
    u.mask.style.top = (r.top - pad) + "px";
    u.mask.style.left = (r.left - pad) + "px";
    u.mask.style.width = (r.width + pad * 2) + "px";
    u.mask.style.height = (r.height + pad * 2) + "px";

    // Beside the target where there is room, below it otherwise, and never off-screen.
    var cw = u.card.offsetWidth, ch = u.card.offsetHeight;
    var left, top;
    if (vw - r.right > cw + 28) left = r.right + 18;
    else if (r.left > cw + 28) left = r.left - cw - 18;
    else left = Math.max(12, Math.min(vw - cw - 12, r.left + r.width / 2 - cw / 2));
    top = r.top + r.height / 2 - ch / 2;
    top = Math.max(12, Math.min(vh - ch - 12, top));
    u.card.style.left = left + "px";
    u.card.style.top = top + "px";
  }

  function reposition() {
    if (!ui || !state.on || state.paused) return;
    var s = step();
    if (!s) return;
    place(s.target ? document.querySelector(s.target) : null);
  }

  function onScrollOrResize() {
    if (frame) return;
    frame = window.requestAnimationFrame(function () { frame = 0; reposition(); });
  }

  // ---------------------------------------------------------------- chrome

  function paintRail(s) {
    var u = build();
    if (u.rail.childElementCount !== (script.chapters || []).length) {
      u.rail.innerHTML = "";
      (script.chapters || []).forEach(function (c) {
        var dot = document.createElement("i");
        dot.className = "vt-dot";
        dot.title = c.label;
        u.rail.appendChild(dot);
      });
    }
    Array.prototype.forEach.call(u.rail.children, function (dot, n) {
      dot.className = "vt-dot"
        + (n + 1 < s.chapter_index ? " is-done" : "")
        + (n + 1 === s.chapter_index ? " is-on" : "");
    });
  }

  function showResult(u) {
    if (state.result && state.result.text) {
      u.result.hidden = false;
      u.result.className = "vt-result " + (state.result.ok ? "is-ok" : "is-bad");
      u.result.textContent = (state.result.ok ? "✓ " : "") + state.result.text;
    } else {
      u.result.hidden = true;
    }
  }

  // -------------------------------------------------------------- rendering

  function offPath(s) {
    var u = build();
    paintRail(s);
    u.chapter.textContent = "Off the path";
    u.where.textContent = "";
    u.chapline.hidden = true;
    u.point.textContent = "Carry on — nothing is lost.";
    u.say.textContent = 'When you want the demo back, it is waiting at "' + s.title + '".';
    u.result.hidden = true;
    u.note.hidden = true;
    u.doBtn.hidden = false;
    u.doBtn.disabled = false;
    u.doBtn.className = "vt-do";
    u.doBtn.textContent = "Back to the demo";
    u.doBtn.onclick = function () { window.location.href = s.page; };
    u.back.disabled = false;
    u.next.textContent = "Next";
    u.hint.textContent = "";
    place(null);
  }

  function render() {
    var s = step();
    if (!s) return;
    if (s.page && s.page !== window.location.pathname) { offPath(s); return; }

    var u = build();
    paintRail(s);
    u.chapter.textContent = s.chapter_label;
    u.where.textContent = s.step_in_chapter + " of " + s.steps_in_chapter;

    // A chapter says what it is and what it proves on its own first step — no title
    // screen to click past.
    u.chapline.hidden = !s.first_in_chapter;
    u.chapline.textContent = s.first_in_chapter ? s.chapter_proves : "";

    u.point.textContent = s.point;
    u.say.textContent = s.say;
    showResult(u);

    u.note.hidden = !s.note;
    u.noteText.textContent = s.note || "";

    if (s.action) {
      var done = !!state.done[s.key];
      u.doBtn.hidden = false;
      u.doBtn.disabled = done;
      u.doBtn.className = "vt-do" + (done ? " is-done" : "");
      u.doBtn.textContent = done ? "✓ Done" : (s.action_label || "Do it");
      u.doBtn.onclick = done ? null : function () { act(s, u.doBtn); };
    } else {
      u.doBtn.hidden = true;
      u.doBtn.onclick = null;
    }

    u.back.disabled = state.i === 0;
    u.next.textContent = state.i === script.steps.length - 1 ? "Finish" : "Next";
    u.hint.textContent = (s.i + 1) + " / " + script.steps.length;

    var el = s.target ? document.querySelector(s.target) : null;
    if (el && el.scrollIntoView) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      window.setTimeout(function () { place(el); }, 260);
    }
    place(el);
  }

  // --------------------------------------------------------------- actions

  function act(s, btn) {
    btn.disabled = true;
    var was = btn.textContent;
    btn.textContent = "Working…";
    fetch("/demo/act/" + s.action, { method: "POST", credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) {
          toast(res.message, "bad");
          state.result = { ok: false, text: res.message };
          save();
          btn.disabled = false;
          btn.textContent = was;
          showResult(build());
          return;
        }
        // Keep the proof on screen: the result is shown on whichever step the change
        // actually happened on, so the room sees the message and the changed page
        // together rather than a toast that vanishes. And the button will not run
        // twice — a second import of the same file looks like a bug to a customer.
        state.result = { ok: true, text: res.message };
        state.done[s.key] = true;
        script = null;                       // the slug may have only just come to exist
        load().then(function (fresh) {
          var dest = res.go || window.location.pathname;
          var cur = fresh.steps[state.i];
          if (!cur || cur.page !== dest) {
            for (var n = state.i; n < fresh.steps.length; n++) {
              if (fresh.steps[n].page === dest) { state.i = n; break; }
            }
          }
          save();
          if (dest && dest !== window.location.pathname) window.location.href = dest;
          else window.location.reload();
        });
      })
      .catch(function () {
        toast("That did not reach the server. Try again.", "bad");
        btn.disabled = false;
        btn.textContent = was;
      });
  }

  // -------------------------------------------------------------- the walk

  function go(i) {
    if (!script || !script.steps.length) return;
    if (i >= script.steps.length) { stop(); toast("Demo finished.", "ok"); return; }
    state.i = Math.max(0, i);
    state.result = null;                     // a new step: the last one's proof goes away
    state.on = true;
    save();
    var s = script.steps[state.i];
    if (s.page && s.page !== window.location.pathname) {
      window.location.href = s.page;
      return;
    }
    render();
  }

  function start(i) {
    state = { on: true, i: i || 0, paused: false, result: null, done: {} };
    save();
    hidePill();
    load().then(function () { go(state.i); });
  }

  function pause() {
    state.paused = true; save();
    teardown(); showPill();
  }

  function resume() {
    state.paused = false; save();
    hidePill();
    load().then(function () { go(state.i); });
  }

  function stop() {
    state = { on: false, i: 0, paused: false, result: null, done: {} };
    save();
    teardown(); hidePill();
  }

  // ------------------------------------------------------------------ wire

  function boot() {
    state = read();
    if (!state.on) return;
    if (state.paused) { showPill(); return; }
    load().then(function (s) {
      if (!s.steps.length) { stop(); return; }
      render();
    });
  }

  document.addEventListener("keydown", function (e) {
    if (!state.on || state.paused || !ui) return;
    var t = e.target || {};
    if (/^(input|textarea|select)$/i.test(t.tagName || "") || t.isContentEditable) return;
    if (e.key === "ArrowRight") { e.preventDefault(); go(state.i + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(state.i - 1); }
    else if (e.key === "Escape") { e.preventDefault(); pause(); }
  });

  window.addEventListener("scroll", onScrollOrResize, { passive: true });
  window.addEventListener("resize", onScrollOrResize);

  window.VyuhaTour = { start: start, resume: resume, pause: pause, stop: stop };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
