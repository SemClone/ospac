"""
Tests for the OSPAC CLI commands.

These tests exercise the full CLI path, including the evaluation context
construction in `evaluate`. This matters because policy templates generated
by `policy init` match on `license_type`, which must be resolved from the
license dataset at evaluation time - a hand-built context in unit tests
would never catch a CLI that forgets to populate it.
"""

import json

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
