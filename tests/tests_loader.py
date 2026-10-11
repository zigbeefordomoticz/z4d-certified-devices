import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from z4d_certified_devices import (
    _is_plugin_version_compatible,
    _iter_valid_entries,
    _load_json_file,
    _register_device_config,
    _version_tuple,
    z4d_import_device_configuration,
)


class FakePlugin:
    def __init__(self, plugin_version="7.0"):
        self.DeviceConf = {}
        self.ModelManufMapping = {}
        self.pluginParameters = {"PluginVersion": plugin_version}
        self.log = MagicMock()
        self.log.logging = MagicMock()


# ---------------------------------------------------------------------------
# _version_tuple
# ---------------------------------------------------------------------------

class TestVersionTuple:
    def test_simple(self):
        assert _version_tuple("7.100") == (7, 100)

    def test_single_component(self):
        assert _version_tuple("7") == (7,)

    def test_invalid_returns_zero(self):
        assert _version_tuple("bad") == (0,)

    def test_none_returns_zero(self):
        assert _version_tuple(None) == (0,)


# ---------------------------------------------------------------------------
# _is_plugin_version_compatible
# ---------------------------------------------------------------------------

class TestVersionCompatibility:
    def test_no_min_version_is_always_compatible(self):
        assert _is_plugin_version_compatible({}, "7.0") is True

    def test_compatible_when_equal(self):
        assert _is_plugin_version_compatible({"MinPluginVersion": "7.0"}, "7.0") is True

    def test_compatible_when_higher(self):
        assert _is_plugin_version_compatible({"MinPluginVersion": "7.0"}, "8.0") is True

    def test_incompatible_when_lower(self):
        assert _is_plugin_version_compatible({"MinPluginVersion": "7.100"}, "7.99") is False

    def test_numeric_minor_comparison(self):
        # Lexicographic "7.99" > "7.100" but numerically 7.99 < 7.100
        assert _is_plugin_version_compatible({"MinPluginVersion": "7.100"}, "7.99") is False

    def test_major_version_bump_satisfies_min(self):
        assert _is_plugin_version_compatible({"MinPluginVersion": "7.500"}, "8.0") is True


# ---------------------------------------------------------------------------
# _iter_valid_entries
# ---------------------------------------------------------------------------

class TestIterValidEntries:
    def test_skips_readme(self, tmp_path):
        (tmp_path / "README.md").touch()
        (tmp_path / "device.json").touch()
        entries = list(_iter_valid_entries(tmp_path))
        assert "README.md" not in entries
        assert "device.json" in entries

    def test_skips_precious(self, tmp_path):
        (tmp_path / ".PRECIOUS").touch()
        (tmp_path / "device.json").touch()
        entries = list(_iter_valid_entries(tmp_path))
        assert ".PRECIOUS" not in entries

    def test_sorted_order(self, tmp_path):
        for name in ["c.json", "a.json", "b.json"]:
            (tmp_path / name).touch()
        assert list(_iter_valid_entries(tmp_path)) == ["a.json", "b.json", "c.json"]

    def test_empty_directory(self, tmp_path):
        assert list(_iter_valid_entries(tmp_path)) == []


# ---------------------------------------------------------------------------
# _load_json_file
# ---------------------------------------------------------------------------

class TestLoadJsonFile:
    def _make_certified(self, base_path: Path, brand: str, filename: str, content: dict):
        """Helper to create a certified device JSON file."""
        brand_dir = base_path / "Certified" / brand
        brand_dir.mkdir(parents=True, exist_ok=True)

        file_path = brand_dir / filename
        file_path.write_text(json.dumps(content))
        return file_path
    
    def test_missing_certified_dir_is_safe(self, tmp_path):
        plugin = FakePlugin()
        z4d_import_device_configuration(plugin, tmp_path)
        plugin.log.logging.assert_called()
        assert plugin.DeviceConf == {}

    def test_skips_incompatible_version(self, tmp_path):
        self._make_certified(tmp_path, "TestBrand", "NewDevice.json",
                             {"Ep": {}, "Type": "", "MinPluginVersion": "99.999"})
        plugin = FakePlugin(plugin_version="7.0")
        z4d_import_device_configuration(plugin, tmp_path)
        assert "NewDevice" not in plugin.DeviceConf

    def test_skips_duplicate_model_name(self, tmp_path):
        for brand in ["BrandA", "BrandB"]:
            d = tmp_path / "Certified" / brand
            d.mkdir(parents=True)
            (d / "SameDevice.json").write_text('{"Ep": {}, "Type": ""}')
        plugin = FakePlugin()
        z4d_import_device_configuration(plugin, tmp_path)
        assert len([k for k in plugin.DeviceConf if k == "SameDevice"]) == 1

    def test_skips_stray_file_at_brand_level(self, tmp_path):
        certified = tmp_path / "Certified"
        certified.mkdir()
        (certified / "stray_file.json").write_text('{"Ep": {}, "Type": ""}')
        plugin = FakePlugin()
        z4d_import_device_configuration(plugin, tmp_path)
        assert "stray_file" not in plugin.DeviceConf

    def test_invalid_json_is_skipped_gracefully(self, tmp_path):
        brand_dir = tmp_path / "Certified" / "BadBrand"
        brand_dir.mkdir(parents=True)
        (brand_dir / "broken.json").write_text("{not json}")
        plugin = FakePlugin()
        z4d_import_device_configuration(plugin, tmp_path)
        assert "broken" not in plugin.DeviceConf

    def test_loading_is_deterministic(self, tmp_path):
        certified = tmp_path / "Certified"
        for brand in ["Zzz", "Aaa"]:
            d = certified / brand
            d.mkdir(parents=True)
            (d / "Device.json").write_text(f'{{"Ep": {{}}, "Type": "{brand}"}}')
        plugin = FakePlugin()
        z4d_import_device_configuration(plugin, tmp_path)
        # "Aaa" sorts before "Zzz", so Aaa/Device loads first and wins
        assert plugin.DeviceConf["Device"]["Type"] == "Aaa"

# ---------------------------------------------------------------------------
# Identifier mappings: Conf/Local-Devices precedence
# ---------------------------------------------------------------------------

class TestIdentifierPrecedence:
    """
    The plugin loads its own Conf/Local-Devices folder before calling
    z4d_import_device_configuration(), so a (model, manufacturer) mapping that
    is already present belongs to the user and must survive this import.
    """

    def _certified(self, tmp_path, brand, model, identifiers):
        d = tmp_path / "Certified" / brand
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{model}.json").write_text(
            json.dumps({"Ep": {}, "Type": "", "Identifier": identifiers})
        )

    def test_local_identifier_is_not_overridden(self, tmp_path):
        self._certified(tmp_path, "Tuya", "TS011F-plug",
                        [["TS011F", "_TZ3000_cehuw1lw"]])
        plugin = FakePlugin()
        plugin.ModelManufMapping[("TS011F", "_TZ3000_cehuw1lw")] = "MyLocalPlug"

        z4d_import_device_configuration(plugin, tmp_path)

        assert plugin.ModelManufMapping[("TS011F", "_TZ3000_cehuw1lw")] == "MyLocalPlug"
        # the certified config itself is still loaded, only the mapping is kept
        assert "TS011F-plug" in plugin.DeviceConf

    def test_new_identifiers_are_still_registered(self, tmp_path):
        self._certified(tmp_path, "Tuya", "TS011F-plug",
                        [["TS011F", "_TZ3000_cehuw1lw"], ["TS011F", "_TZ3000_other"]])
        plugin = FakePlugin()
        plugin.ModelManufMapping[("TS011F", "_TZ3000_cehuw1lw")] = "MyLocalPlug"

        z4d_import_device_configuration(plugin, tmp_path)

        assert plugin.ModelManufMapping[("TS011F", "_TZ3000_cehuw1lw")] == "MyLocalPlug"
        assert plugin.ModelManufMapping[("TS011F", "_TZ3000_other")] == "TS011F-plug"

    def test_duplicate_inside_certified_db_keeps_last_one_wins(self, tmp_path):
        """
        Twelve identifiers are claimed by two different certified files today.
        Protecting pre-existing keys must not silently flip those to
        first-one-wins: only the plugin's own mappings are protected.
        """
        self._certified(tmp_path, "Aaa", "DeviceOne", [["TS0601", "_TZE200_x"]])
        self._certified(tmp_path, "Zzz", "DeviceTwo", [["TS0601", "_TZE200_x"]])
        plugin = FakePlugin()

        z4d_import_device_configuration(plugin, tmp_path)

        # Aaa loads first, Zzz overwrites - unchanged behaviour
        assert plugin.ModelManufMapping[("TS0601", "_TZE200_x")] == "DeviceTwo"

    def test_register_without_protected_set_overwrites(self, tmp_path):
        """_register_device_config keeps its old behaviour when called bare."""
        plugin = FakePlugin()
        plugin.ModelManufMapping[("M", "N")] = "Previous"

        _register_device_config(plugin, "NewModel",
                                {"Ep": {}, "Identifier": [["M", "N"]]})

        assert plugin.ModelManufMapping[("M", "N")] == "NewModel"
