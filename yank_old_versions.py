import os
import subprocess
import sys

import requests
from packaging.version import parse

# Replace with your package name
package_name = "z4d-certified-devices"

# Fetch the list of releases from PyPI
response = requests.get(f"https://pypi.org/pypi/{package_name}/json")
data = response.json()
PYPI_TOKEN = os.environ.get("TWINE_PASSWORD")
if not PYPI_TOKEN:
    print("❌ TWINE_PASSWORD environment variable not set")
    sys.exit(1)

try:
    response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=30)
    response.raise_for_status()
except requests.RequestException as err:
    print(f"❌ Failed to fetch release list from PyPI: {err}")
    sys.exit(1)

# Get the list of versions and sort them
data = response.json()
versions = list(data["releases"].keys())
versions.sort(key=parse, reverse=True)

# Keep only the last 50 versions
versions_to_keep = versions[:50]
versions_to_yank = versions[50:]

# Yank the old versions using the PyPI API
if not versions_to_yank:
    print("✅ No versions to yank.")
    sys.exit(0)

failed = False
for version in versions_to_yank:
    yank_url = f"https://pypi.org/pypi/{package_name}/{version}/json"
    yank_data = {
        "versions": [version]
    }
    response = requests.post(yank_url, json=yank_data, auth=('__token__', 'YOUR_PYPI_API_TOKEN'))
    if response.status_code == 200:
        print(f"Successfully yanked version {version}")
    result = subprocess.run(
        [
            sys.executable, "-m", "twine", "yank",
            package_name,
            "--version", version,
            "--reason", "Superseded by newer release",
        ],
        env={**os.environ, "TWINE_USERNAME": "__token__", "TWINE_PASSWORD": PYPI_TOKEN},
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"✅ Yanked {version}")
    else:
        print(f"Failed to yank version {version}: {response.status_code} {response.text}")
        print(f"❌ Failed to yank {version}: {result.stderr.strip()}")
        failed = True

sys.exit(1 if failed else 0)