"""
OSPAC - Open Source Policy as Code

A comprehensive policy engine for automated OSS license compliance.
"""

from importlib.metadata import PackageNotFoundError, version as _installed_version

# Read the version from installed package metadata so pyproject.toml stays the single
# source of truth. The SPDX sync workflow bumps the patch version there on every dataset
# release, and a hardcoded literal here drifted behind it every month.
try:
    __version__ = _installed_version("ospac")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0.dev0"

from ospac.aliases import license_aliases, license_never_resolve
from ospac.runtime.engine import PolicyRuntime
from ospac.models.license import License
from ospac.models.policy import Policy
from ospac.models.compliance import ComplianceResult

__all__ = [
    "PolicyRuntime",
    "license_aliases",
    "license_never_resolve",
    "License",
    "Policy",
    "ComplianceResult",
]