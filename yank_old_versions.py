import requests
from packaging.version import parse

# Replace with your package name
package_name = "z4d-certified-devices"

# Fetch the list of releases from PyPI
response = requests.get(f"https://pypi.org/pypi/{package_name}/json")
data = response.json()

# Get the list of versions and sort them
versions = list(data["releases"].keys())
versions.sort(key=parse, reverse=True)

# Keep only the last 50 versions
versions_to_keep = versions[:50]
versions_to_yank = versions[50:]

# Yank the old versions using the PyPI API
for version in versions_to_yank:
    yank_url = f"https://pypi.org/pypi/{package_name}/{version}/json"
    yank_data = {
        "versions": [version]
    }
    response = requests.post(yank_url, json=yank_data, auth=('__token__', 'YOUR_PYPI_API_TOKEN'))
    if response.status_code == 200:
        print(f"Successfully yanked version {version}")
    else:
        print(f"Failed to yank version {version}: {response.status_code} {response.text}")

