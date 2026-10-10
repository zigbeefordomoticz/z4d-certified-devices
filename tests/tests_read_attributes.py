#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: GPL-3.0
#
"""Tests for the `ReadAttributes` block of a certified device configuration.

Two layers:

* unit tests of `certified_schema.validate_read_attributes()` against synthetic
  configs — one per rule, so a rule change shows up as a failing rule rather
  than as noise over the whole database;
* a database-wide test asserting the real `Certified/**/*.json` tree introduces
  no finding beyond those recorded in `tests/certified_baseline.json`.

What the block has to look like, and why, is documented in
`tests/certified_schema.py`.
"""

import pytest

import certified_schema
from certified_schema import ERROR, WARNING, validate_read_attributes

BASELINE_HINT = (
    "These are new findings, not pre-existing ones.\n"
    "Fix the device config, or -- if the finding is wrong -- fix the rule in tests/certified_schema.py.\n"
    "Review the full picture with `python tests/certified_schema.py --report`."
)


def codes(issues):
    return [issue.code for issue in issues]


def one(issues):
    """The single expected finding, with a readable failure when there are several."""
    assert len(issues) == 1, "expected exactly one finding, got %s" % (codes(issues),)
    return issues[0]


# ---------------------------------------------------------------------------
# Accepted shapes
# ---------------------------------------------------------------------------

class TestValidReadAttributes:
    def test_canonical_block_is_clean(self):
        model_def = {"ReadAttributes": {
            "0000": ["0004", "0005", "0007"],
            "0b04": ["0505", "0508", "050b"],
        }}
        assert validate_read_attributes(model_def) == []

    def test_absent_block_is_clean(self):
        # ReadAttributes is optional: the plugin falls back to its default lists.
        assert validate_read_attributes({"Ep": {}, "Type": ""}) == []

    def test_empty_block_is_clean(self):
        assert validate_read_attributes({"ReadAttributes": {}}) == []

    def test_empty_attribute_list_is_clean(self):
        # An empty list is a deliberate way to suppress the plugin's default
        # reads for that cluster: retreive_attributes_based_on_configuration()
        # returns [] and the caller stops at "is not None".
        assert validate_read_attributes({"ReadAttributes": {"0000": []}}) == []

    def test_manufacturer_specific_cluster_is_clean(self):
        assert validate_read_attributes({"ReadAttributes": {"fc01": ["0000"]}}) == []


# ---------------------------------------------------------------------------
# Cluster level
# ---------------------------------------------------------------------------

class TestReadAttributesClusterKeys:
    def test_block_must_be_a_dict(self):
        issue = one(validate_read_attributes({"ReadAttributes": ["0000"]}))
        assert issue.code == "ra-not-a-dict"
        assert issue.severity == ERROR

    @pytest.mark.parametrize("cluster", ["000", "00000", "0b4"])
    def test_cluster_id_width_is_an_error(self, cluster):
        # The key is matched against the device's cluster list, which is always
        # 4 lowercase hex digits -- any other width never matches at all.
        issue = one(validate_read_attributes({"ReadAttributes": {cluster: ["0000"]}}))
        assert issue.code == "ra-cluster-id-malformed"
        assert issue.severity == ERROR

    def test_uppercase_cluster_id_is_an_error(self):
        issue = one(validate_read_attributes({"ReadAttributes": {"0B04": ["0505"]}}))
        assert issue.code == "ra-cluster-id-malformed"
        assert issue.severity == ERROR

    def test_non_hex_cluster_id_is_an_error(self):
        issue = one(validate_read_attributes({"ReadAttributes": {"Type": ["0000"]}}))
        assert issue.code == "ra-cluster-id-malformed"

    def test_attribute_list_must_be_a_list(self):
        issue = one(validate_read_attributes({"ReadAttributes": {"0000": {"0004": None}}}))
        assert issue.code == "ra-attributes-not-a-list"
        assert issue.severity == ERROR

    def test_a_string_instead_of_a_list_is_an_error(self):
        # The plugin would iterate the string character by character and build
        # one bogus attribute id per character.
        issue = one(validate_read_attributes({"ReadAttributes": {"0000": "0004"}}))
        assert issue.code == "ra-attributes-not-a-list"
        assert "character by character" in issue.message

    def test_every_cluster_is_reported(self):
        model_def = {"ReadAttributes": {"0000": "0004", "000": ["0004"]}}
        assert sorted(codes(validate_read_attributes(model_def))) == [
            "ra-attributes-not-a-list", "ra-cluster-id-malformed",
        ]


# ---------------------------------------------------------------------------
# Attribute level
# ---------------------------------------------------------------------------

class TestReadAttributesAttributeIds:
    def test_attribute_must_be_a_string(self):
        issue = one(validate_read_attributes({"ReadAttributes": {"0000": [4]}}))
        assert issue.code == "ra-attribute-not-a-string"
        assert issue.severity == ERROR

    def test_non_hex_attribute_is_an_error(self):
        issue = one(validate_read_attributes({"ReadAttributes": {"0000": ["zzzz"]}}))
        assert issue.code == "ra-attribute-not-hex"
        assert issue.severity == ERROR

    @pytest.mark.parametrize("attribute", ["004", "00005"])
    def test_width_typo_that_keeps_the_value_is_a_warning(self, attribute):
        # int(attr, 16) still resolves these, so the request on the wire is right.
        issue = one(validate_read_attributes({"ReadAttributes": {"0000": [attribute]}}))
        assert issue.code == "ra-attribute-id-width"
        assert issue.severity == WARNING

    def test_uppercase_attribute_is_a_warning(self):
        issue = one(validate_read_attributes({"ReadAttributes": {"0b04": ["050F"]}}))
        assert issue.code == "ra-attribute-id-case"
        assert issue.severity == WARNING

    def test_width_typo_that_changes_the_value_is_an_error(self):
        # The real case: a lost ", " between "4000" and "4001" produced "40001",
        # which int() reads as 0x40001 and the frame carries as a 5 digit id.
        issue = one(validate_read_attributes({"ReadAttributes": {"0300": ["40001"]}}))
        assert issue.code == "ra-attribute-id-overflow"
        assert issue.severity == ERROR

    def test_duplicate_attribute_is_a_warning(self):
        issue = one(validate_read_attributes({"ReadAttributes": {"0000": ["0004", "0004"]}}))
        assert issue.code == "ra-duplicate-attribute"
        assert issue.severity == WARNING

    def test_duplicates_are_matched_on_value_not_spelling(self):
        issues = validate_read_attributes({"ReadAttributes": {"0000": ["0004", "004"]}})
        assert sorted(codes(issues)) == ["ra-attribute-id-width", "ra-duplicate-attribute"]

    def test_location_points_at_the_offending_index(self):
        issue = one(validate_read_attributes({"ReadAttributes": {"0000": ["0004", "0005", "zzzz"]}}))
        assert issue.location == "ReadAttributes.0000[2]"


# ---------------------------------------------------------------------------
# The real certified database
# ---------------------------------------------------------------------------

class TestCertifiedReadAttributes:
    def test_no_new_errors(self, issues_by_device, baseline):
        found = certified_schema.unbaselined_issues(issues_by_device, baseline, code_prefix="ra-", severity=ERROR)
        assert not found, certified_schema.format_report(found, BASELINE_HINT)

    def test_no_new_warnings(self, issues_by_device, baseline):
        found = certified_schema.unbaselined_issues(issues_by_device, baseline, code_prefix="ra-", severity=WARNING)
        assert not found, certified_schema.format_report(found, BASELINE_HINT)

    def test_every_cluster_key_is_a_canonical_id(self, certified_devices):
        """Guard the one rule that silently kills a whole entry, across the database."""
        offenders = [
            "%s: ReadAttributes.%s" % (device, cluster)
            for device, model_def in sorted(certified_devices.items())
            for cluster in (model_def.get("ReadAttributes") or {})
            if not certified_schema.is_canonical_id(cluster)
        ]
        assert not offenders, "cluster ids must be 4 lowercase hex digits:\n  " + "\n  ".join(offenders)
