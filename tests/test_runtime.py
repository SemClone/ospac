"""
Tests for the policy runtime engine.
"""

import pytest
import yaml
from pathlib import Path

from ospac.runtime.engine import PolicyRuntime
from ospac.runtime.loader import PolicyLoader
from ospac.runtime.evaluator import RuleEvaluator
from ospac.models.compliance import ActionType


class TestPolicyLoader:
    """Test the PolicyLoader class."""

    def test_load_yaml_file(self, sample_policy_yaml):
        """Test loading a YAML policy file."""
        loader = PolicyLoader()
        policy = loader.load_file(str(sample_policy_yaml))

        assert policy["version"] == "1.0"
        assert policy["name"] == "Test Policy"
        assert len(policy["rules"]) == 1
        assert policy["rules"][0]["id"] == "test_rule"

    def test_load_all_policies(self, policy_directory):
        """Test loading all policies from a directory."""
        loader = PolicyLoader()
        policies = loader.load_all(str(policy_directory))

        assert len(policies) > 0
        assert "licenses/spdx/MIT" in policies
        assert "licenses/spdx/GPL-3.0" in policies
        assert "compatibility/rules" in policies

    def test_load_nonexistent_file(self):
        """Test loading a non-existent file."""
        loader = PolicyLoader()

        with pytest.raises(FileNotFoundError):
            loader.load_file("/nonexistent/file.yaml")

    def test_validate_policy(self):
        """Test policy validation."""
        loader = PolicyLoader()

        valid_policy = {
            "version": "1.0",
            "rules": []
        }
        assert loader.validate_policy(valid_policy) is True

        invalid_policy = {
            "name": "Missing version and rules"
        }
        assert loader.validate_policy(invalid_policy) is False


class TestRuleEvaluator:
    """Test the RuleEvaluator class."""

    def test_evaluate_simple_rule(self):
        """Test evaluating a simple rule."""
        policies = {
            "test": {
                "rules": [
                    {
                        "id": "test_rule",
                        "description": "Test",
                        "then": {
                            "action": "allow",
                            "severity": "info"
                        }
                    }
                ]
            }
        }

        evaluator = RuleEvaluator(policies)
        rule = policies["test"]["rules"][0]
        context = {}

        result = evaluator.evaluate_rule(rule, context)

        assert result["rule_id"] == "test_rule"
        assert result["action"] == "allow"
        assert result["severity"] == "info"

    def test_evaluate_rule_with_message_formatting(self):
        """Test rule evaluation with message formatting."""
        policies = {}
        evaluator = RuleEvaluator(policies)

        rule = {
            "id": "format_test",
            "then": {
                "action": "deny",
                "message": "License {license} is not allowed"
            }
        }

        context = {"license": "GPL-3.0"}
        result = evaluator.evaluate_rule(rule, context)

        assert result["message"] == "License GPL-3.0 is not allowed"

    def test_evaluate_decision_tree(self):
        """Test evaluating a decision tree."""
        policies = {}
        evaluator = RuleEvaluator(policies)

        tree = [
            {
                "if": {"license_type": "permissive"},
                "then": {"action": "approve"}
            },
            {
                "if": {"license_type": "copyleft"},
                "then": {"action": "review"}
            }
        ]

        context = {"license_type": "permissive"}
        result = evaluator.evaluate_decision_tree(tree, context)

        assert result["action"] == "approve"

    def test_decision_tree_no_match(self):
        """Test decision tree with no matching condition."""
        policies = {}
        evaluator = RuleEvaluator(policies)

        tree = [
            {
                "if": {"license_type": "permissive"},
                "then": {"action": "approve"}
            }
        ]

        context = {"license_type": "copyleft"}
        result = evaluator.evaluate_decision_tree(tree, context)

        assert result is None


class TestPolicyRuntime:
    """Test the PolicyRuntime class."""

    def test_initialize_runtime(self, policy_directory):
        """Test initializing the policy runtime."""
        runtime = PolicyRuntime(str(policy_directory))

        assert runtime.policies is not None
        assert runtime.evaluator is not None

    def test_from_path_constructor(self, policy_directory):
        """Test creating runtime from path."""
        runtime = PolicyRuntime.from_path(str(policy_directory))

        assert runtime.policies is not None
        assert runtime.evaluator is not None

    def test_evaluate_without_policies(self):
        """Test evaluation without loaded policies."""
        runtime = PolicyRuntime(skip_default=True)

        with pytest.raises(RuntimeError, match="No policies loaded"):
            runtime.evaluate({})

    def test_evaluate_with_context(self, policy_directory):
        """Test evaluating context against policies."""
        runtime = PolicyRuntime(str(policy_directory))

        context = {
            "license_type": "copyleft_strong",
            "link_type": "static"
        }

        # This should match the copyleft_contamination rule
        result = runtime.evaluate(context)
        assert result is not None

    def test_check_compatibility(self, policy_directory):
        """Test checking license compatibility."""
        runtime = PolicyRuntime(str(policy_directory))

        result = runtime.check_compatibility("MIT", "GPL-3.0", "static_linking")
        assert result is not None

    def test_get_obligations(self, policy_directory):
        """Test getting license obligations."""
        runtime = PolicyRuntime(str(policy_directory))

        obligations = runtime.get_obligations(["MIT", "GPL-3.0"])
        assert isinstance(obligations, dict)

    def test_rule_applies_with_conditions(self):
        """Test checking if a rule applies with conditions."""
        runtime = PolicyRuntime(skip_default=True)
        runtime.policies = {}
        runtime.evaluator = RuleEvaluator({})

        rule = {
            "when": {"license": "MIT", "usage": "commercial"}
        }

        # Matching context
        context = {"license": "MIT", "usage": "commercial"}
        assert runtime._rule_applies(rule, context) is True

        # Non-matching context
        context = {"license": "GPL", "usage": "commercial"}
        assert runtime._rule_applies(rule, context) is False

    def test_rule_applies_with_list_conditions(self):
        """Test rule with list conditions."""
        runtime = PolicyRuntime(skip_default=True)
        runtime.policies = {}
        runtime.evaluator = RuleEvaluator({})

        rule = {
            "when": {"license": ["MIT", "BSD", "Apache"]}
        }

        context = {"license": "MIT"}
        assert runtime._rule_applies(rule, context) is True

        context = {"license": "GPL"}
        assert runtime._rule_applies(rule, context) is False

    def test_rule_without_conditions(self):
        """Test rule without when clause always applies."""
        runtime = PolicyRuntime(skip_default=True)
        runtime.policies = {}
        runtime.evaluator = RuleEvaluator({})

        rule = {"id": "always_apply"}
        context = {"any": "context"}

        assert runtime._rule_applies(rule, context) is True

    def test_get_obligations_from_license_dataset(self):
        """Test obligations are read from the packaged per-license JSON files."""
        runtime = PolicyRuntime()

        obligations = runtime.get_obligations(["MIT", "Apache-2.0"])

        assert obligations["MIT"]["obligations"] == [
            "Retain copyright notices",
            "Include license text"
        ]
        assert obligations["Apache-2.0"]["obligations"] == [
            "Retain copyright notices",
            "Include license text",
            "Document changes made to the code"
        ]

    def test_get_obligations_unknown_license(self):
        """Test unknown license ids return cleanly with no entry."""
        runtime = PolicyRuntime()

        obligations = runtime.get_obligations(["Not-A-Real-License-1.0"])

        assert obligations == {}

    def test_check_compatibility_fires_license_type_rule(self, temp_dir):
        """Test check_compatibility resolves license types so type rules fire."""
        policy = {
            "version": "1.0",
            "name": "Type Rule Policy",
            "rules": [
                {
                    "id": "deny_strong_copyleft",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "Strong copyleft is not allowed"
                    }
                }
            ]
        }

        policy_file = temp_dir / "type_policy.yaml"
        with open(policy_file, "w") as f:
            yaml.dump(policy, f)

        runtime = PolicyRuntime(str(temp_dir))

        # GPL-3.0 is copyleft_strong in the dataset, so the rule must fire
        result = runtime.check_compatibility("MIT", "GPL-3.0")
        assert result.is_compliant is False

        # Two permissive licenses do not trigger the rule, and a compatibility question
        # answers "no known conflict" when no conflict rule matches. The review default
        # belongs to permission questions; applying it here made every license read as
        # incompatible with itself.
        result = runtime.check_compatibility("MIT", "Apache-2.0")
        assert result.violations == []
        assert result.is_compliant is True

    def test_check_compatibility_unknown_license_contributes_no_type(self, temp_dir):
        """Test licenses missing from the dataset contribute no type and do not raise."""
        policy = {
            "version": "1.0",
            "name": "Type Rule Policy",
            "rules": [
                {
                    "id": "deny_strong_copyleft",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "Strong copyleft is not allowed"
                    }
                }
            ]
        }

        policy_file = temp_dir / "type_policy.yaml"
        with open(policy_file, "w") as f:
            yaml.dump(policy, f)

        runtime = PolicyRuntime(str(temp_dir))

        # The unknown license contributes no type, so the copyleft rule cannot fire and
        # nothing raises. No conflict rule matches, so no conflict is known. The CLI adds
        # an unverified-license warning for ids the dataset cannot resolve.
        result = runtime.check_compatibility("Not-A-Real-License-1.0", "MIT")
        assert result.violations == []
        assert result.is_compliant is True

    def test_check_compatibility_gpl2_apache_still_incompatible(self):
        """Regression: GPL-2.0 and Apache-2.0 stay incompatible under the default policy."""
        runtime = PolicyRuntime()

        result = runtime.check_compatibility("GPL-2.0", "Apache-2.0")
        assert result.is_compliant is False

    def test_check_compatibility_mit_gpl3_still_compatible(self):
        """Regression: MIT and GPL-3.0 stay compatible under the default policy."""
        runtime = PolicyRuntime()

        result = runtime.check_compatibility("MIT", "GPL-3.0")
        assert result.is_compliant is True

class TestCheckReportsLicensesChecked:
    """check_compatibility always returned an empty licenses_checked."""

    def test_licenses_checked_is_populated(self):
        runtime = PolicyRuntime()
        result = runtime.check_compatibility("MIT", "GPL-3.0")
        assert result.licenses_checked == ["MIT", "GPL-3.0"]


class TestDeclaredLicenceStringsResolve:
    """
    Package registries do not answer in SPDX. PyPI's license field is free text by
    construction and requests 2.31.0 declares "Apache 2.0"; Maven POMs carry the prose
    name out of a <licenses> block. Matching those verbatim reached no rule and came
    back needing review, which a consumer cannot tell apart from a considered ruling
    even though a deny and a review mean opposite things downstream.
    """

    def test_registry_spellings_reach_the_same_verdict_as_the_identifier(self):
        runtime = PolicyRuntime()

        for declared, identifier, distribution in (
                ("Apache 2.0", "Apache-2.0", "saas"),
                ("MIT License", "MIT", "saas"),
                ("GNU General Public License v3.0 only", "GPL-3.0-only", "commercial"),
        ):
            spelled, _ = runtime.evaluate_licenses([declared],
                                                   {"distribution_type": distribution})
            canonical, _ = runtime.evaluate_licenses([identifier],
                                                     {"distribution_type": distribution})
            assert spelled.action == canonical.action, declared

    def test_the_input_spelling_keeps_matching_alongside_the_resolved_one(self):
        runtime = PolicyRuntime()

        # The default policy names the deprecated GPL-3.0 and resolution turns it into
        # GPL-3.0-only. Replacing the input rather than adding to it would break every
        # policy written against the spelling its author actually used.
        result, _ = runtime.evaluate_licenses(["GPL-3.0"],
                                              {"distribution_type": "commercial"})
        assert result.action == ActionType.DENY

    def test_evaluate_uses_a_verdict_the_readings_share(self):
        runtime = PolicyRuntime()

        # "GNU Affero General Public License v3" is AGPL-3.0-only or AGPL-3.0-or-later
        # and the default policy denies both for saas, so deny asserts nothing the
        # declaration did not carry. Returning review instead kept the deny-versus-review
        # gap open for the spelling Maven Central actually serves, which is the whole
        # complaint. check answered this correctly while evaluate did not.
        base = {"distribution_type": "saas"}
        declared, _ = runtime.evaluate_licenses(
            ["GNU Affero General Public License v3"], base)
        assert declared.action == ActionType.DENY
        for candidate in ("AGPL-3.0-only", "AGPL-3.0-or-later"):
            reading, _ = runtime.evaluate_licenses([candidate], base)
            assert reading.action == ActionType.DENY

    def test_readings_that_disagree_are_never_decided_by_the_strictest(self):
        runtime = PolicyRuntime()

        # "cryptographic autonomy" is CAL-1.0, which is network_copyleft, or its
        # combined-work exception, which is permissive. Exactly one applies and nobody
        # knows which, so most-restrictive-wins would assert an obligation the document
        # may not carry. It is also why the types must come from each reading: taking
        # the union let the permissive reading be judged as network copyleft and the
        # two then looked like they agreed.
        base = {"distribution_type": "saas"}
        assert runtime.evaluate_licenses(["CAL-1.0"], base)[0].action == ActionType.DENY
        assert runtime.evaluate_licenses(
            ["CAL-1.0-Combined-Work-Exception"], base)[0].action == ActionType.APPROVE

        declared, _ = runtime.evaluate_licenses(["cryptographic autonomy"], base)
        assert declared.action == ActionType.FLAG_FOR_REVIEW
        assert "which identifier the declaration means" in declared.message

    def test_only_what_every_reading_requires_is_reported(self):
        runtime = PolicyRuntime()

        # "Apache License" is 1.0, 1.1 or 2.0 and all three are approved, so the actions
        # agree. Their obligations do not: only 2.0 carries NOTICE and state-changes.
        # Unioning them stated an obligation a declaration meaning 1.0 does not have.
        declared, _ = runtime.evaluate_licenses(
            ["apache license"], {"distribution_type": "saas"})
        oldest, _ = runtime.evaluate_licenses(
            ["Apache-1.0"], {"distribution_type": "saas"})
        newest, _ = runtime.evaluate_licenses(
            ["Apache-2.0"], {"distribution_type": "saas"})

        assert declared.action == ActionType.APPROVE
        assert set(declared.requirements) <= set(oldest.requirements)
        assert set(declared.requirements) < set(newest.requirements)
        # An unambiguous declaration keeps everything its own licence requires.
        assert "Preserve copyright and NOTICE file if present" in newest.requirements

    def test_a_conflict_under_some_readings_is_review_not_clean(self, tmp_path):
        # Under the bundled policy the rules already disagree here. This is about the
        # dataset fallback on its own, so the policy has to match everything.
        policy = tmp_path / "policy.yaml"
        policy.write_text(
            'version: "2.0"\n'
            "name: allow-everything\n"
            "rules:\n"
            "  - id: allow_all\n"
            "    priority: 1\n"
            "    when: {}\n"
            "    then: {action: approve, severity: info, message: fine}\n")
        runtime = PolicyRuntime(str(policy))

        # Only Apache-2.0 conflicts with GPL-2.0. Denying would assert a reading the
        # declaration never made; reporting clean would hide one the dataset knows.
        assert runtime.check_compatibility(
            "Apache-2.0", "GPL-2.0-only").is_compliant is False
        assert runtime.check_compatibility(
            "Apache-1.0", "GPL-2.0-only").is_compliant is True

        partial = runtime.check_compatibility("apache license", "GPL-2.0-only")
        assert partial.needs_review is True
        assert any(warning.get("rule_id")
                   == "dataset_incompatibility_under_some_readings"
                   for warning in partial.warnings)

    def test_get_obligations_resolves_the_declared_string(self):
        runtime = PolicyRuntime(skip_default=True)

        # The library entry point took the caller's list verbatim, so a policy naming
        # Apache-2.0 answered nothing for "Apache 2.0" and an ambiguous declaration
        # raised on validation before anything could be reported.
        assert (runtime.get_obligations(["Apache 2.0"])["Apache 2.0"]
                == runtime.get_obligations(["Apache-2.0"])["Apache-2.0"])

        shared = runtime.get_obligations(["Apache License"])["Apache License"]
        oldest = runtime.get_obligations(["Apache-1.0"])["Apache-1.0"]
        newest = runtime.get_obligations(["Apache-2.0"])["Apache-2.0"]
        assert set(shared["obligations"]) <= set(oldest["obligations"])
        assert set(shared["obligations"]) < set(newest["obligations"])

    def test_agreement_is_about_the_outcome_not_the_word(self, tmp_path):
        # One reading matches an approval rule and the others fall through to allow.
        # Both are permissions, so the readings agree; comparing the action verbatim
        # reported review for a pair every reading permits.
        policy = tmp_path / "policy.yaml"
        policy.write_text(
            'version: "2.0"\n'
            "name: approve-apache2-with-mit\n"
            "rules:\n"
            "  - id: approve_apache2_mit\n"
            "    priority: 5\n"
            '    when: {license1: ["Apache-2.0"], license2: ["MIT"]}\n'
            "    then: {action: approve, severity: info, message: fine}\n")
        runtime = PolicyRuntime(str(policy))

        assert runtime.check_compatibility("Apache-2.0", "MIT").is_compliant is True
        assert runtime.check_compatibility("Apache-1.0", "MIT").is_compliant is True
        declared = runtime.check_compatibility("apache license", "MIT")
        assert declared.is_compliant is True
        assert declared.needs_review is False

    def test_a_reading_carries_the_callers_spelling_as_well(self):
        runtime = PolicyRuntime()

        # Rules compare exact strings and a policy may name either spelling, so both
        # reach the rules. They are one license written two ways, not two readings:
        # a rule matching only one of them is a match, not a disagreement.
        assert runtime._readings("Apache 2.0") == [
            ("Apache-2.0", ["Apache 2.0", "Apache-2.0"])]
        assert runtime._readings("gplv2") == [
            ("GPL-2.0-only", ["GPL-2.0-only", "gplv2"]),
            ("GPL-2.0-or-later", ["GPL-2.0-or-later", "gplv2"])]

    def test_a_name_that_states_no_grant_is_not_resolved_for_the_caller(self):
        runtime = PolicyRuntime()

        # "GNU Affero General Public License v3" names the licence and not which id,
        # and -only versus -or-later is the copyright holder's grant. Picking one would
        # assert something the declaration never said.
        resolution = runtime.resolve_licenses(
            ["GNU Affero General Public License v3"])["GNU Affero General Public License v3"]
        assert resolution.status == "ambiguous"
        assert resolution.license_id is None
        assert resolution.candidates == ["AGPL-3.0-only", "AGPL-3.0-or-later"]

    def test_family_names_and_unknown_strings_stay_unresolved(self):
        runtime = PolicyRuntime()

        for declared in ("gpl", "bsd", "Not-A-Real-License"):
            resolution = runtime.resolve_licenses([declared])[declared]
            assert resolution.status == "unresolved", declared
            assert resolution.license_id is None

    def test_resolution_is_reported_so_a_verdict_can_be_trusted(self):
        runtime = PolicyRuntime()

        resolutions = runtime.resolve_licenses(["Apache-2.0", "Apache 2.0"])
        assert resolutions["Apache-2.0"].status == "exact"
        assert resolutions["Apache 2.0"].status == "normalized"
        assert resolutions["Apache 2.0"].license_id == "Apache-2.0"

    def test_obligations_follow_a_declared_name_to_its_record(self):
        runtime = PolicyRuntime()

        assert (runtime.lookup_license_data("Apache 2.0")
                == runtime.lookup_license_data("Apache-2.0"))

    def test_a_declared_pair_reaches_the_same_pairwise_rule(self):
        runtime = PolicyRuntime()

        spelled = runtime.check_compatibility(
            "GNU General Public License v2.0 only", "Apache 2.0")
        canonical = runtime.check_compatibility("GPL-2.0-only", "Apache-2.0")
        assert spelled.is_compliant == canonical.is_compliant is False
        # The report still names what the caller asked about, not what it resolved to.
        assert spelled.licenses_checked == [
            "GNU General Public License v2.0 only", "Apache 2.0"]

    def test_an_input_that_names_a_record_keeps_its_own_record(self):
        runtime = PolicyRuntime()

        # GPL-2.0 is deprecated and the alias map migrates it to GPL-2.0-only, but it
        # ships a record of its own and the bundled pairwise rules name it. Replacing it
        # would break every policy written against the spelling its author used.
        assert runtime._matchable_id("GPL-2.0") == "GPL-2.0"
        assert runtime._matchable_id("Apache 2.0") == "Apache-2.0"

    def test_a_declared_pair_reaches_the_dataset_incompatibility_too(self):
        runtime = PolicyRuntime()

        # GPL-2.0's record names BSD-4-Clause in incompatible_with, and that list holds
        # canonical ids. Resolving only the policy context left the dataset fallback
        # comparing a declared name against canonical ids, so a known incompatible pair
        # read as clean for exactly the inputs resolution was added to serve.
        canonical = runtime.check_compatibility("GPL-2.0", "BSD-4-Clause")
        spelled = runtime.check_compatibility(
            "GNU General Public License v2.0 only",
            'bsd 4-clause "original" or "old" license')
        assert canonical.is_compliant is False
        assert spelled.is_compliant is False

    def test_case_does_not_decide_whether_a_string_is_an_identifier(self):
        runtime = PolicyRuntime()

        # A case-insensitive volume opens Apache-2.0's record for "apache-2.0.json", so
        # probing the filesystem answered "this is already an identifier" and left the
        # lower-cased spelling in place. Rule matching is case-sensitive, so the pair
        # then matched nothing and a reviewed pair read as clean. The shipped id set
        # answers the same on every platform.
        assert runtime._matchable_id("apache-2.0") == "Apache-2.0"
        assert runtime.check_compatibility("apache-2.0", "gpl-3.0").is_compliant is (
            runtime.check_compatibility("Apache-2.0", "GPL-3.0").is_compliant)

    def test_a_deprecated_id_keeps_its_own_record(self):
        runtime = PolicyRuntime()

        # GPL-3.0 is deprecated and the alias map migrates it to GPL-3.0-only, but it
        # ships a record of its own. A caller naming it means that record, including
        # the deprecation metadata the canonical one does not carry.
        record = runtime.lookup_license_data("GPL-3.0")["license"]
        assert record["id"] == "GPL-3.0"
        assert record["alias_of"] == "GPL-3.0-only"
        assert record["spdx_metadata"]["is_deprecated"] is True

    def test_an_ambiguous_name_is_checked_under_every_reading(self):
        runtime = PolicyRuntime()

        # "gplv2" is GPL-2.0-only or GPL-2.0-or-later and BSD-4-Clause's record names
        # both incompatible, so the conflict holds whichever the document meant.
        # Flattening the declaration to its own text threw the readings away and the
        # pair came back compatible, which is the failure direction that matters.
        assert runtime.check_compatibility("gplv2", "BSD-4-Clause").is_compliant is False
        assert runtime.check_compatibility(
            "GPL-2.0-only", "BSD-4-Clause").is_compliant is False
        assert runtime.check_compatibility(
            "GPL-2.0-or-later", "BSD-4-Clause").is_compliant is False

    def test_readings_that_disagree_are_not_decided_for_the_caller(self):
        runtime = PolicyRuntime()

        # The bundled one-way rules name GPL-2.0-only and not GPL-2.0-or-later, so the
        # two readings of "gplv2" answer differently. The declaration did not choose,
        # so neither does the check.
        assert runtime.check_compatibility("gplv2", "MIT").needs_review is True

    def test_one_resolution_policy_for_a_shipped_deprecated_id(self):
        import ospac

        runtime = PolicyRuntime()

        # The record lookup returns GPL-2.0's own record, so the reported resolution
        # has to agree. Saying "normalized to GPL-2.0-only" beside that record put two
        # answers in one payload and the metadata was the one a consumer would believe.
        assert runtime.lookup_license_data("GPL-2.0")["license"]["id"] == "GPL-2.0"
        assert ospac.resolve_license("GPL-2.0").status == "exact"
        assert ospac.resolve_license("GPL-2.0").license_id == "GPL-2.0"

    def test_a_path_is_still_a_path(self):
        runtime = PolicyRuntime()

        # Resolution runs before validation so a prose name can reach a record at all.
        # A string the data does not recognise must still be rejected rather than
        # reaching the filesystem.
        with pytest.raises(ValueError):
            runtime.lookup_license_data("../../../etc/passwd")


class TestStrongerCopyleftIsNeverMorePermissive:
    """
    AGPL-3.0 is GPL-3.0 with the network clause added, so there is no distribution type
    where it is the less restrictive of the two. A gap that let AGPL fall through every
    rule while GPL was denied read as an affirmative permission at the point where the
    policy engine is the only authority in the chain.
    """

    def test_agpl_is_never_more_permissive_than_gpl(self):
        runtime = PolicyRuntime()
        ranked = [ActionType.APPROVE, ActionType.ALLOW, ActionType.FLAG_FOR_REVIEW,
                  ActionType.CONTAMINATE, ActionType.DENY]

        for distribution in ("commercial", "saas", "embedded", "web", "internal",
                             "mobile", "desktop"):
            base = {"distribution_type": distribution}
            agpl, _ = runtime.evaluate_licenses(["AGPL-3.0"], base)
            gpl, _ = runtime.evaluate_licenses(["GPL-3.0"], base)
            assert ranked.index(agpl.action) >= ranked.index(gpl.action), (
                f"AGPL-3.0 is {agpl.action} for {distribution} where GPL-3.0 is "
                f"{gpl.action}; AGPL adds an obligation and can never be laxer")
