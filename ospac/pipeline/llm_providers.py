"""
LLM provider implementations for OSPAC license analysis.
Supports OpenAI, Anthropic Claude, and local Ollama.
"""

import json
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""
    provider: str  # "openai", "claude", "ollama"
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4000
    temperature: float = 0.1


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def analyze_license(self, license_id: str, license_text: str) -> Dict[str, Any]:
        """Analyze a license using the LLM provider."""
        pass

    @abstractmethod
    async def extract_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Extract compatibility rules for a license."""
        pass

    def _get_system_prompt(self) -> str:
        """Get the system prompt for license analysis."""
        return """You are an expert in software licensing and open source compliance.
Your task is to analyze software licenses and provide detailed, accurate information about:
- License obligations and requirements
- Compatibility with other licenses
- Usage restrictions and permissions
- Patent grants and trademark rules

Always provide information in structured JSON format.
Be precise and accurate - licensing compliance is critical."""

    def _get_analysis_prompt(self, license_id: str, license_text: str) -> str:
        """Get the analysis prompt for a specific license."""
        return f"""Analyze the following license and provide detailed information in JSON format.

License ID: {license_id}
License Text (first 3000 chars):
{license_text[:3000]}

Provide a JSON response with the following structure:
{{
    "license_id": "{license_id}",
    "category": "permissive|copyleft_weak|copyleft_strong|proprietary|public_domain",
    "permissions": {{
        "commercial_use": true/false,
        "distribution": true/false,
        "modification": true/false,
        "patent_grant": true/false,
        "private_use": true/false
    }},
    "conditions": {{
        "disclose_source": true/false,
        "include_license": true/false,
        "include_copyright": true/false,
        "include_notice": true/false,
        "state_changes": true/false,
        "same_license": true/false,
        "network_use_disclosure": true/false
    }},
    "limitations": {{
        "liability": true/false,  // false = license disclaims liability (typical)
        "warranty": true/false,   // false = license disclaims warranty (typical)
        "trademark_use": true/false  // false = license doesn't grant trademark rights
    }},
    "compatibility": {{
        "can_combine_with_permissive": true/false,
        "can_combine_with_weak_copyleft": true/false,
        "can_combine_with_strong_copyleft": true/false,
        "static_linking_restrictions": "none|weak|strong",
        "dynamic_linking_restrictions": "none|weak|strong"
    }},
    "obligations": [
        "List of specific obligations when using this license"
    ],
    "key_requirements": [
        "List of key requirements for compliance"
    ]
}}"""

    def _get_compatibility_prompt(self, license_id: str, analysis: Dict[str, Any]) -> str:
        """Get the compatibility rules prompt."""
        return f"""Based on the {license_id} license with category {analysis.get('category', 'unknown')},
provide detailed compatibility rules in JSON format:

{{
    "static_linking": {{
        "compatible_with": ["list of compatible license IDs or categories"],
        "incompatible_with": ["list of incompatible license IDs or categories"],
        "requires_review": ["list of licenses requiring case-by-case review"]
    }},
    "dynamic_linking": {{
        "compatible_with": ["list"],
        "incompatible_with": ["list"],
        "requires_review": ["list"]
    }},
    "distribution": {{
        "can_distribute_with": ["list"],
        "cannot_distribute_with": ["list"],
        "special_requirements": ["list of special requirements"]
    }},
    "contamination_effect": "none|module|derivative|full",
    "notes": "Additional compatibility notes"
}}"""

    def _parse_json_response(self, response_text: str, license_id: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
        try:
            # Find JSON in response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                self.logger.warning(f"Could not extract JSON from LLM response for {license_id}")
                return self._get_fallback_analysis(license_id)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse LLM response for {license_id}: {e}")
            self.logger.debug(f"Response content: {response_text[:500]}")
            return self._get_fallback_analysis(license_id)

    def _get_fallback_analysis(self, license_id: str) -> Dict[str, Any]:
        """Get fallback analysis for when LLM fails."""
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
        elif "LGPL" in license_id:
            analysis["category"] = "copyleft_weak"
            analysis["conditions"]["disclose_source"] = True
        elif "AGPL" in license_id:
            analysis["category"] = "copyleft_strong"
            analysis["conditions"]["network_use_disclosure"] = True
        elif "Apache" in license_id:
            analysis["permissions"]["patent_grant"] = True
            analysis["conditions"]["disclose_source"] = False
            analysis["conditions"]["same_license"] = False
        elif "CC0" in license_id or "Unlicense" in license_id:
            analysis["category"] = "public_domain"

        return analysis


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider using OpenAI API."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import openai
            self.client = openai.AsyncOpenAI(api_key=config.api_key)
            self.available = True
        except ImportError:
            self.logger.error("OpenAI package not installed. Install with: pip install openai")
            self.available = False
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI client: {e}")
            self.available = False

    async def analyze_license(self, license_id: str, license_text: str) -> Dict[str, Any]:
        """Analyze license using OpenAI."""
        if not self.available:
            self.logger.warning(f"OpenAI not available, returning fallback for {license_id}")
            return self._get_fallback_analysis(license_id)

        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": self._get_analysis_prompt(license_id, license_text)}
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )

            response_text = response.choices[0].message.content
            return self._parse_json_response(response_text, license_id)

        except Exception as e:
            self.logger.error(f"OpenAI analysis failed for {license_id}: {e}")
            return self._get_fallback_analysis(license_id)

    async def extract_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Extract compatibility rules using OpenAI."""
        if not self.available:
            return self._get_default_compatibility_rules(license_id, analysis)

        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "user", "content": self._get_compatibility_prompt(license_id, analysis)}
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )

            response_text = response.choices[0].message.content
            return self._parse_json_response(response_text, license_id)

        except Exception as e:
            self.logger.error(f"OpenAI compatibility extraction failed for {license_id}: {e}")
            return self._get_default_compatibility_rules(license_id, analysis)

    def _get_default_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Get default compatibility rules."""
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
                "contamination_effect": "full",
                "notes": "Strong copyleft with viral effect"
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
                "contamination_effect": "none",
                "notes": "Default compatibility rules"
            }


class ClaudeProvider(LLMProvider):
    """Anthropic Claude LLM provider using Anthropic API."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import anthropic
            self.client = anthropic.AsyncAnthropic(api_key=config.api_key)
            self.available = True
        except ImportError:
            self.logger.error("Anthropic package not installed. Install with: pip install anthropic")
            self.available = False
        except Exception as e:
            self.logger.error(f"Failed to initialize Claude client: {e}")
            self.available = False

    async def analyze_license(self, license_id: str, license_text: str) -> Dict[str, Any]:
        """Analyze license using Claude."""
        if not self.available:
            self.logger.warning(f"Claude not available, returning fallback for {license_id}")
            return self._get_fallback_analysis(license_id)

        try:
            message = await self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=self._get_system_prompt(),
                messages=[
                    {"role": "user", "content": self._get_analysis_prompt(license_id, license_text)}
                ]
            )

            response_text = message.content[0].text
            return self._parse_json_response(response_text, license_id)

        except Exception as e:
            self.logger.error(f"Claude analysis failed for {license_id}: {e}")
            return self._get_fallback_analysis(license_id)

    async def extract_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Extract compatibility rules using Claude."""
        if not self.available:
            return self._get_default_compatibility_rules(license_id, analysis)

        try:
            message = await self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[
                    {"role": "user", "content": self._get_compatibility_prompt(license_id, analysis)}
                ]
            )

            response_text = message.content[0].text
            return self._parse_json_response(response_text, license_id)

        except Exception as e:
            self.logger.error(f"Claude compatibility extraction failed for {license_id}: {e}")
            return self._get_default_compatibility_rules(license_id, analysis)

    def _get_default_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Get default compatibility rules (same as OpenAI)."""
        return OpenAIProvider._get_default_compatibility_rules(self, license_id, analysis)


class OllamaProvider(LLMProvider):
    """Local Ollama LLM provider."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            import ollama
            # Test connection
            models = ollama.list()
            available_models = [model.model for model in models.models]

            if config.model not in available_models:
                self.logger.warning(f"Model {config.model} not found. Available: {available_models}")
                self.available = False
            else:
                self.client = ollama
                self.available = True

        except ImportError:
            self.logger.error("Ollama package not installed. Install with: pip install ollama")
            self.available = False
        except Exception as e:
            self.logger.error(f"Failed to initialize Ollama client: {e}")
            self.available = False

    async def analyze_license(self, license_id: str, license_text: str) -> Dict[str, Any]:
        """Analyze license using Ollama."""
        if not self.available:
            self.logger.warning(f"Ollama not available, returning fallback for {license_id}")
            return self._get_fallback_analysis(license_id)

        try:
            response = self.client.chat(
                model=self.config.model,
                messages=[
                    {'role': 'system', 'content': self._get_system_prompt()},
                    {'role': 'user', 'content': self._get_analysis_prompt(license_id, license_text)}
                ]
            )

            response_text = response['message']['content']
            return self._parse_json_response(response_text, license_id)

        except Exception as e:
            self.logger.error(f"Ollama analysis failed for {license_id}: {e}")
            return self._get_fallback_analysis(license_id)

    async def extract_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Extract compatibility rules using Ollama."""
        if not self.available:
            return self._get_default_compatibility_rules(license_id, analysis)

        try:
            response = self.client.chat(
                model=self.config.model,
                messages=[
                    {'role': 'user', 'content': self._get_compatibility_prompt(license_id, analysis)}
                ]
            )

            response_text = response['message']['content']
            return self._parse_json_response(response_text, license_id)

        except Exception as e:
            self.logger.error(f"Ollama compatibility extraction failed for {license_id}: {e}")
            return self._get_default_compatibility_rules(license_id, analysis)

    def _get_default_compatibility_rules(self, license_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Get default compatibility rules (same as OpenAI)."""
        return OpenAIProvider._get_default_compatibility_rules(self, license_id, analysis)


def create_llm_provider(config: LLMConfig) -> LLMProvider:
    """Factory function to create appropriate LLM provider."""
    if config.provider.lower() == "openai":
        return OpenAIProvider(config)
    elif config.provider.lower() == "claude":
        return ClaudeProvider(config)
    elif config.provider.lower() == "ollama":
        return OllamaProvider(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")