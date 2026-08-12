"""
Tests for OSPAC data models.
"""

import os
import subprocess
import sys

import pytest

from ospac.models.license import License
from ospac.models.policy import Policy, Rule
from ospac.models.compliance import (
    ComplianceResult,
    PolicyResult,
    ComplianceStatus,
    ActionType
)


class TestLicense:
    """Test the License model."""

    def test_create_license(self):
        """Test creating a license."""
        license = License(
            id="MIT",
            name="MIT License",
            type="permissive",
            spdx_id="MIT"
        )

        assert license.id == "MIT"
        assert license.name == "MIT License"
        assert license.type == "permissive"
        assert license.spdx_id == "MIT"

    def test_license_compatibility_permissive(self):
        """Test compatibility between permissive licenses."""
        mit = License(
            id="MIT",
            name="MIT License",
            type="permissive"
        )

        bsd = License(
            id="BSD-3-Clause",
            name="BSD 3-Clause",
            type="permissive"
        )

        assert mit.is_compatible_with(bsd) is True
        assert bsd.is_compatible_with(mit) is True

    def test_license_compatibility_with_rules(self):
        """Test license compatibility with explicit rules."""
        gpl = License(
            id="GPL-3.0",
            name="GPL v3",
            type="copyleft_strong",
            compatibility={
                "static_linking": {
                    "compatible_with": ["GPL-3.0", "AGPL-3.0"],
                    "incompatible_with": ["MIT", "permissive"]
                }
            }
        )

        mit = License(
            id="MIT",
            name="MIT License",
            type="permissive"
        )

        assert gpl.is_compatible_with(mit, "static_linking") is False

    def test_get_obligations(self):
        """Test getting license obligations."""
        license = License(
            id="Apache-2.0",
            name="Apache License 2.0",
            type="permissive",
            requirements={
                "include_license": True,
                "include_copyright": True,
                "include_notice": True,
                "state_changes": True
            }
        )

        obligations = license.get_obligations()

        assert "Include license text" in obligations
        assert "Include copyright notice" in obligations
        assert "State changes made to the code" in obligations

    def test_license_from_dict(self):
        """Test creating license from dictionary."""
        data = {
            "id": "MIT",
            "name": "MIT License",
            "type": "permissive",
            "spdx_id": "MIT",
            "properties": {"commercial_use": True},
            "requirements": {"include_license": True}
        }

        license = License.from_dict(data)

        assert license.id == "MIT"
        assert license.properties["commercial_use"] is True
        assert license.requirements["include_license"] is True


class TestRule:
    """Test the Rule model."""

    def test_create_rule(self):
        """Test creating a rule."""
        rule = Rule(
            id="test_rule",
            description="Test rule",
            when={"license": "MIT"},
            then={"action": "allow"},
            priority=10
        )

        assert rule.id == "test_rule"
        assert rule.priority == 10

    def test_rule_matches(self):
        """Test if rule matches context."""
        rule = Rule(
            id="gpl_rule",
            description="GPL rule",
            when={"license": "GPL-3.0", "usage": "static"},
            then={"action": "deny"}
        )

        # Matching context
        context = {"license": "GPL-3.0", "usage": "static"}
        assert rule.matches(context) is True

        # Non-matching context
        context = {"license": "MIT", "usage": "static"}
        assert rule.matches(context) is False

    def test_rule_matches_with_list(self):
        """Test rule matching with list values."""
        rule = Rule(
            id="permissive_rule",
            description="Permissive licenses",
            when={"license": ["MIT", "BSD", "Apache"]},
            then={"action": "allow"}
        )

        assert rule.matches({"license": "MIT"}) is True
        assert rule.matches({"license": "BSD"}) is True
        assert rule.matches({"license": "GPL"}) is False


class TestPolicy:
    """Test the Policy model."""

    def test_create_policy(self):
        """Test creating a policy."""
        policy = Policy(
            name="Test Policy",
            version="1.0"
        )

        assert policy.name == "Test Policy"
        assert policy.version == "1.0"
        assert len(policy.rules) == 0

    def test_add_rule_to_policy(self):
        """Test adding rules to policy."""
        policy = Policy(name="Test", version="1.0")

        rule1 = Rule(
            id="rule1",
            description="First rule",
            when={},
            then={"action": "allow"},
            priority=5
        )

        rule2 = Rule(
            id="rule2",
            description="Second rule",
            when={},
            then={"action": "deny"},
            priority=10
        )

        policy.add_rule(rule1)
        policy.add_rule(rule2)

        assert len(policy.rules) == 2
        # Higher priority should be first
        assert policy.rules[0].id == "rule2"
        assert policy.rules[1].id == "rule1"

    def test_evaluate_policy(self):
        """Test evaluating a policy."""
        policy = Policy(name="Test", version="1.0")

        rule = Rule(
            id="mit_allow",
            description="Allow MIT",
            when={"license": "MIT"},
            then={
                "action": "allow",
                "severity": "info",
                "message": "MIT is allowed"
            }
        )

        policy.add_rule(rule)

        context = {"license": "MIT"}
        results = policy.evaluate(context)

        assert len(results) == 1
        assert results[0]["rule_id"] == "mit_allow"
        assert results[0]["action"] == "allow"
        assert results[0]["message"] == "MIT is allowed"

    def test_policy_from_dict(self):
        """Test creating policy from dictionary."""
        data = {
            "name": "Enterprise Policy",
            "version": "2.0",
            "rules": [
                {
                    "id": "no_gpl",
                    "description": "No GPL",
                    "when": {"license": "GPL"},
                    "then": {"action": "deny"},
                    "priority": 100
                }
            ],
            "extends": "base_policy",
            "metadata": {"author": "test"}
        }

        policy = Policy.from_dict(data)

        assert policy.name == "Enterprise Policy"
        assert policy.version == "2.0"
        assert len(policy.rules) == 1
        assert policy.extends == "base_policy"
        assert policy.metadata["author"] == "test"


class TestComplianceResult:
    """Test the ComplianceResult model."""

    def test_create_compliance_result(self):
        """Test creating a compliance result."""
        result = ComplianceResult(
            status=ComplianceStatus.COMPLIANT,
            licenses_checked=["MIT", "Apache-2.0"]
        )

        assert result.status == ComplianceStatus.COMPLIANT
        assert result.is_compliant is True
        assert result.needs_review is False
        assert len(result.licenses_checked) == 2

    def test_add_violation(self):
        """Test adding violations."""
        result = ComplianceResult(status=ComplianceStatus.COMPLIANT)

        result.add_violation("rule1", "GPL not allowed", "error")

        assert result.status == ComplianceStatus.NON_COMPLIANT
        assert len(result.violations) == 1
        assert result.violations[0]["rule_id"] == "rule1"

    def test_add_warning(self):
        """Test adding warnings."""
        result = ComplianceResult(status=ComplianceStatus.COMPLIANT)

        result.add_warning("rule2", "Consider reviewing")

        assert result.status == ComplianceStatus.WARNING
        assert len(result.warnings) == 1

    def test_from_policy_result(self):
        """Test creating from PolicyResult."""
        policy_result = PolicyResult(
            rule_id="test",
            action=ActionType.DENY,
            severity="error",
            message="License denied",
            requirements=["requirement1"],
            remediation="Use MIT instead"
        )

        compliance = ComplianceResult.from_policy_result(policy_result)

        assert compliance.status == ComplianceStatus.NON_COMPLIANT
        assert len(compliance.violations) == 1
        assert "requirement1" in compliance.obligations
        assert "Use MIT instead" in compliance.required_actions

    def test_compliance_to_dict(self):
        """Test converting to dictionary."""
        result = ComplianceResult(
            status=ComplianceStatus.WARNING,
            licenses_checked=["MIT"]
        )
        result.add_warning("rule1", "Check this")

        data = result.to_dict()

        assert data["status"] == "warning"
        assert data["is_compliant"] is False
        assert data["needs_review"] is False
        assert len(data["warnings"]) == 1


class TestPolicyResult:
    """Test the PolicyResult model."""

    def test_create_policy_result(self):
        """Test creating a policy result."""
        result = PolicyResult(
            rule_id="test_rule",
            action=ActionType.ALLOW,
            severity="info",
            message="All good"
        )

        assert result.rule_id == "test_rule"
        assert result.action == ActionType.ALLOW
        assert result.severity == "info"
        assert result.message == "All good"

    def test_aggregate_results(self):
        """Test aggregating multiple results."""
        results = [
            PolicyResult(
                rule_id="rule1",
                action=ActionType.ALLOW,
                severity="info",
                requirements=["req1"]
            ),
            PolicyResult(
                rule_id="rule2",
                action=ActionType.DENY,
                severity="error",
                requirements=["req2"]
            ),
            PolicyResult(
                rule_id="rule3",
                action=ActionType.FLAG_FOR_REVIEW,
                severity="warning",
                requirements=["req1", "req3"]
            )
        ]

        aggregated = PolicyResult.aggregate(results)

        assert aggregated.rule_id == "aggregate"
        # DENY has highest priority
        assert aggregated.action == ActionType.DENY
        # Error has highest severity
        assert aggregated.severity == "error"
        # All unique requirements
        assert len(aggregated.requirements) == 3
        assert "req1" in aggregated.requirements
        assert "req2" in aggregated.requirements
        assert "req3" in aggregated.requirements

    def test_aggregate_requirements_preserve_first_seen_order(self):
        """Aggregated requirements keep first-seen order and drop duplicates."""
        results = [
            PolicyResult(
                rule_id="rule1",
                action=ActionType.ALLOW,
                severity="info",
                requirements=["include_license", "include_copyright"]
            ),
            PolicyResult(
                rule_id="rule2",
                action=ActionType.ALLOW,
                severity="info",
                requirements=["include_copyright", "state_changes"]
            ),
            PolicyResult(
                rule_id="rule3",
                action=ActionType.ALLOW,
                severity="info",
                requirements=["include_license", "include_notice"]
            )
        ]

        aggregated = PolicyResult.aggregate(results)

        # Exact sequence: duplicates collapse to their first occurrence
        assert aggregated.requirements == [
            "include_license",
            "include_copyright",
            "state_changes",
            "include_notice",
        ]

    def test_aggregate_requirements_stable_across_hash_seeds(self):
        """Aggregation order must not depend on string hash randomization."""
        script = (
            "from ospac.models.compliance import PolicyResult, ActionType\n"
            "results = [\n"
            "    PolicyResult(rule_id='r1', action=ActionType.ALLOW,\n"
            "                 requirements=['include_license', 'include_copyright']),\n"
            "    PolicyResult(rule_id='r2', action=ActionType.ALLOW,\n"
            "                 requirements=['state_changes', 'include_copyright']),\n"
            "]\n"
            "print(PolicyResult.aggregate(results).requirements)\n"
        )

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        outputs = set()
        for seed in ("0", "1", "42"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [repo_root, env.get("PYTHONPATH")])
            )
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            outputs.add(proc.stdout.strip())

        assert outputs == {
            "['include_license', 'include_copyright', 'state_changes']"
        }

    def test_aggregate_empty_results(self):
        """Test aggregating empty results."""
        aggregated = PolicyResult.aggregate([])

        assert aggregated.rule_id == "aggregate"
        assert aggregated.action == ActionType.ALLOW
        assert aggregated.severity == "info"
        assert aggregated.message == "No policies matched"

    def test_explicit_approve_outranks_default_allow(self):
        """
        A rule that states no action falls back to ALLOW. When another rule explicitly
        approves, the aggregate must report approve: callers are told that allow means no
        rule matched and treat it as a policy bug, so letting an actionless rule report
        allow made a correct policy look broken.
        """
        results = [
            PolicyResult(rule_id="explicit", action=ActionType.APPROVE, severity="info",
                         message="vetted"),
            PolicyResult(rule_id="actionless", action=ActionType.ALLOW, severity="info",
                         message="noted"),
        ]

        assert PolicyResult.aggregate(results).action == ActionType.APPROVE
        # Order of the inputs must not change the outcome.
        assert PolicyResult.aggregate(list(reversed(results))).action == ActionType.APPROVE

    def test_restrictive_actions_still_dominate_approve(self):
        """Raising APPROVE above ALLOW must not let it outrank a real restriction."""
        approve = PolicyResult(rule_id="a", action=ActionType.APPROVE, severity="info",
                               message="vetted")
        for stronger in (ActionType.DENY, ActionType.CONTAMINATE, ActionType.FLAG_FOR_REVIEW):
            other = PolicyResult(rule_id="b", action=stronger, severity="error",
                                 message="restricted")
            assert PolicyResult.aggregate([approve, other]).action == stronger
            assert PolicyResult.aggregate([other, approve]).action == stronger