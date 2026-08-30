"""
License alias resolution.

Every tool that normalizes a declared license ends up curating its own alias table,
and divergent tables are how the same SBOM gets different answers from different
tools. ospac regenerates its records from SPDX monthly with provenance, so the alias
data lives here and travels with the dataset.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

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


@dataclass(frozen=True)
class LicenseResolution:
    """
    What the shipped data can say about one declared license string.

    `status` is the part a consumer acts on. "exact" is a canonical SPDX identifier.
    "normalized" resolved through the alias map, and `license_id` names what it became,
    so a caller can see that the verdict it got was about the license it meant.
    "ambiguous" identifies a license and not which identifier, and `candidates` holds
    the readings; nothing is chosen, because -only versus -or-later is the copyright
    holder's grant and the string does not carry it. "unresolved" is a name the data
    does not know, or a family name that must never resolve.
    """

    text: str
    license_id: Optional[str]
    candidates: List[str]
    status: str


def resolve_license(text: str) -> LicenseResolution:
    """
    Resolve a declared license string to an SPDX identifier where the data allows it.

    Package registries do not answer in SPDX. PyPI's license field is free text by
    construction and requests 2.31.0 declares "Apache 2.0"; Maven POMs carry the prose
    name from a <licenses> block. Matching those verbatim against a policy finds
    nothing, and "no rule matched" is indistinguishable from a considered ruling at the
    point where the two mean opposite things.
    """
    key = (text or "").strip().lower()
    if not key or key in license_never_resolve():
        return LicenseResolution(text, None, [], "unresolved")

    candidates = license_ambiguous().get(key)
    if candidates:
        return LicenseResolution(text, None, list(candidates), "ambiguous")

    resolved = license_aliases().get(key)
    if resolved is None:
        return LicenseResolution(text, None, [], "unresolved")
    return LicenseResolution(
        text, resolved, [], "exact" if resolved == text else "normalized")


def matchable_license_id(text: str) -> str:
    """
    The spelling a policy rule or a record lookup should use for a declared string.

    The input wins whenever it is itself a shipped identifier, so a policy written
    against the deprecated GPL-2.0 keeps matching exactly what it always matched, and
    an obligations lookup for it keeps returning that record's own deprecation
    metadata rather than the canonical record's. Only a string that names no record is
    replaced, which is the registry spelling: "Apache 2.0" is not an identifier and
    reached nothing at all.

    Anything that resolves to neither is returned unchanged, so a caller that
    validates identifiers still rejects it.
    """
    from ospac.dataset import known_license_ids

    if text in known_license_ids():
        return text
    return resolve_license(text).license_id or text
