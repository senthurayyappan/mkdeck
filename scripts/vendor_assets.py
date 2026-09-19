"""Vendor the front-end libraries a built deck carries into ``src/mkdeck/assets/``.

reveal.js, KaTeX, Roboto and three.js would normally load from a CDN at view
time. A deck is meant to be built once and opened anywhere — on a plane, from a
USB stick, from an email attachment years later — so mkdeck ships them instead.
The downloaded files are committed, which is what lets ``mkdeck build`` work
with no network at all.

Every library comes from its npm tarball, so the pinned version is the one npm
published and the licence travels with it. Re-run to bump a pin; the result
should be reviewed as a diff like any other change::

    uv run python scripts/vendor_assets.py            # every library
    uv run python scripts/vendor_assets.py three      # just one

Nothing here is imported by mkdeck, and it uses the standard library only.
"""

import fnmatch
import io
import re
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "src" / "mkdeck" / "assets"
"""Where the vendored libraries live."""

REGISTRY = "https://registry.npmjs.org"
"""The npm registry the tarballs come from."""


@dataclass(frozen=True)
class Library:
    """One vendored library.

    Attributes:
        package: The npm package name, scope included.
        version: The pinned version.
        into: The folder under ``assets/`` the files land in.
        files: Pairs of source path inside the tarball and destination path
            under ``into``. A source may hold a ``*``, and then the
            destination is the folder its matches land in.
        after: Run over the destination folder once the files are written, for
            a library that needs the released copy adjusted.
    """

    package: str
    version: str
    into: str
    files: tuple[tuple[str, str], ...]
    after: Callable[[Path], None] | None = field(default=None, compare=False)

    @property
    def url(self) -> str:
        """Where npm serves this version's tarball."""
        return f"{REGISTRY}/{self.package}/-/{self.package.rsplit('/', 1)[-1]}-{self.version}.tgz"


COMMON = (("package.json", "package.json"), ("LICENSE", "LICENSE"))
"""Files every library keeps, so the pin and the licence stay with the code."""

_LEGACY_FONT_SRC = re.compile(r',url\(fonts/[^)]+\) format\("(?:woff|truetype)"\)')
"""The ``.woff`` and ``.ttf`` sources KaTeX lists beside each ``.woff2``."""


def _woff2_only(folder: Path) -> None:
    """Point KaTeX's stylesheet at the fonts that are actually vendored.

    KaTeX ships each face three times over; mkdeck keeps only the ``.woff2``,
    which every browser it targets reads. Left alone, the stylesheet would ask
    for two files per face that are not there.

    Args:
        folder: The vendored ``katex`` folder.
    """
    stylesheet = folder / "dist" / "katex.min.css"
    stylesheet.write_text(_LEGACY_FONT_SRC.sub("", stylesheet.read_text(encoding="utf-8")), encoding="utf-8")


LIBRARIES = (
    Library(
        package="reveal.js",
        version="6.0.2",
        into="reveal.js",
        files=(
            *COMMON,
            ("dist/reset.css", "dist/reset.css"),
            ("dist/reveal.css", "dist/reveal.css"),
            ("dist/reveal.js", "dist/reveal.js"),
            ("dist/plugin/notes.js", "dist/plugin/notes.js"),
            ("dist/plugin/zoom.js", "dist/plugin/zoom.js"),
            ("dist/plugin/highlight.js", "dist/plugin/highlight.js"),
        ),
    ),
    Library(
        package="katex",
        version="0.18.7",
        into="katex",
        files=(
            *COMMON,
            ("dist/katex.min.js", "dist/katex.min.js"),
            ("dist/katex.min.css", "dist/katex.min.css"),
            ("dist/fonts/*.woff2", "dist/fonts"),
        ),
        after=_woff2_only,
    ),
    Library(
        package="@fontsource/roboto",
        version="5.3.0",
        into="roboto",
        # roboto.css is mkdeck's own: three weights of the latin subset, no more.
        files=(
            ("LICENSE", "LICENSE"),
            ("files/roboto-latin-300-normal.woff2", "fonts/roboto-latin-300-normal.woff2"),
            ("files/roboto-latin-400-normal.woff2", "fonts/roboto-latin-400-normal.woff2"),
            ("files/roboto-latin-500-normal.woff2", "fonts/roboto-latin-500-normal.woff2"),
        ),
    ),
    # The rollout viewer's renderer. The pin matches the artifacts server's
    # viewer, which works around a camera.up quirk specific to r150's
    # OrbitControls; moving off r150 means re-reading that workaround.
    Library(
        package="three",
        version="0.150.1",
        into="three",
        files=(
            *COMMON,
            ("build/three.module.js", "three.module.js"),
            ("examples/jsm/controls/OrbitControls.js", "addons/controls/OrbitControls.js"),
        ),
    ),
)
"""Every library a built deck may carry."""


def fetch(library: Library) -> tarfile.TarFile:
    """Download one library's tarball.

    Args:
        library: The library to fetch.

    Returns:
        The opened tarball.

    Raises:
        SystemExit: If the registry cannot be reached or has no such version.
    """
    try:
        with urllib.request.urlopen(library.url, timeout=120) as response:
            payload = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"cannot fetch {library.package}@{library.version}: {exc}") from exc
    return tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")


def vendor(library: Library) -> int:
    """Write one library's files into the assets folder.

    Args:
        library: The library to vendor.

    Returns:
        The number of files written.

    Raises:
        SystemExit: If the tarball does not hold a file the pin names.
    """
    target = ASSETS / library.into
    written = 0
    with fetch(library) as tar:
        # npm puts everything under "package/"; members are matched against the
        # path below it so the pins read like the library's own layout.
        members = {name[len("package/") :]: name for name in tar.getnames() if name.startswith("package/")}
        for source, destination in library.files:
            matches = sorted(name for name in members if fnmatch.fnmatch(name, source))
            if not matches:
                raise SystemExit(f"{library.package}@{library.version} holds no {source}")
            for match in matches:
                out = target / destination / Path(match).name if "*" in source else target / destination
                extracted = tar.extractfile(members[match])
                if extracted is None:
                    raise SystemExit(f"{library.package}@{library.version} holds no readable {match}")
                out.parent.mkdir(parents=True, exist_ok=True)
                with extracted, out.open("wb") as handle:
                    shutil.copyfileobj(extracted, handle)
                written += 1
    if library.after is not None:
        library.after(target)
    return written


def main(names: list[str]) -> None:
    """Vendor the named libraries, or every one of them.

    Args:
        names: The folder names to refresh; empty for all of them.

    Raises:
        SystemExit: If a name matches no library.
    """
    chosen = [lib for lib in LIBRARIES if not names or lib.into in names or lib.package in names]
    unknown = set(names) - {lib.into for lib in chosen} - {lib.package for lib in chosen}
    if unknown:
        known = ", ".join(lib.into for lib in LIBRARIES)
        raise SystemExit(f"no such library: {', '.join(sorted(unknown))}. Known: {known}")
    for library in chosen:
        count = vendor(library)
        print(f"{library.package}@{library.version} -> assets/{library.into} ({count} files)")


if __name__ == "__main__":
    main(sys.argv[1:])
