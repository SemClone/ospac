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
from ospac.pipeline.llm_providers import (
    LLMConfig,
    LLMProvider,
    ProviderUnavailableError,
)
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


def _make_offline_analyzer() -> LicenseAnalyzer:
    """Build an analyzer with no usable LLM provider, without any network access."""
    analyzer = LicenseAnalyzer()
    analyzer.llm_provider = None
    return analyzer


class _StubProvider(LLMProvider):
    """Minimal concrete provider to exercise LLMProvider base class behavior."""

    async def analyze_license(self, license_id, license_text):
        return self._get_fallback_analysis(license_id)

    async def extract_compatibility_rules(self, license_id, analysis):
        return self._get_default_compatibility_rules(license_id, analysis)


class TestLicenseAnalyzer:
    """Test the LicenseAnalyzer class."""

    @pytest.mark.asyncio
    async def test_fallback_analysis_fails_closed(self):
        """Fallback analysis must deny permissions, not grant them."""
        analyzer = _make_offline_analyzer()

        analysis = await analyzer.analyze_license("MIT", "MIT License text")

        assert analysis["license_id"] == "MIT"
        assert analysis["category"] == "unknown"
        assert analysis["permissions"]["commercial_use"] is False
        assert analysis["permissions"]["modification"] is False
        assert analysis["permissions"]["distribution"] is False
        assert analysis["conditions"]["include_license"] is True

    @pytest.mark.asyncio
    async def test_fallback_never_claims_permissive(self):
        """No license, NonCommercial ones included, may fall back to permissive."""
        analyzer = _make_offline_analyzer()

        for license_id in ["CC-BY-NC-3.0-IGO", "GPL-3.0", "Apache-2.0", "CC0-1.0"]:
            analysis = await analyzer.analyze_license(license_id, "some text")
            assert analysis["category"] != "permissive"
            assert analysis["category"] == "unknown"
            assert analysis["permissions"]["commercial_use"] is False

    @pytest.mark.asyncio
    async def test_fallback_records_are_counted(self):
        """Every fallback analysis must be tracked so runs can fail closed."""
        analyzer = _make_offline_analyzer()
        assert analyzer.fallback_count == 0

        await analyzer.analyze_license("MIT", "MIT text")
        await analyzer.analyze_license("GPL-3.0", "GPL text")
        # Same license twice must not double-count
        await analyzer.analyze_license("MIT", "MIT text")

        assert analyzer.fallback_count == 2
        assert analyzer.fallback_licenses == {"MIT", "GPL-3.0"}

    @pytest.mark.asyncio
    async def test_extract_compatibility_rules(self):
        """Test extracting compatibility rules."""
        analyzer = _make_offline_analyzer()

        analysis = {"category": "permissive"}
        rules = await analyzer.extract_compatibility_rules("MIT", analysis)

        assert rules["static_linking"]["compatible_with"] == ["category:any"]
        assert rules["contamination_effect"] == "none"

    @pytest.mark.asyncio
    async def test_compatibility_rules_unknown_category_requires_review(self):
        """Unknown category must not default to compatible-with-anything."""
        analyzer = _make_offline_analyzer()

        rules = await analyzer.extract_compatibility_rules("Whatever-1.0", {"category": "unknown"})

        assert rules["static_linking"]["compatible_with"] == []
        assert rules["static_linking"]["requires_review"] == ["category:any"]
        assert rules["contamination_effect"] == "unknown"

    @pytest.mark.asyncio
    async def test_batch_analyze(self):
        """Test batch analysis of licenses."""
        analyzer = _make_offline_analyzer()

        licenses = [
            {"id": "MIT", "text": "MIT text"},
            {"id": "GPL-3.0", "text": "GPL text"}
        ]

        results = await analyzer.batch_analyze(licenses, max_concurrent=2)

        assert len(results) == 2
        assert results[0]["license_id"] == "MIT"
        assert results[1]["license_id"] == "GPL-3.0"
        assert "compatibility_rules" in results[0]


class TestProviderUnavailability:
    """Requesting an unavailable provider must fail loudly, not fall back."""

    def _patch_import_failure(self, package_name):
        """Simulate a missing package without uninstalling anything."""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == package_name:
                raise ImportError(f"No module named '{package_name}'")
            return real_import(name, *args, **kwargs)

        return patch("builtins.__import__", side_effect=fake_import)

    def test_missing_openai_package_raises(self):
        """Missing openai package must raise a clear error, not return fallback data."""
        with self._patch_import_failure("openai"):
            with pytest.raises(ProviderUnavailableError, match="OpenAI package not installed"):
                LicenseAnalyzer(provider="openai", require_provider=True)

    def test_missing_anthropic_package_raises(self):
        """Missing anthropic package must raise a clear error."""
        with self._patch_import_failure("anthropic"):
            with pytest.raises(ProviderUnavailableError, match="Anthropic package not installed"):
                LicenseAnalyzer(provider="claude", require_provider=True)

    def test_missing_ollama_package_raises(self):
        """Missing ollama package must raise a clear error."""
        with self._patch_import_failure("ollama"):
            with pytest.raises(ProviderUnavailableError, match="Ollama package not installed"):
                LicenseAnalyzer(provider="ollama", require_provider=True)

    def test_missing_openai_api_key_raises(self, monkeypatch):
        """Installed package but missing API key must also fail the preflight."""
        pytest.importorskip("openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ProviderUnavailableError, match="OPENAI_API_KEY"):
            LicenseAnalyzer(provider="openai", require_provider=True)

    def test_without_require_provider_degrades_to_no_provider(self):
        """Library callers that did not demand a provider keep the old soft behavior."""
        with self._patch_import_failure("openai"):
            analyzer = LicenseAnalyzer(provider="openai")

        assert analyzer.llm_provider is None

    def test_provider_fallback_fails_closed_and_is_counted(self):
        """Base provider fallback must under-permit and be recorded."""
        provider = _StubProvider(LLMConfig(provider="stub", model="stub-model"))

        analysis = provider._get_fallback_analysis("CC-BY-NC-3.0-IGO")

        assert analysis["category"] == "unknown"
        assert analysis["permissions"]["commercial_use"] is False
        assert analysis["permissions"]["distribution"] is False
        assert analysis["permissions"]["modification"] is False
        assert provider.fallback_count == 1
        assert provider.fallback_licenses == {"CC-BY-NC-3.0-IGO"}


class TestGenerateFallbackGate:
    """ospac data generate must not exit zero if fallback records were written."""

    def _make_fake_generator_class(self, fallback_licenses, captured_kwargs):
        class FakeAnalyzer:
            pass

        FakeAnalyzer.fallback_licenses = set(fallback_licenses)
        FakeAnalyzer.fallback_count = len(fallback_licenses)

        class FakeGenerator:
            def __init__(self, output_dir=None, **kwargs):
                captured_kwargs.update(kwargs)
                self.output_dir = output_dir
                self.llm_analyzer = FakeAnalyzer()

            async def generate_all_data(self, **kwargs):
                return {
                    "total_licenses": 3,
                    "output_directory": str(self.output_dir),
                    "categories": {"permissive": 2, "unknown": 1},
                    "validation": {"is_valid": True},
                }

        return FakeGenerator

    def _invoke_generate(self, monkeypatch, tmp_path, fallback_licenses):
        from click.testing import CliRunner
        from ospac.cli import commands as cli_commands

        captured_kwargs = {}
        fake_cls = self._make_fake_generator_class(fallback_licenses, captured_kwargs)
        monkeypatch.setattr(cli_commands, "PolicyDataGenerator", fake_cls)

        runner = CliRunner()
        result = runner.invoke(
            cli_commands.cli,
            ["data", "generate", "--output-dir", str(tmp_path),
             "--use-llm", "--llm-provider", "openai"],
        )
        return result, captured_kwargs

    def test_generate_fails_when_fallback_records_written(self, monkeypatch, tmp_path):
        """Any fallback record must be reported and fail the run."""
        result, _ = self._invoke_generate(
            monkeypatch, tmp_path, {"CC-BY-NC-3.0-IGO", "atc-game"}
        )

        assert result.exit_code != 0
        assert "fallback" in result.output.lower()
        assert "CC-BY-NC-3.0-IGO" in result.output

    def test_generate_succeeds_without_fallback_records(self, monkeypatch, tmp_path):
        """A clean LLM run exits zero and reports zero fallbacks."""
        result, captured_kwargs = self._invoke_generate(monkeypatch, tmp_path, set())

        assert result.exit_code == 0
        assert "No fallback records" in result.output
        # --use-llm must demand a working provider (preflight, fail loudly)
        assert captured_kwargs.get("require_provider") is True


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

        # index.json is rebuilt from all on-disk files after generation
        assert (temp_dir / "index.json").exists()

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