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
        assert "noncommercial" in VALID_TYPES
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


class TestRestrictionSemanticsRules:
    """
    NC / ND / SA restrictions are derivable from the SPDX identifier or the
    license name, so the validator enforces them deterministically. A silent
    generation failure once wrote permissive defaults (commercial_use True,
    modification True, same_license False) into every Creative Commons
    NonCommercial, NoDerivatives and ShareAlike record and nothing caught it.
    """

    @staticmethod
    def _record(license_id, name, lic_type="permissive", properties=None, requirements=None):
        """A structurally valid record with overridable fields under test."""
        props = {
            "commercial_use": True,
            "distribution": True,
            "modification": True,
            "patent_grant": False,
            "private_use": True,
        }
        props.update(properties or {})
        reqs = {
            "disclose_source": False,
            "include_license": True,
            "include_copyright": True,
            "same_license": False,
            "network_use_disclosure": False,
            "state_changes": False,
        }
        reqs.update(requirements or {})
        return {
            "id": license_id,
            "name": name,
            "type": lic_type,
            "spdx_id": license_id,
            "properties": props,
            "requirements": reqs,
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
                "is_osi_approved": False,
                "is_fsf_libre": False,
                "is_deprecated": False,
            },
        }

    @classmethod
    def _errors(cls, license_id, name, **kwargs):
        from ospac.utils.data_validation import validate_license

        errors, _ = validate_license(license_id, cls._record(license_id, name, **kwargs))
        return errors

    def test_noncommercial_id_with_commercial_use_true_is_error(self):
        errors = self._errors(
            "CC-BY-NC-4.0",
            "Creative Commons Attribution Non Commercial 4.0 International",
        )
        assert any(
            "NonCommercial license must have properties.commercial_use false" in e
            for e in errors
        )

    def test_noncommercial_id_with_commercial_use_false_passes(self):
        errors = self._errors(
            "CC-BY-NC-4.0",
            "Creative Commons Attribution Non Commercial 4.0 International",
            lic_type="noncommercial",
            properties={"commercial_use": False},
        )
        assert errors == []

    def test_noncommercial_name_without_nc_component_is_matched(self):
        """NCGL-UK-2.0 has no NC component but its name says Non-Commercial."""
        errors = self._errors("NCGL-UK-2.0", "Non-Commercial Government Licence")
        assert any(
            "NonCommercial license must have properties.commercial_use false" in e
            for e in errors
        )

    def test_noderivatives_id_with_modification_true_is_error(self):
        errors = self._errors(
            "CC-BY-ND-3.0-IGO",
            "Creative Commons Attribution No Derivatives 3.0 IGO",
        )
        assert any(
            "NoDerivatives license must have properties.modification false" in e
            for e in errors
        )

    def test_noderivatives_id_with_modification_false_passes(self):
        errors = self._errors(
            "CC-BY-ND-3.0-IGO",
            "Creative Commons Attribution No Derivatives 3.0 IGO",
            lic_type="proprietary",
            properties={"modification": False},
        )
        assert errors == []

    def test_sharealike_id_with_same_license_false_is_error(self):
        errors = self._errors(
            "CC-BY-SA-4.0",
            "Creative Commons Attribution Share Alike 4.0 International",
        )
        assert any(
            "ShareAlike license must have requirements.same_license true" in e
            for e in errors
        )

    def test_sharealike_id_with_same_license_true_passes(self):
        errors = self._errors(
            "CC-BY-SA-4.0",
            "Creative Commons Attribution Share Alike 4.0 International",
            lic_type="copyleft_strong",
            requirements={"same_license": True, "disclose_source": True},
        )
        assert errors == []

    def test_combined_nc_sa_id_reports_both_violations(self):
        errors = self._errors(
            "CC-BY-NC-SA-4.0",
            "Creative Commons Attribution Non Commercial Share Alike 4.0 International",
        )
        assert any("NonCommercial license" in e for e in errors)
        assert any("ShareAlike license" in e for e in errors)

    def test_noncommercial_typed_permissive_is_inconsistent(self):
        """commercial_use false and type permissive contradict each other."""
        errors = self._errors(
            "CC-BY-NC-4.0",
            "Creative Commons Attribution Non Commercial 4.0 International",
            properties={"commercial_use": False},
        )
        assert any(
            "properties.commercial_use false requires type 'noncommercial'" in e
            for e in errors
        )

    def test_commercial_use_false_with_noncommercial_type_passes_consistency(self):
        errors = self._errors(
            "PolyForm-Noncommercial-1.0.0",
            "PolyForm Noncommercial License 1.0.0",
            lic_type="noncommercial",
            properties={"commercial_use": False},
        )
        assert errors == []

    def test_public_domain_dedications_are_not_matched(self):
        """CC0-1.0 and CC-PDDC must not trip the NC / ND / SA rules."""
        errors = self._errors(
            "CC0-1.0",
            "Creative Commons Zero v1.0 Universal",
            lic_type="public_domain",
        )
        assert errors == []

        errors = self._errors(
            "CC-PDDC",
            "Creative Commons Public Domain Dedication and Certification",
            lic_type="public_domain",
        )
        assert errors == []

    def test_incidental_letters_in_id_are_not_matched(self):
        """Ids that merely contain the letters must not match the components."""
        for license_id, name in [
            ("NCSA", "University of Illinois/NCSA Open Source License"),
            ("NASA-1.3", "NASA Open Source Agreement 1.3"),
            ("HPND", "Historical Permission Notice and Disclaimer"),
            ("SAX-PD", "Sax Public Domain Notice"),
            ("NCL", "NCL Source Code License"),
        ]:
            errors = self._errors(license_id, name)
            assert errors == [], f"{license_id} wrongly flagged: {errors}"


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


class TestDatasetPipelineReproducibility:
    """
    Every record in the shipped dataset must be exactly what the generation pipeline
    produces for it. Repairs that existed only as hand-edited JSON were silently
    reverted by the next regeneration: the ShareAlike retypes survived on disk while
    the pipeline would have written permissive back over them.
    """

    def test_pipeline_reproduces_every_shipped_record(self):
        import json

        from ospac.pipeline.data_generator import PolicyDataGenerator as G

        data_dir = Path(__file__).parent.parent / "ospac" / "data" / "licenses" / "json"
        not_reproduced = []
        for path in sorted(data_dir.glob("*.json")):
            record = json.loads(path.read_text())["license"]
            analysis = {
                "license_id": record["id"],
                "name": record.get("name", ""),
                "category": record["type"],
                "permissions": dict(record["properties"]),
                "conditions": dict(record["requirements"]),
                "compatibility_rules": dict(record.get("compatibility", {})),
            }
            analysis = G._apply_known_corrections(G, record["id"], analysis)
            analysis = G._apply_identifier_restrictions(G, record["id"], analysis)
            obligations, key_requirements = G._derive_obligations(
                G, record["id"], analysis["category"],
                analysis["conditions"], analysis["permissions"])

            if (analysis["category"] != record["type"]
                    or analysis["permissions"] != record["properties"]
                    or analysis["conditions"] != record["requirements"]
                    or obligations != record["obligations"]
                    or key_requirements != record["key_requirements"]
                    or analysis["compatibility_rules"] != record.get("compatibility")):
                not_reproduced.append(record["id"])

        assert not_reproduced == [], (
            "the pipeline would rewrite these records differently on regeneration, so "
            "their current values are hand edits that will silently revert: "
            + ", ".join(not_reproduced[:10])
        )

    def test_restricted_categories_are_populated(self):
        import json

        data_dir = Path(__file__).parent.parent / "ospac" / "data" / "licenses" / "json"
        types = {}
        for path in data_dir.glob("*.json"):
            record = json.loads(path.read_text())["license"]
            types.setdefault(record["type"], []).append(record["id"])

        # The identifier states these restrictions, so the categories cannot be empty.
        assert "CC-BY-NC-4.0" in types.get("noncommercial", [])
        assert "Aladdin" in types.get("noncommercial", [])
        assert "CC-BY-ND-4.0" in types.get("no_derivatives", [])
        assert "SSPL-1.0" in types.get("network_copyleft", [])
        assert "BUSL-1.1" in types.get("source_available", [])
        assert "EUPL-1.2" in types.get("copyleft_strong", [])
        # ShareAlike must be in a copyleft category, never permissive. Whether the
        # analysis places CC-BY-SA in weak or strong is its judgement to make; what the
        # invariant forbids is the category a permissive-approve rule would bless.
        sa_copyleft = types.get("copyleft_weak", []) + types.get("copyleft_strong", [])
        assert "CC-BY-SA-4.0" in sa_copyleft
        assert "CC-BY-SA-4.0" not in types.get("permissive", [])


class TestCompatibilityListSoundness:
    """
    The record-level compatibility lists were model-generated and systematically wrong:
    540 permissive records declared themselves incompatible with GPL, which inverts how
    permissive licensing works, and pairs disagreed with each other. The lists are now
    derived from the category plus a known-exception table, so these invariants hold by
    construction and this test keeps them held.
    """

    @staticmethod
    def _records():
        import json

        data_dir = Path(__file__).parent.parent / "ospac" / "data" / "licenses" / "json"
        records = {}
        for path in data_dir.glob("*.json"):
            record = json.loads(path.read_text())["license"]
            records[record["id"]] = record
        return records

    @staticmethod
    def _claims(record, other):
        block = record["compatibility"]["static_linking"]
        other_cat = f"category:{other['type']}"
        if other["id"] in block["incompatible_with"] or other_cat in block["incompatible_with"]:
            return "incompatible"
        if (other["id"] in block["compatible_with"] or other_cat in block["compatible_with"]
                or "category:any" in block["compatible_with"]):
            return "compatible"
        return None

    def test_no_permissive_record_claims_copyleft_incompatibility(self):
        from ospac.pipeline.data_generator import _known_incompatible_ids

        offenders = []
        for record in self._records().values():
            if record["type"] not in ("permissive", "public_domain"):
                continue
            allowed = set(_known_incompatible_ids(record["id"]))
            for entry in record["compatibility"]["static_linking"]["incompatible_with"]:
                if entry not in allowed:
                    offenders.append(f"{record['id']} -> {entry}")
        assert offenders == [], offenders[:10]

    def test_pairwise_claims_are_symmetric(self):
        records = self._records()
        sample = ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-4-Clause", "GPL-2.0-only",
                  "GPL-3.0-only", "LGPL-2.1-only", "MPL-2.0", "AGPL-3.0-only",
                  "CC-BY-NC-4.0", "EPL-2.0"]
        conflicts = []
        for i, a in enumerate(sample):
            for b in sample[i + 1:]:
                ca = self._claims(records[a], records[b])
                cb = self._claims(records[b], records[a])
                if {ca, cb} == {"compatible", "incompatible"}:
                    conflicts.append(f"{a} says {ca} of {b}, {b} says {cb} of {a}")
        assert conflicts == [], conflicts

    def test_known_exception_pairs_are_mutually_incompatible(self):
        records = self._records()
        for a, b in [("GPL-2.0-only", "Apache-2.0"), ("GPL-2.0-only", "GPL-3.0-only"),
                     ("BSD-4-Clause", "GPL-3.0-only")]:
            assert self._claims(records[a], records[b]) == "incompatible"
            assert self._claims(records[b], records[a]) == "incompatible"


class TestRelationshipsTreeSoundness:
    """
    The sparse relationships tree was rebuilt during 1.4.1 from the model's wrong
    lists, one release before the derivation existed, so it shipped claiming MIT is
    statically incompatible with GPL-3.0 while the records said otherwise.
    """

    @staticmethod
    def _family(name):
        import json

        path = (Path(__file__).parent.parent / "ospac" / "data" / "compatibility"
                / "relationships" / f"{name}.json")
        return json.loads(path.read_text())

    def test_permissive_into_copyleft_is_compatible(self):
        mit = self._family("mit")["MIT"]
        assert mit["GPL-3.0-only"]["static_linking"] == "compatible"
        assert mit["GPL-3.0-only"]["distribution"] == "compatible"

    def test_known_pair_is_incompatible_in_every_dimension(self):
        gpl = self._family("gpl")["GPL-2.0-only"]
        assert gpl["Apache-2.0"] == {"static_linking": "incompatible",
                                     "dynamic_linking": "incompatible",
                                     "distribution": "incompatible"}

    def test_noncommercial_rows_require_review(self):
        nc = self._family("cc")["CC-BY-NC-4.0"]
        assert nc["MIT"]["static_linking"] == "review_required"
