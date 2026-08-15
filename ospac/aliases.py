"""
License alias resolution.

Every tool that normalizes a declared license ends up curating its own alias table,
and divergent tables are how the same SBOM gets different answers from different
tools. ospac regenerates its records from SPDX monthly with provenance, so the alias
data lives here and travels with the dataset.
"""

import json
from pathlib import Path
from typing import Dict, Set

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


def license_never_resolve() -> Set[str]:
    """
    Lowercased text that must not resolve to any id.

    Family names: bsd is 2-clause or 3-clause and the choice changes obligations,
    gpl states neither a version nor only/or-later. Resolving them fabricates a
    confident answer the document does not support. Callers normalizing licenses
    should treat these as unresolved rather than guessing.
    """
    return set(_payload()["never_resolve"])
