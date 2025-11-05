"""
Policy execution runtime engine.
"""

from typing import Dict, List, Any, Optional
from pathlib import Path

from ospac.runtime.loader import PolicyLoader
from ospac.runtime.evaluator import RuleEvaluator
from ospac.models.compliance import ComplianceResult, PolicyResult, ActionType


class PolicyRuntime:
    """
    Main policy execution runtime.
    All logic is driven by policy files, not hardcoded.
    """

    def __init__(self, policy_path: Optional[str] = None):
        """Initialize the policy runtime with policy definitions."""
        self.policies = {}
        self.evaluator = None

        if policy_path:
            self.load_policies(policy_path)

    def load_policies(self, policy_path: str) -> None:
        """Load all policy definitions from the specified path."""
        loader = PolicyLoader()
        self.policies = loader.load_all(policy_path)
        self.evaluator = RuleEvaluator(self.policies)

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

        conditions = rule["when"]
        if not isinstance(conditions, list):
            conditions = [conditions]

        for condition in conditions:
            if not self._check_condition(condition, context):
                return False

        return True

    def _check_condition(self, condition: Dict, context: Dict) -> bool:
        """Check if a single condition is met."""
        for key, value in condition.items():
            if key not in context:
                return False

            if isinstance(value, list):
                if context[key] not in value:
                    return False
            elif context[key] != value:
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