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
    """OSPAC - Open Source Policy as Code compliance engine."""
    pass


@cli.command()
@click.option("--policy-dir", "-p", type=click.Path(exists=True),
              default="policies", help="Path to policy directory")
@click.option("--licenses", "-l", required=True,
              help="Comma-separated list of licenses to evaluate")
@click.option("--context", "-c", default="general",
              help="Evaluation context (e.g., static_linking, dynamic_linking)")
@click.option("--distribution", "-d", default="internal",
              help="Distribution type (internal, commercial, open_source)")
@click.option("--output", "-o", type=click.Choice(["json", "text", "markdown"]),
              default="text", help="Output format")
def evaluate(policy_dir: str, licenses: str, context: str,
            distribution: str, output: str):
    """Evaluate licenses against policies."""
    try:
        runtime = PolicyRuntime.from_path(policy_dir)

        license_list = [l.strip() for l in licenses.split(",")]

        eval_context = {
            "licenses_found": license_list,
            "context": context,
            "distribution": distribution,
        }

        result = runtime.evaluate(eval_context)

        if output == "json":
            click.echo(json.dumps(result.__dict__, indent=2))
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
              help="Compatibility context (e.g., static_linking)")
@click.option("--policy-dir", "-p", type=click.Path(exists=True),
              default="policies", help="Path to policy directory")
def check(license1: str, license2: str, context: str, policy_dir: str):
    """Check compatibility between two licenses."""
    try:
        runtime = PolicyRuntime.from_path(policy_dir)
        result = runtime.check_compatibility(license1, license2, context)

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
@click.option("--policy-dir", "-p", type=click.Path(exists=True),
              default="policies", help="Path to policy directory")
@click.option("--format", "-f", type=click.Choice(["text", "checklist", "markdown"]),
              default="text", help="Output format")
def obligations(licenses: str, policy_dir: str, format: str):
    """Get obligations for the specified licenses."""
    try:
        runtime = PolicyRuntime.from_path(policy_dir)
        license_list = [l.strip() for l in licenses.split(",")]

        obligations_dict = runtime.get_obligations(license_list)

        if format == "checklist":
            _output_checklist(obligations_dict)
        elif format == "markdown":
            _output_obligations_markdown(obligations_dict)
        else:
            _output_obligations_text(obligations_dict)

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
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


@cli.command()
@click.argument("license1")
@click.argument("license2")
@click.option("--data-dir", "-d", type=click.Path(exists=True),
              default="data/compatibility", help="Path to compatibility data")
def check_compat(license1: str, license2: str, data_dir: str):
    """Check compatibility between two licenses using split matrix format."""
    from ospac.core.compatibility_matrix import CompatibilityMatrix

    try:
        # Load the split matrix
        matrix = CompatibilityMatrix(data_dir)
        matrix.load()

        # Get compatibility status
        status = matrix.get_compatibility(license1, license2)

        # Display result
        if status == "compatible":
            click.secho(f"✓ {license1} and {license2} are compatible", fg="green")
        elif status == "incompatible":
            click.secho(f"✗ {license1} and {license2} are incompatible", fg="red")
        elif status == "review_needed":
            click.secho(f"⚠ {license1} and {license2} require review", fg="yellow")
        else:
            click.secho(f"? {license1} and {license2} have unknown compatibility", fg="white")

        # Show compatible licenses
        click.echo(f"\n{license1} is compatible with:")
        compatible = matrix.get_compatible_licenses(license1)[:10]  # Show first 10
        for lic in compatible:
            click.echo(f"  • {lic}")
        if len(compatible) > 10:
            click.echo(f"  ... and {len(compatible) - 10} more")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


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
    """Show details for a specific license from the database."""
    try:
        # Try to load from generated data
        data_file = Path("data") / "ospac_license_database.json"

        if not data_file.exists():
            click.secho("No generated data found. Run 'ospac data generate' first.", fg="red")
            sys.exit(1)

        with open(data_file) as f:
            database = json.load(f)

        if license_id not in database.get("licenses", {}):
            click.secho(f"License {license_id} not found in database", fg="red")
            click.echo("\nAvailable licenses (first 10):")
            for lid in list(database.get("licenses", {}).keys())[:10]:
                click.echo(f"  - {lid}")
            sys.exit(1)

        license_data = database["licenses"][license_id]

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
    """Validate generated policy data."""
    try:
        data_path = Path(data_dir)

        # Check required files
        required_files = [
            "ospac_license_database.json",
            "compatibility_matrix.json",
            "obligation_database.json",
            "generation_summary.json"
        ]

        missing = []
        for file_name in required_files:
            if not (data_path / file_name).exists():
                missing.append(file_name)

        if missing:
            click.secho(f"✗ Missing required files:", fg="red")
            for file_name in missing:
                click.echo(f"  - {file_name}")
            sys.exit(1)

        # Load and validate master database
        with open(data_path / "ospac_license_database.json") as f:
            database = json.load(f)

        total = len(database.get("licenses", {}))
        click.echo(f"Validating {total} licenses...")

        issues = []
        for license_id, data in database.get("licenses", {}).items():
            if not data.get("category"):
                issues.append(f"{license_id}: Missing category")
            if not data.get("permissions"):
                issues.append(f"{license_id}: Missing permissions")

        if issues:
            click.secho(f"⚠ Found {len(issues)} validation issues:", fg="yellow")
            for issue in issues[:10]:  # Show first 10
                click.echo(f"  - {issue}")
        else:
            click.secho(f"✓ All {total} licenses validated successfully", fg="green")

        # Show summary
        with open(data_path / "generation_summary.json") as f:
            summary = json.load(f)

        click.echo(f"\nGeneration summary:")
        click.echo(f"  Generated: {summary.get('generated_at')}")
        click.echo(f"  SPDX version: {summary.get('spdx_version')}")

        click.echo("\nCategories:")
        for cat, count in summary.get("categories", {}).items():
            click.echo(f"  {cat}: {count}")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.option("--template", "-t",
              type=click.Choice(["enterprise", "startup", "opensource", "permissive", "strict"]),
              default="enterprise", help="Policy template to use")
@click.option("--output", "-o", type=click.Path(),
              default="my_policy.yaml", help="Output file path")
def init(template: str, output: str):
    """Initialize a new policy from a template."""
    templates = {
        "enterprise": {
            "version": "1.0",
            "name": "Enterprise Policy",
            "rules": [
                {
                    "id": "no_copyleft",
                    "description": "Prevent copyleft in products",
                    "when": {"license_type": "copyleft_strong"},
                    "then": {
                        "action": "deny",
                        "severity": "error",
                        "message": "Strong copyleft licenses not allowed",
                    }
                }
            ]
        },
        "permissive": {
            "version": "1.0",
            "name": "Permissive Policy",
            "rules": [
                {
                    "id": "prefer_permissive",
                    "description": "Allow only permissive licenses",
                    "when": {"license_type": ["permissive", "public_domain"]},
                    "then": {"action": "allow"}
                }
            ]
        }
    }

    policy = templates.get(template, templates["enterprise"])

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


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()