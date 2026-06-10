#!/usr/bin/env python3
"""
Validate all license JSON files in ospac/data/licenses/json/.

Checks structural completeness, semantic correctness, and known-license
spot checks. Prints a summary and exits non-zero if any ERROR-level issues
are found. WARNING-level issues are reported but do not fail the exit code
unless --strict is passed.

Usage:
    python scripts/validate_data.py [--data-dir ospac/data] [--strict] [--json]
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# ── Known-correct values for well-known licenses ─────────────────────────────
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
    """Return (errors, warnings) for one license dict."""
    errors = []
    warnings = []

    def err(msg): errors.append(msg)
    def warn(msg): warnings.append(msg)

    # ── Top-level fields ──────────────────────────────────────────────────────
    missing_top = REQUIRED_TOP_FIELDS - set(lic.keys())
    for f in sorted(missing_top):
        err(f"missing top-level field '{f}'")

    # ── id / name / type ──────────────────────────────────────────────────────
    if lic.get("id") != lid:
        err(f"id field '{lic.get('id')}' does not match filename '{lid}'")
    if lic.get("name", "") == lid:
        warn("name is same as id — should be human-readable (e.g. 'MIT License')")
    lic_type_raw = lic.get("type", "")
    if lic_type_raw and lic_type_raw not in VALID_TYPES:
        if "|" in lic_type_raw:
            # LLM returned ambiguous type for a genuinely grey license — warn, don't fail
            warn(f"ambiguous type '{lic_type_raw}' — resolve to one of {VALID_TYPES}")
        else:
            err(f"invalid type '{lic_type_raw}' — must be one of {VALID_TYPES}")

    # ── properties ────────────────────────────────────────────────────────────
    props = lic.get("properties", {})
    for f in REQUIRED_PROPERTIES - set(props.keys()):
        err(f"properties.{f} missing")
    for f, v in props.items():
        if not isinstance(v, bool):
            err(f"properties.{f} must be bool, got {type(v).__name__}")

    # ── requirements ──────────────────────────────────────────────────────────
    reqs = lic.get("requirements", {})
    for f in REQUIRED_REQUIREMENTS - set(reqs.keys()):
        warn(f"requirements.{f} missing")
    for f, v in reqs.items():
        if not isinstance(v, bool):
            err(f"requirements.{f} must be bool, got {type(v).__name__}")

    # ── limitations ───────────────────────────────────────────────────────────
    lims = lic.get("limitations", {})
    for f in REQUIRED_LIMITATIONS - set(lims.keys()):
        warn(f"limitations.{f} missing")

    # ── compatibility ─────────────────────────────────────────────────────────
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

    # ── obligations / key_requirements ────────────────────────────────────────
    obligs = lic.get("obligations", [])
    lic_type = lic.get("type", "")
    if not obligs and lic_type not in ("public_domain",):
        warn("obligations list is empty")
    if not isinstance(obligs, list):
        err(f"obligations must be a list, got {type(obligs).__name__}")

    krs = lic.get("key_requirements", [])
    if not isinstance(krs, list):
        err(f"key_requirements must be a list, got {type(krs).__name__}")

    # ── spdx_metadata ─────────────────────────────────────────────────────────
    meta = lic.get("spdx_metadata", {})
    for f in ("is_osi_approved", "is_fsf_libre", "is_deprecated"):
        if f not in meta:
            warn(f"spdx_metadata.{f} missing")
        elif not isinstance(meta[f], bool):
            err(f"spdx_metadata.{f} must be bool, got {type(meta[f]).__name__}")

    # ── Known-license spot checks ─────────────────────────────────────────────
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


def run(data_dir: Path, strict: bool, as_json: bool) -> int:
    licenses_dir = data_dir / "licenses" / "json"
    if not licenses_dir.exists():
        print(f"ERROR: {licenses_dir} does not exist", file=sys.stderr)
        return 2

    files = sorted(licenses_dir.glob("*.json"))
    if not files:
        print(f"ERROR: no JSON files found in {licenses_dir}", file=sys.stderr)
        return 2

    all_errors: dict[str, list] = defaultdict(list)
    all_warnings: dict[str, list] = defaultdict(list)
    parse_failures: list[str] = []

    for p in files:
        lid = p.stem
        try:
            raw = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            parse_failures.append(f"{lid}: invalid JSON — {e}")
            continue

        lic = raw.get("license", {})
        if not lic:
            all_errors[lid].append("top-level 'license' key missing or empty")
            continue

        errs, warns = validate_license(lid, lic)
        if errs:
            all_errors[lid] = errs
        if warns:
            all_warnings[lid] = warns

    total = len(files)
    n_err = len(all_errors) + len(parse_failures)
    n_warn = len(all_warnings)
    n_ok = total - n_err - n_warn

    # ── Aggregate stat categories for summary ─────────────────────────────────
    error_categories: dict[str, int] = defaultdict(int)
    warning_categories: dict[str, int] = defaultdict(int)
    for msgs in all_errors.values():
        for m in msgs:
            key = m.split("'")[0].strip().rstrip(" —").split(":")[0]
            error_categories[key] += 1
    for msgs in all_warnings.values():
        for m in msgs:
            key = m.split("'")[0].strip().rstrip(" —").split(":")[0]
            warning_categories[key] += 1

    if as_json:
        output = {
            "total": total,
            "errors": n_err,
            "warnings": n_warn,
            "clean": n_ok,
            "parse_failures": parse_failures,
            "error_details": dict(all_errors),
            "warning_details": dict(all_warnings),
        }
        print(json.dumps(output, indent=2))
        return 1 if (n_err or (strict and n_warn)) else 0

    # ── Human-readable output ──────────────────────────────────────────────────
    W = "\033[33m"
    E = "\033[31m"
    OK = "\033[32m"
    RESET = "\033[0m"

    if parse_failures:
        print(f"\n{E}PARSE FAILURES ({len(parse_failures)}){RESET}")
        for m in parse_failures:
            print(f"  ✗ {m}")

    if all_errors:
        print(f"\n{E}ERRORS — {n_err} files affected{RESET}")
        for lid, msgs in sorted(all_errors.items()):
            print(f"  {lid}:")
            for m in msgs:
                print(f"    ✗ {m}")

    if all_warnings:
        print(f"\n{W}WARNINGS — {n_warn} files affected{RESET}")
        # Group by category to avoid flooding output
        for cat, count in sorted(warning_categories.items(), key=lambda x: -x[1])[:15]:
            print(f"  [{count:4d} files]  {cat}…")
        if n_warn > 15:
            examples = sorted(all_warnings.keys())[:5]
            print(f"\n  Sample affected: {', '.join(examples)}, …")

    print(f"\n{'─'*60}")
    print(f"  Total files  : {total}")
    print(f"  {OK}Clean        : {n_ok}{RESET}")
    print(f"  {W}Warnings     : {n_warn}{RESET}")
    print(f"  {E}Errors       : {n_err}{RESET}")

    if error_categories:
        print(f"\n  Most common errors:")
        for cat, count in sorted(error_categories.items(), key=lambda x: -x[1])[:8]:
            print(f"    [{count:4d}]  {cat}…")
    if warning_categories:
        print(f"\n  Most common warnings:")
        for cat, count in sorted(warning_categories.items(), key=lambda x: -x[1])[:8]:
            print(f"    [{count:4d}]  {cat}…")

    fail = n_err > 0 or (strict and n_warn > 0)
    print(f"\n  {'FAIL' if fail else 'PASS'} (strict={strict})")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="ospac/data", type=Path,
                    help="Path to ospac/data directory (default: ospac/data)")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero on warnings too")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="Output machine-readable JSON")
    args = ap.parse_args()
    sys.exit(run(args.data_dir, args.strict, args.as_json))


if __name__ == "__main__":
    main()
