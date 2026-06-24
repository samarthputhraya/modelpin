# Publishing Modelpin

Steps that need **your own accounts/tokens** (a coding agent can't do these for you). The
package is already PyPI-ready: `pyproject.toml` has metadata + classifiers, `mp`/`modelpin`
entry points, and `python -m pip wheel . --no-deps` builds a clean wheel.

## 1. PyPI (so `pipx install modelpin` works)

```bash
# one-time: install build + twine
python -m pip install --upgrade build twine

# build sdist + wheel into dist/
python -m build            # or: python -m pip wheel . --no-deps -w dist

# (recommended) smoke-test on TestPyPI first
twine upload --repository testpypi dist/*
pipx install --index-url https://test.pypi.org/simple/ "modelpin[providers]"

# publish to real PyPI (needs a PyPI account + an API token in ~/.pypirc or TWINE_PASSWORD)
twine upload dist/*
```

After publishing, anyone can:

```bash
pipx install "modelpin[providers]"     # isolated CLI install
# or
pip install "modelpin[providers]"
mp --help
```

Bump `version` in `pyproject.toml` **and** `__version__` in `modelpin/__init__.py` for each
release (keep them in sync), tag it (`git tag v0.1.0 && git push --tags`), then re-`build` +
`twine upload`.

## 2. GitHub Action

The action lives in `actions/` (`action.yml` + `README.md`).

- **Before PyPI:** consumers set
  `modelpin-spec: "modelpin[providers] @ git+https://github.com/samarthputhraya/modelpin@TAG"`.
- **After PyPI:** the default `modelpin-spec: modelpin[providers]` just works.

To publish to the **GitHub Marketplace**: push a tag (e.g. `v1`), open the tag/release on
GitHub, and check "Publish this Action to the GitHub Marketplace" (requires the `action.yml`
at the path consumers reference and a unique action name). Maintain a moving `v1` tag for
consumers who pin to the major.

## 3. Checklist before the first public release

- [ ] `README.md` quickstart is accurate (install, `mp init/baseline/check`, the Action).
- [ ] Repo URL in `pyproject.toml` `[project.urls]` is github.com/samarthputhraya/modelpin ✓
      — verify the `Homepage = https://modelpin.dev` resolves (you own it) or point it at the repo.
- [ ] `LICENSE` present (Apache-2.0 ✓).
- [ ] `version` synced in `pyproject.toml` + `modelpin/__init__.py`.
- [ ] A green CI run of the Action against a real model (dogfood on this repo's examples).
