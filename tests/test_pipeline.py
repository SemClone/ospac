"""
Tests for the data processing pipeline.
"""

import os
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from ospac.pipeline.spdx_processor import SPDXProcessor
from ospac.pipeline.llm_analyzer import LicenseAnalyzer
from ospac.pipeline.data_generator import PolicyDataGenerator

# Skip LLM tests in CI environment
skip_llm_tests = pytest.mark.skipif(
    os.environ.get("CI", "false") == "true",
    reason="LLM tests skipped in CI environment"
)


class TestSPDXProcessor:
    """Test the SPDXProcessor class."""

    def test_initialize_processor(self, temp_dir):
        """Test initializing the SPDX processor."""
        processor = SPDXProcessor(cache_dir=temp_dir)

        assert processor.cache_dir == temp_dir
        assert processor.licenses == {}
        assert processor.exceptions == {}

    @patch("requests.get")
    def test_download_spdx_data(self, mock_get, temp_dir, mock_spdx_data):
        """Test downloading SPDX data."""
        # Mock the response
        mock_response = Mock()
        mock_response.json.return_value = mock_spdx_data
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        processor = SPDXProcessor(cache_dir=temp_dir)
        data = processor.download_spdx_data(force=True)

        assert len(data["licenses"]) == 3
        assert data["version"] == "3.22"
        assert mock_get.called

    def test_download_cached_data(self, temp_dir, mock_spdx_data):
        """Test loading cached SPDX data."""
        # Create cache files
        licenses_cache = temp_dir / "licenses.json"
        exceptions_cache = temp_dir / "exceptions.json"

        with open(licenses_cache, "w") as f:
            json.dump(mock_spdx_data, f)

        with open(exceptions_cache, "w") as f:
            json.dump({"exceptions": []}, f)

        processor = SPDXProcessor(cache_dir=temp_dir)
        data = processor.download_spdx_data(force=False)

        assert len(data["licenses"]) == 3
        assert data["version"] == "3.22"

    def test_extract_basic_info(self):
        """Test extracting basic info from license data."""
        processor = SPDXProcessor()

        license_data = {
            "licenseId": "MIT",
            "name": "MIT License",
            "reference": "https://spdx.org/licenses/MIT.html",
            "isDeprecatedLicenseId": False,
            "isOsiApproved": True,
            "isFsfLibre": True,
            "seeAlso": ["https://opensource.org/licenses/MIT"]
        }

        info = processor.extract_basic_info(license_data)

        assert info["id"] == "MIT"
        assert info["name"] == "MIT License"
        assert info["is_osi_approved"] is True
        assert info["is_fsf_libre"] is True
        assert info["is_deprecated"] is False

    def test_categorize_license(self):
        """Test license categorization."""
        processor = SPDXProcessor()

        assert processor.categorize_license("MIT") == "permissive"
        assert processor.categorize_license("Apache-2.0") == "permissive"
        assert processor.categorize_license("GPL-3.0") == "copyleft_strong"
        assert processor.categorize_license("LGPL-3.0") == "copyleft_weak"
        assert processor.categorize_license("AGPL-3.0") == "copyleft_strong"
        assert processor.categorize_license("CC0-1.0") == "public_domain"
        assert processor.categorize_license("Unknown-License") == "permissive"

    def test_save_processed_data(self, temp_dir):
        """Test saving processed data."""
        processor = SPDXProcessor()

        data = [
            {"id": "MIT", "category": "permissive", "is_osi_approved": True},
            {"id": "GPL-3.0", "category": "copyleft_strong", "is_osi_approved": True}
        ]

        output_dir = temp_dir / "output"
        processor.save_processed_data(data, output_dir)

        # Check files were created
        json_file = output_dir / "spdx_processed.json"
        stats_file = output_dir / "spdx_stats.yaml"

        assert json_file.exists()
        assert stats_file.exists()

        # Verify JSON content
        with open(json_file) as f:
            saved_data = json.load(f)

        assert len(saved_data["licenses"]) == 2
        assert saved_data["total"] == 2


class TestLicenseAnalyzer:
    """Test the LicenseAnalyzer class."""

    @skip_llm_tests
    @pytest.mark.asyncio
    async def test_get_fallback_analysis(self):
        """Test fallback analysis when LLM is not available."""
        analyzer = LicenseAnalyzer()
        analyzer.agent = None  # Ensure no agent

        analysis = await analyzer.analyze_license("MIT", "MIT License text")

        assert analysis["license_id"] == "MIT"
        assert analysis["category"] == "permissive"
        assert analysis["permissions"]["commercial_use"] is True
        assert analysis["conditions"]["include_license"] is True

    @skip_llm_tests
    @pytest.mark.asyncio
    async def test_analyze_gpl_fallback(self):
        """Test GPL license analysis fallback."""
        analyzer = LicenseAnalyzer()
        analyzer.agent = None

        analysis = await analyzer.analyze_license("GPL-3.0", "GPL text")

        assert analysis["license_id"] == "GPL-3.0"
        assert analysis["category"] == "copyleft_strong"
        assert analysis["conditions"]["disclose_source"] is True
        assert analysis["conditions"]["same_license"] is True
        # Fallback analysis returns basic compatibility info
        assert "compatibility" in analysis

    @skip_llm_tests
    @pytest.mark.asyncio
    async def test_extract_compatibility_rules(self):
        """Test extracting compatibility rules."""
        analyzer = LicenseAnalyzer()
        analyzer.agent = None

        analysis = {"category": "permissive"}
        rules = await analyzer.extract_compatibility_rules("MIT", analysis)

        assert rules["static_linking"]["compatible_with"] == ["category:any"]
        assert rules["contamination_effect"] == "none"

    @skip_llm_tests
    @pytest.mark.asyncio
    async def test_batch_analyze(self):
        """Test batch analysis of licenses."""
        analyzer = LicenseAnalyzer()
        analyzer.agent = None

        licenses = [
            {"id": "MIT", "text": "MIT text"},
            {"id": "GPL-3.0", "text": "GPL text"}
        ]

        results = await analyzer.batch_analyze(licenses, max_concurrent=2)

        assert len(results) == 2
        assert results[0]["license_id"] == "MIT"
        assert results[1]["license_id"] == "GPL-3.0"
        assert "compatibility_rules" in results[0]


class TestPolicyDataGenerator:
    """Test the PolicyDataGenerator class."""

    def test_initialize_generator(self, temp_dir):
        """Test initializing the data generator."""
        generator = PolicyDataGenerator(output_dir=temp_dir)

        assert generator.output_dir == temp_dir
        assert (temp_dir / "licenses").exists()
        assert (temp_dir / "compatibility").exists()
        assert (temp_dir / "obligations").exists()

    @skip_llm_tests
    @pytest.mark.asyncio
    @patch.object(SPDXProcessor, "download_spdx_data")
    @patch.object(SPDXProcessor, "get_license_text")
    @patch.object(LicenseAnalyzer, "batch_analyze")
    async def test_generate_all_data(self, mock_analyze, mock_get_text,
                                     mock_download, temp_dir, mock_spdx_data):
        """Test generating all data."""
        # Setup mocks
        mock_download.return_value = mock_spdx_data
        mock_get_text.return_value = "License text"

        mock_analyze.return_value = [
            {
                "license_id": "MIT",
                "name": "MIT License",
                "category": "permissive",
                "permissions": {"commercial_use": True},
                "conditions": {"include_license": True},
                "obligations": ["Include license"],
                "compatibility_rules": {}
            }
        ]

        generator = PolicyDataGenerator(output_dir=temp_dir)
        summary = await generator.generate_all_data(limit=1)

        assert summary["total_licenses"] == 1
        assert "categories" in summary
        assert "validation" in summary

        # Check generated files
        assert (temp_dir / "generation_summary.json").exists()

    def test_count_categories(self):
        """Test counting license categories."""
        generator = PolicyDataGenerator()

        licenses = [
            {"category": "permissive"},
            {"category": "permissive"},
            {"category": "copyleft_strong"},
            {"category": "copyleft_weak"}
        ]

        counts = generator._count_categories(licenses)

        assert counts["permissive"] == 2
        assert counts["copyleft_strong"] == 1
        assert counts["copyleft_weak"] == 1

    def test_check_license_compatibility(self):
        """Test checking compatibility between licenses."""
        generator = PolicyDataGenerator()

        mit = {"category": "permissive"}
        apache = {"category": "permissive"}
        gpl = {"category": "copyleft_strong"}

        # Permissive licenses are compatible
        compat = generator._check_license_compatibility(mit, apache)
        assert compat["static_linking"] == "compatible"

        # GPL with permissive is incompatible
        compat = generator._check_license_compatibility(gpl, mit)
        assert compat["static_linking"] == "incompatible"

        # Same copyleft is compatible
        compat = generator._check_license_compatibility(gpl, gpl)
        assert compat["static_linking"] == "compatible"

    def test_validate_generated_data(self):
        """Test validating generated data."""
        generator = PolicyDataGenerator()

        licenses = [
            {
                "license_id": "MIT",
                "category": "permissive",
                "permissions": {"commercial_use": True},
                "obligations": ["Include license"],
                "compatibility_rules": {}
            },
            {
                "license_id": "Unknown",
                # Missing category
                "permissions": {},
                # Missing obligations
            }
        ]

        report = generator._validate_generated_data(licenses)

        assert report["total_licenses"] == 2
        assert report["missing_category"] == 1
        assert report["missing_obligations"] == 1
        assert report["is_valid"] is False
        assert len(report["validation_errors"]) > 0