"""
OSPAC utility functions.
"""

from ospac.utils.data_validation import KNOWN_LICENSES, validate_license
from ospac.utils.validation import canonical_spdx_id, validate_license_id, validate_license_path

__all__ = ["KNOWN_LICENSES", "validate_license", "validate_license_id", "validate_license_path"]
