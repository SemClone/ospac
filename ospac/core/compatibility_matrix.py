"""Efficient compatibility matrix storage and retrieval."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum


class CompatibilityStatus(Enum):
    """License compatibility status."""
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    REVIEW_NEEDED = "review_needed"
    UNKNOWN = "unknown"


class CompatibilityMatrix:
    """
    Efficient storage for license compatibility relationships.

    Uses sparse matrix representation to reduce storage size.
    Only stores non-default relationships (default is "unknown").
    """

    def __init__(self, data_dir: str = "data/compatibility"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # In-memory caches
        self._compatibility_cache: Dict[str, Dict[str, str]] = {}
        self._category_cache: Dict[str, List[str]] = {}
        self._metadata: Dict = {}

        # File paths
        self.metadata_file = self.data_dir / "metadata.json"
        self.categories_file = self.data_dir / "categories.json"
        self.relationships_dir = self.data_dir / "relationships"
        self.relationships_dir.mkdir(exist_ok=True)

    def build_from_full_matrix(self, full_matrix_path: str) -> None:
        """
        Convert full NxN matrix to efficient sparse format.

        Args:
            full_matrix_path: Path to full compatibility matrix JSON
        """
        print(f"Loading full matrix from {full_matrix_path}...")
        with open(full_matrix_path, 'r') as f:
            data = json.load(f)

        compatibility = data.get("compatibility", {})

        # Extract metadata
        self._metadata = {
            "version": data.get("version", "1.0"),
            "generated": data.get("generated"),
            "total_licenses": len(compatibility),
            "format": "sparse",
            "default_status": "unknown"
        }

        # Categorize licenses based on patterns
        categories = self._categorize_licenses(list(compatibility.keys()))

        # Save metadata and categories
        self._save_metadata()
        self._save_categories(categories)

        # Process and save relationships in chunks
        self._process_relationships(compatibility, categories)

    def _categorize_licenses(self, license_ids: List[str]) -> Dict[str, List[str]]:
        """Categorize licenses by family/type for efficient storage."""
        categories = {
            "gpl": [],
            "lgpl": [],
            "agpl": [],
            "bsd": [],
            "mit": [],
            "apache": [],
            "cc": [],
            "public_domain": [],
            "proprietary": [],
            "other": []
        }

        for license_id in license_ids:
            lid_lower = license_id.lower()

            if "gpl-" in lid_lower and "lgpl" not in lid_lower and "agpl" not in lid_lower:
                categories["gpl"].append(license_id)
            elif "lgpl" in lid_lower:
                categories["lgpl"].append(license_id)
            elif "agpl" in lid_lower:
                categories["agpl"].append(license_id)
            elif "bsd" in lid_lower:
                categories["bsd"].append(license_id)
            elif "mit" in lid_lower:
                categories["mit"].append(license_id)
            elif "apache" in lid_lower:
                categories["apache"].append(license_id)
            elif lid_lower.startswith("cc"):
                categories["cc"].append(license_id)
            elif "public" in lid_lower or "unlicense" in lid_lower or lid_lower == "0bsd":
                categories["public_domain"].append(license_id)
            elif any(prop in lid_lower for prop in ["proprietary", "commercial", "elastic"]):
                categories["proprietary"].append(license_id)
            else:
                categories["other"].append(license_id)

        # Remove empty categories
        return {k: v for k, v in categories.items() if v}

    def _process_relationships(self, compatibility: Dict, categories: Dict[str, List[str]]) -> None:
        """Process and store non-default relationships efficiently."""
        print("Processing compatibility relationships...")

        # Statistics
        total_relationships = 0
        stored_relationships = 0

        # Process by category to create smaller files
        for category, licenses in categories.items():
            category_relationships = {}

            for license_id in licenses:
                if license_id not in compatibility:
                    continue

                license_compat = compatibility[license_id]

                # Only store non-default relationships
                non_default = {
                    target: status
                    for target, status in license_compat.items()
                    if status and status != "unknown"
                }

                if non_default:
                    category_relationships[license_id] = non_default
                    stored_relationships += len(non_default)

                total_relationships += len(license_compat)

            # Save category relationships
            if category_relationships:
                category_file = self.relationships_dir / f"{category}.json"
                with open(category_file, 'w') as f:
                    json.dump(category_relationships, f, indent=2)
                print(f"  Saved {category}: {len(category_relationships)} licenses")

        compression_ratio = (1 - stored_relationships / total_relationships) * 100 if total_relationships > 0 else 0
        print(f"\nCompression: {stored_relationships}/{total_relationships} relationships stored")
        print(f"Space saved: {compression_ratio:.1f}%")

    def _save_metadata(self) -> None:
        """Save metadata to file."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self._metadata, f, indent=2)

    def _save_categories(self, categories: Dict[str, List[str]]) -> None:
        """Save license categories to file."""
        with open(self.categories_file, 'w') as f:
            json.dump(categories, f, indent=2)

    def load(self) -> None:
        """Load sparse matrix data into memory."""
        # Load metadata
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self._metadata = json.load(f)

        # Load categories
        if self.categories_file.exists():
            with open(self.categories_file, 'r') as f:
                self._category_cache = json.load(f)

        # Load relationships on demand (lazy loading)
        self._compatibility_cache = {}

    def get_compatibility(self, license1: str, license2: str) -> str:
        """
        Get compatibility status between two licenses.

        Args:
            license1: First license ID
            license2: Second license ID

        Returns:
            Compatibility status
        """
        # Check cache first
        if license1 in self._compatibility_cache:
            if license2 in self._compatibility_cache[license1]:
                return self._compatibility_cache[license1][license2]

        # Load from file if needed
        status = self._load_relationship(license1, license2)

        # Cache the result
        if license1 not in self._compatibility_cache:
            self._compatibility_cache[license1] = {}
        self._compatibility_cache[license1][license2] = status

        return status

    def _load_relationship(self, license1: str, license2: str) -> str:
        """Load specific relationship from file."""
        # Find category for license1
        category = self._find_category(license1)
        if not category:
            return self._metadata.get("default_status", "unknown")

        # Load category file if not cached
        category_file = self.relationships_dir / f"{category}.json"
        if not category_file.exists():
            return self._metadata.get("default_status", "unknown")

        with open(category_file, 'r') as f:
            relationships = json.load(f)

        # Get relationship
        if license1 in relationships:
            rel = relationships[license1].get(license2)
            # Handle dict format (with static/dynamic/distribution keys)
            if isinstance(rel, dict):
                # Return overall compatibility based on static linking (most restrictive)
                static = rel.get("static_linking", "unknown")
                if static == "compatible":
                    return "compatible"
                elif static == "incompatible":
                    return "incompatible"
                elif static == "review_required":
                    return "review_needed"
                return static
            # Handle string format
            elif isinstance(rel, str):
                return rel
            else:
                return self._metadata.get("default_status", "unknown")

        return self._metadata.get("default_status", "unknown")

    def _find_category(self, license_id: str) -> Optional[str]:
        """Find which category a license belongs to."""
        for category, licenses in self._category_cache.items():
            if license_id in licenses:
                return category
        return None

    def get_compatible_licenses(self, license_id: str) -> List[str]:
        """Get all licenses compatible with the given license."""
        compatible = []

        # Load all relationships for this license
        category = self._find_category(license_id)
        if category:
            category_file = self.relationships_dir / f"{category}.json"
            if category_file.exists():
                with open(category_file, 'r') as f:
                    relationships = json.load(f)

                if license_id in relationships:
                    for target, status in relationships[license_id].items():
                        # Handle dict format
                        if isinstance(status, dict):
                            if status.get("static_linking") == "compatible":
                                compatible.append(target)
                        # Handle string format
                        elif status == CompatibilityStatus.COMPATIBLE.value:
                            compatible.append(target)

        return sorted(compatible)

    def get_incompatible_licenses(self, license_id: str) -> List[str]:
        """Get all licenses incompatible with the given license."""
        incompatible = []

        # Load all relationships for this license
        category = self._find_category(license_id)
        if category:
            category_file = self.relationships_dir / f"{category}.json"
            if category_file.exists():
                with open(category_file, 'r') as f:
                    relationships = json.load(f)

                if license_id in relationships:
                    for target, status in relationships[license_id].items():
                        if status == CompatibilityStatus.INCOMPATIBLE.value:
                            incompatible.append(target)

        return sorted(incompatible)

    def export_full_matrix(self, output_path: str) -> None:
        """Export back to full matrix format if needed."""
        print("Exporting to full matrix format...")

        # Load all relationships
        full_compatibility = {}

        for category_file in self.relationships_dir.glob("*.json"):
            with open(category_file, 'r') as f:
                relationships = json.load(f)
                full_compatibility.update(relationships)

        # Fill in defaults for all license pairs
        all_licenses = []
        for licenses in self._category_cache.values():
            all_licenses.extend(licenses)

        complete_matrix = {}
        for license1 in all_licenses:
            complete_matrix[license1] = {}
            for license2 in all_licenses:
                if license1 in full_compatibility and license2 in full_compatibility[license1]:
                    complete_matrix[license1][license2] = full_compatibility[license1][license2]
                else:
                    complete_matrix[license1][license2] = self._metadata.get("default_status", "unknown")

        # Save full matrix
        output_data = {
            "version": self._metadata.get("version", "1.0"),
            "generated": self._metadata.get("generated"),
            "total_licenses": len(all_licenses),
            "compatibility": complete_matrix
        }

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"Exported full matrix to {output_path}")