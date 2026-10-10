#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Zigbee for Domoticz Plugin - Certified Device Configuration schema validator
#
# This file is part of the Zigbee for Domoticz plugin: https://github.com/zigbeefordomoticz/Domoticz-Zigbee
# (C) 2015-2025
#
# SPDX-License-Identifier: GPL-3.0
#
"""
Module: certified_schema
========================

Structural validation of the `ReadAttributes` and `ConfigureReporting` blocks of
a certified device configuration (`Certified/<Manufacturer>/<Model>.json`).

Why this exists
---------------
Neither block is validated at load time: `z4d_import_device_configuration()`
only checks that the file is syntactically valid JSON. Everything else is
consumed *verbatim* by the Domoticz-Zigbee plugin, so a structural mistake does
not fail loudly here — it either silently disables a feature on the device or
raises deep inside the plugin at pairing time.

Every rule below mirrors how the plugin actually reads the data, so the codes
map to a real, observable consequence:

`ReadAttributes` — `Modules/readAttributes.py`
    `retreive_attributes_based_on_configuration()` does
    `[int(attr, 16) for attr in DeviceConf[model]["ReadAttributes"][cluster]]`.

    * The cluster key is matched against the *device's* cluster list, which is
      lowercase 4-digit hex. A key of any other shape never matches, so the
      entry is dead config (`ra-cluster-id-malformed`).
    * Attribute ids go through `int(attr, 16)`, which is forgiving about width
      and case — `"004"` still resolves to `0x0004`. A width typo is therefore
      cosmetic (`ra-attribute-id-width`) *unless* it changes the value:
      `"40001"` parses as `0x40001` and is emitted as a 5-digit id
      (`ra-attribute-id-overflow`).
    * A string instead of a list iterates character by character, which yields
      garbage attribute ids (`ra-attributes-not-a-list`).

`ConfigureReporting` — `Classes/ConfigureReporting.py` + `Zigbee/zclCommands.py`
    * `configure_reporting_for_one_endpoint()` does
      `if "Attributes" not in cfgrpt_configuration[cluster]: continue`, so the
      flat shape `{"0001": {"0021": {...}}}` is *silently* skipped
      (`cr-missing-attributes-wrapper`) — no error, nothing above Debug.
    * `prepare_and_send_configure_reporting()` reads `DataType`, `MinInterval`,
      `MaxInterval` and `TimeOut` with no default, so a missing key is a
      `KeyError` that aborts configure reporting for the *whole device*
      (`cr-missing-required-key`). `Change` is read on the analog branch only
      (`cr-missing-change`).
    * A `DataType` that classifies as neither analog, discrete nor composite is
      dropped with "Unexpected Data Type" (`cr-datatype-unknown`).
    * The records are concatenated straight into the ZCL frame
      (`zcl_configure_reporting_requestv2`: `data += direction + x["DataType"]
      + x["Attribute"] + x["minInter"] + x["maxInter"] + x["timeOut"]`), so the
      field widths are load-bearing, not cosmetic (`cr-field-width`).
    * `Change` is the reportable change, whose width follows the attribute's
      data type (`SIZE_DATA_TYPE`). In raw mode it is re-encoded by
      `Zigbee/encoder_tools.py:decode_endian_data()`, which byte-swaps on the
      *expected* width — so a 4-digit `Change` on a 4-byte type is not padded,
      it is byte-swapped into a value a million times too large
      (`cr-change-width`).

Usage
-----
As a library (see `tests_read_attributes.py` / `tests_configure_reporting.py`)::

    from certified_schema import iter_device_files, load_device, validate_device

    issues = validate_device(load_device(path))

As a CLI, to review the whole certified database or refresh the baseline::

    python tests/certified_schema.py --report
    python tests/certified_schema.py --report --severity error
    python tests/certified_schema.py --update-baseline
"""

import argparse
import json
import re
import sys
from collections import namedtuple
from pathlib import Path

# ---------------------------------------------------------------------------
# Severities
# ---------------------------------------------------------------------------

ERROR = "error"
"""The plugin raises, or silently ignores the entry: the config does not work."""

WARNING = "warning"
"""The plugin copes with it: cosmetic or redundant, worth fixing but harmless."""

SEVERITIES = (ERROR, WARNING)

Issue = namedtuple("Issue", ["code", "severity", "location", "message"])
"""A single finding. `location` is a dotted path into the device JSON."""


def _issue_key(issue):
    """Stable, human-readable identity of an issue, used as the baseline key."""
    return "%s %s" % (issue.code, issue.location)


# ---------------------------------------------------------------------------
# Constants mirrored from the plugin
#
# Keep these in sync with Domoticz-Zigbee; they are duplicated rather than
# imported because this package must not depend on the plugin to run its tests.
# ---------------------------------------------------------------------------

# Modules/zigateConsts.py:analog_value()
ANALOG_DATA_TYPES = frozenset(
    list(range(0x20, 0x30)) + [0x38, 0x39, 0x3A, 0xE0, 0xE1, 0xE2]
)

# Modules/zigateConsts.py:discrete_value()
DISCRETE_DATA_TYPES = frozenset(
    list(range(0x08, 0x10)) + list(range(0x18, 0x20)) + [0x10, 0x30, 0x31, 0xE8, 0xE9, 0xEA, 0xF0, 0xF1]
)

# Modules/zigateConsts.py:composite_value()
COMPOSITE_DATA_TYPES = frozenset([0x41, 0x42, 0x43, 0x44, 0x48, 0x4C, 0x50, 0x51])

# Modules/zigateConsts.py:SIZE_DATA_TYPE -- length in bytes of each data type
SIZE_DATA_TYPE = {
    0x08: 1, 0x09: 2, 0x0A: 3, 0x0B: 4, 0x0C: 5, 0x0D: 6, 0x0E: 7, 0x0F: 8,
    0x10: 1,
    0x16: 2, 0x18: 1, 0x19: 2, 0x1A: 3, 0x1B: 4, 0x1C: 5, 0x1D: 6, 0x1E: 7, 0x1F: 8,
    0x20: 1, 0x21: 2, 0x22: 3, 0x23: 4, 0x24: 5, 0x25: 6, 0x26: 7, 0x27: 8,
    0x28: 1, 0x29: 2, 0x2A: 3, 0x2B: 4, 0x2C: 5, 0x2D: 6, 0x2E: 7, 0x2F: 8,
    0x30: 1, 0x31: 2,
    0x38: 2, 0x39: 4, 0x3A: 8,
    0xE0: 4, 0xE1: 4, 0xE2: 4, 0xE8: 2, 0xE9: 2,
    0xF0: 8, 0xF1: 16,
}

# Zigbee/encoder_tools.py:decode_endian_data() explicitly accepts a 16-digit
# (8 byte) literal for the 3, 5, 6 and 7 byte types and trims it, so those
# over-wide `Change` values are tolerated rather than broken.
_TOLERATED_CHANGE_WIDTHS = {3: (8, 16), 5: (16,), 6: (16,), 7: (16,)}

# Keys that may sit next to the attribute records of a ConfigureReporting entry.
CR_CLUSTER_KEYS = ("Attributes",)

# Read with no default by prepare_and_send_configure_reporting(), all branches.
CR_REQUIRED_KEYS = ("DataType", "MinInterval", "MaxInterval", "TimeOut")

# uint16 fields, emitted as 4 hex digits.
CR_INTERVAL_KEYS = ("MinInterval", "MaxInterval", "TimeOut")

CR_OPTIONAL_KEYS = ("Change", "ManufSpecific", "ZDeviceID", "Description")

_RE_ID4 = re.compile(r"^[0-9a-f]{4}$")
_RE_HEX = re.compile(r"^[0-9a-fA-F]+$")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def is_canonical_id(value):
    """True for a canonical cluster/attribute id: exactly 4 lowercase hex digits."""
    return isinstance(value, str) and bool(_RE_ID4.match(value))


def _is_hex_string(value):
    return isinstance(value, str) and bool(_RE_HEX.match(value))


def _data_type_int(data_type):
    """`int()` of a DataType, or None when it is not a usable hex string."""
    if not _is_hex_string(data_type):
        return None
    return int(data_type, 16)


def classify_data_type(data_type):
    """Return "analog", "discrete", "composite" or None, as the plugin does."""
    value = _data_type_int(data_type)
    if value is None:
        return None
    if value in ANALOG_DATA_TYPES:
        return "analog"
    if value in DISCRETE_DATA_TYPES:
        return "discrete"
    if value in COMPOSITE_DATA_TYPES:
        return "composite"
    return None


# ---------------------------------------------------------------------------
# ReadAttributes
# ---------------------------------------------------------------------------

def validate_read_attributes(model_def):
    """Validate the `ReadAttributes` block of one device config.

    Args:
        model_def (dict): a parsed `Certified/<Manufacturer>/<Model>.json`.

    Returns:
        list[Issue]: findings, in document order. Empty when the block is
            absent — `ReadAttributes` is optional, the plugin falls back to its
            own per-cluster default lists.
    """
    issues = []

    if "ReadAttributes" not in model_def:
        return issues

    read_attributes = model_def["ReadAttributes"]
    if not isinstance(read_attributes, dict):
        return [Issue(
            "ra-not-a-dict", ERROR, "ReadAttributes",
            "ReadAttributes must be a dict of cluster -> list of attribute ids, got %s" % type(read_attributes).__name__,
        )]

    for cluster, attributes in read_attributes.items():
        where = "ReadAttributes.%s" % cluster

        if not is_canonical_id(cluster):
            issues.append(Issue(
                "ra-cluster-id-malformed", ERROR, where,
                "cluster id %r is not 4 lowercase hex digits; it can never match the device cluster list, so the entry is dead config" % (cluster,),
            ))

        if isinstance(attributes, str):
            issues.append(Issue(
                "ra-attributes-not-a-list", ERROR, where,
                "expected a list of attribute ids, got the string %r; the plugin would iterate it character by character" % (attributes,),
            ))
            continue

        if not isinstance(attributes, list):
            issues.append(Issue(
                "ra-attributes-not-a-list", ERROR, where,
                "expected a list of attribute ids, got %s" % type(attributes).__name__,
            ))
            continue

        issues.extend(_validate_read_attribute_ids(cluster, attributes))

    return issues


def _validate_read_attribute_ids(cluster, attributes):
    issues = []
    seen = set()

    for index, attribute in enumerate(attributes):
        where = "ReadAttributes.%s[%d]" % (cluster, index)

        if not isinstance(attribute, str):
            issues.append(Issue(
                "ra-attribute-not-a-string", ERROR, where,
                "attribute id must be a hex string, got %s (%r); int(attr, 16) would raise" % (type(attribute).__name__, attribute),
            ))
            continue

        if not _is_hex_string(attribute):
            issues.append(Issue(
                "ra-attribute-not-hex", ERROR, where,
                "attribute id %r is not hexadecimal; int(attr, 16) would raise ValueError" % (attribute,),
            ))
            continue

        value = int(attribute, 16)
        if value > 0xFFFF:
            issues.append(Issue(
                "ra-attribute-id-overflow", ERROR, where,
                "attribute id %r parses as 0x%x, which does not fit a 16 bit id and is emitted as a %d digit id in the frame"
                % (attribute, value, len(("%x" % value))),
            ))
        elif len(attribute) != 4:
            # int(attr, 16) still resolves these, so the request is correct.
            issues.append(Issue(
                "ra-attribute-id-width", WARNING, where,
                "attribute id %r is not 4 hex digits; it still resolves to 0x%04x but should be written %04x"
                % (attribute, value, value),
            ))
        elif not is_canonical_id(attribute):
            issues.append(Issue(
                "ra-attribute-id-case", WARNING, where,
                "attribute id %r should be lowercase (%04x) to match the rest of the database" % (attribute, value),
            ))

        if value in seen:
            issues.append(Issue(
                "ra-duplicate-attribute", WARNING, where,
                "attribute 0x%04x is listed more than once for cluster %s" % (value, cluster),
            ))
        seen.add(value)

    return issues


# ---------------------------------------------------------------------------
# ConfigureReporting
# ---------------------------------------------------------------------------

def validate_configure_reporting(model_def):
    """Validate the `ConfigureReporting` block of one device config.

    Args:
        model_def (dict): a parsed `Certified/<Manufacturer>/<Model>.json`.

    Returns:
        list[Issue]: findings, in document order. Empty when the block is
            absent — `ConfigureReporting` is optional, the plugin falls back to
            `CFG_RPT_ATTRIBUTESbyCLUSTERS`.
    """
    issues = []

    if "ConfigureReporting" not in model_def:
        return issues

    configure_reporting = model_def["ConfigureReporting"]
    if not isinstance(configure_reporting, dict):
        return [Issue(
            "cr-not-a-dict", ERROR, "ConfigureReporting",
            "ConfigureReporting must be a dict of cluster -> {\"Attributes\": {...}}, got %s" % type(configure_reporting).__name__,
        )]

    for cluster, cluster_def in configure_reporting.items():
        where = "ConfigureReporting.%s" % cluster

        if not is_canonical_id(cluster):
            issues.append(Issue(
                "cr-cluster-id-malformed", ERROR, where,
                "cluster id %r is not 4 lowercase hex digits; it can never match the device cluster list, so the entry is dead config" % (cluster,),
            ))

        if not isinstance(cluster_def, dict):
            issues.append(Issue(
                "cr-cluster-not-a-dict", ERROR, where,
                "expected {\"Attributes\": {...}}, got %s" % type(cluster_def).__name__,
            ))
            continue

        if not cluster_def:
            issues.append(Issue(
                "cr-empty-cluster", WARNING, where,
                "empty entry: the cluster is skipped for want of an \"Attributes\" key, so the entry has no effect",
            ))
            continue

        stray = [key for key in cluster_def if key not in CR_CLUSTER_KEYS]

        if "Attributes" not in cluster_def:
            issues.append(Issue(
                "cr-missing-attributes-wrapper", ERROR, where,
                "attribute records %s sit directly under the cluster; the plugin tests `if \"Attributes\" not in ...: continue`, "
                "so this cluster is silently skipped. Wrap them in an \"Attributes\" key." % (sorted(stray),),
            ))
            continue

        for key in stray:
            issues.append(Issue(
                "cr-stray-key-beside-attributes", ERROR, "%s.%s" % (where, key),
                "%r sits next to \"Attributes\" instead of inside it; only the records under \"Attributes\" are ever configured" % (key,),
            ))

        attributes = cluster_def["Attributes"]
        if not isinstance(attributes, dict):
            issues.append(Issue(
                "cr-attributes-not-a-dict", ERROR, "%s.Attributes" % where,
                "expected a dict of attribute id -> reporting record, got %s" % type(attributes).__name__,
            ))
            continue

        for attribute, record in attributes.items():
            issues.extend(_validate_reporting_record(cluster, attribute, record))

    return issues


def _validate_reporting_record(cluster, attribute, record):
    issues = []
    where = "ConfigureReporting.%s.Attributes.%s" % (cluster, attribute)

    if not _is_hex_string(attribute):
        issues.append(Issue(
            "cr-attribute-id-malformed", ERROR, where,
            "attribute id %r is not hexadecimal" % (attribute,),
        ))
    elif len(attribute) != 4:
        # The ZiGate path concatenates the id into the frame verbatim, so a
        # width that is not 4 shifts every field that follows.
        issues.append(Issue(
            "cr-attribute-id-malformed", ERROR, where,
            "attribute id %r must be 4 hex digits; it is concatenated as-is into the Configure Reporting frame" % (attribute,),
        ))
    elif not is_canonical_id(attribute):
        issues.append(Issue(
            "cr-attribute-id-case", WARNING, where,
            "attribute id %r should be lowercase (%04x) to match the rest of the database" % (attribute, int(attribute, 16)),
        ))

    if not isinstance(record, dict):
        return issues + [Issue(
            "cr-record-not-a-dict", ERROR, where,
            "expected a reporting record dict, got %s" % type(record).__name__,
        )]

    missing = [key for key in CR_REQUIRED_KEYS if key not in record]
    if missing:
        issues.append(Issue(
            "cr-missing-required-key", ERROR, where,
            "missing %s; prepare_and_send_configure_reporting() reads these with no default, so the KeyError aborts configure "
            "reporting for the whole device" % (", ".join(missing),),
        ))

    kind = classify_data_type(record.get("DataType"))
    if "DataType" in record and kind is None:
        issues.append(Issue(
            "cr-datatype-unknown", ERROR, "%s.DataType" % where,
            "DataType %r classifies as neither analog, discrete nor composite, so the attribute is dropped with "
            "\"Unexpected Data Type\"" % (record.get("DataType"),),
        ))

    if "DataType" in record and not (_is_hex_string(record["DataType"]) and len(record["DataType"]) == 2):
        issues.append(Issue(
            "cr-field-width", ERROR, "%s.DataType" % where,
            "DataType %r must be 2 hex digits; it is concatenated as-is into the frame" % (record["DataType"],),
        ))

    for key in CR_INTERVAL_KEYS:
        if key in record:
            issues.extend(_validate_uint16_field(where, key, record[key]))

    issues.extend(_validate_change(where, record, kind))
    issues.extend(_validate_interval_order(where, record))
    issues.extend(_validate_manuf_specific(where, record))

    if cluster == "0300" and "ZDeviceID" in record and not isinstance(record["ZDeviceID"], list):
        issues.append(Issue(
            "cr-zdeviceid-not-a-list", ERROR, "%s.ZDeviceID" % where,
            "ZDeviceID must be a list of device ids; the plugin tests `ZDeviceID not in record[\"ZDeviceID\"]` and takes its len()",
        ))

    unknown = [key for key in record if key not in CR_REQUIRED_KEYS + CR_OPTIONAL_KEYS]
    for key in unknown:
        issues.append(Issue(
            "cr-unknown-key", WARNING, "%s.%s" % (where, key),
            "%r is not read by Classes/ConfigureReporting.py and has no effect" % (key,),
        ))

    return issues


def _validate_uint16_field(where, key, value):
    if not isinstance(value, str):
        return [Issue(
            "cr-value-not-a-string", ERROR, "%s.%s" % (where, key),
            "%s must be a hex string, got %s (%r); it is concatenated into the frame" % (key, type(value).__name__, value),
        )]
    if not _is_hex_string(value):
        return [Issue(
            "cr-value-not-hex", ERROR, "%s.%s" % (where, key),
            "%s %r is not hexadecimal" % (key, value),
        )]
    if len(value) != 4:
        return [Issue(
            "cr-field-width", ERROR, "%s.%s" % (where, key),
            "%s %r must be 4 hex digits (uint16); it is concatenated as-is into the frame" % (key, value),
        )]
    return []


def _validate_change(where, record, kind):
    """`Change` is required on analog types only, and its width follows the data type."""
    if kind == "analog" and "Change" not in record:
        return [Issue(
            "cr-missing-change", ERROR, where,
            "DataType %r is analog, so prepare_and_send_configure_reporting() reads \"Change\" with no default; the KeyError "
            "aborts configure reporting for the whole device" % (record.get("DataType"),),
        )]

    if "Change" not in record:
        return []

    change = record["Change"]

    if kind != "analog":
        # Discrete and composite records omit rptChg from the frame, so the
        # value is never read -- a broken one is dead weight, not a failure.
        if not _is_hex_string(change):
            return [Issue(
                "cr-change-ignored", WARNING, "%s.Change" % where,
                "Change %r is not a hex string; DataType %r is not analog so the plugin never reads it, but the key should go"
                % (change, record.get("DataType")),
            )]
        return []

    if not isinstance(change, str):
        return [Issue(
            "cr-value-not-a-string", ERROR, "%s.Change" % where,
            "Change must be a hex string, got %s (%r)" % (type(change).__name__, change),
        )]
    if not _is_hex_string(change):
        return [Issue(
            "cr-value-not-hex", ERROR, "%s.Change" % where,
            "Change %r is not hexadecimal" % (change,),
        )]

    size = SIZE_DATA_TYPE.get(_data_type_int(record.get("DataType")))
    if size is None:
        return []

    accepted = (2 * size,) + _TOLERATED_CHANGE_WIDTHS.get(size, ())
    if len(change) not in accepted:
        return [Issue(
            "cr-change-width", ERROR, "%s.Change" % where,
            "Change %r is %d hex digits but DataType %s is %d byte(s), so %d are expected; decode_endian_data() byte-swaps on the "
            "expected width, turning this into a wrong reportable change rather than padding it"
            % (change, len(change), record.get("DataType"), size, 2 * size),
        )]
    return []


def _validate_interval_order(where, record):
    minimum, maximum = record.get("MinInterval"), record.get("MaxInterval")
    if not (_is_hex_string(minimum) and _is_hex_string(maximum)):
        return []

    minimum, maximum = int(minimum, 16), int(maximum, 16)
    # 0x0000 means "no periodic report" and 0xffff disables reporting, so
    # neither is bounded by MinInterval.
    if maximum in (0x0000, 0xFFFF) or minimum <= maximum:
        return []

    return [Issue(
        "cr-interval-order", ERROR, where,
        "MinInterval 0x%04x (%ds) is greater than MaxInterval 0x%04x (%ds); the device answers INVALID_VALUE and configures no "
        "reporting for this attribute" % (minimum, minimum, maximum, maximum),
    )]


def _validate_manuf_specific(where, record):
    if "ManufSpecific" not in record:
        return []

    manuf = record["ManufSpecific"]
    if not is_canonical_id(manuf):
        return [Issue(
            "cr-manufspecific-malformed", ERROR, "%s.ManufSpecific" % where,
            "ManufSpecific %r must be a 4 lowercase hex digit manufacturer code; it is passed to int(manufacturer, 16) and "
            "packed as a uint16" % (manuf,),
        )]
    return []


# ---------------------------------------------------------------------------
# Whole-device entry point
# ---------------------------------------------------------------------------

def validate_device(model_def):
    """Run every structural check over one device config.

    Args:
        model_def (dict): a parsed `Certified/<Manufacturer>/<Model>.json`.

    Returns:
        list[Issue]: every finding, `ReadAttributes` first.
    """
    if not isinstance(model_def, dict):
        return [Issue(
            "device-not-a-dict", ERROR, "<root>",
            "a device configuration must be a JSON object, got %s" % type(model_def).__name__,
        )]

    return validate_read_attributes(model_def) + validate_configure_reporting(model_def)


def filter_by_severity(issues, severity):
    return [issue for issue in issues if issue.severity == severity]


# ---------------------------------------------------------------------------
# Certified database access
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
CERTIFIED_ROOT = REPO_ROOT / "z4d_certified_devices" / "Certified"
BASELINE_PATH = Path(__file__).resolve().parent / "certified_baseline.json"


def iter_device_files(certified_root=None):
    """Every certified device JSON, sorted, as `<Manufacturer>/<Model>.json` paths."""
    root = Path(certified_root) if certified_root else CERTIFIED_ROOT
    return sorted(root.glob("*/*.json"))


def device_id(path, certified_root=None):
    """`<Manufacturer>/<Model>.json`, the key used by the baseline and test ids."""
    root = Path(certified_root) if certified_root else CERTIFIED_ROOT
    return Path(path).resolve().relative_to(root.resolve()).as_posix()


def load_device(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Baseline
#
# The certified database predates these checks and still carries known
# violations, several of which have a fix in flight. The baseline records them
# so the suite is green on `main` while still failing on anything *new*: a
# device added or edited from now on has to be clean.
#
# Refresh it with `python tests/certified_schema.py --update-baseline` once a
# batch of fixes lands, and the entries disappear.
# ---------------------------------------------------------------------------

def load_baseline(baseline_path=None):
    """Known pre-existing violations: `{"<Manufacturer>/<Model>.json": ["<code> <location>", ...]}`."""
    path = Path(baseline_path) if baseline_path else BASELINE_PATH
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle).get("known_issues", {})


def collect_all_issues(certified_root=None):
    """Validate the whole certified database.

    Returns:
        dict: `{"<Manufacturer>/<Model>.json": [Issue, ...]}`, files without a
            finding omitted.
    """
    found = {}
    for path in iter_device_files(certified_root):
        issues = validate_device(load_device(path))
        if issues:
            found[device_id(path, certified_root)] = issues
    return found


def new_issues(issues, baselined):
    """The issues of `issues` that `baselined` (a list of keys) does not cover."""
    known = set(baselined or ())
    return [issue for issue in issues if _issue_key(issue) not in known]


def stale_baseline_entries(issues, baselined):
    """Baseline keys that no longer match a finding, i.e. fixed in the meantime."""
    present = {_issue_key(issue) for issue in issues}
    return sorted(key for key in (baselined or ()) if key not in present)


def format_issue(device, issue):
    return "%s: [%s] %s -- %s" % (device, issue.severity, _issue_key(issue), issue.message)


def unbaselined_issues(issues_by_device, baseline, code_prefix=None, severity=None):
    """Findings that the baseline does not already record.

    Args:
        issues_by_device (dict): `{device: [Issue, ...]}`, as `collect_all_issues()`.
        baseline (dict): `{device: ["<code> <location>", ...]}`, as `load_baseline()`.
        code_prefix (str): keep only codes starting with this, e.g. `"ra-"`.
        severity (str): keep only this severity.

    Returns:
        dict: `{device: [Issue, ...]}`, devices without a remaining finding omitted.
    """
    remaining = {}
    for device, issues in sorted(issues_by_device.items()):
        selected = new_issues(issues, baseline.get(device))
        if code_prefix:
            selected = [issue for issue in selected if issue.code.startswith(code_prefix)]
        if severity:
            selected = [issue for issue in selected if issue.severity == severity]
        if selected:
            remaining[device] = selected
    return remaining


def format_report(found, hint=None):
    """Render `{device: [Issue, ...]}` as a multi-line assertion message."""
    lines = []
    for device, issues in sorted(found.items()):
        for issue in issues:
            lines.append("  " + format_issue(device, issue))
    total = sum(len(issues) for issues in found.values())
    header = "%d issue(s) in %d device config(s):" % (total, len(found))
    footer = ("\n\n" + hint) if hint else ""
    return "%s\n%s%s" % (header, "\n".join(lines), footer)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_baseline(found):
    return {
        "_comment": (
            "Known structural violations of the certified database, recorded so the schema tests fail only on NEW ones. "
            "Regenerate with `python tests/certified_schema.py --update-baseline`. Entries disappear as the files are fixed."
        ),
        "known_issues": {
            device: sorted(_issue_key(issue) for issue in issues)
            for device, issues in sorted(found.items())
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate the ReadAttributes / ConfigureReporting structure of the certified database.")
    parser.add_argument("--report", action="store_true", help="list every finding (default action)")
    parser.add_argument("--severity", choices=SEVERITIES, help="restrict the report to one severity")
    parser.add_argument("--new-only", action="store_true", help="report only findings the baseline does not cover")
    parser.add_argument("--update-baseline", action="store_true", help="rewrite tests/certified_baseline.json from the current state")
    args = parser.parse_args(argv)

    found = collect_all_issues()

    if args.update_baseline:
        with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
            json.dump(_build_baseline(found), handle, indent=2, sort_keys=False)
            handle.write("\n")
        total = sum(len(issues) for issues in found.values())
        print("Wrote %s: %d issue(s) across %d file(s)." % (BASELINE_PATH.name, total, len(found)))
        return 0

    baseline = load_baseline()
    counts = dict.fromkeys(SEVERITIES, 0)
    reported = 0

    for device, issues in sorted(found.items()):
        if args.new_only:
            issues = new_issues(issues, baseline.get(device))
        for issue in issues:
            counts[issue.severity] += 1
            if args.severity and issue.severity != args.severity:
                continue
            print(format_issue(device, issue))
            reported += 1

    print("\n%d file(s) scanned, %d error(s), %d warning(s)%s."
          % (len(iter_device_files()), counts[ERROR], counts[WARNING], " not covered by the baseline" if args.new_only else ""))
    return 1 if reported else 0


if __name__ == "__main__":
    sys.exit(main())
