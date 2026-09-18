"""Check a built deck in headless Chromium, slide by slide.

Playwright is an optional extra, so it is imported only when a check actually
runs. Importing :mod:`mkdeck`, serving a deck and building one all work without
it.
"""

import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from mkdeck.build import build_source, find_markdown
from mkdeck.errors import DeckError

EMBED_BLOCK_BYTES = 2_000_000
"""Embeds larger than this are replaced with a stub so the check stays fast."""

DEFAULT_SIZE = (1920, 1080)

INSTALL_HINT = (
    "This command needs Playwright, which mkdeck does not install by default.\n"
    "  uv pip install 'mkdeck[check]'\n"
    "  playwright install chromium"
)

BLOCKED_BODY = (
    '<html><body style="margin:0;background:#f4f4f4;font:14px Roboto,sans-serif;color:#999">'
    '<div style="padding:12px">embed (blocked in the checker)</div></body></html>'
)

PROBE = r"""
() => {
  const slide = document.querySelector('.reveal .slides section.present')
             || document.querySelector('.reveal .slides section');
  if (!slide) { return {error: 'no visible slide'}; }
  const vh = window.innerHeight, vw = window.innerWidth;
  const style = getComputedStyle(slide);
  const padTop = parseFloat(style.paddingTop) || 0;
  const padBottom = parseFloat(style.paddingBottom) || 0;
  const body = slide.querySelector('.mkd-body') || slide;
  const kids = Array.from(body.children).filter(k => k.getClientRects().length);
  let top = Infinity, bottom = -Infinity, left = Infinity, right = -Infinity;
  for (const k of kids) {
    const r = k.getBoundingClientRect();
    if (r.height === 0 && r.width === 0) { continue; }
    top = Math.min(top, r.top); bottom = Math.max(bottom, r.bottom);
    left = Math.min(left, r.left); right = Math.max(right, r.right);
  }
  if (!isFinite(top)) { top = 0; bottom = 0; left = 0; right = 0; }
  const scrollers = [];
  for (const e of slide.querySelectorAll('*')) {
    const cs = getComputedStyle(e);
    const canScroll = /(auto|scroll)/.test(cs.overflowX + cs.overflowY);
    if (canScroll && (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)) {
      scrollers.push({tag: e.tagName.toLowerCase(), cls: e.className.toString().slice(0, 40),
                      sw: e.scrollWidth, cw: e.clientWidth, sh: e.scrollHeight, ch: e.clientHeight});
    }
  }
  const overlaps = [];
  const boxes = kids.map(k => k.getBoundingClientRect()).filter(r => r.height > 0);
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ox > 2 && oy > 2) { overlaps.push({i: i, j: j, ox: Math.round(ox), oy: Math.round(oy)}); }
    }
  }
  const chrome = document.querySelector('.mkd-chrome-left') || document.querySelector('.mkd-chrome');
  const chromeTop = chrome ? chrome.getBoundingClientRect().top : vh - 34;
  const sentence = Array.from(slide.querySelectorAll('.mkd-sentence')).map(p => p.innerText).join(' ');
  const bullets = Array.from(slide.querySelectorAll('.mkd-bullets li')).map(li => li.innerText);
  const table = slide.querySelector('.mkd-table');
  const left_text = chrome ? chrome.textContent : '';
  const rightChrome = document.querySelector('.mkd-chrome-right');
  const maths = Array.from(slide.querySelectorAll('.mkd-math'));
  return {
    vw: vw, vh: vh,
    top: Math.round(top), bottom: Math.round(bottom), left: Math.round(left), right: Math.round(right),
    overflow_top: Math.round(Math.max(0, padTop - top)),
    overflow_bottom: Math.round(Math.max(0, bottom - (vh - padBottom))),
    into_chrome: bottom > chromeTop,
    scrollers: scrollers,
    overlaps: overlaps,
    sentence_chars: sentence.length,
    bullets: bullets.length,
    bullet_chars: bullets.map(b => b.length),
    table: table ? {rows: table.querySelectorAll('tbody tr').length,
                    cols: table.querySelectorAll('thead th').length,
                    width: Math.round(table.getBoundingClientRect().width)} : null,
    figures: slide.querySelectorAll('.mkd-figure').length,
    formula_blocks: slide.querySelectorAll('.mkd-math-block').length,
    katex_errors: slide.querySelectorAll('.katex-error').length,
    math_unrendered: maths.filter(m => !m.querySelector('.katex')).length,
    layout: slide.dataset.layout || '',
    id: slide.dataset.id || '',
    dense: slide.classList.contains('dense'),
    chrome_left: left_text, chrome_right: rightChrome ? rightChrome.textContent : ''
  };
}
"""


def require_playwright() -> Any:
    """Import Playwright's synchronous API, or explain how to install it.

    Returns:
        The ``sync_playwright`` context manager factory.

    Raises:
        DeckError: If Playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise DeckError(INSTALL_HINT) from exc
    return sync_playwright


def browser_env() -> dict[str, str]:
    """Build the environment Chromium is launched with.

    ``MKDECK_BROWSER_LIBS`` is prepended to ``LD_LIBRARY_PATH``, which is how a
    machine without system NSS or ALSA can still run the checker.

    Returns:
        The environment mapping.
    """
    env = dict(os.environ)
    extra = env.get("MKDECK_BROWSER_LIBS", "").strip()
    if extra:
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{extra}:{existing}" if existing else extra
    return env


def launch_browser(playwright: Any) -> Any:
    """Start headless Chromium, turning a missing browser into a clear error.

    Args:
        playwright: The started Playwright instance.

    Returns:
        The launched browser.

    Raises:
        DeckError: If Chromium cannot be started.
    """
    try:
        return playwright.chromium.launch(env=browser_env())
    except Exception as exc:  # pragma: no cover - depends on the machine
        raise DeckError(
            f"Could not start headless Chromium: {exc}\n"
            "Install it with: playwright install chromium\n"
            "On a machine without system NSS or ALSA, point MKDECK_BROWSER_LIBS at a folder holding them."
        ) from exc


def _prepare(path: Path, workdir: Path) -> Path:
    """Get an HTML document to check, building the deck when needed.

    Args:
        path: A built ``.html`` file, a Markdown file, or a deck folder.
        workdir: A scratch folder the deck is built into.

    Returns:
        The HTML document to open.

    Raises:
        DeckError: If the path holds no deck.
    """
    path = Path(path)
    if path.is_file() and path.suffix.lower() in {".html", ".htm"}:
        return path
    find_markdown(path)
    return build_source(path, workdir)


def slide_flags(record: dict[str, Any]) -> list[str]:
    """List everything wrong with one slide.

    The same list is written into ``report.json`` and printed in ``report.txt``, so a
    program reading the JSON sees exactly what a person reading the text sees.

    Args:
        record: The probe result for a slide.

    Returns:
        One string per finding, empty when the slide is clean.
    """
    flags: list[str] = []
    if record.get("overflow_top", 0) > 0 or record.get("overflow_bottom", 0) > 0:
        flags.append(f"OVERFLOW top {record['overflow_top']}px bottom {record['overflow_bottom']}px")
    if record.get("into_chrome"):
        flags.append("INTO-CHROME")
    if record.get("scrollers"):
        details = ", ".join(
            f"{s['tag']}.{s['cls']} {s['sw']}>{s['cw']}w {s['sh']}>{s['ch']}h" for s in record["scrollers"]
        )
        flags.append(f"SCROLLBAR {details}")
    if record.get("overlaps"):
        flags.append("OVERLAP " + json.dumps(record["overlaps"]))
    if record.get("katex_errors"):
        flags.append(f"KATEX-ERROR x{record['katex_errors']}")
    if record.get("math_unrendered"):
        flags.append(f"MATH-UNRENDERED x{record['math_unrendered']}")
    return flags


def _format_row(record: dict[str, Any]) -> str:
    """Format one slide's findings as a report line.

    Args:
        record: The probe result for a slide.

    Returns:
        A single line of ``report.txt``.
    """
    number = record.get("n", 0)
    slide_id = str(record.get("id") or "")
    if record.get("error"):
        return f"{number:3d} {slide_id:26s} {record['error']}"
    flags = slide_flags(record)
    table = record.get("table")
    table_text = f" table {table['rows']}x{table['cols']} {table['width']}px" if table else ""
    bullets = record.get("bullets", 0)
    bullet_text = "/" + "+".join(str(n) for n in record.get("bullet_chars", [])) if bullets else ""
    return (
        f"{number:3d} {slide_id:26s} {record.get('layout', ''):9s}"
        f" sent {record.get('sentence_chars', 0):4d}"
        f" bul {bullets}{bullet_text}"
        f" fig {record.get('figures', 0)}{table_text}"
        f" fb {record.get('formula_blocks', 0)}"
        f" h {record.get('top', 0)}-{record.get('bottom', 0)}"
        f"  {' | '.join(flags) if flags else 'ok'}"
    )


def check_deck(
    path: Path | str,
    *,
    out: Path | str = Path("report"),
    size: tuple[int, int] = DEFAULT_SIZE,
    shots: bool = True,
    first: int = 1,
    last: int = 0,
) -> list[dict[str, Any]]:
    """Open a deck in headless Chromium and report what each slide does.

    Every slide is measured for content overflow past the viewport, elements
    that would show a scrollbar, elements overlapping the chrome and KaTeX
    failures. A screenshot is written for each slide unless ``shots`` is off.

    Args:
        path: A built ``.html`` file, a Markdown file, or a deck folder.
        out: The folder the report and screenshots are written to.
        size: The viewport, as ``(width, height)`` in pixels.
        shots: True to write one PNG per slide.
        first: The first slide number to check, counting from 1.
        last: The last slide number to check; 0 means every slide.

    Returns:
        One record per checked slide, the same data as ``report.json``.

    Raises:
        DeckError: If Playwright is missing, Chromium cannot start, or the path
            holds no deck.
    """
    sync_playwright = require_playwright()
    width, height = size
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="mkdeck-check-"))
    records: list[dict[str, Any]] = []
    try:
        document = _prepare(Path(path), workdir)
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            page = browser.new_page(viewport={"width": width, "height": height})

            def route(handler: Any) -> None:
                url = handler.request.url
                heavy = False
                if url.startswith("file://") and url.endswith((".html", ".htm")):
                    try:
                        heavy = os.path.getsize(url[7:].split("?", 1)[0]) > EMBED_BLOCK_BYTES
                    except OSError:
                        heavy = False
                if heavy:
                    handler.fulfill(status=200, content_type="text/html", body=BLOCKED_BODY)
                else:
                    handler.continue_()

            page.route("**/*", route)
            page.goto(document.resolve().as_uri())
            page.wait_for_function("document.querySelectorAll('.reveal .slides section').length > 0")
            page.wait_for_timeout(600)
            total = page.evaluate("document.querySelectorAll('.reveal .slides section').length")
            stop = total if last <= 0 else min(total, last)
            for number in range(max(1, first), stop + 1):
                page.evaluate("(i) => window.Reveal && Reveal.slide(i, 0)", number - 1)
                page.wait_for_timeout(150)
                if shots:
                    with contextlib.suppress(Exception):
                        page.wait_for_load_state("networkidle", timeout=4000)
                    page.wait_for_timeout(400)
                record = page.evaluate(PROBE)
                record["n"] = number
                records.append(record)
                if shots:
                    page.screenshot(path=str(out / f"slide_{number:02d}.png"))
            browser.close()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    for record in records:
        record["flags"] = slide_flags(record)
    (out / "report.json").write_text(json.dumps(records, indent=1), encoding="utf-8")
    header = f"viewport {width}x{height}, deck {Path(path)}"
    text = header + "\n" + "\n".join(_format_row(record) for record in records) + "\n"
    (out / "report.txt").write_text(text, encoding="utf-8")
    print(text, end="")
    return records
