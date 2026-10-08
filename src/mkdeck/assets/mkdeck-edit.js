/*! mkdeck — edit slide text on the page.
 *
 * Only `mkdeck serve` loads this, and only for a Markdown deck served from this
 * machine. Double-click a title, a sentence, a bullet or a table cell to edit
 * its Markdown. The dev server writes the edit into the deck file, and the
 * page reloads on the rebuild as it does after an edit made in an editor.
 *
 *   Enter          save
 *   Shift+Enter    a new paragraph in a sentence, a new bullet in a bullet
 *   Esc            cancel
 *
 * Text the server cannot trace to one place in the file, such as a title set
 * in the slide options, is not marked and cannot be edited here.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var endpoint = script && script.getAttribute("data-endpoint");
  var token = null;
  var open = null; // the editor in use: { box, hint, target }

  var HINTS = {
    title: "Enter to save, Esc to cancel",
    sentence: "Enter to save, Shift+Enter for a new paragraph, Esc to cancel",
    bullet: "Enter to save, Shift+Enter for a new bullet, Esc to cancel",
    cell: "Enter to save, Esc to cancel"
  };

  var STYLE =
    "[data-mkd-edit]{cursor:text}" +
    ".mkd-edit-box{position:fixed;z-index:2147483646;box-sizing:border-box;margin:0;padding:6px 8px;" +
    "resize:none;overflow:hidden;border:1px solid var(--mkd-line,#ccc);border-radius:6px;" +
    "background:var(--mkd-surface,#fff);color:var(--mkd-ink,#111);box-shadow:0 4px 16px rgba(0,0,0,.12);" +
    "outline:none}" +
    ".mkd-edit-hint{position:fixed;z-index:2147483646;margin:0;padding:2px 6px;white-space:nowrap;" +
    "border-radius:4px;background:var(--mkd-surface,#fff);" +
    "font:12px/1.4 system-ui,sans-serif;color:var(--mkd-grey,#666)}" +
    ".mkd-edit-hint[data-error]{color:#b42318}";

  function kind(target) {
    return target.getAttribute("data-mkd-edit").split(":")[0];
  }

  function shownText(target) {
    var text = target.getAttribute("data-mkd-text");
    // A bullet is one line per bullet here, so a wrapped bullet shows on one line.
    return kind(target) === "bullet" ? text.replace(/\s*\n\s*/g, " ") : text;
  }

  function place() {
    var rect = open.target.getBoundingClientRect();
    var width = Math.max(rect.width + 24, 240); // room for the padding, so the text wraps as it does on the slide
    var left = Math.min(Math.max(rect.left - 8, 8), window.innerWidth - width - 8);
    open.box.style.left = left + "px";
    open.box.style.top = rect.top - 6 + "px";
    open.box.style.width = width + "px";
    open.box.style.height = "auto";
    open.box.style.height = open.box.scrollHeight + 2 + "px";
    var box = open.box.getBoundingClientRect();
    open.hint.style.left = box.left + "px";
    open.hint.style.top = box.bottom + 4 + "px";
  }

  function close() {
    if (!open) {
      return;
    }
    var editor = open;
    open = null;
    window.removeEventListener("resize", place);
    editor.box.remove();
    editor.hint.remove();
  }

  function fail(message) {
    open.hint.setAttribute("data-error", "");
    open.hint.textContent = message;
    open.box.disabled = false;
    open.box.focus();
  }

  function save() {
    var target = open.target;
    var text = open.box.value;
    if (text === shownText(target)) {
      close();
      return;
    }
    open.box.disabled = true;
    open.hint.removeAttribute("data-error");
    open.hint.textContent = "Saving";
    var editor = open;
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Mkdeck-Token": token },
      body: JSON.stringify({
        slide: Number(target.closest("[data-mkd-slide]").getAttribute("data-mkd-slide")),
        key: target.getAttribute("data-mkd-edit"),
        expected: target.getAttribute("data-mkd-text"),
        text: text
      })
    })
      .then(function (response) {
        return response.json().then(function (body) {
          if (open !== editor) {
            return;
          }
          if (response.ok) {
            open.hint.textContent = "Saved, waiting for the rebuild";
          } else {
            fail(body.error || "The edit was not saved.");
          }
        });
      })
      .catch(function () {
        if (open === editor) {
          fail("The dev server did not answer; is mkdeck serve still running?");
        }
      });
  }

  function onKey(event) {
    event.stopPropagation(); // keep reveal's keys (space, arrows, r) out of the box
    var what = kind(open.target);
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      save();
    } else if (event.key === "Enter" && event.shiftKey) {
      event.preventDefault();
      if (what === "sentence" || what === "bullet") {
        // A single line break in a paragraph renders as a space, so a sentence takes a blank line.
        document.execCommand("insertText", false, what === "sentence" ? "\n\n" : "\n");
      }
    }
  }

  function edit(target) {
    close();
    var style = window.getComputedStyle(target);
    var box = document.createElement("textarea");
    box.className = "mkd-edit-box";
    box.spellcheck = true;
    box.value = shownText(target);
    box.style.font = style.font;
    box.style.letterSpacing = style.letterSpacing;
    var hint = document.createElement("p");
    hint.className = "mkd-edit-hint";
    hint.textContent = HINTS[kind(target)] || HINTS.title;
    document.body.appendChild(box);
    document.body.appendChild(hint);
    open = { box: box, hint: hint, target: target };
    place();
    box.addEventListener("keydown", onKey);
    box.addEventListener("keyup", function (event) {
      event.stopPropagation();
    });
    box.addEventListener("input", place);
    box.addEventListener("blur", function () {
      // A click elsewhere on the page saves; leaving the window keeps the box open.
      if (open && open.box === box && !box.disabled && document.hasFocus()) {
        save();
      }
    });
    window.addEventListener("resize", place);
    box.focus();
    if (kind(target) === "title" || kind(target) === "cell") {
      box.select(); // a short piece is usually rewritten, so typing replaces it
    } else {
      box.setSelectionRange(box.value.length, box.value.length);
    }
  }

  function start() {
    var style = document.createElement("style");
    style.textContent = STYLE;
    document.head.appendChild(style);
    document.addEventListener("dblclick", function (event) {
      var target = event.target.closest && event.target.closest("[data-mkd-edit]");
      if (target && target.closest("section.present")) {
        event.preventDefault();
        edit(target);
      }
    });
    if (window.Reveal && typeof window.Reveal.on === "function") {
      window.Reveal.on("slidechanged", close);
    }
  }

  if (!endpoint || !window.fetch) {
    return;
  }
  fetch(endpoint, { cache: "no-store" })
    .then(function (response) {
      return response.ok ? response.json() : null;
    })
    .then(function (body) {
      if (body && body.token) {
        token = body.token;
        start();
      }
    })
    .catch(function () {});
})();
