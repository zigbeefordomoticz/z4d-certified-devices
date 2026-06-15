# AGENT.md

Guidance for AI coding agents (and humans) working in this repository.

## What this project is

`z4d-certified-devices` is a Python package that ships **certified Zigbee
device configuration files** for the
[Zigbee for Domoticz](https://github.com/zigbeefordomoticz/Domoticz-Zigbee)
plugin. It is published to PyPI as `z4d-certified-devices` and is a runtime
dependency of the plugin.

The package is *mostly data*: ~700 JSON files describing how individual Zigbee
devices should be paired and behave. The only meaningful Python code is a small
loader that the plugin calls at startup.

## Repository layout

```
z4d_certified_devices/
├── __init__.py            # The loader: z4d_import_device_configuration() + helpers
├── version.py             # MAJOR_VERSION / MINOR_VERSION / __version__
└── Certified/
    └── <Manufacturer>/    # one folder per brand (Ikea, Philips, Tuya, ...)
        └── <Model>.json   # one file per device model
tests/
└── tests_loader.py        # pytest suite for the loader
bump_version.py            # bumps MINOR_VERSION and commits (used by CI)
pyproject.toml             # build + pytest config
setup.cfg                  # package metadata, package_data globs
.flake8                    # lint config
.github/workflows/         # CI: PyPI release, JSON lint, issue triage
```

## How the loader works

`z4d_import_device_configuration(self, path_name)` in
`z4d_certified_devices/__init__.py` is the entry point. It:

1. Looks for a `Certified/` directory under `path_name`.
2. Iterates each `<Manufacturer>/<Model>.json` (skipping `README.md` and
   `.PRECIOUS` via `_iter_valid_entries`).
3. Loads/validates each JSON file (`_load_json_file`).
4. Skips files whose `MinPluginVersion` is newer than the running plugin
   (`_is_plugin_version_compatible` / `_version_tuple`) — note version
   comparison is **numeric per component**, not lexicographic (`7.99 < 7.100`).
5. Skips duplicate model names (first one wins; iteration is sorted, so loading
   is deterministic).
6. Registers each config into `self.DeviceConf` (keyed by model name, the file
   stem) and `self.ModelManufMapping` (keyed by `Identifier` tuples)
   via `_register_device_config`.

The `self` passed in is the plugin instance; it is expected to provide
`pluginParameters`, `DeviceConf`, `ModelManufMapping`, and
`log.logging(category, level, message)`.

## Device JSON files

Each file under `Certified/<Manufacturer>/` describes one device model. The
**filename stem is the model name** used as the `DeviceConf` key, so keep names
accurate and unique across the whole `Certified/` tree.

Common keys seen in these files:

- `Ep` — endpoint → cluster map (with per-endpoint `Type`).
- `Type` — top-level Domoticz device type.
- `ClusterToBind` — clusters to bind at pairing.
- `ConfigureReporting` — attribute reporting configuration.
- `ReadAttributes` — attributes to read at pairing.
- `Identifier` (optional) — list of `[model, manufacturer]` pairs that map a
  device to this config in `ModelManufMapping`.
- `MinPluginVersion` (optional) — minimum plugin version required to load this
  config.

When adding or editing a device:

- Place the file in the correct manufacturer folder (create it if the brand is
  new).
- Use tabs/structure consistent with neighbouring files in the same folder.
- **Valid JSON only** — CI runs a JSON syntax check on changed `*.json` files.
- Don't rename an existing model file casually; the stem is a stable key.

## Build, test, and lint

```bash
# Install dev tooling
pip install -r requirements-dev.txt

# Run the test suite.
# NOTE: the file is tests/tests_loader.py, which does NOT match pytest's
# default test_*.py discovery glob, so a bare `pytest` collects 0 tests.
# Run it by path:
pytest tests/tests_loader.py

# Lint Python (config in .flake8, max-line-length 160, many codes ignored)
flake8 z4d_certified_devices tests

# Build the distribution locally
python -m build
```

There is no application to "run" — this package is a library/data set consumed
by the Domoticz plugin.

## Versioning & releases — IMPORTANT

- **Do not manually bump the version.** `version.py` is bumped automatically.
- On every push to `main`, the `PyPI Release` workflow
  (`.github/workflows/ci-cd.yml`) runs `bump_version.py` to increment
  `MINOR_VERSION`, commits `Bump to X.YYY`, and publishes to PyPI. Commits whose
  message starts with `Bump to` are skipped to avoid an infinite loop.
- Practical effect: a normal change adds/edits JSON or loader code; the version
  bump happens for you after merge to `main`.

## Conventions for agents

- Keep changes minimal and focused; this is a curated device database.
- Prefer adding/editing JSON over touching the loader. If you change the loader,
  add/adjust tests in `tests/tests_loader.py`.
- Match the style of surrounding files (the codebase tolerates loose formatting;
  see `.flake8` for what's intentionally ignored).
- Do not create pull requests unless explicitly asked.
- Do not edit `version.py` by hand or add `Bump to ...` commits — CI owns that.
