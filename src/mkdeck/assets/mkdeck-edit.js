/*! mkdeck — edit the deck on the page.
 *
 * Only `mkdeck serve` loads this, and only for a Markdown deck served from this
 * machine. The dev server writes every edit into the deck file, and the page
 * reloads on the rebuild as it does after an edit made in an editor.
 *
 * Two ways in:
 *
 *   the edit button (top right, faint until you point at it) or the e key
 *       opens the Markdown of the whole slide in a popover.
 *       Cmd/Ctrl+Enter saves, Esc closes.
 *   a double-click on a title, a sentence, a bullet or a table cell
 *       edits that text in place. Enter saves, Esc cancels, Shift+Enter
 *       starts a new paragraph in a sentence and a new bullet in a bullet.
 *
 * The export button under it downloads the deck, with every saved edit, as one
 * HTML file: what `mkdeck build --single-file` writes.
 *
 * An unsaved slide edit is kept in sessionStorage, so a reload (yours, or the
 * one an edit in your editor causes) reopens it with your text.
 *
 * The look follows shadcn's popover, button and kbd, drawn from the deck
 * theme's tokens so it sits on a light or a dark deck.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var endpoint = script && script.getAttribute("data-endpoint");
  var exportPath = script && script.getAttribute("data-export");
  var token = null;
  var inline = null; // the open inline editor: { box, hint, target }
  var panel = null; // the open slide editor: { root, box, status, save, slide, expected }
  var button = null; // the edit button
  var exporter = null; // the export button
  var tip = null;
  var notice = null; // the export's progress or outcome, beside its button
  var noticeTimer = 0;
  var tipTimer = 0;
  var DRAFT_KEY = "mkdeck-edit-draft";
  var MAC = /Mac|iPhone|iPad/.test(navigator.platform || "");
  var MOD = MAC ? "⌘" : "Ctrl";

  var STYLE = [
    ":root{--mkde-fg:var(--mkd-ink,#111);--mkde-bg:var(--mkd-surface,#fff);",
    "--mkde-popover:var(--mkde-bg);",
    "--mkde-muted:color-mix(in oklab,var(--mkde-fg) 6%,var(--mkde-bg));",
    "--mkde-muted-fg:color-mix(in oklab,var(--mkde-fg) 60%,var(--mkde-bg));",
    "--mkde-border:color-mix(in oklab,var(--mkde-fg) 14%,var(--mkde-bg));",
    "--mkde-ring:color-mix(in oklab,var(--mkde-fg) 45%,var(--mkde-bg));",
    "--mkde-destructive:oklch(0.577 0.245 27.325);",
    "--mkde-font:var(--mkd-font,system-ui,sans-serif)}",
    "html[data-theme=dark]{--mkde-popover:color-mix(in oklab,var(--mkde-fg) 7%,var(--mkde-bg));",
    "--mkde-destructive:oklch(0.704 0.191 22.216)}",
    // the floating layer: shadcn's popover surface
    ".mkde-float{position:fixed;z-index:2147483646;box-sizing:border-box;background:var(--mkde-popover);",
    "color:var(--mkde-fg);border-radius:8px;box-shadow:0 0 0 1px color-mix(in oklab,var(--mkde-fg) 10%,transparent),",
    "0 4px 6px -1px rgb(0 0 0/.1),0 2px 4px -2px rgb(0 0 0/.1);font:400 14px/20px var(--mkde-font);",
    "animation:mkde-in 100ms ease-out}",
    "@keyframes mkde-in{from{opacity:0;transform:scale(.95)}}",
    "@media (prefers-reduced-motion:reduce){.mkde-float{animation:none}}",
    // the edit and export buttons: shadcn ghost icon buttons, size sm, faint at rest so an
    // audience does not notice them
    ".mkde-bar{position:fixed;top:12px;right:12px;z-index:2147483645;display:flex;flex-direction:column;gap:4px}",
    ".mkde-trigger{display:grid;place-items:center;",
    "width:28px;height:28px;padding:0;border:0;border-radius:6px;background:transparent;opacity:.3;",
    "color:var(--mkde-muted-fg);cursor:pointer;transition:background-color 150ms,color 150ms,opacity 150ms}",
    ".mkde-trigger:hover,.mkde-trigger:focus-visible,.mkde-trigger[aria-expanded=true],",
    ".mkde-trigger[aria-busy=true]{opacity:1}",
    ".mkde-trigger:hover,.mkde-trigger[aria-expanded=true]{background:var(--mkde-muted);color:var(--mkde-fg)}",
    ".mkde-trigger[aria-busy=true]{cursor:progress}",
    ".mkde-trigger[aria-busy=true] svg{animation:mkde-pulse 1s ease-in-out infinite alternate}",
    "@keyframes mkde-pulse{to{opacity:.35}}",
    "@media (prefers-reduced-motion:reduce){.mkde-trigger[aria-busy=true] svg{animation:none}}",
    ".mkde-trigger:focus-visible{outline:none;box-shadow:0 0 0 3px color-mix(in oklab,var(--mkde-ring) 50%,transparent)}",
    ".mkde-trigger[aria-disabled=true]{opacity:.3;cursor:default;background:transparent;color:var(--mkde-muted-fg)}",
    ".mkde-trigger svg{width:16px;height:16px}",
    "@media print{.mkde-bar{display:none}}",
    // tooltip
    ".mkde-tip{padding:4px 8px;font-size:12px;line-height:16px;display:flex;gap:8px;align-items:center;",
    "white-space:nowrap;pointer-events:none}",
    ".mkde-tip[data-error]{color:var(--mkde-destructive);white-space:normal;max-width:320px}",
    // kbd
    ".mkde-kbd{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;",
    "padding:0 4px;border-radius:4px;background:var(--mkde-muted);color:var(--mkde-muted-fg);",
    "font:500 12px/1 var(--mkde-font);box-sizing:border-box}",
    // the slide editor
    // beside the buttons, so the export button stays in reach
    ".mkde-panel{top:12px;right:48px;width:min(560px,calc(100vw - 60px));padding:8px;display:grid;gap:8px}",
    ".mkde-source{display:block;box-sizing:border-box;width:100%;min-height:160px;max-height:60vh;margin:0;",
    "padding:8px;resize:vertical;border:1px solid var(--mkde-border);border-radius:6px;background:var(--mkde-bg);",
    "color:var(--mkde-fg);font:400 13px/20px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;",
    "tab-size:2;outline:none;transition:border-color 150ms}",
    // a text box being edited gets a border in the text colour, and no glow
    ".mkde-source:focus,.mkde-inline:focus{border-color:var(--mkde-fg)}",
    ".mkde-source:disabled{opacity:.6}",
    ".mkde-row{display:flex;align-items:center;gap:8px;min-width:0}",
    ".mkde-status{flex:1 1 auto;min-width:0;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
    "font-size:12px;line-height:16px;color:var(--mkde-muted-fg)}",
    ".mkde-status[data-error]{color:var(--mkde-destructive);white-space:normal}",
    // buttons: shadcn outline and default, size sm
    ".mkde-btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:6px;",
    "font:500 14px/20px var(--mkde-font);cursor:pointer;white-space:nowrap;",
    "transition:background-color 150ms,opacity 150ms;border:1px solid transparent}",
    ".mkde-btn:active{transform:translateY(1px)}",
    ".mkde-btn:focus-visible{outline:none;box-shadow:0 0 0 3px color-mix(in oklab,var(--mkde-ring) 50%,transparent)}",
    ".mkde-btn:disabled{opacity:.5;cursor:default;transform:none}",
    ".mkde-outline{background:var(--mkde-bg);color:var(--mkde-fg);border-color:var(--mkde-border)}",
    ".mkde-outline:hover{background:var(--mkde-muted)}",
    ".mkde-primary{background:var(--mkde-fg);color:var(--mkde-bg)}",
    ".mkde-primary:hover{opacity:.9}",
    ".mkde-primary .mkde-kbd{background:color-mix(in oklab,var(--mkde-bg) 20%,transparent);color:inherit}",
    // the inline editor
    "[data-mkd-edit]{cursor:text}",
    ".mkde-inline{margin:0;padding:6px 8px;resize:none;overflow:hidden;border:1px solid var(--mkde-border);",
    "outline:none;box-shadow:none;transition:border-color 150ms}",
    ".mkde-hint{padding:4px 8px;display:flex;gap:12px;align-items:center;font-size:12px;line-height:16px;",
    "color:var(--mkde-muted-fg);white-space:nowrap}",
    ".mkde-hint span{display:inline-flex;gap:4px;align-items:center}",
    ".mkde-hint[data-error]{color:var(--mkde-destructive);white-space:normal;max-width:360px}"
  ].join("");

  var PENCIL =
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M11.2 2.3a1.6 1.6 0 0 1 2.3 2.3L5.4 12.7 2.5 13.5l.8-2.9z"/><path d="M10 3.5 12.5 6"/></svg>';

  var DOWNLOAD =
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M8 2.5v8"/><path d="M4.5 7 8 10.5 11.5 7"/><path d="M3 13.5h10"/></svg>';

  /* ---------------------------------------------------------------- helpers */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text) {
      node.textContent = text;
    }
    return node;
  }

  function kbd(text) {
    return el("kbd", "mkde-kbd", text);
  }

  function readDraft() {
    try {
      var draft = JSON.parse(window.sessionStorage.getItem(DRAFT_KEY) || "null");
      return draft && typeof draft.slide === "number" && typeof draft.text === "string" &&
        typeof draft.expected === "string" ? draft : null;
    } catch (error) {
      return null;
    }
  }

  function writeDraft(draft) {
    try {
      if (draft) {
        window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
      } else {
        window.sessionStorage.removeItem(DRAFT_KEY);
      }
    } catch (error) {
      // a blocked storage costs only the draft's survival across a reload
    }
  }

  function post(body) {
    return fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Mkdeck-Token": token },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          throw new Error(data.error || "The edit was not saved.");
        }
        return data;
      });
    }, function () {
      throw new Error("The dev server did not answer; is mkdeck serve still running?");
    });
  }

  function currentSlide() {
    var slide = window.Reveal && window.Reveal.getCurrentSlide && window.Reveal.getCurrentSlide();
    var index = slide && slide.getAttribute("data-mkd-slide");
    return index === null || index === undefined ? null : Number(index);
  }

  /* ---------------------------------------------------------------- tooltip */

  function beside(node, anchor) {
    // to the left of a button in the bar, centred on it
    document.body.appendChild(node);
    var rect = anchor.getBoundingClientRect();
    node.style.top = rect.top + (rect.height - node.offsetHeight) / 2 + "px";
    node.style.right = window.innerWidth - rect.left + 6 + "px";
  }

  function showTip(anchor) {
    hideTip();
    if (anchor === exporter && notice) {
      return; // the export's own progress is already showing there
    }
    tip = el("div", "mkde-float mkde-tip");
    if (anchor === exporter) {
      tip.appendChild(el("span", "", "Download as one HTML file"));
    } else if (currentSlide() !== null) {
      tip.appendChild(el("span", "", "Edit slide"));
      tip.appendChild(kbd("E"));
    } else {
      tip.appendChild(el("span", "", "This slide comes from the deck settings; edit them in the file"));
    }
    beside(tip, anchor);
  }

  function hideTip() {
    window.clearTimeout(tipTimer);
    if (tip) {
      tip.remove();
      tip = null;
    }
  }

  /* ----------------------------------------------------------- slide editor */

  function dirty() {
    return Boolean(panel) && panel.box.value !== panel.expected;
  }

  function setStatus(text, error) {
    panel.status.textContent = text;
    if (error) {
      panel.status.setAttribute("data-error", "");
    } else {
      panel.status.removeAttribute("data-error");
    }
  }

  function closePanel(keepDraft) {
    if (!panel) {
      return;
    }
    if (!keepDraft) {
      writeDraft(null);
    }
    panel.root.remove();
    panel = null;
    button.setAttribute("aria-expanded", "false");
  }

  function savePanel() {
    if (!panel || panel.save.disabled) {
      return;
    }
    if (!dirty()) {
      closePanel();
      return;
    }
    var editor = panel;
    editor.save.disabled = true;
    editor.box.disabled = true;
    setStatus("Saving");
    post({ slide: editor.slide, key: "slide", expected: editor.expected, text: editor.box.value }).then(
      function () {
        if (panel === editor) {
          writeDraft(null);
          setStatus("Saved, waiting for the rebuild");
        }
      },
      function (error) {
        if (panel === editor) {
          editor.save.disabled = false;
          editor.box.disabled = false;
          editor.box.focus();
          setStatus(error.message, true);
        }
      }
    );
  }

  function grow(box) {
    // Fit the text, from the minimum height up to the CSS max-height, then scroll.
    box.style.height = "auto";
    box.style.height = box.scrollHeight + 2 + "px";
  }

  function openPanel(slide, draft) {
    closeInline();
    closePanel(true);
    hideTip();
    var root = el("div", "mkde-float mkde-panel");
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-label", "Edit slide");
    var box = el("textarea", "mkde-source");
    box.spellcheck = false;
    box.setAttribute("aria-label", "Markdown of this slide");
    box.disabled = true;
    var row = el("div", "mkde-row");
    var status = el("p", "mkde-status", "Loading");
    var cancel = el("button", "mkde-btn mkde-outline", "Cancel");
    cancel.type = "button";
    var save = el("button", "mkde-btn mkde-primary", "Save");
    save.type = "button";
    save.appendChild(kbd(MOD + "↵"));
    save.disabled = true;
    row.appendChild(status);
    row.appendChild(cancel);
    row.appendChild(save);
    root.appendChild(box);
    root.appendChild(row);
    document.body.appendChild(root);
    panel = { root: root, box: box, status: status, save: save, slide: slide, expected: "" };
    var editor = panel;
    button.setAttribute("aria-expanded", "true");

    cancel.addEventListener("click", function () {
      closePanel();
    });
    save.addEventListener("click", savePanel);
    box.addEventListener("input", function () {
      grow(box);
      writeDraft({ slide: editor.slide, expected: editor.expected, text: box.value });
    });
    root.addEventListener("keydown", function (event) {
      event.stopPropagation(); // reveal's keys stay out of the editor
      if (event.key === "Escape") {
        event.preventDefault();
        closePanel();
      } else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        savePanel();
      }
    });
    root.addEventListener("keyup", function (event) {
      event.stopPropagation();
    });

    function ready(expected, text, note) {
      if (panel !== editor) {
        return;
      }
      editor.expected = expected;
      box.value = text;
      box.disabled = false;
      save.disabled = false;
      setStatus(note || "");
      grow(box);
      box.focus();
    }

    if (draft) {
      ready(draft.expected, draft.text, "Restored your unsaved edit");
      return;
    }
    fetch(endpoint + "?slide=" + slide, { cache: "no-store", headers: { "X-Mkdeck-Token": token } })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            throw new Error(data.error || "The slide could not be read.");
          }
          return data;
        });
      })
      .then(
        function (data) {
          ready(data.text, data.text);
        },
        function (error) {
          if (panel === editor) {
            setStatus(error.message, true);
          }
        }
      );
  }

  function togglePanel() {
    if (panel) {
      if (!dirty()) {
        closePanel();
      }
      return;
    }
    var slide = currentSlide();
    if (slide !== null) {
      openPanel(slide, null);
    }
  }

  /* ---------------------------------------------------------- inline editor */

  var HINTS = {
    title: [["↵", "Save"], ["Esc", "Cancel"]],
    cell: [["↵", "Save"], ["Esc", "Cancel"]],
    sentence: [["↵", "Save"], ["⇧↵", "New paragraph"], ["Esc", "Cancel"]],
    bullet: [["↵", "Save"], ["⇧↵", "New bullet"], ["Esc", "Cancel"]]
  };

  function kind(target) {
    return target.getAttribute("data-mkd-edit").split(":")[0];
  }

  function shownText(target) {
    var text = target.getAttribute("data-mkd-text");
    // A bullet is one line per bullet here, so a wrapped bullet shows on one line.
    return kind(target) === "bullet" ? text.replace(/\s*\n\s*/g, " ") : text;
  }

  function showHints(hint, target) {
    hint.removeAttribute("data-error");
    hint.textContent = "";
    (HINTS[kind(target)] || HINTS.title).forEach(function (pair) {
      var item = el("span");
      item.appendChild(kbd(pair[0]));
      item.appendChild(document.createTextNode(pair[1]));
      hint.appendChild(item);
    });
  }

  function placeInline() {
    var rect = inline.target.getBoundingClientRect();
    var width = Math.min(Math.max(rect.width + 24, 240), window.innerWidth - 16);
    var left = Math.min(Math.max(rect.left - 8, 8), window.innerWidth - width - 8);
    inline.box.style.left = left + "px";
    inline.box.style.top = rect.top - 7 + "px";
    inline.box.style.width = width + "px";
    inline.box.style.height = "auto";
    inline.box.style.height = inline.box.scrollHeight + 2 + "px";
    var box = inline.box.getBoundingClientRect();
    inline.hint.style.left = box.left + "px";
    inline.hint.style.top = box.bottom + 6 + "px";
  }

  function closeInline() {
    if (!inline) {
      return;
    }
    var editor = inline;
    inline = null;
    window.removeEventListener("resize", placeInline);
    editor.box.remove();
    editor.hint.remove();
  }

  function inlineError(message) {
    inline.hint.setAttribute("data-error", "");
    inline.hint.textContent = message;
    inline.box.disabled = false;
    inline.box.focus();
  }

  function saveInline() {
    var target = inline.target;
    var text = inline.box.value;
    if (text === shownText(target)) {
      closeInline();
      return;
    }
    var editor = inline;
    editor.box.disabled = true;
    editor.hint.removeAttribute("data-error");
    editor.hint.textContent = "Saving";
    post({
      slide: Number(target.closest("[data-mkd-slide]").getAttribute("data-mkd-slide")),
      key: target.getAttribute("data-mkd-edit"),
      expected: target.getAttribute("data-mkd-text"),
      text: text
    }).then(
      function () {
        if (inline === editor) {
          editor.hint.textContent = "Saved, waiting for the rebuild";
        }
      },
      function (error) {
        if (inline === editor) {
          inlineError(error.message);
        }
      }
    );
  }

  function onInlineKey(event) {
    event.stopPropagation(); // keep reveal's keys (space, arrows, r) out of the box
    var what = kind(inline.target);
    if (event.key === "Escape") {
      event.preventDefault();
      closeInline();
    } else if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      saveInline();
    } else if (event.key === "Enter" && event.shiftKey) {
      event.preventDefault();
      if (what === "sentence" || what === "bullet") {
        // A single line break in a paragraph renders as a space, so a sentence takes a blank line.
        document.execCommand("insertText", false, what === "sentence" ? "\n\n" : "\n");
      }
    }
  }

  function editInline(target) {
    closeInline();
    if (panel) {
      return; // the slide editor holds this slide's source; one editor at a time
    }
    var style = window.getComputedStyle(target);
    var box = el("textarea", "mkde-float mkde-inline");
    box.rows = 1; // the box grows to its text; two default rows would pad a one-line title
    box.spellcheck = true;
    box.value = shownText(target);
    box.style.font = style.font;
    box.style.letterSpacing = style.letterSpacing;
    box.style.textAlign = style.textAlign;
    var hint = el("div", "mkde-float mkde-hint");
    document.body.appendChild(box);
    document.body.appendChild(hint);
    inline = { box: box, hint: hint, target: target };
    showHints(hint, target);
    placeInline();
    box.addEventListener("keydown", onInlineKey);
    box.addEventListener("keyup", function (event) {
      event.stopPropagation();
    });
    box.addEventListener("input", placeInline);
    box.addEventListener("blur", function () {
      // A click elsewhere on the page saves; leaving the window keeps the box open.
      if (inline && inline.box === box && !box.disabled && document.hasFocus()) {
        saveInline();
      }
    });
    window.addEventListener("resize", placeInline);
    box.focus();
    if (kind(target) === "title" || kind(target) === "cell") {
      box.select(); // a short piece is usually rewritten, so typing replaces it
    } else {
      box.setSelectionRange(box.value.length, box.value.length);
    }
  }

  /* ----------------------------------------------------------------- export */

  function showNotice(text, error, seconds) {
    window.clearTimeout(noticeTimer);
    if (notice) {
      notice.remove();
    }
    hideTip();
    notice = el("div", "mkde-float mkde-tip", text);
    notice.setAttribute("role", "status");
    if (error) {
      notice.setAttribute("data-error", "");
    }
    beside(notice, exporter);
    if (seconds) {
      noticeTimer = window.setTimeout(function () {
        notice.remove();
        notice = null;
      }, seconds * 1000);
    }
  }

  function exportDeck() {
    if (exporter.getAttribute("aria-busy") === "true") {
      return;
    }
    exporter.setAttribute("aria-busy", "true");
    showNotice("Building one HTML file");
    fetch(exportPath, { cache: "no-store", headers: { "X-Mkdeck-Token": token } })
      .then(
        function (response) {
          if (!response.ok) {
            return response.json().then(function (data) {
              throw new Error(data.error || "The deck could not be exported.");
            });
          }
          var match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "");
          var name = match ? match[1] : "deck.html";
          return response.blob().then(function (blob) {
            var link = el("a");
            link.href = URL.createObjectURL(blob);
            link.download = name;
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.setTimeout(function () {
              URL.revokeObjectURL(link.href);
            }, 1000);
            return name;
          });
        },
        function () {
          throw new Error("The dev server did not answer; is mkdeck serve still running?");
        }
      )
      .then(
        function (name) {
          showNotice("Downloaded " + name, false, 2.5);
        },
        function (error) {
          showNotice(error.message, true, 6);
        }
      )
      .then(function () {
        exporter.setAttribute("aria-busy", "false");
      });
  }

  /* ------------------------------------------------------------------ start */

  function syncButton() {
    button.setAttribute("aria-disabled", currentSlide() !== null ? "false" : "true");
  }

  function start() {
    var style = el("style");
    style.textContent = STYLE;
    document.head.appendChild(style);

    var bar = el("div", "mkde-bar");
    button = el("button", "mkde-trigger");
    button.setAttribute("aria-label", "Edit slide");
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-expanded", "false");
    button.innerHTML = PENCIL;
    exporter = el("button", "mkde-trigger");
    exporter.setAttribute("aria-label", "Download as one HTML file");
    exporter.innerHTML = DOWNLOAD;
    [button, exporter].forEach(function (control) {
      control.type = "button";
      bar.appendChild(control);
      control.addEventListener("mouseenter", function () {
        tipTimer = window.setTimeout(function () {
          showTip(control);
        }, 400);
      });
      control.addEventListener("mouseleave", hideTip);
      control.addEventListener("focus", function () {
        if (control.matches(":focus-visible")) {
          showTip(control);
        }
      });
      control.addEventListener("blur", hideTip);
    });
    document.body.appendChild(bar);
    button.addEventListener("click", function () {
      hideTip();
      if (button.getAttribute("aria-disabled") !== "true") {
        togglePanel();
      }
    });
    exporter.addEventListener("click", exportDeck);

    document.addEventListener("dblclick", function (event) {
      var target = event.target.closest && event.target.closest("[data-mkd-edit]");
      if (target && target.closest("section.present")) {
        event.preventDefault();
        editInline(target);
      }
    });
    // A click outside an unchanged slide editor closes it, as a popover does.
    document.addEventListener("pointerdown", function (event) {
      if (panel && !dirty() && !panel.root.contains(event.target) && !button.contains(event.target)) {
        closePanel();
      }
    });

    var deck = window.Reveal;
    if (deck && typeof deck.addKeyBinding === "function") {
      deck.addKeyBinding({ keyCode: 69, key: "E", description: "Edit this slide" }, function () {
        if (button.getAttribute("aria-disabled") !== "true") {
          togglePanel();
        }
      });
    }
    function onSlide() {
      closeInline();
      if (panel && !dirty()) {
        closePanel();
      }
      syncButton();
    }
    if (deck && typeof deck.on === "function") {
      deck.on("slidechanged", onSlide);
      deck.on("ready", syncButton);
    }
    syncButton();

    // An unsaved slide edit survives a reload: reopen it on its slide.
    var draft = readDraft();
    if (draft && draft.slide === currentSlide()) {
      openPanel(draft.slide, draft);
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
