#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: GPL-3.0
#
"""Tests for the `ConfigureReporting` block of a certified device configuration.

`ConfigureReporting` is the least forgiving block in a certified config. Its
records are read with no defaults and concatenated straight into the ZCL
Configure Reporting frame, so a structural mistake has one of three outcomes,
none of which this repository notices on its own:

* the cluster is **silently skipped** (no `"Attributes"` wrapper);
* configure reporting is **aborted for the whole device** (`KeyError` on a
  missing `DataType` / `MinInterval` / `MaxInterval` / `TimeOut`, or on
  `Change` for an analog type);
* a **malformed frame** goes out (wrong field width).

Two layers, as in `tests_read_attributes.py`: unit tests of
`certified_schema.validate_configure_reporting()` per rule, then a
database-wide test against `tests/certified_baseline.json`.
"""

import pytest

import certified_schema
from certified_schema import ERROR, WARNING, classify_data_type, validate_configure_reporting

BASELINE_HINT = (
    "These are new findings, not pre-existing ones.\n"
    "Fix the device config, or -- if the finding is wrong -- fix the rule in tests/certified_schema.py.\n"
    "Review the full picture with `python tests/certified_schema.py --report`."
)


REMOVED = object()
"""Sentinel for `record(TimeOut=REMOVED)`, to drop a key rather than blank it."""


def record(**overrides):
    """A valid analog reporting record (uint16 / 2 bytes), with overrides applied."""
    base = {"DataType": "21", "MinInterval": "0001", "MaxInterval": "012c", "TimeOut": "0000", "Change": "0001"}
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not REMOVED}


def block(cluster="0001", attribute="0021", **overrides):
    return {"ConfigureReporting": {cluster: {"Attributes": {attribute: record(**overrides)}}}}


def codes(issues):
    return [issue.code for issue in issues]


def one(issues):
    assert len(issues) == 1, "expected exactly one finding, got %s" % (codes(issues),)
    return issues[0]


# ---------------------------------------------------------------------------
# Accepted shapes
# ---------------------------------------------------------------------------

class TestValidConfigureReporting:
    def test_canonical_block_is_clean(self):
        assert validate_configure_reporting(block()) == []

    def test_absent_block_is_clean(self):
        # Optional: the plugin falls back to CFG_RPT_ATTRIBUTESbyCLUSTERS.
        assert validate_configure_reporting({"Ep": {}, "Type": ""}) == []

    def test_empty_block_is_clean(self):
        assert validate_configure_reporting({"ConfigureReporting": {}}) == []

    def test_discrete_type_needs_no_change(self):
        # prepare_and_send_configure_reporting() reads "Change" on the analog
        # branch only, and the discrete record omits rptChg from the frame.
        model_def = {"ConfigureReporting": {"0006": {"Attributes": {"0000": {
            "DataType": "10", "MinInterval": "0001", "MaxInterval": "012c", "TimeOut": "0000",
        }}}}}
        assert validate_configure_reporting(model_def) == []

    def test_change_on_a_discrete_type_is_tolerated(self):
        # Widespread in the database and genuinely ignored by the plugin.
        model_def = {"ConfigureReporting": {"0006": {"Attributes": {"0000": {
            "DataType": "10", "MinInterval": "0001", "MaxInterval": "012c", "TimeOut": "0000", "Change": "01",
        }}}}}
        assert validate_configure_reporting(model_def) == []

    def test_manufacturer_specific_record_is_clean(self):
        assert validate_configure_reporting(block(ManufSpecific="117c")) == []

    def test_several_attributes_per_cluster_are_clean(self):
        model_def = {"ConfigureReporting": {"0702": {"Attributes": {
            "0000": record(DataType="25", Change="000000000005"),
            "0400": record(DataType="2a", Change="000005"),
        }}}}
        assert validate_configure_reporting(model_def) == []


# ---------------------------------------------------------------------------
# The "Attributes" wrapper -- the silent killer
# ---------------------------------------------------------------------------

class TestAttributesWrapper:
    def test_flat_shape_is_an_error(self):
        # {"0001": {"0021": {...}}} parses, lints, and is silently skipped by
        # `if "Attributes" not in cfgrpt_configuration[cluster]: continue`.
        model_def = {"ConfigureReporting": {"0001": {"0021": record()}}}
        issue = one(validate_configure_reporting(model_def))
        assert issue.code == "cr-missing-attributes-wrapper"
        assert issue.severity == ERROR
        assert issue.location == "ConfigureReporting.0001"

    def test_flat_shape_names_the_stranded_records(self):
        model_def = {"ConfigureReporting": {"0001": {"0021": record(), "0020": record()}}}
        assert "'0020', '0021'" in one(validate_configure_reporting(model_def)).message

    def test_record_beside_the_wrapper_is_an_error(self):
        # The Owon/AC221 shape: one record inside "Attributes", a sibling outside.
        model_def = {"ConfigureReporting": {"0204": {
            "Attributes": {"0000": record()},
            "0001": record(),
        }}}
        issue = one(validate_configure_reporting(model_def))
        assert issue.code == "cr-stray-key-beside-attributes"
        assert issue.severity == ERROR
        assert issue.location == "ConfigureReporting.0204.0001"

    def test_wrapped_records_are_still_validated_when_a_sibling_is_stray(self):
        model_def = {"ConfigureReporting": {"0204": {
            "Attributes": {"0000": record(TimeOut=REMOVED)},
            "0001": record(),
        }}}
        assert sorted(codes(validate_configure_reporting(model_def))) == [
            "cr-missing-required-key", "cr-stray-key-beside-attributes",
        ]

    def test_empty_cluster_entry_is_a_warning(self):
        # Skipped like the flat shape, but with nothing stranded: dead weight
        # rather than a lost feature.
        issue = one(validate_configure_reporting({"ConfigureReporting": {"ff66": {}}}))
        assert issue.code == "cr-empty-cluster"
        assert issue.severity == WARNING

    def test_attributes_must_be_a_dict(self):
        model_def = {"ConfigureReporting": {"0001": {"Attributes": ["0021"]}}}
        issue = one(validate_configure_reporting(model_def))
        assert issue.code == "cr-attributes-not-a-dict"
        assert issue.severity == ERROR


# ---------------------------------------------------------------------------
# Cluster / attribute ids
# ---------------------------------------------------------------------------

class TestConfigureReportingIds:
    def test_block_must_be_a_dict(self):
        issue = one(validate_configure_reporting({"ConfigureReporting": []}))
        assert issue.code == "cr-not-a-dict"
        assert issue.severity == ERROR

    @pytest.mark.parametrize("cluster", ["001", "00001", "0B04", "nope"])
    def test_malformed_cluster_id_is_an_error(self, cluster):
        model_def = {"ConfigureReporting": {cluster: {"Attributes": {"0021": record()}}}}
        issue = one(validate_configure_reporting(model_def))
        assert issue.code == "cr-cluster-id-malformed"
        assert issue.severity == ERROR

    def test_cluster_entry_must_be_a_dict(self):
        model_def = {"ConfigureReporting": {"0001": ["0021"]}}
        issue = one(validate_configure_reporting(model_def))
        assert issue.code == "cr-cluster-not-a-dict"

    @pytest.mark.parametrize("attribute", ["021", "00021", "nope"])
    def test_malformed_attribute_id_is_an_error(self, attribute):
        # Concatenated into the frame as-is by the ZiGate path, so a wrong
        # width shifts every field that follows it.
        issue = one(validate_configure_reporting(block(attribute=attribute)))
        assert issue.code == "cr-attribute-id-malformed"
        assert issue.severity == ERROR

    def test_uppercase_attribute_id_is_a_warning(self):
        issue = one(validate_configure_reporting(block(cluster="0b04", attribute="050F")))
        assert issue.code == "cr-attribute-id-case"
        assert issue.severity == WARNING

    def test_record_must_be_a_dict(self):
        model_def = {"ConfigureReporting": {"0001": {"Attributes": {"0021": "0001"}}}}
        issue = one(validate_configure_reporting(model_def))
        assert issue.code == "cr-record-not-a-dict"


# ---------------------------------------------------------------------------
# Required keys
# ---------------------------------------------------------------------------

class TestRequiredKeys:
    @pytest.mark.parametrize("key", ["DataType", "MinInterval", "MaxInterval", "TimeOut"])
    def test_missing_key_is_an_error(self, key):
        # Read with no default, in all three branches: the KeyError propagates
        # out of prepare_and_send_configure_reporting() and no call site wraps
        # it, so the device gets no configure reporting at all.
        issues = validate_configure_reporting(block(**{key: REMOVED}))
        assert "cr-missing-required-key" in codes(issues)
        assert [issue for issue in issues if issue.code == "cr-missing-required-key"][0].severity == ERROR

    def test_missing_key_is_named_in_the_message(self):
        issue = one(validate_configure_reporting(block(TimeOut=REMOVED)))
        assert "missing TimeOut" in issue.message

    def test_several_missing_keys_are_reported_together(self):
        issues = validate_configure_reporting(block(TimeOut=REMOVED, MaxInterval=REMOVED))
        assert codes(issues) == ["cr-missing-required-key"]
        assert "MaxInterval, TimeOut" in issues[0].message

    def test_analog_type_without_change_is_an_error(self):
        issue = one(validate_configure_reporting(block(DataType="21", Change=REMOVED)))
        assert issue.code == "cr-missing-change"
        assert issue.severity == ERROR

    def test_unknown_key_is_a_warning(self):
        issue = one(validate_configure_reporting(block(Flavour="vanilla")))
        assert issue.code == "cr-unknown-key"
        assert issue.severity == WARNING


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class TestDataType:
    @pytest.mark.parametrize("data_type,kind", [
        ("20", "analog"), ("21", "analog"), ("23", "analog"), ("25", "analog"),
        ("29", "analog"), ("2a", "analog"), ("2b", "analog"), ("39", "analog"),
        ("10", "discrete"), ("18", "discrete"), ("19", "discrete"),
        ("30", "discrete"), ("31", "discrete"),
        ("42", "composite"),
        ("07", None), ("32", None), ("ff", None),
    ])
    def test_classification_matches_the_plugin(self, data_type, kind):
        assert classify_data_type(data_type) == kind

    def test_unknown_data_type_is_an_error(self):
        # Dropped by prepare_and_send_configure_reporting() with
        # "Unexpected Data Type", so the attribute is never configured.
        issues = validate_configure_reporting(block(DataType="32"))
        assert "cr-datatype-unknown" in codes(issues)

    def test_data_type_width_is_an_error(self):
        issues = validate_configure_reporting(block(DataType="0021"))
        assert "cr-field-width" in codes(issues)


# ---------------------------------------------------------------------------
# Field widths and values
# ---------------------------------------------------------------------------

class TestFieldWidths:
    @pytest.mark.parametrize("key", ["MinInterval", "MaxInterval", "TimeOut"])
    def test_interval_must_be_four_hex_digits(self, key):
        issue = one(validate_configure_reporting(block(**{key: "01"})))
        assert issue.code == "cr-field-width"
        assert issue.location.endswith(key)

    @pytest.mark.parametrize("key", ["MinInterval", "MaxInterval", "TimeOut", "Change"])
    def test_non_string_value_is_an_error(self, key):
        # `"Change": {}` on an analog type would be concatenated onto a str.
        issue = one(validate_configure_reporting(block(**{key: {}})))
        assert issue.code == "cr-value-not-a-string"
        assert issue.severity == ERROR

    @pytest.mark.parametrize("key", ["MinInterval", "MaxInterval", "TimeOut", "Change"])
    def test_non_hex_value_is_an_error(self, key):
        issue = one(validate_configure_reporting(block(**{key: ""})))
        assert issue.code == "cr-value-not-hex"

    @pytest.mark.parametrize("data_type", ["10", "30", "42"])
    def test_broken_change_on_a_non_analog_type_is_only_a_warning(self, data_type):
        # rptChg is omitted from the frame for discrete and composite records,
        # so `"Change": {}` there is dead weight rather than a bad payload.
        issue = one(validate_configure_reporting(block(DataType=data_type, Change={})))
        assert issue.code == "cr-change-ignored"
        assert issue.severity == WARNING

    @pytest.mark.parametrize("data_type,change,expected_digits", [
        ("20", "0001", 2),    # uint8  -- 1 byte
        ("21", "01", 4),      # uint16 -- 2 bytes
        ("23", "01", 8),      # uint32 -- 4 bytes
        ("2b", "0001", 8),    # int32  -- 4 bytes
        ("39", "0001", 8),    # float  -- 4 bytes
    ])
    def test_change_width_must_match_the_data_type(self, data_type, change, expected_digits):
        # decode_endian_data() byte-swaps on the *expected* width rather than
        # padding, so "0001" on a 4 byte type becomes 0x01000000.
        issue = one(validate_configure_reporting(block(DataType=data_type, Change=change)))
        assert issue.code == "cr-change-width"
        assert issue.severity == ERROR
        assert "so %d are expected" % expected_digits in issue.message

    @pytest.mark.parametrize("data_type,change", [
        ("25", "000000000005"),          # uint48, exact 6 bytes
        ("25", "000000000000000a"),      # uint48 written as 8 bytes -- trimmed
        ("2a", "000005"),                # int24, exact 3 bytes
        ("2a", "0000000a"),              # int24 written as 4 bytes -- trimmed
    ])
    def test_widths_decode_endian_data_trims_are_accepted(self, data_type, change):
        assert validate_configure_reporting(block(DataType=data_type, Change=change)) == []

    def test_change_width_is_not_checked_on_discrete_types(self):
        model_def = {"ConfigureReporting": {"0006": {"Attributes": {"0000": {
            "DataType": "19", "MinInterval": "0001", "MaxInterval": "012c", "TimeOut": "0000", "Change": "01",
        }}}}}
        assert validate_configure_reporting(model_def) == []

    def test_malformed_manufspecific_is_an_error(self):
        issue = one(validate_configure_reporting(block(ManufSpecific="117")))
        assert issue.code == "cr-manufspecific-malformed"
        assert issue.severity == ERROR


# ---------------------------------------------------------------------------
# Interval semantics
# ---------------------------------------------------------------------------

class TestIntervals:
    def test_min_greater_than_max_is_an_error(self):
        # The device answers INVALID_VALUE and configures nothing.
        issue = one(validate_configure_reporting(block(MinInterval="0258", MaxInterval="012c")))
        assert issue.code == "cr-interval-order"
        assert issue.severity == ERROR

    def test_equal_intervals_are_accepted(self):
        assert validate_configure_reporting(block(MinInterval="012c", MaxInterval="012c")) == []

    def test_max_interval_zero_is_accepted(self):
        # 0x0000 means "no periodic report", so MinInterval does not bound it.
        assert validate_configure_reporting(block(MinInterval="0258", MaxInterval="0000")) == []

    def test_max_interval_ffff_is_accepted(self):
        # 0xffff switches reporting off for the attribute.
        assert validate_configure_reporting(block(MinInterval="0258", MaxInterval="ffff")) == []


# ---------------------------------------------------------------------------
# The real certified database
# ---------------------------------------------------------------------------

class TestCertifiedConfigureReporting:
    def test_no_new_errors(self, issues_by_device, baseline):
        found = certified_schema.unbaselined_issues(issues_by_device, baseline, code_prefix="cr-", severity=ERROR)
        assert not found, certified_schema.format_report(found, BASELINE_HINT)

    def test_no_new_warnings(self, issues_by_device, baseline):
        found = certified_schema.unbaselined_issues(issues_by_device, baseline, code_prefix="cr-", severity=WARNING)
        assert not found, certified_schema.format_report(found, BASELINE_HINT)

    def test_every_cluster_key_is_a_canonical_id(self, certified_devices):
        """A hard invariant, deliberately not baseline-aware: a non-canonical cluster id is dead config."""
        offenders = [
            "%s: ConfigureReporting.%s" % (device, cluster)
            for device, model_def in sorted(certified_devices.items())
            for cluster in (model_def.get("ConfigureReporting") or {})
            if not certified_schema.is_canonical_id(cluster)
        ]
        assert not offenders, "cluster ids must be 4 lowercase hex digits:\n  " + "\n  ".join(offenders)

    def test_every_data_type_is_one_the_plugin_knows(self, certified_devices):
        """A hard invariant: an unclassifiable DataType drops the attribute at pairing time."""
        offenders = []
        for device, model_def in sorted(certified_devices.items()):
            for cluster, cluster_def in (model_def.get("ConfigureReporting") or {}).items():
                if not isinstance(cluster_def, dict) or not isinstance(cluster_def.get("Attributes"), dict):
                    continue
                for attribute, cfg in cluster_def["Attributes"].items():
                    if isinstance(cfg, dict) and classify_data_type(cfg.get("DataType")) is None:
                        offenders.append("%s: ConfigureReporting.%s.Attributes.%s has DataType %r"
                                         % (device, cluster, attribute, cfg.get("DataType")))
        assert not offenders, "DataType must classify as analog, discrete or composite:\n  " + "\n  ".join(offenders)
