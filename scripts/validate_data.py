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

# Make the source checkout importable when the script is run directly,
# e.g. `python scripts/validate_data.py` without PYTHONPATH set.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Single source of truth for the validation rules, shared with the
# `ospac data validate` CLI command.
from ospac.utils.data_validation import validate_license  # noqa: E402


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
            parse_failures.append(f"{lid}: invalid JSON: {e}")
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
            key = m.split("'")[0].strip().rstrip(" ,").split(":")[0]
            error_categories[key] += 1
    for msgs in all_warnings.values():
        for m in msgs:
            key = m.split("'")[0].strip().rstrip(" ,").split(":")[0]
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
        print(f"\n{E}ERRORS: {n_err} files affected{RESET}")
        for lid, msgs in sorted(all_errors.items()):
            print(f"  {lid}:")
            for m in msgs:
                print(f"    ✗ {m}")

    if all_warnings:
        print(f"\n{W}WARNINGS: {n_warn} files affected{RESET}")
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
