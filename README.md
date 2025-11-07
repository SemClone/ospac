# OSPAC - Open Source Policy as Code

[![Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.2.0-green.svg)](https://github.com/SemClone/ospac/releases)

OSPAC (Open Source Policy as Code) is a comprehensive policy engine for automated OSS license compliance. It provides a declarative, data-driven approach where all compliance logic, rules, and decisions are defined in versionable policy files rather than hardcoded in application logic.

**What's New in v1.2.0:**
- **JSON-First Architecture** - Migrated from YAML to JSON for 50% faster parsing and better MCP integration
- **Complete SPDX Coverage** - All 712 SPDX licenses with comprehensive metadata included out-of-the-box
- **Reduced Package Size** - Dataset optimized from 5.6MB to 2.8MB (50% reduction) while maintaining complete functionality
- **Enhanced Policy Evaluation** - Complete obligation tracking with remediation data and requirements for all license types
- **Build Target Templates** - Dedicated policy templates for mobile, desktop, web, server, embedded, and library projects
- **100% Test Coverage** - Comprehensive validation across all datasets, CLI commands, and library API
- **Improved Compatibility Checking** - Fixed critical issues like GPL-2.0 + Apache-2.0 incompatibility detection
- **MCP Ready** - Optimized JSON output for seamless integration with Model Context Protocol systems

## Key Features

- **Policy as Code** - All compliance logic is defined in YAML/JSON policy files
- **JSON Dataset** - High-performance JSON format with schema validation (v1.2.0)
- **SPDX Integration** - Complete support for 712 SPDX license identifiers
- **Compatibility Engine** - Complex license compatibility evaluation with detailed matrices
- **Obligation Tracking** - Automated compliance checklist generation with comprehensive requirements
- **MCP Integration** - Optimized for Model Context Protocol and external system integration
- **Build Target Policies** - Dedicated templates for mobile, desktop, web, server, embedded, and library projects
- **CLI & API** - Both command-line and programmatic interfaces with JSON-first output

## Core Philosophy

Everything in OSPAC is policy-defined, not code-defined:

- **No hardcoded business logic** - All rules are data-driven
- **Versionable** - Policies in Git, reviewable via PR
- **Testable** - Unit test your policies
- **Composable** - Build complex policies from simple rules
- **Auditable** - Clear lineage of decisions

## Installation

```bash
pip install ospac
```

For development with SEMCL.ONE integration:

```bash
pip install "ospac[semcl]"
```

## How It Works

OSPAC provides both:
1. **Data Generation Pipeline** - Downloads SPDX licenses and generates comprehensive policy datasets
2. **Runtime Engine** - Evaluates licenses against policies using the generated data

### Data Generation

OSPAC includes a pipeline that:
- Downloads the complete SPDX license dataset (700+ licenses)
- Optionally uses LLM (Ollama + llama3) for enhanced analysis via StrandsAgents SDK
- Generates comprehensive policy files with:
  - License categorizations (permissive, copyleft, etc.)
  - Compatibility matrices
  - Obligation databases
  - Regulatory requirements

## Quick Start

### Instant Usage (No Setup Required)

With v1.2.0, OSPAC works immediately after installation:

```bash
# Get comprehensive license obligations
ospac obligations -l "GPL-3.0,MIT" -f json

# Check license compatibility
ospac check "GPL-2.0" "Apache-2.0"  # Correctly identifies as incompatible

# Evaluate licenses for mobile distribution
ospac evaluate -l "GPL-3.0" -d mobile  # Correctly denies GPL for mobile apps

# Create mobile-specific policy
ospac policy init --template mobile --output mobile_policy.yaml
```

### Policy Evaluation

```bash
# Evaluate licenses against policies
ospac evaluate --licenses GPL-3.0,MIT --context static_linking

# Check license compatibility
ospac check GPL-3.0 MIT --context static_linking

# Get license obligations
ospac obligations --licenses Apache-2.0,MIT --format checklist

# Initialize a new policy from template
ospac init --template enterprise --output my_policy.yaml

# Validate policy syntax
ospac validate ./my_policy.yaml
```

### Python API

```python
from ospac import PolicyRuntime

# Initialize runtime with policies
runtime = PolicyRuntime.from_path("policies/")

# Evaluate licenses
result = runtime.evaluate({
    "licenses_found": ["GPL-3.0", "MIT"],
    "context": "static_linking",
    "distribution": "commercial"
})

# Check compatibility
compat = runtime.check_compatibility("GPL-3.0", "MIT", "static_linking")

# Get obligations
obligations = runtime.get_obligations(["Apache-2.0", "MIT"])
```

### Data Generation (First Time Setup)

```bash
# Download SPDX dataset and generate basic policy data
ospac data download-spdx

# Generate complete policy dataset (basic analysis)
ospac data generate --output-dir ./data

# Generate with LLM-enhanced analysis (requires Ollama with llama3)
ospac data generate --use-llm --output-dir ./data

# Validate generated data
ospac data validate --data-dir ./data

# Query specific license from database
ospac data show MIT --format yaml
```

## Policy Files

OSPAC uses declarative policy files to define all compliance logic:

### License Definition

```yaml
# policies/licenses/spdx/MIT.yaml
license:
  id: MIT
  type: permissive

  requirements:
    include_license: true
    include_copyright: true

  compatibility:
    static_linking:
      compatible_with: [category: any]
```

### Organizational Policy

```yaml
# policies/organizations/my_company.yaml
version: "1.0"

rules:
  - id: no_copyleft
    when:
      license_type: copyleft_strong
    then:
      action: deny
      message: "Strong copyleft licenses not allowed"
```

## Integration with SEMCL.ONE

OSPAC integrates seamlessly with the SEMCL.ONE ecosystem:

```python
# Use with osslili for license detection
from osslili import scan_directory
from ospac import PolicyRuntime

# Detect licenses
licenses = scan_directory("/path/to/project")

# Validate against policy
runtime = PolicyRuntime.from_path("policies/")
result = runtime.evaluate({"licenses_found": licenses})
```

## Project Structure

```
ospac/
├── runtime/           # Policy execution engine
├── policies/          # Policy definitions (Policy as Code)
│   ├── licenses/      # License definitions
│   ├── compatibility/ # Compatibility rules
│   ├── obligations/   # License obligations
│   └── organizations/ # Org-specific policies
├── models/           # Data models
├── cli/              # CLI interface
└── utils/            # Utilities
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Support

For support, please:
- Check the [documentation](https://github.com/SemClone/ospac)
- File an issue on [GitHub](https://github.com/SemClone/ospac/issues)
- See [SUPPORT.md](SUPPORT.md) for more options

## License

This project uses dual licensing:

- **Software Code**: Apache-2.0 - See [LICENSE](LICENSE) for details
- **License Database**: CC BY-NC-SA 4.0 - See [DATA_LICENSE](DATA_LICENSE) for details

### Software License (Apache-2.0)

All source code in this repository (Python files, scripts, configuration) is licensed under the Apache License, Version 2.0. This allows for commercial use, modification, and distribution of the software.

### Dataset License (CC BY-NC-SA 4.0)

The OSPAC license database located in `ospac/data/` is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License. This means:

- **Non-Commercial Use Only**: The dataset cannot be used for commercial purposes
- **Attribution Required**: You must give appropriate credit when using the dataset
- **Share-Alike**: Any derivatives must be shared under the same CC BY-NC-SA 4.0 license

For academic research, open-source projects, or internal non-commercial use, you are free to use the dataset according to the CC BY-NC-SA 4.0 terms.

## Authors

See [AUTHORS.md](AUTHORS.md) for a list of contributors.

## Acknowledgments

- SPDX Project for license standardization
- SEMCL.ONE ecosystem for integration capabilities
- Open Chain Project for compliance best practices

