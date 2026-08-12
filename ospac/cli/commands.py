"""
OSPAC CLI commands.
"""

import json
import sys
from pathlib import Path
from typing import Optional, List

import click
import yaml
from colorama import Fore, Style, init

from ospac.runtime.engine import PolicyRuntime
from ospac.models.compliance import ComplianceStatus
from ospac.pipeline.spdx_processor import SPDXProcessor
from ospac.pipeline.data_generator import PolicyDataGenerator
from ospac.utils.validation import validate_license_id
from ospac.utils.data_validation import validate_license

# Initialize colorama
init(autoreset=True)


@click.group()
@click.version_option(prog_name="ospac")
def cli():
    """OSPAC - Open Source Policy as Code compliance engine.

    A tool for evaluating open source licenses against organizational policies.

    Common use cases:

    1. Evaluate a license for commercial use:
       ospac evaluate -l GPL-3.0 -d commercial

    2. Check compatibility between two licenses:
       ospac check MIT GPL-3.0

    3. Get license obligations:
       ospac obligations -l "MIT, Apache-2.0"

    4. Generate license data (requires initial setup):
       ospac data generate

    5. Initialize a policy for your build target:
       ospac policy init --template mobile

    Available templates: mobile, desktop, web, server, embedded, library, custom.
    Create targeted policies with 'ospac policy init' to match your development needs.
    """
    pass


@cli.command()
@click.option("--policy-dir", "-p", type=click.Path(exists=False),
              default=None, help="Path to policy directory (uses default enterprise policy if not provided)")
@click.option("--licenses", "-l", required=True,
              help="Comma-separated list of licenses to evaluate")
@click.option("--context", "-c", default="general",
              help="Evaluation context (e.g., static_linking, dynamic_linking)")
@click.option("--distribution", "-d", default="commercial",
              help="Distribution type (internal, commercial, saas, embedded, mobile, desktop, web, open_source)")
@click.option("--output", "-o", type=click.Choice(["json", "text", "markdown"]),
              default="json", help="Output format (default: json)")
def evaluate(policy_dir: str, licenses: str, context: str,
            distribution: str, output: str):
    """Evaluate licenses against policies.

    Examples:
        # Evaluate GPL-3.0 for commercial distribution
        ospac evaluate -l GPL-3.0 -d commercial

        # Evaluate multiple licenses
        ospac evaluate -l "MIT, Apache-2.0, GPL-3.0" -d saas

        # Use custom policy
        ospac evaluate -l MIT -p my_policy.yaml

        # Check for static linking context
        ospac evaluate -l LGPL-2.1 -c static_linking -d commercial
    """
    try:
        runtime = PolicyRuntime(policy_dir)

        if runtime._using_default and output == "text":
            click.secho("Using default enterprise policy. Create a custom policy with 'ospac policy init' to customize.", fg="yellow")

        license_list = [l.strip() for l in licenses.split(",")]

        # Resolve license types from the dataset so rules matching on
        # license_type (e.g. copyleft_strong) can fire. Licenses missing
        # from the dataset simply contribute no type.
        license_types = []
        for license_id in license_list:
            try:
                license_data = runtime.lookup_license_data(license_id)
            except ValueError:
                continue
            license_type = (license_data or {}).get("license", {}).get("type")
            if license_type and license_type not in license_types:
                license_types.append(license_type)

        eval_context = {
            "licenses_found": license_list,
            "licenses": license_list,  # Support both keys
            "license_type": license_types,
            "context": context,
            "distribution": distribution,
            "distribution_type": distribution,  # Support both keys
            "linking_type": context if "linking" in context else None
        }

        result = runtime.evaluate(eval_context)

        # Add license obligations to requirements regardless of policy decision
        _enhance_result_with_obligations(result, license_list, runtime)

        if output == "json":
            # Convert result to JSON-serializable format
            result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"result": str(result)}

            output_data = {
                "licenses": license_list,
                "context": context,
                "distribution": distribution,
                "result": result_dict,
                "using_default_policy": runtime._using_default
            }
            click.echo(json.dumps(output_data, indent=2))
        elif output == "markdown":
            _output_markdown(result, license_list)
        else:
            _output_text(result, license_list)

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.argument("license1")
@click.argument("license2")
@click.option("--context", "-c", default="general",
              help="Compatibility context (e.g., static_linking, dynamic_linking)")
@click.option("--policy-dir", "-p", type=click.Path(exists=False),
              default=None, help="Path to policy directory (uses default enterprise policy if not provided)")
@click.option("--output", "-o", type=click.Choice(["json", "text"]),
              default="json", help="Output format (default: json)")
def check(license1: str, license2: str, context: str, policy_dir: str, output: str):
    """Check compatibility between two licenses.

    Examples:
        # Check if MIT and GPL-3.0 are compatible
        ospac check MIT GPL-3.0

        # Check compatibility for static linking
        ospac check MIT LGPL-2.1 -c static_linking

        # Use text output
        ospac check Apache-2.0 BSD-3-Clause -o text
    """
    try:
        runtime = PolicyRuntime(policy_dir)

        if runtime._using_default and output == "text":
            click.secho("Using default enterprise policy. Create a custom policy with 'ospac policy init' to customize.", fg="yellow")

        result = runtime.check_compatibility(license1, license2, context)

        if output == "json":
            output_data = {
                "license1": license1,
                "license2": license2,
                "context": context,
                "compatible": result.is_compliant,
                "violations": result.violations if result.violations else [],
                "using_default_policy": runtime._using_default
            }
            click.echo(json.dumps(output_data, indent=2))
        else:
            # Text output
            if result.is_compliant:
                click.secho(f"✓ {license1} and {license2} are compatible", fg="green")
            else:
                click.secho(f"✗ {license1} and {license2} are incompatible", fg="red")

                if result.violations:
                    click.echo("\nViolations:")
                    for violation in result.violations:
                        click.echo(f"  - {violation['message']}")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.option("--licenses", "-l", required=True,
              help="Comma-separated list of licenses")
@click.option("--policy-dir", "-p", type=click.Path(exists=False),
              default=None, help="Path to policy directory (uses default enterprise policy if not provided)")
@click.option("--data-dir", "-d", type=click.Path(exists=False),
              default=None, help="Path to data directory containing license databases")
@click.option("--format", "-f", type=click.Choice(["json", "text", "checklist", "markdown"]),
              default="json", help="Output format (default: json)")
def obligations(licenses: str, policy_dir: str, data_dir: Optional[str], format: str):
    """Get obligations for the specified licenses.

    Examples:
        # Get obligations for MIT license
        ospac obligations -l MIT

        # Get obligations for multiple licenses
        ospac obligations -l "MIT, Apache-2.0, BSD-3-Clause"

        # Output as checklist
        ospac obligations -l "GPL-3.0, LGPL-2.1" -f checklist
    """
    try:
        license_list = [l.strip() for l in licenses.split(",")]

        # Use package data directory if not specified
        if data_dir is None:
            data_dir = str(Path(__file__).parent.parent / "data")

        # For basic license obligations, directly load from license data
        # Policy system is only needed for custom compliance rules
        if policy_dir:
            # Use policy system when custom policy is specified
            runtime = PolicyRuntime(policy_dir)
            obligations_dict = runtime.get_obligations(license_list, data_dir=data_dir)
        else:
            # Use direct license data loading for complete license information
            obligations_dict = _get_license_data_directly(license_list, data_dir)

        if format == "json":
            if policy_dir:
                # When using policies, return obligations format
                output_data = {
                    "licenses": license_list,
                    "obligations": obligations_dict,
                    "using_policy": True
                }
            else:
                # When using direct data, return raw license data for system consumption
                output_data = {
                    "licenses": license_list,
                    "license_data": obligations_dict,
                    "using_policy": False
                }
            click.echo(json.dumps(output_data, indent=2))
        elif format == "checklist":
            # For human-readable formats, extract obligations from license data
            obligations_only = _extract_obligations_for_display(obligations_dict, policy_dir)
            _output_checklist(obligations_only)
        elif format == "markdown":
            obligations_only = _extract_obligations_for_display(obligations_dict, policy_dir)
            _output_obligations_markdown(obligations_only)
        else:
            obligations_only = _extract_obligations_for_display(obligations_dict, policy_dir)
            _output_obligations_text(obligations_only)

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.group()
def policy():
    """Policy management commands."""
    pass


@policy.command()
@click.argument("policy_file", type=click.Path(exists=True))
def validate(policy_file: str):
    """Validate a policy file syntax."""
    try:
        path = Path(policy_file)

        with open(path, "r") as f:
            if path.suffix == ".json":
                data = json.load(f)
            else:
                data = yaml.safe_load(f)

        # Basic validation
        if "version" not in data:
            click.secho("⚠ Missing 'version' field", fg="yellow")

        if "rules" not in data and "license" not in data:
            click.secho("⚠ Missing 'rules' or 'license' field", fg="yellow")

        click.secho(f"✓ Policy file is valid", fg="green")

    except (json.JSONDecodeError, yaml.YAMLError) as e:
        click.secho(f"✗ Invalid syntax: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.group()
def data():
    """Manage OSPAC license data generation."""
    pass




@data.command()
@click.option("--output-dir", "-o", type=click.Path(), default="data",
              help="Output directory for generated data")
@click.option("--force", "-f", is_flag=True,
              help="Force re-download of SPDX data")
@click.option("--force-reprocess", is_flag=True,
              help="Force reprocessing of all licenses (ignore existing)")
@click.option("--limit", "-l", type=int,
              help="Limit number of licenses to process (for testing)")
@click.option("--use-llm", is_flag=True, default=False,
              help="Use LLM for enhanced analysis")
@click.option("--llm-provider", type=click.Choice(["openai", "claude", "ollama"]),
              default="ollama", help="LLM provider to use")
@click.option("--llm-model", type=str,
              help="LLM model name (auto-selected if not provided)")
@click.option("--llm-api-key", type=str,
              help="API key for cloud LLM providers (or set OPENAI_API_KEY/ANTHROPIC_API_KEY)")
def generate(output_dir: str, force: bool, force_reprocess: bool, limit: Optional[int],
             use_llm: bool, llm_provider: str, llm_model: Optional[str], llm_api_key: Optional[str]):
    """Generate policy data from SPDX licenses."""
    import asyncio

    async def run_generation():
        # Create generator with LLM configuration
        if use_llm:
            # require_provider=True makes provider initialization a preflight
            # check: a missing package or API key aborts here, before any
            # license is processed, instead of silently producing fallback data.
            generator = PolicyDataGenerator(
                output_dir=Path(output_dir),
                llm_provider=llm_provider,
                llm_model=llm_model,
                llm_api_key=llm_api_key,
                require_provider=True
            )
            click.echo(f"Using {llm_provider.upper()} LLM provider for enhanced analysis")
        else:
            generator = PolicyDataGenerator(Path(output_dir))
            click.secho("⚠ Running without LLM analysis. Data will be basic.", fg="yellow")
            click.echo("To enable LLM analysis, use --use-llm flag with --llm-provider")

        click.echo(f"Generating policy data in {output_dir}...")

        with click.progressbar(length=100, label="Generating data") as bar:
            # This is simplified - in reality would update progress
            summary = await generator.generate_all_data(
                force_download=force,
                limit=limit,
                force_reprocess=force_reprocess
            )
            bar.update(100)

        click.secho(f"✓ Generated data for {summary['total_licenses']} licenses", fg="green")
        click.echo(f"Output directory: {summary['output_directory']}")

        # Show category breakdown
        click.echo("\nLicense categories:")
        for category, count in summary.get("categories", {}).items():
            click.echo(f"  {category}: {count}")

        # Show validation results
        validation = summary.get("validation", {})
        if validation.get("is_valid"):
            click.secho("✓ All data validated successfully", fg="green")
        else:
            click.secho(f"⚠ Validation issues found: {len(validation.get('validation_errors', []))}", fg="yellow")

        # Fail closed if any record came from fallback instead of the LLM.
        # A partially fabricated compliance dataset must not be publishable.
        if use_llm:
            fallback_ids = sorted(getattr(generator.llm_analyzer, "fallback_licenses", set()))
            if fallback_ids:
                preview = ", ".join(fallback_ids[:10])
                if len(fallback_ids) > 10:
                    preview += f", and {len(fallback_ids) - 10} more"
                click.secho(
                    f"✗ {len(fallback_ids)} license record(s) were produced by fallback analysis "
                    f"instead of {llm_provider.upper()}: {preview}",
                    fg="red", err=True
                )
                click.secho(
                    "Fallback records deliberately under-permit and must not be published. "
                    "Fix the provider errors logged above and re-run.",
                    fg="red", err=True
                )
                sys.exit(1)
            click.secho("✓ No fallback records: all licenses analyzed by the LLM provider", fg="green")

    try:
        asyncio.run(run_generation())
    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@data.command()
@click.option("--output-dir", "-o", type=click.Path(), default="data",
              help="Output directory for SPDX data")
@click.option("--force", "-f", is_flag=True,
              help="Force re-download even if cached")
def download_spdx(output_dir: str, force: bool):
    """Download SPDX license dataset."""
    try:
        processor = SPDXProcessor(cache_dir=Path(output_dir) / ".cache")

        click.echo("Downloading SPDX license data...")
        data = processor.download_spdx_data(force=force)

        click.secho(f"✓ Downloaded {len(data['licenses'])} licenses", fg="green")
        click.echo(f"SPDX version: {data.get('version')}")
        click.echo(f"Release date: {data.get('release_date')}")

        # Process and save
        click.echo("\nProcessing licenses...")
        processed = processor.process_all_licenses()
        processor.save_processed_data(processed, Path(output_dir))

        click.secho(f"✓ Processed and saved {len(processed)} licenses", fg="green")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@data.command()
@click.argument("license_id")
@click.option("--format", "-f", type=click.Choice(["json", "yaml", "text"]),
              default="yaml", help="Output format")
def show(license_id: str, format: str):
    """Show details for a specific license from SPDX data."""
    import yaml
    try:
        # Validate license_id to prevent path traversal
        validate_license_id(license_id)

        # Use package data directory
        data_dir = Path(__file__).parent.parent / "data"

        # Load from JSON file (preferred format)
        json_file = data_dir / "licenses" / "json" / f"{license_id}.json"

        if not json_file.exists():
            click.secho(f"License {license_id} not found", fg="red")

            # Show available licenses
            json_dir = data_dir / "licenses" / "json"
            if json_dir.exists():
                available = [f.stem for f in json_dir.glob("*.json")][:10]
                click.echo("\nAvailable licenses (first 10):")
                for lid in available:
                    click.echo(f"  - {lid}")
            sys.exit(1)

        with open(json_file) as f:
            data = json.load(f)
        license_data = data.get("license", {})

        if format == "json":
            click.echo(json.dumps(license_data, indent=2))
        elif format == "yaml":
            click.echo(yaml.dump(license_data, default_flow_style=False))
        else:
            # Text format
            click.secho(f"License: {license_id}", fg="cyan", bold=True)
            click.echo(f"Name: {license_data.get('name')}")
            click.echo(f"Type: {license_data.get('type')}")

            spdx_metadata = license_data.get("spdx_metadata", {})
            if spdx_metadata.get("is_deprecated"):
                click.secho("⚠ This license identifier is DEPRECATED", fg="yellow")

            def bool_mark(value):
                return "✓" if value else "✗"

            permissions = license_data.get("properties", {})
            if permissions:
                click.echo("\nPermissions:")
                for perm, value in permissions.items():
                    click.echo(f"  {bool_mark(value)} {perm}")

            conditions = license_data.get("requirements", {})
            if conditions:
                click.echo("\nConditions:")
                for cond, value in conditions.items():
                    click.echo(f"  {bool_mark(value)} {cond}")

            limitations = license_data.get("limitations", {})
            if limitations:
                click.echo("\nLimitations:")
                for limitation, value in limitations.items():
                    click.echo(f"  {bool_mark(value)} {limitation}")

            obligations_list = license_data.get("obligations", [])
            if obligations_list:
                click.echo("\nObligations:")
                for obligation in obligations_list:
                    click.echo(f"  • {obligation}")

            key_requirements = license_data.get("key_requirements", [])
            if key_requirements:
                click.echo("\nKey requirements:")
                for req in key_requirements:
                    click.echo(f"  • {req}")

            if spdx_metadata:
                click.echo("\nSPDX metadata:")
                for key, value in spdx_metadata.items():
                    click.echo(f"  {bool_mark(value)} {key}")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@data.command()
@click.option("--data-dir", "-d", type=click.Path(exists=True),
              default=None, help="Directory containing generated data (defaults to packaged data)")
@click.option("--strict", is_flag=True,
              help="Treat warnings as errors")
def validate(data_dir: Optional[str], strict: bool):
    """Validate the license JSON dataset."""
    try:
        # Use package data directory if not specified
        if data_dir is None:
            data_dir = str(Path(__file__).parent.parent / "data")

        licenses_dir = Path(data_dir) / "licenses" / "json"
        if not licenses_dir.exists():
            click.secho(f"✗ License JSON directory not found: {licenses_dir}", fg="red")
            sys.exit(1)

        json_files = sorted(licenses_dir.glob("*.json"))
        total = len(json_files)

        if total == 0:
            click.secho(f"✗ No license JSON files found in {licenses_dir}", fg="red")
            sys.exit(1)

        click.echo(f"Validating {total} license JSON files...")

        all_errors = {}
        all_warnings = {}

        for json_file in json_files:
            license_id = json_file.stem
            try:
                with open(json_file) as f:
                    raw = json.load(f)
            except json.JSONDecodeError as e:
                all_errors[license_id] = [f"invalid JSON: {e}"]
                continue

            license_record = raw.get("license", {})
            if not license_record:
                all_errors[license_id] = ["top-level 'license' key missing or empty"]
                continue

            errors, warnings = validate_license(license_id, license_record)
            if errors:
                all_errors[license_id] = errors
            if warnings:
                all_warnings[license_id] = warnings

        clean = total - len(set(all_errors) | set(all_warnings))

        if all_errors:
            click.secho(f"\n✗ Errors in {len(all_errors)} files:", fg="red")
            for license_id, messages in sorted(all_errors.items())[:10]:
                for message in messages:
                    click.echo(f"  - {license_id}: {message}")
            if len(all_errors) > 10:
                click.echo(f"  ... and {len(all_errors) - 10} more files with errors")

        if all_warnings:
            click.secho(f"\n⚠ Warnings in {len(all_warnings)} files:", fg="yellow")
            for license_id, messages in sorted(all_warnings.items())[:10]:
                for message in messages:
                    click.echo(f"  - {license_id}: {message}")
            if len(all_warnings) > 10:
                click.echo(f"  ... and {len(all_warnings) - 10} more files with warnings")

        click.echo(f"\nData summary: {total} files, {clean} clean, "
                   f"{len(all_warnings)} with warnings, {len(all_errors)} with errors")

        if all_errors or (strict and all_warnings):
            click.secho("✗ Validation failed", fg="red")
            sys.exit(1)

        click.secho(f"✓ All {total} licenses validated successfully", fg="green")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@policy.command()
@click.option("--template", "-t",
              type=click.Choice(["mobile", "desktop", "web", "server", "embedded", "library", "custom"]),
              default="web", help="Policy template for build target")
@click.option("--output", "-o", type=click.Path(),
              default=None, help="Output file path")
@click.option("--format", "-f", type=click.Choice(["yaml", "json"]),
              default="yaml", help="Output format (default: yaml)")
def init(template: str, output: str, format: str):
    """Initialize a new policy from a build target template."""
    templates = {
        "mobile": {
            "version": "1.0",
            "name": "Mobile App Policy",
            "description": "Optimized for mobile app distribution (App Store/Play Store)",
            "rules": [
                {
                    "id": "deny_strong_copyleft",
                    "description": "Deny GPL and strong copyleft in mobile apps",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "GPL may conflict with app store terms and requires source disclosure",
                        "remediation": "Replace with MIT, Apache-2.0, or BSD licensed alternative for app store compatibility"
                    }
                },
                {
                    "id": "deny_weak_copyleft",
                    "description": "Deny LGPL and weak copyleft in mobile apps",
                    "when": {"license_type": "copyleft_weak"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "LGPL may conflict with app store terms and complicates mobile compliance",
                        "remediation": "Replace with MIT, Apache-2.0, or BSD licensed alternative for app store compatibility"
                    }
                },
                {
                    "id": "allow_permissive",
                    "description": "Allow permissive licenses",
                    "when": {"license_type": ["permissive", "public_domain"]},
                    "then": {"action": "approve"}
                }
            ]
        },
        "desktop": {
            "version": "1.0",
            "name": "Desktop Application Policy",
            "description": "For desktop applications with flexible distribution",
            "rules": [
                {
                    "id": "deny_strong_copyleft",
                    "description": "Deny GPL and strong copyleft for desktop apps",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "GPL requires source disclosure for distributed software",
                        "remediation": "Use permissive licenses like MIT, Apache-2.0, or BSD for desktop distribution"
                    }
                },
                {
                    "id": "review_weak_copyleft",
                    "description": "Review LGPL and weak copyleft licenses",
                    "when": {"license_type": "copyleft_weak"},
                    "then": {
                        "action": "review",
                        "message": "LGPL requires review - ensure dynamic linking compliance if approved"
                    }
                },
                {
                    "id": "allow_permissive",
                    "description": "Allow permissive licenses",
                    "when": {"license_type": ["permissive", "public_domain"]},
                    "then": {"action": "approve"}
                }
            ]
        },
        "web": {
            "version": "1.0",
            "name": "Web Application Policy",
            "description": "For web applications and services",
            "rules": [
                {
                    "id": "deny_strong_copyleft",
                    "description": "Deny GPL and strong copyleft licenses",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "GPL requires source disclosure which conflicts with commercial web applications",
                        "remediation": "Use permissive licenses like MIT, Apache-2.0, or BSD for web applications"
                    }
                },
                {
                    "id": "deny_weak_copyleft",
                    "description": "Deny LGPL and weak copyleft licenses",
                    "when": {"license_type": "copyleft_weak"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "LGPL complicates web application compliance and distribution",
                        "remediation": "Use permissive licenses like MIT, Apache-2.0, or BSD for web applications"
                    }
                },
                {
                    "id": "allow_permissive",
                    "description": "Allow permissive licenses",
                    "when": {"license_type": ["permissive", "public_domain"]},
                    "then": {"action": "approve"}
                }
            ]
        },
        "server": {
            "version": "1.0",
            "name": "Server Application Policy",
            "description": "For backend services and server applications",
            "rules": [
                {
                    "id": "deny_strong_copyleft",
                    "description": "Deny GPL, AGPL and strong copyleft licenses",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "GPL/AGPL requires source disclosure for networked services",
                        "remediation": "Use permissive licenses like MIT, Apache-2.0, or BSD for server applications"
                    }
                },
                {
                    "id": "review_weak_copyleft",
                    "description": "Review LGPL and weak copyleft licenses",
                    "when": {"license_type": "copyleft_weak"},
                    "then": {
                        "action": "review",
                        "message": "LGPL requires review - verify compliance requirements"
                    }
                },
                {
                    "id": "allow_permissive",
                    "description": "Allow permissive licenses",
                    "when": {"license_type": ["permissive", "public_domain"]},
                    "then": {"action": "approve"}
                }
            ]
        },
        "embedded": {
            "version": "1.0",
            "name": "Embedded Device Policy",
            "description": "For embedded devices and IoT applications",
            "rules": [
                {
                    "id": "deny_strong_copyleft",
                    "description": "Deny GPL and strong copyleft in embedded devices",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "GPL requires source disclosure which complicates embedded device distribution",
                        "remediation": "Use MIT or BSD-2-Clause for minimal embedded device restrictions"
                    }
                },
                {
                    "id": "deny_weak_copyleft",
                    "description": "Deny LGPL and weak copyleft in embedded devices",
                    "when": {"license_type": "copyleft_weak"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "LGPL complicates embedded device compliance due to dynamic linking requirements",
                        "remediation": "Use MIT or BSD-2-Clause for minimal embedded device restrictions"
                    }
                },
                {
                    "id": "allow_permissive",
                    "description": "Allow permissive licenses for embedded",
                    "when": {"license_type": ["permissive", "public_domain"]},
                    "then": {"action": "approve"}
                }
            ]
        },
        "library": {
            "version": "1.0",
            "name": "Library/SDK Policy",
            "description": "For libraries and SDKs distributed to third parties",
            "rules": [
                {
                    "id": "deny_strong_copyleft",
                    "description": "Deny GPL and strong copyleft in libraries",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "Strong copyleft would contaminate library users",
                        "remediation": "Use Apache-2.0, MIT, or BSD for maximum library compatibility"
                    }
                },
                {
                    "id": "deny_weak_copyleft",
                    "description": "Deny LGPL and weak copyleft licenses",
                    "when": {"license_type": "copyleft_weak"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "LGPL restricts library users and limits distribution flexibility",
                        "remediation": "Use Apache-2.0, MIT, or BSD for maximum library compatibility"
                    }
                },
                {
                    "id": "allow_permissive",
                    "description": "Allow permissive licenses",
                    "when": {"license_type": ["permissive", "public_domain"]},
                    "then": {"action": "approve"}
                }
            ]
        },
        "custom": {
            "version": "1.0",
            "name": "Custom Policy Template",
            "description": "Minimal template for custom policies",
            "rules": [
                {
                    "id": "default_allow",
                    "description": "Allow all licenses by default",
                    "when": {},
                    "then": {"action": "approve"}
                }
            ]
        }
    }

    policy = templates.get(template, templates["web"])  # Default to web template

    # Set default output filename based on format if not provided
    if output is None:
        output = f"policy.{format}"

    with open(output, "w") as f:
        if format == "json":
            json.dump(policy, f, indent=2)
        else:
            yaml.dump(policy, f, default_flow_style=False)

    click.secho(f"✓ Created {format.upper()} policy file: {output}", fg="green")


def _output_text(result, licenses):
    """Output result in text format."""
    click.echo(f"\nEvaluating licenses: {', '.join(licenses)}")
    click.echo("-" * 50)

    if hasattr(result, "action"):
        action_color = "green" if result.action.value == "allow" else "red"
        click.secho(f"Action: {result.action.value}", fg=action_color)

        if result.message:
            click.echo(f"Message: {result.message}")

        if result.requirements:
            click.echo("\nRequirements:")
            for req in result.requirements:
                click.echo(f"  • {req}")


def _output_markdown(result, licenses):
    """Output result in markdown format."""
    click.echo(f"# License Evaluation Report\n")
    click.echo(f"**Licenses evaluated:** {', '.join(licenses)}\n")

    if hasattr(result, "action"):
        status = "✅ Allowed" if result.action.value == "allow" else "❌ Denied"
        click.echo(f"## Status: {status}\n")

        if result.message:
            click.echo(f"**Message:** {result.message}\n")

        if result.requirements:
            click.echo("## Requirements\n")
            for req in result.requirements:
                click.echo(f"- {req}")


def _output_checklist(obligations_dict):
    """Output obligations as a checklist."""
    for license_id, oblig in obligations_dict.items():
        click.echo(f"\n{license_id}:")
        click.echo("-" * 40)

        if isinstance(oblig, dict):
            for key, value in oblig.items():
                if isinstance(value, bool):
                    checkbox = "☑" if value else "☐"
                    click.echo(f"  {checkbox} {key}")
                elif isinstance(value, list):
                    for item in value:
                        click.echo(f"  ☐ {item}")


def _output_obligations_text(obligations_dict):
    """Output obligations in text format."""
    for license_id, oblig in obligations_dict.items():
        click.secho(f"\n{license_id}:", fg="cyan", bold=True)

        if isinstance(oblig, dict):
            for key, value in oblig.items():
                if value:
                    click.echo(f"  • {key}: {value}")


def _output_obligations_markdown(obligations_dict):
    """Output obligations in markdown format."""
    click.echo("# License Obligations\n")

    for license_id, oblig in obligations_dict.items():
        click.echo(f"## {license_id}\n")

        if isinstance(oblig, dict):
            for key, value in oblig.items():
                if isinstance(value, bool) and value:
                    click.echo(f"- **{key}**")
                elif isinstance(value, str):
                    click.echo(f"- **{key}:** {value}")
                elif isinstance(value, list):
                    click.echo(f"- **{key}:**")
                    for item in value:
                        click.echo(f"  - {item}")


def _get_license_data_directly(licenses: list, data_dir: Optional[str] = None) -> dict:
    """Load complete license data directly from SPDX JSON files."""
    import json
    from pathlib import Path

    # Use package data directory if not specified
    if data_dir is None:
        data_dir = str(Path(__file__).parent.parent / "data")

    license_data_result = {}

    # Try JSON files first (preferred format)
    json_dir = Path(data_dir) / "licenses" / "json"
    if json_dir.exists():
        for license_id in licenses:
            try:
                # Validate license_id to prevent path traversal
                validate_license_id(license_id)
            except ValueError as e:
                click.echo(f"⚠️  Error: Invalid license ID '{license_id}': {e}", err=True)
                continue

            json_file = json_dir / f"{license_id}.json"
            if json_file.exists():
                try:
                    with open(json_file) as f:
                        spdx_data = json.load(f)

                    # Extract license data from SPDX format
                    if "license" in spdx_data:
                        license_data = spdx_data["license"]
                        license_data_result[license_id] = license_data
                    else:
                        click.echo(f"⚠️  Warning: {license_id} JSON file missing 'license' key", err=True)

                except Exception as e:
                    click.echo(f"⚠️  Warning: Failed to load {license_id}.json: {e}", err=True)
            else:
                click.echo(f"⚠️  Warning: {license_id}.json not found", err=True)

    # Fallback to YAML files if JSON not available
    else:
        import yaml
        spdx_dir = Path(data_dir) / "licenses" / "spdx"
        if spdx_dir.exists():
            for license_id in licenses:
                try:
                    # Validate license_id to prevent path traversal
                    validate_license_id(license_id)
                except ValueError:
                    # Skip invalid license IDs
                    continue

                spdx_file = spdx_dir / f"{license_id}.yaml"
                if spdx_file.exists():
                    try:
                        with open(spdx_file) as f:
                            spdx_data = yaml.safe_load(f)

                        # Extract license data from SPDX format
                        if "license" in spdx_data:
                            license_data = spdx_data["license"]
                            license_data_result[license_id] = license_data
                    except Exception:
                        # Continue with other licenses if this file fails
                        pass

    return license_data_result


def _enhance_result_with_obligations(result, license_list: list, runtime: PolicyRuntime,
                                     data_dir: Optional[str] = None):
    """Add license obligations to policy result requirements.

    Loads obligations from the packaged license JSON dataset (or an explicit
    data_dir override) so enrichment works regardless of the current working
    directory. The legacy YAML layout no longer ships, so there is no fallback.
    """
    json_dir = Path(runtime.resolve_data_dir(data_dir)) / "licenses" / "json"

    all_obligations = []

    for license_id in license_list:
        try:
            # Validate license_id to prevent path traversal
            validate_license_id(license_id)
        except ValueError:
            # Skip invalid license IDs
            continue

        json_file = json_dir / f"{license_id}.json"

        spdx_data = None

        if json_file.exists():
            try:
                with open(json_file) as f:
                    spdx_data = json.load(f)
            except Exception:
                pass

        if spdx_data:
            license_data = spdx_data.get("license", {})
            obligations = license_data.get("obligations", [])
            key_requirements = license_data.get("key_requirements", [])

            # Add license prefix to make it clear which license requires what
            prefixed_obligations = [f"{license_id}: {obligation}" for obligation in obligations]
            prefixed_requirements = [f"{license_id}: {req}" for req in key_requirements]

            all_obligations.extend(prefixed_obligations)
            all_obligations.extend(prefixed_requirements)

    # Add obligations to existing requirements
    if hasattr(result, 'requirements'):
        result.requirements.extend(all_obligations)


def _extract_obligations_for_display(license_data_dict: dict, using_policy: bool) -> dict:
    """Extract obligations from license data for human-readable display formats."""
    if using_policy:
        # Policy data is already in obligations format
        return license_data_dict

    # Extract obligations from raw license data
    obligations_dict = {}
    for license_id, license_data in license_data_dict.items():
        if isinstance(license_data, dict):
            obligations = license_data.get("obligations", [])
            if obligations:
                obligations_dict[license_id] = {"obligations": obligations}

    return obligations_dict


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()