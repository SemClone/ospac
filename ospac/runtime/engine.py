"""
Policy execution runtime engine.
"""

import os
from typing import Dict, List, Any, Optional
from pathlib import Path
import tempfile
import shutil

from ospac.runtime.loader import PolicyLoader
from ospac.runtime.evaluator import RuleEvaluator
from ospac.models.compliance import ComplianceResult, PolicyResult, ActionType


class PolicyRuntime:
    """
    Main policy execution runtime.
    All logic is driven by policy files, not hardcoded.
    """

    def __init__(self, policy_path: Optional[str] = None, skip_default: bool = False):
        """Initialize the policy runtime with policy definitions."""
        self.policies = {}
        self.evaluator = None
        self._using_default = False

        if policy_path:
            self.load_policies(policy_path)
        elif not skip_default:
            self._load_default_policy()

    def load_policies(self, policy_path: str) -> None:
        """Load all policy definitions from the specified path."""
        path = Path(policy_path)

        # If path doesn't exist or is empty, use default policy
        if not path.exists() or (path.is_dir() and not any(path.iterdir())):
            self._load_default_policy()
            return

        loader = PolicyLoader()
        self.policies = loader.load_all(policy_path)
        self.evaluator = RuleEvaluator(self.policies)

    def _load_default_policy(self) -> None:
        """Load the default enterprise policy."""
        # Get the default policy file from the package
        default_policy = Path(__file__).parent.parent / "defaults" / "enterprise_policy.yaml"

        if not default_policy.exists():
            raise RuntimeError(f"Default policy file not found: {default_policy}")

        loader = PolicyLoader()
        self.policies = {"default_enterprise": loader.load_file(str(default_policy))}
        self.evaluator = RuleEvaluator(self.policies)
        self._using_default = True

    @classmethod
    def from_path(cls, policy_path: str) -> "PolicyRuntime":
        """Create a PolicyRuntime instance from a policy directory."""
        return cls(policy_path)

    def evaluate(self, context: Dict[str, Any]) -> PolicyResult:
        """
        Evaluate context against all loaded policies.
        No business logic here - just policy execution.
        """
        if not self.evaluator:
            raise RuntimeError("No policies loaded. Call load_policies() first.")

        applicable_rules = self._find_applicable_rules(context)
        results = []

        for rule in applicable_rules:
            result = self.evaluator.evaluate_rule(rule, context)
            # Convert dict result to PolicyResult
            policy_result = PolicyResult(
                rule_id=result.get("rule_id", "unknown"),
                action=ActionType[result.get("action", "allow").upper()],
                severity=result.get("severity", "info"),
                message=result.get("message"),
                requirements=result.get("requirements", []),
                remediation=result.get("remediation")
            )
            results.append(policy_result)

        return PolicyResult.aggregate(results)

    def _find_applicable_rules(self, context: Dict[str, Any]) -> List[Dict]:
        """Find all rules that apply to the given context."""
        applicable = []

        for policy_name, policy in self.policies.items():
            if "rules" in policy:
                for rule in policy["rules"]:
                    if self._rule_applies(rule, context):
                        applicable.append(rule)

        return applicable

    def _rule_applies(self, rule: Dict, context: Dict) -> bool:
        """Check if a rule applies to the given context."""
        if "when" not in rule:
            return True

        return self._check_condition(rule["when"], context)

    def _check_condition(self, condition: Dict, context: Dict) -> bool:
        """Check if a single condition is met."""
        # All conditions in the when clause must be satisfied
        for key, value in condition.items():
            context_value = context.get(key)

            # Special handling for license checks
            if key == "license":
                # Check if any of the licenses in context match
                licenses_to_check = []

                # Support different ways licenses might be specified
                if "licenses" in context:
                    licenses_to_check.extend(context["licenses"])
                if "licenses_found" in context:
                    licenses_to_check.extend(context["licenses_found"])
                if "license" in context:
                    # Also support single license field for compatibility
                    single_license = context["license"]
                    if isinstance(single_license, str):
                        licenses_to_check.append(single_license)
                    elif isinstance(single_license, list):
                        licenses_to_check.extend(single_license)

                # If no licenses found in any expected field, no match
                if not licenses_to_check:
                    return False

                if isinstance(value, list):
                    # Check if any license in context matches any in the rule
                    if not any(lic in value for lic in licenses_to_check):
                        return False
                else:
                    if value not in licenses_to_check:
                        return False
            else:
                # Normal field checking
                if context_value is None:
                    return False

                if isinstance(value, list):
                    if context_value not in value:
                        return False
                elif context_value != value:
                    return False

        return True

    def check_compatibility(self, license1: str, license2: str,
                           context: str = "general") -> ComplianceResult:
        """Check if two licenses are compatible."""
        eval_context = {
            "license1": license1,
            "license2": license2,
            "compatibility_context": context
        }

        result = self.evaluate(eval_context)
        return ComplianceResult.from_policy_result(result)

    def get_obligations(self, licenses: List[str]) -> Dict[str, Any]:
        """Get all obligations for the given licenses."""
        obligations = {}

        # Look for obligations in all obligation policy files
        for policy_name, policy_data in self.policies.items():
            if policy_name.startswith("obligations/") and "obligations" in policy_data:
                for license_id in licenses:
                    if license_id in policy_data["obligations"]:
                        if license_id not in obligations:
                            obligations[license_id] = {}
                        obligations[license_id].update(policy_data["obligations"][license_id])

        return obligations