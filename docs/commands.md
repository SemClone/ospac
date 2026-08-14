---
layout: default
title: Commands
nav_order: 2
description: The ospac command line interface, one section per command.
---

# Commands

ospac has three top-level commands and two command groups:

```
ospac evaluate      # is this set of licenses acceptable?
ospac check         # can these two licenses be combined?
ospac obligations   # what do I owe if I ship them?
ospac policy ...    # create and validate policy files
ospac data ...      # inspect and regenerate the license dataset
```

Every command that reads a policy accepts `-p/--policy-dir`. When you omit it, ospac
loads the bundled default enterprise policy and prints a notice to stderr. Because the
notice goes to stderr, `-o json` output stays valid when piped.

`evaluate`, `check` and `obligations` all default to JSON output, which is what makes them
usable from scripts without flags.

## evaluate

Evaluates a set of licenses against a policy for a given distribution type, and returns a
single decision.

```
ospac evaluate -l LICENSES [-d DIST] [-c CONTEXT] [-p DIR] [-o FORMAT]
```

| Option | Effect |
|:--|:--|
| `-l, --licenses` | Comma-separated licenses. Required. Whitespace after commas is fine. |
| `-d, --distribution` | How you ship: `internal`, `commercial`, `saas`, `embedded`, `mobile`, `desktop`, `web`, `open_source`. Default `commercial`. |
| `-c, --context` | Evaluation context, chiefly `static_linking` or `dynamic_linking`. Default `general`. |
| `-p, --policy-dir` | Policy file or directory. Defaults to the bundled enterprise policy. |
| `-o, --output` | `json` (default), `text`, or `markdown`. |

The distribution type is what makes the same input produce different answers:

```bash
ospac evaluate -l GPL-3.0 -d mobile       # deny, app store terms
ospac evaluate -l GPL-3.0 -d open_source  # policy-dependent
ospac evaluate -l MIT -d embedded         # approve
```

The `action` field is the answer; `remediation` tells you what to do about a denial.

```bash
$ ospac evaluate -l GPL-3.0 -d mobile
{
  "licenses": [
    "GPL-3.0"
  ],
  "context": "general",
  "distribution": "mobile",
  "result": {
    "rule_id": "aggregate",
    "action": "deny",
    "severity": "error",
    "message": "GPL licenses not allowed in commercial products due to viral copyleft requirements",
    "requirements": [
      "GPL-3.0: Retain copyright notices",
      "GPL-3.0: Include license text",
      "GPL-3.0: Provide or offer access to complete source code",
      "GPL-3.0: Distribute modifications under the same license"
    ],
    "remediation": "Replace with MIT, Apache-2.0, or BSD licensed alternative"
  },
  "per_license": {
    "GPL-3.0": {
      "action": "deny",
      "message": "GPL licenses not allowed in commercial products due to viral copyleft requirements"
    }
  },
  "using_default_policy": true
}
```

`action` is one of `approve`, `deny`, or `flag_for_review`. Each license is evaluated
independently and the verdicts aggregate with the most severe action winning, reported
under the synthetic `rule_id` of `aggregate`; `per_license` attributes the outcome, so in
a mixed set you can see which license drove a denial. A license that matches no rule
comes back `flag_for_review` on its own, so one permissive license cannot answer for the
others. `using_default_policy` tells you whether the decision came from
your policy or the bundled one, worth asserting on in CI.

Linking context matters for weak copyleft, where the same license is fine dynamically and
needs review statically:

```bash
ospac evaluate -l LGPL-2.1 -c static_linking -d commercial
```

## check

Checks whether two licenses can be combined. Narrower than `evaluate`: two licenses, and
the answer is a boolean plus the violations behind it.

```
ospac check LICENSE1 LICENSE2 [-c CONTEXT] [-p DIR] [-o FORMAT]
```

| Option | Effect |
|:--|:--|
| `-c, --context` | `static_linking`, `dynamic_linking`, or `general` (default). |
| `-p, --policy-dir` | Policy file or directory. |
| `-o, --output` | `json` (default) or `text`. No markdown for this command. |

```bash
$ ospac check GPL-2.0 Apache-2.0
{
  "license1": "GPL-2.0",
  "license2": "Apache-2.0",
  "context": "general",
  "compatible": false,
  "requires_review": false,
  "violations": [
    {
      "rule_id": "aggregate",
      "message": "GPL-2.0 and Apache-2.0 are incompatible due to patent clause conflicts",
      "severity": "error"
    }
  ],
  "warnings": [],
  "using_default_policy": true
}
```

`compatible: false` with `requires_review: true` means a human needs to look, not that a
conflict is known. When no conflict rule matches at all, the answer is "no known
conflicts", so a license is always compatible with itself, and a license id that does not
resolve in the dataset adds a warning rather than reading as a clean pass.

GPL-2.0 and Apache-2.0 are the canonical incompatible pair. Apache's patent termination
clause is an additional restriction GPL-2.0 does not permit. Text output is more readable
when a human is watching:

```bash
$ ospac check MIT GPL-3.0 -o text
✓ MIT and GPL-3.0 are compatible
```

Compatibility is directional in practice even though the flag is a boolean: combining MIT
code into a GPL-3.0 project is fine, while the reverse is not. Read the result as "can
these coexist in one distributed work under this policy", and use `evaluate` when what you
actually need is a decision about shipping.

## obligations

Lists what each license requires of you. This reads the dataset rather than making a
policy decision, so it works the same regardless of distribution type.

```
ospac obligations -l LICENSES [-f FORMAT] [-p DIR] [-d DATA_DIR]
```

| Option | Effect |
|:--|:--|
| `-l, --licenses` | Comma-separated licenses. Required. |
| `-f, --format` | `json` (default), `text`, `checklist`, or `markdown`. |
| `-p, --policy-dir` | Policy directory, if it contributes extra obligations. |
| `-d, --data-dir` | Read license data from elsewhere instead of the bundled dataset. |

`checklist` is the format for a human working through a release:

```bash
$ ospac obligations -l MIT -f checklist

MIT:
----------------------------------------
  ☐ Retain copyright notices
  ☐ Include license text
```

The `json` format returns the full license record under `license_data`, not just the
obligation strings, the same structure documented in
[The dataset]({{ site.baseurl }}/dataset/). That is the format to consume programmatically,
because it carries `requirements`, `properties` and `compatibility` alongside the
human-readable obligation list.

## policy

Creates and validates policy files. See [Policies]({{ site.baseurl }}/policies/) for what
goes in them.

### policy init

Writes a starter policy for a build target.

```
ospac policy init [-t TEMPLATE] [-o FILE] [-f FORMAT]
```

| Option | Effect |
|:--|:--|
| `-t, --template` | `mobile`, `desktop`, `web`, `server`, `embedded`, `library`, or `custom`. Default `web`. |
| `-o, --output` | Output path. Prints to stdout when omitted. |
| `-f, --format` | `yaml` (default) or `json`. |

```bash
$ ospac policy init --template mobile --output mobile_policy.yaml
✓ Created YAML policy file: mobile_policy.yaml
```

The templates differ in how they treat copyleft: `mobile` denies both strong and weak
copyleft outright, while `library` and `server` are more permissive. Start from the
nearest one and edit.

### policy validate

Checks a policy file for structural errors before you rely on it.

```bash
ospac policy validate ./my_policy.yaml
```

Run this in CI on any change to a policy file. A policy that fails to load falls back to
the default, which means a typo can silently replace your rules with someone else's.

## data

Inspects the bundled dataset and, for maintainers, regenerates it. Read
[The dataset]({{ site.baseurl }}/dataset/) before using the generation commands.

### data show

Prints one license record from the bundled dataset.

```
ospac data show LICENSE_ID [-f FORMAT]
```

`-f` accepts `yaml` (default), `json`, or `text`. Use `json` or `yaml`:

```bash
$ ospac data show MIT -f json
{
  "id": "MIT",
  "name": "MIT License",
  "type": "permissive",
  "spdx_id": "MIT",
  "properties": {
    "commercial_use": true,
    "distribution": true,
    "modification": true,
    "patent_grant": false,
    "private_use": true
  },
  ...
}
```

`-f text` prints a human-readable summary: type, permissions, conditions, limitations,
obligations and SPDX metadata, with false values shown explicitly (`✗`) rather than
omitted, and a marker when the identifier is deprecated.

License IDs are validated before use, so a path-traversal attempt in the ID is rejected
rather than resolved. An unknown ID exits non-zero and lists a sample of valid IDs.

### data generate

Regenerates the license dataset from upstream SPDX. This is a maintainer operation that
normally runs in CI once a month, you do not need it to use ospac.

```
ospac data generate [-o DIR] [--use-llm] [--llm-provider P] [--llm-model M]
                    [--llm-api-key K] [--force] [--force-reprocess] [--limit N]
```

| Option | Effect |
|:--|:--|
| `-o, --output-dir` | Where to write. Default `data`. CI passes `ospac/data` to regenerate in place. |
| `--use-llm` | Required. Without a provider every record would be a fail-closed placeholder, so the command refuses to run rather than fabricate a dataset. |
| `--llm-provider` | `openai`, `claude`, or `ollama`. |
| `--llm-model` | Model name, if you want something other than the provider default. |
| `--llm-api-key` | API key. Prefer the provider's environment variable. |
| `--force` | Overwrite existing output. |
| `--force-reprocess` | Reanalyze every license, not just new ones. Expensive. |
| `--limit N` | Process at most N new licenses. Useful for a cheap trial run. |

```bash
# Regenerate only what is new, no LLM
ospac data generate --output-dir ./data

# What CI runs
ospac data generate --output-dir ospac/data --use-llm --llm-provider openai --force
```

### data download-spdx

Fetches the raw upstream SPDX license list without processing it.

```
ospac data download-spdx [-o DIR] [--force]
```

### data validate

Validates every record in a dataset against the schema and its semantic invariants,
including the restriction rules: a NonCommercial identifier must not permit commercial
use, NoDerivatives must not permit modification, ShareAlike must carry the same-license
requirement, and a type must not contradict the record's own booleans.

```
ospac data validate [-d DIR] [--strict]
```

Defaults to the packaged data directory. Errors exit non-zero; `--strict` fails on
warnings too. The same rules back `scripts/validate_data.py`, the maintainer script CI
runs, so the two cannot disagree.

Per-record validation cannot notice that a whole dataset is templated, which is how
years of fabricated records once shipped with every record individually well formed.
`scripts/corpus_quality.py` covers that: it fails a dataset whose decision fields are
uniform across the corpus or whose records match a known fallback fingerprint, and runs
in CI on full regenerations.
