#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: GPL-3.0
#
"""Tests for the top-level `ZDeviceID` / `ProfileID` keys of a certified device configuration.

What the keys mean, and why their spelling matters, is documented in
`tests/certified_schema.py` ("Device identity").
"""

import pytest

import certified_schema
from certified_schema import ERROR, validate_identity

BASELINE_HINT = (
    "These are new findings, not pre-existing ones.\n"
    "Fix the device config, or -- if the finding is wrong -- fix the rule in tests/certified_schema.py.\n"
    "Review the full picture with `python tests/certified_schema.py --report`."
)


class TestValidateIdentity:
    def test_absent_keys_are_fine(self):
        assert validate_identity({}) == []

    @pytest.mark.parametrize("model_def", [
        {"ZDeviceID": "0202"},
        {"ProfileID": "c05e", "ZDeviceID": "0830"},
    ])
    def test_canonical_ids_are_fine(self, model_def):
        assert validate_identity(model_def) == []

    @pytest.mark.parametrize("value", ["202", "0x0202", "C05E", "02020", "", 514, None, "zzzz"])
    @pytest.mark.parametrize("key", certified_schema.IDENTITY_KEYS)
    def test_malformed_id_is_an_error(self, key, value):
        issues = validate_identity({key: value})
        assert len(issues) == 1
        assert issues[0].code == "id-malformed"
        assert issues[0].severity == ERROR
        assert issues[0].location == key

    def test_both_keys_are_reported(self):
        issues = validate_identity({"ProfileID": "104", "ZDeviceID": "C412"})
        assert [issue.location for issue in issues] == ["ZDeviceID", "ProfileID"]

    def test_validate_device_includes_identity(self):
        assert [issue.code for issue in certified_schema.validate_device({"ZDeviceID": "C412"})] == ["id-malformed"]


# ---------------------------------------------------------------------------
# The real certified database
# ---------------------------------------------------------------------------

class TestCertifiedIdentity:
    def test_no_new_errors(self, issues_by_device, baseline):
        found = certified_schema.unbaselined_issues(issues_by_device, baseline, code_prefix="id-", severity=ERROR)
        assert not found, certified_schema.format_report(found, BASELINE_HINT)
