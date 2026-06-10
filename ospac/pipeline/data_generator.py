"""
Policy data generator that produces OSPAC datasets.
Combines SPDX data with LLM analysis to generate comprehensive policy files.
"""

import json
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
    # LGPL permits linking from proprietary code — it is weak copyleft, not strong
    "LGPL-2.0-only":     {"category": "copyleft_weak"},
    "LGPL-2.0-or-later": {"category": "copyleft_weak"},
    "LGPL-2.1-only":     {"category": "copyleft_weak"},
    "LGPL-2.1-or-later": {"category": "copyleft_weak"},
    "LGPL-3.0-only":     {"category": "copyleft_weak"},
    "LGPL-3.0-or-later": {"category": "copyleft_weak"},
    # MPL-2.0 is file-level (weak) copyleft; LLM frequently calls it permissive
    "MPL-2.0":                       {"category": "copyleft_weak"},
    "MPL-2.0-no-copyleft-exception": {"category": "copyleft_weak"},
    # AGPL §13 requires network-use disclosure; LLM omits this condition
    "AGPL-3.0-only":     {"conditions": {"network_use_disclosure": True}},
    "AGPL-3.0-or-later": {"conditions": {"network_use_disclosure": True}},
}


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
            self._apply_known_corrections(l.get("license_id", ""), l)
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

            # Resolve category-based wildcards
            for entry in compatible:
                if entry == "category:any":
                    return "compatible"
                if entry == f"category:{cat2}":
                    return "compatible"
            for entry in incompatible:
                if entry == f"category:{cat2}":
                    return "incompatible"

            return None  # not specified — fall through to category logic

        static = resolve("static_linking")
        dynamic = resolve("dynamic_linking")
        distribution = resolve("distribution")

        # Category-level fallback for any dimension not covered by LLM rules
        if static is None or dynamic is None or distribution is None:
            cat1 = license1.get("category", "permissive")
            if cat1 == "permissive" and cat2 == "permissive":
                fallback_static, fallback_dynamic, fallback_dist = "compatible", "compatible", "compatible"
            elif cat1 == "copyleft_strong" or cat2 == "copyleft_strong":
                if cat1 == cat2:
                    fallback_static, fallback_dynamic, fallback_dist = "compatible", "compatible", "compatible"
                else:
                    # Dynamic linking may be permitted under some interpretations;
                    # distribution of the combined work under a different license is not.
                    fallback_static, fallback_dynamic, fallback_dist = "incompatible", "review_required", "incompatible"
            elif cat1 == "copyleft_weak" or cat2 == "copyleft_weak":
                fallback_static, fallback_dynamic, fallback_dist = "review_required", "compatible", "compatible"
            else:
                fallback_static, fallback_dynamic, fallback_dist = "unknown", "unknown", "unknown"

            if static is None:
                static = fallback_static
            if dynamic is None:
                dynamic = fallback_dynamic
            if distribution is None:
                distribution = fallback_dist

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
            obligs = obligation_database.get("licenses", {}).get(license_id, {})

            # Use the same schema as existing files (license wrapper, type/properties/requirements)
            license_file_data = {
                "license": {
                    "id": license_id,
                    "name": license_data.get("name", license_id),
                    "type": license_data.get("category", "permissive"),
                    "spdx_id": license_id,
                    "properties": license_data.get("permissions", {}),
                    "requirements": license_data.get("conditions", {}),
                    "limitations": license_data.get("limitations", {}),
                    "compatibility": {
                        "static_linking": compat_rules.get("static_linking", {}),
                        "dynamic_linking": compat_rules.get("dynamic_linking", {}),
                        "contamination_effect": compat_rules.get("contamination_effect", "unknown"),
                        "notes": compat_rules.get("notes", ""),
                    },
                    "obligations": obligs.get("obligations", license_data.get("obligations", [])),
                    "key_requirements": obligs.get("key_requirements", license_data.get("key_requirements", [])),
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
        # Index is rebuilt from ALL files after the delta — see _rebuild_index_from_files

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