# Contributing

Follow this page to change mkdeck, test the change, and get it merged.

The short path has five steps:

1. Create a branch from `main` and run `make install`.
2. Change the code, and add tests for the change.
3. Run `make check`, `make test`, and `make docs-test`.
4. Run `make smoke` too if you touched packaging, the vendored assets, or `pyproject.toml`.
5. Open a pull request with a title such as `fix: handle empty input`.

The Makefile holds the `uv` command behind each target. On Windows, run those `uv` commands directly.

## Set up

Install [uv](https://docs.astral.sh/uv/), and then run:

```bash
make install
```

The target installs the development tools and every extra with `uv sync --all-extras`. It also installs the Git hooks for pre-commit and for commit messages. If a hook changes a file, review the change and stage it before you commit again.

`.python-version` is the Python version you develop on, and it can be newer than the oldest version that mkdeck supports.

## Change dependencies

Use `uv add` for a project dependency and `uv add --dev` for a development tool, and commit `pyproject.toml` and `uv.lock` together.

To change the supported Python versions, update all of these:

- `requires-python` and the classifiers in `pyproject.toml`
- Ruff's `target-version`
- ty's `python-version`
- the Python versions in the CI test matrix

## Run tests

Run the whole suite with coverage:

```bash
make test
```

To run one file, use `uv run pytest tests/test_docs.py`. The browser tests skip themselves when Playwright or Chromium is missing, so `make test` works on a bare checkout.

## Run browser tests

The browser tests drive headless Chromium. They cover `mkdeck.js`, the rollout viewer, `probe.js`, KaTeX, Mermaid, and the PDF export. Install the `check` extra and Chromium, and then run the suite:

```bash
uv sync --extra check
uv run playwright install chromium
uv run pytest
```

Set `MKDECK_REQUIRE_BROWSER=1` to fail instead of skip when the browser is missing. CI sets it on the Python 3.13 leg. The tests need no network, because the Mermaid test uses a stub.

## Lint and check types

Run these targets:

| Command | What it does |
| --- | --- |
| `make lint` | Checks lint and formatting with Ruff, and changes nothing |
| `make format` | Applies safe Ruff fixes and formats the code |
| `make typecheck` | Checks types with ty |
| `make check` | Runs every pre-commit hook: Ruff, ty, deptry, and file checks |

Write Google-style docstrings for public APIs.

## Write a commit message

Use [Conventional Commits](https://www.conventionalcommits.org/), such as `feat: add export` or `fix: handle empty input`. Add `!` after the type for a breaking change, as in `feat!: change the API`.

A Git hook checks each commit message, and CI checks the pull request title. Squash merge the pull request so that Release Please reads the title.

## Write documentation

The docs live in `docs/`, and `mkdocs.yml` lists every page in its `nav`. Follow these rules:

- Write short sentences in the active voice.
- Give each page one purpose, and keep it under 500 words.
- Start each page with what the reader can do, and end it with a `Next:` link.
- Keep code examples small and runnable. `tests/test_docs.py` parses every `markdown` example and checks every link.

## Build the docs

Serve the docs while you write, and then build them with warnings as errors:

```bash
make docs
make docs-test
```

The **Docs** workflow deploys the site on each push to `main`, but only when the repository variable `DEPLOY_DOCS` is `true`. It pushes to the `gh-pages` branch, so Settings → Pages must serve that branch from `/ (root)`.

## Know the CI jobs

CI runs on pushes to `main` and on pull requests:

- **quality** runs pre-commit, checks the pull request title, and builds the docs with `--strict`.
- **package** builds the wheel and the source distribution and runs `twine check --strict`. It then installs the wheel into an empty virtual environment and runs `mkdeck new` and `mkdeck build` from it. `make smoke` runs the same checks locally.
- **tests** runs the suite on Linux with Python 3.11, 3.12, 3.13, and 3.14. The 3.13 leg also installs the `check` extra and Chromium, so it runs the browser tests. It fails if coverage drops below 90%.

The workflows install the `uv` version in `UV_VERSION`, and `twine` at the version that `Makefile` and the workflows pin. Dependabot does not bump either one, so raise them by hand now and then.

## Find your way in the code

Only `mkdeck`, `mkdeck.errors`, and `mkdeck.rollout` are public API. Every other module keeps a correct `__all__`, and a test checks that a module imports from another only what that one exports.

Each operation has one entry point: `Deck.build` and `Deck.serve`, and the same two methods on the `DeckSource` that `load_source` returns. The CLI, `check`, and `export` call those methods.

| Module | Job |
| --- | --- |
| `model` | The slide model and its validation |
| `config`, `markdown`, `source` | Settings, Markdown into slides, and `load_source` |
| `render`, `inline` | A deck into HTML, and that HTML into one file |
| `build`, `server` | Writing a build folder, and serving it with live reload |
| `check`, `export`, `probe.js` | Headless Chromium: the slide checker and the PDF printer |
| `rollout` | Brax page into `.rollout` and `.meshes` |

## Package a change

The source distribution carries `tests/`, `scripts/`, and `docs/`, so that its tests can run. If a test starts to read another file outside `tests/` and `src/`, add that file to `source-include` in `pyproject.toml` and to `SDIST_FILES` in `scripts/smoke_wheel.py`.

## Vendor a library

reveal.js, KaTeX, Roboto, and three.js live under `src/mkdeck/assets/`, and pre-commit skips these folders. To bump a library:

1. Change its pin in `scripts/vendor_assets.py`.
2. Run `make vendor`. To refresh one library, pass its folder name, as in `uv run scripts/vendor_assets.py three`.
3. Review the diff like any other change.
4. Update the version in `THIRD_PARTY_NOTICES.md`.
5. Run `make smoke`, which fails if a vendored file is missing from the wheel.

Keep each license file next to its library. For a new library, also list its license in `THIRD_PARTY_NOTICES.md` and in `license-files` in `pyproject.toml`.

!!! warning
    three.js stays on r150 on purpose. Read `scripts/VENDOR_VIEWER.md` before you move it.

## Release

Release Please turns Conventional Commits into releases, so you never edit the version by hand.

1. Merge pull requests into `main` with a Conventional Commit title.
2. Release Please opens a pull request with the new version and the changelog. It updates the version in `pyproject.toml` and `uv.lock`.
3. Merge that pull request. The next run of `.github/workflows/release-please.yml` creates the GitHub release and the version tag.
4. The `build` job checks out the tag, builds the wheel and the source distribution, and runs `twine check --strict` and the wheel smoke test. It then uploads `dist/` as an artifact.
5. The `publish` job runs in the `pypi` environment. It downloads `dist/` and uploads it with [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no PyPI token exists.
6. If the `pypi` environment requires a reviewer, approve the run. Then check https://pypi.org/project/mkdeck/.

The two jobs are separate so that the build never holds the upload credential.

### Set up the repository

Enable **Allow GitHub Actions to create and approve pull requests** in Settings → Actions → General. Optionally, add a `RELEASE_PLEASE_TOKEN` secret so that CI runs on release pull requests. Use a fine-grained token with read and write access to Contents, Pull requests, and Issues.

Without that secret, GitHub does not start CI on release pull requests. Run **CI** on the release branch before you merge.

### Match the PyPI publisher

PyPI accepts an upload only from the trusted publisher that you registered:

| Field | Value |
| --- | --- |
| PyPI project name | `mkdeck` |
| Owner | `senthurayyappan` |
| Repository name | `mkdeck` |
| Workflow name | `release-please.yml` |
| Environment name | `pypi` |

If you rename the workflow file or the environment, change the publisher on PyPI to match. Otherwise, PyPI rejects the upload.
