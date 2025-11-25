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
# Latest stable release (v1.2.0)
pip install ospac
```

## How It Works

OSPAC includes a pre-built JSON dataset with instant functionality:

1. **Ready-to-Use Dataset** - 712 SPDX licenses in optimized JSON format (included with installation)
2. **Runtime Engine** - Evaluates licenses against policies using comprehensive metadata
3. **Optional Data Pipeline** - Advanced users can regenerate data with custom analysis

### Pre-Built Dataset

**No setup required!** OSPAC ships with:
- 712 complete SPDX license definitions in JSON format
- Comprehensive compatibility matrices for static/dynamic linking
- Complete obligation tracking with license-specific requirements
- Structured contamination effects and compatibility notes
- Schema-validated data integrity

### Advanced Data Generation (Optional)

For custom analysis, OSPAC includes a pipeline that:
- Downloads the latest SPDX license dataset
- Optionally uses LLM (Ollama + llama3) for enhanced analysis via StrandsAgents SDK
- Generates comprehensive policy files with custom requirements

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

## Command Examples

### Policy Evaluation

```bash
# Evaluate licenses against policies (JSON output by default)
ospac evaluate -l "GPL-3.0,MIT" -d commercial

# Check license compatibility
ospac check GPL-3.0 MIT -c static_linking

# Get license obligations with complete metadata
ospac obligations -l "Apache-2.0,MIT" -f json

# Create policies for specific build targets
ospac policy init --template mobile --output mobile_policy.yaml
ospac policy init --template desktop --output desktop_policy.yaml

# Validate policy syntax
ospac policy validate ./my_policy.yaml

# Evaluate for specific distribution types
ospac evaluate -l "GPL-3.0" -d mobile    # Correctly denies GPL for mobile
ospac evaluate -l "MIT" -d embedded      # Allows permissive licenses
```


### Data Commands (Advanced Usage)

**Note:** v1.2.0 includes a complete pre-built dataset. Data generation is only needed for custom analysis.

```bash
# Show license information (works out of the box)
ospac data show MIT
ospac data show GPL-3.0

# Optional: Regenerate data with latest SPDX
ospac data download-spdx
ospac data generate --output-dir ./data

# Advanced: Generate with LLM analysis (requires Ollama with llama3)
ospac data generate --use-llm --output-dir ./data

# Validate data integrity
ospac data validate --data-dir ./data
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Support

For support, please:
- Check the [documentation](https://github.com/SemClone/ospac/tree/main/docs)
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

