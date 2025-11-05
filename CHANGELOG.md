# Changelog

All notable changes to OSPAC (Open Source Policy as Code) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.4] - 2025-11-04

### Fixed

**CLI Command Improvements**
- Fixed `ospac obligations` command returning no output
- Corrected policy loader integration for obligation data retrieval
- Updated get_obligations method to properly traverse nested policy structure
- Resolved obligation policy path resolution for CLI commands

**GitHub Actions Workflow**
- Removed duplicate release workflow causing PyPI publishing conflicts
- Consolidated to standard python-publish.yml workflow
- Fixed action errors during release process

### Changed

**Internal Architecture**
- Improved PolicyRuntime obligation handling for nested policy files
- Enhanced policy loader to correctly map obligation policies
- Standardized workflow configuration to prevent CI/CD conflicts

## [1.0.3] - 2025-11-04

### Fixed

**Critical Data Quality Corrections**
- Fixed systematic license limitation value errors across all 712 SPDX licenses
- Corrected liability and warranty limitation semantics (false = license disclaims, not provides)
- Fixed Apache-2.0 license classification as permissive (removed incorrect copyleft requirements)
- Corrected MIT license patent grant status (false, as MIT provides no explicit patent grant)
- Fixed Apache-2.0 patent grant status (true, as Apache-2.0 provides explicit patent grants)

**Data Generation Pipeline Improvements**
- Fixed fallback analysis methods in LLM analyzer and provider modules
- Improved LLM prompt clarity for limitation field semantics
- Enhanced license-specific handling for Apache, MIT, GPL, LGPL, and AGPL families
- Standardized copyleft vs permissive license requirement patterns

**AGPL License Data Corrections**
- Fixed inconsistent license compatibility data across all AGPL license variants
- Corrected AGPL-3.0.yaml incompatible licenses list (MIT-LICENSED → MIT)
- Fixed AGPL-3.0-or-later.yaml limitation values and same_license requirements
- Updated contamination_effect values for strong copyleft licenses (module → full)
- Standardized incompatible license naming (Proprietary → proprietary)

**Database Integrity**
- Regenerated complete license database with corrected pipeline logic
- Ensured consistent data structure and semantics across all license definitions
- Maintained compatibility with existing CLI functionality and policy evaluation
- Verified all 712 SPDX licenses have accurate legal metadata

### Technical Details
- Root cause identified in fallback analysis methods with incorrect default values
- Fixed semantic interpretation of limitation fields in license analysis
- Improved license categorization logic for permissive vs copyleft licenses
- Enhanced compatibility matrix generation with corrected license relationships

## [1.0.2] - 2025-11-04

### Added
- Complete SPDX license database coverage (712/712 licenses)
- All Apache family licenses now included (Apache-1.0, Apache-1.1, Apache-2.0)
- Enhanced data generation process for comprehensive license coverage

### Fixed
- Critical issue where Apache-2.0 and other licenses were missing from the main database
- Data generation process bug that excluded previously processed licenses from master database
- YAML format conversion issues between individual license files and database generation
- Database completeness ensuring all 712 SPDX licenses are accessible via CLI

### Changed
- Updated data generation flow to include all processed licenses instead of incremental updates only
- Improved license database structure to support complete SPDX license set
- Enhanced compatibility checking to work with full license catalog

### Technical Details
- Fixed `ospac/pipeline/data_generator.py` to use all analyzed licenses in master database generation
- Added `_convert_yaml_format()` function to transform YAML license data to expected database format
- Updated database from 638 to 712 licenses with complete metadata and compatibility rules

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

[1.0.3]: https://github.com/SemClone/ospac/releases/tag/v1.0.3
[1.0.2]: https://github.com/SemClone/ospac/releases/tag/v1.0.2
[1.0.1]: https://github.com/SemClone/ospac/releases/tag/v1.0.1
[0.1.0]: https://github.com/SemClone/ospac/releases/tag/v0.1.0