"""Converting a Brax playback page into a rollout the deck plays offline."""

import base64
import gzip
import json
import zlib
from array import array

import pytest

from mkdeck import DeckError
from mkdeck.rollout import convert_brax_html, load_rollout, read_brax_scene, to_rollout

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
def brax(tmp_path):
    source = tmp_path / "run.html"
    source.write_text(page(scene()))
    return source


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


def test_a_file_that_is_not_a_rollout_says_so(tmp_path):
    stray = tmp_path / "stray.rollout"
    stray.write_bytes(b"NOPE" + b"\x00" * 16)
    with pytest.raises(DeckError, match="not a rollout"):
        load_rollout(stray)
