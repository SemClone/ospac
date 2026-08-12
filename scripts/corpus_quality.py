#!/usr/bin/env python3
"""
Corpus-level quality gate for the license dataset.

The per-record validator cannot detect the failure this project actually shipped: the
LLM analysis silently never ran, a hardcoded fallback wrote the same permissive answer
into almost every record, and every record was individually well formed. Detecting that
requires looking across records, not within one.

Two independent signals:

1. Uniformity. A decision-relevant field carrying one value across hundreds of licenses
   was not analysed. Real licenses differ.
2. Fallback fingerprints. Both the historical permissive fallback and the current
   fail-closed fallback have known exact shapes, so fabricated records are countable.

Run after a regeneration, before publishing:

    python scripts/corpus_quality.py --data-dir ospac/data

Exits non-zero on errors. Warnings report but do not fail unless --strict is passed.
"""

import argparse
import collections
import glob
import json
import sys

# The historical fallback, which claimed everything was permissive and commercially
# usable. Any record still matching it end to end was fabricated, never analysed.
LEGACY_FALLBACK_PROPERTIES = {
    "commercial_use": True, "distribution": True, "modification": True,
    "patent_grant": False, "private_use": True,
}
LEGACY_FALLBACK_REQUIREMENTS = {
    "disclose_source": False, "include_license": True, "include_copyright": True,
    "include_notice": False, "state_changes": False, "same_license": False,
    "network_use_disclosure": False,
}
# The fabricated records never carried real disclaimer analysis, so their limitations
# were uniformly false. A genuinely permissive license can legitimately match the
# property and requirement templates, but real analysis reports the disclaimers, so
# limitations distinguish fabricated from coincidentally similar.
LEGACY_FALLBACK_LIMITATIONS = {
    "liability": False, "warranty": False, "trademark_use": False,
}

# Fields a person reads to make a decision. These must not be templated corpus-wide.
DECISION_FIELDS = {
    "limitations": lambda r: json.dumps(r.get("limitations"), sort_keys=True),
    "compatibility": lambda r: json.dumps(
        r.get("compatibility"), sort_keys=True).replace(r["id"], "SELF"),
    "contamination_effect": lambda r: str(
        r.get("compatibility", {}).get("contamination_effect")),
    "obligations": lambda r: json.dumps(r.get("obligations")),
    "key_requirements": lambda r: json.dumps(r.get("key_requirements")),
}

MIN_RECORDS = 100      # below this, uniformity says nothing
MODAL_ERROR = 0.98     # one value covering this share of records is a hard failure
MODAL_WARN = 0.85      # likely templated, report it


def load_records(data_dir):
    records = []
    for path in sorted(glob.glob(f"{data_dir}/licenses/json/*.json")):
        with open(path) as f:
            records.append(json.load(f)["license"])
    return records


def run(data_dir, strict):
    records = load_records(data_dir)
    count = len(records)
    errors, warnings = [], []

    print(f"corpus quality check: {count} records in {data_dir}\n")
    print(f"{'field':22} {'distinct':>9} {'modal share':>12}   verdict")
    print("-" * 64)

    for field, key_of in DECISION_FIELDS.items():
        counts = collections.Counter(key_of(r) for r in records)
        distinct = len(counts)
        modal = counts.most_common(1)[0][1] / count if count else 0

        verdict = "ok"
        if count >= MIN_RECORDS and distinct == 1:
            errors.append(f"{field}: a single value across all {count} records, "
                          f"so this field was never analysed")
            verdict = "ERROR"
        elif modal >= MODAL_ERROR:
            errors.append(f"{field}: {modal * 100:.0f}% of records share one value, "
                          f"which no real analysis produces")
            verdict = "ERROR"
        elif modal >= MODAL_WARN:
            warnings.append(f"{field}: {modal * 100:.0f}% of records share one value, "
                            f"likely templated")
            verdict = "warn"
        print(f"{field:22} {distinct:>9} {modal * 100:>11.0f}%   {verdict}")

    legacy = sum(
        1 for r in records
        if r.get("type") == "permissive"
        and r.get("properties") == LEGACY_FALLBACK_PROPERTIES
        and r.get("requirements") == LEGACY_FALLBACK_REQUIREMENTS
        and r.get("limitations") == LEGACY_FALLBACK_LIMITATIONS)
    unknown = sum(1 for r in records if r.get("type") == "unknown")

    print()
    print(f"legacy permissive fallback shape : {legacy} "
          f"({legacy * 100 // count if count else 0}%)")
    print(f"fail-closed unknown records      : {unknown}")

    if legacy:
        errors.append(f"{legacy} records carry the legacy permissive fallback shape, "
                      f"so they were fabricated rather than analysed")
    if unknown:
        errors.append(f"{unknown} records are typed unknown, meaning a fallback ran "
                      f"during generation")

    print()
    for message in errors:
        print(f"  ERROR   {message}")
    for message in warnings:
        print(f"  WARN    {message}")
    print()

    if errors:
        print("FAIL")
        return 1
    if warnings:
        print("PASS with warnings" + (" (strict: FAIL)" if strict else ""))
        return 1 if strict else 0
    print("PASS")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default="ospac/data")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero on warnings too")
    args = parser.parse_args()
    sys.exit(run(args.data_dir, args.strict))


if __name__ == "__main__":
    main()
