# Contributing

1. Create a branch from `main` and run `make install`.
2. Add tests for your changes. Use Google-style docstrings for public APIs.
3. Run `make check`, `make test`, and `make docs-test`. If you touched
   packaging, the vendored assets or `pyproject.toml`, also run `make smoke`.
4. Open a pull request with a title such as `fix: handle empty input`.
5. Squash merge the pull request so Release Please can use its title.

The Makefile contains the uv commands for each task. You can also run those
commands directly on Windows. If a Git hook changes a file, review and stage
the change before you commit again.

Use `uv add` for project dependencies and `uv add --dev` for development tools.
Commit `pyproject.toml` and `uv.lock` together. When you change the supported
Python versions, update `requires-python`, the classifiers, Ruff's
`target-version`, ty's `python-version` and the Python versions in the CI test
matrix. `.python-version` is the version you develop on, and it can be newer
than the oldest version mkdeck supports.

The `check` extra (`pip install "mkdeck[check]"`) installs Playwright, which
both `mkdeck check` and `mkdeck export` need. It keeps its name because the
hint that `mkdeck check` prints refers to it.

## Code layout

Only `mkdeck`, `mkdeck.errors` and `mkdeck.rollout` are public API. Every other
module is an implementation detail; each keeps a correct `__all__`, and a test
checks that a module imports from another only what that one exports. Public
behaviour has one entry point per operation: `Deck.build` and `Deck.serve`, and
the same two methods on the `DeckSource` that `load_source` returns. The CLI,
`check` and `export` call those methods.

| Module | Job |
| --- | --- |
| `model` | The slide model and its validation; plain data |
| `config`, `markdown`, `source` | `deck.yml` and the frontmatter into `Deck` fields, Markdown into slides, and `load_source` |
| `render`, `inline` | A deck into HTML, and that HTML folded into one file |
| `build`, `server` | Writing a build folder, and serving it with live reload |
| `check`, `export`, `probe.js` | Headless Chromium: the slide checker and the PDF printer |
| `rollout` | Brax page into `.rollout` and `.meshes` (public) |

## Workflows

CI runs on pushes to `main` and on pull requests:

- **quality** runs pre-commit (Ruff, ty, deptry), checks the pull request
  title, and builds the docs with `--strict`.
- **package** builds the wheel and the source distribution, runs
  `twine check --strict`, installs the wheel into an empty virtual environment
  outside the checkout, and runs `mkdeck new` and `mkdeck build` from it. The
  tests run against the source tree, and `.gitignore` swallows `dist/`, where
  reveal.js and KaTeX keep their files, so a file missing from the wheel would
  otherwise go unnoticed. `make smoke` runs the same checks locally.
- **tests** runs the test suite on Linux with Python 3.11, 3.12, 3.13 and 3.14.
- **platforms** runs the test suite on Windows and macOS. These jobs are
  informational (`continue-on-error`) until they are green, because the code
  handles Windows paths and the file watcher and dev server behave differently
  per platform. Check them on your pull request, and make them required once
  they pass.

## Vendored libraries

reveal.js, KaTeX, Roboto and three.js are committed under
`src/mkdeck/assets/`, so `mkdeck build` needs no network and no Node. Pre-commit
skips these folders, so nothing rewrites them.

`make vendor` downloads the pinned versions from npm again
(`uv run scripts/vendor_assets.py`; pass a folder name such as `three` to
refresh one library). To bump a library, change its pin in the script, run
`make vendor`, review the diff like any other change, update the version in
`THIRD_PARTY_NOTICES.md`, and run `make smoke`. `.gitignore` re-includes the
`dist/` folders under `assets/`, which its `dist/` rule would otherwise
swallow, and `make smoke` fails if a vendored file is missing from the wheel.
Keep each library's license file next to its code, and list a new library's
license in `THIRD_PARTY_NOTICES.md` and in `license-files` in `pyproject.toml`.

three.js is pinned to r150 on purpose. The rollout viewer works around how that
release's `OrbitControls` reads `camera.up`; read the note in
`scripts/VENDOR_VIEWER.md` before you move it.

## Publish the docs

The docs use the **mkdocs-shadcn** theme and generated API reference. Run `make docs-test` to check them.
To publish them:

1. Set `DEPLOY_DOCS=true` in Settings → Secrets and variables → Actions → Variables.
2. Run the **Docs** workflow once, or push to `main`.
3. In Settings → Pages, select **Deploy from a branch**, `gh-pages`, `/ (root)`.

For a private repository, check that your GitHub plan supports Pages.
A private repository can have a public docs site, so check the Pages visibility
before publishing. You can publish docs without publishing a Python package.

## Releases

Use [Conventional Commits](https://www.conventionalcommits.org/), such as
`feat: add export` or `fix: handle empty input`. Add `!` after the commit type
for a breaking change, as in `feat!: change the API`.
The Git hook checks commit messages. CI checks titles when it runs on pull requests.

Release Please opens a pull request with the new version and changelog.
It updates the version in both `pyproject.toml` and `uv.lock`. After that pull
request is merged, its next run creates the GitHub release and version tag.

In Settings → Actions → General, enable **Allow GitHub Actions to create and approve
pull requests**. With automatic CI enabled, add a
`RELEASE_PLEASE_TOKEN` secret to run checks on release pull requests. Use a
fine-grained personal access token with
read and write access to Contents, Pull requests, and Issues for this repository.

Without that secret, Release Please uses `GITHUB_TOKEN`. GitHub does not start
CI for pull requests created with that token. Run **CI** on the release branch
before merging those pull requests.

Release Please creates the GitHub release and tag. The same workflow
(`.github/workflows/release-please.yml`) then publishes to PyPI: a `build` job
checks out the tag, builds the wheel and the source distribution, runs
`twine check --strict` and the wheel smoke test, and uploads `dist/` as an
artifact. A separate `publish` job, which runs in the `pypi` environment,
downloads it and uploads it with
[trusted publishing](https://docs.pypi.org/trusted-publishers/). There is no
PyPI token to store or rotate. The build job cannot mint the upload credential,
so nothing that runs during the build can publish.

### One-time PyPI setup

A maintainer has to do this once, before the first release:

1. On GitHub, open Settings → Environments and create an environment named
   `pypi`. Adding yourself as a required reviewer makes every release wait for
   your approval before it uploads.
2. On PyPI, open Your account → Publishing and add a **pending publisher**,
   because the project does not exist yet:
   - PyPI project name: `mkdeck`
   - Owner: `senthurayyappan`
   - Repository name: `mkdeck`
   - Workflow name: `release-please.yml`
   - Environment name: `pypi`
3. Merge the first release pull request. The first upload creates the project
   and turns the pending publisher into a regular one.

If you rename the workflow file or the environment, change the publisher on
PyPI to match, or the upload is rejected.
