# Contributing

1. Create a branch from `main` and run `make install`.
2. Add tests for your changes. Use Google-style docstrings for public APIs.
3. Run `make check`, `make test`, and `make docs-test`.
4. Open a pull request with a title such as `fix: handle empty input`.
5. Squash merge the pull request so Release Please can use its title.

The Makefile contains the uv commands for each task. You can also run those
commands directly on Windows. If a Git hook changes a file, review and stage
the change before you commit again.

Use `uv add` for project dependencies and `uv add --dev` for development tools.
Commit `pyproject.toml` and `uv.lock` together. When you change the supported
Python versions, update `.python-version`, `requires-python`, Ruff's target,
and the Python versions in CI.

## Workflows

CI runs on pushes to `main` and on pull requests. It runs the checks and the
docs build once, then the test suite on Python 3.13 and 3.14. Linux only: a
deck is HTML, and nothing in mkdeck touches a platform API, so the Windows and
macOS runners would cost minutes without testing anything new.

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

Release Please creates the GitHub release and tag. Publishing to PyPI is a
separate step and is not wired up yet.
