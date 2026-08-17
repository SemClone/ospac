# OSPAC - Open Source Policy as Code

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/pypi/v/ospac.svg)](https://pypi.org/project/ospac/)

OSPAC answers a narrow question: given a set of licenses and something you intend to do with them, is that allowed? It reads the licenses, applies a policy you keep in Git, and returns an action (approve, deny, or flag for review) along with the obligations you take on if you proceed.

The answer lives in a policy file, not in OSPAC's code. Compliance rules differ between a mobile app and an internal service, and they change as legal guidance changes, so OSPAC treats those rules as data: versioned, reviewable in a pull request, and testable.

It ships with the complete SPDX license list, so it works offline the moment it is installed. Nothing needs to be generated or downloaded first.

## Features

- **Policy as Code**: compliance rules in YAML or JSON, not hardcoded
- **Complete SPDX dataset**: every SPDX license bundled in the wheel, no setup step
- **Distribution-aware**: the same licenses can pass for `internal` and fail for `mobile`
- **Compatibility engine**: per-linking-context rules for static and dynamic linking
- **Obligation tracking**: derived deterministically from structured license fields
- **JSON-first output**: every command defaults to JSON for scripting and MCP
- **Offline**: evaluation makes no network calls and consults no model

## Installation

```bash
pip install ospac
```

Requires Python 3.10 or later. The license dataset is included.

```bash
pip install "ospac[semcl]"   # osslili + upmex, for scanning real projects
pip install "ospac[llm]"     # LLM providers, only needed to regenerate the dataset
pip install "ospac[all]"     # both
```

## Quick start

```bash
# Can these two licenses be combined?
ospac check GPL-2.0 Apache-2.0
# → incompatible

# Is this set acceptable for how we ship?
ospac evaluate -l "GPL-3.0,MIT" -d commercial -o text
# → deny

# What do we owe if we ship MIT code?
ospac obligations -l MIT -f checklist
# → ☐ Retain copyright notices
#   ☐ Include license text

# Start a policy of our own
ospac policy init --template mobile --output mobile_policy.yaml
```

The distribution type is what makes the same input produce different answers. `-d mobile` is stricter than `-d internal` because the policy says so, not because OSPAC hard-codes it.

## How it works

OSPAC has two halves that are worth keeping separate in your head.

**The tool you install** is offline and deterministic. It reads the bundled dataset and your policy files, and returns a decision. No network, no model.

**The dataset behind it** is regenerated from upstream SPDX by an automated pipeline that runs monthly, analyses new license texts with an LLM, validates the result, and opens a pull request for human review. Obligations are derived mechanically from structured boolean fields rather than written by the model, and a correction table pins fields that LLMs consistently got wrong. Dataset updates reach you as ordinary patch releases.

You never run the generation pipeline to use OSPAC. See [The dataset](https://semclone.github.io/ospac/dataset/) for how it works and how to run it yourself.

### Two things worth knowing early

**There is always a policy in play.** With no `--policy-dir`, OSPAC loads a bundled default enterprise policy and says so on stderr. That default is opinionated: it denies GPL for commercial distribution and flags LGPL static linking for review. Treat it as a starting point to copy, not as neutral ground.

**Exit codes do not reflect the decision.** `ospac evaluate` and `ospac check` exit 0 even when the answer is deny. Parse the JSON in CI:

```bash
ACTION=$(ospac evaluate -l "$LICENSES" -d mobile | jq -r '.result.action')
case "$ACTION" in deny|flag_for_review) exit 1 ;; esac
```

**An unanswered question is not an approval.** When no rule matches, OSPAC returns `flag_for_review`, not `allow`. A policy with no rule for a case has not permitted it, so the gap is reported rather than treated as a pass.

See [Integration](https://semclone.github.io/ospac/integration/) for a CI gate that cannot pass by accident.

## Python API

```python
from ospac import PolicyRuntime
from ospac.models.compliance import ActionType

runtime = PolicyRuntime("./compliance-policy.yaml")
assert not runtime._using_default, "policy failed to load"

licenses = ["MIT", "Apache-2.0", "GPL-3.0"]
result = runtime.evaluate({
    "licenses": licenses,
    "licenses_found": licenses,
    "distribution_type": "mobile",
    "distribution": "mobile",
    "context": "general",
    "linking_type": None,
})

if result.action == ActionType.DENY:
    raise SystemExit(result.to_dict()["remediation"])
```

Full reference at [Python API](https://semclone.github.io/ospac/api/).

## Documentation

Full documentation is at **[semclone.github.io/ospac](https://semclone.github.io/ospac/)**.

- [Overview](https://semclone.github.io/ospac/): what OSPAC does, installing, first run
- [Commands](https://semclone.github.io/ospac/commands/): every CLI command and flag, with real output
- [Policies](https://semclone.github.io/ospac/policies/): rule schema, how matching works, templates
- [The dataset](https://semclone.github.io/ospac/dataset/): how license data is shaped, shipped, and regenerated
- [Data contract](https://semclone.github.io/ospac/data-contract/): what a downstream consumer may rely on, what `version` means, how changes are announced
- [Python API](https://semclone.github.io/ospac/api/): using OSPAC as a library
- [Integration](https://semclone.github.io/ospac/integration/): CI, the SEMCL.ONE toolchain, MCP

## SEMCL.ONE toolchain

OSPAC evaluates licenses but does not discover them. Finding out what is in a project is the job of the neighbouring tools:

| Tool | Role |
|:--|:--|
| [osslili](https://github.com/SemClone/osslili) | Detects licenses and copyright in source trees |
| [upmex](https://github.com/SemClone/upmex) | Extracts declared metadata from package files |
| **ospac** | Decides whether the result is acceptable under policy |

They compose over JSON on the command line:

```bash
LICENSES=$(upmex extract gson-2.10.1.jar \
  | jq -r '[.licensing.declared_licenses[].spdx_id] | join(",")')

ospac evaluate -l "$LICENSES" -d mobile
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Documentation sources live in `docs/` and are published by GitHub Pages; every page has an "Edit this page on GitHub" link.

## Support

- [Documentation](https://semclone.github.io/ospac/)
- [GitHub issues](https://github.com/SemClone/ospac/issues)
- [SUPPORT.md](SUPPORT.md) for other options

## License

This project is dual-licensed, and the split matters.

**Software code**: Apache-2.0. All source in this repository (Python, scripts, configuration). Commercial use, modification, and distribution are permitted. See [LICENSE](LICENSE).

**License database**: CC BY-NC-SA 4.0. The dataset in `ospac/data/` is Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International: non-commercial use only, attribution required, derivatives shared alike. See [DATA_LICENSE](DATA_LICENSE).

Installing OSPAC and running it inside a commercial organization to check your own compliance is ordinary internal use. Redistributing the dataset, or building a commercial product on top of it, is what the NonCommercial term restricts. If you are unsure which side of that line you are on, that is a question for your counsel.

## Authors

See [AUTHORS.md](AUTHORS.md).

## Acknowledgments

- SPDX Project for license standardization
- SEMCL.ONE ecosystem for integration capabilities
- OpenChain Project for compliance best practices
