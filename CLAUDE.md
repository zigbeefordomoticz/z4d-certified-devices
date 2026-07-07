# CLAUDE.md

This file gives Claude Code guidance for working in this repository.

The full project guidance lives in **[AGENT.md](./AGENT.md)** — read it first.
It covers the repo layout, how the device loader works, the device JSON format,
build/test/lint commands, and the automated versioning/release flow.

## Quick reference

- **What this is:** a PyPI package of certified Zigbee device config files
  (`Certified/<Manufacturer>/<Model>.json`) for the Zigbee for Domoticz plugin.
  Mostly data, plus a small loader in `z4d_certified_devices/__init__.py`.
- **Test:** `pytest tests/tests_loader.py` (a bare `pytest` collects 0 — the
  filename doesn't match the default `test_*.py` glob)
- **Lint:** `flake8 z4d_certified_devices tests`
- **Build:** `python -m build`

## Reminders

- **Never** bump `version.py` by hand — CI does it on push to `main`
  (`.github/workflows/ci-cd.yml`). Never create `Bump to ...` commits.
- Adding a device = add a valid JSON file under the right manufacturer folder.
  The filename stem is the model name and must be unique across `Certified/`.
- CI lints changed JSON files, so keep JSON syntactically valid.
- Prefer JSON edits over loader changes; if you change the loader, update
  `tests/tests_loader.py`.
- Multi-gang / DP-based Tuya (TS0601) devices: route each datapoint to its own
  widget with `domo_ep`, and declare non-physical endpoints in both `Ep` and the
  top-level `FakeEp`. See the "Multi-gang" note in AGENT.md.
- To identify a device or find its datapoints, cross-check upstream:
  [zigbee-herdsman-converters](https://github.com/Koenkk/zigbee-herdsman-converters)
  and [zha-device-handlers](https://github.com/zigpy/zha-device-handlers) —
  especially for Tuya `TS0601` DPs (their DP numbers are **decimal**; convert to
  this repo's two-digit **hex** keys). See AGENT.md → "Upstream references".
- Don't open a pull request unless explicitly asked.
