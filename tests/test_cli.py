"""
Tests for the OSPAC CLI commands.

These tests exercise the full CLI path, including the evaluation context
construction in `evaluate`. This matters because policy templates generated
by `policy init` match on `license_type`, which must be resolved from the
license dataset at evaluation time - a hand-built context in unit tests
would never catch a CLI that forgets to populate it.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ospac.cli.commands import cli


# Templates whose rules deny strong copyleft licenses
DENY_COPYLEFT_TEMPLATES = ["mobile", "desktop", "web", "server", "embedded", "library"]


@pytest.fixture
def runner():
    """Provide a Click CLI test runner."""
    return CliRunner()


def _init_policy(runner, tmp_path, template):
    """Generate a policy file from a template and return its path."""
    policy_file = tmp_path / f"{template}_policy.yaml"
    result = runner.invoke(
        cli, ["policy", "init", "-t", template, "-o", str(policy_file)]
    )
    assert result.exit_code == 0, result.output
    assert policy_file.exists()
    return policy_file


def _evaluate(runner, licenses, distribution, policy_file=None):
    """Run `ospac evaluate` with JSON output and return the parsed result."""
    args = ["evaluate", "-l", licenses, "-d", distribution, "--output", "json"]
    if policy_file is not None:
        args.extend(["-p", str(policy_file)])
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


class TestPolicyInitTemplatesDenyCopyleft:
    """Generated templates must actually deny what they claim to deny."""

    @pytest.mark.parametrize("template", DENY_COPYLEFT_TEMPLATES)
    def test_strong_copyleft_is_denied(self, runner, tmp_path, template):
        policy_file = _init_policy(runner, tmp_path, template)
        output = _evaluate(runner, "GPL-3.0", template, policy_file)

        assert output["result"]["action"] == "deny", (
            f"{template} template must deny GPL-3.0, "
            f"got: {output['result']}"
        )

    @pytest.mark.parametrize("template", DENY_COPYLEFT_TEMPLATES)
    def test_permissive_is_not_denied(self, runner, tmp_path, template):
        policy_file = _init_policy(runner, tmp_path, template)
        output = _evaluate(runner, "MIT", template, policy_file)

        assert output["result"]["action"] != "deny", (
            f"{template} template must not deny MIT, "
            f"got: {output['result']}"
        )

    def test_permissive_is_approved_by_mobile_template(self, runner, tmp_path):
        policy_file = _init_policy(runner, tmp_path, "mobile")
        output = _evaluate(runner, "MIT", "mobile", policy_file)

        assert output["result"]["action"] == "approve"

    @pytest.mark.parametrize("template", ["mobile", "web", "embedded", "library"])
    def test_weak_copyleft_is_denied_where_template_says_so(
        self, runner, tmp_path, template
    ):
        policy_file = _init_policy(runner, tmp_path, template)
        output = _evaluate(runner, "LGPL-3.0-only", template, policy_file)

        assert output["result"]["action"] == "deny", (
            f"{template} template must deny weak copyleft, "
            f"got: {output['result']}"
        )

    @pytest.mark.parametrize("template", ["desktop", "server"])
    def test_weak_copyleft_is_flagged_for_review_where_template_says_so(
        self, runner, tmp_path, template
    ):
        policy_file = _init_policy(runner, tmp_path, template)
        output = _evaluate(runner, "LGPL-3.0-only", template, policy_file)

        assert output["result"]["action"] == "flag_for_review", (
            f"{template} template must flag weak copyleft for review, "
            f"got: {output['result']}"
        )


class TestEvaluateMultiLicense:
    """Any-match semantics: one bad license taints the whole evaluation."""

    def test_copyleft_mixed_with_permissive_still_denies(self, runner, tmp_path):
        policy_file = _init_policy(runner, tmp_path, "mobile")
        output = _evaluate(runner, "MIT,GPL-3.0", "mobile", policy_file)

        assert output["result"]["action"] == "deny", (
            "A copyleft license mixed with permissive ones must still deny, "
            f"got: {output['result']}"
        )

    def test_all_permissive_multi_license_is_not_denied(self, runner, tmp_path):
        policy_file = _init_policy(runner, tmp_path, "mobile")
        output = _evaluate(runner, "MIT,Apache-2.0", "mobile", policy_file)

        assert output["result"]["action"] != "deny"


class TestEvaluateContextConstruction:
    """Regression guards for the evaluation context built by the CLI."""

    def test_license_type_rules_are_matched(self, runner, tmp_path):
        # Regression guard: the CLI must populate license_type in the
        # evaluation context, otherwise every license_type rule silently
        # falls through to "No policies matched" and fails open.
        policy_file = _init_policy(runner, tmp_path, "mobile")
        output = _evaluate(runner, "GPL-3.0", "mobile", policy_file)

        assert output["result"]["message"] != "No policies matched", (
            "GPL-3.0 must match the mobile template's license_type rules; "
            "'No policies matched' means license_type was never resolved"
        )
        assert output["result"]["action"] == "deny"

    def test_unknown_license_does_not_crash(self, runner, tmp_path):
        policy_file = _init_policy(runner, tmp_path, "mobile")
        output = _evaluate(runner, "NotARealLicense-1.0", "mobile", policy_file)

        # A license absent from the dataset contributes no type, so no
        # license_type rule matches - but the command must still succeed.
        assert "result" in output


class TestEvaluateDefaultPolicy:
    """The built-in enterprise policy must keep working unchanged."""

    def test_gpl_denied_for_commercial(self, runner):
        output = _evaluate(runner, "GPL-3.0", "commercial")

        assert output["using_default_policy"] is True
        assert output["result"]["action"] == "deny"

    def test_mit_not_denied_for_commercial(self, runner):
        output = _evaluate(runner, "MIT", "commercial")

        assert output["using_default_policy"] is True
        assert output["result"]["action"] != "deny"

    def test_default_policy_hint_names_a_real_command(self, runner):
        result = runner.invoke(cli, ["evaluate", "-l", "MIT", "-o", "text"])

        assert result.exit_code == 0, result.output
        assert "ospac policy init" in result.output
        assert "'ospac init'" not in result.output, (
            "There is no 'ospac init' command; the hint must say "
            "'ospac policy init'"
        )


class TestDataShow:
    """`data show` must read the migrated JSON schema, not pre-v1.2.0 fields."""

    def test_text_output_uses_migrated_fields(self, runner):
        result = runner.invoke(cli, ["data", "show", "MIT", "-f", "text"])

        assert result.exit_code == 0, result.output
        assert "Type: permissive" in result.output
        assert "Category: None" not in result.output, (
            "'category' is a pre-migration field; the dataset uses 'type'"
        )
        # Permissions come from 'properties', conditions from 'requirements'
        assert "commercial_use" in result.output
        assert "include_license" in result.output
        # False values must be shown explicitly, not silently omitted
        assert "✗ disclose_source" in result.output
        assert "✗ warranty" in result.output
        assert "is_osi_approved" in result.output

    def test_json_output_shape_is_unchanged(self, runner):
        result = runner.invoke(cli, ["data", "show", "MIT", "-f", "json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["id"] == "MIT"
        assert data["type"] == "permissive"
        assert data["properties"]["commercial_use"] is True
        assert data["requirements"]["include_license"] is True
        assert data["spdx_metadata"]["is_osi_approved"] is True
        assert data["obligations"] == [
            "Retain copyright notices",
            "Include license text",
        ]


class TestDataValidate:
    """`data validate` must validate the JSON dataset that actually ships."""

    def test_shipped_dataset_validates(self, runner):
        result = runner.invoke(cli, ["data", "validate"])

        assert result.exit_code == 0, result.output
        assert "licenses/spdx" not in result.output, (
            "The pre-migration YAML layout no longer ships and must not "
            "be required for validation"
        )
        assert "Data summary" in result.output

    def test_shipped_dataset_validates_with_explicit_dir(self, runner):
        import ospac

        data_dir = Path(ospac.__file__).parent / "data"
        result = runner.invoke(cli, ["data", "validate", "-d", str(data_dir)])

        assert result.exit_code == 0, result.output

    def test_corrupt_dataset_fails(self, runner, tmp_path):
        json_dir = tmp_path / "licenses" / "json"
        json_dir.mkdir(parents=True)
        # id does not match the filename and every required field is missing
        (json_dir / "Broken-1.0.json").write_text('{"license": {"id": "Other"}}')

        result = runner.invoke(cli, ["data", "validate", "-d", str(tmp_path)])

        assert result.exit_code != 0, result.output
        assert "Broken-1.0" in result.output

    def test_unparseable_json_fails(self, runner, tmp_path):
        json_dir = tmp_path / "licenses" / "json"
        json_dir.mkdir(parents=True)
        (json_dir / "Mangled-1.0.json").write_text("{not json")

        result = runner.invoke(cli, ["data", "validate", "-d", str(tmp_path)])

        assert result.exit_code != 0, result.output


class TestObligationEnrichment:
    """Obligation enrichment must use packaged data, not the process cwd."""

    def test_evaluate_carries_obligations_without_local_data_dir(self, runner):
        # isolated_filesystem chdirs into an empty temp directory, so a
        # cwd-relative "data/" lookup would find nothing and enrichment
        # would silently become a no-op.
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["evaluate", "-l", "MIT", "--output", "json"]
            )

            assert result.exit_code == 0, result.output
            output = json.loads(result.output)
            requirements = output["result"]["requirements"]
            assert any(r.startswith("MIT: ") for r in requirements), (
                "evaluate must carry per-license obligations in its "
                f"requirements regardless of cwd, got: {requirements}"
            )
            assert "MIT: Retain copyright notices" in requirements
