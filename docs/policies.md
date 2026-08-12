---
layout: default
title: Policies
nav_order: 3
description: The policy file format, how rules are matched, and which context fields actually work.
---

# Policies

A policy is a YAML or JSON file listing rules. Each rule says: when this situation holds,
take this action. Policies are the part of ospac you are expected to own, edit, and review
in pull requests.

## File shape

```yaml
version: "1.0"
name: "Mobile App Policy"
description: "Optimized for mobile app distribution"

rules:
  - id: deny_gpl_mobile
    description: "GPL conflicts with app store terms"
    priority: 10
    when:
      distribution_type: ["mobile", "commercial"]
      license: ["GPL-2.0", "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later"]
    then:
      action: deny
      severity: error
      message: "GPL licenses are not allowed in mobile apps"
      remediation: "Replace with an MIT, Apache-2.0, or BSD licensed alternative"
```

`-p/--policy-dir` accepts either a single file or a directory. Given a directory, every
policy in it is loaded and all rules are pooled together.

### `then`

| Key | Meaning |
|:--|:--|
| `action` | `approve`, `deny`, or `flag_for_review`. |
| `severity` | `error`, `warning`, or `info`. Drives how the result is reported. |
| `message` | Why the decision was made. Shown to whoever runs the command. |
| `remediation` | What to do about it. Surfaces in the `remediation` output field. |
| `requirements` | A list of obligations this rule adds. |
| `notify` | Addresses to notify. Recorded in the result; ospac does not send mail. |

## How rules are matched

Three things govern the outcome, and all three surprise people at least once.

**Every key in `when` must match.** Conditions are ANDed. A rule with both
`distribution_type` and `license` fires only when both hold. To express OR, use a list.
`distribution_type: ["mobile", "web"]` matches either, or write separate rules.

**A missing context field never matches.** If `when` names a field that is not in the
evaluation context, the rule is skipped. It does not match loosely and it does not error;
it is silently inert. This is the single biggest source of policies that appear to do
nothing.

**`license` is the one OR-ish key.** It matches if *any* license under evaluation appears
in the rule's list. Every other key compares a single context value.

When several rules match, results are aggregated and the most severe action wins, reported
under `rule_id: "aggregate"`. `priority` is a number you can set for ordering; higher
values are conventionally more important.

### Context fields you can match on

`ospac evaluate` builds exactly these fields:

| Field | Value | Notes |
|:--|:--|:--|
| `license` | The licenses from `-l` | Matches if any one is in your list. Also readable as `licenses` / `licenses_found`. |
| `distribution_type` | The `-d` value | `internal`, `commercial`, `saas`, `embedded`, `mobile`, `desktop`, `web`, `open_source`. Also readable as `distribution`. |
| `context` | The `-c` value | `general` by default. |
| `linking_type` | The `-c` value, but **only if it contains "linking"** | `null` otherwise, so a `linking_type` rule is inert unless you pass `-c static_linking` or `-c dynamic_linking`. |

{: .warning }
> **`license_type` does not work, and the built-in templates depend on it.**
>
> `ospac evaluate` never puts `license_type` into the context, so any rule matching on
> `license_type: copyleft_strong` is silently skipped. Every policy written by
> `ospac policy init` matches on `license_type`, which means the generated templates match
> nothing:
>
> ```bash
> $ ospac policy init --template mobile --output mobile_policy.yaml
> $ ospac evaluate -l GPL-3.0 -d mobile -p mobile_policy.yaml
> {
>   "result": {
>     "action": "allow",
>     "message": "No policies matched"
>   }
> }
> ```
>
> GPL-3.0 under a mobile policy that is written to deny it returns `allow`. This fails
> open, so it will not draw attention to itself in CI.
>
> Until this is fixed, match on `license` with explicit SPDX IDs instead of on
> `license_type`. That path works: it is what the bundled default enterprise policy uses,
> and why the default policy produces correct answers while the templates do not.

Rewriting the example above to match on `license` makes it fire:

```yaml
rules:
  - id: deny_gpl_mobile
    priority: 10
    when:
      distribution_type: ["mobile"]
      license: ["GPL-2.0", "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later"]
    then:
      action: deny
      severity: error
      message: "GPL conflicts with app store terms"
      remediation: "Use an MIT or Apache-2.0 alternative"
```

```bash
$ ospac evaluate -l GPL-3.0 -d mobile -p mobile_policy.yaml
    "action": "deny",
    "remediation": "Use an MIT or Apache-2.0 alternative"
```

The cost of this approach is that ID lists need maintaining, since a license family has many
spellings (`GPL-3.0`, `GPL-3.0-only`, `GPL-3.0-or-later`, `GPL-3.0+`), and a missing
variant is a rule that quietly does not cover it. Enumerate the variants you actually
encounter, and read `ospac/data/compatibility/categories.json` for the full membership of
each family.

## Nothing matching means review, not approval

When no rule matches, ospac returns `flag_for_review`:

```json
{
  "action": "flag_for_review",
  "severity": "warning",
  "message": "No policy rule matched, so this needs review",
  "remediation": "Add a rule covering this case, or approve it explicitly after review"
}
```

A policy that has no rule for a situation has not approved it, it simply has no answer, and
those are different things. ospac reports the absence of an answer rather than treating it
as permission.

{: .note }
> This changed in 1.4.0. Earlier versions returned `allow` here, which meant an unanswered
> question and an explicit approval were indistinguishable, so a policy whose rules had
> silently stopped matching read as a clean pass. If your CI treated `allow` as success,
> note that uncovered cases now surface as `flag_for_review` instead.

The practical consequence is that a policy needs to cover the licenses you actually use, or
you will get review requests. That is the intended pressure: the alternative is a policy
that quietly permits everything it forgot to mention.

Two habits still help. Assert that your policy is actually loaded, since a policy that fails
to parse falls back to the bundled default:

```bash
ospac evaluate -l MIT -p ./policy.yaml -o json \
  | jq -e '.using_default_policy == false' > /dev/null \
  || { echo "custom policy was not loaded"; exit 1; }
```

And keep a case in your test suite that must be denied. If your policy denies GPL for
mobile, test exactly that, so rules going inert fails a test rather than turning every
answer into a review request.

## The default policy

With no `-p`, ospac loads `ospac/defaults/enterprise_policy.yaml` and prints a notice on
stderr. It is a real, opinionated policy:

- GPL is denied for `commercial`, `embedded`, `saas`, `mobile`, `desktop` and `web`
- AGPL is denied for `saas`, `cloud` and `api`
- LGPL with `static_linking` is flagged for review, with requirements attached
- LGPL with dynamic linking is allowed

Those are defensible defaults for a commercial product and wrong for plenty of other
projects. Copy it as a starting point rather than inheriting it by accident:

```bash
cp "$(python -c 'import ospac,pathlib;print(pathlib.Path(ospac.__file__).parent)')/defaults/enterprise_policy.yaml" ./policy.yaml
```

Editing that file gives you a policy that already matches on `license`, which sidesteps the
`license_type` problem entirely.

## Templates

`ospac policy init -t NAME` writes one of `mobile`, `desktop`, `web`, `server`, `embedded`,
`library`, or `custom`. They differ mainly in copyleft treatment: `mobile` denies both
strong and weak copyleft, `library` and `server` are laxer.

Given the `license_type` issue above, treat these as a sketch of intent to be rewritten
against `license`, not as working policies.

## Validating

```bash
ospac policy validate ./policy.yaml
```

Run this in CI on every policy change. A policy that fails to load falls back to the
default, so a typo replaces your rules with the bundled ones, and because the fallback
still returns plausible answers, nothing looks broken. Pair validation with the
`using_default_policy` assertion above.
