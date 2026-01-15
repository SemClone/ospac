"""
Input validation utilities for OSPAC.

This module provides security-focused input validation to prevent
injection attacks and path traversal vulnerabilities.
"""

import re
from pathlib import Path
from typing import Optional


def validate_license_id(license_id: str, allow_empty: bool = False) -> str:
    """
    Validate that a license ID is safe to use in file paths.

    This prevents path traversal attacks by ensuring the license_id
    conforms to valid SPDX license identifier format.

    Valid SPDX license IDs contain only:
    - Alphanumeric characters (A-Z, a-z, 0-9)
    - Dots (.)
    - Hyphens (-)
    - Plus signs (+)

    Args:
        license_id: The license identifier to validate
        allow_empty: Whether to allow empty strings (default: False)

    Returns:
        The validated license_id (unchanged if valid)

    Raises:
        ValueError: If the license_id contains invalid characters or path separators

    Examples:
        >>> validate_license_id("MIT")
        'MIT'
        >>> validate_license_id("GPL-3.0")
        'GPL-3.0'
        >>> validate_license_id("Apache-2.0")
        'Apache-2.0'
        >>> validate_license_id("../../../etc/passwd")
        Traceback (most recent call last):
            ...
        ValueError: Invalid license ID format: '../../../etc/passwd'. License IDs must contain only alphanumeric characters, dots, hyphens, and plus signs.
    """
    # Handle empty string case
    if not license_id:
        if allow_empty:
            return license_id
        raise ValueError("License ID cannot be empty")

    # Check for path separators (catches most obvious path traversal attempts)
    if '/' in license_id or '\\' in license_id:
        raise ValueError(
            f"Invalid license ID format: '{license_id}'. "
            "License IDs cannot contain path separators (/ or \\)."
        )

    # Reject relative path components
    if license_id in ('.', '..') or license_id.startswith('./') or license_id.startswith('../'):
        raise ValueError(
            f"Invalid license ID format: '{license_id}'. "
            "License IDs cannot be relative path components."
        )

    # Validate against SPDX license ID format
    # SPDX IDs contain only: alphanumeric, dots, hyphens, plus
    # Must start with alphanumeric character
    # Use fullmatch to ensure entire string matches (not just prefix)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-+]*', license_id):
        raise ValueError(
            f"Invalid license ID format: '{license_id}'. "
            "License IDs must start with alphanumeric and contain only alphanumeric characters, dots, hyphens, and plus signs."
        )

    return license_id


def validate_license_path(
    license_id: str,
    base_dir: Path,
    filename: str
) -> Path:
    """
    Validate that a constructed file path stays within the base directory.

    This provides defense-in-depth by verifying that even after path
    construction, the resulting path doesn't escape the intended directory.

    Args:
        license_id: The license identifier (should be pre-validated)
        base_dir: The base directory that files must be within
        filename: The filename pattern (e.g., "{license_id}.json")

    Returns:
        The validated absolute path

    Raises:
        ValueError: If the resolved path escapes the base directory

    Examples:
        >>> base = Path("/data/licenses")
        >>> validate_license_path("MIT", base, "MIT.json")
        PosixPath('/data/licenses/MIT.json')
    """
    # Construct the path
    target_path = base_dir / filename

    # Resolve both paths to absolute, normalized paths
    try:
        base_resolved = base_dir.resolve()
        target_resolved = target_path.resolve()

        # Verify target is within base directory
        target_resolved.relative_to(base_resolved)

    except ValueError:
        raise ValueError(
            f"Security violation: License ID '{license_id}' resulted in path outside "
            f"the licenses directory. Attempted path: {target_path}"
        )

    return target_resolved
