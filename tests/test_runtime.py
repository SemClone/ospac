"""
Tests for the policy runtime engine.
"""

import pytest
import yaml
from pathlib import Path

from ospac.runtime.engine import PolicyRuntime
from ospac.runtime.loader import PolicyLoader
from ospac.runtime.evaluator import RuleEvaluator


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

        # Two permissive licenses do not trigger the rule
        result = runtime.check_compatibility("MIT", "Apache-2.0")
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

        result = runtime.check_compatibility("Not-A-Real-License-1.0", "MIT")
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