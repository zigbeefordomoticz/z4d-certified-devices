#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: GPL-3.0
#
"""Shared pytest fixtures for the certified-device test suite.

`tests/` is not a package, so pytest prepends this directory to `sys.path` and
`certified_schema` imports directly. The repository root is added here as well
so `z4d_certified_devices` imports whatever the checkout contains rather than
an installed copy of the package.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import certified_schema  # noqa: E402  (needs the sys.path tweak above)


@pytest.fixture(scope="session")
def certified_devices():
    """Every certified config, parsed once: `{"<Manufacturer>/<Model>.json": model_def}`."""
    return {
        certified_schema.device_id(path): certified_schema.load_device(path)
        for path in certified_schema.iter_device_files()
    }


@pytest.fixture(scope="session")
def baseline():
    """Pre-existing violations the suite tolerates. See `tests/certified_baseline.json`."""
    return certified_schema.load_baseline()


@pytest.fixture(scope="session")
def issues_by_device(certified_devices):
    """Every finding of the whole database: `{device: [Issue, ...]}`, clean files omitted."""
    found = {}
    for device, model_def in certified_devices.items():
        issues = certified_schema.validate_device(model_def)
        if issues:
            found[device] = issues
    return found
