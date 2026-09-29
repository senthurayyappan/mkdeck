"""Install a built wheel into a clean virtualenv and check that it works.

The tests run against the source tree, and ``.gitignore`` swallows ``dist/``,
which is where reveal.js and KaTeX keep their files. A file left out of the
wheel is therefore invisible to the test suite and to a build that merely
succeeds. This script builds nothing; it takes what ``uv build`` produced and
answers four questions:

1. Does the wheel hold the vendored front end, the themes, ``py.typed`` and
   every license file?
2. Does the wheel install into an empty virtualenv outside the checkout, so
   nothing can be imported from ``src/``?
3. Do ``mkdeck new`` and ``mkdeck build`` work from that installation?
4. Does the source distribution carry the tests and everything they load, such
   as ``scripts/vendor_assets.py``, so its tests can be collected?

Usage::

    uv build --no-sources --clear
    uv run python scripts/smoke_wheel.py dist

Nothing here is imported by mkdeck, and it uses the standard library only.
"""

import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import NoReturn

REQUIRED_FILES = (
    "mkdeck/py.typed",
    "mkdeck/probe.js",
    "mkdeck/assets/mkdeck.js",
    "mkdeck/assets/mkdeck.css",
    "mkdeck/assets/mkdeck-rollout.js",
    "mkdeck/assets/templates/deck.html.jinja",
    "mkdeck/assets/themes/minimal.css",
    "mkdeck/assets/themes/dark.css",
    "mkdeck/assets/reveal.js/dist/reveal.js",
    "mkdeck/assets/reveal.js/dist/reveal.css",
    "mkdeck/assets/reveal.js/dist/reset.css",
    "mkdeck/assets/reveal.js/dist/plugin/notes.js",
    "mkdeck/assets/reveal.js/dist/plugin/zoom.js",
    "mkdeck/assets/katex/dist/katex.min.js",
    "mkdeck/assets/katex/dist/katex.min.css",
    "mkdeck/assets/katex/dist/fonts/OFL.txt",
    "mkdeck/assets/roboto/roboto.css",
    "mkdeck/assets/three/three.module.js",
    "mkdeck/assets/three/addons/controls/OrbitControls.js",
    "mkdeck/assets/viewer/rollout_viewer.js",
    "mkdeck/assets/viewer/bundle_parser.js",
    "mkdeck/assets/viewer/camera.js",
)
"""Paths the wheel has to hold, relative to its root."""

REQUIRED_SUFFIXES = (
    "mkdeck/assets/katex/dist/fonts/KaTeX_Main-Regular.woff2",
    "mkdeck/assets/roboto/fonts/roboto-latin-400-normal.woff2",
)
"""Font files whose names are fixed by their upstream packages."""

LICENSE_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "src/mkdeck/assets/reveal.js/LICENSE",
    "src/mkdeck/assets/katex/LICENSE",
    "src/mkdeck/assets/katex/dist/fonts/OFL.txt",
    "src/mkdeck/assets/roboto/LICENSE",
    "src/mkdeck/assets/three/LICENSE",
)
"""Files that have to sit under ``<name>.dist-info/licenses/``."""

SDIST_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "scripts/vendor_assets.py",
    "src/mkdeck/probe.js",
    "tests/conftest.py",
    "tests/rollout_reader.mjs",
    "tests/test_vendor_assets.py",
)
"""Paths the source distribution has to hold, relative to its root folder.

``tests/test_vendor_assets.py`` loads ``scripts/vendor_assets.py``, so a
source distribution without the script cannot even collect its tests.
"""

BUILT_FILES = (
    "index.html",
    "mkdeck-assets/reveal.js/dist/reveal.js",
    "mkdeck-assets/katex/dist/katex.min.js",
    "mkdeck-assets/themes/minimal.css",
)
"""Files a folder build has to write, relative to the output folder."""


def fail(message: str) -> NoReturn:
    """Report a failed check and stop.

    Args:
        message: What is wrong.

    Raises:
        SystemExit: Always.
    """
    raise SystemExit(f"smoke test failed: {message}")


def find_wheel(dist: Path) -> Path:
    """Find the one wheel in a build folder.

    Args:
        dist: The folder ``uv build`` wrote into.

    Returns:
        The wheel.
    """
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        fail(f"expected one wheel in {dist}, found {len(wheels)}")
    return wheels[0]


def check_contents(wheel: Path) -> None:
    """Check that the wheel holds every file a deck needs.

    Args:
        wheel: The built wheel.
    """
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    marker = next((name for name in names if name.endswith(".dist-info/WHEEL")), None)
    if marker is None:
        fail("the wheel has no .dist-info folder")
    licenses_dir = marker.removesuffix("WHEEL")
    missing = [path for path in REQUIRED_FILES if path not in names]
    missing += [path for path in REQUIRED_SUFFIXES if path not in names]
    licensed = [f"{licenses_dir}licenses/{path}" for path in LICENSE_FILES]
    missing += [path for path in licensed if path not in names]
    if missing:
        fail("the wheel is missing:\n  " + "\n  ".join(missing))
    stray = sorted(name for name in names if "__pycache__" in name or name.startswith(("tests/", ".github/")))
    if stray:
        fail("the wheel holds files that do not belong in it:\n  " + "\n  ".join(stray))
    print(f"ok: {wheel.name} holds {len(names)} entries, including the vendored assets and license files")


def find_sdist(dist: Path) -> Path:
    """Find the one source distribution in a build folder.

    Args:
        dist: The folder ``uv build`` wrote into.

    Returns:
        The source distribution.
    """
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(sdists) != 1:
        fail(f"expected one source distribution in {dist}, found {len(sdists)}")
    return sdists[0]


def check_sdist(sdist: Path) -> None:
    """Check that the source distribution holds the tests and what they load.

    Args:
        sdist: The built source distribution.
    """
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
    root = sdist.name.removesuffix(".tar.gz")
    missing = [path for path in SDIST_FILES if f"{root}/{path}" not in names]
    if missing:
        fail("the source distribution is missing:\n  " + "\n  ".join(missing))
    tests = [name for name in names if name.startswith(f"{root}/tests/test_")]
    print(f"ok: {sdist.name} holds {len(names)} entries, including {len(tests)} test modules and the scripts they load")


def run(command: list[str], *, cwd: Path) -> str:
    """Run a command and stop if it fails.

    Args:
        command: The program and its arguments.
        cwd: The folder to run in.

    Returns:
        What the command printed on standard output.
    """
    print(f"$ {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        fail(f"{' '.join(command)} exited with {result.returncode}\n{result.stdout}{result.stderr}")
    return result.stdout


def check_installation(wheel: Path) -> None:
    """Install the wheel into a clean virtualenv and use it from another folder.

    Args:
        wheel: The built wheel.
    """
    with tempfile.TemporaryDirectory(prefix="mkdeck-smoke-") as tmp:
        root = Path(tmp)
        venv = root / "venv"
        work = root / "work"
        work.mkdir()
        run(["uv", "venv", "--python", sys.executable, str(venv)], cwd=work)
        bindir = venv / ("Scripts" if sys.platform == "win32" else "bin")
        python = bindir / ("python.exe" if sys.platform == "win32" else "python")
        run(["uv", "pip", "install", "--python", str(python), str(wheel)], cwd=work)

        located = run([str(python), "-c", "import mkdeck; print(mkdeck.__file__)"], cwd=work).strip()
        if str(venv) not in located:
            fail(f"mkdeck was imported from {located}, not from the installed wheel")
        print(f"ok: mkdeck imports from {located}")

        mkdeck = str(bindir / ("mkdeck.exe" if sys.platform == "win32" else "mkdeck"))
        print(run([mkdeck, "--version"], cwd=work).strip())
        run([mkdeck, "new", "talk"], cwd=work)
        run([mkdeck, "build", "talk", "--out", "site"], cwd=work)
        absent = [name for name in BUILT_FILES if not (work / "site" / name).is_file()]
        if absent:
            fail("the folder build did not write:\n  " + "\n  ".join(absent))
        run([mkdeck, "build", "talk", "--single-file", "--out", "talk.html"], cwd=work)
        if not (work / "talk.html").is_file():
            fail("the single-file build did not write talk.html")
        print("ok: mkdeck new, build and build --single-file work from the installed wheel")


def main(args: list[str]) -> None:
    """Run every check against the wheel and the source distribution in a build folder.

    Args:
        args: The command line, holding the build folder (``dist`` by default).
    """
    dist = Path(args[0] if args else "dist").resolve()
    wheel = find_wheel(dist)
    check_contents(wheel)
    check_sdist(find_sdist(dist))
    check_installation(wheel)
    print("smoke test passed")


if __name__ == "__main__":
    main(sys.argv[1:])
