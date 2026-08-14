---
layout: default
title: Integration
nav_order: 6
description: Wiring ospac into CI, the SEMCL.ONE toolchain, and MCP.
---

# Integration

ospac is built to be called by other things: a CI job, a scanner further up the chain, an
agent. All three commands default to JSON output for that reason.

## Exit codes do not reflect the decision

Read this before writing a CI job.

`ospac evaluate` and `ospac check` **exit 0 even when the answer is deny or incompatible.**
The exit code reports whether ospac ran, not what it concluded.

```bash
$ ospac evaluate -l GPL-3.0 -d mobile > /dev/null; echo $?
0                      # ...and the decision was "deny"

$ ospac check GPL-2.0 Apache-2.0 > /dev/null; echo $?
0                      # ...and they are incompatible
```

A job written as `ospac evaluate -l "$LICENSES" -d mobile` and nothing more always passes.
Parse the JSON:

```bash
ACTION=$(ospac evaluate -l "$LICENSES" -d mobile | jq -r '.result.action')
[ "$ACTION" = "deny" ] && { echo "blocked"; exit 1; }
```

Non-zero exits are reserved for real failures: an unknown license ID, an unreadable
policy, a malformed dataset.

## A CI gate that cannot pass by accident

Two things can still make a compliance check pass without meaning much: the decision is
ignored (above), or the custom policy failed to load and the bundled default answered
instead. This job guards both, and also treats an unanswered case as a failure.

```yaml
name: License compliance

on: [pull_request]

jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install ospac

      - name: Validate the policy before trusting it
        run: ospac policy validate ./compliance-policy.yaml

      - name: Evaluate
        run: |
          set -euo pipefail
          RESULT=$(ospac evaluate \
            -l "MIT,Apache-2.0,GPL-3.0" \
            -d mobile \
            -p ./compliance-policy.yaml)
          echo "$RESULT" | jq .

          # Our policy must be the one that answered.
          if [ "$(echo "$RESULT" | jq -r '.using_default_policy')" != "false" ]; then
            echo "::error::custom policy was not loaded; the bundled default answered"
            exit 1
          fi

          ACTION=$(echo "$RESULT" | jq -r '.result.action')
          if [ "$ACTION" = "deny" ]; then
            echo "::error::$(echo "$RESULT" | jq -r '.result.message')"
            echo "remediation: $(echo "$RESULT" | jq -r '.result.remediation')"
            exit 1
          fi
          if [ "$ACTION" = "flag_for_review" ]; then
            echo "::warning::needs legal review"
          fi

      - name: Prove the policy still bites
        run: |
          # Rules going inert now surfaces as flag_for_review rather than a silent pass,
          # but asserting on a case that must be denied still catches it soonest.
          ACTION=$(ospac evaluate -l GPL-3.0 -d mobile -p ./compliance-policy.yaml \
            | jq -r '.result.action')
          if [ "$ACTION" != "deny" ]; then
            echo "::error::GPL-3.0 was not denied, policy rules are not matching"
            exit 1
          fi
```

That last step is worth keeping even though the fail-safe default now covers the same
ground. It fails on the specific rule you care about rather than on a generic review
request, which is a much faster diagnosis. See
[Policies]({{ site.baseurl }}/policies/) for why rules go inert. Most often a `when` clause
naming a context field that is not populated.

### Reporting into a pull request

`-o markdown` renders a result for a PR comment or job summary:

```bash
ospac evaluate -l "$LICENSES" -d commercial -o markdown >> "$GITHUB_STEP_SUMMARY"
ospac obligations -l "$LICENSES" -f markdown >> "$GITHUB_STEP_SUMMARY"
```

## The SEMCL.ONE toolchain

ospac evaluates licenses but does not discover them. Finding out what is in a project is
the job of the neighbouring tools:

| Tool | Role |
|:--|:--|
| [osslili](https://github.com/SemClone/osslili) | Detects licenses and copyright in source trees |
| [upmex](https://github.com/SemClone/upmex) | Extracts declared metadata from package files |
| **ospac** | Decides whether the result is acceptable under policy |

They compose over JSON on the command line, which is the integration path least likely to
break:

```bash
# What licence does this package declare, and may we ship it in a mobile app?
LICENSES=$(upmex extract gson-2.10.1.jar \
  | jq -r '[.licensing.declared_licenses[].spdx_id] | join(",")')

ospac evaluate -l "$LICENSES" -d mobile
```

```json
{
  "licenses": ["Apache-2.0"],
  "distribution": "mobile",
  "result": {
    "rule_id": "aggregate",
    "action": "approve",
    "severity": "info",
    "message": "Apache 2.0 license approved for all uses",
    "requirements": [
      "Preserve copyright and NOTICE file if present",
      "Include Apache 2.0 license text",
      "State changes made to the code"
    ],
    "remediation": null
  },
  "using_default_policy": true
}
```

Note that `approve` still carries `requirements`. Permission to ship is not the same as
having nothing to do. Feed those into your NOTICE file.

Install the neighbours with the extra:

```bash
pip install "ospac[semcl]"
```

Their Python APIs are `upmex.PackageExtractor` and `osslili.LicenseCopyrightDetector`.
Consult each project's own documentation for those; the CLI-and-JSON path above is the
stable contract between the tools.

## MCP

The SEMCL.ONE MCP server exposes this toolchain to agents, so a model can run a compliance
check rather than guess at licence rules. The ospac-backed tools include:

| Tool | Purpose |
|:--|:--|
| `run_compliance_check` | End-to-end check over a path |
| `check_license_compatibility` | Whether two licences can be combined |
| `validate_policy` | Whether a set of licences passes for a distribution type |
| `get_license_obligations` | Obligations for a licence |
| `get_license_details` | Full dataset record |
| `generate_legal_notices` | NOTICE file content |

JSON-first output is what makes this work: the same structures documented here are what
the agent receives.

## Docker

The dataset ships in the wheel, so an image needs no data step and no network at runtime:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir ospac
COPY compliance-policy.yaml /policy.yaml
ENTRYPOINT ["ospac"]
```

```bash
docker build -t ospac .
docker run --rm ospac evaluate -l "MIT,GPL-3.0" -d mobile -p /policy.yaml
```

Pin the version when the answer needs to be reproducible. Dataset changes ship in patch
releases (see [The dataset]({{ site.baseurl }}/dataset/#the-monthly-pipeline)), so
`ospac==1.3.0` fixes both the code and the licence data behind a decision, which matters if
you are keeping compliance evidence.

## Pre-commit

```yaml
repos:
  - repo: local
    hooks:
      - id: ospac-policy
        name: Validate compliance policy
        entry: ospac policy validate
        language: system
        files: ^compliance-policy\.ya?ml$
```

## Consuming the JSON

The fields worth building on, all present in `evaluate` output:

| Field | Use |
|:--|:--|
| `result.action` | The decision: `approve`, `deny`, or `flag_for_review`. Also `allow` when a matched rule states no action of its own |
| `result.severity` | `error`, `warning`, `info` |
| `result.message` | Why |
| `result.remediation` | What to do instead, on a denial |
| `result.requirements` | Obligations attached to the decision |
| `using_default_policy` | Whether your policy or the bundled default answered |

`evaluate` also returns a `per_license` map with each license's own action, so a review or
denial can be attributed to the license that caused it rather than to the set.

`check` returns `compatible` plus `requires_review`, `violations` and `warnings`.
`compatible: false` with `requires_review: true` means a human needs to look, not that a
conflict is known; a warning is added when a license id does not resolve in the dataset,
so a typo cannot read as clean compatibility. When no conflict rule matches, `check`
answers "no known conflicts" rather than review, so a license is always compatible with
itself. `obligations -f json` returns
the full licence records under `license_data`, whose schema is in
[The dataset]({{ site.baseurl }}/dataset/#what-a-license-record-contains).

An evaluation that matches no rule returns `flag_for_review`, not `allow`. A policy with no
rule for a case has not approved it, it has no answer, so ospac surfaces that rather than
permitting it. Handle all four values explicitly:

```bash
RESULT=$(ospac evaluate -l "$LICENSES" -d "$DIST" -p ./policy.yaml)
case "$(echo "$RESULT" | jq -r '.result.action')" in
  deny)            echo "blocked"; exit 1 ;;
  flag_for_review) echo "needs review"; exit 1 ;;
  approve)         echo "ok" ;;
  allow)           echo "permitted by a rule that states no action" ;;
esac
```

Whether `flag_for_review` should fail the build is yours to decide. Failing is the safer
default, since it covers both "legal must look at this" and "the policy does not mention
this case". If you let it pass, log it somewhere a human reads, otherwise a policy that has
drifted out of coverage becomes invisible again.

{: .note }
> Before 1.4.0 an unmatched evaluation returned `allow`, so a CI job checking only for `deny`
> would pass on a policy whose rules had stopped matching entirely. If you wrote such a job
> against an earlier version, uncovered cases now arrive as `flag_for_review`.
