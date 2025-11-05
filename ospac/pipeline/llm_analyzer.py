"""
LLM-based license analyzer with configurable providers.
Supports OpenAI, Anthropic Claude, and local Ollama.
Analyzes licenses to extract obligations, compatibility rules, and classifications.
"""

import logging
from typing import Dict, List, Any, Optional
import asyncio
import os

from ospac.pipeline.llm_providers import (
    LLMConfig,
    LLMProvider,
    create_llm_provider
)

logger = logging.getLogger(__name__)


class LicenseAnalyzer:
    """
    Analyze licenses using configurable LLM providers.
    Supports OpenAI, Anthropic Claude, and local Ollama.
    """

    def __init__(self, provider: str = "ollama", model: str = None, api_key: str = None, **kwargs):
        """
        Initialize the license analyzer with specified provider.

        Args:
            provider: LLM provider ("openai", "claude", "ollama")
            model: Model name (auto-selected if not provided)
            api_key: API key for cloud providers (or from environment)
            **kwargs: Additional provider-specific configuration
        """
        self.provider_name = provider.lower()

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

        # Initialize provider
        try:
            self.llm_provider = create_llm_provider(self.config)
            logger.info(f"Initialized {self.provider_name} provider with model {model}")
        except Exception as e:
            logger.error(f"Failed to initialize {self.provider_name} provider: {e}")
            self.llm_provider = None

    def _get_default_model(self, provider: str) -> str:
        """Get default model for each provider."""
        defaults = {
            "openai": "gpt-4o-mini",
            "claude": "claude-3-haiku-20240307",
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
        Get fallback analysis based on known license patterns.

        Args:
            license_id: SPDX license identifier

        Returns:
            Basic analysis results
        """
        # Default analysis structure
        analysis = {
            "license_id": license_id,
            "category": "permissive",
            "permissions": {
                "commercial_use": True,
                "distribution": True,
                "modification": True,
                "patent_grant": False,
                "private_use": True
            },
            "conditions": {
                "disclose_source": False,
                "include_license": True,
                "include_copyright": True,
                "include_notice": False,
                "state_changes": False,
                "same_license": False,
                "network_use_disclosure": False
            },
            "limitations": {
                "liability": False,
                "warranty": False,
                "trademark_use": False
            },
            "compatibility": {
                "can_combine_with_permissive": True,
                "can_combine_with_weak_copyleft": True,
                "can_combine_with_strong_copyleft": False,
                "static_linking_restrictions": "none",
                "dynamic_linking_restrictions": "none"
            },
            "obligations": ["Include license text", "Include copyright notice"],
            "key_requirements": ["Attribution required"]
        }

        # Customize based on known patterns
        if "GPL" in license_id:
            analysis["category"] = "copyleft_strong"
            analysis["conditions"]["disclose_source"] = True
            analysis["conditions"]["same_license"] = True
            analysis["compatibility"]["can_combine_with_strong_copyleft"] = True
            analysis["compatibility"]["can_combine_with_permissive"] = False
            analysis["compatibility"]["static_linking_restrictions"] = "strong"
            analysis["obligations"] = [
                "Disclose source code",
                "Include license text",
                "State changes",
                "Use same license for derivatives"
            ]

        elif "LGPL" in license_id:
            analysis["category"] = "copyleft_weak"
            analysis["conditions"]["disclose_source"] = True
            analysis["compatibility"]["static_linking_restrictions"] = "weak"
            analysis["obligations"] = [
                "Disclose source of LGPL components",
                "Allow relinking",
                "Include license text"
            ]

        elif "AGPL" in license_id:
            analysis["category"] = "copyleft_strong"
            analysis["conditions"]["disclose_source"] = True
            analysis["conditions"]["same_license"] = True
            analysis["conditions"]["network_use_disclosure"] = True
            analysis["compatibility"]["static_linking_restrictions"] = "strong"

        elif "Apache" in license_id:
            analysis["category"] = "permissive"
            analysis["permissions"]["patent_grant"] = True
            analysis["conditions"]["include_notice"] = True
            analysis["conditions"]["state_changes"] = True
            analysis["conditions"]["disclose_source"] = False
            analysis["conditions"]["same_license"] = False

        elif "MIT" in license_id or "BSD" in license_id or "ISC" in license_id:
            analysis["category"] = "permissive"
            analysis["permissions"]["patent_grant"] = False

        elif "CC0" in license_id or "Unlicense" in license_id:
            analysis["category"] = "public_domain"
            analysis["conditions"]["include_license"] = False
            analysis["conditions"]["include_copyright"] = False
            analysis["obligations"] = []

        return analysis

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
            return self._get_default_compatibility_rules(license_id, analysis)

        return await self.llm_provider.extract_compatibility_rules(license_id, analysis)

    def _get_default_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Get default compatibility rules based on license category."""
        category = analysis.get("category", "permissive")

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
                    "special_requirements": []
                },
                "contamination_effect": "none",
                "notes": "Default compatibility rules"
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