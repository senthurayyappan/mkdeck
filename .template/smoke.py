"""Create a project and test its files, tools, and installed package."""

import argparse
import json
import shutil
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str, cwd: Path) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("library", "app", "bare"))
    parser.add_argument("--python", default="3.12")
    parser.add_argument("--no-ci", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=f"template-{args.kind}-") as scratch:
        project = Path(scratch) / "project"
        manifest = json.loads((ROOT / ".template/manifest.json").read_text())
        for relative in [*manifest, ".template/manifest.json"]:
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        run("git", "init", "-b", "main", cwd=project)
        run("git", "config", "user.name", "Template CI", cwd=project)
        run("git", "config", "user.email", "template@example.invalid", cwd=project)
        run("git", "add", ".", cwd=project)
        run("git", "commit", "-m", "chore: copy template", cwd=project)
        run(sys.executable, "configure.py", "--kind", args.kind,
            "--name", "sample-project", "--python", args.python,
            *(["--no-ci"] if args.no_ci else []), cwd=project)
        if (project / "configure.py").exists() or (project / ".template").exists():
            raise RuntimeError("Setup left template scaffolding behind")
        run("git", "add", "-A", cwd=project)
        run("git", "commit", "-m", "chore: initialize test project", cwd=project)
        run("uv", "sync", "--locked", "--group", "docs", cwd=project)
        run("uv", "run", "pre-commit", "install", "--hook-type", "pre-commit",
            "--hook-type", "commit-msg", cwd=project)
        run("uv", "run", "pre-commit", "run", "--all-files", cwd=project)
        run("git", "diff", "--exit-code", cwd=project)
        message = Path(scratch) / "commit-message"
        message.write_text("feat(cli)!: change behavior\n\nBREAKING CHANGE: new API\n")
        run("uv", "run", "pre-commit", "run", "--hook-stage", "commit-msg",
            "--commit-msg-filename", str(message), cwd=project)
        message.write_text("updated stuff\n")
        result = subprocess.run(["uv", "run", "pre-commit", "run", "--hook-stage",
                                 "commit-msg", "--commit-msg-filename", str(message)], cwd=project)
        if result.returncode == 0:
            raise RuntimeError("Commit hook accepted an invalid message")
        test_args = ["--cov", "--cov-report=term-missing"] if args.kind != "bare" else []
        run("uv", "run", "pytest", *test_args, cwd=project)
        run("uv", "run", "--group", "docs", "mkdocs", "build", "--strict", cwd=project)
        # Test docs publishing with a local Git repository.
        remote = Path(scratch) / "docs-remote.git"
        run("git", "init", "--bare", str(remote), cwd=project)
        run("git", "remote", "add", "origin", str(remote), cwd=project)
        os.environ["GIT_COMMITTER_NAME"] = "github-actions[bot]"
        os.environ["GIT_COMMITTER_EMAIL"] = "41898282+github-actions[bot]@users.noreply.github.com"
        run("uv", "run", "--group", "docs", "mkdocs", "gh-deploy", "--strict", cwd=project)
        run("git", "--git-dir", str(remote), "cat-file", "-e", "gh-pages:index.html", cwd=project)
        if args.kind != "bare":
            run("uv", "build", "--no-sources", cwd=project)
            wheel = next((project / "dist").glob("*.whl"))
            # Test the installed wheel from a separate directory.
            run("uv", "run", "--no-project", "--isolated", "--python", args.python,
                "--with", str(wheel), "--with", "pytest", "python", "-m", "pytest",
                str(project / "tests"), cwd=Path(scratch))
            if args.kind == "app":
                for command in (("sample-project", "hello", "Ada"), ("python", "-m", "sample_project", "hello", "Ada")):
                    run("uv", "run", "--no-project", "--isolated", "--python", args.python,
                        "--with", str(wheel), *command, cwd=Path(scratch))
        run("git", "diff", "--exit-code", cwd=project)
    print(f"PASS: {args.kind}, Python {args.python}")


if __name__ == "__main__":
    os.environ.pop("VIRTUAL_ENV", None)
    main()
