"""Vendor the front-end libraries a built deck carries.

They are written into ``src/mkdeck/assets/``.

reveal.js, KaTeX, Roboto and three.js would normally load from a CDN at view
time. A deck is meant to be built once and opened anywhere — on a plane, from a
USB stick, from an email attachment years later — so mkdeck ships them instead.
The downloaded files are committed, which is what lets ``mkdeck build`` work
with no network at all.

Every library comes from its npm tarball, so the pinned version is the one npm
published and the licence travels with it. Each download is checked against the
``dist.integrity`` hash the registry publishes for that version, and the run
stops on a mismatch before it touches a file. A run also removes files that a
library's folder holds but its pin no longer names (bar the few mkdeck keeps
itself, listed per library), so the folder ends up exactly as the pins describe
it. Re-run to bump a pin; the result should be reviewed as a diff like any other
change. It needs network access and nothing but the standard library::

    uv run scripts/vendor_assets.py        # every library
    uv run scripts/vendor_assets.py three  # one library, by folder or name

three.js is pinned at r150 on purpose. The rollout viewer builds an
``OrbitControls`` that reads ``camera.up`` once, in its constructor, and never
refreshes it, which is how r150 behaves; the viewer rebuilds the controls
whenever the camera's up axis changes (see ``setCameraUp`` in
``assets/viewer/rollout_viewer.js``). Moving to a newer release means checking
that workaround still does what it is for, and that the viewer still runs
against the newer module.

Nothing here is imported by mkdeck. ``scripts/VENDOR_VIEWER.md`` says where the
viewer under ``assets/viewer/`` came from.
"""

import base64
import fnmatch
import hashlib
import io
import json
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
            under ``into``. A source may hold a ``*``, and then the destination
            is the folder its matches land in.
        keep: Paths under ``into`` that mkdeck maintains itself, which a run
            leaves alone when it removes files the pins no longer name.
        after: Run over the destination folder once the files are written, for a
            library that needs the released copy adjusted.
    """

    package: str
    version: str
    into: str
    files: tuple[tuple[str, str], ...]
    keep: tuple[str, ...] = ()
    after: Callable[[Path], None] | None = field(default=None, compare=False)

    @property
    def url(self) -> str:
        """Where npm serves this version's tarball."""
        filename = self.package.rsplit("/", 1)[-1]
        return f"{REGISTRY}/{self.package}/-/{filename}-{self.version}.tgz"


COMMON = (("package.json", "package.json"), ("LICENSE", "LICENSE"))
"""Files every library keeps, so the pin and the licence stay with the code."""

_LEGACY_FONT_SRC = re.compile(
    r',url\(fonts/[^)]+\) format\("(?:woff|truetype)"\)'
)
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
    stylesheet.write_text(
        _LEGACY_FONT_SRC.sub("", stylesheet.read_text(encoding="utf-8")),
        encoding="utf-8",
    )


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
        ),
    ),
    # The npm tarball's LICENSE covers the code. The fonts are SIL OFL, and
    # dist/fonts/OFL.txt is kept in the tree because the tarball does not ship
    # it.
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
        keep=("dist/fonts/OFL.txt",),
        after=_woff2_only,
    ),
    Library(
        package="@fontsource/roboto",
        version="5.3.0",
        into="roboto",
        # roboto.css is mkdeck's own: three weights of the latin subset, no
        # more.
        keep=("roboto.css",),
        files=(
            ("LICENSE", "LICENSE"),
            (
                "files/roboto-latin-300-normal.woff2",
                "fonts/roboto-latin-300-normal.woff2",
            ),
            (
                "files/roboto-latin-400-normal.woff2",
                "fonts/roboto-latin-400-normal.woff2",
            ),
            (
                "files/roboto-latin-500-normal.woff2",
                "fonts/roboto-latin-500-normal.woff2",
            ),
        ),
    ),
    # The rollout viewer's renderer. The pin is r150 because the viewer works
    # around how that release's OrbitControls reads camera.up; see the docstring
    # above before moving it.
    Library(
        package="three",
        version="0.150.1",
        into="three",
        files=(
            *COMMON,
            ("build/three.module.js", "three.module.js"),
            (
                "examples/jsm/controls/OrbitControls.js",
                "addons/controls/OrbitControls.js",
            ),
        ),
    ),
)
"""Every library a built deck may carry."""


def _get(url: str) -> bytes:
    """Download one URL.

    Args:
        url: The address to fetch.

    Returns:
        The body.

    Raises:
        SystemExit: If the registry cannot be reached or has no such file.
    """
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"cannot fetch {url}: {exc}") from exc


def verify(payload: bytes, dist: dict[str, str], label: str) -> None:
    """Check a tarball against the checksum npm published for it.

    Args:
        payload: The downloaded tarball.
        dist: The ``dist`` object of the version's registry document.
        label: The package and version, for the message.

    Raises:
        SystemExit: If the registry published no checksum, or the tarball does
            not match it.
    """
    if dist.get("integrity"):
        # An SRI string: one or more "<algorithm>-<base64 digest>" entries.
        expected = {
            entry.partition("-")[::2] for entry in dist["integrity"].split()
        }
        actual = {
            (
                algorithm,
                base64.b64encode(
                    hashlib.new(algorithm, payload).digest()
                ).decode(),
            )
            for algorithm, _ in expected
            if algorithm in hashlib.algorithms_available
        }
    elif dist.get("shasum"):
        expected, actual = (
            {("sha1", dist["shasum"])},
            {("sha1", hashlib.sha1(payload).hexdigest())},
        )
    else:
        raise SystemExit(
            f"{label}: the registry publishes no checksum for it, so it cannot "
            f"be verified."
        )
    if not expected & actual:
        raise SystemExit(
            f"{label}: the downloaded tarball does not match the checksum npm "
            f"published; not vendoring it."
        )


def fetch(library: Library) -> tarfile.TarFile:
    """Download one library's tarball and verify it.

    Args:
        library: The library to fetch.

    Returns:
        The opened tarball.

    Raises:
        SystemExit: If the registry cannot be reached, has no such version, or
            serves a tarball that does not match its published checksum.
    """
    label = f"{library.package}@{library.version}"
    document = json.loads(
        _get(f"{REGISTRY}/{library.package}/{library.version}")
    )
    payload = _get(library.url)
    verify(payload, document.get("dist", {}), label)
    return tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")


def _remove_stale(
    target: Path, written: set[Path], keep: tuple[str, ...]
) -> list[Path]:
    """Delete the files under a library's folder that no pin writes.

    Args:
        target: The library's folder under ``assets/``.
        written: The files this run wrote.
        keep: Paths under ``target`` that mkdeck maintains itself.

    Returns:
        The files removed.
    """
    kept = written | {target / name for name in keep}
    stale = sorted(
        path
        for path in target.rglob("*")
        if path.is_file() and path not in kept
    )
    for path in stale:
        path.unlink()
    for folder in sorted(
        (p for p in target.rglob("*") if p.is_dir()), reverse=True
    ):
        if not any(folder.iterdir()):
            folder.rmdir()
    return stale


def vendor(library: Library, *, root: Path = ASSETS) -> int:
    """Write one library's files into the assets folder.

    Args:
        library: The library to vendor.
        root: The assets folder to write under.

    Returns:
        The number of files written.

    Raises:
        SystemExit: If the tarball fails verification or does not hold a file
            the pin names.
    """
    target = root / library.into
    written: set[Path] = set()
    with fetch(library) as tar:
        # npm puts everything under "package/"; members are matched against the
        # path below it so the pins read like the library's own layout.
        members = {
            name[len("package/") :]: name
            for name in tar.getnames()
            if name.startswith("package/")
        }
        for source, destination in library.files:
            matches = sorted(
                name for name in members if fnmatch.fnmatch(name, source)
            )
            if not matches:
                raise SystemExit(
                    f"{library.package}@{library.version} holds no {source}"
                )
            for match in matches:
                out = (
                    target / destination / Path(match).name
                    if "*" in source
                    else target / destination
                )
                extracted = tar.extractfile(members[match])
                if extracted is None:
                    raise SystemExit(
                        f"{library.package}@{library.version} holds no "
                        f"readable {match}"
                    )
                out.parent.mkdir(parents=True, exist_ok=True)
                with extracted, out.open("wb") as handle:
                    shutil.copyfileobj(extracted, handle)
                written.add(out)
    for path in _remove_stale(target, written, library.keep):
        print(f"removed {path.relative_to(root)}")
    if library.after is not None:
        library.after(target)
    return len(written)


def main(names: list[str]) -> None:
    """Vendor the named libraries, or every one of them.

    Args:
        names: The folder names to refresh; empty for all of them.

    Raises:
        SystemExit: If a name matches no library.
    """
    chosen = [
        lib
        for lib in LIBRARIES
        if not names or lib.into in names or lib.package in names
    ]
    unknown = (
        set(names)
        - {lib.into for lib in chosen}
        - {lib.package for lib in chosen}
    )
    if unknown:
        known = ", ".join(lib.into for lib in LIBRARIES)
        raise SystemExit(
            f"no such library: {', '.join(sorted(unknown))}. Known: {known}"
        )
    for library in chosen:
        count = vendor(library)
        print(
            f"{library.package}@{library.version} -> "
            f"assets/{library.into} ({count} files)"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
