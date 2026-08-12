---
layout: default
title: Python API
nav_order: 5
description: Using ospac as a library, with the classes and methods it actually exposes.
---

# Python API

The entry point is `PolicyRuntime`. It loads policies, evaluates a context against them,
and looks up license data.

```python
from ospac import PolicyRuntime, License, Policy, ComplianceResult
```

Those four names are ospac's public surface. Anything under `ospac.pipeline` is
dataset-generation machinery, not an API to build on.

## PolicyRuntime

```python
from ospac import PolicyRuntime

runtime = PolicyRuntime()                       # bundled default enterprise policy
runtime = PolicyRuntime("./policy.yaml")        # your policy
runtime = PolicyRuntime(skip_default=True)      # no policy at all
```

`PolicyRuntime._using_default` tells you whether the default policy was loaded. It is
underscore-prefixed but it is what the CLI checks to emit its warning, and it is worth
asserting on in automation. See
[Policies]({{ site.baseurl }}/policies/#nothing-matching-means-review-not-approval).

```python
runtime = PolicyRuntime("./policy.yaml")
assert not runtime._using_default, "custom policy failed to load"
```

### evaluate

```python
result = runtime.evaluate(context)
```

`context` is a dict, and the keys must be the ones policy rules match on. The CLI builds
this shape, and replicating it exactly is the difference between rules firing and rules
being silently skipped:

```python
context = {
    "licenses": ["GPL-3.0"],
    "licenses_found": ["GPL-3.0"],   # both keys are read; set both
    "distribution_type": "mobile",
    "distribution": "mobile",
    "context": "general",
    "linking_type": None,            # or "static_linking" / "dynamic_linking"
}

result = runtime.evaluate(context)
print(result.action)     # ActionType.DENY
print(result.message)    # 'Evaluated 1 rules'
print(result.to_dict())
```

```python
{'rule_id': 'aggregate', 'action': 'deny', 'severity': 'error',
 'message': 'Evaluated 1 rules', 'requirements': [],
 'remediation': 'Replace with MIT, Apache-2.0, or BSD licensed alternative'}
```

Returns a `PolicyResult`. `action` is an `ActionType` enum, so compare against the enum or
call `to_dict()` for the plain string:

```python
from ospac.models.compliance import ActionType

if result.action == ActionType.DENY:
    raise SystemExit(result.to_dict()["remediation"])
```

A context missing a field that a rule matches on causes that rule to be skipped, not to
error. If evaluation returns `flag_for_review` with `"No policy rule matched"` when you
expected a denial, the rule was skipped: check the context keys first.

### evaluate_licenses

```python
result, per_license = runtime.evaluate_licenses(
    ["MIT", "MPL-2.0"],
    {"distribution_type": "commercial", "distribution": "commercial",
     "context": "general", "linking_type": None},
)
```

The per-license entry point, and the one the CLI uses. Each license is evaluated
independently, with its own `license_type` resolved from the dataset, and the verdicts
aggregate with most-restrictive-wins. `evaluate()` judges the context as a single unit, so
a rule matched by one license produces a result and the no-match fail-safe never runs for
the others: with `evaluate()`, one permissive license in the list can answer for a license
that matched nothing. Use `evaluate_licenses` whenever the input is a list of licenses.

`per_license` maps each license id to its own `PolicyResult`, so you can report which
license drove the aggregate verdict.

### check_compatibility

```python
result = runtime.check_compatibility("GPL-2.0", "Apache-2.0")
result = runtime.check_compatibility("MIT", "GPL-3.0", context="static_linking")
```

Returns a `ComplianceResult`:

```python
>>> r = runtime.check_compatibility("GPL-2.0", "Apache-2.0")
>>> r.is_compliant
False
>>> r.violations
[{'rule_id': 'aggregate', 'message': 'Evaluated 1 rules', 'severity': 'error'}]
>>> r.required_actions
['Use GPL-3.0 (compatible with Apache-2.0) or choose different licenses']
```

Note that `licenses_checked` comes back empty here even though two licenses were compared;
read the licenses from your own call arguments rather than from the result.

### lookup_license_data

```python
data = runtime.lookup_license_data("MIT")
```

Returns the raw record from the dataset, or `None` if the license is unknown. The record is
wrapped in a `license` key, matching the file on disk:

```python
>>> runtime.lookup_license_data("MIT").keys()
dict_keys(['license'])
>>> runtime.lookup_license_data("MIT")["license"]["type"]
'permissive'
```

Unwrap before use. Field meanings are in [The dataset]({{ site.baseurl }}/dataset/).

### resolve_data_dir

```python
>>> runtime.resolve_data_dir()
'/usr/lib/python3.12/site-packages/ospac/data'
```

Where ospac reads license data from. Pass a path to override.

### get_obligations

{: .warning }
> `PolicyRuntime.get_obligations(["MIT"])` returns `{}` for every license. It reads
> `lookup_license_data()["obligations"]`, but obligations live at
> `["license"]["obligations"]`, so the lookup always misses. The CLI's `ospac obligations`
> is unaffected: it uses a separate code path.
>
> Read obligations directly until this is fixed:
>
> ```python
> record = runtime.lookup_license_data("MIT")
> obligations = record["license"]["obligations"]
> # ['Retain copyright notices', 'Include license text']
> ```

## License

A dataclass over one license record.

```python
from ospac import License

record = runtime.lookup_license_data("MIT")
lic = License.from_dict(record["license"])

lic.id             # 'MIT'
lic.name           # 'MIT License'
lic.type           # 'permissive'
lic.properties     # {'commercial_use': True, ...}
lic.requirements   # {'include_license': True, ...}
lic.compatibility  # per-linking-context rules
```

`from_dict` expects the unwrapped record, so pass `record["license"]` rather than `record`.

```python
lic.is_compatible_with(other, context="static_linking")   # -> bool
lic.get_obligations()                                     # -> list[str]
```

`License.get_obligations()` recomputes obligation strings from the boolean fields rather
than returning the dataset's `obligations` list, so the wording differs slightly:

```python
>>> lic.get_obligations()
['Include license text', 'Include copyright notice']
>>> record["license"]["obligations"]
['Retain copyright notices', 'Include license text']
```

Both describe the same duties. Use the dataset's list when you want the same text the CLI
prints.

`is_compatible_with` is a model-level convenience that reads the license's own
`compatibility` block. It does not consult your policy. Use `runtime.check_compatibility()`
when the answer should respect policy.

## ComplianceResult and PolicyResult

`PolicyResult` is what `evaluate` returns; `ComplianceResult` is what
`check_compatibility` returns and the richer of the two.

```python
result.is_compliant     # property: no violations
result.needs_review     # property: flagged rather than denied
result.violations       # list of dicts
result.warnings
result.obligations
result.required_actions
result.metadata
result.to_dict()        # JSON-serializable
```

```python
from ospac import ComplianceResult
ComplianceResult.from_policy_result(policy_result)   # convert
```

`PolicyResult.aggregate([...])` merges several results, taking the most severe action.
This is what produces the `rule_id: "aggregate"` you see in CLI output.

## A CI gate

Putting the pieces together, including the two assertions that keep the check from failing
open:

```python
import sys
from ospac import PolicyRuntime
from ospac.models.compliance import ActionType

DISTRIBUTION = "mobile"
LICENSES = ["MIT", "Apache-2.0", "GPL-3.0"]

runtime = PolicyRuntime("./compliance-policy.yaml")
if runtime._using_default:
    sys.exit("policy did not load; refusing to pass on the default policy")

result = runtime.evaluate({
    "licenses": LICENSES,
    "licenses_found": LICENSES,
    "distribution_type": DISTRIBUTION,
    "distribution": DISTRIBUTION,
    "context": "general",
    "linking_type": None,
})

detail = result.to_dict()
if result.action == ActionType.DENY:
    sys.exit(f"denied: {detail['message']}\nremediation: {detail['remediation']}")

print(f"ok: {detail['action']}")
```

Pair it with a case that must be denied, so the gate is proven to still bite:

```python
gpl = runtime.evaluate({**base_context, "licenses": ["GPL-3.0"],
                        "licenses_found": ["GPL-3.0"]})
assert gpl.action == ActionType.DENY, "policy stopped denying GPL, rules are inert"
```
