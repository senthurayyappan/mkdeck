"""Check each project type and protect existing files during setup."""

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import configure  # noqa: E402


def options(kind="library", **overrides):
    values = dict(
        kind=kind,
        name="sample-project",
        owner="someone",
        repo=None,
        description='A "quoted" description: with YAML punctuation.',
        author='A "Quoted" Author',
        python="3.12",
        license="MIT",
        output=None,
        no_ci=False,
    )
    return argparse.Namespace(**(values | overrides))


@pytest.mark.parametrize("kind", ["library", "app", "bare"])
@pytest.mark.parametrize("python", configure.PYTHONS)
def test_rendered_configuration(tmp_path, kind, python):
    args = options(kind, python=python)
    with patch.object(configure.subprocess, "run"):
        configure.generate(tmp_path, args)
    project = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert project["project"]["name"] == "sample-project"
    assert project["project"]["description"] == args.description
    assert project["project"]["requires-python"] == f">={python}"
    assert project["project"]["authors"][0]["name"] == args.author
    assert ("build-system" in project) == (kind != "bare")
    assert ("scripts" in project["project"]) == (kind == "app")
    assert (tmp_path / "src").exists() == (kind != "bare")
    assert (tmp_path / "LICENSE").exists()
    for path in tmp_path.rglob("*.py"):
        compile(path.read_text(), str(path), "exec")
    for path in tmp_path.rglob("*.yml"):
        yaml.safe_load(path.read_text())
    docs = yaml.safe_load((tmp_path / "mkdocs.yml").read_text())
    assert docs["theme"]["name"] == "shadcn"
    assert docs["site_description"] == args.description
    workflow = yaml.safe_load((tmp_path / ".github/workflows/release-please.yml").read_text())
    assert ("publish" in workflow["jobs"]) == (kind == "library")
    assert "${{" in (tmp_path / ".github/workflows/ci.yml").read_text()
    hooks = yaml.safe_load((tmp_path / ".pre-commit-config.yaml").read_text())
    assert hooks["repos"][-1]["hooks"][-1]["stages"] == ["commit-msg"]


@pytest.mark.parametrize("name", ["../oops", "class", "123name", "a;echo bad", "a\nname"])
def test_invalid_name(name):
    with pytest.raises(ValueError):
        configure.context_for(options(name=name))


def test_normalizes_distribution_name():
    result = configure.context_for(options(name="My_Project.Tools"))
    assert result["name"] == "my-project-tools"
    assert result["module"] == "my_project_tools"


def test_existing_output_is_preserved(tmp_path):
    target = tmp_path / "keep.txt"
    target.write_text("keep me")
    with pytest.raises(ValueError, match="empty"):
        configure.generate(tmp_path, options())
    assert target.read_text() == "keep me"


def test_no_license(tmp_path):
    with patch.object(configure.subprocess, "run"):
        configure.generate(tmp_path, options(license="none"))
    assert not (tmp_path / "LICENSE").exists()
    assert "license" not in tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]


def pristine_copy(tmp_path):
    destination = tmp_path / "copy"
    manifest = json.loads((ROOT / ".template/manifest.json").read_text())
    for relative in [*manifest, ".template/manifest.json"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return destination


def snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_failed_lock_leaves_template_untouched(tmp_path):
    destination = pristine_copy(tmp_path)
    before = snapshot(destination)
    with (
        patch.object(configure, "ROOT", destination),
        patch.object(
            configure.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["uv", "lock"]),
        ),
        pytest.raises(subprocess.CalledProcessError),
    ):
        configure.configure_in_place(options())
    assert snapshot(destination) == before


def test_modified_template_is_preserved(tmp_path):
    destination = pristine_copy(tmp_path)
    (destination / "README.md").write_text("my changes")
    before = snapshot(destination)
    with patch.object(configure, "ROOT", destination), pytest.raises(ValueError, match="changed"):
        configure.configure_in_place(options())
    assert snapshot(destination) == before


def test_in_place_preserves_git_and_unrelated_files(tmp_path):
    destination = pristine_copy(tmp_path)
    (destination / ".git").mkdir()
    (destination / ".git/config").write_text("keep git history")
    (destination / "notes.txt").write_text("my notes")
    with patch.object(configure, "ROOT", destination), patch.object(configure.subprocess, "run"):
        configure.configure_in_place(options("app"))
    assert (destination / ".git/config").read_text() == "keep git history"
    assert (destination / "notes.txt").read_text() == "my notes"
    assert not (destination / "configure.py").exists()
    assert not (destination / ".template").exists()
    assert not (destination / "tests/test_template.py").exists()
    assert (destination / "src/sample_project/cli.py").exists()


def test_colliding_user_file_is_preserved(tmp_path):
    destination = pristine_copy(tmp_path)
    target = destination / "src/sample_project/core.py"
    target.parent.mkdir(parents=True)
    target.write_text("my code")
    before = snapshot(destination)
    with (
        patch.object(configure, "ROOT", destination),
        patch.object(configure.subprocess, "run"),
        pytest.raises(ValueError, match="overwrite"),
    ):
        configure.configure_in_place(options())
    assert snapshot(destination) == before


@pytest.mark.parametrize(
    "message, expected",
    [
        ("feat: add CLI", True),
        ("fix(core)!: change API\n\nBREAKING CHANGE: changed", True),
        ("chore(deps): update dependencies", True),
        ("docs: explain usage", True),
        ("updated stuff", False),
        ("feat: ", False),
        ("", False),
    ],
)
def test_conventional_commit_checker(tmp_path, message, expected):
    source = ROOT / ".template/common/.github/scripts/check_commit_message.py.in"
    target = tmp_path / "checker.py"
    target.write_text(source.read_text())
    spec = importlib.util.spec_from_file_location("checker", target)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.valid_header(message) == expected


@pytest.mark.parametrize("kind", ["library", "app", "bare"])
@pytest.mark.parametrize("no_ci", [False, True])
def test_workflow_triggers(tmp_path, kind, no_ci):
    with patch.object(configure.subprocess, "run"):
        configure.generate(tmp_path, options(kind, no_ci=no_ci))
    for filename in ("ci.yml", "docs.yml", "release-please.yml"):
        # BaseLoader keeps the YAML key "on" as text.
        workflow = yaml.load(
            (tmp_path / ".github/workflows" / filename).read_text(), Loader=yaml.BaseLoader
        )
        events = workflow["on"]
        if no_ci:
            assert set(events) == {"workflow_dispatch"}
        else:
            expected = {"push", "workflow_dispatch"}
            if filename == "ci.yml":
                expected.add("pull_request")
            assert set(events) == expected
            assert events["push"]["branches"] == ["main"]
        assert workflow["jobs"]
    assert (tmp_path / "tests").is_dir()
    assert (tmp_path / ".pre-commit-config.yaml").is_file()
    assert "make check" in (tmp_path / "README.md").read_text()
    assert ("CI-manual" in (tmp_path / "README.md").read_text()) == no_ci
    assert json.loads((tmp_path / ".template-project.json").read_text())["ci"] is not no_ci
