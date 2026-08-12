"""
Shared validation rules for the license JSON dataset.

This module is the single source of truth for the dataset validation rules.
It is used by two callers:

- the ``ospac data validate`` CLI command (``ospac/cli/commands.py``), which
  must work from an installed package, and
- the maintainer script ``scripts/validate_data.py``, which is only present
  in a source checkout (packaging ships ``ospac*`` only).

Keep all rule changes here so both callers stay in sync automatically.

"""

# Known-correct values for well-known licenses, used as spot checks.
KNOWN_LICENSES = {
    "Apache-2.0": {
        "type": "permissive",
        "properties": {"patent_grant": True},
        "requirements": {"disclose_source": False, "same_license": False},
        "spdx_metadata": {"is_osi_approved": True},
    },
    "MIT": {
        "type": "permissive",
        "requirements": {"disclose_source": False, "same_license": False},
        "spdx_metadata": {"is_osi_approved": True},
    },
    "GPL-3.0-only": {
        "type": "copyleft_strong",
        "requirements": {"disclose_source": True, "same_license": True},
        "spdx_metadata": {"is_osi_approved": True},
    },
    "GPL-2.0-only": {
        "type": "copyleft_strong",
        "requirements": {"disclose_source": True, "same_license": True},
        "spdx_metadata": {"is_osi_approved": True},
    },
    "LGPL-2.1-only": {
        "type": "copyleft_weak",
        "requirements": {"disclose_source": True},
        "spdx_metadata": {"is_osi_approved": True},
    },
    "LGPL-3.0-only": {
        "type": "copyleft_weak",
        "requirements": {"disclose_source": True},
        "spdx_metadata": {"is_osi_approved": True},
    },
    # Deprecated aliases of the LGPL identifiers above. Spot checked explicitly because
    # they were classified copyleft_strong while their modern equivalents were weak, and
    # nothing here caught the disagreement.
    "LGPL-2.1": {
        "type": "copyleft_weak",
        "requirements": {"disclose_source": True},
    },
    "LGPL-3.0": {
        "type": "copyleft_weak",
        "requirements": {"disclose_source": True},
    },
    "AGPL-3.0-only": {
        "type": "copyleft_strong",
        "requirements": {"disclose_source": True, "same_license": True, "network_use_disclosure": True},
        "spdx_metadata": {"is_osi_approved": True},
    },
    "BSD-2-Clause": {
        "type": "permissive",
        "requirements": {"disclose_source": False, "same_license": False},
        "spdx_metadata": {"is_osi_approved": True},
    },
    "BSD-3-Clause": {
        "type": "permissive",
        "requirements": {"disclose_source": False, "same_license": False},
        "spdx_metadata": {"is_osi_approved": True},
    },
    "CC0-1.0": {
        "type": "public_domain",
        "requirements": {"disclose_source": False, "same_license": False},
    },
    "ISC": {
        "type": "permissive",
        "spdx_metadata": {"is_osi_approved": True},
    },
    "MPL-2.0": {
        "type": "copyleft_weak",
        "spdx_metadata": {"is_osi_approved": True},
    },
}

REQUIRED_TOP_FIELDS = {"id", "name", "type", "spdx_id", "properties", "requirements",
                        "limitations", "compatibility", "obligations", "key_requirements",
                        "spdx_metadata"}

REQUIRED_PROPERTIES = {"commercial_use", "distribution", "modification", "patent_grant", "private_use"}
REQUIRED_REQUIREMENTS = {"disclose_source", "include_license", "include_copyright",
                          "same_license", "network_use_disclosure", "state_changes"}
REQUIRED_LIMITATIONS = {"liability", "warranty", "trademark_use"}
REQUIRED_COMPAT_KEYS = {"static_linking", "dynamic_linking", "contamination_effect"}
REQUIRED_COMPAT_LINK_KEYS = {"compatible_with", "incompatible_with", "requires_review"}

VALID_TYPES = {"permissive", "copyleft_strong", "copyleft_weak", "public_domain",
               "network_copyleft", "source_available", "proprietary", "unknown"}
# 'derivative' is valid for share-alike licenses (CC-BY-SA etc.) where only derivative
# works must use the same license, not the whole combined work.
VALID_CONTAMINATION = {"none", "module", "full", "derivative", "unknown"}


def validate_license(lid: str, lic: dict) -> tuple[list, list]:
    """Return (errors, warnings) for one unwrapped license record."""
    errors = []
    warnings = []

    def err(msg): errors.append(msg)
    def warn(msg): warnings.append(msg)

    # Top-level fields
    missing_top = REQUIRED_TOP_FIELDS - set(lic.keys())
    for f in sorted(missing_top):
        err(f"missing top-level field '{f}'")

    # id / name / type
    if lic.get("id") != lid:
        err(f"id field '{lic.get('id')}' does not match filename '{lid}'")
    if lic.get("name", "") == lid:
        warn("name is same as id, should be human-readable (e.g. 'MIT License')")
    lic_type_raw = lic.get("type", "")
    if lic_type_raw and lic_type_raw not in VALID_TYPES:
        if "|" in lic_type_raw:
            # Ambiguous type on a genuinely grey license: warn, don't fail
            warn(f"ambiguous type '{lic_type_raw}', resolve to one of {VALID_TYPES}")
        else:
            err(f"invalid type '{lic_type_raw}', must be one of {VALID_TYPES}")

    # properties
    props = lic.get("properties", {})
    for f in REQUIRED_PROPERTIES - set(props.keys()):
        err(f"properties.{f} missing")
    for f, v in props.items():
        if not isinstance(v, bool):
            err(f"properties.{f} must be bool, got {type(v).__name__}")

    # requirements
    reqs = lic.get("requirements", {})
    for f in REQUIRED_REQUIREMENTS - set(reqs.keys()):
        warn(f"requirements.{f} missing")
    for f, v in reqs.items():
        if not isinstance(v, bool):
            err(f"requirements.{f} must be bool, got {type(v).__name__}")

    # limitations
    lims = lic.get("limitations", {})
    for f in REQUIRED_LIMITATIONS - set(lims.keys()):
        warn(f"limitations.{f} missing")

    # compatibility
    compat = lic.get("compatibility", {})
    for f in REQUIRED_COMPAT_KEYS - set(compat.keys()):
        err(f"compatibility.{f} missing")

    for link in ("static_linking", "dynamic_linking"):
        section = compat.get(link, {})
        if not isinstance(section, dict):
            err(f"compatibility.{link} must be a dict")
            continue
        for f in REQUIRED_COMPAT_LINK_KEYS - set(section.keys()):
            warn(f"compatibility.{link}.{f} missing")
        # At least some entries should be non-empty
        if (isinstance(section.get("compatible_with"), list) and
                isinstance(section.get("incompatible_with"), list) and
                not section["compatible_with"] and not section["incompatible_with"]):
            warn(f"compatibility.{link} has empty compatible_with AND incompatible_with")

    contamination = compat.get("contamination_effect", "")
    if contamination and contamination not in VALID_CONTAMINATION:
        err(f"compatibility.contamination_effect '{contamination}' not in {VALID_CONTAMINATION}")

    # obligations / key_requirements
    obligs = lic.get("obligations", [])
    lic_type = lic.get("type", "")
    if not obligs and lic_type not in ("public_domain",):
        warn("obligations list is empty")
    if not isinstance(obligs, list):
        err(f"obligations must be a list, got {type(obligs).__name__}")

    krs = lic.get("key_requirements", [])
    if not isinstance(krs, list):
        err(f"key_requirements must be a list, got {type(krs).__name__}")

    # spdx_metadata
    meta = lic.get("spdx_metadata", {})
    for f in ("is_osi_approved", "is_fsf_libre", "is_deprecated"):
        if f not in meta:
            warn(f"spdx_metadata.{f} missing")
        elif not isinstance(meta[f], bool):
            err(f"spdx_metadata.{f} must be bool, got {type(meta[f]).__name__}")

    # Known-license spot checks
    if lid in KNOWN_LICENSES:
        spec = KNOWN_LICENSES[lid]
        if "type" in spec and lic.get("type") != spec["type"]:
            err(f"known-license: type should be '{spec['type']}', got '{lic.get('type')}'")
        for section, expected in spec.items():
            if section == "type":
                continue
            actual = lic.get(section, {})
            for k, v in expected.items():
                if actual.get(k) != v:
                    err(f"known-license: {section}.{k} should be {v}, got {actual.get(k)!r}")

    return errors, warnings
