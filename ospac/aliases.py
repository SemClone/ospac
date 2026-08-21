"""
License alias resolution.

Every tool that normalizes a declared license ends up curating its own alias table,
and divergent tables are how the same SBOM gets different answers from different
tools. ospac regenerates its records from SPDX monthly with provenance, so the alias
data lives here and travels with the dataset.
"""

import json
from pathlib import Path
from typing import Dict, List, Set

_ALIASES_FILE = Path(__file__).parent / "data" / "aliases.json"


def _payload() -> dict:
    with open(_ALIASES_FILE) as f:
        return json.load(f)


def license_aliases() -> Dict[str, str]:
    """
    Lowercased alias to SPDX id.

    Covers each license's own id and official name, the deprecated SPDX spellings
    mapped forward (gpl-3.0 to GPL-3.0-only, gpl-3.0+ to GPL-3.0-or-later), and
    curated spellings package ecosystems actually write (expat to MIT, apache2 to
    Apache-2.0). An alias claimed by more than one license resolves to nothing and
    is absent. Look up with your input lowercased.
    """
    return dict(_payload()["aliases"])


def license_ambiguous() -> Dict[str, List[str]]:
    """
    Lowercased text that names a license but not which id, to its candidate ids.

    "gnu lesser general public license v2.1" names the license and the version and is
    still not an identifier, because -only versus -or-later is the copyright holder's
    grant and the license's own name does not carry it. Resolving it either way asserts
    something the document never said. These are absent from license_aliases() for that
    reason; here a caller can report which distinction is missing instead of reporting a
    perfectly legible name as unrecognised. Every candidate list has at least two ids.
    Look up with your input lowercased.
    """
    return {name: list(ids) for name, ids in _payload()["ambiguous"].items()}


def license_never_resolve() -> Set[str]:
    """
    Lowercased text that must not resolve to any id.

    Family names: bsd is 2-clause or 3-clause and the choice changes obligations,
    gpl states neither a version nor only/or-later. Resolving them fabricates a
    confident answer the document does not support. Callers normalizing licenses
    should treat these as unresolved rather than guessing.
    """
    return set(_payload()["never_resolve"])
