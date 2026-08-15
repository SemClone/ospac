"""
Policy data generator that produces OSPAC datasets.
Combines SPDX data with LLM analysis to generate comprehensive policy files.
"""

import json
import re
import yaml
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from ospac.pipeline.spdx_processor import SPDXProcessor
from ospac.pipeline.llm_analyzer import LicenseAnalyzer

logger = logging.getLogger(__name__)

# LLMs consistently misclassify these licenses; values here override LLM output.
# "category" maps to the `category` field (license type).
# "conditions" are merged into the `conditions` dict (any key overrides the LLM value).
_KNOWN_OVERRIDES: Dict[str, Dict] = {
    # LGPL permits linking from proprietary code, so it is weak copyleft, not strong
    "LGPL-2.0-only":     {"category": "copyleft_weak"},
    "LGPL-2.0-or-later": {"category": "copyleft_weak"},
    "LGPL-2.1-only":     {"category": "copyleft_weak"},
    "LGPL-2.1-or-later": {"category": "copyleft_weak"},
    "LGPL-3.0-only":     {"category": "copyleft_weak"},
    "LGPL-3.0-or-later": {"category": "copyleft_weak"},
    # The deprecated bare and "+" spellings are aliases of the identifiers above, so they
    # must classify identically. They were missing here, so the LLM kept marking them
    # strong while their modern equivalents were corrected to weak. These are also the
    # spellings that appear most often in real package metadata.
    "LGPL-2.0":          {"category": "copyleft_weak"},
    "LGPL-2.0+":         {"category": "copyleft_weak"},
    "LGPL-2.1":          {"category": "copyleft_weak"},
    "LGPL-2.1+":         {"category": "copyleft_weak"},
    "LGPL-3.0":          {"category": "copyleft_weak"},
    "LGPL-3.0+":         {"category": "copyleft_weak"},
    # LGPLLR is the lesser licence for linguistic resources. It is not an alias of any
    # LGPL identifier, but its properties, requirements, limitations and contamination
    # effect are identical to LGPL-2.1's, so typing it strong while LGPL-2.1 is weak was
    # inconsistent on the dataset's own terms.
    "LGPLLR":            {"category": "copyleft_weak"},
    # Mainstream licenses the broken analysis recorded as freely permissive. Each entry
    # states what the license text says, so a regeneration cannot reintroduce the error.
    # EPL and CDDL are weak copyleft with file-level source disclosure.
    "EPL-1.0":  {"category": "copyleft_weak",
                 "conditions": {"disclose_source": True, "same_license": True}},
    "EPL-2.0":  {"category": "copyleft_weak",
                 "conditions": {"disclose_source": True, "same_license": True}},
    "CDDL-1.0": {"category": "copyleft_weak",
                 "conditions": {"disclose_source": True, "same_license": True}},
    "CDDL-1.1": {"category": "copyleft_weak",
                 "conditions": {"disclose_source": True, "same_license": True}},
    # EUPL is copyleft for the work as a whole, with an interoperability compatibility list
    "EUPL-1.1": {"category": "copyleft_strong",
                 "conditions": {"disclose_source": True, "same_license": True}},
    "EUPL-1.2": {"category": "copyleft_strong",
                 "conditions": {"disclose_source": True, "same_license": True}},
    # OSL and CAL treat network use as distribution; SSPL extends disclosure to the whole
    # service stack
    "OSL-3.0":  {"category": "network_copyleft",
                 "conditions": {"disclose_source": True, "same_license": True,
                                "network_use_disclosure": True}},
    "CAL-1.0":  {"category": "network_copyleft",
                 "conditions": {"disclose_source": True, "same_license": True,
                                "network_use_disclosure": True}},
    "SSPL-1.0": {"category": "network_copyleft",
                 "conditions": {"disclose_source": True, "same_license": True,
                                "network_use_disclosure": True}},
    # Source-available: source is published but use is restricted, so not open source
    "BUSL-1.1":    {"category": "source_available"},
    "Elastic-2.0": {"category": "source_available"},
    # Parity requires releasing all software that uses the work
    "Parity-7.0.0": {"category": "copyleft_strong",
                     "conditions": {"disclose_source": True, "same_license": True}},
    # Aladdin (AFPL) and NPOSL forbid commercial use outright
    "Aladdin":    {"category": "noncommercial", "permissions": {"commercial_use": False}},
    "NPOSL-3.0":  {"category": "noncommercial", "permissions": {"commercial_use": False}},
    # ODbL and CDLA-Sharing are share-alike for data
    "ODbL-1.0":         {"category": "copyleft_weak", "conditions": {"same_license": True}},
    "CDLA-Sharing-1.0": {"category": "copyleft_weak", "conditions": {"same_license": True}},
    # CERN OHL v2: S is strongly reciprocal, W weakly; the name says so
    "CERN-OHL-S-2.0": {"category": "copyleft_strong",
                       "conditions": {"disclose_source": True, "same_license": True}},
    "CERN-OHL-W-2.0": {"category": "copyleft_weak",
                       "conditions": {"disclose_source": True, "same_license": True}},
    # RPL extends reciprocity to internal deployment, and ESA-PL's strong variant says
    # strong in its own name; the reciprocity name stem alone would floor these at weak
    "RPL-1.1": {"category": "copyleft_strong",
                "conditions": {"disclose_source": True, "same_license": True}},
    "RPL-1.5": {"category": "copyleft_strong",
                "conditions": {"disclose_source": True, "same_license": True}},
    "ESA-PL-strong-copyleft-2.4": {"category": "copyleft_strong",
                                   "conditions": {"disclose_source": True,
                                                  "same_license": True}},
    # MPL-2.0: file-level (weak) copyleft, modified files must stay MPL and source disclosed
    "MPL-2.0": {
        "category": "copyleft_weak",
        "conditions": {"disclose_source": True, "same_license": True},
    },
    "MPL-2.0-no-copyleft-exception": {
        "category": "copyleft_weak",
        "conditions": {"disclose_source": True, "same_license": True},
    },
    # AGPL is strong copyleft plus the network clause, not one instead of the other.
    # Models reasonably answer network_copyleft, which would soften commercial
    # distribution from deny to review, so the category is pinned. All spellings carry
    # the network-use disclosure condition, including AGPL-1.0's own clause 2(d).
    "AGPL-3.0-only":     {"category": "copyleft_strong",
                          "conditions": {"network_use_disclosure": True}},
    "AGPL-3.0-or-later": {"category": "copyleft_strong",
                          "conditions": {"network_use_disclosure": True}},
    "AGPL-3.0":          {"category": "copyleft_strong",
                          "conditions": {"network_use_disclosure": True}},
    "AGPL-1.0":          {"category": "copyleft_strong",
                          "conditions": {"network_use_disclosure": True}},
    "AGPL-1.0-only":     {"category": "copyleft_strong",
                          "conditions": {"network_use_disclosure": True}},
    "AGPL-1.0-or-later": {"category": "copyleft_strong",
                          "conditions": {"network_use_disclosure": True}},
    # Apache-2.0 requires documenting changes made to original files
    "Apache-2.0": {"conditions": {"state_changes": True}},
    # CC0 is a full public domain waiver, with no copyright or license text requirements
    "CC0-1.0": {"conditions": {"include_copyright": False, "include_license": False}},
    # 0BSD is the zero-clause BSD: it requires nothing at all, and the analysis kept
    # asking for attribution anyway
    "0BSD":    {"conditions": {"include_copyright": False, "include_license": False}},
}


# License-level compatibility exceptions that category reasoning cannot express. Each
# pair lands in both records' incompatible_with, so the claims stay symmetric.
_KNOWN_INCOMPATIBLE_PAIRS = [
    # GPL-2.0's "no further restrictions" clause conflicts with Apache-2.0's patent
    # termination. GPL-2.0-or-later escapes by upgrading, so it is not listed.
    ({"GPL-2.0", "GPL-2.0-only"}, {"Apache-2.0"}),
    # The GPL versions are mutually incompatible unless or-later allows upgrading.
    ({"GPL-2.0", "GPL-2.0-only"}, {"GPL-3.0", "GPL-3.0-only"}),
    # The 4-clause BSD advertising requirement is an additional restriction no GPL
    # version permits.
    ({"BSD-4-Clause", "BSD-4-Clause-UC", "BSD-4-Clause-Shortened"},
     {"GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later",
      "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later"}),
]


def _known_incompatible_ids(license_id: str) -> list:
    """Every license id the exception table declares incompatible with this one."""
    ids = set()
    for side_a, side_b in _KNOWN_INCOMPATIBLE_PAIRS:
        if license_id in side_a:
            ids.update(side_b)
        elif license_id in side_b:
            ids.update(side_a)
    return sorted(ids)


class PolicyDataGenerator:
    """
    Generate comprehensive policy data from SPDX licenses.
    Produces all required datasets for OSPAC runtime.
    """

    def __init__(self, output_dir: Path = None, llm_provider: str = "ollama",
                 llm_model: str = None, llm_api_key: str = None, **llm_kwargs):
        """
        Initialize the data generator.

        Args:
            output_dir: Output directory for generated data
            llm_provider: LLM provider ("openai", "claude", "ollama")
            llm_model: LLM model name (auto-selected if not provided)
            llm_api_key: API key for cloud providers
            **llm_kwargs: Additional LLM configuration
        """
        self.output_dir = output_dir or Path("data")
        self.spdx_processor = SPDXProcessor()
        self.llm_analyzer = LicenseAnalyzer(
            provider=llm_provider,
            model=llm_model,
            api_key=llm_api_key,
            **llm_kwargs
        )

        # Ensure output directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "licenses").mkdir(exist_ok=True)
        (self.output_dir / "licenses" / "spdx").mkdir(exist_ok=True)
        (self.output_dir / "compatibility").mkdir(exist_ok=True)
        (self.output_dir / "compatibility" / "relationships").mkdir(exist_ok=True)
        (self.output_dir / "obligations").mkdir(exist_ok=True)

        # Progress tracking
        self.progress_file = self.output_dir / "generation_progress.json"
        self.processed_licenses = self._load_progress()

    def _load_progress(self) -> set:
        """Load previously processed licenses from progress file."""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('processed_licenses', []))
            except Exception as e:
                logger.warning(f"Failed to load progress file: {e}")
        return set()

    def _save_progress(self, license_id: str):
        """Save progress after processing each license."""
        self.processed_licenses.add(license_id)
        progress_data = {
            'last_updated': datetime.now().isoformat(),
            'total_processed': len(self.processed_licenses),
            'processed_licenses': list(self.processed_licenses)
        }
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")

    def _generate_individual_policy(self, analysis: Dict[str, Any]):
        """Generate individual policy file for a license."""
        license_id = analysis.get("license_id")
        if not license_id:
            return

        # Create policy structure
        policy_data = {
            "license": {
                "id": license_id,
                "name": license_id,
                "type": analysis.get("category", "unknown"),
                "spdx_id": license_id,
                "properties": analysis.get("permissions", {}),
                "requirements": analysis.get("conditions", {}),
                "limitations": analysis.get("limitations", {}),
                "compatibility": self._format_compatibility_rules(analysis.get("compatibility_rules", {})),
                "obligations": analysis.get("obligations", []),
                "key_requirements": analysis.get("key_requirements", [])
            }
        }

        # Save to individual file
        license_file = self.output_dir / "licenses" / "spdx" / f"{license_id}.yaml"
        try:
            with open(license_file, 'w') as f:
                yaml.dump(policy_data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to save policy file for {license_id}: {e}")

    def _format_compatibility_rules(self, rules: Dict) -> Dict:
        """Format compatibility rules for policy file."""
        if not rules:
            return {
                "static_linking": {"compatible_with": [], "incompatible_with": [], "requires_review": []},
                "dynamic_linking": {"compatible_with": [], "incompatible_with": [], "requires_review": []},
                "contamination_effect": "unknown",
                "notes": ""
            }

        return {
            "static_linking": rules.get("static_linking", {}),
            "dynamic_linking": rules.get("dynamic_linking", {}),
            "contamination_effect": rules.get("contamination_effect", "unknown"),
            "notes": rules.get("notes", "")
        }

    def _load_all_processed_licenses(self) -> List[Dict]:
        """Load all previously processed license analyses from the canonical JSON store."""
        analyzed_licenses = []
        json_dir = self.output_dir / "licenses" / "json"

        if not json_dir.exists():
            return analyzed_licenses

        for license_file in json_dir.glob("*.json"):
            try:
                with open(license_file, 'r') as f:
                    policy_data = json.load(f)
                    if "license" in policy_data:
                        analyzed_licenses.append(policy_data["license"])
            except Exception as e:
                logger.warning(f"Failed to load {license_file}: {e}")

        return analyzed_licenses

    def _convert_yaml_format(self, yaml_licenses: List[Dict]) -> List[Dict]:
        """Convert YAML format licenses to the expected format for database generation."""
        converted = []
        for license_data in yaml_licenses:
            # Handle both direct format and wrapped format from YAML files
            if isinstance(license_data, dict) and 'id' in license_data:
                # Direct format from YAML files
                converted_license = {
                    "license_id": license_data.get("id"),
                    "name": license_data.get("name", license_data.get("id")),
                    "category": license_data.get("type", "permissive"),
                    "permissions": license_data.get("properties", {}),
                    "conditions": license_data.get("requirements", {}),
                    "limitations": license_data.get("limitations", {}),
                    "compatibility_rules": license_data.get("compatibility", {}),
                    "obligations": license_data.get("obligations", []),
                    "key_requirements": license_data.get("key_requirements", []),
                    "spdx_data": {
                        "isOsiApproved": license_data.get("spdx_metadata", {}).get("is_osi_approved", False),
                        "isFsfLibre": license_data.get("spdx_metadata", {}).get("is_fsf_libre", False),
                        "isDeprecatedLicenseId": license_data.get("spdx_metadata", {}).get("is_deprecated", False),
                    }
                }
                converted.append(converted_license)
            elif isinstance(license_data, dict) and 'license_id' in license_data:
                # Already in expected format
                converted.append(license_data)

        return converted

    def _update_master_databases(self, all_analyzed: List[Dict]):
        """Update master databases with all processed licenses."""
        # This method will update the main database files
        pass

    def _get_licenses_to_process(self, all_licenses: List[Dict], force: bool = False) -> List[Dict]:
        """Get list of licenses that need processing (delta processing)."""
        if force:
            return all_licenses

        # Use existing JSON files as the source of truth, not the transient progress file
        licenses_json_dir = self.output_dir / "licenses" / "json"
        existing_ids = (
            {p.stem for p in licenses_json_dir.glob("*.json")}
            if licenses_json_dir.exists() else set()
        )

        licenses_to_process = [
            l for l in all_licenses
            if l.get("licenseId", l.get("id", "")) not in existing_ids
        ]

        logger.info(f"Found {len(licenses_to_process)} new licenses to process out of {len(all_licenses)} total")
        return licenses_to_process

    def _derive_obligations(self, license_id: str, category: str,
                            conditions: Dict, permissions: Dict) -> tuple:
        """
        Build obligations and key_requirements from structured boolean fields.
        LLM-generated prose for these fields is uniformly generic; derive them
        deterministically so every license gets accurate, distinct values.
        """
        obligs = []
        # Always required when distributing open-source software
        if conditions.get("include_copyright", True):
            obligs.append("Retain copyright notices")
        if conditions.get("include_license", True):
            obligs.append("Include license text")
        if conditions.get("state_changes"):
            obligs.append("Document changes made to the code")
        if conditions.get("disclose_source"):
            obligs.append("Provide or offer access to complete source code")
        if conditions.get("same_license"):
            obligs.append("Distribute modifications under the same license")
        if conditions.get("network_use_disclosure"):
            obligs.append("Make source available to users interacting over a network")
        if not permissions.get("commercial_use", True):
            obligs.append("Non-commercial use only")
        if not permissions.get("modification", True):
            obligs.append("No modification permitted")
        if not permissions.get("distribution", True):
            obligs.append("No redistribution permitted")

        # key_requirements: one-line summary driven by license category
        _CATEGORY_KEY = {
            "permissive":      ["Attribution required"],
            "copyleft_weak":   ["Attribution required",
                                "Modifications to covered files must stay open-source"],
            "copyleft_strong": ["Attribution required",
                                "Combined works must be released under the same license"],
            "network_copyleft":["Attribution required",
                                "Network use triggers source-disclosure obligation"],
            "public_domain":   ["No restrictions"],
            "source_available":["Source visible but redistribution restricted"],
            "noncommercial":   ["Attribution required",
                                "Commercial use not permitted"],
            "no_derivatives":  ["Attribution required",
                                "Distribution of modified versions not permitted"],
            "proprietary":     ["All rights reserved, no redistribution"],
            "unknown":         ["Review license terms before use"],
        }
        key_reqs = list(_CATEGORY_KEY.get(category, ["Review license terms before use"]))
        if conditions.get("network_use_disclosure") and category != "network_copyleft":
            key_reqs.append("Network use triggers source-disclosure obligation")
        # A license can carry more than one restriction, and the category headline only
        # states the dominant one: CC-BY-NC-SA headlined the NC term and dropped the
        # share-alike term entirely. Add the lines the category did not already say.
        if conditions.get("same_license") and not any(
                "same license" in k.lower() or "stay open-source" in k for k in key_reqs):
            key_reqs.append("Derivative works must be shared under the same license")
        if permissions.get("modification") is False and not any(
                "modified versions" in k for k in key_reqs):
            key_reqs.append("Distribution of modified versions not permitted")

        return obligs, key_reqs

    def _apply_known_corrections(self, license_id: str, analysis: Dict) -> Dict:
        """Override fields that LLMs consistently misclassify for well-known licenses."""
        overrides = _KNOWN_OVERRIDES.get(license_id)
        if not overrides:
            return analysis
        result = dict(analysis)
        if "category" in overrides:
            result["category"] = overrides["category"]
        if "conditions" in overrides:
            result["conditions"] = dict(result.get("conditions") or {})
            result["conditions"].update(overrides["conditions"])
        if "permissions" in overrides:
            result["permissions"] = dict(result.get("permissions") or {})
            result["permissions"].update(overrides["permissions"])
        return result

    @staticmethod
    def _identifier_restrictions(license_id: str, name: str = "") -> Dict[str, Any]:
        """
        Read the restrictions that an SPDX identifier states outright.

        Creative Commons encodes its terms in the identifier itself: NC means
        NonCommercial, ND means NoDerivatives, SA means ShareAlike. These are facts about
        the identifier, not judgements about licence text, so they are derived here rather
        than asked of a model. Every NonCommercial licence in the dataset had been recorded
        as commercially usable because the analysis silently fell back to a permissive
        default, which is exactly the kind of answer a model should never be trusted for.

        Matching is on hyphen-delimited components so an identifier that merely contains
        the letters is not caught. Names are compared with punctuation and case removed,
        because the wording varies: NCGL-UK-2.0 is the "Non-Commercial Government Licence"
        and a plain "NonCommercial" test misses it.
        """
        parts = set(license_id.split("-"))
        flat = re.sub(r"[^a-z]", "", name.lower())
        restrictions: Dict[str, Any] = {}

        if "NC" in parts or "noncommercial" in flat or "nonprofit" in flat:
            restrictions["commercial_use"] = False
        if "ND" in parts or "noderivative" in flat:
            restrictions["modification"] = False
        # Reciprocity is frequently stated in the name itself: ShareAlike (CC), Reciprocal
        # (MS-RL, RPL), or plain copyleft (copyleft-next, the ESA-PL variants).
        if ("SA" in parts or "sharealike" in flat or "reciprocal" in flat
                or "copyleft" in flat):
            restrictions["same_license"] = True

        return restrictions

    @staticmethod
    def _derive_compatibility(license_id: str, category: str,
                              notes: Optional[str] = None) -> Dict[str, Any]:
        """
        Build the record's compatibility block from its category plus the known
        license-level exceptions.

        The model was asked for these lists per license and got them systematically
        wrong: 540 permissive records declared themselves incompatible with GPL, which
        inverts how permissive licensing works, MPL-2.0 claimed incompatibility with the
        GPL it is expressly designed to combine with, and pairs disagreed with each
        other. Compatibility between categories is a derivable fact, so it is derived;
        the model contributes only the prose notes.
        """
        known_incompatible = _known_incompatible_ids(license_id)

        if category in ("permissive", "public_domain"):
            static = {
                "compatible_with": ["category:any"],
                "incompatible_with": list(known_incompatible),
                "requires_review": [],
            }
            dynamic = dict(static)
            contamination = "none"
            default_note = ("Permissive terms: can be incorporated into works under "
                            "any license")
        elif category == "copyleft_weak":
            static = {
                "compatible_with": [license_id, "category:permissive",
                                    "category:public_domain"],
                "incompatible_with": list(known_incompatible),
                "requires_review": ["category:copyleft_weak", "category:copyleft_strong",
                                    "category:network_copyleft"],
            }
            dynamic = {
                "compatible_with": [license_id, "category:permissive",
                                    "category:public_domain", "category:copyleft_weak"],
                "incompatible_with": list(known_incompatible),
                "requires_review": ["category:copyleft_strong",
                                    "category:network_copyleft"],
            }
            contamination = "module"
            default_note = ("Weak copyleft: changes to the covered component must stay "
                            "under its license")
        elif category in ("copyleft_strong", "network_copyleft"):
            block = {
                "compatible_with": [license_id, "category:permissive",
                                    "category:public_domain"],
                "incompatible_with": ["category:proprietary"] + list(known_incompatible),
                "requires_review": ["category:copyleft_weak", "category:copyleft_strong",
                                    "category:network_copyleft", "category:noncommercial",
                                    "category:no_derivatives",
                                    "category:source_available"],
            }
            static = block
            dynamic = dict(block)
            contamination = "full"
            default_note = ("Strong copyleft: the combined work must be released under "
                            "the same license")
            if category == "network_copyleft":
                default_note = ("Network copyleft: serving users over a network triggers "
                                "source disclosure for the combined work")
        else:
            # noncommercial, no_derivatives, source_available, proprietary, unknown:
            # nothing is asserted without a human looking at the terms.
            block = {
                "compatible_with": [],
                "incompatible_with": [],
                "requires_review": ["category:any"],
            }
            static = block
            dynamic = dict(block)
            contamination = "none" if category in ("noncommercial",
                                                   "no_derivatives") else "unknown"
            default_note = "Restricted license: combination requires review of the terms"

        # ShareAlike-style reciprocity binds derivative works specifically.
        if category == "copyleft_weak" and "SA" in license_id.split("-"):
            contamination = "derivative"

        return {
            "static_linking": static,
            "dynamic_linking": dynamic,
            "contamination_effect": contamination,
            "notes": notes or default_note,
        }

    def _apply_identifier_restrictions(self, license_id: str, analysis: Dict) -> Dict:
        """
        Force the terms the identifier states outright, then coerce the category to be
        honest about the record's final booleans. No early return when the identifier has
        no markers: the coercion must also cover restrictions only the analysis reports.
        """
        restrictions = self._identifier_restrictions(license_id, analysis.get("name", ""))

        result = dict(analysis)
        if "commercial_use" in restrictions or "modification" in restrictions:
            result["permissions"] = dict(result.get("permissions") or {})
            for key in ("commercial_use", "modification"):
                if key in restrictions:
                    result["permissions"][key] = restrictions[key]
        if "same_license" in restrictions:
            result["conditions"] = dict(result.get("conditions") or {})
            result["conditions"]["same_license"] = restrictions["same_license"]

        # The category must be honest about the restriction, because policy rules match on
        # it. The coercion reads the record's final booleans, not only the
        # identifier-derived ones: the first real analysis run returned modification false
        # for two Adobe licenses while calling them permissive, which the identifier says
        # nothing about, and only the validator caught the contradiction. NonCommercial
        # dominates and is forced regardless of the incoming category, so a model
        # classifying CC-BY-NC-SA as copyleft cannot bypass the noncommercial deny rules.
        # ShareAlike and NoDerivatives only lift a record out of permissive: a stronger
        # category already expresses the restriction.
        permissions = result.get("permissions") or {}
        conditions = result.get("conditions") or {}
        if permissions.get("commercial_use") is False:
            result["category"] = "noncommercial"
        elif conditions.get("same_license") is True and result.get("category") == "permissive":
            result["category"] = "copyleft_weak"
        if permissions.get("modification") is False and result.get("category") == "permissive":
            result["category"] = "no_derivatives"

        # The compatibility lists are derived from the final category, keeping whatever
        # prose notes the analysis produced. This runs on every path that writes a
        # record, so the lists cannot drift from the category they describe.
        existing_notes = (result.get("compatibility_rules") or {}).get("notes")
        result["compatibility_rules"] = PolicyDataGenerator._derive_compatibility(
            license_id, result["category"], existing_notes)

        return result

    async def generate_all_data(self, force_download: bool = False,
                               limit: Optional[int] = None,
                               force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Generate all policy data from SPDX licenses.

        Args:
            force_download: Force re-download of SPDX data
            limit: Limit number of licenses to process (for testing)

        Returns:
            Summary of generated data
        """
        logger.info("Starting policy data generation")

        # Step 1: Download and process SPDX data
        logger.info("Downloading SPDX license data...")
        spdx_data = self.spdx_processor.download_spdx_data(force=force_download)
        all_licenses = spdx_data["licenses"]

        # Step 1b: Flag any newly-deprecated licenses in existing data (no LLM needed)
        deprecated_updated = self.update_deprecated_licenses(all_licenses)
        if deprecated_updated:
            logger.info(f"Flagged {len(deprecated_updated)} licenses as deprecated")

        # Step 2: Determine which licenses need processing (delta processing)
        licenses_to_process = self._get_licenses_to_process(all_licenses, force_reprocess)

        if limit:
            licenses_to_process = licenses_to_process[:limit]
            logger.info(f"Processing limited to {limit} licenses")

        if not licenses_to_process:
            logger.info("No new licenses to process. All licenses up to date.")
            # Rebuild index so deprecated-flag updates from Step 1b are reflected
            self._rebuild_index_from_files(spdx_version=spdx_data.get("version", ""))
            return self._generate_summary(all_licenses, spdx_data)

        logger.info(f"Processing {len(licenses_to_process)} licenses with progress tracking...")

        # Step 3: Process licenses with progress tracking
        processed_licenses = []
        analyzed_licenses = []

        for i, license_data in enumerate(licenses_to_process, 1):
            license_id = license_data.get("licenseId")
            if not license_id:
                continue

            logger.info(f"[{i}/{len(licenses_to_process)}] Processing {license_id}")

            try:
                # Get license text
                license_text = self.spdx_processor.get_license_text(license_id)

                license_to_analyze = {
                    "id": license_id,
                    "text": license_text or "",
                    "spdx_data": license_data
                }

                # Analyze with LLM
                analysis = await self.llm_analyzer.analyze_license(license_id, license_text or "")
                compatibility = await self.llm_analyzer.extract_compatibility_rules(license_id, analysis)
                analysis["compatibility_rules"] = compatibility
                analysis["spdx_data"] = license_data  # raw SPDX entry for OSI/FSF/deprecated flags
                analysis["name"] = license_data.get("name", license_id)
                analysis = self._apply_known_corrections(license_id, analysis)
                analysis = self._apply_identifier_restrictions(license_id, analysis)
                analyzed_licenses.append(analysis)

                # Generate individual policy file immediately
                self._generate_individual_policy(analysis)

                # Save progress after each license
                self._save_progress(license_id)

                logger.info(f"✓ Completed {license_id} ({i}/{len(licenses_to_process)})")

            except Exception as e:
                logger.error(f"Failed to process {license_id}: {e}")
                continue

        # Step 4: Update master databases and compatibility matrix
        logger.info("Updating master databases...")
        all_analyzed = self._load_all_processed_licenses()
        self._update_master_databases(all_analyzed)

        # Convert YAML format to expected format for compatibility functions
        converted_analyzed = self._convert_yaml_format(analyzed_licenses)
        converted_all = self._convert_yaml_format(all_analyzed)

        # Merge: existing on-disk licenses + current batch (current batch takes precedence)
        by_id = {l.get("license_id"): l for l in converted_all}
        for lic in converted_analyzed:
            lid = lic.get("license_id")
            if lid:
                by_id[lid] = lic
        # Apply overrides to the full merged set so existing on-disk files are also corrected
        all_to_write = [
            self._apply_identifier_restrictions(
                l.get("license_id", ""),
                self._apply_known_corrections(l.get("license_id", ""), l),
            )
            for l in by_id.values()
        ]

        compatibility_matrix = self._generate_compatibility_matrix(all_to_write)
        obligation_database = self._generate_obligation_database(all_to_write)

        # Step 5: Generate modular per-license files and rebuild the full index
        logger.info("Generating modular per-license files...")
        self._generate_modular_license_files(
            all_to_write, compatibility_matrix, obligation_database,
            spdx_version=spdx_data.get("version", "")
        )
        # Rebuild index from ALL on-disk files so delta runs don't truncate the index
        self._rebuild_index_from_files(spdx_version=spdx_data.get("version", ""))

        # Skip legacy master database generation - using modular files only

        # Step 6: Generate validation data
        validation_report = self._validate_generated_data(analyzed_licenses)

        summary = {
            "total_licenses": len(analyzed_licenses),
            "spdx_version": spdx_data.get("version"),
            "generated_at": datetime.now().isoformat(),
            "output_directory": str(self.output_dir),
            "categories": self._count_categories(analyzed_licenses),
            "validation": validation_report
        }

        # Save summary
        summary_file = self.output_dir / "generation_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        # Step 7: Clean up temporary/intermediate files for packaging
        logger.info("Cleaning up temporary files for final package...")
        self._cleanup_temporary_files()

        logger.info(f"Data generation complete. Summary saved to {summary_file}")
        return summary

    def _generate_license_policies(self, licenses: List[Dict[str, Any]]) -> None:
        """Generate individual license policy files."""
        license_dir = self.output_dir / "licenses" / "spdx"
        license_dir.mkdir(parents=True, exist_ok=True)

        for license_data in licenses:
            license_id = license_data.get("license_id")
            if not license_id:
                continue

            # Create policy structure
            policy = {
                "license": {
                    "id": license_id,
                    "name": license_data.get("name", license_id),
                    "type": license_data.get("category", "permissive"),
                    "spdx_id": license_id,

                    "properties": license_data.get("permissions", {}),
                    "requirements": license_data.get("conditions", {}),
                    "limitations": license_data.get("limitations", {}),

                    "compatibility": self._format_compatibility_for_policy(
                        license_data.get("compatibility_rules", {})
                    ),

                    "obligations": license_data.get("obligations", []),
                    "key_requirements": license_data.get("key_requirements", [])
                }
            }

            # Save as YAML
            policy_file = license_dir / f"{license_id}.yaml"
            with open(policy_file, "w") as f:
                yaml.dump(policy, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Generated {len(licenses)} license policy files")

    def _format_compatibility_for_policy(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Format compatibility rules for policy file."""
        return {
            "static_linking": {
                "compatible_with": rules.get("static_linking", {}).get("compatible_with", []),
                "incompatible_with": rules.get("static_linking", {}).get("incompatible_with", []),
                "requires_review": rules.get("static_linking", {}).get("requires_review", [])
            },
            "dynamic_linking": {
                "compatible_with": rules.get("dynamic_linking", {}).get("compatible_with", []),
                "incompatible_with": rules.get("dynamic_linking", {}).get("incompatible_with", []),
                "requires_review": rules.get("dynamic_linking", {}).get("requires_review", [])
            },
            "contamination_effect": rules.get("contamination_effect", "none"),
            "notes": rules.get("notes", "")
        }

    def _generate_compatibility_matrix(self, licenses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate license compatibility matrix using split architecture."""
        from ospac.core.compatibility_matrix import CompatibilityMatrix

        # Initialize the matrix handler
        matrix_handler = CompatibilityMatrix(str(self.output_dir / "compatibility"))

        # Build full matrix for conversion
        full_matrix = {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "total_licenses": len(licenses),
            "compatibility": {}
        }

        # Build compatibility matrix
        for license1 in licenses:
            id1 = license1.get("license_id")
            if not id1:
                continue

            full_matrix["compatibility"][id1] = {}

            for license2 in licenses:
                id2 = license2.get("license_id")
                if not id2:
                    continue

                # Determine compatibility
                compat = self._check_license_compatibility(license1, license2)
                full_matrix["compatibility"][id1][id2] = compat

        # Save both formats: full matrix for backward compatibility and split for efficiency
        # Save full matrix (can be removed later if space is an issue)
        matrix_file = self.output_dir / "compatibility_matrix.json"
        with open(matrix_file, "w") as f:
            json.dump(full_matrix, f, indent=2)

        # Convert to efficient split format
        matrix_handler.build_from_full_matrix(str(matrix_file))

        logger.info(f"Generated compatibility matrix in both formats")
        logger.info(f"  Full matrix: {matrix_file}")
        logger.info(f"  Split format: {self.output_dir / 'compatibility'}")

        return full_matrix

    def _check_license_compatibility(self, license1: Dict, license2: Dict) -> Dict[str, Any]:
        """
        Derive compatibility between two licenses.

        Uses the LLM-generated compatibility_rules from license1 when available,
        falling back to category-level inference only when the specific pair is unlisted.
        """
        id2 = license2.get("license_id", "")
        cat2 = license2.get("category", "permissive")
        rules = license1.get("compatibility_rules", {})

        def resolve(section_key: str) -> str:
            section = rules.get(section_key, {})
            compatible = section.get("compatible_with", [])
            incompatible = section.get("incompatible_with", [])
            review = section.get("requires_review", [])

            if id2 in compatible:
                return "compatible"
            if id2 in incompatible:
                return "incompatible"
            if id2 in review:
                return "review_required"

            # Resolve category-based wildcards. Review wildcards were previously not
            # resolved at all, so a record whose derived lists say "review everything"
            # fell through to the category fallback instead.
            for entry in compatible:
                if entry == "category:any":
                    return "compatible"
                if entry == f"category:{cat2}":
                    return "compatible"
            for entry in incompatible:
                if entry == f"category:{cat2}":
                    return "incompatible"
            for entry in review:
                if entry == "category:any" or entry == f"category:{cat2}":
                    return "review_required"

            return None  # not specified, fall through to category logic

        static = resolve("static_linking")
        dynamic = resolve("dynamic_linking")
        distribution = resolve("distribution")

        # Category-level fallback for dimensions the record's lists do not cover. The
        # semantics mirror _derive_compatibility: permissive code can live inside a
        # copyleft work, so that pairing is compatible, and the old fallback that called
        # it incompatible is what wrote "MIT is incompatible with GPL" into the shipped
        # relationships tree.
        if static is None or dynamic is None:
            cat1 = license1.get("category", "permissive")
            open_cats = ("permissive", "public_domain")
            strong_cats = ("copyleft_strong", "network_copyleft")

            if cat1 in open_cats and cat2 in open_cats:
                fallback_static = fallback_dynamic = "compatible"
            elif (cat1 in strong_cats and cat2 in open_cats) or (
                    cat1 in open_cats and cat2 in strong_cats):
                fallback_static = fallback_dynamic = "compatible"
            elif cat1 in strong_cats or cat2 in strong_cats:
                fallback_static = fallback_dynamic = "review_required"
            elif cat1 == "copyleft_weak" or cat2 == "copyleft_weak":
                fallback_static, fallback_dynamic = "review_required", "compatible"
            else:
                fallback_static = fallback_dynamic = "review_required"

            if static is None:
                static = fallback_static
            if dynamic is None:
                dynamic = fallback_dynamic

        # Records carry no distribution section, so this dimension follows the static
        # verdict: whether two licenses can coexist in a distributed work is what the
        # static lists, including the known-incompatible pairs, already answer. The old
        # category guess here reported GPL-2.0 with Apache-2.0 as distributable together.
        if distribution is None:
            distribution = static

        return {
            "static_linking": static,
            "dynamic_linking": dynamic,
            "distribution": distribution,
        }

    def _generate_obligation_database(self, licenses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate obligation database."""
        obligations = {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "licenses": {}
        }

        for license_data in licenses:
            license_id = license_data.get("license_id")
            if not license_id:
                continue

            obligations["licenses"][license_id] = {
                "obligations": license_data.get("obligations", []),
                "key_requirements": license_data.get("key_requirements", []),
                "conditions": license_data.get("conditions", {}),
                "attribution_required": license_data.get("conditions", {}).get("include_copyright", False),
                "source_disclosure_required": license_data.get("conditions", {}).get("disclose_source", False),
                "notice_required": license_data.get("conditions", {}).get("include_notice", False)
            }

        # Save obligations
        obligations_file = self.output_dir / "obligation_database.json"
        with open(obligations_file, "w") as f:
            json.dump(obligations, f, indent=2)

        logger.info(f"Generated obligation database: {obligations_file}")
        return obligations

    def _generate_master_database(self, licenses: List[Dict[str, Any]],
                                 compatibility_matrix: Dict[str, Any],
                                 obligation_database: Dict[str, Any]) -> None:
        """Generate master database with all license information."""
        master_db = {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "total_licenses": len(licenses),
            "licenses": {}
        }

        for license_data in licenses:
            license_id = license_data.get("license_id")
            if not license_id:
                continue

            master_db["licenses"][license_id] = {
                "id": license_id,
                "name": license_data.get("name", license_id),
                "category": license_data.get("category"),
                "permissions": license_data.get("permissions"),
                "conditions": license_data.get("conditions"),
                "limitations": license_data.get("limitations"),
                "obligations": obligation_database["licenses"].get(license_id, {}).get("obligations", []),
                "compatibility_rules": license_data.get("compatibility_rules", {}),
                "spdx_metadata": {
                    "is_osi_approved": license_data.get("spdx_data", {}).get("isOsiApproved", False),
                    "is_fsf_libre": license_data.get("spdx_data", {}).get("isFsfLibre", False),
                    "is_deprecated": license_data.get("spdx_data", {}).get("isDeprecatedLicenseId", False)
                }
            }

        # Save master database
        master_file = self.output_dir / "ospac_license_database.json"
        with open(master_file, "w") as f:
            json.dump(master_db, f, indent=2)

        logger.info(f"Generated master database: {master_file}")

        # Also save as YAML for readability
        master_yaml = self.output_dir / "ospac_license_database.yaml"
        with open(master_yaml, "w") as f:
            yaml.dump(master_db, f, default_flow_style=False)

    def _count_categories(self, licenses: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count licenses by category."""
        categories = {}
        for license_data in licenses:
            cat = license_data.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        return categories

    def _validate_generated_data(self, licenses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate the generated data for completeness and consistency."""
        report = {
            "total_licenses": len(licenses),
            "missing_category": 0,
            "missing_permissions": 0,
            "missing_obligations": 0,
            "missing_compatibility": 0,
            "validation_errors": []
        }

        for license_data in licenses:
            license_id = license_data.get("license_id", "unknown")

            if not license_data.get("category"):
                report["missing_category"] += 1
                report["validation_errors"].append(f"{license_id}: Missing category")

            if not license_data.get("permissions"):
                report["missing_permissions"] += 1
                report["validation_errors"].append(f"{license_id}: Missing permissions")

            if not license_data.get("obligations"):
                report["missing_obligations"] += 1

            if not license_data.get("compatibility_rules"):
                report["missing_compatibility"] += 1

        report["is_valid"] = len(report["validation_errors"]) == 0

        return report

    def update_deprecated_licenses(self, spdx_licenses: List[Dict[str, Any]]) -> List[str]:
        """
        Stamp any existing per-license JSON files whose SPDX entry is now marked deprecated.
        Returns the list of license IDs that were updated.
        """
        licenses_json_dir = self.output_dir / "licenses" / "json"
        if not licenses_json_dir.exists():
            return []

        deprecated_ids = {
            l.get("licenseId") for l in spdx_licenses
            if l.get("isDeprecatedLicenseId", False) and l.get("licenseId")
        }

        updated = []
        for license_id in deprecated_ids:
            json_path = licenses_json_dir / f"{license_id}.json"
            if not json_path.exists():
                continue

            with open(json_path) as f:
                data = json.load(f)

            spdx_meta = data.get("license", {}).get("spdx_metadata", {})
            if spdx_meta.get("is_deprecated"):
                continue  # already flagged

            data.setdefault("license", {}).setdefault("spdx_metadata", {})["is_deprecated"] = True
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2)

            updated.append(license_id)
            logger.info(f"Flagged as deprecated: {license_id}")

        return updated

    def _generate_summary(self, all_licenses: List[Dict], spdx_data: Dict = None) -> Dict[str, Any]:
        """Return a summary when no new licenses needed processing."""
        licenses_json_dir = self.output_dir / "licenses" / "json"
        existing_count = len(list(licenses_json_dir.glob("*.json"))) if licenses_json_dir.exists() else 0
        spdx_data = spdx_data or {}
        return {
            "total_licenses": existing_count,
            "new_licenses_processed": 0,
            "spdx_version": spdx_data.get("version"),
            "generated_at": datetime.now().isoformat(),
            "output_directory": str(self.output_dir),
            "categories": {},
            "validation": {"total_licenses": existing_count, "is_valid": True, "validation_errors": []},
            "message": "All licenses already up to date",
        }

    def _cleanup_temporary_files(self) -> None:
        """Remove intermediate files produced during generation, keeping final artifacts."""
        import shutil

        logger.info("Cleaning up intermediate files...")

        # Transient files that are inputs/logs, not outputs
        for filename in [
            "generation_progress.json",
            "generation_summary.json",
            "ospac_license_database.yaml",
            "ospac_license_database.json",
            "obligation_database.json",
            "compatibility_matrix.json",
        ]:
            p = self.output_dir / filename
            if p.exists():
                p.unlink()
                logger.info(f"Removed: {filename}")

        # YAML intermediate files (superseded by licenses/json/)
        for dirname in ["obligations", "licenses/spdx"]:
            d = self.output_dir / dirname
            if d.exists():
                shutil.rmtree(d)
                logger.info(f"Removed directory: {dirname}")

        # Keep: licenses/json/, index.json, compatibility/ (split matrix for runtime queries)
        logger.info("Cleanup complete. Final artifacts: licenses/json/, index.json, compatibility/")

    def _generate_modular_license_files(self, licenses: List[Dict[str, Any]],
                                      compatibility_matrix: Dict[str, Any],
                                      obligation_database: Dict[str, Any],
                                      spdx_version: str = "") -> None:
        """Generate individual license files with obligations and compatibility data."""
        # Write to licenses/json/ to match the established on-disk layout
        licenses_json_dir = self.output_dir / "licenses" / "json"
        licenses_json_dir.mkdir(parents=True, exist_ok=True)

        generated_at = datetime.now().isoformat()

        for license_data in licenses:
            license_id = license_data.get("license_id")
            if not license_id:
                continue

            spdx_meta = license_data.get("spdx_data", {})
            compat_rules = license_data.get("compatibility_rules", {})
            category = license_data.get("category", "permissive")
            conditions = license_data.get("conditions", {})
            permissions = license_data.get("permissions", {})

            obligations, key_requirements = self._derive_obligations(
                license_id, category, conditions, permissions
            )

            # Use the same schema as existing files (license wrapper, type/properties/requirements)
            license_file_data = {
                "license": {
                    "id": license_id,
                    "name": license_data.get("name", license_id),
                    "type": category,
                    "spdx_id": license_id,
                    "properties": permissions,
                    "requirements": conditions,
                    "limitations": license_data.get("limitations", {}),
                    "compatibility": {
                        "static_linking": compat_rules.get("static_linking", {}),
                        "dynamic_linking": compat_rules.get("dynamic_linking", {}),
                        "contamination_effect": compat_rules.get("contamination_effect", "unknown"),
                        "notes": compat_rules.get("notes", ""),
                    },
                    "obligations": obligations,
                    "key_requirements": key_requirements,
                    "spdx_metadata": {
                        "is_osi_approved": spdx_meta.get("isOsiApproved", False),
                        "is_fsf_libre": spdx_meta.get("isFsfLibre", False),
                        "is_deprecated": spdx_meta.get("isDeprecatedLicenseId", False),
                    },
                    "generated": generated_at,
                    "spdx_list_version": spdx_version,
                }
            }

            license_file = licenses_json_dir / f"{license_id}.json"
            with open(license_file, "w") as f:
                json.dump(license_file_data, f, indent=2)

        logger.info(f"Wrote {len(licenses)} license files to {licenses_json_dir}")
        # Index is rebuilt from ALL files after the delta, see _rebuild_index_from_files

    def _rebuild_index_from_files(self, spdx_version: str = "") -> None:
        """Build index.json from ALL license JSON files on disk, not just the current batch."""
        licenses_json_dir = self.output_dir / "licenses" / "json"
        index = {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "spdx_list_version": spdx_version,
            "total_licenses": 0,
            "licenses": {},
        }

        for p in sorted(licenses_json_dir.glob("*.json")):
            try:
                with open(p) as f:
                    d = json.load(f)
                lic = d.get("license", {})
                lid = lic.get("id") or p.stem
                index["licenses"][lid] = {
                    "name": lic.get("name", lid),
                    "category": lic.get("type", "unknown"),
                    "file": f"licenses/json/{p.name}",
                    "is_deprecated": lic.get("spdx_metadata", {}).get("is_deprecated", False),
                    "obligations_count": len(lic.get("obligations", [])),
                }
            except Exception as e:
                logger.warning(f"Skipping {p.name} in index rebuild: {e}")

        index["total_licenses"] = len(index["licenses"])
        index_file = self.output_dir / "index.json"
        with open(index_file, "w") as f:
            json.dump(index, f, indent=2)

        logger.info(f"Rebuilt index.json: {index['total_licenses']} licenses, SPDX {spdx_version}")