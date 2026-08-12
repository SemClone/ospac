"""
Tests for input validation utilities.
"""

import pytest
from pathlib import Path

from ospac.utils.validation import validate_license_id, validate_license_path


class TestValidateLicenseId:
    """Tests for validate_license_id function."""

    def test_valid_license_ids(self):
        """Test that valid SPDX license IDs pass validation."""
        valid_ids = [
            "MIT",
            "GPL-3.0",
            "Apache-2.0",
            "BSD-3-Clause",
            "LGPL-2.1",
            "MPL-2.0",
            "ISC",
            "CC-BY-4.0",
            "Artistic-2.0",
            "EPL-1.0",
            "BSD-2-Clause-Patent",
            "Python-2.0.1",
            "GPL-3.0+",
            "LGPL-2.1+",
        ]

        for license_id in valid_ids:
            # Should not raise any exception
            result = validate_license_id(license_id)
            assert result == license_id

    def test_path_traversal_attempts(self):
        """Test that path traversal attempts are rejected."""
        malicious_ids = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "../LICENSE",
            "../../secrets.json",
            "licenses/../../../etc/passwd",
            "..",
            ".",
            "./MIT",
            "../MIT",
        ]

        for malicious_id in malicious_ids:
            with pytest.raises(ValueError, match="Invalid license ID format|cannot contain path separators"):
                validate_license_id(malicious_id)

    def test_invalid_characters(self):
        """Test that license IDs with invalid characters are rejected."""
        invalid_ids = [
            "MIT; rm -rf /",
            "GPL-3.0 && malicious_command",
            "MIT|GPL",
            "MIT<script>",
            "MIT\x00",
            "MIT\n",
            "MIT\r",
            "MIT\t",
            "MIT;DROP TABLE licenses;",
            "MIT OR GPL",  # space is invalid
            "MIT/GPL",     # forward slash
            "MIT\\GPL",    # backslash
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(ValueError, match="Invalid license ID format|cannot contain path separators"):
                validate_license_id(invalid_id)

    def test_empty_license_id(self):
        """Test handling of empty license ID."""
        with pytest.raises(ValueError, match="License ID cannot be empty"):
            validate_license_id("")

        # Test with allow_empty=True
        result = validate_license_id("", allow_empty=True)
        assert result == ""

    def test_special_valid_characters(self):
        """Test that dots, hyphens, and plus signs are allowed."""
        valid_special = [
            "GPL-3.0+",
            "Python-2.0.1",
            "CC-BY-SA-4.0",
            "AGPL-3.0-or-later",
            "CDDL-1.0+",
        ]

        for license_id in valid_special:
            result = validate_license_id(license_id)
            assert result == license_id


class TestValidateLicensePath:
    """Tests for validate_license_path function."""

    def test_valid_path_within_base(self, tmp_path):
        """Test that valid paths within base directory are accepted."""
        base_dir = tmp_path / "licenses"
        base_dir.mkdir()

        # Create a test file
        test_file = base_dir / "MIT.json"
        test_file.write_text('{"license": "MIT"}')

        # Validate path
        result = validate_license_path("MIT", base_dir, "MIT.json")
        assert result == test_file.resolve()

    def test_path_traversal_blocked(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        base_dir = tmp_path / "licenses"
        base_dir.mkdir()

        # Create a file outside the base directory for testing path traversal protection
        # Note: This is test data for security validation, not actual sensitive data
        outside_dir = tmp_path / "private"
        outside_dir.mkdir()
        private_file = outside_dir / "private.json"
        private_file.write_text('{"data": "sensitive"}')

        # Attempt path traversal
        with pytest.raises(ValueError, match="Security violation|outside"):
            validate_license_path("../private/private", base_dir, "../private/private.json")

    def test_symlink_escape_blocked(self, tmp_path):
        """Test that symlink-based escapes are blocked."""
        base_dir = tmp_path / "licenses"
        base_dir.mkdir()

        # Create a directory outside base
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        target_file = outside_dir / "target.json"
        target_file.write_text('{"data": "sensitive"}')

        # Create a symlink inside base_dir pointing outside
        symlink = base_dir / "escape.json"
        try:
            symlink.symlink_to(target_file)

            # This should fail because resolved path is outside base_dir
            with pytest.raises(ValueError, match="Security violation|outside"):
                validate_license_path("escape", base_dir, "escape.json")
        except OSError:
            # Symlinks might not be supported on some systems
            pytest.skip("Symlinks not supported on this system")


class TestIntegrationSecurity:
    """Integration tests for security fixes."""

    def test_lookup_license_data_path_traversal(self):
        """Test that PolicyRuntime.lookup_license_data blocks path traversal."""
        from ospac.runtime.engine import PolicyRuntime

        runtime = PolicyRuntime(skip_default=True)

        # Attempt path traversal - should raise ValueError
        with pytest.raises(ValueError, match="Invalid license ID format"):
            runtime.lookup_license_data("../../../etc/passwd")

        with pytest.raises(ValueError, match="Invalid license ID format"):
            runtime.lookup_license_data("../../secrets")

    def test_get_obligations_path_traversal(self):
        """Test that PolicyRuntime.get_obligations blocks path traversal."""
        from ospac.runtime.engine import PolicyRuntime

        runtime = PolicyRuntime(skip_default=True)

        # Attempt path traversal via list of licenses
        # Should raise ValueError when validation catches it
        with pytest.raises(ValueError, match="Invalid license ID format"):
            runtime.get_obligations(["../../../etc/passwd"])

    def test_cli_show_command_validation(self, tmp_path):
        """Test that CLI show command validates license_id."""
        from click.testing import CliRunner
        from ospac.cli.commands import data

        runner = CliRunner()

        # Test with malicious license ID
        result = runner.invoke(data, ["show", "../../../etc/passwd"])

        # Should fail with validation error
        assert result.exit_code != 0

    def test_valid_license_works(self):
        """Test that valid license IDs still work correctly."""
        from ospac.runtime.engine import PolicyRuntime

        runtime = PolicyRuntime(skip_default=True)

        # These should not raise exceptions (even if files don't exist)
        # The function should return None if file not found
        result1 = runtime.lookup_license_data("MIT")
        result2 = runtime.lookup_license_data("GPL-3.0")
        result3 = runtime.lookup_license_data("Apache-2.0")

        # Results will be None if files don't exist, which is fine
        # The important thing is no exception was raised
        assert result1 is None or isinstance(result1, dict)
        assert result2 is None or isinstance(result2, dict)
        assert result3 is None or isinstance(result3, dict)


class TestSharedDataValidation:
    """The dataset validation rules must have exactly one implementation."""

    def test_cli_uses_shared_implementation(self):
        """The CLI command resolves validate_license to the shared function."""
        import ospac.cli.commands as commands
        from ospac.utils import data_validation

        assert commands.validate_license is data_validation.validate_license

    def test_script_uses_shared_implementation(self):
        """scripts/validate_data.py resolves validate_license to the shared function."""
        import importlib.util

        from ospac.utils import data_validation

        script_path = Path(__file__).parent.parent / "scripts" / "validate_data.py"
        spec = importlib.util.spec_from_file_location("validate_data_script", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.validate_license is data_validation.validate_license

    def test_shared_rule_constants(self):
        """Sanity-check the shared rule tables."""
        from ospac.utils.data_validation import (
            KNOWN_LICENSES,
            REQUIRED_TOP_FIELDS,
            VALID_CONTAMINATION,
            VALID_TYPES,
        )

        assert "MIT" in KNOWN_LICENSES
        assert KNOWN_LICENSES["GPL-3.0-only"]["type"] == "copyleft_strong"
        assert "spdx_id" in REQUIRED_TOP_FIELDS
        assert "permissive" in VALID_TYPES
        assert "derivative" in VALID_CONTAMINATION

    def test_validate_license_known_good_record(self):
        """A well-formed record produces no errors and no warnings."""
        from ospac.utils.data_validation import validate_license

        record = {
            "id": "MIT",
            "name": "MIT License",
            "type": "permissive",
            "spdx_id": "MIT",
            "properties": {
                "commercial_use": True,
                "distribution": True,
                "modification": True,
                "patent_grant": False,
                "private_use": True,
            },
            "requirements": {
                "disclose_source": False,
                "include_license": True,
                "include_copyright": True,
                "same_license": False,
                "network_use_disclosure": False,
                "state_changes": False,
            },
            "limitations": {"liability": True, "warranty": True, "trademark_use": False},
            "compatibility": {
                "static_linking": {
                    "compatible_with": ["Apache-2.0"],
                    "incompatible_with": [],
                    "requires_review": [],
                },
                "dynamic_linking": {
                    "compatible_with": ["Apache-2.0"],
                    "incompatible_with": [],
                    "requires_review": [],
                },
                "contamination_effect": "none",
            },
            "obligations": ["Include the license text"],
            "key_requirements": ["Include copyright notice"],
            "spdx_metadata": {
                "is_osi_approved": True,
                "is_fsf_libre": True,
                "is_deprecated": False,
            },
        }

        errors, warnings = validate_license("MIT", record)
        assert errors == []
        assert warnings == []


class TestDeprecatedAliasConsistency:
    """
    A deprecated SPDX identifier is an alias of a modern one, so the two must classify
    identically. Six LGPL aliases were marked copyleft_strong while their modern
    equivalents were copyleft_weak, which made policy rules deny them where the modern
    spelling was only flagged for review. Nothing detected the disagreement, so the
    invariant is asserted directly against the shipped dataset.
    """

    @staticmethod
    def _canonical(license_id):
        if license_id.endswith("+"):
            return license_id[:-1] + "-or-later"
        return license_id + "-only"

    def _shipped_records(self):
        import json

        data_dir = Path(__file__).parent.parent / "ospac" / "data" / "licenses" / "json"
        records = {}
        for path in data_dir.glob("*.json"):
            record = json.loads(path.read_text())["license"]
            records[record["id"]] = record
        return records

    def test_deprecated_aliases_match_their_canonical_type(self):
        records = self._shipped_records()
        mismatches = []
        for license_id, record in sorted(records.items()):
            if not record.get("spdx_metadata", {}).get("is_deprecated"):
                continue
            canonical = self._canonical(license_id)
            if canonical not in records:
                continue
            if record["type"] != records[canonical]["type"]:
                mismatches.append(
                    f"{license_id} is {record['type']} but {canonical} is "
                    f"{records[canonical]['type']}"
                )
        assert mismatches == [], "deprecated aliases disagree with canonical form: " + "; ".join(
            mismatches
        )

    def test_lgpl_aliases_are_weak_copyleft(self):
        """LGPL permits linking from proprietary code, so every spelling is weak copyleft."""
        records = self._shipped_records()
        for license_id in ["LGPL-2.0", "LGPL-2.0+", "LGPL-2.1", "LGPL-2.1+",
                           "LGPL-3.0", "LGPL-3.0+", "LGPL-2.0-only", "LGPL-2.1-only",
                           "LGPL-3.0-only"]:
            assert records[license_id]["type"] == "copyleft_weak", (
                f"{license_id} should be copyleft_weak, got {records[license_id]['type']}"
            )
