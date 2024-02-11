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

from .version import __version__


def z4d_import_device_configuration(self, path_name):

    model_certified = Path(path_name) / "Certified"
    plugin_version = self.pluginParameters.get("PluginVersion")

    if not os.path.isdir(model_certified):
        self.log.logging("z4dCertifiedDevices", "Status", f"none existing Z4D Certified Db at {model_certified} !!!")
        return
    
    for device_brand in os.listdir(model_certified):
        if device_brand in ("README.md", ".PRECIOUS"):
            continue

        model_directory = model_certified / device_brand

        for model_device_file in os.listdir(model_directory):
            if model_device_file in ("README.md", ".PRECIOUS"):
                continue

            filename = model_directory / model_device_file
            try:
                with open(filename, "rt", encoding='utf-8') as file_handle:
                    model_definition = json.load(file_handle)

            except ValueError as error:
                self.log.logging("z4dCertifiedDevices", "Error", f"JSON ConfFile: {filename} load failed with error: {error}, skiping this config file.")
                continue

            except Exception as error:
                self.log.logging("z4dCertifiedDevices", "Error", f"JSON ConfFile: {filename} load general error: {error}, skiping this config file.")
                continue

            device_model_name = _get_model_name(model_device_file )
            if device_model_name in self.DeviceConf:
                self.log.logging("z4dCertifiedDevices", "Debug", f"Config for {device_brand}/{device_model_name} not loaded as already defined")
                continue

            self.log.logging("z4dCertifiedDevices", "Debug", f"processing certified {device_brand}/{device_model_name}")

            if not _is_model_requirement_match_plugin_version(self, model_definition, plugin_version):
                self.log.logging( "z4dCertifiedDevices", "Error", f"Certified Devices load skip this Certified device %{device_brand}-{device_model_name} requires Plugin version {model_definition['MinPluginVersion']}")
                continue

            _process_device_config_file(self, device_model_name, model_definition)

    self.log.logging("z4dCertifiedDevices", "Debug", f"Config loaded: {self.DeviceConf.keys()}")
    self.log.logging("z4dCertifiedDevices", "Debug", f"Certified Devices ModelManufMapping loaded - {self.ModelManufMapping.keys()}")
    
    self.log.logging("z4dCertifiedDevices", "Status", f"{len(self.DeviceConf)} Certified devices loaded from z4d repository.")

def _get_model_name(model_device_file ):
    """ Purpose is to remove .json from filename to get the Device Model"""
    basename = os.path.basename(model_device_file)
    device_model_name = os.path.splitext(basename)[0]
    return device_model_name


def _is_model_requirement_match_plugin_version(self, model_definition, plugin_version):
    """ is the config file working with this version of the plugin """
    return not ("MinPluginVersion" in model_definition and plugin_version < model_definition["MinPluginVersion"])

    
def _process_device_config_file(self, device_model_name, model_definition):
    """ let's load the config into DeviceConf , and if needed (Tuya) lets also load into the model name mapping"""
    self.DeviceConf[device_model_name] = dict(model_definition)
    if "Identifier" not in model_definition:
        return
    for identifier_tuple in model_definition["Identifier"]:
        self.ModelManufMapping[ tuple(identifier_tuple) ] = device_model_name

