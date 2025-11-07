# LLM Prompts for License Analysis

This document describes the AI prompts OSPAC uses to analyze software licenses and extract structured data.

## Overview

OSPAC uses LLMs (AI models) to analyze license texts and extract:
- License obligations and requirements
- Compatibility rules with other licenses
- Permissions, conditions, and limitations
- Usage restrictions and patent grants

The prompts are located in `ospac/pipeline/llm_providers.py` and are used by all supported LLM providers (OpenAI, Claude, and Ollama).

## System Prompt

**Location**: `ospac/pipeline/llm_providers.py:44-54` (`_get_system_prompt()`)

The system prompt establishes the AI's role and expertise:

```
You are an expert in software licensing and open source compliance.
Your task is to analyze software licenses and provide detailed, accurate information about:
- License obligations and requirements
- Compatibility with other licenses
- Usage restrictions and permissions
- Patent grants and trademark rules

Always provide information in structured JSON format.
Be precise and accurate - licensing compliance is critical.
```

**Purpose**: Sets the context for the AI to act as a licensing expert and ensures responses are in JSON format for structured data extraction.

## License Analysis Prompt

**Location**: `ospac/pipeline/llm_providers.py:56-102` (`_get_analysis_prompt()`)

This prompt analyzes a specific license and extracts comprehensive information.

### Input Parameters
- `license_id`: SPDX license identifier (e.g., "MIT", "GPL-3.0-only")
- `license_text`: Full license text (truncated to first 3000 characters)

### Output Structure

The prompt requests a JSON response with the following structure:

```json
{
    "license_id": "MIT",
    "category": "permissive|copyleft_weak|copyleft_strong|proprietary|public_domain",
    "permissions": {
        "commercial_use": true/false,
        "distribution": true/false,
        "modification": true/false,
        "patent_grant": true/false,
        "private_use": true/false
    },
    "conditions": {
        "disclose_source": true/false,
        "include_license": true/false,
        "include_copyright": true/false,
        "include_notice": true/false,
        "state_changes": true/false,
        "same_license": true/false,
        "network_use_disclosure": true/false
    },
    "limitations": {
        "liability": true/false,
        "warranty": true/false,
        "trademark_use": true/false
    },
    "compatibility": {
        "can_combine_with_permissive": true/false,
        "can_combine_with_weak_copyleft": true/false,
        "can_combine_with_strong_copyleft": true/false,
        "static_linking_restrictions": "none|weak|strong",
        "dynamic_linking_restrictions": "none|weak|strong"
    },
    "obligations": [
        "List of specific obligations when using this license"
    ],
    "key_requirements": [
        "List of key requirements for compliance"
    ]
}
```

### Field Descriptions

#### Category
- **permissive**: Minimal restrictions (e.g., MIT, Apache-2.0, BSD)
- **copyleft_weak**: Module-level copyleft (e.g., LGPL)
- **copyleft_strong**: Full copyleft/viral (e.g., GPL, AGPL)
- **proprietary**: Commercial/closed source
- **public_domain**: No restrictions (e.g., CC0, Unlicense)

#### Permissions
- **commercial_use**: Can be used for commercial purposes
- **distribution**: Can be distributed
- **modification**: Can be modified
- **patent_grant**: Grants patent rights
- **private_use**: Can be used privately

#### Conditions
- **disclose_source**: Must provide source code
- **include_license**: Must include license text
- **include_copyright**: Must include copyright notice
- **include_notice**: Must include NOTICE file
- **state_changes**: Must document changes
- **same_license**: Derivatives must use the same license
- **network_use_disclosure**: Network use triggers disclosure (AGPL)

#### Limitations
- **liability**: License disclaims liability (typically false)
- **warranty**: License disclaims warranty (typically false)
- **trademark_use**: License doesn't grant trademark rights (typically false)

## Compatibility Rules Prompt

**Location**: `ospac/pipeline/llm_providers.py:104-127` (`_get_compatibility_prompt()`)

This prompt extracts detailed compatibility rules based on the initial license analysis.

### Input Parameters
- `license_id`: SPDX license identifier
- `analysis`: The complete analysis result from the license analysis prompt

### Output Structure

```json
{
    "static_linking": {
        "compatible_with": ["list of compatible license IDs or categories"],
        "incompatible_with": ["list of incompatible license IDs or categories"],
        "requires_review": ["list of licenses requiring case-by-case review"]
    },
    "dynamic_linking": {
        "compatible_with": ["list"],
        "incompatible_with": ["list"],
        "requires_review": ["list"]
    },
    "distribution": {
        "can_distribute_with": ["list"],
        "cannot_distribute_with": ["list"],
        "special_requirements": ["list of special requirements"]
    },
    "contamination_effect": "none|module|derivative|full",
    "notes": "Additional compatibility notes"
}
```

### Field Descriptions

#### Linking Compatibility
- **static_linking**: Compatibility when statically linking libraries
- **dynamic_linking**: Compatibility when dynamically linking libraries
- Lists use format: `"MIT"` for specific licenses, `"category:permissive"` for categories

#### Contamination Effect
- **none**: No viral effect (permissive licenses)
- **module**: Affects only the specific module (weak copyleft)
- **derivative**: Affects derivative works
- **full**: Full viral effect (strong copyleft)

## Usage in Code

### OpenAI Provider
```python
# ospac/pipeline/llm_providers.py:227-235
response = await self.client.chat.completions.create(
    model=self.config.model,
    messages=[
        {"role": "system", "content": self._get_system_prompt()},
        {"role": "user", "content": self._get_analysis_prompt(license_id, license_text)}
    ],
    max_tokens=self.config.max_tokens,
    temperature=self.config.temperature
)
```

### Claude Provider
```python
# ospac/pipeline/llm_providers.py:340-348
message = await self.client.messages.create(
    model=self.config.model,
    max_tokens=self.config.max_tokens,
    temperature=self.config.temperature,
    system=self._get_system_prompt(),
    messages=[
        {"role": "user", "content": self._get_analysis_prompt(license_id, license_text)}
    ]
)
```

### Ollama Provider
```python
# ospac/pipeline/llm_providers.py:416-422
response = self.client.chat(
    model=self.config.model,
    messages=[
        {'role': 'system', 'content': self._get_system_prompt()},
        {'role': 'user', 'content': self._get_analysis_prompt(license_id, license_text)}
    ]
)
```

## Configuration

### Temperature Setting
Default: `0.1` (low temperature for more deterministic/accurate results)

The low temperature ensures consistent and factual analysis of licenses, which is critical for compliance.

### Max Tokens
Default: `4000` tokens

Sufficient for detailed license analysis responses with complete JSON structures.

## Fallback Mechanism

If the LLM fails or returns invalid JSON, OSPAC uses pattern-based fallback analysis:

**Location**: `ospac/pipeline/llm_providers.py:146-201` (`_get_fallback_analysis()`)

The fallback uses license ID patterns to determine:
- GPL → `copyleft_strong` with source disclosure requirements
- LGPL → `copyleft_weak` with module-level restrictions
- AGPL → `copyleft_strong` with network use disclosure
- Apache → `permissive` with patent grant
- MIT/BSD/ISC → `permissive` with minimal restrictions
- CC0/Unlicense → `public_domain` with no restrictions

## Best Practices

1. **Temperature**: Keep at 0.1 for consistency and accuracy
2. **Token Limit**: Ensure max_tokens is sufficient (4000+) for complete responses
3. **Error Handling**: Always implement fallback for when LLM fails
4. **JSON Parsing**: Extract JSON from response text robustly (handle markdown code blocks)
5. **Validation**: Validate extracted data against expected schema

## Example Analysis Flow

```python
from ospac.pipeline.llm_analyzer import LicenseAnalyzer

# Initialize analyzer
analyzer = LicenseAnalyzer(provider="openai", model="gpt-4o-mini")

# Analyze license
analysis = await analyzer.analyze_license("MIT", license_text)

# Extract compatibility rules
compatibility = await analyzer.extract_compatibility_rules("MIT", analysis)

# Result includes structured data about permissions, obligations, and compatibility
```

## Related Documentation

- [Integration Guide](INTEGRATION.md) - How to integrate OSPAC with LLM providers
- [API Documentation](API.md) - Complete API reference
- [Datasets](DATASETS.md) - Information about license datasets

## Contributing

When modifying prompts:
1. Test with all supported providers (OpenAI, API providers, Ollama)
2. Validate JSON output structure
3. Update fallback logic if needed
4. Run integration tests: `pytest tests/test_pipeline.py::TestLicenseAnalyzer -v`
