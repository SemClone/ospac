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

    def _make_fake_generator_class(self, fallback_licenses, captured_kwargs,
                                   analysis_fallbacks=None, rejected=()):
        class FakeAnalyzer:
            pass

        FakeAnalyzer.fallback_licenses = set(fallback_licenses)
        # Defaults to the whole set: a caller naming a fallback without saying which kind
        # means the fatal one.
        FakeAnalyzer.analysis_fallback_licenses = set(
            fallback_licenses if analysis_fallbacks is None else analysis_fallbacks)
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
                    "rejected_licenses": sorted(rejected),
                }

        return FakeGenerator

    def _invoke_generate(self, monkeypatch, tmp_path, fallback_licenses,
                         analysis_fallbacks=None, rejected=()):
        from click.testing import CliRunner
        from ospac.cli import commands as cli_commands

        captured_kwargs = {}
        fake_cls = self._make_fake_generator_class(
            fallback_licenses, captured_kwargs, analysis_fallbacks, rejected)
        monkeypatch.setattr(cli_commands, "PolicyDataGenerator", fake_cls)

        runner = CliRunner()
        result = runner.invoke(
            cli_commands.cli,
            ["data", "generate", "--output-dir", str(tmp_path),
             "--use-llm", "--llm-provider", "openai"],
        )
        return result, captured_kwargs

    def test_a_compatibility_only_fallback_does_not_fail_the_run(self, monkeypatch,
                                                                 tmp_path):
        """
        The compatibility lists are re-derived from the category before a record is
        written, so a fallback there leaves nothing fabricated behind. Failing on it
        refused a dataset that was fine.
        """
        result, _ = self._invoke_generate(
            monkeypatch, tmp_path, {"MIT"}, analysis_fallbacks=set())

        assert result.exit_code == 0, result.output
        assert "compatibility rules only" in result.output

    def test_a_rejected_licence_fails_the_run(self, monkeypatch, tmp_path):
        """
        A licence the generator refused has no fresh analysis, whether it was refused for
        a fabricated one or for a record that did not satisfy the dataset rules. The run
        cannot report success over it.
        """
        result, _ = self._invoke_generate(
            monkeypatch, tmp_path, set(), analysis_fallbacks=set(), rejected={"Zed"})

        assert result.exit_code == 1
        assert "Zed" in result.output

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
    @patch.object(LicenseAnalyzer, "analyze_license")
    async def test_generate_all_data(self, mock_analyze, mock_get_text,
                                     mock_download, temp_dir, mock_spdx_data):
        """Test generating all data."""
        # Setup mocks
        mock_download.return_value = mock_spdx_data
        mock_get_text.return_value = "License text"

        # analyze_license is what generate_all_data calls. Patching batch_analyze left
        # the real one running, and with no LLM configured it returns a maximally
        # restrictive fallback that was then written as MIT's record.
        #
        # A complete analysis, with MIT's real values. A response missing any of these
        # booleans is refused rather than written with the gap.
        async def analysis(license_id, text):
            return {
                "license_id": license_id,
                "name": "MIT License",
                "category": "permissive",
                "permissions": {"commercial_use": True, "distribution": True,
                                "modification": True, "patent_grant": False,
                                "private_use": True},
                "conditions": {"disclose_source": False, "include_license": True,
                               "include_copyright": True, "include_notice": False,
                               "state_changes": False, "same_license": False,
                               "network_use_disclosure": False},
                "limitations": {"liability": True, "warranty": True,
                                "trademark_use": False},
                "obligations": ["Include license"],
                "compatibility_rules": {},
            }
        mock_analyze.side_effect = analysis

        generator = PolicyDataGenerator(output_dir=temp_dir)
        summary = await generator.generate_all_data(limit=1)

        assert summary["total_licenses"] == 1
        assert summary["rejected_licenses"] == []
        assert "categories" in summary
        assert "validation" in summary
        assert (temp_dir / "licenses" / "json" / "MIT.json").exists()

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

        # Permissive code can be incorporated into a copyleft work, so the pairing is
        # compatible; the combined work is simply GPL. This test used to assert
        # incompatible, which is the claim that poisoned the relationships tree.
        compat = generator._check_license_compatibility(gpl, mit)
        assert compat["static_linking"] == "compatible"
        assert compat["distribution"] == "compatible"

        # Known incompatible pairs resolve from the record's lists across every
        # dimension, including distribution, which used to fall back to a category
        # guess that called GPL-2.0 and Apache-2.0 distributable together.
        gpl2 = {"license_id": "GPL-2.0-only", "category": "copyleft_strong",
                "compatibility_rules": {
                    "static_linking": {"compatible_with": ["category:permissive"],
                                       "incompatible_with": ["Apache-2.0"],
                                       "requires_review": []},
                    "dynamic_linking": {"compatible_with": ["category:permissive"],
                                        "incompatible_with": ["Apache-2.0"],
                                        "requires_review": []}}}
        apache2 = {"license_id": "Apache-2.0", "category": "permissive"}
        compat = generator._check_license_compatibility(gpl2, apache2)
        assert compat["static_linking"] == "incompatible"
        assert compat["distribution"] == "incompatible"

        # A review-everything record, the derived shape for restricted categories,
        # resolves to review rather than falling through to a category guess.
        nc = {"license_id": "CC-BY-NC-4.0", "category": "noncommercial",
              "compatibility_rules": {
                  "static_linking": {"compatible_with": [], "incompatible_with": [],
                                     "requires_review": ["category:any"]},
                  "dynamic_linking": {"compatible_with": [], "incompatible_with": [],
                                      "requires_review": ["category:any"]}}}
        compat = generator._check_license_compatibility(nc, mit)
        assert compat["static_linking"] == "review_required"
        assert compat["distribution"] == "review_required"

        # Same copyleft is compatible
        # Sharing the strong-copyleft category does not make two licenses compatible:
        # GPL-2.0 and GPL-3.0 share it and are incompatible. A genuine self-pair
        # resolves through the record's own id in its derived lists; a bare category
        # tie is an unknown pair and gets review.
        compat = generator._check_license_compatibility(gpl, gpl)
        assert compat["static_linking"] == "review_required"

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

class TestAnalysisCategoryCoercion:
    """
    The category coercion must read the record's final booleans, not only the
    identifier-derived restrictions. The first real analysis run returned
    modification false for Adobe-Glyph while calling it permissive; the identifier
    carries no ND marker, so the record shipped to validation with a contradiction.
    """

    def _coerce(self, license_id, name, category, permissions, conditions):
        from ospac.pipeline.data_generator import PolicyDataGenerator

        analysis = {"license_id": license_id, "name": name, "category": category,
                    "permissions": permissions, "conditions": conditions}
        return PolicyDataGenerator._apply_identifier_restrictions(
            PolicyDataGenerator, license_id, analysis)["category"]

    def test_model_reported_no_modification_is_coerced(self):
        assert self._coerce(
            "Adobe-Glyph", "Adobe Glyph List License", "permissive",
            {"commercial_use": True, "modification": False}, {},
        ) == "no_derivatives"

    def test_model_reported_noncommercial_is_coerced(self):
        assert self._coerce(
            "Some-License", "Some License", "permissive",
            {"commercial_use": False, "modification": True}, {},
        ) == "noncommercial"

    def test_model_reported_share_alike_is_coerced(self):
        assert self._coerce(
            "Some-License", "Some License", "permissive",
            {"commercial_use": True, "modification": True}, {"same_license": True},
        ) == "copyleft_weak"

    def test_genuinely_permissive_record_is_untouched(self):
        assert self._coerce(
            "MIT", "MIT License", "permissive",
            {"commercial_use": True, "modification": True}, {"same_license": False},
        ) == "permissive"


class TestAnIncompleteAnalysisIsNotARecord:
    """
    An LLM response that drops a boolean used to produce a record missing that key. The
    validator only warned, so the sync's first gate passed it and the schema test failed
    later with a message naming the schema, when the fault was upstream. Defaulting the
    missing boolean instead would be worse: disclose_source False on a copyleft licence
    is wrong and silent, the same failure as the permissive default that once recorded
    every NonCommercial licence as commercially usable.
    """

    @staticmethod
    def _analysis(license_id):
        from ospac.pipeline.data_generator import PolicyDataGenerator
        from ospac.utils.data_validation import (REQUIRED_LIMITATIONS,
                                                 REQUIRED_PROPERTIES,
                                                 REQUIRED_REQUIREMENTS)
        return {
            "license_id": license_id,
            "name": f"{license_id} name",
            "category": "permissive",
            "permissions": {k: True for k in REQUIRED_PROPERTIES},
            "conditions": {k: False for k in REQUIRED_REQUIREMENTS},
            "limitations": {k: True for k in REQUIRED_LIMITATIONS},
            "compatibility_rules": PolicyDataGenerator._derive_compatibility(
                license_id, "permissive"),
            "spdx_data": {},
        }

    def _generate(self, tmp_path, analyses):
        """Filter as generate_all_data does, then write what survived."""
        from ospac.pipeline.data_generator import PolicyDataGenerator

        generator = PolicyDataGenerator.__new__(PolicyDataGenerator)
        generator.output_dir = tmp_path
        kept, _ = generator._reject_incomplete_records(analyses)
        generator._generate_modular_license_files(kept, {}, {}, spdx_version="test")
        return sorted(p.stem for p in (tmp_path / "licenses" / "json").glob("*.json"))

    def test_a_complete_analysis_is_written(self, tmp_path):
        assert self._generate(tmp_path, [self._analysis("TEST-1.0")]) == ["TEST-1.0"]

    def test_a_missing_boolean_skips_the_record(self, tmp_path, caplog):
        import logging

        partial = self._analysis("TEST-2.0")
        del partial["conditions"]["include_notice"]

        with caplog.at_level(logging.ERROR):
            written = self._generate(tmp_path, [self._analysis("TEST-1.0"), partial])

        assert written == ["TEST-1.0"]
        assert "requirements.include_notice" in caplog.text
        assert "TEST-2.0" in caplog.text

    def test_every_block_is_checked(self, tmp_path):
        for block, key in (("permissions", "commercial_use"),
                           ("conditions", "disclose_source"),
                           ("limitations", "liability")):
            partial = self._analysis("TEST-3.0")
            del partial[block][key]
            assert self._generate(tmp_path, [partial]) == [], f"{block}.{key} was written"

    def test_an_llm_fallback_is_not_a_record(self):
        """
        With no provider configured, analyze_license returns a maximally restrictive
        fallback: every permission false, every condition true. Written out, that is a
        fabricated record claiming MIT forbids commercial use and requires source
        disclosure. It is refused for the same reason an incomplete one is.
        """
        import asyncio

        from ospac.pipeline.data_generator import PolicyDataGenerator
        from ospac.pipeline.llm_analyzer import LicenseAnalyzer

        # llm_provider is forced to None rather than left to the environment. A machine
        # with Ollama installed and running would otherwise send a live request and get
        # a real analysis, and the test would assert nothing.
        analyzer = LicenseAnalyzer()
        analyzer.llm_provider = None

        # An id outside KNOWN_LICENSES, which is the case schema validation cannot catch:
        # every permission false coerces to noncommercial and the record is then
        # internally consistent.
        fallback = asyncio.run(analyzer.analyze_license("Zed", "Zed license text"))
        fallback["license_id"] = "Zed"
        fallback["name"] = "Zed License"
        assert "Zed" in analyzer.analysis_fallback_licenses

        generator = PolicyDataGenerator.__new__(PolicyDataGenerator)
        generator.llm_analyzer = analyzer
        kept, rejected = generator._reject_incomplete_records([fallback])
        assert kept == []
        assert rejected == {"Zed"}

    def test_a_provider_compatibility_fallback_alone_is_not_fatal(self):
        """
        The provider records both kinds through _record_fallback. Unioning its whole set
        into the analysis set put a valid analysis whose compatibility rules fell back
        back into the fatal category, which is the conflation the split exists to remove.
        """
        from ospac.pipeline.llm_providers import LLMProvider

        class Provider(LLMProvider):
            def __init__(self):
                super().__init__("model")

            async def analyze_license(self, *args):
                pass

            async def extract_compatibility_rules(self, *args):
                pass

        provider = Provider()
        provider._record_fallback("A", "analysis failed")
        provider._record_fallback("B", "compat defaults", analysis=False)

        assert provider.fallback_licenses == {"A", "B"}
        assert provider.analysis_fallback_licenses == {"A"}

    def test_a_compatibility_fallback_alone_is_not_fatal(self):
        """
        The compatibility lists are re-derived from the category before a record is
        written, so a fallback there is discarded rather than published. Rejecting on the
        wider fallback_licenses would have thrown away good analyses.
        """
        import asyncio

        from ospac.pipeline.llm_analyzer import LicenseAnalyzer

        analyzer = LicenseAnalyzer()
        analyzer.llm_provider = None
        asyncio.run(analyzer.extract_compatibility_rules("Zed", {"category": "permissive"}))

        assert "Zed" in analyzer.fallback_licenses
        assert "Zed" not in analyzer.analysis_fallback_licenses

    def test_a_rejected_licence_is_absent_from_the_derived_artifacts(self, tmp_path):
        from ospac.pipeline.data_generator import PolicyDataGenerator

        # The filter runs before the compatibility matrix, the obligation database and
        # the summary counts are built. Dropping a licence at the point of writing
        # instead published relationships and a count for a licence that has no record.
        partial = self._analysis("TEST-2.0")
        del partial["conditions"]["include_notice"]

        generator = PolicyDataGenerator.__new__(PolicyDataGenerator)
        generator.output_dir = tmp_path
        kept, rejected = generator._reject_incomplete_records(
            [self._analysis("TEST-1.0"), partial])

        assert [l["license_id"] for l in kept] == ["TEST-1.0"]
        assert rejected == {"TEST-2.0"}

    def test_a_missing_category_is_not_permissive(self, tmp_path):
        """
        A record whose analysis states no category was published as permissive with
        compatible_with ["category:any"], which is the silent permissive fallback this
        pipeline already had to fix once, on the path that rewrites all 733 records.
        """
        from ospac.pipeline.data_generator import PolicyDataGenerator

        analysis = self._analysis("TEST-4.0")
        del analysis["category"]

        generator = PolicyDataGenerator.__new__(PolicyDataGenerator)
        assert generator._assemble_record(analysis, "")["license"]["type"] is None
        kept, rejected = generator._reject_incomplete_records([analysis])
        assert kept == []
        assert rejected == {"TEST-4.0"}

    def test_an_empty_type_is_rejected_by_the_validator(self):
        import json

        from ospac.utils.data_validation import validate_license

        # The key being present satisfied the top-level requirement and the domain check
        # skipped a falsy value, so type: null validated clean for any licence outside
        # KNOWN_LICENSES and was published.
        record = json.loads(
            (Path(__file__).parent.parent / "ospac" / "data" / "licenses" / "json"
             / "Zed.json").read_text())["license"]
        assert validate_license("Zed", record)[0] == []

        record["type"] = None
        assert any("type is empty" in e for e in validate_license("Zed", record)[0])

    def test_a_compatibility_fallback_leaves_no_prose_behind(self):
        import asyncio

        from ospac.pipeline.data_generator import PolicyDataGenerator
        from ospac.pipeline.llm_analyzer import LicenseAnalyzer

        # The lists are re-derived, but a note survived the derivation, so a fallback
        # published "Category unknown or unrecognized" as the compatibility note of a
        # licence whose category was known.
        analyzer = LicenseAnalyzer()
        analyzer.llm_provider = None
        rules = asyncio.run(
            analyzer.extract_compatibility_rules("MPL-2.0", {"category": "copyleft_weak"}))

        generator = PolicyDataGenerator.__new__(PolicyDataGenerator)
        applied = generator._apply_identifier_restrictions("MPL-2.0", {
            "category": "copyleft_weak", "compatibility_rules": rules,
            "permissions": {}, "conditions": {}})

        notes = applied["compatibility_rules"]["notes"]
        assert "unknown or unrecognized" not in notes
        assert "Weak copyleft" in notes

    def test_the_record_id_is_the_one_the_pipeline_asked_about(self):
        """
        Filenames, the merge, rejection and the fallback match all key off license_id. A
        model echoing a different id overwrote that licence's record and left its own
        unprocessed, to be re-queued every month.
        """
        import inspect

        from ospac.pipeline.data_generator import PolicyDataGenerator

        source = inspect.getsource(PolicyDataGenerator.generate_all_data)
        assert 'analysis["license_id"] = license_id' in source

    def test_an_invalid_disk_record_stops_the_run_rather_than_half_regenerating(self):
        """
        Dropping such a record from the write set does not unpublish it: nothing deletes
        it, and the index and alias rebuilds read it straight back off disk. It would
        stay in index.json and aliases.json while the compatibility matrix omitted it.
        """
        import inspect

        from ospac.pipeline.data_generator import PolicyDataGenerator

        source = inspect.getsource(PolicyDataGenerator.generate_all_data)
        stop = source.index("if stale:")
        derive = source.index("_generate_compatibility_matrix")
        assert stop < derive, "the check must run before anything is derived"
        assert "raise RuntimeError" in source[stop:derive]

    def test_a_written_record_satisfies_the_normative_schema(self, tmp_path):
        import json

        import jsonschema

        self._generate(tmp_path, [self._analysis("TEST-1.0")])
        record = json.loads((tmp_path / "licenses" / "json" / "TEST-1.0.json").read_text())
        schema = json.loads((Path(__file__).parent.parent / "schemas"
                             / "license_schema.json").read_text())
        jsonschema.validate(record, schema)
