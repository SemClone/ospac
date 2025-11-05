# Changelog

All notable changes to OSPAC (Open Source Policy as Code) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2025-11-05

### Added
- Package now includes all default data files in distribution
  - 700+ SPDX license files
  - Compatibility matrices and relationships
  - Pre-generated obligation database
- MANIFEST.in for proper source distribution packaging

### Changed
- Data directory moved to `ospac/data/` for wheel distribution compatibility
- Updated pyproject.toml with comprehensive package-data configuration

### Fixed
- Default data now ships with PyPI package installation
- Users can use the tool immediately without generating data first

## [0.1.0] - 2025-11-04

### Added
- Initial release of OSPAC - Open Source Policy as Code engine
- Core features:
  - Policy-as-code framework for OSS license compliance
  - SPDX license database integration (712 licenses)
  - License compatibility checking system
  - Obligation tracking and enforcement
  - CLI tool for policy evaluation

- Data generation pipeline:
  - SPDX license processor
  - LLM-enhanced analysis support (OpenAI, Ollama)
  - Compatibility matrix generation
  - Split matrix architecture for efficient storage

- Runtime engine:
  - YAML-based policy definitions
  - Rule evaluation system
  - Context-aware compliance checking
  - Decision tree support

- CLI commands:
  - `ospac evaluate` - Evaluate licenses against policies
  - `ospac check-compat` - Check compatibility between licenses
  - `ospac data generate` - Generate license database
  - `ospac data show` - Display license information
  - `ospac data download-spdx` - Download SPDX dataset

### Technical Details
- Python 3.9+ support
- Async/await architecture for LLM operations
- Efficient sparse matrix storage for compatibility data
- Comprehensive test suite (52 tests)
- GitHub Actions CI/CD pipeline

### Known Issues
- 13 SPDX licenses return 404 from API (fallback data provided)
- LLM analysis optional but recommended for enhanced accuracy

[1.0.1]: https://github.com/SemClone/ospac/releases/tag/v1.0.1
[0.1.0]: https://github.com/SemClone/ospac/releases/tag/v0.1.0