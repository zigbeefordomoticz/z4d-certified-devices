import json
import os.path
from os import listdir
from os.path import isdir, isfile, join
import Domoticz



def z4d_import_device_configuration(self, path_name):

    # Read DeviceConf for backward compatibility 
    self.DeviceConf = {}
    model_certified =  path_name + "Certified"

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
                with open(filename, "rt") as handle:
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

                    if device_model_name not in self.DeviceConf:
                        self.log.logging(
                            "Database", "Debug", "--> Config for %s/%s" % (str(brand), str(device_model_name))
                        )
                        self.DeviceConf[device_model_name] = dict(model_definition)
                    else:
                        self.log.logging(
                            "Database",
                            "Debug",
                            "--> Config for %s/%s not loaded as already defined" % (str(brand), str(device_model_name)),
                        )
                except Exception:
                    Domoticz.Error("--> Unexpected error when loading a configuration file")

    self.log.logging("Database", "Debug", "--> Config loaded: %s" % self.DeviceConf.keys())
    self.log.logging("Database", "Status", "Certified Devices loaded - %s confs loaded" %len(self.DeviceConf))
