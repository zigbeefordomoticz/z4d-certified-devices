
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

### Upstream references for identifying a device

When adding or investigating a device, cross-check it against the two upstream
open-source integration databases — they are the fastest way to identify what a
device actually is from its Zigbee model/manufacturer and to discover its
attributes:

- **zigbee-herdsman-converters** (Zigbee2MQTT) —
  <https://github.com/Koenkk/zigbee-herdsman-converters>
- **zha-device-handlers / zha-quirks** (Home Assistant ZHA) —
  <https://github.com/zigpy/zha-device-handlers>

These are **especially useful for Tuya `TS0601` datapoints (DPs)**: a `TS0601`
manufacturer id (e.g. `_TZE284_dvosyycn`) is opaque on its own, but grepping the
converter source for that id reveals the real model, description, and the full
DP → function map. In zigbee-herdsman-converters the mapping lives in the
device's `meta.tuyaDatapoints` (`[dp, name, converter]`), e.g. in
`src/devices/tuya.ts`. Note the **numbering difference**: upstream lists DPs in
**decimal**, while this repo's `TS0601_DP` keys are **two-digit lowercase hex**
(DP 101 → `"65"`), so convert when copying a mapping across.

- Document the TS0601_DP key format explicitly: keys are two-digit lowercase hex representing the Tuya datapoint (DP) index (e.g., DP 101 → "65", DP 37 → "25"), not the decimal DP number. This tripped me up initially — the irrigation valve file's "65", "66", "6f" keys aren't obvious as DP 101/102/111 without doing the hex conversion, and there's no comment anywhere stating the convention.
- Document the sub-keys used inside a TS0601_DP entry (store_tuya_attribute, sensor_type, action_type, domo_ep) and roughly what each governs, since the loader/plugin-side meaning isn't visible from this repo alone. `domo_ep` (optional) is the endpoint whose Domoticz widget that datapoint drives; it defaults to the source endpoint (`01`) and is the sub-key that routes one physical device's datapoints to several widgets (see the multi-gang note below).
- Add a note that action_type is a closed vocabulary interpreted by the Domoticz-Zigbee plugin itself (not this repo) — so a new DP mapping should reuse an existing action_type/sensor_type value where the behavior matches, rather than inventing a new one, unless the plugin actually defines a handler for it. I only discovered the existing vocabulary by grepping across all Tuya files; nothing points an agent there.
- Suggest a pointer to where action_type values are actually implemented (presumably in the Domoticz-Zigbee plugin repo, not here) — right now there's no way to verify from this repo alone whether a chosen action_type string is real or will silently no-op.

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
- `FakeEp` (optional) — list of *virtual* endpoints (e.g. `f2`, `f3`) that are
  declared in `Ep` so they host a widget, but that don't physically exist on the
  device. The plugin skips binding / reporting / attribute reads on them
  (`Modules/tools.py:is_fake_ep`). Used to give one physical device several
  Domoticz widgets.

### Multi-gang / DP-based Tuya (TS0601) switches

Some TS0601 devices expose several sub-devices over the single Tuya `ef00`
endpoint, each addressed by its own datapoint — e.g. the `TS0601_switch_8`
8-gang switch (`_TZE284_dvosyycn`), see
`Certified/Tuya/TS0601-8Gangs-switch.json`. To surface each gang as its own
Domoticz widget:

- Give each `TS0601_DP` switch entry (`sensor_type`/`action_type` = `"switch"`) a
  distinct `domo_ep`. That endpoint — not `action_type` — is what
  disambiguates the gangs.
- Every `domo_ep` value must be a real key in `Ep` (with a `Type`) so the widget
  exists. The physical endpoint (`01`) can host the first gang
  (`domo_ep: "01"`); the remaining gangs use virtual endpoints (`f2`, `f3`, …)
  that are declared in `Ep` **and** listed in `FakeEp`. A `domo_ep` pointing at
  an endpoint that appears in neither is a bug — that gang's widget is never
  updated. See `Certified/LUMI/lumi.switch.acn047.json` for the same pattern.
- Plugin caveat: independent per-gang *control* requires the Domoticz-Zigbee
  plugin's `ts0601_actuator` to select the datapoint by the widget endpoint
  (`domo_ep`), not only by `action_type`; otherwise every gang toggles the first
  switch datapoint. State reporting works without that change.

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
