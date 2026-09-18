# mkdeck

[![CI](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-MkDocs-blue)](docs/index.md)
[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)](.python-version)
[![uv](https://img.shields.io/badge/uv-managed-DE5FE9?logo=uv)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/badge/lint-Ruff-D7FF64?logo=ruff)](https://docs.astral.sh/ruff/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Minimal HTML slide decks from Markdown or Python, served like mkdocs.

## Get started

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```bash
make install
uv run mkdeck hello Ada
```

Code lives in `src/mkdeck/`. Add commands in `cli.py` and subpackages as needed.

## Develop

| Command | Purpose |
| --- | --- |
| `make check` | Lint, format, and type checks |
| `make test` | Run tests with coverage |
| `make format` | Format code and apply safe lint fixes |
| `make docs` | Serve documentation locally |
| `make build` | Build a wheel and source distribution |

Add dependencies with `uv add package-name`, or `uv add --dev tool-name`
for development tools. Commit `pyproject.toml` and `uv.lock` together.

CI runs on pushes to main and on pull requests.

Use [Conventional Commits](https://www.conventionalcommits.org/), such as `feat: add export` or `fix: handle empty input`.
[Release Please](https://github.com/googleapis/release-please) uses them to prepare version bumps and changelogs.

See [CONTRIBUTING.md](CONTRIBUTING.md) for release and docs deployment setup.
