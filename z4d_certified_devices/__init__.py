import json
import os.path
from os import listdir
from os.path import isdir, isfile, join
import Domoticz

from .version import __version__


def z4d_import_device_configuration(self, path_name):

    # Read DeviceConf for backward compatibility 
    self.DeviceConf = {}
    model_certified = path_name + "Certified"
    plugin_version = self.pluginParameters["PluginVersion"]

    if os.path.isdir(model_certified):
        model_brand_list = [f for f in listdir(model_certified) if isdir(join(model_certified, f))]

        for brand in model_brand_list:
            if brand in ("README.md", ".PRECIOUS"):
                continue

            model_directory = model_certified + "/" + brand

            model_list = [f for f in listdir(model_directory) if isfile(join(model_directory, f))]

            for model_device in model_list:
                if model_device in ("README.md", ".PRECIOUS"):
                    continue

                filename = str(model_directory + "/" + model_device)
                with open(filename, "rt", encoding='utf-8') as handle:
                    try:
                        model_definition = json.load(handle)
                    except ValueError as e:
                        Domoticz.Error("--> JSON ConfFile: %s load failed with error: %s" % (filename, str(e)))

                        continue
                    except Exception as e:
                        Domoticz.Error("--> JSON ConfFile: %s load general error: %s" % (filename, str(e)))

                        continue

                try:
                    device_model_name = model_device.rsplit(".", 1)[0]
                    if device_model_name in self.DeviceConf:
                        self.log.logging( "z4dCertifiedDevices", "Debug", "--> Config for %s/%s not loaded as already defined" % (str(brand), str(device_model_name)),)
                        continue

                    self.log.logging( "z4dCertifiedDevices", "Debug", "--> Config for %s/%s" % (str(brand), str(device_model_name)))
                    if "MinPluginVersion" in model_definition and plugin_version < model_definition["MinPluginVersion"]:
                        self.log.logging( "z4dCertifiedDevices", "Log", "Skip this Certified device %s-%s requires Plugin version %s" % (
                            str(brand), str(device_model_name), model_definition["MinPluginVersion"] ),)
                        continue

                    self.DeviceConf[device_model_name] = dict(model_definition)
                except Exception:
                    Domoticz.Error("--> Unexpected error when loading a configuration file")

    self.log.logging("z4dCertifiedDevices", "Debug", "--> Config loaded: %s" % self.DeviceConf.keys())
    self.log.logging("z4dCertifiedDevices", "Status", "Certified Devices loaded - %s confs loaded" %len(self.DeviceConf))
