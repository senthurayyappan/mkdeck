"""``scripts/vendor_assets.py``: it must not vendor a tarball npm did not
publish.
"""

import base64
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vendor_assets.py"
spec = importlib.util.spec_from_file_location("vendor_assets", SCRIPT)
assert spec is not None and spec.loader is not None
vendor_assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vendor_assets)


def tarball(files: dict[str, bytes]) -> bytes:
    """An npm-shaped tarball: everything under ``package/``."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in files.items():
            member = tarfile.TarInfo(f"package/{name}")
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def integrity(payload: bytes) -> str:
    return (
        "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode()
    )


LIBRARY = vendor_assets.Library(
    package="thing",
    version="1.0.0",
    into="thing",
    files=(("package.json", "package.json"), ("dist/*.js", "dist")),
    keep=("mine.css",),
)


@pytest.fixture
def registry(monkeypatch):
    """Serve one fabricated package, with whatever checksum a test asks for."""
    served = {}

    def get(url: str) -> bytes:
        return served[url]

    def publish(payload: bytes, dist: dict) -> None:
        served[f"{vendor_assets.REGISTRY}/thing/1.0.0"] = json.dumps(
            {"dist": dist}
        ).encode()
        served[LIBRARY.url] = payload

    monkeypatch.setattr(vendor_assets, "_get", get)
    return publish


def test_a_matching_integrity_passes() -> None:
    payload = tarball({"package.json": b"{}"})
    vendor_assets.verify(
        payload, {"integrity": integrity(payload)}, "thing@1.0.0"
    )


def test_a_matching_sha1_is_accepted_when_there_is_no_integrity() -> None:
    payload = tarball({"package.json": b"{}"})
    vendor_assets.verify(
        payload, {"shasum": hashlib.sha1(payload).hexdigest()}, "thing@1.0.0"
    )


def test_a_tarball_that_is_not_the_published_one_is_refused() -> None:
    payload = tarball({"package.json": b"{}"})
    forged = tarball({"package.json": b'{"evil": true}'})
    with pytest.raises(SystemExit, match="does not match"):
        vendor_assets.verify(
            forged, {"integrity": integrity(payload)}, "thing@1.0.0"
        )


def test_a_version_with_no_published_checksum_is_refused() -> None:
    with pytest.raises(SystemExit, match="no checksum"):
        vendor_assets.verify(b"anything", {}, "thing@1.0.0")


def test_vendoring_stops_before_writing_when_the_checksum_fails(
    registry, tmp_path
) -> None:
    good = tarball({"package.json": b"{}", "dist/a.js": b"a"})
    registry(
        tarball({"package.json": b"{}", "dist/a.js": b"tampered"}),
        {"integrity": integrity(good)},
    )
    with pytest.raises(SystemExit, match="does not match"):
        vendor_assets.vendor(LIBRARY, root=tmp_path)
    assert not (tmp_path / "thing").exists()


def test_vendoring_writes_the_pinned_files_and_removes_the_stale_ones(
    registry, tmp_path, capsys
) -> None:
    payload = tarball(
        {
            "package.json": b'{"v": 1}',
            "dist/a.js": b"a",
            "dist/b.js": b"b",
            "other.txt": b"x",
        }
    )
    registry(payload, {"integrity": integrity(payload)})
    folder = tmp_path / "thing"
    (folder / "dist").mkdir(parents=True)
    (folder / "dist" / "old.js").write_text("left over from an earlier pin")
    (folder / "gone" / "deep").mkdir(parents=True)
    (folder / "gone" / "deep" / "x.txt").write_text("stale")
    (folder / "mine.css").write_text("kept: mkdeck maintains it")
    assert vendor_assets.vendor(LIBRARY, root=tmp_path) == 3
    assert sorted(
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    ) == [
        "dist/a.js",
        "dist/b.js",
        "mine.css",
        "package.json",
    ]
    assert not (folder / "gone").exists()
    assert f"removed {Path('thing/dist/old.js')}" in capsys.readouterr().out
