#!/usr/bin/env python3
"""Set up a new project from a GitHub template copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import keyword
import re
import shutil
import subprocess
import tempfile
from contextlib import suppress
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHONS = ("3.12", "3.13", "3.14")


def render(text: str, context: dict[str, str]) -> str:
    """Fill in template values and keep GitHub Actions expressions unchanged."""
    return re.sub(r"(?<!\$)\{\{([a-z_]+)\}\}", lambda m: context[m[1]], text)


def context_for(args: argparse.Namespace) -> dict[str, str]:
    """Check project options and set the template values."""
    name = re.sub(r"[-_.]+", "-", args.name).lower()
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name):
        raise ValueError(
            "Use a project name starting with a letter, containing letters, digits or hyphens."
        )
    module = name.replace("-", "_")
    if keyword.iskeyword(module):
        raise ValueError("The project name must not be a Python keyword.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", args.owner):
        raise ValueError("Invalid GitHub owner.")
    repo = args.repo or name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise ValueError("Invalid GitHub repository name.")
    if args.python not in PYTHONS:
        raise ValueError(f"Supported Python versions: {', '.join(PYTHONS)}")
    packaged = args.kind != "bare"
    descriptions = {
        "library": (
            "A Python library with a package layout, tests, and documentation. "
            "The project uses the same tools for local development and automated checks."
        ),
        "app": (
            "A Typer command-line app with tests and documentation. "
            "Add commands and Python packages with the same tools for local development and automated checks."
        ),
        "bare": (
            "A project for Python scripts and notebooks. It keeps dependencies, tests, and documentation "
            "in one place as your experiments grow."
        ),
    }
    description = args.description or descriptions[args.kind]
    if any(ord(c) < 32 for c in args.author + description):
        raise ValueError(
            "Author and description must be single-line text without control characters."
        )
    matrix = list(PYTHONS[PYTHONS.index(args.python) :])
    workflow_url = f"https://github.com/{args.owner}/{repo}/actions/workflows/ci.yml"
    result = {
        "push_trigger": "" if args.no_ci else "  push:\n    branches: [main]\n",
        "pull_request_trigger": ""
        if args.no_ci
        else (
            "  pull_request:\n    types: [opened, synchronize, reopened, edited, ready_for_review]\n"
        ),
        "ci_badge": (
            f"[![CI: manual](https://img.shields.io/badge/CI-manual-lightgrey)]({workflow_url})"
            if args.no_ci
            else f"[![CI]({workflow_url}/badge.svg?branch=main)]({workflow_url})"
        ),
        "workflow_note": (
            "Automatic workflows are off. To run CI, Docs, or Release Please, open "
            "the Actions tab, select the workflow, and click **Run workflow**."
            if args.no_ci
            else "CI runs on pushes to main and on pull requests."
        ),
        "docs_start": "Run the **Docs** workflow."
        if args.no_ci
        else ("Run the **Docs** workflow once, or push to `main`."),
        "release_step_note": (
            "Run **Release Please** to open or update a release pull request. "
            "After merging it, run **Release Please** again to create the release and tag.\n"
            if args.no_ci
            else ""
        ),
        "name": name,
        "name_json": json.dumps(name),
        "module": module,
        "repo": repo,
        "owner": args.owner,
        "description": description,
        "readme_description": description.replace(
            "A Typer ", "A [Typer](https://typer.tiangolo.com/) ", 1
        )
        if args.kind == "app" and not args.description
        else description,
        "description_json": json.dumps(description),
        "author_json": json.dumps(args.author),
        "python": args.python,
        "python_digits": args.python.replace(".", ""),
        "python_tuple": args.python.replace(".", ", "),
        "python_matrix": json.dumps(matrix),
        "matrix_description": ", ".join(matrix)
        + ", with macOS and Windows checks on the minimum version",
        "license_badge": "[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)"
        if args.license == "MIT"
        else "",
        "license_metadata": 'license = "MIT"\nlicense-files = ["LICENSE"]'
        if args.license == "MIT"
        else "",
        "dependencies": '["typer>=0.21,<1"]' if args.kind == "app" else "[]",
        "build_system": (
            '[build-system]\nrequires = ["uv_build>=0.12.5,<0.13"]\nbuild-backend = "uv_build"\n'
            if packaged
            else "[tool.uv]\npackage = false\n"
        ),
        "deptry_dependency": '    "deptry>=0.24",\n' if packaged else "",
        "ruff_src": 'src = ["src"]' if packaged else "",
        "docstring_rules": ', "D"' if packaged else "",
        "type_paths": '["src", "tests", ".github/scripts"]'
        if packaged
        else '["experiments", "tests", ".github/scripts"]',
        "pytest_extra": "" if packaged else 'pythonpath = ["."]\n',
        "coverage_source": '["src"]' if packaged else '["experiments"]',
        "deptry_config": '[tool.deptry]\nknown_first_party = ["' + module + '"]\n'
        if packaged
        else "",
        "deptry_hook": (
            "      - id: deptry\n        name: Dependency checks\n"
            "        entry: uv run deptry src\n        language: system\n"
            "        pass_filenames: false\n        always_run: true\n"
            if packaged
            else ""
        ),
        "test_command": "uv run pytest --cov --cov-report=term-missing --cov-report=xml"
        if packaged
        else "uv run pytest",
        "build_target": "build: ## Build a wheel and source distribution\n\tuv build --no-sources\n"
        if packaged
        else "",
        "build_step": "      - run: uv build --no-sources\n" if packaged else "",
        "api_nav": "  - API reference: api.md" if packaged else "",
        "api_plugin": (
            "  - mkdocstrings:\n      handlers:\n        python:\n          paths: [src]\n"
            "          options:\n            docstring_style: google\n"
            "            allow_inspection: false\n            show_root_heading: true\n"
            "            show_signature_annotations: true\n            show_source: true\n"
            if packaged
            else ""
        ),
        "usage": f"uv run {name} hello Ada"
        if args.kind == "app"
        else (
            f"uv run python -c \"from {module} import greet; print(greet('Ada'))\""
            if packaged
            else "uv run python"
        ),
        "layout_description": (
            f"Code lives in `src/{module}/`. Add commands in `cli.py` and subpackages as needed."
            if args.kind == "app"
            else (
                f"Library code lives in `src/{module}/`, with tests in `tests/`."
                if packaged
                else "Put scripts in `experiments/` and notebooks in `notebooks/`."
            )
        ),
        "deptry_label": ", and dependency checks" if packaged else "",
        "coverage_label": " with coverage" if packaged else "",
        "build_table": "| `make build` | Build a wheel and source distribution |"
        if packaged
        else "",
        "api_description": " and generated API reference" if packaged else "",
        "publish_job": "",
        "publishing": "\nThis preset creates GitHub releases only. It does not publish to PyPI.",
    }
    if args.kind == "app":
        result["build_system"] += f'\n[project.scripts]\n{name} = "{module}.cli:app"\n'
    if args.kind == "library":
        result["publish_job"] = (ROOT / ".template/publish-job.txt").read_text()
        result["publishing"] = """
### Publish the library to PyPI

To publish releases to PyPI:

1. Set up a PyPI Trusted Publisher for this repository. Use workflow
   `release-please.yml` and environment `pypi`.
2. Create the `pypi` environment in GitHub.
3. Set the repository variable `PUBLISH_PYPI=true`.

Check that the package name is available on PyPI before the first release.
The workflow builds and tests the release tag, then publishes the package.
It uses GitHub's identity to sign in to PyPI, so you do not need a PyPI API token.

If publishing fails after the GitHub release is created, check out the release tag.
Run `uv build --no-sources`, then `uv publish` with your local PyPI credentials.
Running Release Please again does not publish an existing release.
"""
    return result


def generate(destination: Path, args: argparse.Namespace) -> None:
    """Write the project files to an empty directory and create the lockfile."""
    context = context_for(args)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Output directory must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    for folder in ("common", args.kind):
        base = ROOT / ".template" / folder
        for source in sorted(base.rglob("*.in")):
            relative = render(str(source.relative_to(base))[:-3], context)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                render(source.read_text(), context).rstrip() + "\n" if source.stat().st_size else ""
            )
    for name in (".gitignore", ".editorconfig", ".gitattributes"):
        shutil.copy2(ROOT / name, destination / name)
    if args.license == "MIT":
        license_text = (
            (ROOT / "LICENSE")
            .read_text()
            .replace("2026 Senthur Ayyappan", f"{date.today().year} {args.author}")
        )
        (destination / "LICENSE").write_text(license_text)
    (destination / ".python-version").write_text(args.python + "\n")
    if args.kind != "bare":
        api_module = context["module"] + (".cli" if args.kind == "app" else ".core")
        (destination / "docs/api.md").write_text(f"# API reference\n\n::: {api_module}\n")
    config = {
        "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
        "packages": {
            ".": {
                "release-type": "python",
                "package-name": context["name"],
                "include-component-in-tag": False,
                "extra-files": [
                    {
                        "type": "toml",
                        "path": "uv.lock",
                        "jsonpath": f"$.package[?(@.name.value=='{context['name']}')].version",
                    }
                ],
            }
        },
        "bump-minor-pre-major": True,
        "bump-patch-for-minor-pre-major": True,
    }
    (destination / ".release-please-config.json").write_text(json.dumps(config, indent=2) + "\n")
    (destination / ".release-please-manifest.json").write_text('{".": "0.1.0"}\n')
    (destination / ".template-project.json").write_text(
        json.dumps(
            {
                "kind": args.kind,
                "name": context["name"],
                "python": args.python,
                "ci": not args.no_ci,
            },
            indent=2,
        )
        + "\n"
    )
    subprocess.run(["uv", "lock", "--project", str(destination)], check=True)


def configure_in_place(args: argparse.Namespace) -> None:
    """Create the project first, then replace the unchanged template files."""
    manifest_path = ROOT / ".template/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for relative, expected in manifest.items():
        path = ROOT / relative
        if (
            path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError(
                f"Template file changed: {relative}. Use --output to preserve your edits."
            )
    # Create the project in a temporary directory so setup failures do not change this copy.
    with tempfile.TemporaryDirectory(prefix="python-template-") as scratch:
        staged = Path(scratch) / "project"
        generate(staged, args)
        generated = [p for p in staged.rglob("*") if p.is_file()]
        for source in generated:
            relative = source.relative_to(staged)
            target = ROOT / relative
            if target.is_symlink() or (target.exists() and str(relative) not in manifest):
                raise ValueError(f"Refusing to overwrite existing file: {relative}")
            for parent in target.parents:
                if parent == ROOT:
                    break
                if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                    raise ValueError(f"Invalid destination directory: {parent}")
        for relative in manifest:
            (ROOT / relative).unlink()
        manifest_path.unlink()
        for source in generated:
            target = ROOT / source.relative_to(staged)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        # Remove empty directories left by the template.
        parents = {
            parent
            for relative in manifest
            for parent in (ROOT / relative).parents
            if parent != ROOT and ROOT in parent.parents
        }
        for directory in sorted(parents, key=lambda p: len(p.parts), reverse=True):
            with suppress(OSError):
                directory.rmdir()


def main() -> None:
    """Read the setup options and create the project."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("library", "app", "bare"), required=True)
    parser.add_argument("--name", required=True, help="Distribution name, e.g. robot-tools")
    parser.add_argument("--owner", default="senthurayyappan", help="GitHub owner")
    parser.add_argument("--repo", help="GitHub repository name if different from the distribution")
    parser.add_argument("--description", default="")
    parser.add_argument("--author", default="Senthur Ayyappan")
    parser.add_argument("--python", choices=PYTHONS, default="3.12")
    parser.add_argument("--license", choices=("MIT", "none"), default="MIT")
    parser.add_argument(
        "--no-ci",
        action="store_true",
        help="Run CI, docs, and release workflows manually instead of on pushes and pull requests",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Generate into an empty directory instead of configuring this copy",
    )
    args = parser.parse_args()
    try:
        if args.output:
            destination = args.output.resolve()
            if destination == ROOT:
                raise ValueError("Omit --output to configure the current template copy.")
            generate(destination, args)
        else:
            destination = ROOT
            configure_in_place(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Configuration failed: {exc}\n")
    print(f"Created {args.kind} project in {destination}")
    print(
        "Next: uv sync && uv run pre-commit install --hook-type pre-commit --hook-type commit-msg"
    )
    print(
        "Then review the files and commit: git add -A && git commit -m 'chore: initialize project'"
    )


if __name__ == "__main__":
    main()
