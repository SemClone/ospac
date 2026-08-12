"""
LLM-based license analyzer with configurable providers.
Supports OpenAI, Anthropic Claude, and local Ollama.
Analyzes licenses to extract obligations, compatibility rules, and classifications.
"""

import logging
from typing import Dict, List, Any, Optional, Set
import asyncio
import os

from ospac.pipeline.llm_providers import (
    LLMConfig,
    LLMProvider,
    ProviderUnavailableError,
    create_llm_provider
)

logger = logging.getLogger(__name__)


class LicenseAnalyzer:
    """
    Analyze licenses using configurable LLM providers.
    Supports OpenAI, Anthropic Claude, and local Ollama.
    """

    def __init__(self, provider: str = "ollama", model: str = None, api_key: str = None,
                 require_provider: bool = False, **kwargs):
        """
        Initialize the license analyzer with specified provider.

        Args:
            provider: LLM provider ("openai", "claude", "ollama")
            model: Model name (auto-selected if not provided)
            api_key: API key for cloud providers (or from environment)
            require_provider: If True, raise instead of degrading to fallback
                analysis when the provider cannot be initialized. Set this
                whenever the caller explicitly requested LLM analysis.
            **kwargs: Additional provider-specific configuration
        """
        self.provider_name = provider.lower()

        # License IDs analyzed by this analyzer's own fallback path
        # (provider missing). Provider-level fallbacks are tracked by the
        # provider itself; see the fallback_licenses property.
        self._fallback_licenses: Set[str] = set()

        # Auto-select models if not provided
        if not model:
            model = self._get_default_model(self.provider_name)

        # Get API key from environment if not provided
        if not api_key:
            api_key = self._get_api_key_from_env(self.provider_name)

        # Create configuration
        self.config = LLMConfig(
            provider=self.provider_name,
            model=model,
            api_key=api_key,
            **kwargs
        )

        # Initialize provider. This acts as a preflight check: it fails
        # before any license is processed, not on the first record.
        try:
            self.llm_provider = create_llm_provider(self.config)
            logger.info(f"Initialized {self.provider_name} provider with model {model}")
        except Exception as e:
            if require_provider:
                logger.error(f"LLM provider {self.provider_name} was requested but is unavailable: {e}")
                raise
            logger.error(f"Failed to initialize {self.provider_name} provider: {e}")
            logger.warning("Continuing without LLM: analyses will be conservative fallback records")
            self.llm_provider = None

    @property
    def fallback_licenses(self) -> Set[str]:
        """License IDs whose analysis came from a fallback instead of the LLM."""
        licenses = set(self._fallback_licenses)
        if self.llm_provider is not None:
            licenses |= self.llm_provider.fallback_licenses
        return licenses

    @property
    def fallback_count(self) -> int:
        """Number of licenses whose analysis fell back instead of using the LLM."""
        return len(self.fallback_licenses)

    def _get_default_model(self, provider: str) -> str:
        """Get default model for each provider."""
        defaults = {
            "openai": "gpt-4o-mini",
            "claude": "claude-haiku-4-5-20251001",
            "ollama": "llama3:latest"
        }
        return defaults.get(provider, "gpt-4o-mini")

    def _get_api_key_from_env(self, provider: str) -> Optional[str]:
        """Get API key from environment variables."""
        env_vars = {
            "openai": "OPENAI_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "ollama": None  # No API key needed for local Ollama
        }

        env_var = env_vars.get(provider)
        if env_var:
            api_key = os.getenv(env_var)
            if not api_key:
                logger.warning(f"No API key found in environment variable {env_var}")
            return api_key
        return None

    async def analyze_license(self, license_id: str, license_text: str) -> Dict[str, Any]:
        """
        Analyze a license using the configured LLM provider.

        Args:
            license_id: SPDX license identifier
            license_text: Full license text

        Returns:
            Analysis results
        """
        if not self.llm_provider:
            logger.warning(f"LLM provider not available, returning fallback for {license_id}")
            return self._get_fallback_analysis(license_id)

        return await self.llm_provider.analyze_license(license_id, license_text)

    def _get_fallback_analysis(self, license_id: str) -> Dict[str, Any]:
        """
        Conservative placeholder used when no LLM provider is available.

        Fails closed: category is "unknown" and every permission is denied,
        so a record built from this can never silently authorize use of an
        unanalyzed license. It is meant to be obviously wrong and to force
        manual review, never to pass as a real analysis.

        Args:
            license_id: SPDX license identifier

        Returns:
            Conservative placeholder analysis
        """
        self._fallback_licenses.add(license_id)
        return {
            "license_id": license_id,
            "category": "unknown",
            "permissions": {
                "commercial_use": False,
                "distribution": False,
                "modification": False,
                "patent_grant": False,
                "private_use": False
            },
            "conditions": {
                "disclose_source": True,
                "include_license": True,
                "include_copyright": True,
                "include_notice": True,
                "state_changes": True,
                "same_license": True,
                "network_use_disclosure": True
            },
            "limitations": {
                "liability": False,
                "warranty": False,
                "trademark_use": True
            },
            "compatibility": {
                "can_combine_with_permissive": False,
                "can_combine_with_weak_copyleft": False,
                "can_combine_with_strong_copyleft": False,
                "static_linking_restrictions": "unknown",
                "dynamic_linking_restrictions": "unknown"
            },
            "obligations": ["Automated license analysis failed, manual legal review required"],
            "key_requirements": ["Do not rely on this record, manual review required"]
        }

    async def extract_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract detailed compatibility rules for a license.

        Args:
            license_id: SPDX license identifier
            analysis: License analysis results

        Returns:
            Compatibility rules
        """
        if not self.llm_provider:
            self._fallback_licenses.add(license_id)
            return self._get_default_compatibility_rules(license_id, analysis)

        return await self.llm_provider.extract_compatibility_rules(license_id, analysis)

    def _get_default_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Get default compatibility rules based on license category."""
        category = analysis.get("category", "unknown")

        if category == "permissive":
            return {
                "static_linking": {
                    "compatible_with": ["category:any"],
                    "incompatible_with": [],
                    "requires_review": []
                },
                "dynamic_linking": {
                    "compatible_with": ["category:any"],
                    "incompatible_with": [],
                    "requires_review": []
                },
                "distribution": {
                    "can_distribute_with": ["category:any"],
                    "cannot_distribute_with": [],
                    "special_requirements": ["Include license and copyright notice"]
                },
                "contamination_effect": "none",
                "notes": "Permissive license with minimal restrictions"
            }

        elif category == "copyleft_strong":
            return {
                "static_linking": {
                    "compatible_with": [license_id, "category:copyleft_strong"],
                    "incompatible_with": ["category:permissive", "category:proprietary"],
                    "requires_review": ["category:copyleft_weak"]
                },
                "dynamic_linking": {
                    "compatible_with": ["category:any"],
                    "incompatible_with": [],
                    "requires_review": ["category:proprietary"]
                },
                "distribution": {
                    "can_distribute_with": [license_id],
                    "cannot_distribute_with": ["category:proprietary"],
                    "special_requirements": ["Source code must be provided", "Same license required"]
                },
                "contamination_effect": "full",
                "notes": "Strong copyleft with viral effect"
            }

        elif category == "copyleft_weak":
            return {
                "static_linking": {
                    "compatible_with": ["category:permissive", license_id],
                    "incompatible_with": [],
                    "requires_review": ["category:copyleft_strong"]
                },
                "dynamic_linking": {
                    "compatible_with": ["category:any"],
                    "incompatible_with": [],
                    "requires_review": []
                },
                "distribution": {
                    "can_distribute_with": ["category:any"],
                    "cannot_distribute_with": [],
                    "special_requirements": ["Allow relinking", "Provide LGPL source"]
                },
                "contamination_effect": "module",
                "notes": "Weak copyleft affecting only the library itself"
            }

        else:
            # Unknown or unrecognized category: fail closed, require review
            return {
                "static_linking": {
                    "compatible_with": [],
                    "incompatible_with": [],
                    "requires_review": ["category:any"]
                },
                "dynamic_linking": {
                    "compatible_with": [],
                    "incompatible_with": [],
                    "requires_review": ["category:any"]
                },
                "distribution": {
                    "can_distribute_with": [],
                    "cannot_distribute_with": [],
                    "special_requirements": ["Manual review required before distribution"]
                },
                "contamination_effect": "unknown",
                "notes": "Category unknown or unrecognized, manual review required"
            }

    async def batch_analyze(self, licenses: List[Dict[str, Any]], max_concurrent: int = 5) -> List[Dict[str, Any]]:
        """
        Analyze multiple licenses concurrently.

        Args:
            licenses: List of license data with id and text
            max_concurrent: Maximum concurrent analyses

        Returns:
            List of analysis results
        """
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_semaphore(license_data):
            async with semaphore:
                license_id = license_data.get("id")
                license_text = license_data.get("text", "")

                logger.info(f"Analyzing {license_id}")

                # Basic analysis
                analysis = await self.analyze_license(license_id, license_text)

                # Extract compatibility rules
                compatibility = await self.extract_compatibility_rules(license_id, analysis)
                analysis["compatibility_rules"] = compatibility

                return analysis

        # Process all licenses
        tasks = [analyze_with_semaphore(lic) for lic in licenses]
        results = await asyncio.gather(*tasks)

        return results