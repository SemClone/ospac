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

{: .note }
> **Before 1.3.0, `license_type` never reached the evaluation context**, so rules
> matching on it were silently skipped and the generated templates matched nothing. That
> is fixed: `evaluate` resolves each license's type from the dataset, and each license in
> a multi-license evaluation is judged independently, so one permissive license cannot
> answer for the others.

Matching on `license_type` is now the preferred way to write category rules, because it
covers licenses nobody remembered to enumerate:

```yaml
rules:
  - id: deny_strong_copyleft_mobile
    priority: 10
    when:
      distribution_type: ["mobile"]
      license_type: "copyleft_strong"
    then:
      action: deny
      severity: error
      message: "Strong copyleft conflicts with app store terms"
      remediation: "Use an MIT or Apache-2.0 alternative"
```

```bash
$ ospac evaluate -l GPL-3.0 -d mobile -p mobile_policy.yaml
    "action": "deny",
    "remediation": "Use an MIT or Apache-2.0 alternative"
```

The types the dataset uses are listed in
[The dataset]({{ site.baseurl }}/dataset/#what-a-license-record-contains). Two exist
precisely so category rules stay honest: `noncommercial` for licenses that forbid
commercial use, and `no_derivatives` for licenses that forbid distributing modified
versions. Neither may sit in `permissive`, so a rule approving permissive licenses cannot
bless them by accident.

Matching on `license` with explicit SPDX IDs still works and is right for rules about one
specific license. Its cost is that ID lists need maintaining, since a license family has
many spellings (`GPL-3.0`, `GPL-3.0-only`, `GPL-3.0-or-later`, `GPL-3.0+`), and a missing
variant is a rule that quietly does not cover it.

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

- strong copyleft is denied for `commercial`, `embedded`, `saas`, `mobile`, `desktop` and `web`, by category
- network copyleft is denied for `saas`, `cloud`, `api` and `web`
- NonCommercial licenses are denied for every commercial-adjacent distribution type
- weak copyleft is approved under `dynamic_linking`, reviewed under `static_linking`, and
  reviewed when the linking context is unknown
- permissive and public domain licenses are approved by category
- no-derivatives, source-available and unknown licenses are flagged for review
- known incompatible pairs, such as GPL-2.0 with Apache-2.0, are denied by `check`

Those are defensible defaults for a commercial product and wrong for plenty of other
projects. Copy it as a starting point rather than inheriting it by accident:

```bash
cp "$(python -c 'import ospac,pathlib;print(pathlib.Path(ospac.__file__).parent)')/defaults/enterprise_policy.yaml" ./policy.yaml
```

## Templates

`ospac policy init -t NAME` writes one of `mobile`, `desktop`, `web`, `server`, `embedded`,
`library`, or `custom`. They differ mainly in copyleft treatment: `mobile` denies both
strong and weak copyleft, `library` and `server` are laxer. All of them deny
`noncommercial` licenses and flag `no_derivatives`, `source_available`,
`network_copyleft` and `unknown` for review.

They are working starting points. Edit them rather than inheriting them unread: the
choices they make, such as denying weak copyleft outright on mobile, are defensible
defaults and not universal truths.

## Validating

```bash
ospac policy validate ./policy.yaml
```

Run this in CI on every policy change. A policy that fails to load falls back to the
default, so a typo replaces your rules with the bundled ones, and because the fallback
still returns plausible answers, nothing looks broken. Pair validation with the
`using_default_policy` assertion above.
