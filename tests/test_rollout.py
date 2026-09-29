"""Converting a Brax playback page into a rollout the deck plays offline."""

import base64
import copy
import gzip
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from array import array
from pathlib import Path

import pytest

from mkdeck import DeckError, Embed, load_source
from mkdeck import rollout as rollout_module
from mkdeck.model import resolve_embed_kind
from mkdeck.rollout import (
    NotBraxPage,
    convert_brax_html,
    dump_rollout,
    meshes_of,
    read_brax_scene,
    to_rollout,
)

ASSETS = Path(rollout_module.__file__).parent / "assets"
READER = Path(__file__).with_name("rollout_reader.mjs")

FRAMES = 3
VERTS = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
FACES = [[0, 1, 2], [0, 1, 3]]


def scene(*, frames=FRAMES, geoms=None):
    """A Brax scene of two links, a floor, a crate and one mesh."""
    return {
        "opt": {"timestep": 0.02, "name": "Option"},
        "name": "System",
        "link_names": ["torso", "leg"],
        "geoms": {
            "world": [
                {
                    "name": "Plane",
                    "link_idx": -1,
                    "pos": [0, 0, 0],
                    "rot": [1, 0, 0, 0],
                    "rgba": [0.4, 0.3, 0.2, 1],
                    "size": [0, 0, 0.05],
                },
                {
                    "name": "Box",
                    "link_idx": -1,
                    "pos": [0.7, 0, 0.25],
                    "rot": [1, 0, 0, 0],
                    "rgba": [0.8, 0.7, 0.5, 1],
                    "size": [0.1, 0.45, 0.25],
                },
            ],
            "torso": geoms
            if geoms is not None
            else [
                {
                    "name": "Mesh",
                    "link_idx": 0,
                    "pos": [0.01, 0.02, 0.03],
                    "rot": [1, 0, 0, 0],
                    "rgba": [0.7, 0.7, 0.8, 1],
                    "size": [0.1, 0.1, 0.2],
                    "vert": VERTS,
                    "face": FACES,
                }
            ],
            "leg": [
                {
                    "name": "Capsule",
                    "link_idx": 1,
                    "pos": [0, 0, 0],
                    "rot": [1, 0, 0, 0],
                    "rgba": [0.2, 0.2, 0.2, 1],
                    "size": [0.02, 0.1, 0],
                }
            ],
        },
        "states": {
            "x": [
                {
                    "pos": [[0.1 * t, 0.0, 0.3], [0.1 * t, 0.0, 0.1]],
                    "rot": [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]],
                    "name": "Transform",
                }
                for t in range(frames)
            ]
        },
    }


def page(payload):
    """The Brax playback page that carries a scene."""
    blob = base64.b64encode(zlib.compress(json.dumps(payload).encode())).decode()
    return f'<!DOCTYPE html><html><script>var system = "{blob}";</script></html>'


@pytest.fixture
def deck_folder(tmp_path):
    """A deck whose one figure is an ordinary page, for the negative case."""
    folder = tmp_path / "plain"
    (folder / "assets").mkdir(parents=True)
    (folder / "assets" / "plot.html").write_text("<!doctype html><title>plot</title>")
    (folder / "deck.md").write_text("---\ntitle: Plots\n---\n\nA plot.\n\n![p](assets/plot.html)\n")
    return folder


@pytest.fixture
def brax(tmp_path):
    source = tmp_path / "run.html"
    source.write_text(page(scene()))
    return source


def load_rollout(path):
    """Read a ``.rollout`` back: its header, and its pose tail uncompressed."""
    raw = Path(path).read_bytes()
    assert raw[:4] == b"RSPL", f"{path} is not a rollout"
    length = struct.unpack("<Q", raw[4:12])[0]
    return json.loads(raw[12 : 12 + length]), gzip.decompress(raw[12 + length :])


def f32(blob, off, count):
    values = array("f")
    values.frombytes(blob[off : off + count * 4])
    return list(values)


def test_a_page_becomes_a_rollout_and_a_shared_mesh_file(brax, tmp_path):
    converted = convert_brax_html(brax, tmp_path / "out")
    assert converted.rollout.name == "run.rollout"
    assert converted.meshes.suffix == ".meshes"
    assert not converted.shared


def test_a_second_run_of_the_same_model_reuses_the_meshes(brax, tmp_path):
    first = convert_brax_html(brax, tmp_path / "out")
    other = tmp_path / "other.html"
    other.write_text(page(scene(frames=8)))
    second = convert_brax_html(other, tmp_path / "out")
    assert second.meshes == first.meshes
    assert second.shared
    assert len(list((tmp_path / "out").glob("*.meshes"))) == 1


def test_the_world_body_is_added_in_front_of_the_links(brax, tmp_path):
    header, poses = load_rollout(convert_brax_html(brax, tmp_path / "out").rollout)
    assert header["meta"]["body_names"] == ["world", "torso", "leg"]
    assert header["buffers"]["body_pos"]["shape"] == [FRAMES, 3, 3]
    # The pose tail starts where the shared mesh tail ends, and the world body
    # sits at the origin in front of every frame's links.
    base = header["meshes"]["bytes"]
    assert header["buffers"]["body_pos"]["off"] == base
    assert f32(poses, 0, 9) == pytest.approx([0, 0, 0, 0.0, 0.0, 0.3, 0.0, 0.0, 0.1])


def test_the_offsets_index_the_shared_tail_then_this_run(brax, tmp_path):
    converted = convert_brax_html(brax, tmp_path / "out")
    header, poses = load_rollout(converted.rollout)
    meshes = gzip.decompress(converted.meshes.read_bytes())
    assert len(meshes) == header["meshes"]["bytes"]
    mesh = next(geom for geom in header["geoms"] if geom["type"] == "mesh")
    assert f32(meshes, mesh["mesh"]["verts_off"], 3) == pytest.approx(VERTS[0])
    assert mesh["mesh"]["verts_count"] == 3 * len(VERTS)
    assert mesh["mesh"]["faces_count"] == 3 * len(FACES)
    # body_quat follows body_pos in the same tail, both past the meshes.
    quat = header["buffers"]["body_quat"]
    assert quat["off"] == header["buffers"]["body_pos"]["off"] + FRAMES * 3 * 3 * 4
    assert len(poses) == FRAMES * 3 * (3 + 4) * 4


def test_the_geom_names_become_viewer_types(brax, tmp_path):
    header, _ = load_rollout(convert_brax_html(brax, tmp_path / "out").rollout)
    assert [geom["type"] for geom in header["geoms"]] == ["plane", "box", "mesh", "capsule"]
    assert [geom["body"] for geom in header["geoms"]] == [0, 0, 1, 2]


def test_the_timestep_carries_the_playback_rate(brax, tmp_path):
    header, _ = load_rollout(convert_brax_html(brax, tmp_path / "out").rollout)
    assert header["meta"]["dt"] == pytest.approx(0.02)
    assert header["meta"]["fps"] == pytest.approx(50.0)


def test_a_page_without_a_scene_says_so(tmp_path):
    empty = tmp_path / "empty.html"
    empty.write_text("<!DOCTYPE html><html><body>no scene here</body></html>")
    with pytest.raises(DeckError, match="no 'var system"):
        read_brax_scene(empty)


def test_a_scene_that_will_not_decode_says_so(tmp_path):
    broken = tmp_path / "broken.html"
    broken.write_text('<script>var system = "bm90emxpYg==";</script>')
    with pytest.raises(DeckError, match="will not decode"):
        read_brax_scene(broken)


def test_a_geom_that_leaves_out_its_placement_gets_the_defaults():
    bare = [{"name": "Sphere", "link_idx": 0}]
    header = to_rollout(scene(geoms=bare)).header
    sphere = next(geom for geom in header["geoms"] if geom["type"] == "sphere")
    assert sphere["local_pos"] == [0.0, 0.0, 0.0]
    assert sphere["local_quat"] == [1.0, 0.0, 0.0, 0.0]
    assert sphere["rgba"] == [0.8, 0.8, 0.8, 1.0]
    assert sphere["size"] == [0.0, 0.0, 0.0]


def test_a_geom_the_viewer_cannot_draw_says_so():
    odd = [
        {
            "name": "Heightfield",
            "link_idx": 0,
            "pos": [0, 0, 0],
            "rot": [1, 0, 0, 0],
            "rgba": [1, 1, 1, 1],
            "size": [1, 1, 1],
        }
    ]
    with pytest.raises(DeckError, match="Heightfield"):
        to_rollout(scene(geoms=odd))


def test_a_scene_without_frames_says_so():
    with pytest.raises(DeckError, match="no frames"):
        to_rollout(scene(frames=0))


# --------------------------------------------------------------------------- #
# A rollout on a slide
# --------------------------------------------------------------------------- #


@pytest.fixture
def rollout_deck(tmp_path, brax):
    """A deck folder whose one figure is a converted rollout."""
    folder = tmp_path / "deck"
    (folder / "assets").mkdir(parents=True)
    convert_brax_html(brax, folder / "assets")
    (folder / "deck.md").write_text(
        "---\ntitle: Runs\ndate: 2026-09-18\n---\n\nThe robot crosses.\n\n![stage 0](assets/run.rollout)\n"
    )
    return folder


def test_a_rollout_source_is_drawn_by_the_viewer():
    assert resolve_embed_kind(Embed("assets/run.rollout")) == "rollout"
    assert resolve_embed_kind(Embed("assets/run.rbundle")) == "rollout"
    assert resolve_embed_kind(Embed("assets/plot.html")) == "iframe"


def test_a_deck_with_a_rollout_carries_the_viewer(rollout_deck, tmp_path):
    index = load_source(rollout_deck).build(tmp_path / "site")
    html = index.read_text(encoding="utf-8")
    assert '<deck-rollout src="assets/run.rollout">' in html
    assert "mkdeck-rollout.js" in html
    assert (tmp_path / "site" / "mkdeck-assets" / "three" / "three.module.js").is_file()
    assert (tmp_path / "site" / "mkdeck-assets" / "viewer" / "rollout_viewer.js").is_file()


def test_the_shared_meshes_are_copied_beside_the_rollout(rollout_deck, tmp_path):
    load_source(rollout_deck).build(tmp_path / "site")
    built = sorted(path.name for path in (tmp_path / "site" / "assets").iterdir())
    assert "run.rollout" in built
    assert any(name.endswith(".meshes") for name in built)


def test_a_deck_without_a_rollout_pays_for_no_viewer(deck_folder, tmp_path):
    index = load_source(deck_folder).build(tmp_path / "site")
    assert "mkdeck-rollout.js" not in index.read_text(encoding="utf-8")
    assert not (tmp_path / "site" / "mkdeck-assets" / "three").exists()
    assert not (tmp_path / "site" / "mkdeck-assets" / "viewer").exists()


def test_a_single_file_deck_carries_its_rollouts_inside_it(rollout_deck, tmp_path):
    index = load_source(rollout_deck).build(tmp_path / "one" / "deck.html", single_file=True)
    html = index.read_text(encoding="utf-8")
    for specifier in ("three", "rollout-bundle", "mkdeck-camera", "mkdeck-viewer"):
        assert f'data-mkd-module="{specifier}"' in html
    assert 'data-mkd-rollout="assets/run.rollout"' in html
    assert html.count("data-mkd-rollout=") == 2  # the run and its shared meshes
    # The payloads have to be behind the parser before any script runs.
    assert html.index('data-mkd-module="three"') < html.index("<deck-rollout")
    # and nothing is left beside the document to ship along with it.
    assert not any((tmp_path / "one" / "assets").glob("*.rollout"))
    assert not any((tmp_path / "one" / "assets").glob("*.meshes"))


# --------------------------------------------------------------------------- #
# A page that is not what it looks like
# --------------------------------------------------------------------------- #


def broken(edit):
    """A scene with one thing wrong, made by ``edit`` on a fresh copy."""
    payload = scene()
    edit(payload)
    return payload


def set_frame(**fields):
    def edit(payload):
        payload["states"]["x"][1].update(fields)

    return edit


MALFORMED = {
    "a list for a scene": lambda payload: ["not", "a", "scene"],
    "a missing pos": lambda payload: payload["states"]["x"][0].pop("pos"),
    "a mesh without vert": lambda payload: payload["geoms"]["torso"][0].pop("vert"),
    "a mesh without face": lambda payload: payload["geoms"]["torso"][0].pop("face"),
    "a non-numeric pose": set_frame(pos=[["a", 0, 0], [0, 0, 0]]),
    "a string timestep": lambda payload: payload["opt"].update(timestep="fast"),
    "a negative timestep": lambda payload: payload["opt"].update(timestep=-0.02),
    "a string for the frames": lambda payload: payload["states"].update(x="abcdef"),
    "a short rotation": set_frame(rot=[[1.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]),
    "too few rotations": set_frame(rot=[[1.0, 0.0, 0.0, 0.0]]),
    "too many positions": set_frame(pos=[[0, 0, 0]] * 3),
    "a ragged face list": lambda payload: payload["geoms"]["torso"][0].update(face=[[0, 1, 2], [0, 1]]),
    "a NaN position": set_frame(pos=[[float("nan"), 0, 0], [0, 0, 0]]),
    "an infinite vertex": lambda payload: payload["geoms"]["torso"][0].update(
        vert=[[0.0, 0.0, float("inf")], *VERTS[1:]]
    ),
    "a timestep too small to divide by": lambda payload: payload["opt"].update(timestep=1e-320),
    "a NaN timestep": lambda payload: payload["opt"].update(timestep=float("nan")),
    "a face past the vertices": lambda payload: payload["geoms"]["torso"][0].update(face=[[0, 1, 9]]),
    "a geom on a link that is not there": lambda payload: payload["geoms"]["leg"][0].update(link_idx=7),
    "a size that is a string": lambda payload: payload["geoms"]["leg"][0].update(size="abc"),
    "geoms as a list": lambda payload: payload.update(geoms=[]),
    "link names as a string": lambda payload: payload.update(link_names="torso"),
}


@pytest.mark.parametrize("what", MALFORMED)
def test_a_malformed_page_is_a_deck_error_that_names_the_page(what, tmp_path):
    payload = copy.deepcopy(scene())
    replaced = MALFORMED[what](payload)
    source = tmp_path / "odd.html"
    source.write_text(page(replaced if isinstance(replaced, list) else payload))
    with pytest.raises(DeckError, match=r"odd\.html") as raised:
        convert_brax_html(source, tmp_path / "out")
    assert not isinstance(raised.value, NotBraxPage)
    # Nothing half-made is left behind for the next run to trust.
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


def test_a_short_rotation_is_refused_rather_than_written_truncated():
    payload = broken(set_frame(rot=[[1.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]))
    with pytest.raises(DeckError, match="frame 1 rot"):
        to_rollout(payload)


def test_a_ragged_face_list_is_refused_rather_than_written_as_wrong_triangles():
    with pytest.raises(DeckError, match="triangle"):
        to_rollout(broken(lambda payload: payload["geoms"]["torso"][0].update(face=[[0, 1, 2], [0, 1]])))


def test_a_page_with_no_scene_is_not_a_brax_page(tmp_path):
    plain = tmp_path / "plot.html"
    plain.write_text("<html>plot</html>")
    with pytest.raises(NotBraxPage):
        convert_brax_html(plain, tmp_path / "out")
    assert issubclass(NotBraxPage, DeckError)


def test_a_scene_that_inflates_too_far_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(rollout_module, "_MAX_SCENE_BYTES", 1000)
    bomb = tmp_path / "bomb.html"
    bomb.write_text(page({"padding": "0" * 100_000}))
    with pytest.raises(DeckError, match="inflates past"):
        read_brax_scene(bomb)


def test_a_scene_within_the_limit_still_reads(brax):
    assert read_brax_scene(brax)["link_names"] == ["torso", "leg"]


def test_a_crash_while_writing_leaves_no_partial_file(brax, tmp_path, monkeypatch):
    out = tmp_path / "out"

    def crash(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError, match="disk full"):
        convert_brax_html(brax, out)
    # No mesh file for the next run to take as shared, and no temporary either.
    assert list(out.iterdir()) == []
    monkeypatch.undo()
    assert not convert_brax_html(brax, out).shared


# --------------------------------------------------------------------------- #
# Naming the meshes a rollout needs
# --------------------------------------------------------------------------- #


def rollout_file(tmp_path, header, *, name="x.rollout"):
    """A ``.rollout`` container around a hand-made header."""
    encoded = json.dumps(header).encode()
    path = tmp_path / name
    path.write_bytes(b"RSPL" + struct.pack("<Q", len(encoded)) + encoded + gzip.compress(b""))
    return path


def test_a_file_that_is_not_a_rollout_names_no_meshes(tmp_path):
    stray = tmp_path / "plot.html"
    stray.write_text("<html></html>")
    assert meshes_of(stray) is None
    assert meshes_of(tmp_path / "missing.rollout") is None


def test_a_whole_bundle_names_no_meshes(tmp_path):
    bundle = tmp_path / "run.rbundle"
    bundle.write_bytes(b"RBDL" + struct.pack("<Q", 2) + b"{}")
    assert meshes_of(bundle) is None


def test_a_rollout_names_its_meshes(brax, tmp_path):
    converted = convert_brax_html(brax, tmp_path / "out")
    assert meshes_of(converted.rollout) == converted.meshes.name


@pytest.mark.parametrize(
    "damage",
    [
        b"RSPL",
        b"RSPL" + struct.pack("<Q", 500) + b"{}",
        b"RSPL" + struct.pack("<Q", 3) + b"not",
        b"RSPL" + struct.pack("<Q", 2**63) + b"{}",
        b"RSPL" + struct.pack("<Q", 2**64 - 1) + b"{}",
    ],
    ids=["truncated", "header runs past the end", "header is not JSON", "length past 2**63", "length of 2**64 - 1"],
)
def test_a_damaged_rollout_is_a_deck_error(damage, tmp_path):
    path = tmp_path / "bad.rollout"
    path.write_bytes(damage)
    with pytest.raises(DeckError, match="damaged"):
        meshes_of(path)


def test_a_rollout_with_no_meshes_entry_is_damaged(tmp_path):
    with pytest.raises(DeckError, match="damaged"):
        meshes_of(rollout_file(tmp_path, {"version": 1}))


@pytest.mark.parametrize("name", ["../secret", "/etc/passwd", "a/b.meshes", "..\\up", "C:evil", "..", "", 7])
def test_a_mesh_name_that_leaves_the_folder_is_refused(name, tmp_path):
    with pytest.raises(DeckError, match="plain file name"):
        meshes_of(rollout_file(tmp_path, {"meshes": {"file": name}}))


# --------------------------------------------------------------------------- #
# The wire format, pinned
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("model", ["", "a", "ab", "abc", "abcd", "abcde", "abcdef", "abcdefg", "abcdefgh"])
def test_the_header_is_padded_so_every_offset_lands_aligned(model, brax, tmp_path):
    rollout = to_rollout(read_brax_scene(brax), name=model)
    raw = dump_rollout(rollout, meshes_name="0123456789abcdef.meshes")
    assert raw[:4] == b"RSPL"
    (length,) = struct.unpack("<Q", raw[4:12])
    # The tail starts on an 8-byte boundary, and headerLen counts the padding.
    assert (12 + length) % 8 == 0
    header_bytes = raw[12 : 12 + length]
    header = json.loads(header_bytes)
    assert header["meshes"]["file"] == "0123456789abcdef.meshes"
    poses = gzip.decompress(raw[12 + length :])
    assert poses == rollout.poses
    # Every buffer is 4-byte elements at 4-byte offsets into the combined tail,
    # the poses follow the meshes, and the counts add up to the tail's length.
    pos, quat = header["buffers"]["body_pos"], header["buffers"]["body_quat"]
    assert pos["off"] == quat["off"] - pos["count"] * 4 == header["meshes"]["bytes"]
    assert pos["off"] % 4 == 0 and quat["off"] % 4 == 0
    assert len(poses) == (pos["count"] + quat["count"]) * 4
    for geom in header["geoms"]:
        if geom["type"] == "mesh":
            mesh = geom["mesh"]
            assert mesh["verts_off"] % 4 == 0 and mesh["faces_off"] % 4 == 0
            assert mesh["faces_off"] == mesh["verts_off"] + mesh["verts_count"] * 4
            assert mesh["faces_off"] + mesh["faces_count"] * 4 <= header["meshes"]["bytes"]


def test_the_header_padding_is_spaces_and_the_json_still_parses(brax):
    lengths = set()
    for model in ("", "a", "ab", "abc", "abcd", "abcde", "abcdef", "abcdefg"):
        raw = dump_rollout(to_rollout(read_brax_scene(brax), name=model), meshes_name="m.meshes")
        (length,) = struct.unpack("<Q", raw[4:12])
        text = raw[12 : 12 + length].decode()
        assert json.loads(text) == json.loads(text.rstrip(" "))
        lengths.add(len(text) - len(text.rstrip(" ")))
    assert len(lengths) > 1  # the padding really does vary with the header


# --------------------------------------------------------------------------- #
# The JavaScript reader, against what Python wrote
# --------------------------------------------------------------------------- #

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def read_with_node(path):
    """Read a rollout or bundle through the deck's own JavaScript."""
    done = subprocess.run(["node", str(READER), str(ASSETS), str(path)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def bundle_bytes(rollout, *, compress):
    """The whole-``.rbundle`` form of a rollout, v1 raw or v2 gzip."""
    header = {key: value for key, value in rollout.header.items() if key not in ("meshes", "version")}
    tail = rollout.meshes + rollout.poses
    if compress:
        header["compression"] = "gzip"
        tail = gzip.compress(tail)
    encoded = json.dumps(header).encode()
    encoded += b" " * (-(len(encoded) + 12) % 8)
    return b"RBDL" + struct.pack("<Q", len(encoded)) + encoded + tail


def check_playback(got):
    assert got["posShape"] == [FRAMES, 3, 3]
    assert got["quatShape"] == [FRAMES, 3, 4]
    assert got["pos"][:9] == pytest.approx([0, 0, 0, 0.0, 0.0, 0.3, 0.0, 0.0, 0.1])
    assert got["pos"][9:18] == pytest.approx([0, 0, 0, 0.1, 0.0, 0.3, 0.1, 0.0, 0.1])
    assert got["quat"][:4] == [1, 0, 0, 0]
    assert [geom["type"] for geom in got["geoms"]] == ["plane", "box", "mesh", "capsule"]
    mesh = got["geoms"][2]
    assert mesh["verts"] == [value for vert in VERTS for value in vert]
    assert mesh["faces"] == [index for face in FACES for index in face]
    assert got["meta"]["body_names"] == ["world", "torso", "leg"]


@needs_node
def test_the_reader_parses_a_rollout_python_wrote(brax, tmp_path):
    converted = convert_brax_html(brax, tmp_path / "out")
    check_playback(read_with_node(converted.rollout))


@needs_node
def test_the_reader_plays_a_raw_bundle_untouched(brax, tmp_path):
    made = to_rollout(read_brax_scene(brax), name="run")
    path = tmp_path / "raw.rbundle"
    path.write_bytes(bundle_bytes(made, compress=False))
    check_playback(read_with_node(path))


@needs_node
def test_the_reader_plays_a_gzip_bundle(brax, tmp_path):
    made = to_rollout(read_brax_scene(brax), name="run")
    path = tmp_path / "gz.rbundle"
    path.write_bytes(bundle_bytes(made, compress=True))
    check_playback(read_with_node(path))


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no permission bits to set")
@pytest.mark.parametrize(("umask", "mode"), [(0o022, 0o644), (0o077, 0o600), (0o002, 0o664)])
def test_the_files_written_take_the_umask_like_any_other(umask, mode, brax, tmp_path):
    """mkstemp made them readable by their owner alone, so another user or a container got a 403."""
    before = os.umask(umask)
    try:
        converted = convert_brax_html(brax, tmp_path / "out")
    finally:
        os.umask(before)
    assert converted.rollout.stat().st_mode & 0o777 == mode
    assert converted.meshes.stat().st_mode & 0o777 == mode
