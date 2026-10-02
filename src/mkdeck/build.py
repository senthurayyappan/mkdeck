"""Write a deck to a folder, or to one HTML file, with the files it needs."""

import json
import os
import posixpath
import shutil
from pathlib import Path

from mkdeck._messages import warn_deck
from mkdeck.errors import DeckError
from mkdeck.inline import VIEWER_MODULES, inline_assets, inline_rollouts
from mkdeck.model import (
    ROLLOUT_SUFFIXES,
    Deck,
    deck_has_rollouts,
    resolve_embed_kind,
)
from mkdeck.paths import (
    ASSET_BASE,
    ASSET_ROOT,
    ASSETS_DIRNAME,
    find_in_deck,
    is_remote,
    local_path,
    stays_inside,
)
from mkdeck.render import render_deck
from mkdeck.rollout import MESHES_SUFFIX, meshes_of

__all__ = [
    "EMBED_WARN_BYTES",
    "MANIFEST_NAME",
    "ROLLOUT_ASSETS",
    "build_deck",
]

ROLLOUT_ASSETS = frozenset(
    {path.split("/", 1)[0] for _, path in VIEWER_MODULES}
    | {"mkdeck-rollout.js"}
)
"""The viewer and its renderer, carried only by a deck that draws a rollout.

three.js is a megabyte, so a deck of plots and images does not pay for it.
"""

EMBED_WARN_BYTES = 2_000_000
"""An embed larger than this is called out at build time."""

MANIFEST_NAME = ".mkdeck-build.json"
"""The list of files a build wrote.

The next build into the folder sweeps it clean.
"""

_NON_RUNTIME = frozenset({"package.json", "VENDOR.md"})
"""Files that sit with the vendored libraries but that no deck loads."""

_INLINED_SUFFIXES = (*ROLLOUT_SUFFIXES, MESHES_SUFFIX)
"""Files a single-file build folds into the document.

It does not copy them beside the document.
"""


def _copy(origin: Path, out: Path, rel: str, written: set[str]) -> None:
    """Copy one file to `out/rel`, unless this build already has.

    Only the contents are copied. The copy is a new file that the person running
    the build can write and that takes their umask, whatever the mode of the
    original: a read-only file, or one that a tool wrote as readable by its
    owner alone, is not passed on.

    Args:
        origin: The file to copy.
        out: The output folder.
        rel: The path in the output, relative to `out`, in the form `_relative`
            gives.
        written: The paths this build has written; `rel` is added to it.
    """
    if rel in written:
        return
    written.add(rel)
    destination = out / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Replace a link, or a read-only file an older build left, rather
    # than write through it.
    destination.unlink(missing_ok=True)
    shutil.copyfile(origin, destination)


def _relative(src: str) -> str:
    """Name where a reference from the document lands in the output folder.

    Args:
        src: The reference, as the document holds it.

    Returns:
        The normalised path of its file, relative to the deck folder.
    """
    return posixpath.normpath(local_path(src))


def _copy_vendor_assets(
    out: Path, *, theme: str, rollouts: bool, written: set[str]
) -> None:
    """Copy the front-end files a deck loads next to `index.html`.

    Only what runs is copied: no template, no package metadata, no theme the
    deck does not use, and the rollout viewer only for a deck that draws a
    rollout. The license files of the vendored libraries go with them.

    Args:
        out: The output folder.
        theme: The theme the deck uses.
        rollouts: True when a slide draws a rollout, which is what the viewer
            and its renderer are carried for.
        written: The paths this build has written.
    """
    skip = {"templates"} | (set() if rollouts else ROLLOUT_ASSETS)
    for entry in sorted(ASSET_ROOT.iterdir()):
        if entry.name in skip:
            continue
        for path in [entry] if entry.is_file() else sorted(entry.rglob("*")):
            rel = path.relative_to(ASSET_ROOT)
            if (
                not path.is_file()
                or path.name in _NON_RUNTIME
                or (rel.parts[0] == "themes" and path.stem != theme)
            ):
                continue
            _copy(path, out, f"{ASSET_BASE}/{rel.as_posix()}", written)


def _copy_assets_tree(
    source: Path, out: Path, *, rollouts: bool, written: set[str]
) -> None:
    """Copy the deck's `assets/` folder into the output, file by file.

    A link that leaves the deck folder is not followed, and neither is a link to
    a folder. Hidden files and folders are left behind, and so is the output
    folder itself when it sits inside `assets/`.

    Args:
        source: The deck source folder.
        out: The output folder.
        rollouts: False when a single-file build folds the rollouts into the
            document, so their files are not copied beside it.
        written: The paths this build has written.

    Raises:
        DeckError: If `assets` itself is a link out of the deck folder.
    """
    tree = source / ASSETS_DIRNAME
    if not tree.is_dir():
        return
    if not stays_inside(tree, source):
        raise DeckError(
            f'The folder "{ASSETS_DIRNAME}" leaves the deck folder; keep it '
            f"inside the deck folder.",
            source=source,
        )
    for folder, dirnames, filenames in os.walk(tree):
        here = Path(folder)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".")
            and (here / name).resolve() != out.resolve()
        )
        for name in dirnames:
            if (here / name).is_symlink():
                warn_deck(
                    f"The folder "
                    f'"{(here / name).relative_to(source).as_posix()}" is a '
                    f"link, so it was not copied."
                )
        for name in sorted(filenames):
            path = here / name
            rel = path.relative_to(source).as_posix()
            if (
                name.startswith(".")
                or not path.is_file()
                or (not rollouts and path.suffix in _INLINED_SUFFIXES)
            ):
                continue
            if not stays_inside(path, source):
                warn_deck(
                    f'The file "{rel}" is a link out of the deck folder, so it '
                    f"was not copied."
                )
                continue
            _copy(path, out, rel, written)


def _copy_embeds(
    deck: Deck, out: Path, *, source: Path, rollouts: bool, written: set[str]
) -> None:
    """Copy every local file the slides embed, and the meshes a rollout shares.

    A deck normally shows the same embed on several slides, so each one is
    handled once: the file is copied once and its warning is said once.

    Args:
        deck: The deck being built.
        out: The output folder.
        source: The deck source folder.
        rollouts: False when a single-file build has already folded the rollouts
            into the document, so their files are not copied beside it.
        written: The paths this build has written.

    Raises:
        DeckError: If an embed, or the meshes a rollout names, is outside the
            deck folder.
    """
    seen: set[str] = set()
    for slide in deck.slides:
        for embed in slide.embeds:
            rel = _relative(embed.src)
            if is_remote(embed.src) or rel in seen:
                continue
            seen.add(rel)
            is_rollout = resolve_embed_kind(embed) == "rollout"
            if is_rollout and not rollouts:
                continue
            origin = find_in_deck(source, rel, what="embed")
            if origin is None:
                continue
            size = origin.stat().st_size
            if size > EMBED_WARN_BYTES:
                warn_deck(
                    f"The embed {embed.src} is {size / 1_000_000:.1f} MB; a "
                    f"deck full of these is slow to open."
                )
            _copy(origin, out, rel, written)
            # A rollout names its shared meshes rather than the document doing
            # it, so
            # the file every run of one model points at is copied here.
            if is_rollout and (meshes := meshes_of(origin)) is not None:
                shared_rel = posixpath.join(posixpath.dirname(rel), meshes)
                if shared := find_in_deck(
                    source, shared_rel, what="shared meshes"
                ):
                    _copy(shared, out, shared_rel, written)


def _copy_extras(
    deck: Deck, out: Path, *, source: Path, written: set[str]
) -> None:
    """Copy the stylesheets and scripts the deck adds.

    Their paths stay relative to the deck.

    Args:
        deck: The deck being built.
        out: The output folder.
        source: The deck source folder.
        written: The paths this build has written.

    Raises:
        DeckError: If one of them is outside the deck folder.
    """
    for src in (*deck.extra_css, *deck.extra_js):
        if is_remote(src):
            continue
        rel = _relative(src)
        if (
            origin := find_in_deck(source, rel, what="stylesheet or script")
        ) is not None:
            _copy(origin, out, rel, written)


def _sweep(out: Path, written: set[str]) -> None:
    """Remove what the previous build wrote and this one did not.

    Then record this build.

    Only files named in the previous build's manifest are removed, so nothing
    the author put in the folder is touched.

    Args:
        out: The output folder.
        written: The paths this build has written.
    """
    manifest = out / MANIFEST_NAME
    try:
        previous = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    except (OSError, ValueError, KeyError, TypeError):
        previous = []
    for rel in previous if isinstance(previous, list) else []:
        path = out / str(rel)
        if rel in written or not stays_inside(path.parent, out):
            continue
        try:
            path.unlink(missing_ok=True)
            for parent in path.parents:
                if parent == out or any(parent.iterdir()):
                    break
                parent.rmdir()
        except OSError:
            continue
    manifest.write_text(
        json.dumps({"files": sorted(written)}, indent=1), encoding="utf-8"
    )


def build_deck(
    deck: Deck,
    out: Path | str = "site",
    *,
    source: Path | str | None = None,
    single_file: bool = False,
    live_reload: bool = False,
) -> Path:
    """Write a deck to an output folder.

    `Deck.build` is the public way to call this.

    Building again into the same folder brings it up to date: every file is
    copied afresh, and a file the previous build wrote that this one no longer
    needs is removed.

    Args:
        deck: The deck to build.
        out: The output folder, or the HTML file itself when `single_file` is
            set and the path ends in `.html`.
        source: The deck source folder, used to copy the deck's own assets; the
            current directory when omitted.
        single_file: True to fold the stylesheets and scripts into the document,
            so the result opens from a `file://` URL.
        live_reload: True to add the client that reloads the page when the dev
            server rebuilds the deck. Only the dev server sets it.

    Returns:
        The path of the written HTML document.

    Raises:
        DeckError: If a slide breaks a rule of the model, the source folder does
            not exist, the output folder is the source folder or its `assets`
            folder, or a file the deck names is outside the deck folder.
    """
    out = Path(out)
    folder = Path(source) if source is not None else Path.cwd()
    if not folder.is_dir():
        raise DeckError(
            "The source folder does not exist or is not a folder.",
            source=folder,
        )
    root: Path | None = folder
    into_file = single_file and out.suffix.lower() in {".html", ".htm"}
    directory, index = (
        (out.parent, out) if into_file else (out, out / "index.html")
    )
    if directory.resolve() == folder.resolve():
        if source is not None:
            raise DeckError(
                "The output folder is the deck source folder; write the build "
                "somewhere else with -o."
            )
        # a Python deck built into the folder it lives in: its files are already
        # there
        root = None
    elif directory.resolve() == (folder / ASSETS_DIRNAME).resolve():
        raise DeckError(
            f"The output folder is the deck's {ASSETS_DIRNAME} folder, which "
            f"the build copies into it; "
            "write the build somewhere else with -o."
        )

    html = render_deck(deck, live_reload=live_reload)
    rollouts = deck_has_rollouts(deck)
    if single_file:
        html = inline_assets(html, source=folder)
        if rollouts:
            html = inline_rollouts(html, deck, source=folder)
    directory.mkdir(parents=True, exist_ok=True)
    written = {index.relative_to(directory).as_posix()}
    if not single_file:
        _copy_vendor_assets(
            directory, theme=deck.theme, rollouts=rollouts, written=written
        )
    if root is not None:
        _copy_assets_tree(
            root, directory, rollouts=not single_file, written=written
        )
        _copy_embeds(
            deck,
            directory,
            source=root,
            rollouts=not single_file,
            written=written,
        )
        if not single_file:
            _copy_extras(deck, directory, source=root, written=written)
    index.write_text(html, encoding="utf-8")
    if (
        not into_file
    ):  # a lone HTML file may sit in a folder the build does not own
        _sweep(directory, written)
    return index
