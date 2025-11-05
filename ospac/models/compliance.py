"""
Compliance result models.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class ComplianceStatus(Enum):
    """Status of compliance check."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    WARNING = "warning"
    REQUIRES_REVIEW = "requires_review"
    UNKNOWN = "unknown"


class ActionType(Enum):
    """Action to take based on policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    FLAG_FOR_REVIEW = "flag_for_review"
    CONTAMINATE = "contaminate"
    APPROVE = "approve"


@dataclass
class PolicyResult:
    """Result of policy evaluation."""

    rule_id: str
    action: ActionType
    severity: str = "info"
    message: Optional[str] = None
    requirements: List[str] = field(default_factory=list)
    remediation: Optional[str] = None

    @classmethod
    def aggregate(cls, results: List["PolicyResult"]) -> "PolicyResult":
        """Aggregate multiple results into a single result."""
        if not results:
            return cls(
                rule_id="aggregate",
                action=ActionType.ALLOW,
                severity="info",
                message="No policies matched",
            )

        # Find the highest severity result
        severity_order = {"error": 3, "warning": 2, "info": 1}
        highest_severity = max(results, key=lambda r: severity_order.get(r.severity, 0))

        # Determine overall action (most restrictive wins)
        action_priority = {
            ActionType.DENY: 5,
            ActionType.CONTAMINATE: 4,
            ActionType.FLAG_FOR_REVIEW: 3,
            ActionType.ALLOW: 2,
            ActionType.APPROVE: 1,
        }

        most_restrictive = max(results, key=lambda r: action_priority.get(r.action, 0))

        # Combine all requirements
        all_requirements = []
        for result in results:
            all_requirements.extend(result.requirements)

        return cls(
            rule_id="aggregate",
            action=most_restrictive.action,
            severity=highest_severity.severity,
            message=f"Evaluated {len(results)} rules",
            requirements=list(set(all_requirements)),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "rule_id": self.rule_id,
            "action": self.action.value if isinstance(self.action, ActionType) else self.action,
            "severity": self.severity,
            "message": self.message,
            "requirements": self.requirements,
            "remediation": self.remediation,
        }


@dataclass
class ComplianceResult:
    """Final compliance result."""

    status: ComplianceStatus
    licenses_checked: List[str] = field(default_factory=list)
    violations: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    obligations: List[str] = field(default_factory=list)
    required_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_compliant(self) -> bool:
        """Check if the result is compliant."""
        return self.status == ComplianceStatus.COMPLIANT

    @property
    def needs_review(self) -> bool:
        """Check if manual review is required."""
        return self.status == ComplianceStatus.REQUIRES_REVIEW

    def add_violation(self, rule_id: str, message: str, severity: str = "error") -> None:
        """Add a violation to the result."""
        self.violations.append({
            "rule_id": rule_id,
            "message": message,
            "severity": severity,
        })
        if self.status != ComplianceStatus.NON_COMPLIANT:
            self.status = ComplianceStatus.NON_COMPLIANT

    def add_warning(self, rule_id: str, message: str) -> None:
        """Add a warning to the result."""
        self.warnings.append({
            "rule_id": rule_id,
            "message": message,
            "severity": "warning",
        })
        if self.status == ComplianceStatus.COMPLIANT:
            self.status = ComplianceStatus.WARNING

    @classmethod
    def from_policy_result(cls, policy_result: PolicyResult) -> "ComplianceResult":
        """Create a ComplianceResult from a PolicyResult."""
        result = cls(status=ComplianceStatus.UNKNOWN)

        if policy_result.action == ActionType.DENY:
            result.status = ComplianceStatus.NON_COMPLIANT
            if policy_result.message:
                result.add_violation(policy_result.rule_id, policy_result.message, policy_result.severity)

        elif policy_result.action == ActionType.FLAG_FOR_REVIEW:
            result.status = ComplianceStatus.REQUIRES_REVIEW
            if policy_result.message:
                result.add_warning(policy_result.rule_id, policy_result.message)

        elif policy_result.action in [ActionType.ALLOW, ActionType.APPROVE]:
            result.status = ComplianceStatus.COMPLIANT

        if policy_result.requirements:
            result.obligations.extend(policy_result.requirements)

        if policy_result.remediation:
            result.required_actions.append(policy_result.remediation)

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "is_compliant": self.is_compliant,
            "needs_review": self.needs_review,
            "licenses_checked": self.licenses_checked,
            "violations": self.violations,
            "warnings": self.warnings,
            "obligations": self.obligations,
            "required_actions": self.required_actions,
            "metadata": self.metadata,
        }