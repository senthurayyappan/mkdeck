"""Turn a Brax playback page into a rollout the deck can show offline.

A Brax ``html.render`` page carries its whole world inline: six CDN modules and
one base64 zlib blob holding every mesh alongside the trajectory. The meshes are
~99% of it, and a deck that shows one robot over thirty slides ships thirty
copies of that robot.

This module splits the two apart. The meshes of one model go into a shared
``.meshes`` file named after their content hash, so every run of that model
points at the same bytes; each run keeps only its per-frame poses, in a
``.rollout`` file. The pair is a ``.rbundle`` cut in half: the reader
(``assets/mkdeck-rollout.js``) glues the two tails back together and hands the
viewer the exact wire form it already reads, which is why a whole ``.rbundle``,
the same format uncut, also plays in a deck without conversion.

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
import math
import os
import re
import struct
import sys
import tempfile
import zlib
from array import array
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import chain
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from mkdeck.errors import DeckError

__all__ = [
    "MESHES_SUFFIX",
    "ROLLOUT_SUFFIX",
    "Converted",
    "NotBraxPage",
    "convert_brax_html",
    "meshes_of",
]

_MAGIC = b"RSPL"
"""The four bytes a ``.rollout`` starts with."""

_FORMAT_VERSION = 1
"""The version of the container written here."""

MESHES_SUFFIX = ".meshes"
"""The suffix of the shared geometry file a rollout points at."""

ROLLOUT_SUFFIX = ".rollout"
"""The suffix of the per-run file."""

_MAX_SCENE_BYTES = 512 * 1024 * 1024
"""The most a page's scene may inflate to.

A real 100k-triangle model is a tenth of it.
"""

_SCENE = re.compile(r'var system = "([A-Za-z0-9+/=]+)"')
"""The assignment a Brax page holds its zlib-compressed scene in."""

_GEOM_TYPES = frozenset(
    {"plane", "box", "sphere", "capsule", "cylinder", "ellipsoid", "mesh"}
)
"""Brax names its geoms after their class.

The viewer wants the lowercase form.
"""

_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)
"""The world body never moves, so every frame repeats this rotation."""


class NotBraxPage(DeckError):  # noqa: N818 - a case for the caller to choose on, not a failure name
    """The page is not a Brax playback page, which is not always a mistake.

    An assets folder normally mixes playback pages with plots, so a caller
    converting a batch may want to skip these and still fail on the rest.
    """


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
        shared: True when the mesh file was already there, written by an earlier
            run of the same model.
    """

    rollout: Path
    meshes: Path
    shared: bool


def _pack(typecode: str, rows: Iterable[Iterable[Any]]) -> bytes:
    """Pack rows of numbers as little-endian 32-bit values.

    Args:
        typecode: ``"f"`` for float32 or ``"I"`` for uint32.
        rows: Rows of numbers, such as a list of ``[x, y, z]``.

    Returns:
        The packed bytes.
    """
    packed = array(typecode, chain.from_iterable(rows))
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def _is_number(value: Any) -> bool:
    """Say whether a JSON value is a finite number.

    A bool is not one, and neither is NaN.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return isinstance(value, int) or math.isfinite(value)


def _vector(value: Any, length: int, what: str) -> list[float]:
    """Check that a JSON value is ``length`` numbers.

    Args:
        value: The value the scene holds.
        length: How many numbers it must have.
        what: What it is, for the message.

    Returns:
        The numbers.

    Raises:
        DeckError: If it is not exactly ``length`` numbers.
    """
    if (
        not isinstance(value, list | tuple)
        or len(value) != length
        or not all(_is_number(item) for item in value)
    ):
        raise DeckError(
            f"the Brax scene's {what} is not a list of {length} finite numbers."
        )
    return list(value)


def _rows(
    value: Any, width: int, what: str, *, count: int | None = None
) -> list[list[float]]:
    """Check that a JSON value is a list of ``width``-number rows.

    Args:
        value: The value the scene holds.
        width: How many numbers each row must have.
        what: What it is, for the message.
        count: How many rows it must have, or ``None`` for any number.

    Returns:
        The rows.

    Raises:
        DeckError: If the shape is wrong.
    """
    if not isinstance(value, list) or (
        count is not None and len(value) != count
    ):
        raise DeckError(
            f"the Brax scene's {what} is not a list of "
            f"{count if count is not None else 'some'} rows."
        )
    return [_vector(row, width, what) for row in value]


def _faces(value: Any, vertex_count: int, what: str) -> list[list[int]]:
    """Check that a JSON value is a list of triangles.

    The triangles refer to ``vertex_count`` vertices.

    Args:
        value: The value the scene holds.
        vertex_count: How many vertices the triangles index.
        what: What it is, for the message.

    Returns:
        The triangles.

    Raises:
        DeckError: If a face is not three indices that name a vertex.
    """
    if not isinstance(value, list) or not value:
        raise DeckError(f"the Brax scene's {what} holds no triangles.")
    for face in value:
        if (
            not isinstance(face, list)
            or len(face) != 3
            or not all(
                isinstance(i, int)
                and not isinstance(i, bool)
                and 0 <= i < vertex_count
                for i in face
            )
        ):
            raise DeckError(
                f"the Brax scene's {what} holds {face!r}, which is not a "
                f"triangle over its vertices."
            )
    return value


def _write_atomic(path: Path, data: bytes) -> None:
    """Write a file so a crash never leaves half of it behind.

    Args:
        path: The file to write.
        data: Its bytes.
    """
    handle, name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        # mkstemp makes a file only its owner can read, which a web server,
        # another user or a
        # container would then refuse to serve; a new file takes the umask like
        # any other.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(name, 0o666 & ~umask)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def read_brax_scene(path: Path | str) -> dict[str, Any]:
    """Read the scene a Brax playback page holds inline.

    Args:
        path: The ``.html`` Brax wrote.

    Returns:
        The decoded scene, as ``brax.io.json`` wrote it.

    Raises:
        NotBraxPage: If the page holds no scene.
        DeckError: If the page holds a scene that will not decode.
    """
    path = Path(path)
    try:
        page = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise DeckError(f"Cannot read {path}: {exc}") from exc
    found = _SCENE.search(page)
    if found is None:
        raise NotBraxPage(
            f"{path} holds no Brax scene; it has no 'var system = \"...\"' "
            f"line."
        )
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(
            base64.b64decode(found.group(1)), _MAX_SCENE_BYTES + 1
        )
        if len(raw) > _MAX_SCENE_BYTES:
            raise DeckError(
                f"{path} holds a Brax scene that inflates past "
                f"{_MAX_SCENE_BYTES:,} bytes."
            )
        scene = json.loads(raw)
    except (ValueError, zlib.error, RecursionError) as exc:
        raise DeckError(
            f"{path} holds a Brax scene that will not decode: {exc}"
        ) from exc
    if not isinstance(scene, dict):
        raise DeckError(
            f"{path} holds a Brax scene that will not decode: it is not a JSON "
            f"object."
        )
    return scene


def _geoms(scene: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Walk every geom in the scene, in the order the groups hold them.

    Args:
        scene: A decoded Brax scene.

    Yields:
        One geom at a time.
    """
    for group in scene.get("geoms", {}).values():
        yield from group


def _pose_tail(scene: dict[str, Any], links: int) -> tuple[bytes, int]:
    """Pack every frame's body positions and rotations.

    Body 0 is the world, which Brax leaves out of its state because it never
    moves; it is written as the identity so a geom fixed to the world needs no
    special case in the viewer.

    Args:
        scene: A decoded Brax scene.
        links: The link count, the world not included.

    Returns:
        The positions, the rotations, and the frame count.

    Raises:
        DeckError: If the scene holds no frames, or a frame that does not hold
            one pose per link.
    """
    frames = scene.get("states", {}).get("x", [])
    if not isinstance(frames, list):
        raise DeckError("the Brax scene's states.x is not a list of frames.")
    if not frames:
        raise DeckError("the Brax scene holds no frames under states.x.")
    positions: list[bytes] = []
    rotations: list[bytes] = []
    for number, frame in enumerate(frames):
        pos = _rows(frame["pos"], 3, f"frame {number} pos", count=links)
        rot = _rows(frame["rot"], 4, f"frame {number} rot", count=links)
        positions.append(_pack("f", [(0.0, 0.0, 0.0), *pos]))
        rotations.append(_pack("f", [_IDENTITY_QUAT, *rot]))
    return b"".join(positions) + b"".join(rotations), len(frames)


def to_rollout(scene: dict[str, Any], *, name: str = "") -> Rollout:
    """Split a decoded Brax scene into shared meshes and per-run poses.

    Args:
        scene: A decoded Brax scene, from :func:`read_brax_scene`.
        name: A name for the model, recorded in the metadata.

    Returns:
        The converted rollout.

    Raises:
        DeckError: If the scene holds a geom the viewer cannot draw, a shape
            that does not add up, or no frames.
        KeyError: If a required field is missing.
        TypeError: If a field has the wrong type.
    """
    link_names = scene.get("link_names", [])
    if not isinstance(link_names, list):
        raise DeckError("the Brax scene's link_names is not a list.")
    links = [str(link) for link in link_names]
    bodies = len(links) + 1
    mesh_tail = bytearray()
    geoms: list[dict[str, Any]] = []
    for geom in _geoms(scene):
        kind = str(geom.get("name", "")).lower()
        if kind not in _GEOM_TYPES:
            raise DeckError(
                f"the Brax scene holds a {geom.get('name')!r} geom, which the "
                f"viewer cannot draw."
            )
        body = int(geom.get("link_idx", -1)) + 1
        if not 0 <= body < bodies:
            raise DeckError(
                f"a {geom['name']!r} geom sits on link {body - 1}, but the "
                f"scene has {len(links)} links."
            )
        entry: dict[str, Any] = {
            "name": str(geom["name"]),
            "body": body,
            "type": kind,
            "size": _vector(
                geom.get("size", [0.0, 0.0, 0.0]), 3, f"{kind} size"
            ),
            "rgba": _vector(
                geom.get("rgba", [0.8, 0.8, 0.8, 1.0]), 4, f"{kind} rgba"
            ),
            "group": 0,
            "is_collision": False,
            "local_pos": _vector(
                geom.get("pos", [0.0, 0.0, 0.0]), 3, f"{kind} pos"
            ),
            "local_quat": _vector(
                geom.get("rot", _IDENTITY_QUAT), 4, f"{kind} rot"
            ),
        }
        if kind == "mesh":
            vertices = _rows(geom["vert"], 3, "mesh vert")
            faces = _faces(geom["face"], len(vertices), "mesh face")
            verts, indices = _pack("f", vertices), _pack("I", faces)
            entry["mesh"] = {
                "verts_off": len(mesh_tail),
                "verts_count": len(verts) // 4,
                "faces_off": len(mesh_tail) + len(verts),
                "faces_count": len(indices) // 4,
            }
            mesh_tail += verts + indices
        geoms.append(entry)

    poses, frames = _pose_tail(scene, len(links))
    # Every offset the viewer reads indexes the combined tail, so the pose
    # buffers start where the shared mesh tail ends.
    base = len(mesh_tail)
    half = frames * bodies * 3 * 4
    timestep = float(scene.get("opt", {}).get("timestep", 0.0)) or 1 / 30
    if (
        not math.isfinite(timestep)
        or timestep < 0
        or not math.isfinite(1 / timestep)
    ):
        raise DeckError(
            f"the Brax scene's timestep {timestep} is not a usable number of "
            f"seconds."
        )
    header = {
        "version": _FORMAT_VERSION,
        "meta": {
            "dt": timestep,
            "fps": 1 / timestep,
            "model_name": name or str(scene.get("name", "")),
            "body_names": ["world", *links],
        },
        "meshes": {"bytes": len(mesh_tail)},
        "buffers": {
            "body_pos": {
                "off": base,
                "count": frames * bodies * 3,
                "shape": [frames, bodies, 3],
                "dtype": "f32",
            },
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
        meshes_name: The file name of the shared meshes, recorded in the header
            so the reader knows what to fetch.

    Returns:
        The complete file, ready to write.
    """
    header = {
        **rollout.header,
        "meshes": {**rollout.header["meshes"], "file": meshes_name},
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    padding = -(len(encoded) + 12) % 8
    encoded += b" " * padding
    return (
        _MAGIC
        + struct.pack("<Q", len(encoded))
        + encoded
        + gzip.compress(rollout.poses, 6, mtime=0)
    )


def meshes_of(path: Path | str) -> str | None:
    """Name the shared mesh file a rollout points at.

    Args:
        path: A ``.rollout``, or any other file.

    Returns:
        The file name, or ``None`` when the file is missing or is not a split
        rollout — a whole ``.rbundle`` carries its meshes itself.

    Raises:
        DeckError: If the file is a rollout that is damaged, or names a mesh
            file that is not a plain file name beside it.
    """
    path = Path(path)
    try:
        with path.open("rb") as handle:
            head = handle.read(12)
            if head[:4] != _MAGIC:
                return None
            length = (
                struct.unpack("<Q", head[4:12])[0] if len(head) == 12 else 0
            )
            raw = handle.read(
                min(length, os.fstat(handle.fileno()).st_size)
            )  # a length past the file is damage, not a size to allocate
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DeckError(f"Cannot read {path}: {exc}") from exc
    try:
        name = json.loads(raw)["meshes"]["file"]
    except (ValueError, KeyError, TypeError) as exc:
        raise DeckError(
            f"{path} is a damaged rollout; its header does not name a meshes "
            f"file."
        ) from exc
    if (
        not isinstance(name, str)
        or name in {"", ".", ".."}
        or "\0" in name
        or not (PurePosixPath(name).name == PureWindowsPath(name).name == name)
    ):
        raise DeckError(
            f"{path} names {name!r} as its meshes, which is not a plain file "
            f"name beside it."
        )
    return name


def convert_brax_html(src: Path | str, out: Path | str) -> Converted:
    """Convert one Brax page into a rollout and its shared meshes.

    The mesh file is named after its own content, so converting a second run of
    the same model writes only the small per-run file and leaves the meshes
    alone. Both files are written whole or not at all.

    Args:
        src: The Brax ``.html`` to read.
        out: The folder to write into; it is created when missing.

    Returns:
        Where the files went.

    Raises:
        NotBraxPage: If the page holds no scene at all.
        DeckError: If the page holds a scene that cannot be converted.
    """
    src, out = Path(src), Path(out)
    scene = read_brax_scene(src)
    try:
        rollout = to_rollout(scene, name=src.stem)
    except DeckError as exc:
        raise DeckError(exc.message, source=src) from exc
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        OverflowError,
    ) as exc:
        raise DeckError(
            f"holds a Brax scene this version cannot read "
            f"({type(exc).__name__}: {exc}).",
            source=src,
        ) from exc
    out.mkdir(parents=True, exist_ok=True)
    meshes = out / f"{rollout.meshes_hash}{MESHES_SUFFIX}"
    shared = meshes.is_file()
    if not shared:
        _write_atomic(meshes, gzip.compress(rollout.meshes, 6, mtime=0))
    target = out / f"{src.stem}{ROLLOUT_SUFFIX}"
    _write_atomic(target, dump_rollout(rollout, meshes_name=meshes.name))
    return Converted(rollout=target, meshes=meshes, shared=shared)
