/*! mkdeck — <deck-rollout src="run.rollout">
 *
 * A rollout is a robot run: shared meshes in one file, this run's poses in
 * another, drawn by the three.js viewer under viewer/. The element behaves like
 * <deck-embed> — load(eager) and unload(), driven by mkdeck.js from the slide
 * distance — so a deck of runs still keeps only a couple of WebGL contexts.
 *
 * Why this script is plain and the viewer is modules: a shipped deck is opened
 * from a file:// URL, where the browser refuses to fetch an ES module, so the
 * viewer's sources are read as text and imported from blob: URLs, which
 * file:// allows. Served or shipped, the path is the same one.
 *
 * A single-file deck carries each source and each rollout inline, base64 for
 * the binaries; otherwise both are fetched next to the page.
 */
(function () {
  "use strict";

  var RBDL = "RBDL";
  var RSPL = "RSPL";

  // Import specifier -> file under the assets folder. Order is dependency
  // order: each source is rewritten to point at the blob URLs already built.
  var MODULES = [
    ["three", "three/three.module.js"],
    ["three/addons/controls/OrbitControls.js", "three/addons/controls/OrbitControls.js"],
    ["rollout-bundle", "viewer/bundle_parser.js"],
    ["mkdeck-camera", "viewer/camera.js"],
    ["mkdeck-viewer", "viewer/rollout_viewer.js"],
  ];

  var viewerModule = null; // the one import, shared by every rollout on the deck
  var meshes = {}; // mesh file -> Promise<Uint8Array>, so a model is fetched once

  function assetBase() {
    var root = document.querySelector("[data-mkd-assets]");
    var base = root ? root.getAttribute("data-mkd-assets") : "mkdeck-assets";
    return base.replace(/\/+$/, "") + "/";
  }

  /* ---------------------------------------------------------------- *
   * Sources and bytes: inline when the deck is one file, fetched when
   * it is a folder.
   * ---------------------------------------------------------------- */

  function inlineNode(attribute, value) {
    return document.querySelector('script[' + attribute + '="' + value + '"]');
  }

  function sourceOf(specifier, path) {
    var inline = inlineNode("data-mkd-module", specifier);
    if (inline) {
      return Promise.resolve(inline.textContent);
    }
    return fetch(assetBase() + path).then(function (response) {
      if (!response.ok) {
        throw new Error("cannot load " + path + " (" + response.status + ")");
      }
      return response.text();
    });
  }

  function base64Bytes(text) {
    var binary = atob(text.replace(/\s+/g, ""));
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  function bytesOf(src) {
    var inline = inlineNode("data-mkd-rollout", src);
    if (inline) {
      return Promise.resolve(base64Bytes(inline.textContent));
    }
    return fetch(src).then(function (response) {
      if (!response.ok) {
        throw new Error("cannot load " + src + " (" + response.status + ")");
      }
      return response.arrayBuffer();
    }).catch(function (error) {
      // A browser will not read a neighbouring file from a file:// page, so a
      // folder build has to be served. A single-file build carries its
      // rollouts inside the document and never reaches this.
      if (window.location.protocol === "file:") {
        throw new Error("a deck opened from a file:// URL cannot read " + src
          + "; serve the folder, or build it with --single-file");
      }
      throw error;
    }).then(function (buffer) {
      return new Uint8Array(buffer);
    });
  }

  // gzip, through the browser's own decompressor. Every browser that runs
  // WebGL2 has it, which is why no inflate library is vendored.
  function gunzip(bytes) {
    if (typeof DecompressionStream !== "function") {
      return Promise.reject(new Error("this browser cannot decompress the rollout (no DecompressionStream)"));
    }
    var stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Response(stream).arrayBuffer().then(function (buffer) {
      return new Uint8Array(buffer);
    });
  }

  /* ---------------------------------------------------------------- *
   * The viewer module, imported once per deck from blob: URLs.
   * ---------------------------------------------------------------- */

  function rewrite(source, resolved) {
    Object.keys(resolved).forEach(function (specifier) {
      var escaped = specifier.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
      var pattern = new RegExp("(from\\s*|import\\s*)([\"'])" + escaped + "\\2", "g");
      source = source.replace(pattern, '$1"' + resolved[specifier] + '"');
    });
    return source;
  }

  function loadViewer() {
    if (viewerModule) {
      return viewerModule;
    }
    var resolved = {};
    viewerModule = MODULES.reduce(function (chain, entry) {
      return chain.then(function () {
        return sourceOf(entry[0], entry[1]).then(function (source) {
          var blob = new Blob([rewrite(source, resolved)], { type: "text/javascript" });
          resolved[entry[0]] = URL.createObjectURL(blob);
        });
      });
    }, Promise.resolve()).then(function () {
      return import(resolved["mkdeck-viewer"]);
    });
    return viewerModule;
  }

  /* ---------------------------------------------------------------- *
   * .rollout + .meshes -> the .rbundle the viewer reads
   *
   * The split is mkdeck's: one mesh file per model, one small file per run,
   * with every offset in the header already indexing the two tails joined in
   * that order. Gluing them back together is the whole of it.
   * ---------------------------------------------------------------- */

  function magic(bytes) {
    return String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
  }

  function splitContainer(bytes) {
    var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    var length = Number(view.getBigUint64(4, true));
    var header = JSON.parse(new TextDecoder().decode(bytes.subarray(12, 12 + length)));
    return { header: header, tail: bytes.subarray(12 + length) };
  }

  function bundleFrom(bytes, dirname) {
    if (magic(bytes) === RBDL) {
      return Promise.resolve(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
    }
    if (magic(bytes) !== RSPL) {
      return Promise.reject(new Error("not a rollout (bad magic)"));
    }
    var split = splitContainer(bytes);
    var file = split.header.meshes.file;
    if (!meshes[file]) {
      meshes[file] = bytesOf(dirname + file).then(gunzip);
    }
    return Promise.all([meshes[file], gunzip(split.tail)]).then(function (parts) {
      var mesh = parts[0], poses = parts[1];
      if (mesh.byteLength !== split.header.meshes.bytes) {
        throw new Error("the shared meshes are not the ones this rollout was written against");
      }
      var header = {};
      Object.keys(split.header).forEach(function (key) {
        if (key !== "meshes" && key !== "version") {
          header[key] = split.header[key];
        }
      });
      var encoded = new TextEncoder().encode(JSON.stringify(header));
      var padding = (8 - ((encoded.length + 12) % 8)) % 8;
      var total = 12 + encoded.length + padding + mesh.byteLength + poses.byteLength;
      var out = new Uint8Array(total);
      var view = new DataView(out.buffer);
      for (var i = 0; i < 4; i++) {
        out[i] = RBDL.charCodeAt(i);
      }
      view.setBigUint64(4, BigInt(encoded.length + padding), true);
      out.set(encoded, 12);
      out.fill(0x20, 12 + encoded.length, 12 + encoded.length + padding);
      out.set(mesh, 12 + encoded.length + padding);
      out.set(poses, 12 + encoded.length + padding + mesh.byteLength);
      return out.buffer;
    });
  }

  /* ---------------------------------------------------------------- *
   * <deck-rollout>
   * ---------------------------------------------------------------- */

  function dirnameOf(src) {
    var cut = src.lastIndexOf("/");
    return cut < 0 ? "" : src.slice(0, cut + 1);
  }

  function controlsFor(host, viewer) {
    var bar = document.createElement("div");
    bar.className = "mkd-rollout-controls";

    var play = document.createElement("button");
    play.type = "button";
    play.className = "mkd-rollout-play";
    play.setAttribute("aria-label", "Play or pause");

    var scrub = document.createElement("input");
    scrub.type = "range";
    scrub.className = "mkd-rollout-scrub";
    scrub.min = "0";
    scrub.max = "1000";
    scrub.value = "0";
    scrub.setAttribute("aria-label", "Position in the run");

    var time = document.createElement("span");
    time.className = "mkd-rollout-time";

    function paint() {
      play.textContent = viewer.playing ? "❚❚" : "▶";
    }
    play.addEventListener("click", function () {
      viewer.toggle();
      paint();
    });
    scrub.addEventListener("input", function () {
      viewer.pause();
      paint();
      viewer.seek((Number(scrub.value) / 1000) * viewer.duration);
    });
    bar.appendChild(play);
    bar.appendChild(scrub);
    bar.appendChild(time);
    host.appendChild(bar);
    paint();
    return {
      frame: function (t, total) {
        if (document.activeElement !== scrub) {
          scrub.value = String(total > 0 ? Math.round((t / total) * 1000) : 0);
        }
        time.textContent = t.toFixed(2) + " s";
      },
      paint: paint,
    };
  }

  function fail(host, message) {
    host.dataset.mkdState = "error";
    var note = document.createElement("p");
    note.className = "mkd-rollout-error";
    note.textContent = "rollout: " + message;
    host.appendChild(note);
    if (window.console) {
      window.console.warn("mkdeck: " + message);
    }
  }

  function loadRollout(host, eager) {
    if (host.dataset.mkdState) {
      return;
    }
    var src = host.getAttribute("src");
    if (!src) {
      return;
    }
    host.dataset.mkdState = "loading";
    var stage = document.createElement("div");
    stage.className = "mkd-rollout-stage";
    host.appendChild(stage);

    var chrome = null;
    loadViewer()
      .then(function (module) {
        return bytesOf(src).then(function (bytes) {
          return bundleFrom(bytes, dirnameOf(src));
        }).then(function (bundle) {
          if (host.dataset.mkdState !== "loading") {
            return; // unloaded while the bytes were in flight
          }
          var viewer = module.createViewer(stage, {
            background: host.getAttribute("data-background") || undefined,
            scale: Number(host.getAttribute("data-scale")) || undefined,
            loop: host.getAttribute("data-loop") !== "false",
            follow: host.getAttribute("data-follow") !== "false",
            onFrame: function (t, total) {
              if (chrome) {
                chrome.frame(t, total);
              }
            },
          });
          host.mkdViewer = viewer;
          viewer.load(bundle);
          var view = host.getAttribute("data-view");
          if (view) {
            viewer.setView(view);
          }
          chrome = controlsFor(host, viewer);
          host.dataset.mkdState = "ready";
          if (eager && host.getAttribute("data-autoplay") !== "false") {
            viewer.play();
            chrome.paint();
          }
        });
      })
      .catch(function (error) {
        unloadRollout(host);
        fail(host, error.message);
      });
  }

  function unloadRollout(host) {
    if (host.mkdViewer) {
      host.mkdViewer.dispose();
      host.mkdViewer = null;
    }
    delete host.dataset.mkdState;
    while (host.firstChild) {
      host.removeChild(host.firstChild);
    }
  }

  if (window.customElements && !window.customElements.get("deck-rollout")) {
    window.customElements.define(
      "deck-rollout",
      class extends HTMLElement {
        load(eager) {
          loadRollout(this, eager !== false);
        }
        unload() {
          unloadRollout(this);
        }
        reload() {
          unloadRollout(this);
          loadRollout(this, true);
        }
        disconnectedCallback() {
          unloadRollout(this);
        }
      },
    );
  }
})();
