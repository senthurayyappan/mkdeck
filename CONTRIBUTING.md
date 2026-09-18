# Maintaining the template

Shared files live in `.template/common/`; each preset adds files from
`.template/library/`, `.template/app/`, or `.template/bare/`.
`configure.py` fills in project names and settings.

After editing the template, update its file hashes and run the checks:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run --no-project python .template/update_manifest.py
uv run pytest
```

To create a test project in a separate directory:

```bash
uv run --no-project python configure.py --kind app --name my-cli --output ../my-cli
```

The output directory must be empty. GitHub Actions tests all three presets,
including installation, Git hooks, docs, package builds, and release updates.

Use Conventional Commits for changes to this template. CI uses `uv sync --locked`
to check that the lockfile is up to date. Local commands use uv's defaults.
