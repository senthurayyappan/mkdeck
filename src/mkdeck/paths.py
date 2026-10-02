"""Where a deck's files come from and where they may go.

The model, the renderer and the builder all ask the same questions of a source
string: is it remote, which file on disk does it name, and does that file stay
inside the deck folder. They are answered here, once. `validate_src` and
`asset_path_error` judge the text alone; `resolve_inside` and `read_text` touch
the filesystem.
"""

import re
from pathlib import Path
from urllib.parse import unquote

from mkdeck._messages import suggest, warn_deck
from mkdeck.errors import DeckError

__all__ = [
    "ASSETS_DIRNAME",
    "ASSET_BASE",
    "ASSET_ROOT",
    "asset_path_error",
    "available_themes",
    "find_in_deck",
    "is_remote",
    "local_path",
    "read_text",
    "relative_url",
    "resolve_inside",
    "stays_inside",
    "theme_error",
    "validate_src",
]

ASSET_ROOT = Path(__file__).resolve().parent / "assets"
"""Folder holding the front-end assets shipped inside the wheel."""

ASSET_BASE = "mkdeck-assets"
"""Folder the shipped assets are copied into, next to `index.html`."""

ASSETS_DIRNAME = "assets"
"""The deck's own asset folder, copied into the output as it stands."""

_REMOTE_PREFIXES = ("http://", "https://", "//", "data:")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_URL_SCHEME = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*):(?P<slashes>//)?"
)
_OPAQUE_SCHEMES = frozenset(
    {"about", "blob", "data", "file", "javascript", "mailto", "tel", "vbscript"}
)
"""Schemes that are not followed by `//`.

Any other `name:` is a file name with a colon.
"""


def is_remote(src: str) -> bool:
    """Say whether the browser fetches a reference.

    Otherwise the file is read from the deck folder.

    Args:
        src: The reference, as the document holds it.

    Returns:
        True for an `http(s)://` URL, a protocol-relative `//` one or a `data:`
        URI, in any case.
    """
    return src.strip().lower().startswith(_REMOTE_PREFIXES)


def local_path(src: str) -> str:
    """Name the file a local reference points at, without its query or fragment.

    `figs/g3.html?seed=2#top` is the file `figs/g3.html`, and `a%20b.html` is `a
    b.html`, which is how the browser and a static server read them.

    Args:
        src: The reference, as the document holds it.

    Returns:
        The path of the file, relative to the deck folder.
    """
    return unquote(src.strip().split("?", 1)[0].split("#", 1)[0])


def relative_url(src: str) -> str:
    """Write a local reference so that a browser reads it as a path.

    A browser takes `run:3.html` for a URL with the scheme `run:`, so a file
    name with a colon in its first segment is written out as `./run:3.html`.

    Args:
        src: The reference from the deck.

    Returns:
        The reference to put in the document.
    """
    if is_remote(src) or ":" not in src.split("/", 1)[0]:
        return src
    return f"./{src}"


def stays_inside(path: Path, root: Path) -> bool:
    """Say whether a path stays inside a folder.

    The check runs once `..` and links are resolved.

    Args:
        path: The path to check. It need not exist.
        root: The folder it has to stay inside.

    Returns:
        True when `path` is `root` or a file under it.
    """
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def resolve_inside(root: Path, rel: str) -> Path | None:
    """Find the file a relative path names, refusing one that leaves the folder.

    Args:
        root: The folder the path has to stay inside.
        rel: The path, relative to `root`; use `local_path` on a reference
            first.

    Returns:
        The resolved path, links followed, or `None` when it leaves `root` or
        cannot name a file. The file need not exist.
    """
    # No file has a NUL in its name. POSIX rejects it in resolve();
    # Windows does not.
    if "\0" in rel:
        return None
    target = (root / rel).resolve()
    return target if stays_inside(target, root) else None


def find_in_deck(root: Path, rel: str, *, what: str) -> Path | None:
    """Find a file the deck refers to, refusing one outside the deck folder.

    Args:
        root: The deck folder.
        rel: The path of the file, relative to `root`; use `local_path` on a
            reference first.
        what: What the file is, used in the messages, such as `embed` or
            `stylesheet`.

    Returns:
        The resolved path of the file, or `None` when there is no such file,
        which is also reported as a `DeckWarning`.

    Raises:
        DeckError: If the path leaves the deck folder, by `..` or by a link.
    """
    path = resolve_inside(root, rel)
    if path is None:
        raise DeckError(
            f'The {what} "{rel}" leaves the deck folder; keep the file inside '
            f"the deck folder.",
            source=root,
        )
    if not path.is_file():
        warn_deck(f'The {what} "{rel}" was not found in the deck folder.')
        return None
    return path


def read_text(path: Path) -> str:
    """Read a UTF-8 text file the deck depends on.

    Args:
        path: The file to read.

    Returns:
        The text of the file.

    Raises:
        DeckError: If the file cannot be read or is not valid UTF-8.
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise DeckError(
            f"The file is not valid UTF-8 text (it breaks at byte "
            f"{error.start}); save it as UTF-8.",
            source=path,
        ) from error
    except OSError as error:
        raise DeckError(
            f"The file could not be read: {error.strerror}.", source=path
        ) from error


def available_themes() -> tuple[str, ...]:
    """List the themes that ship with mkdeck.

    Returns:
        The names of the stylesheets under `assets/themes`, without `.css`,
        sorted.
    """
    return tuple(
        sorted(path.stem for path in (ASSET_ROOT / "themes").glob("*.css"))
    )


def theme_error(theme: str) -> str | None:
    """Say why a theme name cannot be used.

    Args:
        theme: The name from `theme:` or `Deck.theme`.

    Returns:
        The error message, or `None` when a stylesheet of that name ships with
        mkdeck.
    """
    themes = available_themes()
    if theme in themes:
        return None
    return (
        f'The theme "{theme}" does not exist. '
        f"{suggest(theme, themes, noun='themes')}"
    )


def validate_src(src: str) -> str | None:
    """Check that an embed source stays inside the deck folder.

    The check is on the text alone. `resolve_inside` is the one that follows
    links.

    Args:
        src: The source to check.

    Returns:
        The reason the source is rejected, as a sentence, or `None` when it is
        fine.
    """
    text = src.strip()
    if not text:
        return (
            "The embed has an empty src; point it at a page or an image "
            "under the deck folder."
        )
    path = local_path(text)
    absolute = (
        f'The embed src "{src}" is an absolute path; make it relative '
        f"to the deck folder."
    )
    if _WINDOWS_DRIVE.match(path):
        return absolute
    scheme = _URL_SCHEME.match(text)
    if scheme is not None and (
        scheme.group("slashes")
        or scheme.group("scheme").lower() in _OPAQUE_SCHEMES
    ):
        if scheme.group("scheme").lower() in {"http", "https"}:
            return None
        return (
            f'The embed src "{src}" has a "{scheme.group("scheme")}:" scheme, '
            f"which is not supported; "
            "use a path relative to the deck folder, or an http(s) URL."
        )
    if "\0" in path:
        return (
            f"The embed src {src!r} holds a NUL character, which no file "
            f"name can; remove it."
        )
    if path.startswith(("/", "\\")):
        return absolute
    depth = 0
    for part in path.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return (
                    f'The embed src "{src}" leaves the deck folder; copy '
                    f"the file under the deck folder."
                )
        else:
            depth += 1
    return None


def asset_path_error(src: str, *, key: str) -> str | None:
    """Say why a stylesheet or script path cannot be used.

    A remote URL is accepted. Anything else has to stay inside the deck folder,
    by the same rule `validate_src` applies to an embed.

    Args:
        src: The path from `extra_css` or `extra_js`.
        key: The setting it was written under, used in the message.

    Returns:
        The error message, or `None` when the path may be linked.
    """
    if is_remote(src) or validate_src(src) is None:
        return None
    return (
        f'The path "{src}" under "{key}" has to stay inside the deck folder '
        f"or be an http(s) URL."
    )
