"""Turn a Brax playback page into a rollout the deck can show offline.

A Brax ``html.render`` page carries its whole world inline: six CDN modules and
one base64 zlib blob holding every mesh alongside the trajectory. The meshes are
~99% of it, and a deck that shows one robot over thirty slides ships thirty
copies of that robot.

This module splits the two apart. The meshes of one model go into a shared
``.meshes`` file named after their content hash, so every run of that model
points at the same bytes; each run keeps only its per-frame poses, in a
``.rollout`` file. The pair is a ``.rbundle`` cut in half: the reader in
:mod:`mkdeck.assets` glues the two tails back together and hands the viewer the
exact wire form it already reads, which is why a whole ``.rbundle`` pushed to an
artifacts server also plays in a deck without conversion.

Wire format, which the JavaScript reader defines its twin of::

    [4B "RSPL"][8B LE uint64 headerLen][headerLen B UTF-8 JSON][gzipped tail]

The header is padded with trailing spaces so the tail starts on an 8-byte
boundary, exactly as ``.rbundle`` does, and ``headerLen`` counts that padding.
Offsets in it index the *combined* tail — the shared mesh tail first, then this
run's pose tail — so the reader concatenates and never rewrites an offset.
"""

import base64
import gzip
import hashlib
import json
import re
import struct
import sys
import zlib
from array import array
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Any

from mkdeck.errors import DeckError

MAGIC = b"RSPL"
"""The four bytes a ``.rollout`` starts with."""

FORMAT_VERSION = 1
"""The version of the container written here."""

MESHES_SUFFIX = ".meshes"
"""The suffix of the shared geometry file a rollout points at."""

ROLLOUT_SUFFIX = ".rollout"
"""The suffix of the per-run file."""

_SCENE = re.compile(r'var system = "([A-Za-z0-9+/=]+)"')
"""The assignment a Brax page holds its zlib-compressed scene in."""

_GEOM_TYPES = {
    "plane": "plane",
    "box": "box",
    "sphere": "sphere",
    "capsule": "capsule",
    "cylinder": "cylinder",
    "ellipsoid": "ellipsoid",
    "mesh": "mesh",
}
"""Brax names its geoms after their class; the viewer wants the lowercase form."""

_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)
"""The world body never moves, so every frame repeats this rotation."""


@dataclass(frozen=True)
class Rollout:
    """One converted run, ready to write.

    Attributes:
        header: The JSON header, with offsets into the combined tail.
        meshes: The shared mesh tail, uncompressed.
        poses: This run's pose tail, uncompressed.
    """

    header: dict[str, Any]
    meshes: bytes
    poses: bytes

    @property
    def meshes_hash(self) -> str:
        """The content hash the shared mesh file is named after."""
        return hashlib.sha256(self.meshes).hexdigest()[:16]


@dataclass(frozen=True)
class Converted:
    """Where one conversion put its files.

    Attributes:
        rollout: The written ``.rollout``.
        meshes: The shared ``.meshes`` the rollout points at.
        shared: True when the mesh file was already there, written by an
            earlier run of the same model.
    """

    rollout: Path
    meshes: Path
    shared: bool


def _f32(values: Iterable[Any]) -> bytes:
    """Pack a nested sequence of numbers as little-endian float32.

    Args:
        values: Rows of numbers, such as a list of ``[x, y, z]``.

    Returns:
        The packed bytes.
    """
    packed = array("f", chain.from_iterable(values))
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def _u32(values: Iterable[Any]) -> bytes:
    """Pack a nested sequence of indices as little-endian uint32.

    Args:
        values: Rows of indices, such as a list of ``[i, j, k]``.

    Returns:
        The packed bytes.
    """
    packed = array("I", chain.from_iterable(values))
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def read_brax_scene(path: Path | str) -> dict[str, Any]:
    """Read the scene a Brax playback page holds inline.

    Args:
        path: The ``.html`` Brax wrote.

    Returns:
        The decoded scene, as ``brax.io.json`` wrote it.

    Raises:
        DeckError: If the page holds no scene, or holds one that will not
            decode.
    """
    path = Path(path)
    try:
        page = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise DeckError(f"Cannot read {path}: {exc}") from exc
    found = _SCENE.search(page)
    if found is None:
        raise DeckError(f"{path} holds no Brax scene; it has no 'var system = \"...\"' line.")
    try:
        return json.loads(zlib.decompress(base64.b64decode(found.group(1))))
    except (ValueError, zlib.error) as exc:
        raise DeckError(f"{path} holds a Brax scene that will not decode: {exc}") from exc


def _geoms(scene: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Walk every geom in the scene, in the order the groups hold them.

    Args:
        scene: A decoded Brax scene.

    Yields:
        One geom at a time.
    """
    for group in scene.get("geoms", {}).values():
        yield from group


def _pose_tail(scene: dict[str, Any], bodies: int) -> tuple[bytes, int]:
    """Pack every frame's body positions and rotations.

    Body 0 is the world, which Brax leaves out of its state because it never
    moves; it is written as the identity so a geom fixed to the world needs no
    special case in the viewer.

    Args:
        scene: A decoded Brax scene.
        bodies: The body count, the world included.

    Returns:
        The positions, the rotations, and the frame count.

    Raises:
        DeckError: If the scene holds no frames.
    """
    frames = scene.get("states", {}).get("x", [])
    if not frames:
        raise DeckError("the Brax scene holds no frames under states.x.")
    positions: list[bytes] = []
    rotations: list[bytes] = []
    for frame in frames:
        positions.append(_f32([(0.0, 0.0, 0.0), *frame["pos"]]))
        rotations.append(_f32([_IDENTITY_QUAT, *frame["rot"]]))
    if any(len(chunk) != bodies * 3 * 4 for chunk in positions):
        raise DeckError("the Brax scene's frames do not all hold one pose per link.")
    return b"".join(positions) + b"".join(rotations), len(frames)


def to_rollout(scene: dict[str, Any], *, name: str = "") -> Rollout:
    """Split a decoded Brax scene into shared meshes and per-run poses.

    Args:
        scene: A decoded Brax scene, from :func:`read_brax_scene`.
        name: A name for the model, recorded in the metadata.

    Returns:
        The converted rollout.

    Raises:
        DeckError: If the scene holds a geom the viewer cannot draw, or no
            frames.
    """
    links = list(scene.get("link_names", []))
    bodies = len(links) + 1
    mesh_tail = bytearray()
    geoms: list[dict[str, Any]] = []
    for geom in _geoms(scene):
        kind = _GEOM_TYPES.get(str(geom.get("name", "")).lower())
        if kind is None:
            raise DeckError(f"the Brax scene holds a {geom.get('name')!r} geom, which the viewer cannot draw.")
        entry: dict[str, Any] = {
            "name": str(geom.get("name", kind)),
            "body": int(geom.get("link_idx", -1)) + 1,
            "type": kind,
            "size": list(geom.get("size", (0.0, 0.0, 0.0))),
            "rgba": list(geom.get("rgba", (0.8, 0.8, 0.8, 1.0))),
            "group": 0,
            "is_collision": False,
            "local_pos": list(geom.get("pos", (0.0, 0.0, 0.0))),
            "local_quat": list(geom.get("rot", _IDENTITY_QUAT)),
        }
        if kind == "mesh":
            verts, faces = _f32(geom["vert"]), _u32(geom["face"])
            entry["mesh"] = {
                "verts_off": len(mesh_tail),
                "verts_count": len(verts) // 4,
                "faces_off": len(mesh_tail) + len(verts),
                "faces_count": len(faces) // 4,
            }
            mesh_tail += verts + faces
        geoms.append(entry)

    poses, frames = _pose_tail(scene, bodies)
    # Every offset the viewer reads indexes the combined tail, so the pose
    # buffers start where the shared mesh tail ends.
    base = len(mesh_tail)
    half = frames * bodies * 3 * 4
    timestep = float(scene.get("opt", {}).get("timestep", 0.0)) or 1 / 30
    header = {
        "version": FORMAT_VERSION,
        "meta": {
            "dt": timestep,
            "fps": 1 / timestep,
            "model_name": name or str(scene.get("name", "")),
            "body_names": ["world", *links],
        },
        "meshes": {"bytes": len(mesh_tail)},
        "buffers": {
            "body_pos": {"off": base, "count": frames * bodies * 3, "shape": [frames, bodies, 3], "dtype": "f32"},
            "body_quat": {
                "off": base + half,
                "count": frames * bodies * 4,
                "shape": [frames, bodies, 4],
                "dtype": "f32",
            },
        },
        "geoms": geoms,
        "force_labels": [],
    }
    return Rollout(header=header, meshes=bytes(mesh_tail), poses=poses)


def dump_rollout(rollout: Rollout, *, meshes_name: str) -> bytes:
    """Serialize one rollout to ``.rollout`` bytes.

    Args:
        rollout: The rollout to write.
        meshes_name: The file name of the shared meshes, recorded in the
            header so the reader knows what to fetch.

    Returns:
        The complete file, ready to write.
    """
    header = {**rollout.header, "meshes": {**rollout.header["meshes"], "file": meshes_name}}
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    padding = -(len(encoded) + 12) % 8
    encoded += b" " * padding
    return MAGIC + struct.pack("<Q", len(encoded)) + encoded + gzip.compress(rollout.poses, 6, mtime=0)


def load_rollout(path: Path | str) -> tuple[dict[str, Any], bytes]:
    """Read a ``.rollout`` back, for a check or a test.

    Args:
        path: The file to read.

    Returns:
        The header and the uncompressed pose tail.

    Raises:
        DeckError: If the file is not a rollout.
    """
    raw = Path(path).read_bytes()
    if raw[:4] != MAGIC:
        raise DeckError(f"{path} is not a rollout; it does not start with {MAGIC.decode()}.")
    length = struct.unpack("<Q", raw[4:12])[0]
    header = json.loads(raw[12 : 12 + length])
    return header, gzip.decompress(raw[12 + length :])


def convert_brax_html(src: Path | str, out: Path | str, *, name: str = "") -> Converted:
    """Convert one Brax page into a rollout and its shared meshes.

    The mesh file is named after its own content, so converting a second run of
    the same model writes only the small per-run file and leaves the meshes
    alone.

    Args:
        src: The Brax ``.html`` to read.
        out: The folder to write into; it is created when missing.
        name: A name for the model, recorded in the metadata.

    Returns:
        Where the files went.

    Raises:
        DeckError: If the page holds no usable scene.
    """
    src, out = Path(src), Path(out)
    rollout = to_rollout(read_brax_scene(src), name=name or src.stem)
    out.mkdir(parents=True, exist_ok=True)
    meshes = out / f"{rollout.meshes_hash}{MESHES_SUFFIX}"
    shared = meshes.is_file()
    if not shared:
        meshes.write_bytes(gzip.compress(rollout.meshes, 6, mtime=0))
    target = out / f"{src.stem}{ROLLOUT_SUFFIX}"
    target.write_bytes(dump_rollout(rollout, meshes_name=meshes.name))
    return Converted(rollout=target, meshes=meshes, shared=shared)
