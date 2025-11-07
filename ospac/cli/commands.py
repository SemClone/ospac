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
            click.secho("Using default enterprise policy. Create a custom policy with 'ospac init' to customize.", fg="yellow")

        license_list = [l.strip() for l in licenses.split(",")]

        eval_context = {
            "licenses_found": license_list,
            "licenses": license_list,  # Support both keys
            "context": context,
            "distribution": distribution,
            "distribution_type": distribution,  # Support both keys
            "linking_type": context if "linking" in context else None
        }

        result = runtime.evaluate(eval_context)

        # Add license obligations to requirements regardless of policy decision
        _enhance_result_with_obligations(result, license_list)

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
            click.secho("Using default enterprise policy. Create a custom policy with 'ospac init' to customize.", fg="yellow")

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
              default="data", help="Path to data directory containing license databases")
@click.option("--format", "-f", type=click.Choice(["json", "text", "checklist", "markdown"]),
              default="json", help="Output format (default: json)")
def obligations(licenses: str, policy_dir: str, data_dir: str, format: str):
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
            generator = PolicyDataGenerator(
                output_dir=Path(output_dir),
                llm_provider=llm_provider,
                llm_model=llm_model,
                llm_api_key=llm_api_key
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
        # Load from SPDX YAML file
        spdx_file = Path("data") / "licenses" / "spdx" / f"{license_id}.yaml"

        if not spdx_file.exists():
            click.secho(f"License {license_id} not found", fg="red")

            # Show available licenses
            spdx_dir = Path("data") / "licenses" / "spdx"
            if spdx_dir.exists():
                available = [f.stem for f in spdx_dir.glob("*.yaml")][:10]
                click.echo("\nAvailable licenses (first 10):")
                for lid in available:
                    click.echo(f"  - {lid}")
            sys.exit(1)

        with open(spdx_file) as f:
            data = yaml.safe_load(f)

        license_data = data.get("license", {})

        if format == "json":
            click.echo(json.dumps(license_data, indent=2))
        elif format == "yaml":
            click.echo(yaml.dump(license_data, default_flow_style=False))
        else:
            # Text format
            click.secho(f"License: {license_id}", fg="cyan", bold=True)
            click.echo(f"Category: {license_data.get('category')}")
            click.echo(f"Name: {license_data.get('name')}")

            click.echo("\nPermissions:")
            for perm, value in license_data.get("permissions", {}).items():
                symbol = "✓" if value else "✗"
                click.echo(f"  {symbol} {perm}")

            click.echo("\nConditions:")
            for cond, value in license_data.get("conditions", {}).items():
                if value:
                    click.echo(f"  • {cond}")

            click.echo("\nObligations:")
            for obligation in license_data.get("obligations", []):
                click.echo(f"  • {obligation}")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@data.command()
@click.option("--data-dir", "-d", type=click.Path(exists=True),
              default="data", help="Directory containing generated data")
def validate(data_dir: str):
    """Validate SPDX license data."""
    import yaml
    try:
        data_path = Path(data_dir)

        # Check SPDX directory exists
        spdx_dir = data_path / "licenses" / "spdx"
        if not spdx_dir.exists():
            click.secho(f"✗ SPDX directory not found: {spdx_dir}", fg="red")
            sys.exit(1)

        # Count and validate SPDX files
        yaml_files = list(spdx_dir.glob("*.yaml"))
        total = len(yaml_files)

        if total == 0:
            click.secho(f"✗ No SPDX YAML files found in {spdx_dir}", fg="red")
            sys.exit(1)

        click.echo(f"Validating {total} SPDX licenses...")

        issues = []
        required_fields = {"id", "name", "type", "properties", "requirements", "limitations", "obligations"}

        for yaml_file in yaml_files:
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                if "license" not in data:
                    issues.append(f"{yaml_file.name}: Missing 'license' section")
                    continue

                license_data = data["license"]
                missing_fields = required_fields - set(license_data.keys())
                if missing_fields:
                    issues.append(f"{yaml_file.name}: Missing fields: {missing_fields}")

            except Exception as e:
                issues.append(f"{yaml_file.name}: Parse error - {e}")

        if issues:
            click.secho(f"⚠ Found {len(issues)} validation issues:", fg="yellow")
            for issue in issues[:10]:  # Show first 10
                click.echo(f"  - {issue}")
        else:
            click.secho(f"✓ All {total} licenses validated successfully", fg="green")

        click.echo(f"\nData summary: {total} SPDX license files validated")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@policy.command()
@click.option("--template", "-t",
              type=click.Choice(["mobile", "desktop", "web", "server", "embedded", "library", "custom"]),
              default="web", help="Policy template for build target")
@click.option("--output", "-o", type=click.Path(),
              default="policy.yaml", help="Output file path")
def init(template: str, output: str):
    """Initialize a new policy from a build target template."""
    templates = {
        "mobile": {
            "version": "1.0",
            "name": "Mobile App Policy",
            "description": "Optimized for mobile app distribution (App Store/Play Store)",
            "rules": [
                {
                    "id": "no_copyleft",
                    "description": "Prevent copyleft in mobile apps",
                    "when": {"license_type": ["copyleft_strong", "copyleft_weak"]},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "Copyleft licenses may conflict with app store terms",
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
                    "id": "dynamic_linking_ok",
                    "description": "Allow LGPL with dynamic linking",
                    "when": {
                        "license_type": "copyleft_weak",
                        "context": "dynamic_linking"
                    },
                    "then": {"action": "approve"}
                },
                {
                    "id": "strong_copyleft_review",
                    "description": "Review GPL for desktop apps",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "review",
                        "message": "GPL requires source disclosure for distributed software"
                    }
                }
            ]
        },
        "web": {
            "version": "1.0",
            "name": "Web Application Policy",
            "description": "For web applications and services",
            "rules": [
                {
                    "id": "server_side_gpl_ok",
                    "description": "Allow GPL for server-side code",
                    "when": {
                        "license_type": "copyleft_strong",
                        "distribution": "saas"
                    },
                    "then": {"action": "approve"}
                },
                {
                    "id": "client_side_restrictions",
                    "description": "Restrict copyleft in client-side code",
                    "when": {
                        "license_type": "copyleft_strong",
                        "distribution": ["commercial", "embedded"]
                    },
                    "then": {
                        "action": "review",
                        "message": "Client-side GPL requires source disclosure"
                    }
                }
            ]
        },
        "server": {
            "version": "1.0",
            "name": "Server Application Policy",
            "description": "For backend services and server applications",
            "rules": [
                {
                    "id": "agpl_restrictions",
                    "description": "Careful with AGPL for networked services",
                    "when": {"spdx_id": ["AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later"]},
                    "then": {
                        "action": "review",
                        "message": "AGPL requires source disclosure for network use"
                    }
                },
                {
                    "id": "gpl_ok_internal",
                    "description": "Allow GPL for internal services",
                    "when": {
                        "license_type": "copyleft_strong",
                        "distribution": "internal"
                    },
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
                    "id": "no_copyleft_embedded",
                    "description": "Avoid copyleft in embedded devices",
                    "when": {"license_type": ["copyleft_strong", "copyleft_weak"]},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "Copyleft complicates embedded device compliance",
                        "remediation": "Use MIT or BSD-2-Clause for minimal embedded device restrictions"
                    }
                },
                {
                    "id": "prefer_bsd_mit",
                    "description": "Prefer BSD/MIT for embedded",
                    "when": {"spdx_id": ["MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0"]},
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
                    "id": "lgpl_dependencies_ok",
                    "description": "Allow LGPL dependencies in libraries",
                    "when": {
                        "license_type": "copyleft_weak",
                        "context": "dynamic_linking"
                    },
                    "then": {"action": "approve"}
                },
                {
                    "id": "viral_licenses_restricted",
                    "description": "Restrict viral licenses in libraries",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "Strong copyleft would contaminate library users",
                        "remediation": "Use Apache-2.0, MIT, or BSD for maximum library compatibility"
                    }
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

    with open(output, "w") as f:
        yaml.dump(policy, f, default_flow_style=False)

    click.secho(f"✓ Created policy file: {output}", fg="green")


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


def _get_license_data_directly(licenses: list, data_dir: str = "data") -> dict:
    """Load complete license data directly from SPDX JSON files."""
    import json
    from pathlib import Path

    license_data_result = {}

    # Try JSON files first (preferred format)
    json_dir = Path(data_dir) / "licenses" / "json"
    if json_dir.exists():
        for license_id in licenses:
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


def _enhance_result_with_obligations(result, license_list: list):
    """Add license obligations to policy result requirements."""
    import json
    from pathlib import Path

    # Get license obligations from JSON files (preferred) or YAML files
    all_obligations = []

    for license_id in license_list:
        # Try JSON first, then fallback to YAML
        json_file = Path("data") / "licenses" / "json" / f"{license_id}.json"
        yaml_file = Path("data") / "licenses" / "spdx" / f"{license_id}.yaml"

        spdx_data = None

        if json_file.exists():
            try:
                with open(json_file) as f:
                    spdx_data = json.load(f)
            except Exception:
                pass

        if spdx_data is None and yaml_file.exists():
            try:
                import yaml
                with open(yaml_file) as f:
                    spdx_data = yaml.safe_load(f)
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