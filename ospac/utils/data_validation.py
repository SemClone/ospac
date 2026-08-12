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

import re

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
    # Pinned after a deliberate reclassification: every structured field matches LGPL-2.1,
    # so it belongs in the same category rather than in strong copyleft.
    "LGPLLR": {
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

# 'noncommercial' covers licenses that permit use, modification and
# redistribution but forbid commercial use (CC-BY-NC-*, PolyForm-Noncommercial).
# They cannot sit in 'permissive': policy rules match on license_type, and a
# permissive-allow rule would approve them for commercial distribution.
# 'no_derivatives' covers licenses that permit verbatim redistribution, including
# commercially, but forbid distributing modified versions (the CC BY-ND family). They
# cannot sit in 'permissive' for the same reason 'noncommercial' cannot: policy rules
# match on license_type, and a permissive-approve rule would silently bless them.
VALID_TYPES = {"permissive", "copyleft_strong", "copyleft_weak", "public_domain",
               "network_copyleft", "source_available", "proprietary", "noncommercial",
               "no_derivatives", "unknown"}
# 'derivative' is valid for share-alike licenses (CC-BY-SA etc.) where only derivative
# works must use the same license, not the whole combined work.
VALID_CONTAMINATION = {"none", "module", "full", "derivative", "unknown"}


def _id_has_component(identifier: str, component: str) -> bool:
    """
    True if ``component`` is a hyphen-delimited component of the SPDX identifier.

    SPDX ids like CC-BY-NC-SA-4.0 encode restrictions as uppercase components
    (NC, ND, SA). Splitting on hyphens keeps the match exact: a naive substring
    test would wrongly flag ids that merely contain the letters, such as NCSA,
    NCL, HPND, NASA-1.3 or SAX-PD.
    """
    return component in identifier.split("-")


def _name_has_word(name: str, word: str) -> bool:
    """
    True if ``word`` (lowercase letters only) appears in the license name once
    spacing, hyphens and case are ignored. The dataset spells the restrictions
    inconsistently ("NonCommercial", "Non Commercial", "Non-Commercial",
    "Noncommercial", "Share Alike"), so compare with everything but letters
    stripped.
    """
    return word in re.sub(r"[^a-z]", "", name.lower())


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

    # Restriction semantics derivable from the identifier or name.
    # These caught a silent generation failure where a fallback wrote
    # permissive defaults into NonCommercial / NoDerivatives / ShareAlike
    # records. Public domain dedications (CC0-1.0, CC-PDDC) have no NC/ND/SA
    # component and no matching name word, so they are not caught here.
    spdx_id = str(lic.get("spdx_id") or lid)
    name = str(lic.get("name") or "")

    noncommercial = _id_has_component(spdx_id, "NC") or _name_has_word(name, "noncommercial")
    # Singular stem so both NoDerivative and NoDerivatives spellings match.
    noderivatives = _id_has_component(spdx_id, "ND") or _name_has_word(name, "noderivative")
    sharealike = _id_has_component(spdx_id, "SA") or _name_has_word(name, "sharealike")

    if noncommercial and props.get("commercial_use") is not False:
        err(f"NonCommercial license must have properties.commercial_use false, "
            f"got {props.get('commercial_use')!r}")
    if noderivatives and props.get("modification") is not False:
        err(f"NoDerivatives license must have properties.modification false, "
            f"got {props.get('modification')!r}")
    if sharealike and reqs.get("same_license") is not True:
        err(f"ShareAlike license must have requirements.same_license true, "
            f"got {reqs.get('same_license')!r}")

    # The type must be honest about what the booleans say, because policy rules match on
    # license_type. These are direction-specific: a record whose booleans state a
    # restriction may not sit in a category that policy rules treat as unrestricted.
    if props.get("commercial_use") is False and lic.get("type") != "noncommercial":
        err(f"properties.commercial_use false requires type 'noncommercial', got "
            f"'{lic.get('type')}'; any other type bypasses the noncommercial policy rules")
    if props.get("modification") is False and lic.get("type") == "permissive":
        err("type 'permissive' contradicts properties.modification false, "
            "a permissive license permits modification")
    if reqs.get("same_license") is True and lic.get("type") in ("permissive", "public_domain"):
        err(f"requirements.same_license true contradicts type '{lic.get('type')}', "
            "a share-alike term binds derivative works")

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
