import json
import os.path
from os import listdir
from os.path import isdir, isfile, join
import Domoticz



def importDeviceConfV2(self):


    # Read DeviceConf for backward compatibility 
    self.DeviceConf = {}
    model_certified = self.pluginconf.pluginConf["pluginConfig"] + "Certified"

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
    self.log.logging("Database", "Status", "DeviceConf loaded - %s confs loaded" %len(self.DeviceConf))


def load_zcl_cluster(self):
    zcl_cluster_path = self.pluginconf.pluginConf["pluginConfig"] + "ZclDefinitions"
    if not isdir(zcl_cluster_path):
        return

    self.log.logging("ZclClusters", "Status", "Loading ZCL Cluster definitions")

    zcl_cluster_definition = [f for f in listdir(zcl_cluster_path) if isfile(join(zcl_cluster_path, f))]
    for cluster_definition in sorted(zcl_cluster_definition):
        cluster_filename = str(zcl_cluster_path + "/" + cluster_definition)
        cluster_definition = _read_zcl_cluster( self, cluster_filename )

        if (
            cluster_definition is None
            or "ClusterId" not in cluster_definition
            or "Enabled" not in cluster_definition or not cluster_definition["Enabled"]
            or cluster_definition[ "ClusterId"] in self.readZclClusters
            or "Description" not in cluster_definition
        ):
            continue
        
        self.readZclClusters[ cluster_definition[ "ClusterId"] ] = {
            "Description": cluster_definition[ "Description" ],
            "Version": cluster_definition[ "Version" ],
            "Attributes": dict( cluster_definition[ "Attributes" ] )
        }

        self.log.logging("ZclClusters", "Status", " - ZCL Cluster %s - (V%s) %s loaded" %( 
            cluster_definition[ "ClusterId"], cluster_definition[ "Version" ], cluster_definition["Description"],))


def _read_zcl_cluster( self, cluster_filename ):
    with open(cluster_filename, "rt") as handle:
        try:
            return json.load(handle)
        except ValueError as e:
            self.log.logging("ZclClusters", "Error", "--> JSON readZclClusters: %s load failed with error: %s" % (cluster_filename, str(e)))
            return None

        except Exception as e:
            self.log.logging("ZclClusters", "Error", "--> JSON readZclClusters: %s load general error: %s" % (cluster_filename, str(e)))
            return None
    return None
