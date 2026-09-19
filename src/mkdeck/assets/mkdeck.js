/*! mkdeck — deck behaviour.
 *
 * One plain script, no modules and no build step, so you can read it and write
 * your own custom element beside it. It provides:
 *
 *   <deck-embed src="...">   an iframe with a lifecycle (see syncEmbeds below)
 *   <deck-rollout src="..."> a robot run, when mkdeck-rollout.js is on the deck
 *   <deck-mermaid>           a diagram, with Mermaid fetched only if one exists
 *   the KaTeX pass           every .mkd-math is rendered from its data-tex
 *   the dense pass           a crowded slide is marked so the figure shrinks
 *   the chrome               the date on the left, "n / total" on the right
 *   the r key                reload this slide's embeds
 *
 * and a documented global:
 *
 *   window.mkdeck.onSlide(fn)    fn({ index, total, slide, date }) per slide
 *   window.mkdeck.reloadEmbeds() reload the current slide's embeds
 *   window.mkdeck.deck           the Reveal instance
 */
(function () {
  "use strict";

  var MERMAID_SRC = "https://cdn.jsdelivr.net/npm/mermaid@12/dist/mermaid.min.js";

  var deck = null; // the Reveal instance, once it exists
  var slides = []; // every .mkd-slide, in presentation order
  var dates = []; // the effective date of each slide, same order
  var index = 0; // the current slide
  var started = false;
  var listeners = [];
  var mermaidLoad = null; // the one Mermaid fetch, if a deck ever needs it
  var mermaidCount = 0;

  function each(list, fn) {
    Array.prototype.forEach.call(list, fn);
  }

  /* ------------------------------------------------------------------ *
   * <deck-embed src="page.html">
   *
   * The piece that matters. A deck of WebGL pages must never hold more
   * than a couple of live contexts, so at any moment:
   *
   *   the current slide   iframes exist and load eagerly
   *   its two neighbours  iframes exist and load lazily
   *   every other slide   the iframe is blanked and detached
   *
   * Detaching is what frees the context; setting src to about:blank first
   * stops a page that is still loading.
   * ------------------------------------------------------------------ */

  function loadEmbed(host, eager) {
    var src = host.getAttribute("src");
    if (!src) {
      return;
    }
    var frame = host.querySelector("iframe");
    if (frame) {
      frame.setAttribute("loading", eager ? "eager" : "lazy");
      return;
    }
    frame = document.createElement("iframe");
    frame.setAttribute("allow", "fullscreen");
    frame.setAttribute("referrerpolicy", "no-referrer");
    frame.setAttribute("title", host.getAttribute("title") || "embed");
    frame.setAttribute("loading", eager ? "eager" : "lazy");
    frame.src = src;
    host.appendChild(frame);
  }

  function unloadEmbed(host) {
    var frame = host.querySelector("iframe");
    if (!frame) {
      return;
    }
    frame.src = "about:blank";
    frame.remove();
  }

  function reloadEmbed(host) {
    unloadEmbed(host);
    loadEmbed(host, true);
  }

  if (window.customElements && !window.customElements.get("deck-embed")) {
    window.customElements.define(
      "deck-embed",
      class extends HTMLElement {
        load(eager) {
          loadEmbed(this, eager !== false);
        }
        unload() {
          unloadEmbed(this);
        }
        reload() {
          reloadEmbed(this);
        }
      },
    );
  }

  function syncEmbeds() {
    slides.forEach(function (slide, i) {
      var distance = Math.abs(i - index);
      each(slide.querySelectorAll("deck-embed"), function (host) {
        if (distance <= 1) {
          loadEmbed(host, distance === 0);
        } else {
          unloadEmbed(host);
        }
      });
      // A rollout holds a WebGL context of its own, so it keeps the same
      // window. The element only answers when mkdeck-rollout.js is on the deck.
      each(slide.querySelectorAll("deck-rollout"), function (host) {
        if (typeof host.load !== "function") {
          return;
        }
        if (distance <= 1) {
          host.load(distance === 0);
        } else {
          host.unload();
        }
      });
    });
  }

  function reloadEmbeds() {
    var slide = slides[index];
    if (!slide) {
      return;
    }
    each(slide.querySelectorAll("deck-embed"), reloadEmbed);
    each(slide.querySelectorAll("deck-rollout"), function (host) {
      if (typeof host.reload === "function") {
        host.reload();
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * <deck-mermaid>
   *
   * Mermaid is a large library, so it is fetched the first time a slide
   * that holds a diagram comes into range and never otherwise. Point
   * data-src at a vendored copy to keep the deck offline.
   * ------------------------------------------------------------------ */

  function loadMermaid(src) {
    if (mermaidLoad) {
      return mermaidLoad;
    }
    mermaidLoad = new Promise(function (resolve, reject) {
      if (window.mermaid) {
        resolve(window.mermaid);
        return;
      }
      var script = document.createElement("script");
      script.src = src || MERMAID_SRC;
      script.onload = function () {
        if (window.mermaid) {
          window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
          resolve(window.mermaid);
        } else {
          reject(new Error("mermaid loaded but did not register itself"));
        }
      };
      script.onerror = function () {
        reject(new Error("mermaid could not be loaded from " + script.src));
      };
      document.head.appendChild(script);
    });
    return mermaidLoad;
  }

  function renderMermaid(host) {
    if (host.dataset.mkdState) {
      return;
    }
    host.dataset.mkdState = "loading";
    var source = (host.textContent || "").trim();
    mermaidCount += 1;
    var id = "mkd-mermaid-" + mermaidCount;
    loadMermaid(host.getAttribute("data-src"))
      .then(function (mermaid) {
        return mermaid.render(id, source);
      })
      .then(function (result) {
        host.innerHTML = result.svg;
        host.dataset.mkdState = "done";
      })
      .catch(function (error) {
        host.textContent = source;
        host.dataset.mkdState = "error";
        if (window.console) {
          window.console.warn("mkdeck: " + error.message);
        }
      });
  }

  if (window.customElements && !window.customElements.get("deck-mermaid")) {
    window.customElements.define(
      "deck-mermaid",
      class extends HTMLElement {
        render() {
          renderMermaid(this);
        }
      },
    );
  }

  function syncMermaid() {
    slides.forEach(function (slide, i) {
      if (Math.abs(i - index) > 1) {
        return;
      }
      each(slide.querySelectorAll("deck-mermaid"), renderMermaid);
    });
  }

  /* ------------------------------------------------------------------ *
   * KaTeX
   *
   * The renderer emits the escaped source in data-tex and leaves the span
   * empty, so a formula that KaTeX cannot parse degrades to its own source
   * text instead of breaking the slide.
   * ------------------------------------------------------------------ */

  function renderMath(root) {
    each(root.querySelectorAll(".mkd-math"), function (node) {
      if (node.querySelector(".katex")) {
        return;
      }
      var tex = node.getAttribute("data-tex") || "";
      if (!window.katex) {
        node.textContent = tex;
        return;
      }
      try {
        window.katex.render(tex, node, { displayMode: false, throwOnError: false });
      } catch (error) {
        node.textContent = tex;
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * The dense pass
   *
   * Bullets, or a stack of display formulas, leave less room for a figure
   * or a table. The class drives the shorter figure heights in mkdeck.css.
   * ------------------------------------------------------------------ */

  function markDense() {
    slides.forEach(function (slide) {
      var crowded =
        slide.querySelectorAll(".mkd-bullets").length > 0 || slide.querySelectorAll(".mkd-math-block").length >= 2;
      slide.classList.toggle("dense", crowded);
    });
  }

  /* ------------------------------------------------------------------ *
   * The chrome
   *
   * Left: the date this part of the deck is stamped with — the slide's own
   * data-date, else the nearest earlier slide that carries one (a section
   * title, usually), else the deck date. Right: the position.
   * ------------------------------------------------------------------ */

  function deckDate() {
    var root = document.querySelector(".reveal");
    if (root && root.dataset.deckDate) {
      return root.dataset.deckDate;
    }
    return document.body.dataset.deckDate || "";
  }

  function stampDates() {
    var stamp = deckDate();
    dates = slides.map(function (slide) {
      if (slide.dataset.date) {
        stamp = slide.dataset.date;
      }
      return stamp;
    });
  }

  function updateChrome() {
    var left = document.querySelector(".mkd-chrome-left");
    var right = document.querySelector(".mkd-chrome-right");
    if (left) {
      left.textContent = dates[index] || "";
    }
    if (right) {
      right.textContent = slides.length ? index + 1 + " / " + slides.length : "";
    }
  }

  /* ------------------------------------------------------------------ *
   * Wiring
   * ------------------------------------------------------------------ */

  function collect() {
    var stage = document.querySelector(".reveal .slides");
    slides = stage ? Array.prototype.slice.call(stage.querySelectorAll("section.mkd-slide")) : [];
  }

  function locate() {
    var slide = deck && deck.getCurrentSlide ? deck.getCurrentSlide() : null;
    if (!slide) {
      return 0;
    }
    var found = slides.indexOf(slide);
    if (found < 0 && slide.closest) {
      var host = slide.closest("section.mkd-slide");
      found = host ? slides.indexOf(host) : -1;
    }
    return found < 0 ? 0 : found;
  }

  function announce() {
    var info = { index: index, total: slides.length, slide: slides[index] || null, date: dates[index] || "" };
    listeners.forEach(function (fn) {
      try {
        fn(info);
      } catch (error) {
        if (window.console) {
          window.console.error("mkdeck: a slide listener threw", error);
        }
      }
    });
  }

  function onSlideChanged() {
    index = locate();
    syncEmbeds();
    syncMermaid();
    updateChrome();
    announce();
  }

  function onReady() {
    collect();
    markDense();
    renderMath(document);
    stampDates();
    bindKeys();
    started = true;
    onSlideChanged();
  }

  // Called from onReady: addKeyBinding only exists once reveal has initialised.
  function bindKeys() {
    if (deck && typeof deck.addKeyBinding === "function") {
      deck.addKeyBinding({ keyCode: 82, key: "R", description: "Reload the embeds on this slide" }, reloadEmbeds);
      return;
    }
    document.addEventListener("keydown", function (event) {
      if (event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      if (event.key === "r" || event.key === "R") {
        event.preventDefault();
        reloadEmbeds();
      }
    });
  }

  window.mkdeck = {
    /** Call fn({ index, total, slide, date }) now and on every slide change. */
    onSlide: function (fn) {
      if (typeof fn !== "function") {
        return function () {};
      }
      listeners.push(fn);
      if (started) {
        fn({ index: index, total: slides.length, slide: slides[index] || null, date: dates[index] || "" });
      }
      return function () {
        var at = listeners.indexOf(fn);
        if (at >= 0) {
          listeners.splice(at, 1);
        }
      };
    },
    /** Blank and recreate the current slide's iframes. The fix for a dead viewer. */
    reloadEmbeds: reloadEmbeds,
    /** The Reveal instance, for anything reveal already does well. */
    deck: null,
  };

  if (window.Reveal) {
    deck = window.Reveal;
    window.mkdeck.deck = deck;
    // Registered before Reveal.initialize runs; reveal queues these for us.
    deck.on("ready", onReady);
    deck.on("slidechanged", onSlideChanged);
  } else if (document.readyState === "loading") {
    // No reveal: still draw the deck, so a check or an export sees real slides.
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
