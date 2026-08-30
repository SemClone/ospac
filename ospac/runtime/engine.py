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
from ospac.models.compliance import ComplianceResult, ComplianceStatus, PolicyResult, ActionType
from ospac.utils.validation import validate_license_id
from ospac.aliases import (LicenseResolution, matchable_license_id,
                           resolve_license)

# What each action answers, for deciding whether two readings of one declaration agree.
# Two actions in one class are one answer: approve and allow are both permissions, deny
# and contaminate are both refusals. Leaving contaminate out downgraded a declaration
# whose every reading is refused to review, which is the direction that matters.
#
# ComplianceResult.from_policy_result maps contaminate to UNKNOWN rather than to
# NON_COMPLIANT. That is a separate question about one result's status and is left
# alone here; this table is only about agreement.
_COMPLIANCE_CLASS = {
    ActionType.APPROVE: ComplianceStatus.COMPLIANT,
    ActionType.ALLOW: ComplianceStatus.COMPLIANT,
    ActionType.FLAG_FOR_REVIEW: ComplianceStatus.REQUIRES_REVIEW,
    ActionType.DENY: ComplianceStatus.NON_COMPLIANT,
    ActionType.CONTAMINATE: ComplianceStatus.NON_COMPLIANT,
}


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

        A declared license is resolved through the shipped alias map before matching.
        Registries do not answer in SPDX, so "Apache 2.0" and "MIT License" reached no
        rule and came back needing review, which a consumer cannot tell apart from a
        considered ruling even though the two mean opposite things. Both spellings are
        offered to the rules rather than the resolved one replacing the input: a policy
        naming the deprecated GPL-2.0 keeps matching, and one naming GPL-2.0-only starts
        matching the same input.

        A declaration that names a license without naming which identifier is evaluated
        under every reading. "GNU Affero General Public License v3" is AGPL-3.0-only or
        AGPL-3.0-or-later and the default policy denies both for saas, so the verdict is
        deny and asserts nothing the declaration did not already carry. Where the
        readings disagree the answer is review, which is the honest one.

        Returns (aggregated PolicyResult, {license_id: per-license PolicyResult}).
        base_context carries the shared fields (distribution_type, context, linking_type);
        the per-license fields are filled in here.
        """
        per_license: Dict[str, PolicyResult] = {}
        for license_id in licenses:
            results = []
            for identifier, spellings in self._readings(license_id):
                license_type = self.resolve_license_type(identifier)
                ctx = dict(base_context)
                ctx["licenses"] = spellings
                ctx["licenses_found"] = spellings
                ctx["license_type"] = [license_type] if license_type else []
                results.append(self.evaluate(ctx))
            per_license[license_id] = self._agree_or_review(results, license_id)

        combined = PolicyResult.aggregate(list(per_license.values()))
        return combined, per_license

    @staticmethod
    def resolve_licenses(licenses: List[str]) -> Dict[str, LicenseResolution]:
        """
        What the alias map made of each declared license, keyed by the string given.

        A caller that can see "Apache 2.0" became Apache-2.0 can trust the verdict was
        about the license it meant; one that cannot has to re-derive the mapping to find
        out, which is the duplicated alias table this data exists to remove.
        """
        return {license_id: resolve_license(license_id) for license_id in licenses}

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
        """
        Check if two licenses are compatible.

        A declaration that names a license without naming its identifier is checked
        under every reading it could have. "gplv2" is GPL-2.0-only or GPL-2.0-or-later
        and BSD-4-Clause's record names both incompatible, so the conflict holds
        whichever the document meant and saying so asserts nothing extra. Where the
        readings disagree the declaration decides nothing on its own, and the answer is
        review rather than the reading that happens to be checked first.
        """
        readings1 = self._readings(license1)
        readings2 = self._readings(license2)

        per_reading = []
        for identifier1, spellings1 in readings1:
            for identifier2, spellings2 in readings2:
                # Types come from the reading's own identifier. Taking the union across
                # candidates let a permissive reading be judged as the network-copyleft
                # one it shares a name with, which made the readings look like they
                # agreed: "cryptographic autonomy" is CAL-1.0 or its combined-work
                # exception, and those are network_copyleft and permissive.
                license_types = []
                for identifier in (identifier1, identifier2):
                    try:
                        license_data = self.lookup_license_data(identifier)
                    except ValueError:
                        continue
                    license_type = (license_data or {}).get("license", {}).get("type")
                    if license_type and license_type not in license_types:
                        license_types.append(license_type)

                # A compatibility check asks whether a conflict is known, so no rule
                # matching means "no known conflict", not "needs review". The review
                # default belongs to permission questions; applying it here made every
                # license read as incompatible with itself, since this context carries
                # no distribution_type and most rules therefore cannot match.
                spelled = [self.evaluate({
                    "license1": spelling1,
                    "license2": spelling2,
                    "license_type": license_types,
                    "compatibility_context": context,
                    # Mirror evaluate's derivation so linking rules can fire on pairs
                    # too. check -c static_linking previously reached no rule that
                    # matched on linking_type, because the field was never set here.
                    "linking_type": context if "linking" in context else None,
                }, when_unmatched="allow")
                    for spelling1 in spellings1 for spelling2 in spellings2]
                per_reading.append(
                    PolicyResult.aggregate(spelled, when_unmatched="allow"))

        result = self._agree_or_review(per_reading, f"{license1} and {license2}",
                                       when_unmatched="allow")
        compliance = ComplianceResult.from_policy_result(result)
        # The result always reported an empty licenses_checked even though exactly two
        # licenses were checked.
        compliance.licenses_checked = [license1, license2]

        # The dataset's known-incompatible pairs outrank a category-level approval,
        # the same precedence named exceptions get in License.is_compatible_with.
        # Policy rules only enumerated some of the pairs, so GPL-2.0 with BSD-4-Clause
        # was reported compliant while the records named each other incompatible. The
        # list a record holds is canonical ids, so a declared name compared against it
        # matches nothing and a known incompatible pair reads as clean. Every reading
        # has to conflict: one that does not is a reading under which the pair is fine,
        # and the declaration did not rule it out.
        if compliance.is_compliant or compliance.needs_review:
            conflicts = [self._dataset_names_incompatible(identifier1, identifier2)
                         or self._dataset_names_incompatible(identifier2, identifier1)
                         for identifier1, _ in readings1
                         for identifier2, _ in readings2]
            if all(conflicts):
                compliance.status = ComplianceStatus.NON_COMPLIANT
                compliance.add_violation(
                    "dataset_known_incompatibility",
                    f"{license1} and {license2} are a known incompatible pair in the "
                    f"license dataset")
            elif any(conflicts):
                # A conflict under some readings and not others. Denying would assert a
                # reading the declaration never made, and reporting clean would hide one
                # the dataset positively knows about. "Apache License" is 1.0, 1.1 or
                # 2.0 and only 2.0 conflicts with GPL-2.0.
                compliance.status = ComplianceStatus.REQUIRES_REVIEW
                compliance.add_warning(
                    "dataset_incompatibility_under_some_readings",
                    f"{license1} and {license2} are a known incompatible pair under "
                    f"some readings of the declaration but not all")
        return compliance

    @staticmethod
    def _agree_or_review(results: List[PolicyResult], subject: str,
                         when_unmatched: str = "review") -> PolicyResult:
        """
        The verdict the readings share, or review when they do not share one.

        Most-restrictive-wins is right across licenses, where every one of them applies.
        It is wrong across readings of one declaration, where exactly one applies and
        nobody knows which: taking the strictest would assert an obligation the document
        may not carry. Agreement is the only thing a reading set can assert on its own.
        """
        # Agreement is about the outcome, not the word. approve and allow are one
        # compliance class, and a reading that matched an approval rule alongside one
        # that fell through to allow is two permissions, not a disagreement; reporting
        # review there would flag a pair every reading permits.
        if len({_COMPLIANCE_CLASS.get(result.action, result.action)
                for result in results}) == 1:
            agreed = PolicyResult.aggregate(results, when_unmatched=when_unmatched)
            if len(results) > 1:
                # aggregate() unions requirements, which is right across licenses that
                # all apply and wrong across readings where exactly one does. "Apache
                # License" is 1.0, 1.1 or 2.0 and all three are approved, but only 2.0
                # carries the NOTICE and state-changes obligations; reporting them for a
                # declaration that may be 1.0 states an obligation it does not have.
                shared = set(results[0].requirements or [])
                for result in results[1:]:
                    shared &= set(result.requirements or [])
                agreed.requirements = [requirement
                                       for requirement in (agreed.requirements or [])
                                       if requirement in shared]
            return agreed
        return PolicyResult(
            rule_id="ambiguous_declaration",
            action=ActionType.FLAG_FOR_REVIEW,
            severity="warning",
            message=f"{subject} evaluates differently depending on which identifier "
                    f"the declaration means",
            requirements=["Establish which identifier the declaration means"])

    def _readings(self, license_id: str) -> List[tuple]:
        """
        The identifiers a declared string could mean, each with the spellings that name it.

        One reading unless the declaration names a license without naming which
        identifier, in which case one per candidate. Readings are different licenses and
        have to agree before an answer is asserted; spellings are one license written two
        ways and any of them matching is a match, because a policy may be written against
        the caller's spelling or against the identifier and rules compare exact strings.

        A deprecated identifier carries the current one it stands for as a spelling. It
        keeps its own record, because a caller naming GPL-2.0 means GPL-2.0's record and
        its deprecation metadata, but a policy written against GPL-2.0-only is a policy
        about the same license and has to fire.
        """
        resolution = resolve_license(license_id)
        identifiers = resolution.candidates or [resolution.license_id or license_id]

        readings = []
        for identifier in identifiers:
            spellings = {identifier, license_id}
            try:
                record = self.lookup_license_data(identifier) or {}
            except ValueError:
                record = {}
            current = (record.get("license") or {}).get("alias_of")
            if current:
                spellings.add(current)
            readings.append((identifier, sorted(spellings)))
        return readings

    def _matchable_id(self, license_id: str) -> str:
        """The spelling a rule should be matched against. See matchable_license_id."""
        return matchable_license_id(license_id)

    def _dataset_names_incompatible(self, license_a: str, license_b: str) -> bool:
        """True if license_a's record names license_b in its incompatible list."""
        try:
            record = self.lookup_license_data(license_a)
        except ValueError:
            return False
        block = (((record or {}).get("license") or {}).get("compatibility") or {})
        incompatible = (block.get("static_linking") or {}).get("incompatible_with", [])
        return license_b in incompatible

    def get_obligations(self, licenses: List[str], data_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all obligations for the given licenses.

        Args:
            licenses: Declared license strings, SPDX identifiers or not
            data_dir: Optional data directory path

        Returns:
            Dictionary keyed by the string that was passed in. Each value is a
            dictionary that contains an "obligations" list from the license dataset,
            merged with any entries from obligations/ policy files. Licenses with no
            known obligations are omitted.

            Declared strings are resolved, so a policy naming Apache-2.0 answers for a
            caller passing "Apache 2.0". A declaration that names a license without
            naming which identifier reports only what every reading of it carries,
            because exactly one reading applies and nobody knows which.
        """
        # Use package data directory if not specified
        data_dir = self.resolve_data_dir(data_dir)

        obligations = {}
        for declared in licenses:
            per_reading = [self._obligations_for(identifier, data_dir)
                           for identifier, _ in self._readings(declared)]
            shared = self._shared_obligations(per_reading)
            if shared:
                obligations[declared] = shared
        return obligations

    def _obligations_for(self, license_id: str, data_dir: str) -> Dict[str, Any]:
        """The obligations one identifier carries, from the policies and the dataset."""
        entry: Dict[str, Any] = {}

        # Look for obligations in all obligation policy files
        for policy_name, policy_data in self.policies.items():
            if policy_name.startswith("obligations/") and "obligations" in policy_data:
                if license_id in policy_data["obligations"]:
                    entry.update(policy_data["obligations"][license_id])

        # Check for modular per-license files first (preferred)
        listed = []
        if (Path(data_dir) / "licenses").exists():
            # A ValueError is not caught: an id that reaches this and is not a licence
            # is a path, and refusing it is the point of the guard.
            license_data = self.lookup_license_data(license_id, data_dir) or {}
            # Per-license JSON files wrap the record in a "license" key
            listed = license_data.get("license", license_data).get("obligations", [])
        else:
            # Fallback to legacy obligation database for backward compatibility
            obligation_db_path = Path(data_dir) / "obligation_database.json"
            if obligation_db_path.exists():
                try:
                    with open(obligation_db_path) as f:
                        obligation_db = json.load(f)
                    listed = (obligation_db.get("licenses", {})
                              .get(license_id, {}).get("obligations", []))
                except Exception:
                    # If we can't load the obligation database, just continue with
                    # policy-based obligations
                    listed = []

        if listed:
            entry["obligations"] = listed
        return entry

    @staticmethod
    def _shared_obligations(per_reading: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        What every reading of one declaration carries.

        A single reading keeps everything it has. Several keep only the entries they all
        agree on: "Apache License" is 1.0, 1.1 or 2.0 and reporting 2.0's NOTICE
        obligation for it would state something a declaration meaning 1.0 does not.
        """
        if not per_reading:
            return {}
        if len(per_reading) == 1:
            return per_reading[0]

        shared = {key: value for key, value in per_reading[0].items()
                  if all(other.get(key) == value for other in per_reading[1:])}
        listed = [entry.get("obligations", []) for entry in per_reading]
        common = [obligation for obligation in listed[0]
                  if all(obligation in other for other in listed[1:])]
        if common:
            shared["obligations"] = common
        else:
            shared.pop("obligations", None)
        return shared

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
        # A registry does not answer in SPDX: PyPI's license field is free text by
        # construction and requests 2.31.0 declares "Apache 2.0", which names no file
        # here and is not even a legal identifier. Resolve first, so a declared name
        # reaches its record; an input that is already a shipped id keeps its own
        # record, and anything that resolves to nothing still fails validation and so
        # never reaches the filesystem.
        target = matchable_license_id(license_id)
        validate_license_id(target)
        return self._read_license_record(target, data_dir)

    def _read_license_record(self, license_id: str,
                             data_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Read one license record by exact id, or None if there is no such file."""
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
