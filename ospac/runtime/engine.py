"""
Policy execution runtime engine.
"""

import os
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
import tempfile
import shutil

from ospac.runtime.loader import PolicyLoader
from ospac.runtime.evaluator import RuleEvaluator
from ospac.models.compliance import ComplianceResult, PolicyResult, ActionType
from ospac.utils.validation import validate_license_id

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

    def evaluate(self, context: Dict[str, Any],
                 when_unmatched: str = "review") -> PolicyResult:
        """
        Evaluate context against all loaded policies.
        No business logic here - just policy execution.

        Evaluates the context as a single unit. For a list of licenses prefer
        evaluate_licenses(), which evaluates each license independently so that one
        license matching a rule cannot answer for the others.
        """
        if not self.evaluator:
            raise RuntimeError("No policies loaded. Call load_policies() first.")

        applicable_rules = self._find_applicable_rules(context)
        results = []

        for rule in applicable_rules:
            result = self.evaluator.evaluate_rule(rule, context)
            # Convert dict result to PolicyResult
            action_name = result.get("action", "allow").lower()
            if action_name == "review":
                # Policies may use "review" as shorthand for flag_for_review
                action_name = "flag_for_review"
            policy_result = PolicyResult(
                rule_id=result.get("rule_id", "unknown"),
                action=ActionType[action_name.upper()],
                severity=result.get("severity", "info"),
                message=result.get("message"),
                requirements=result.get("requirements", []),
                remediation=result.get("remediation")
            )
            results.append(policy_result)

        return PolicyResult.aggregate(results, when_unmatched=when_unmatched)

    def resolve_license_type(self, license_id: str,
                             data_dir: Optional[str] = None) -> Optional[str]:
        """Look up a license's type from the dataset, or None if unresolvable."""
        try:
            record = self.lookup_license_data(license_id, data_dir)
        except ValueError:
            return None
        return ((record or {}).get("license") or {}).get("type")

    def evaluate_licenses(self, licenses: List[str],
                          base_context: Dict[str, Any]) -> tuple:
        """
        Evaluate each license independently, then aggregate the per-license verdicts.

        Set-level evaluation let one license answer for the whole set: an approve rule
        matching MIT approved "MIT,AGPL-3.0", because the rule list was non-empty and the
        no-match fail-safe never ran for the AGPL that matched nothing. Evaluating per
        license means every license either gets a verdict from a rule or falls to the
        fail-safe on its own.

        Returns (aggregated PolicyResult, {license_id: per-license PolicyResult}).
        base_context carries the shared fields (distribution_type, context, linking_type);
        the per-license fields are filled in here.
        """
        per_license: Dict[str, PolicyResult] = {}
        for license_id in licenses:
            license_type = self.resolve_license_type(license_id)
            ctx = dict(base_context)
            ctx["licenses"] = [license_id]
            ctx["licenses_found"] = [license_id]
            ctx["license_type"] = [license_type] if license_type else []
            per_license[license_id] = self.evaluate(ctx)

        combined = PolicyResult.aggregate(list(per_license.values()))
        return combined, per_license

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
            elif key == "license_type":
                # Multiple licenses may be evaluated at once, so the context
                # value can be a scalar or a list of types. The rule matches
                # if any evaluated license's type matches the rule value.
                types_to_check = []

                if isinstance(context_value, str):
                    types_to_check.append(context_value)
                elif isinstance(context_value, list):
                    types_to_check.extend(context_value)

                # If no license types are available in context, no match
                if not types_to_check:
                    return False

                if isinstance(value, list):
                    # Check if any type in context matches any in the rule
                    if not any(lic_type in value for lic_type in types_to_check):
                        return False
                else:
                    if value not in types_to_check:
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
        # Resolve license types from the dataset so rules matching on
        # license_type (e.g. copyleft_strong) can fire. Licenses missing
        # from the dataset simply contribute no type.
        license_types = []
        for license_id in (license1, license2):
            try:
                license_data = self.lookup_license_data(license_id)
            except ValueError:
                continue
            license_type = (license_data or {}).get("license", {}).get("type")
            if license_type and license_type not in license_types:
                license_types.append(license_type)

        eval_context = {
            "license1": license1,
            "license2": license2,
            "license_type": license_types,
            "compatibility_context": context,
            # Mirror evaluate's derivation so linking rules can fire on pairs too.
            # check -c static_linking previously reached no rule that matched on
            # linking_type, because the field was never set here.
            "linking_type": context if "linking" in context else None
        }

        # A compatibility check asks whether a conflict is known, so no rule matching
        # means "no known conflict", not "needs review". The review default belongs to
        # permission questions; applying it here made every license read as incompatible
        # with itself, since this context carries no distribution_type and most rules
        # therefore cannot match.
        result = self.evaluate(eval_context, when_unmatched="allow")
        compliance = ComplianceResult.from_policy_result(result)
        # The result always reported an empty licenses_checked even though exactly two
        # licenses were checked.
        compliance.licenses_checked = [license1, license2]
        return compliance

    def get_obligations(self, licenses: List[str], data_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all obligations for the given licenses.

        Args:
            licenses: List of SPDX license identifiers
            data_dir: Optional data directory path

        Returns:
            Dictionary keyed by license id. Each value is a dictionary that
            contains an "obligations" list from the license dataset, merged
            with any entries from obligations/ policy files. Licenses with
            no known obligations are omitted.
        """
        # Use package data directory if not specified
        data_dir = self.resolve_data_dir(data_dir)

        obligations = {}

        # Look for obligations in all obligation policy files
        for policy_name, policy_data in self.policies.items():
            if policy_name.startswith("obligations/") and "obligations" in policy_data:
                for license_id in licenses:
                    if license_id in policy_data["obligations"]:
                        if license_id not in obligations:
                            obligations[license_id] = {}
                        obligations[license_id].update(policy_data["obligations"][license_id])

        # Check for modular per-license files first (preferred)
        licenses_dir = Path(data_dir) / "licenses"
        if licenses_dir.exists():
            for license_id in licenses:
                license_data = self.lookup_license_data(license_id, data_dir) or {}
                # Per-license JSON files wrap the record in a "license" key
                license_record = license_data.get("license", license_data)
                license_obligations = license_record.get("obligations", [])
                if license_obligations:
                    if license_id not in obligations:
                        obligations[license_id] = {}
                    obligations[license_id]["obligations"] = license_obligations
        else:
            # Fallback to legacy obligation database for backward compatibility
            obligation_db_path = Path(data_dir) / "obligation_database.json"
            if obligation_db_path.exists():
                try:
                    with open(obligation_db_path) as f:
                        obligation_db = json.load(f)

                    for license_id in licenses:
                        if license_id in obligation_db.get("licenses", {}):
                            license_obligations = obligation_db["licenses"][license_id].get("obligations", [])
                            if license_obligations:
                                if license_id not in obligations:
                                    obligations[license_id] = {}
                                obligations[license_id]["obligations"] = license_obligations
                except Exception:
                    # If we can't load the obligation database, just continue with policy-based obligations
                    pass

        return obligations

    def lookup_license_data(self, license_id: str, data_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Lookup detailed information about a license.

        Args:
            license_id: SPDX license identifier (validated for security)
            data_dir: Optional data directory path

        Returns:
            License data dictionary if found, None otherwise

        Raises:
            ValueError: If license_id contains invalid characters or path separators
        """
        # Validate license_id to prevent path traversal attacks
        validate_license_id(license_id)

        data_dir = self.resolve_data_dir(data_dir)
        licenses_dir = Path(data_dir) / "licenses"
        if licenses_dir.exists():
            license_file = licenses_dir / "json" / f"{license_id}.json"

            # Additional safety check: verify path stays within licenses_dir
            try:
                license_file.resolve().relative_to(licenses_dir.resolve())
            except ValueError:
                # Path escaped the licenses directory
                return None

            if license_file.exists():
                try:
                    with open(license_file) as f:
                        license_data = json.load(f)
                    return license_data
                except Exception:
                    pass
        return None

    def resolve_data_dir(self, data_dir: Optional[str] = None) -> str:
        """Provide a default data directory if none is specified."""
        if data_dir is None:
            data_dir = str(Path(__file__).parent.parent / "data")
        return data_dir
