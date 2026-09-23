/* Vyuha — the guided demo, in the browser.
 *
 * The demo walks across real page loads, because the whole point is that the prospect is
 * looking at the live product and not at a recording of it. So the position lives in
 * localStorage and every page picks the walk up where the last one left off.
 *
 * Three things it refuses to do:
 *   - trap the presenter: Pause puts the app back exactly as it was, and every action is
 *     optional — type it yourself if the room would rather watch you type;
 *   - fight the presenter: wander off a step and it says so and offers the way back,
 *     rather than dragging the page somewhere;
 *   - pretend: an action calls the real endpoint and the message it shows is the real one.
 *
 * No dependencies. Alpine is used only if it happens to be there, for toasts.
 */

(function () {
  "use strict";

  var KEY = "vy-tour";
  var state = { on: false, i: 0, paused: false };
  var script = null;          // { steps, chapters, status } — fetched once per page
  var ui = null;              // the overlay, built lazily
  var pill = null;
  var frame = 0;

  // ------------------------------------------------------------------ state

  function read() {
    try {
      var raw = JSON.parse(localStorage.getItem(KEY) || "{}");
      return { on: !!raw.on, i: raw.i || 0, paused: !!raw.paused };
    } catch (e) { return { on: false, i: 0, paused: false }; }
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
    } else {
      window.console && console.log("[demo]", text);
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
      '<div class="vt-head"><span class="vt-chapter"></span><span class="vt-count"></span></div>' +
      '<h2 class="vt-title"></h2>' +
      '<p class="vt-say"></p>' +
      '<details class="vt-note" hidden><summary>For you, not them</summary><p></p></details>' +
      '<button type="button" class="vt-do" hidden></button>' +
      '<div class="vt-bar">' +
      '<button type="button" class="vt-back">Back</button>' +
      '<button type="button" class="vt-next">Next</button>' +
      '<span class="vt-sp"></span>' +
      '<select class="vt-jump" aria-label="Jump to a chapter"></select>' +
      '<button type="button" class="vt-pause">Pause</button>' +
      '<button type="button" class="vt-exit">End</button>' +
      "</div>" +
      '<div class="vt-progress"><i></i></div>';

    document.body.appendChild(mask);
    document.body.appendChild(card);

    ui = {
      mask: mask, card: card,
      chapter: card.querySelector(".vt-chapter"),
      count: card.querySelector(".vt-count"),
      title: card.querySelector(".vt-title"),
      say: card.querySelector(".vt-say"),
      note: card.querySelector(".vt-note"),
      noteText: card.querySelector(".vt-note p"),
      doBtn: card.querySelector(".vt-do"),
      back: card.querySelector(".vt-back"),
      next: card.querySelector(".vt-next"),
      jump: card.querySelector(".vt-jump"),
      pause: card.querySelector(".vt-pause"),
      exit: card.querySelector(".vt-exit"),
      bar: card.querySelector(".vt-progress i")
    };

    ui.back.addEventListener("click", function () { go(state.i - 1); });
    ui.next.addEventListener("click", function () { go(state.i + 1); });
    ui.pause.addEventListener("click", pause);
    ui.exit.addEventListener("click", stop);
    ui.jump.addEventListener("change", function () {
      var i = parseInt(ui.jump.value, 10);
      if (!isNaN(i)) go(i);
    });
    return ui;
  }

  function teardown() {
    if (ui) {
      ui.mask.remove();
      ui.card.remove();
      ui = null;
    }
  }

  function showPill() {
    if (pill) return;
    pill = document.createElement("button");
    pill.type = "button";
    pill.className = "vt-pill";
    pill.innerHTML = 'Resume demo <span>&#9654;</span>';
    pill.addEventListener("click", resume);
    document.body.appendChild(pill);
  }

  function hidePill() {
    if (pill) { pill.remove(); pill = null; }
  }

  // ------------------------------------------------------------- rendering

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

    // Below the target if it fits, above if not, and never off the side.
    var cw = u.card.offsetWidth, ch = u.card.offsetHeight;
    var top = r.bottom + 14;
    if (top + ch > vh - 12) top = r.top - ch - 14;
    if (top < 12) top = Math.max(12, Math.min(vh - ch - 12, r.top));
    var left = r.left + r.width / 2 - cw / 2;
    left = Math.max(12, Math.min(vw - cw - 12, left));
    u.card.style.top = top + "px";
    u.card.style.left = left + "px";
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

  function offPath(s) {
    var u = build();
    u.chapter.textContent = "Off the path";
    u.count.textContent = (state.i + 1) + " / " + script.steps.length;
    u.title.textContent = "You have wandered off";
    u.say.className = "vt-say is-off";
    u.say.textContent = 'Carry on as long as you like — nothing is lost. When you want the '
      + 'demo back, it is waiting at "' + s.title + '".';
    u.note.hidden = true;
    u.doBtn.hidden = false;
    u.doBtn.disabled = false;
    u.doBtn.textContent = "Back to the demo";
    u.doBtn.onclick = function () { window.location.href = s.path; };
    u.bar.style.width = ((state.i + 1) / script.steps.length * 100) + "%";
    fillJump();
    place(null);
  }

  function fillJump() {
    var u = build();
    if (u.jump.options.length) return;
    (script.chapters || []).forEach(function (c) {
      var first = -1;
      script.steps.forEach(function (s, i) { if (first < 0 && s.chapter === c.key) first = i; });
      if (first < 0) return;
      var opt = document.createElement("option");
      opt.value = String(first);
      opt.textContent = c.label;
      u.jump.appendChild(opt);
    });
  }

  function render() {
    var s = step();
    if (!s) return;
    var here = window.location.pathname;

    if (s.path && s.path !== here) { offPath(s); return; }

    var u = build();
    u.chapter.textContent = s.chapter_label || "";
    u.count.textContent = (state.i + 1) + " / " + script.steps.length;
    u.title.textContent = s.title;
    u.say.className = "vt-say";
    u.say.textContent = s.say;

    u.note.hidden = !s.note;
    u.noteText.textContent = s.note || "";

    if (s.action) {
      u.doBtn.hidden = false;
      u.doBtn.disabled = false;
      u.doBtn.textContent = s.action_label || "Do it";
      u.doBtn.onclick = function () { act(s, u.doBtn); };
    } else {
      u.doBtn.hidden = true;
      u.doBtn.onclick = null;
    }

    u.back.disabled = state.i === 0;
    u.next.textContent = state.i === script.steps.length - 1 ? "Finish" : "Next";
    u.bar.style.width = ((state.i + 1) / script.steps.length * 100) + "%";
    fillJump();
    var chapterStart = -1;
    script.steps.forEach(function (st, i) {
      if (st.chapter === s.chapter && chapterStart < 0) chapterStart = i;
    });
    u.jump.value = String(chapterStart);

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
        toast(res.message, res.ok ? "ok" : "bad");
        if (!res.ok) { btn.disabled = false; btn.textContent = was; return; }
        // The business may have only just come into existence, so every address in the
        // script has to be fetched again before we decide where to go.
        script = null;
        state.i = Math.min(state.i + 1, 999);
        save();
        load().then(function (fresh) {
          state.i = Math.min(state.i, fresh.steps.length - 1);
          save();
          var nextStep = fresh.steps[state.i];
          var dest = (nextStep && nextStep.path) || res.go || window.location.pathname;
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

  // ------------------------------------------------------------- the walk

  function go(i) {
    if (!script || !script.steps.length) return;
    if (i >= script.steps.length) { stop(); toast("Demo finished.", "ok"); return; }
    state.i = Math.max(0, i);
    save();
    var s = script.steps[state.i];
    if (s.path && s.path !== window.location.pathname) {
      window.location.href = s.path;
      return;
    }
    render();
  }

  function start(i) {
    state = { on: true, i: i || 0, paused: false };
    save();
    hidePill();
    load().then(function () { go(state.i); });
  }

  function pause() {
    state.paused = true;
    save();
    teardown();
    showPill();
  }

  function resume() {
    state.paused = false;
    save();
    hidePill();
    load().then(function () { go(state.i); });
  }

  function stop() {
    state = { on: false, i: 0, paused: false };
    save();
    teardown();
    hidePill();
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
    var typing = /^(input|textarea|select)$/i.test(t.tagName || "")
      || t.isContentEditable;
    if (typing) return;
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
