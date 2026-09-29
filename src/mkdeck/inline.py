"""Fold a rendered deck into one HTML file: its stylesheets, scripts, fonts and rollouts.

A folder build links `mkdeck-assets/` and the deck's own extras next to `index.html`. A
single-file build reads them instead and writes them into the document, so it opens from
a `file://` URL. Only the tags of the template are folded; the slides, which may hold the
author's own HTML, are left as written.
"""

import base64
import re
from html import unescape
from pathlib import Path, PurePosixPath

from markupsafe import escape

from mkdeck._messages import warn_deck
from mkdeck.model import Deck, resolve_embed_kind
from mkdeck.paths import (
    ASSET_BASE,
    ASSET_ROOT,
    find_in_deck,
    is_remote,
    local_path,
    read_text,
    relative_url,
    stays_inside,
)
from mkdeck.rollout import meshes_of

__all__ = ["PAYLOAD_MARKER", "SLIDES_CLOSE", "SLIDES_OPEN", "VIEWER_MODULES", "inline_assets", "inline_rollouts"]

PAYLOAD_MARKER = "<!--mkdeck-payloads-->"
"""Where in the head a single-file build puts the viewer and the rollouts."""

SLIDES_OPEN = "<!--mkdeck-slides-->"
SLIDES_CLOSE = "<!--/mkdeck-slides-->"
"""Fence the slides in the template, so single-file inlining leaves the author's HTML alone."""

VIEWER_MODULES: tuple[tuple[str, str], ...] = (
    ("three", "three/three.module.js"),
    ("three/addons/controls/OrbitControls.js", "three/addons/controls/OrbitControls.js"),
    ("rollout-bundle", "viewer/bundle_parser.js"),
    ("mkdeck-camera", "viewer/camera.js"),
    ("mkdeck-viewer", "viewer/rollout_viewer.js"),
)
"""The viewer's modules, by import specifier and path under the assets. The twin of MODULES in mkdeck-rollout.js."""

_CSS_REF = re.compile(
    r"""@import\s+(?:url\(\s*(?P<iquote>['"]?)(?P<iurl>[^'")]+)(?P=iquote)\s*\)|(?P<squote>['"])(?P<surl>[^'"]+)(?P=squote))"""
    r"""(?P<media>[^;{}]*);"""
    r"""|url\(\s*(?P<quote>['"]?)(?P<target>[^'")]+)(?P=quote)\s*\)"""
)
_ASSET_TAG = re.compile(
    r"""(?P<link><link\b[^>]*\brel=["']stylesheet["'][^>]*>)"""
    r"""|(?P<script><script\b[^>]*\bsrc=["'](?P<src>[^"']+)["'][^>]*>\s*</script>)""",
    re.IGNORECASE,
)
_HREF = re.compile(r"""\bhref=["'](?P<href>[^"']+)["']""", re.IGNORECASE)

_MEDIA_TYPES = {
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _media_type(path: Path) -> str:
    """Guess the media type of a file inlined as a `data:` URI.

    Args:
        path: The file being inlined.

    Returns:
        A media type string.
    """
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _script_safe(text: str, tag: str) -> str:
    """Hide from the HTML parser what would end, or confuse, an inlined element.

    Args:
        text: The source of a script or a stylesheet.
        tag: `script` or `style`, the element it is going into.

    Returns:
        The source with a closing tag, and in a script an opening comment, escaped. Both
        escapes read the same to JavaScript and CSS.
    """
    text = text.replace(f"</{tag}", f"<\\/{tag}")
    return text.replace("<!--", "<\\!--") if tag == "script" else text


def _inline_css(text: str, *, base: Path, root: Path, chain: tuple[Path, ...] = ()) -> str:
    """Inline what a stylesheet refers to: its `@import`s and its `url(...)` files.

    A local `url(...)` becomes a `data:` URI and a local `@import` becomes the stylesheet
    it names, inlined in turn. A remote reference is left alone. One that resolves outside
    `root`, or cannot be found, is reported and its file is not read.

    Args:
        text: The stylesheet source.
        base: The folder the stylesheet was read from.
        root: The folder a reference has to stay inside.
        chain: The stylesheets being inlined, outermost first, to catch a loop of imports.

    Returns:
        The stylesheet with every resolvable local reference inlined.
    """

    def replace(match: re.Match[str]) -> str:
        imported = match.group("iurl") or match.group("surl")
        target = (imported or match.group("target")).strip()
        if not target or is_remote(target) or (not imported and target.startswith("#")):
            return match.group(0)
        path = (base / local_path(target)).resolve()
        if not stays_inside(path, root):
            warn_deck(
                f'The stylesheet refers to "{target}", which leaves the deck folder, so the reference was dropped.'
            )
            return "" if imported else "url('')"
        if not path.is_file():
            warn_deck(f'The stylesheet refers to "{target}", which was not found, so the reference stays as written.')
            return match.group(0)
        if not imported:
            payload = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"url(data:{_media_type(path)};base64,{payload})"
        if path in chain:
            warn_deck(f'The stylesheet "{target}" imports itself, so the import was dropped.')
            return ""
        css = _inline_css(read_text(path), base=path.parent, root=root, chain=(*chain, path))
        media = match.group("media").strip()
        return f"@media {media} {{{css}}}" if media else css

    return _CSS_REF.sub(replace, text)


def _locate_asset(href: str, *, source: Path | None) -> tuple[Path, Path] | None:
    """Find the file a stylesheet or script reference points at.

    Args:
        href: The reference, HTML-unescaped.
        source: The deck source folder, for the deck's own extras.

    Returns:
        The file and the folder it has to stay inside, or `None` when the reference is
        remote or the file is missing (a missing one is reported).

    Raises:
        DeckError: If the reference leaves the folder it belongs to.
    """
    if not href or is_remote(href):
        return None
    prefix = f"{ASSET_BASE}/"
    if href.startswith(prefix):
        path = find_in_deck(ASSET_ROOT, local_path(href[len(prefix) :]), what="bundled asset")
        return (path, ASSET_ROOT) if path is not None else None
    if source is None:
        return None
    path = find_in_deck(source, local_path(href), what="stylesheet or script")
    return (path, source) if path is not None else None


def inline_assets(html: str, *, source: Path | str | None = None) -> str:
    """Fold every stylesheet and script of a rendered deck into the document.

    Only the tags of the template are touched; the slides, which may hold the author's
    own HTML, are left as written. Fonts and images a stylesheet refers to become `data:`
    URIs, and its `@import`s are inlined, so the result opens from a `file://` URL with
    only the deck's own figures left outside. A reference to a CDN is left alone.

    Args:
        html: The rendered document.
        source: The deck source folder, for the deck's own extras.

    Returns:
        The document with its stylesheets and scripts inlined.

    Raises:
        DeckError: If a stylesheet or script leaves the deck folder, or cannot be read.
    """
    folder = Path(source) if source is not None else None

    def fold(match: re.Match[str]) -> str:
        if match.group("link"):
            found = _HREF.search(match.group("link"))
            href = unescape(found.group("href")) if found else ""
        else:
            href = unescape(match.group("src"))
        located = _locate_asset(href, source=folder)
        if located is None:
            return match.group(0)
        path, root = located
        text = read_text(path)
        if match.group("link"):
            css = _inline_css(text, base=path.parent, root=root, chain=(path,))
            return f"<style>{_script_safe(css, 'style')}</style>"
        return f"<script>{_script_safe(text, 'script')}</script>"

    # The slides are fenced off, so a tag the author wrote in one is not mistaken for ours.
    before, opened, rest = html.partition(SLIDES_OPEN)
    slides, closed, after = rest.rpartition(SLIDES_CLOSE)
    if not opened or not closed:
        return _ASSET_TAG.sub(fold, html)
    return _ASSET_TAG.sub(fold, before) + opened + slides + closed + _ASSET_TAG.sub(fold, after)


def _inline_payload(attribute: str, key: str, text: str) -> str:
    """Wrap one inlined source or payload in the tag the loader looks for.

    A `<script>` element holds raw text, so only a closing tag has to be
    hidden; the loader reads the content back with `textContent`.

    Args:
        attribute: The data attribute the loader queries on.
        key: The value of that attribute.
        text: The content to carry.

    Returns:
        The element, as HTML.
    """
    return f'<script type="text/plain" {attribute}="{escape(key)}">{_script_safe(text, "script")}</script>'


def inline_rollouts(html: str, deck: Deck, *, source: Path | str | None = None) -> str:
    """Fold the rollout viewer and every rollout into a rendered deck.

    A rollout is binary and its viewer is a set of ES modules, neither of which
    a `file://` page may fetch. Both are carried as text instead — the
    modules verbatim, the binaries base64 — and `mkdeck-rollout.js` reads
    them from the document rather than from the network.

    Args:
        html: The rendered document, with its scripts already inlined.
        deck: The deck being built, for the rollouts its slides name.
        source: The deck source folder the rollouts sit in; the current directory when
            omitted.

    Returns:
        The document with the viewer and the rollouts inside it.

    Raises:
        DeckError: If a rollout, or the meshes it names, is outside the deck folder.
    """
    root = Path(source) if source is not None else Path.cwd()
    parts: list[str] = []
    for specifier, path in VIEWER_MODULES:
        parts.append(_inline_payload("data-mkd-module", specifier, read_text(ASSET_ROOT / path)))

    carried: set[str] = set()
    for slide in deck.slides:
        for embed in slide.embeds:
            if resolve_embed_kind(embed) != "rollout" or is_remote(embed.src):
                continue
            emitted = relative_url(embed.src)
            run = find_in_deck(root, local_path(embed.src), what="rollout")
            if run is None:
                continue
            files = [(emitted, run)]
            if (meshes := meshes_of(run)) is not None:
                # The viewer asks for the meshes by the folder of the rollout's own src, plus their name.
                key = emitted[: emitted.rfind("/") + 1] + meshes
                shared = find_in_deck(
                    root, str(PurePosixPath(local_path(embed.src)).parent / meshes), what="shared meshes"
                )
                if shared is not None:
                    files.append((key, shared))
            for key, origin in files:
                if key not in carried:
                    carried.add(key)
                    payload = base64.b64encode(origin.read_bytes()).decode("ascii")
                    parts.append(_inline_payload("data-mkd-rollout", key, payload))

    # The payloads go in the head: the loader looks for them the moment a slide
    # asks for a rollout, which can be while the document is still parsing, so
    # they have to be behind the parser before any script runs. They go at a
    # marker rather than at "</head>", because by now the document carries
    # three.js, whose own source holds that text and would be found first.
    block = "\n".join(parts)
    if PAYLOAD_MARKER in html:
        return html.replace(PAYLOAD_MARKER, block, 1)
    warn_deck("The deck template has no payload marker, so the rollouts went at the end of the document.")
    return html + block
