# Getting started

```bash
uv sync
uv run mkdeck hello Ada
```

## Development

```bash
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
uv run pre-commit run --all-files
uv run pytest --cov --cov-report=term-missing --cov-report=xml
uv run --group docs mkdocs serve
```

Add runtime dependencies with `uv add package-name`, development tools with
`uv add --dev tool-name`, and documentation tools with `uv add --group docs tool-name`.
Commit both `pyproject.toml` and `uv.lock` after dependency changes.
