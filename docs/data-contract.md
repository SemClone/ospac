---
layout: default
title: Data contract
nav_order: 5
description: What a downstream consumer of the ospac dataset may rely on, what the version field means, and how changes are announced.
---

# Data contract

[The dataset]({{ site.baseurl }}/dataset/) describes how the license data is shaped and
where it comes from. This page is narrower and more boring: it is the promise. If you are
reading `ospac/data/` from another tool, these are the files and fields you may build on,
and this is what happens when one of them changes.

The reason to write it down is that the alternative is inference. `index.json` has carried
a `version` field since the first release, with no stated meaning, so a consumer had to
guess whether it tracked the schema or the data. Three consumers guessing produce three
different answers, which is the same failure that moved the alias table into the dataset in
the first place. Guessing is cheap to prevent now and expensive to unwind later.

## The published surface

Four things are published. Everything else in the package is an implementation detail that
may move or vanish in any release.

| Path | What it is |
|:--|:--|
| `ospac/data/index.json` | Lookup index over every license: id, name, family, file path, deprecation flag, obligation count |
| `ospac/data/aliases.json` | Flattened alias map and the never-resolve list |
| `ospac/data/licenses/json/<id>.json` | One record per license, the full analysis |
| `ospac/data/compatibility/` | `metadata.json`, `categories.json`, and `relationships/*.json` |

### index.json

```json
{
  "version": "1.1.0",
  "generated": "2026-08-12T09:45:09.769222",
  "spdx_list_version": "e4c1f27",
  "total_licenses": 733,
  "licenses": {
    "MIT": {
      "name": "MIT License",
      "category": "permissive",
      "file": "licenses/json/MIT.json",
      "is_deprecated": false,
      "obligations_count": 2
    }
  }
}
```

Five top-level keys, five keys per record, and no others. `total_licenses` always equals
the size of `licenses`. Every `file` path is relative to `ospac/data/` and always resolves.

Worth knowing: ospac barely reads this file. Evaluation reads the per-license records,
`aliases.json`, and `compatibility/`. The only internal reader is `data_version()`, which
touches the four metadata keys and never opens the `licenses` map. So the whole per-record
half of the index exists purely for consumers, and breaking it would fail no code path of
ours. That is exactly why it is pinned by test rather than left to be noticed.

The record field is called `category` here and `type` in the license record. They hold the
same value from the same domain. The two names are historical, both are published, and
neither will be renamed inside a major version.

### aliases.json

```json
{
  "version": "1.1.0",
  "spdx_list_version": "e4c1f27",
  "aliases": { "expat": "MIT", "gpl-3.0+": "GPL-3.0-or-later" },
  "ambiguous": {
    "gnu general public license v2.0": ["GPL-2.0-only", "GPL-2.0-or-later"],
    "gplv3": ["GPL-3.0-only", "GPL-3.0-or-later"]
  },
  "never_resolve": ["agpl", "apache", "bsd", "gpl", "lgpl", "public domain"]
}
```

Keys in all three tables are lowercased, so lowercase your input before looking it up. The
three do not overlap: a string gets an id, a choice, or nothing, and never two of those.

Every value in `aliases` is an id present in `index.json`. An alias claimed by more than one
license is not resolved, because a confidently wrong answer is worse than none.

`ambiguous` maps text that identifies a license but not which id, to the ids it could mean.
Every value has at least two of them, each present in `index.json`. "GNU General Public
License v2.0" is the SPDX name of both `GPL-2.0-only` and `GPL-2.0-or-later`: only versus
or-later is the copyright holder's grant and the license's own name does not carry it, so a
document writing that name has not said which one it means. Report the choice rather than
making it. Which strings are ambiguous is license data that moves with SPDX, which is why it
is here rather than curated per consumer.

`never_resolve` is not a subset of `aliases`, it is the complement: text that must not
resolve to anything and offers no candidates either. `bsd` is 2-clause or 3-clause and the
choice changes obligations. Treat these as unresolved rather than inventing a guess. Read all
three through
[`license_aliases()`, `license_ambiguous()` and `license_never_resolve()`]({{ site.baseurl }}/api/#license_aliases-license_ambiguous-and-license_never_resolve)
rather than parsing the file, if you are in Python.

### licenses/json/&lt;id&gt;.json

The per-license record. Its shape is defined normatively by
[`schemas/license_schema.json`](https://github.com/SemClone/ospac/blob/main/schemas/license_schema.json),
and the field-by-field meanings are in
[The dataset]({{ site.baseurl }}/dataset/#what-a-license-record-contains).

Yes, normative. That schema used to be an unused internal artifact that had drifted so far
out of date it rejected all 733 records it claimed to describe: five of the ten license
families were absent from its `type` enum, three of the five real `contamination_effect`
values were absent while three values the generator never emits were listed, and it was
closed against five fields the records had carried for releases. It now matches the shipped
data, its value domains are pinned by test to the same constants the dataset validator uses,
and every shipped record is validated against it in CI. You can point a validator at it and
trust the result.

One deliberate looseness: the schema does not forbid unknown fields. The compatibility
promise below permits new fields in a minor release, so a schema that rejected them would
break every consumer on an additive change. Absence of a field is what the schema catches;
addition of one is caught by our own test, not by yours.

The schema lives in the repository and the source distribution, not in the wheel, because
validating records is a consumer's CI activity rather than something the installed tool
does. Vendor a copy at the major version you support rather than fetching it at runtime;
ospac makes no network calls and neither should a compliance check.

### compatibility/

`metadata.json` publishes `version`, `generated`, `total_licenses`, `format`, and
`default_status`. `categories.json` maps a family name to the license ids in it.
`relationships/<family>.json` holds the pair rules.

A relationship file is keyed by source license id, then by target license id, then by
linking context:

```json
{
  "Apache-1.0": {
    "0BSD": {
      "static_linking": "compatible",
      "dynamic_linking": "compatible",
      "distribution": "compatible"
    }
  }
}
```

The family in the filename groups the *source* license only. Targets are every license, so
`apache.json` contains rows for the three Apache sources against all 733 targets. Note that
the pair rules carry a third context, `distribution`, which the per-license record's
`compatibility` block does not have.

**Budget for the size.** `relationships/` is currently about 73 MB across ten files, and
`other.json` alone is 59 MB. Stream it or index it; do not plan on holding it in memory
next to everything else you are doing.

That size is the thing to know about `"format": "sparse"`, because the label promises more
than the data delivers. The intent of the format is that pairs resolving to `unknown` are
omitted. In the shipped data there are no `unknown` statuses, so nothing is omitted and the
store is a full enumeration: all 733 by 733 pairs, 537,289 of them, are present. Treat
`sparse` as a statement about the writer's rule, not as a promise that the file is small.

`"default_status": "unknown"` is still the rule you must implement for a pair you cannot
find: **unknown, not compatible**. Absence of a recorded conflict is not evidence of its
absence. A consumer that treats a missing pair as approval will ship a violation and blame
the dataset. Today no pair is missing, but that is a property of the current data and not a
promise, so code the default anyway.

Note also that the family names in `categories.json` (`gpl`, `bsd`, `cc`, `apache` and so
on) are a different taxonomy from the `type`/`category` field on a license (`permissive`,
`copyleft_strong` and so on). They are not interchangeable and one does not map onto the
other.

## What is not published

These exist, and reading them is not a supported thing to do:

- `obligation_database.json`, `ospac_license_database.json`, and `compatibility_matrix.json`.
  Generation-time intermediates. They are deleted by the generator's own cleanup step, so
  they are not in the wheel at all, and their `version` field is unrelated to this contract.
- Everything under `ospac.pipeline`. Dataset-generation machinery. It calls an LLM; the
  installed tool does not.
- `ospac/defaults/` and `ospac/data/LICENSE`. The bundled default policy is documented as
  behaviour, not as a data format, and it is opinionated on purpose. Copy it, do not parse it.
- Any file added under `ospac/data/` that this page does not name. If you find something
  useful there and want to depend on it, open an issue and it can be published deliberately.

## What `version` means

`version` is the version of the **data layout**, not of the ospac package and not of the
license data. It is a three-part string, `MAJOR.MINOR.PATCH`, and it is the same value in
`index.json`, `aliases.json`, and `compatibility/metadata.json`.

| Change | Bump |
|:--|:--|
| A published field is removed or renamed, a type changes, or a documented meaning changes | MAJOR |
| A published field is added, or a new file joins the published surface | MINOR |
| The contract text is corrected without the shape changing | PATCH |
| A monthly SPDX refresh: new licenses, changed classifications, updated deprecation flags | none |

That last row is the important one. A dataset refresh changes hundreds of values and does
not touch `version`, because the shape did not change. If you want to know whether your copy
of the data is stale, `version` is the wrong field.

Three parts rather than two, and a string rather than a number, for one reason: `1.10` sorts
below `1.9` under both float and lexicographic comparison. Compare on integers.

### version, generated, spdx_list_version

Three fields, three questions, no overlap:

| Field | Answers | Use it for |
|:--|:--|:--|
| `version` | Is the shape one I understand? | Compatibility gates |
| `spdx_list_version` | Which upstream SPDX revision is this? | Provenance, reproducing a decision |
| `generated` | When did the build that produced this run? | Staleness |

For a staleness check, use `generated`. The dataset is rebuilt monthly, so data older than
about six weeks means releases stopped arriving. `spdx_list_version` also moves on a refresh
but it is a commit hash, so it tells you *which* upstream you have and not *how old* it is.

### Checking compatibility from Python

Rather than opening `index.json` yourself:

```python
import ospac

info = ospac.data_version()
info.schema_version        # "1.1.0"
info.schema_version_info   # (1, 1, 0)
info.spdx_list_version     # "e4c1f27"
info.generated             # "2026-08-12T09:45:09.769222"
info.total_licenses        # 733
```

Assert once, at import, so an incompatible dataset fails loudly instead of producing quietly
wrong normalization:

```python
import ospac

major, _, _ = ospac.data_version().schema_version_info
if major != 1:
    raise RuntimeError(f"ospac data schema v{major} is not supported by this consumer")
```

`ospac.DATA_SCHEMA_VERSION` is the same value as a module constant, for a build-time pin.

## The compatibility promise

Within a major version:

- No published field is removed, renamed, or retyped.
- No published field's meaning changes. If the meaning has to change, that is a new field
  and the old one is deprecated, not a redefinition of the existing one.
- Fields may be added. Tolerate unknown keys.
- Values may change freely. A license may be reclassified, gain obligations, or flip its
  deprecation flag on any monthly refresh. The contract is about shape, never about
  verdicts. If a reclassification would change your output, pin `spdx_list_version` in
  whatever you store, so you can explain a decision later.
- License ids may appear and disappear, following SPDX. A deprecated id is kept, with
  `is_deprecated: true`, so a removal from upstream does not orphan an id you already
  recorded.

  `alias_of` is **not** guaranteed on a deprecated record. It is populated for the GPL,
  LGPL, AGPL and GFDL spellings, where the deprecated form maps onto an unambiguous
  `-only` or `-or-later` identifier. Fifteen other deprecated ids carry `alias_of: null`,
  including `wxWindows`, `eCos-2.0`, `Net-SNMP`, the two `BSD-2-Clause-*BSD` spellings and
  the seven `GPL-*-with-*-exception` ids, because SPDX replaced them with something other
  than a single plain identifier. To migrate a stored id, read `alias_of` and fall back to
  the alias map rather than assuming a non-null value.

### How a removal is announced

Nothing in the published surface is removed without all of:

1. A minor release that documents the deprecation on this page and in the
   [CHANGELOG](https://github.com/SemClone/ospac/blob/main/CHANGELOG.md), while the field
   keeps working.
2. At least one further minor release in which it still works.
3. A major bump of `version` that removes it, called out in the changelog under a
   `Breaking` heading.

There is no in-band notice mechanism, no deprecation flag inside the JSON. The changelog
and this page are the channel. If you consume the dataset in automation, watch releases.

## How this is enforced

`tests/test_data_contract.py` asserts every field named on this page, that the schema's
value domains still match the dataset validator's constants, and that all 733 shipped
records validate against the normative schema. A silent removal fails CI.

The field lists in that test are typed out by hand rather than read from the data, on
purpose. A test that derives its expectations from the file it is checking asserts only that
the data equals itself, which is how a contract test passes through the exact change it was
written to catch.

The test does not pin values, only shape. It has to stay green across a monthly refresh that
reclassifies licenses, and a test that pinned verdicts would fail on correct data and get
weakened until it stopped meaning anything.
