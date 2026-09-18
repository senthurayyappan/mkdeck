# Python template

[![CI](https://github.com/senthurayyappan/python-template/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/senthurayyappan/python-template/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-guide-blue)](#get-started)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](.python-version)
[![uv](https://img.shields.io/badge/uv-managed-DE5FE9?logo=uv)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/badge/lint-Ruff-D7FF64?logo=ruff)](https://docs.astral.sh/ruff/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

A shared starting point for Python libraries, command-line apps, and experiments.
It keeps dependencies, code checks, documentation, and releases consistent across
projects, so you don't have to configure them each time.

The setup uses [uv](https://docs.astral.sh/uv/), [Ruff](https://docs.astral.sh/ruff/),
[ty](https://docs.astral.sh/ty/), [pytest](https://docs.pytest.org/en/stable/),
[pre-commit](https://pre-commit.com/), and [MkDocs](https://www.mkdocs.org/).
[Release Please](https://github.com/googleapis/release-please) turns
[Conventional Commits](https://www.conventionalcommits.org/) into version updates and changelogs.

## Get started

Click **Use this template**, create a repository, and clone it. Choose a preset:

| Preset | For |
| --- | --- |
| `library` | A package you can publish to [PyPI](https://pypi.org/) |
| `app` | An installable [Typer](https://typer.tiangolo.com/) CLI |
| `bare` | Scripts, notebooks, and experiments |

Before editing any files, run this from your new repository:

```bash
uv run --no-project python configure.py --kind library --name my-project
make install
```

Replace `library` and `my-project` with your preset and repository name.
Setup creates your project and lockfile; `make install` installs dependencies
and Git hooks. Commit and push the generated files when ready.

For experiments, add `--no-ci` to the setup command. CI, docs, and release
workflows will run only when you start them from the Actions tab.
Local checks and Git hooks stay available.

Defaults are Python 3.12 and the MIT license. Run
`uv run --no-project python configure.py --help` for other options.

## Everyday commands

```bash
make check    # Lint, format, and type checks
make test     # Unit tests
make docs     # Serve documentation locally
```

[GitHub Actions](https://docs.github.com/en/actions) runs the checks automatically. Use commit messages such as
`feat: add export` or `fix: handle empty input` for automated changelogs.
The generated project's `CONTRIBUTING.md` covers release and deployment setup.

[Maintaining this template](CONTRIBUTING.md)
