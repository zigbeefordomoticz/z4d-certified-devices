#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: GPL-3.0
#
"""Database-wide tests: layout, model-name uniqueness, baseline hygiene.

`tests_loader.py` proves the loader *behaves* a certain way on a synthetic
tree; these tests prove the real `Certified/` tree is one the loader actually
loads. Both of the invariants below are enforced by silence in the loader:

* a JSON file that is not at `Certified/<Manufacturer>/<Model>.json` is never
  visited (`if not brand_path.is_dir(): continue`);
* two files with the same stem collide on the `DeviceConf` key, and the second
  one is dropped with a Debug-level message.
"""

import json

import pytest

import certified_schema
from certified_schema import ERROR, WARNING

# Model names that already collide across two manufacturer folders. The loader
# keeps the alphabetically first folder and drops the other, so the dropped
# config is unreachable -- but these are long-standing brand aliases, left as
# they are. Nothing new may join the list.
KNOWN_DUPLICATE_MODELS = {
    "Dimmer-Switch-ZB3.0": ["EcoDim", "Idinio"],
    "LXEK-1": ["Adeo", "ENKI-LEXMAN"],
    "LXEK-2": ["Adeo", "ENKI-LEXMAN"],
    "LXEK-7": ["Adeo", "ENKI-LEXMAN"],
    "SA-003-Zigbee": ["Others", "eWeLink"],
    "SA-030-1": ["Sonoff", "eWeLink"],
    "ZB-CL01": ["Others", "Ysrai"],
    "ZB-CT01": ["Others", "Ysrai"],
    "ZB-SW01": ["Others", "Ysrai"],
    "ZB-SW02": ["Others", "Ysrai"],
}

# JSON files sitting at the root of Certified/ instead of in a manufacturer
# folder. The loader never reaches them, so they are dead files.
KNOWN_STRAY_FILES = {"Excellux.json"}


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

class TestCertifiedLayout:
    def test_certified_directory_exists(self):
        assert certified_schema.CERTIFIED_ROOT.is_dir(), "missing %s" % certified_schema.CERTIFIED_ROOT

    def test_database_is_not_empty(self):
        assert len(certified_schema.iter_device_files()) > 500

    def test_every_json_file_is_in_a_manufacturer_folder(self):
        root = certified_schema.CERTIFIED_ROOT
        stray = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*.json")
            if path.parent == root or path.parent.parent != root
        )
        assert set(stray) <= KNOWN_STRAY_FILES, (
            "these files are not at Certified/<Manufacturer>/<Model>.json, so the loader never visits them: %s"
            % sorted(set(stray) - KNOWN_STRAY_FILES)
        )

    def test_model_names_are_unique_across_manufacturers(self):
        by_stem = {}
        for path in certified_schema.iter_device_files():
            by_stem.setdefault(path.stem, []).append(path.parent.name)

        duplicates = {stem: sorted(brands) for stem, brands in by_stem.items() if len(brands) > 1}
        new = {stem: brands for stem, brands in duplicates.items() if KNOWN_DUPLICATE_MODELS.get(stem) != brands}
        assert not new, (
            "the file stem is the DeviceConf key, so a duplicate silently drops one config: %s" % new
        )


# ---------------------------------------------------------------------------
# JSON integrity
# ---------------------------------------------------------------------------

class TestCertifiedJson:
    def test_every_file_is_valid_json(self):
        broken = []
        for path in certified_schema.iter_device_files():
            try:
                certified_schema.load_device(path)
            except (json.JSONDecodeError, UnicodeDecodeError) as err:
                broken.append("%s: %s" % (certified_schema.device_id(path), err))
        assert not broken, "invalid JSON is skipped at load time with an Error log:\n  " + "\n  ".join(broken)

    def test_every_file_is_a_json_object(self, certified_devices):
        wrong = sorted(device for device, model_def in certified_devices.items() if not isinstance(model_def, dict))
        assert not wrong, "a device config must be a JSON object: %s" % wrong

    def test_every_file_declares_endpoints(self, certified_devices):
        # _register_device_config() stores the config as-is; the plugin then
        # walks model_def["Ep"] to build the widgets.
        missing = sorted(device for device, model_def in certified_devices.items() if not isinstance(model_def.get("Ep"), dict))
        assert not missing, "every config needs an \"Ep\" object: %s" % missing


# ---------------------------------------------------------------------------
# Baseline hygiene
# ---------------------------------------------------------------------------

class TestBaseline:
    def test_baseline_file_is_present_and_well_formed(self):
        baseline = certified_schema.load_baseline()
        assert isinstance(baseline, dict)
        for device, keys in baseline.items():
            assert isinstance(keys, list), "%s must map to a list" % device
            assert keys == sorted(keys), "%s entries must be sorted; regenerate the baseline" % device

    def test_baseline_only_mentions_existing_devices(self, certified_devices):
        unknown = sorted(set(certified_schema.load_baseline()) - set(certified_devices))
        assert not unknown, (
            "the baseline names device configs that no longer exist (renamed or removed): %s\n"
            "Refresh it with `python tests/certified_schema.py --update-baseline`." % unknown
        )

    def test_baseline_has_no_stale_entries(self, issues_by_device, baseline):
        """Every baselined issue must still be a real finding, so the list shrinks honestly."""
        stale = {}
        for device, keys in sorted(baseline.items()):
            fixed = certified_schema.stale_baseline_entries(issues_by_device.get(device, []), keys)
            if fixed:
                stale[device] = fixed
        assert not stale, (
            "these issues are fixed -- well done, now drop them from the baseline with "
            "`python tests/certified_schema.py --update-baseline`:\n%s"
            % "\n".join("  %s: %s" % (device, ", ".join(keys)) for device, keys in stale.items())
        )

    @pytest.mark.parametrize("severity", [ERROR, WARNING])
    def test_baseline_covers_the_whole_current_state(self, issues_by_device, baseline, severity):
        """Sanity check on the mechanism itself: nothing outstanding is left unaccounted for."""
        found = certified_schema.unbaselined_issues(issues_by_device, baseline, severity=severity)
        assert not found, certified_schema.format_report(found)
