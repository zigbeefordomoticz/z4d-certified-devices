#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Zigbee for Domoticz Plugin - Certified Device Configuration Loader
#
# This file is part of the Zigbee for Domoticz plugin: https://github.com/zigbeefordomoticz/Domoticz-Zigbee
# (C) 2015-2025
#
# SPDX-License-Identifier: GPL-3.0
#
#
"""
Module: certified_devices_loader
================================

This module provides functionality to import and register **certified Zigbee device configurations**
for the Zigbee for Domoticz plugin.

It scans the `Certified/` subdirectory within a specified repository path, where each manufacturer
has a dedicated folder containing JSON files that describe device models and their attributes.

The loader validates JSON integrity, checks plugin version compatibility, and populates
the plugin’s internal mappings:

- `self.DeviceConf`: Maps device model names to their JSON definitions.
- `self.ModelManufMapping`: Maps manufacturer identifiers to model names.

Key Functions
-------------
- `z4d_import_device_configuration(self, path_name)`: Main entry point to load all configurations.
- `_iter_valid_entries(directory)`: Internal helper to skip unwanted files.
- `_load_json_file(self, filename)`: Loads and validates JSON configuration files.
- `_is_plugin_version_compatible(model_def, plugin_version)`: Ensures compatibility with plugin version.
- `_register_device_config(self, model_name, model_def)`: Registers a certified device configuration.

Logging
-------
All operations are logged through `self.log.logging()` under the "z4dCertifiedDevices" category,
using log levels: `Status`, `Debug`, and `Error`.

Example Directory Layout
------------------------
Certified/
├── IKEA/
│   ├── TRADFRI_bulb.json
│   └── README.md
└── Philips/
    └── Hue_dimmer.json

Example Usage
-------------
>>> z4d_import_device_configuration(plugin_instance, "/opt/zigbee4domoticz/CertifiedDevices")

"""


import json
import os
from pathlib import Path

from .version import __version__


def z4d_import_device_configuration(self, path_name):
    """
    Load all certified Zigbee device configuration files from the given path.

    This function scans the Certified Devices directory structure:
    Certified/<Manufacturer>/<Device>.json
    Each valid JSON file defines a certified Zigbee device model configuration.

    Steps:
        1. Validate that the Certified directory exists.
        2. Iterate over each manufacturer folder.
        3. Parse and load each JSON config file if compatible with plugin version.
        4. Populate self.DeviceConf and self.ModelManufMapping.

    Args:
        self: Plugin instance, expected to have:
              - self.pluginParameters (dict)
              - self.DeviceConf (dict)
              - self.ModelManufMapping (dict)
              - self.log.logging(category, level, message)
        path_name (str | Path): Base path containing the "Certified" subdirectory.

    Logs:
        - Status: Summary of loaded device count.
        - Debug: Step-by-step loading details.
        - Error: Any file or version compatibility issues.
    """
    model_certified = Path(path_name) / "Certified"

    if not model_certified.is_dir():
        self.log.logging("z4dCertifiedDevices", "Status",
                         f"Z4D found an empty Certified Db {model_certified}")
        return

    plugin_version = self.pluginParameters.get("PluginVersion")
    device_count_before = len(self.DeviceConf)

    for brand_dir in _iter_valid_entries(model_certified):
        for config_file in _iter_valid_entries(model_certified / brand_dir):
            filename = model_certified / brand_dir / config_file
            model_def = _load_json_file(self, filename)
            if not model_def:
                continue

            model_name = Path(config_file).stem

            if model_name in self.DeviceConf:
                self.log.logging("z4dCertifiedDevices", "Debug",
                                 f"Config for {brand_dir}/{model_name} already defined, skipped.")
                continue

            if not _is_plugin_version_compatible(model_def, plugin_version):
                required = model_def.get("MinPluginVersion", "N/A")
                self.log.logging("z4dCertifiedDevices", "Error",
                                 f"Skipping {brand_dir}/{model_name}: requires Plugin ≥ {required}")
                continue

            _register_device_config(self, model_name, model_def)
            self.log.logging("z4dCertifiedDevices", "Debug",
                             f"Loaded certified {brand_dir}/{model_name}")

    new_device_count = len(self.DeviceConf) - device_count_before
    self.log.logging("z4dCertifiedDevices", "Status",
                     f"Z4D loaded {new_device_count} certified devices from repository version [{__version__}]")
    self.log.logging("z4dCertifiedDevices", "Debug",
                     f"DeviceConf keys: {list(self.DeviceConf.keys())}")
    self.log.logging("z4dCertifiedDevices", "Debug",
                     f"ModelManufMapping keys: {list(self.ModelManufMapping.keys())}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iter_valid_entries(directory: Path):
    """Yield directory entries, skipping README.md and .PRECIOUS."""
    for entry in os.listdir(directory):
        if entry not in ("README.md", ".PRECIOUS"):
            yield entry


def _load_json_file(self, filename: Path):
    """
    Load and parse a JSON configuration file.

    Returns:
        dict | None: Parsed JSON data if successful, otherwise None.

    Logs:
        - Error: If the file cannot be read or contains invalid JSON.
    """
    try:
        with open(filename, "r", encoding="utf-8") as fh:
            return json.load(fh)

    except FileNotFoundError:
        self.log.logging(
            "z4dCertifiedDevices", "Error",
            f"Configuration file not found: {filename}"
        )

    except json.JSONDecodeError as err:
        self.log.logging(
            "z4dCertifiedDevices", "Error",
            f"Invalid JSON in {filename} (line {err.lineno}, column {err.colno}): {err.msg}"
        )

    except OSError as err:
        self.log.logging(
            "z4dCertifiedDevices", "Error",
            f"I/O error while reading {filename}: {err.strerror or err}"
        )

    return None


def _is_plugin_version_compatible(model_def: dict, plugin_version: str) -> bool:
    """Return True if the model's minimum required plugin version is met."""
    min_version = model_def.get("MinPluginVersion")
    return not (min_version and plugin_version < min_version)


def _register_device_config(self, model_name: str, model_def: dict):
    """
    Register the loaded device configuration.

    Adds the device model to `DeviceConf` and updates
    `ModelManufMapping` with all identifiers.
    """
    self.DeviceConf[model_name] = model_def
    for identifier in model_def.get("Identifier", []):
        self.ModelManufMapping[tuple(identifier)] = model_name
