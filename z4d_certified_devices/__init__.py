#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Implementation of Zigbee for Domoticz plugin.
#
# This file is part of Zigbee for Domoticz plugin. https://github.com/zigbeefordomoticz/Domoticz-Zigbee
# (C) 2015-2024
#
# Initial authors: zaraki673 & pipiche38
#
# SPDX-License-Identifier:    GPL-3.0 license

import json
import os.path
from pathlib import Path
import os

from .version import __version__


def z4d_import_device_configuration(self, path_name):

    model_certified = Path(path_name) / "Certified"
    plugin_version = self.pluginParameters.get("PluginVersion")

    if not os.path.isdir(model_certified):
        self.log.logging("z4dCertifiedDevices", "Status", f"Z4D found an empty Certified Db {model_certified}")
        return
    
    for device_brand in os.listdir(model_certified):
        if device_brand in ("README.md", ".PRECIOUS"):
            continue
    
        model_directory = Path(model_certified) / device_brand
    
        for model_device_file in os.listdir(model_directory):
            if model_device_file in ("README.md", ".PRECIOUS"):
                continue
    
            filename = model_directory / model_device_file
    
            try:
                with open(filename, "rt", encoding='utf-8') as file_handle:
                    model_definition = json.load(file_handle)
    
            except (ValueError, Exception) as error:
                error_type = type(error).__name__
                error_msg = f"JSON ConfFile: {filename} load failed with error: {error_type}, skipping this config file."
                self.log.logging("z4dCertifiedDevices", "Error", error_msg)
                continue
    
            device_model_name = _get_model_name(model_device_file)
    
            if device_model_name in self.DeviceConf:
                self.log.logging("z4dCertifiedDevices", "Debug", f"Config for {device_brand}/{device_model_name} not loaded as already defined")
                continue
    
            self.log.logging("z4dCertifiedDevices", "Debug", f"processing certified {device_brand}/{device_model_name}")
    
            if not _is_model_requirement_match_plugin_version(self, model_definition, plugin_version):
                min_plugin_version = model_definition.get("MinPluginVersion", "N/A")
                error_msg = f"Certified Devices load skip this Certified device {device_brand}-{device_model_name} requires Plugin version {min_plugin_version}"
                self.log.logging("z4dCertifiedDevices", "Error", error_msg)
                continue

            _process_device_config_file(self, device_model_name, model_definition)

    self.log.logging("z4dCertifiedDevices", "Debug", f"Config loaded: {self.DeviceConf.keys()}")
    self.log.logging("z4dCertifiedDevices", "Debug", f"Certified Devices ModelManufMapping loaded - {self.ModelManufMapping.keys()}")
    
    self.log.logging("z4dCertifiedDevices", "Status", f"Z4D loads {len(self.DeviceConf)} Certified devices from repository.")


def _get_model_name(model_device_file):
    """Remove .json from filename to get the Device Model."""
    return os.path.splitext(os.path.basename(model_device_file))[0]


def _is_model_requirement_match_plugin_version(self, model_definition, plugin_version):
    """ is the config file working with this version of the plugin """
    return not ("MinPluginVersion" in model_definition and plugin_version < model_definition["MinPluginVersion"])

    
def _process_device_config_file(self, device_model_name, model_definition):
    """Load the config into DeviceConf and, if needed (Tuya), load into the model name mapping."""
    self.DeviceConf[device_model_name] = model_definition
    identifier_list = model_definition.get("Identifier", [])
    for identifier_tuple in identifier_list:
        self.ModelManufMapping[tuple(identifier_tuple)] = device_model_name
