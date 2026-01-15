# Changelog

All notable changes to OSPAC (Open Source Policy as Code) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.5] - 2026-01-15

### Security

**Path Traversal Vulnerability Fix (CVE-TBD)**
- **Critical**: Fixed path traversal vulnerability in license ID input validation (CWE-22)
- Added comprehensive input validation to prevent arbitrary file reads via malicious license IDs
- Vulnerability allowed attackers to read arbitrary JSON files by exploiting unchecked `license_id` parameters
- Attack examples: `ospac obligations -l "../../../etc/passwd"`, `ospac data show "../../secrets/api_keys"`

**Affected Components (Fixed)**
- `PolicyRuntime.lookup_license_data()` - Core license data lookup function
- `ospac data show` CLI command - License information display
- `ospac obligations` CLI command - License obligation retrieval
- `ospac evaluate` CLI command - Policy evaluation with obligations
- All functions using `license_id` to construct file paths

**Security Measures Implemented**
- Created `ospac.utils.validation` module with security-focused input validation
- `validate_license_id()`: Validates SPDX license identifier format
  - Rejects path separators (`/`, `\`)
  - Blocks relative path components (`.`, `..`, `./`, `../`)
  - Enforces alphanumeric start character
  - Allows only: `A-Z`, `a-z`, `0-9`, `.`, `-`, `+`
- `validate_license_path()`: Defense-in-depth path verification to ensure resolved paths stay within base directory
- Applied validation to all 7 user-facing code paths accepting license ID input
- Added path resolution checks to prevent symlink-based directory escapes

**Test Coverage**
- Added 12 comprehensive security tests covering:
  - Path traversal attack prevention
  - Invalid character rejection
  - Relative path component blocking
  - Symlink escape protection
  - Integration tests for all vulnerable code paths
- All 59 existing tests continue passing (zero regressions)

**Impact**
- **Severity**: Medium (arbitrary file read limited to .json files)
- **CVSS v3.1 Estimate**: 5.3 (AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N)
- **Affected versions**: All versions prior to 1.2.5
- **Fixed in**: 1.2.5
- **Credit**: Internal security review

### Fixed

**Input Validation**
- License IDs now properly validated against SPDX identifier format across all CLI commands
- Invalid license IDs produce clear error messages instead of attempting file operations
- Enhanced error handling for malformed input

**Code Quality**
- Centralized input validation logic in dedicated utility module
- Improved code maintainability with reusable validation functions
- Added comprehensive docstrings with security considerations

## [1.2.3] - 2025-11-10

### Added

**Policy Format Support**
- Added `--format` option to `ospac policy init` command supporting both YAML and JSON output
- Default output filename now automatically uses selected format extension
- JSON policy format fully supported for all policy operations and evaluations

### Changed

**Policy Templates - Enhanced Copyleft Restrictions**
- Updated all policy templates with more consistent and strict copyleft handling
- Strong copyleft licenses (GPL, AGPL) now set to `deny` across all templates
- Weak copyleft licenses (LGPL) handling improved:
  - Mobile template: LGPL now `deny` (app store compliance)
  - Embedded template: LGPL now `deny` (device distribution complexity)
  - Web template: LGPL changed from `review` to `deny` (compliance simplification)
  - Library template: LGPL changed from `review` to `deny` (user restriction prevention)
  - Desktop template: LGPL remains `review` (dynamic linking flexibility)
  - Server template: LGPL remains `review` (backend service flexibility)
- Permissive licenses (MIT, Apache-2.0, BSD) remain `approve` in all templates
- Added comprehensive remediation messages for all denied licenses

**Policy Command Improvements**
- Policy init command now generates format-appropriate output files
- Enhanced validation to work seamlessly with both YAML and JSON formats
- Improved consistency across all policy template rules

## [1.2.2] - 2025-11-07

### Fixed

**Data Show Command**
- Fixed `ospac data show` command to use package data directory instead of relative path
- Command now works correctly regardless of current working directory
- Added JSON file support as primary data source with YAML fallback
- Improved error messages when license is not found

## [1.2.1] - 2025-11-07

### Fixed

**Package Data Distribution**
- Fixed data files not being included in installed package
- Moved data directory from `ospac/data/` to `ospac/ospac/data/` to ensure proper packaging
- Updated all code paths to use package-relative data directory paths instead of relative to current working directory
- CLI commands now work correctly regardless of which directory the tool is run from
- Updated MANIFEST.in to reflect new data location

**Code Improvements**
- Updated `ospac.cli.commands` to use `Path(__file__).parent.parent / "data"` for data resolution
- Updated `ospac.runtime.engine.PolicyRuntime.get_obligations()` to use package-relative paths
- Updated `ospac.core.compatibility_matrix.CompatibilityMatrix` to use package-relative paths
- Made data_dir parameter optional (defaults to None) across all affected functions

## [1.2.0] - 2024-11-06

### Added

**JSON Dataset Format**
- Migrated license dataset from YAML to JSON format for improved parsing reliability
- Added comprehensive JSON schema validation for license data structure
- Enhanced data loading performance and reduced parsing errors
- Support for 712 SPDX licenses in structured JSON format with complete metadata

**Enhanced Data Structure**
- Complete license information including properties, requirements, limitations, and obligations
- Detailed compatibility matrices for static and dynamic linking scenarios
- Comprehensive obligation tracking with license-specific requirements
- Structured contamination effect and compatibility notes

**Improved API Integration**
- JSON-first design optimized for MCP (Model Context Protocol) integration
- Clean, machine-readable output perfect for external system consumption
- Backward compatibility with YAML fallback for legacy support
- Enhanced library API for programmatic usage

### Changed

**Dataset Architecture**
- Primary license data format changed from YAML to JSON
- Reduced dataset size from 5.6MB to 2.8MB (50% reduction)
- Eliminated duplicate data structures and simplified maintenance
- Streamlined file structure for better package distribution

**Policy Evaluation Enhancement**
- Fixed policy aggregation to preserve remediation and requirements data
- Added comprehensive license obligations to policy evaluation results
- Improved compatibility checking with explicit incompatible license pairs
- Enhanced mobile/embedded distribution recognition in default policy

**Test Coverage**
- Achieved 100% test success rate with comprehensive validation suite
- Added dataset integrity validation for all 712 license files
- Enhanced CLI command testing across all options and scenarios
- Improved library API testing for external system integration

### Fixed
- Resolved GPL-2.0 + Apache-2.0 compatibility checking issue
- Fixed missing remediation data in policy aggregation results
- Corrected empty requirements field for denied licenses
- Enhanced mobile distribution type recognition in default policies
- Improved error handling for edge cases in license data loading

### Technical Improvements
- Added JSON schema for license data validation
- Implemented fallback mechanism from JSON to YAML for compatibility
- Enhanced data loading with proper error handling and validation
- Optimized file structure and removed redundant datasets
- Improved package size and distribution efficiency

## [1.1.5] - 2025-11-05

### Added

**Default Enterprise Policy**
- Embedded comprehensive default enterprise policy for immediate use without configuration
- Automatic policy loading when no custom policy is specified
- Default policy includes rules for GPL, AGPL, LGPL, permissive licenses, and public domain
- Support for different distribution types: commercial, SaaS, embedded, internal
- Context-aware evaluation for static vs dynamic linking

**CLI Enhancements**
- Added detailed examples to all CLI commands via help text
- New `-o/--output` option for `check` command supporting JSON and text formats
- Improved main help text with common use cases
- User notification when using default policy (in text output mode)

### Changed

**Output Format**
- JSON is now the default output format for all commands (previously text)
- Consistent JSON structure across all commands for better programmatic parsing
- Added `using_default_policy` field to JSON output for transparency
- Proper serialization of enums and complex types in JSON output

**Policy Loading**
- Modified PolicyRuntime to automatically load default policy when:
  - No policy directory is specified
  - Specified directory doesn't exist
  - Policy directory is empty
- Package now includes embedded default policy file in `ospac/defaults/`

### Fixed
- Improved rule matching logic for license evaluation
- Fixed JSON serialization errors with ActionType enums
- Enhanced context handling for linking types and distribution modes

## [1.1.0] - 2025-11-05

### Added

**Dual Licensing Implementation**
- Introduced dual licensing structure for the project
- Added CC BY-NC-SA 4.0 license for the OSPAC license database
- Created DATA_LICENSE file with full Creative Commons license text
- Added LICENSE file to ospac/data/ directory for clarity

### Changed

**License Structure**
- Software code remains under Apache-2.0 license
- License database now protected under CC BY-NC-SA 4.0 for non-commercial use only
- Updated README with comprehensive dual licensing explanation
- Clear separation between software and data licensing terms

### Documentation
- Enhanced README license section with detailed breakdown of dual licensing
- Added guidance for commercial vs non-commercial usage
- Clarified attribution and share-alike requirements for database usage

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

[1.2.5]: https://github.com/SemClone/ospac/releases/tag/v1.2.5
[1.2.3]: https://github.com/SemClone/ospac/releases/tag/v1.2.3
[1.2.2]: https://github.com/SemClone/ospac/releases/tag/v1.2.2
[1.2.1]: https://github.com/SemClone/ospac/releases/tag/v1.2.1
[1.2.0]: https://github.com/SemClone/ospac/releases/tag/v1.2.0
[1.1.5]: https://github.com/SemClone/ospac/releases/tag/v1.1.5
[1.1.0]: https://github.com/SemClone/ospac/releases/tag/v1.1.0
[1.0.4]: https://github.com/SemClone/ospac/releases/tag/v1.0.4
[1.0.3]: https://github.com/SemClone/ospac/releases/tag/v1.0.3
[1.0.2]: https://github.com/SemClone/ospac/releases/tag/v1.0.2
[1.0.1]: https://github.com/SemClone/ospac/releases/tag/v1.0.1
[0.1.0]: https://github.com/SemClone/ospac/releases/tag/v0.1.0