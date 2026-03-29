#!/usr/bin/env python3
"""
Bump the MINOR_VERSION in version.py and commit with message 'Bump to x.yyy'.
Usage: python bump_version.py
"""

import re
import subprocess
import sys

VERSION_FILE = "z4d_certified_devices/version.py"

# Read current content
with open(VERSION_FILE, "r") as f:
    content = f.read()

# Extract current values
major_match = re.search(r"^MAJOR_VERSION\s*=\s*(\d+)", content, re.MULTILINE)
minor_match = re.search(r"^MINOR_VERSION\s*=\s*(\d+)", content, re.MULTILINE)

if not major_match or not minor_match:
    print("❌ Could not find MAJOR_VERSION or MINOR_VERSION in version.py")
    sys.exit(1)

major = int(major_match.group(1))
minor = int(minor_match.group(1))

# Bump minor
new_minor = minor + 1
new_version = f"{major}.{new_minor}"

# Replace only the MINOR_VERSION line
new_content = re.sub(
    r"^(MINOR_VERSION\s*=\s*)\d+",
    rf"\g<1>{new_minor}",
    content,
    flags=re.MULTILINE
)

# Write back
with open(VERSION_FILE, "w") as f:
    f.write(new_content)

print(f"✅ Bumped MINOR_VERSION: {major}.{minor} → {new_version}")

# Git commit
try:
    subprocess.run(["git", "add", VERSION_FILE], check=True)
    subprocess.run(["git", "commit", "-m", f"Bump to {new_version}"], check=True)
    print(f"✅ Committed: 'Bump to {new_version}'")
except subprocess.CalledProcessError as e:
    print(f"❌ Git error: {e}")
    sys.exit(1)
