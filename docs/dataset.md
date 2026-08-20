---
layout: default
title: The dataset
nav_order: 4
description: How the license data is shaped, how it ships with the package, and how it is regenerated from SPDX.
---

# The dataset

ospac's decisions are only as good as its license data, so it is worth knowing what that
data is, where it comes from, and what it does and does not claim.

The short version: every license in the SPDX list, one JSON file each, bundled inside the installed
wheel, regenerated monthly by an automated pipeline that opens a pull request for review.

## How it ships

The dataset is package data inside `ospac/data/`, declared in `pyproject.toml` under
`[tool.setuptools.package-data]`. It is inside the wheel, so `pip install ospac` gives you a
working tool with no download or generation step. There is no separate data package and no
first-run setup.

```
ospac/data/
├── index.json                    # lookup index over every license
├── LICENSE                       # CC BY-NC-SA 4.0, applies to this directory
├── licenses/
│   └── json/
│       ├── MIT.json              # one file per license
│       ├── Apache-2.0.json
│       └── ...
└── compatibility/
    ├── metadata.json             # version, count, format
    ├── categories.json           # license ID → family membership
    └── relationships/            # cross-family rules, one file per family
        ├── gpl.json
        ├── apache.json
        └── ...
```

One file per license is deliberate. Looking up a single license reads a single small file
rather than parsing a multi-megabyte database, which is what makes CLI startup fast.
`index.json` exists so that listing and category questions can be answered without opening
every license file:

```json
{
  "version": "1.1.0",
  "generated": "2026-08-01T03:04:52.358635",
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

Note `spdx_list_version` in both the index and every license record. Every value in the
dataset is traceable to a specific upstream SPDX commit and a generation timestamp.

If you are reading these files from another tool, `version` and the field list are a
promise, not an accident. What that promise covers is on
[Data contract]({{ site.baseurl }}/data-contract/).

### The dataset is licensed separately from the code

ospac is dual-licensed, and this trips people up. The code is Apache-2.0. The dataset in
`ospac/data/` is **CC BY-NC-SA 4.0**: non-commercial, attribution required, share-alike.
See [`DATA_LICENSE`](https://github.com/SemClone/ospac/blob/main/DATA_LICENSE).

Installing ospac and running it inside a commercial organization to check your own
compliance is ordinary internal use. Redistributing the dataset, or building a commercial
product on top of it, is what the NC term restricts. If you are unsure which side of that
line you are on, that is a question for your counsel, not for this page.

## What a license record contains

Each file wraps a single `license` object. `ospac data show MIT -f json` unwraps it for you;
the file on disk has the extra nesting level.

```json
{
  "license": {
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
    "requirements": {
      "disclose_source": false,
      "include_license": true,
      "include_copyright": true,
      "include_notice": false,
      "state_changes": false,
      "same_license": false,
      "network_use_disclosure": false
    },
    "limitations": {
      "liability": true,
      "warranty": true,
      "trademark_use": false
    },
    "compatibility": {
      "static_linking": {
        "compatible_with": ["category:any"],
        "incompatible_with": [],
        "requires_review": []
      },
      "dynamic_linking": { "...": "same shape" },
      "contamination_effect": "none",
      "notes": "MIT license is permissive and does not impose restrictions on the licensing of combined works."
    },
    "obligations": [
      "Retain copyright notices",
      "Include license text"
    ],
    "key_requirements": ["Attribution required"],
    "spdx_metadata": {
      "is_osi_approved": true,
      "is_fsf_libre": true,
      "is_deprecated": false
    },
    "generated": "2026-08-12T08:41:12.418762",
    "spdx_list_version": "e4c1f27"
  }
}
```

| Field | Meaning |
|:--|:--|
| `type` | Family: `permissive`, `copyleft_weak`, `copyleft_strong`, `network_copyleft`, `noncommercial`, `no_derivatives`, `source_available`, `proprietary`, `public_domain`, `unknown`. Policy rules match on this via `license_type`. `noncommercial` and `no_derivatives` exist because those restrictions contradict `permissive`, and policy rules that approve by category would otherwise bless them. |
| `properties` | What the license lets you do. |
| `requirements` | Conditions you must satisfy. The booleans here drive `obligations`. |
| `limitations` | Disclaimer analysis: `liability: true` means the license disclaims liability, which is standard for OSS. `trademark_use: true` means trademark use is restricted. |
| `compatibility` | Per-linking-context rules, derived from the record's category plus a table of known license-level exceptions such as GPL-2.0 with Apache-2.0. Entries are license ids or `category:<type>` specifiers; `category:any` means compatible with every family. Only the prose `notes` come from the analysis. |
| `contamination_effect` | How far copyleft reaches: `none`, `module` (the linked module only), `derivative` (derivative works only, which is what share-alike licenses such as CC-BY-SA require), `full` (the whole combined work), `unknown`. |
| `obligations` | Human-readable duties, derived from `requirements`. |
| `aliases` | Lowercased spellings that mean this license: its own id and name, the deprecated SPDX spellings mapped forward, and curated ecosystem spellings such as `expat` for MIT. Empty exactly when `alias_of` is set, because those spellings live on the canonical record instead. A deprecated record with `alias_of: null` keeps its own spellings, since there is no single canonical id to move them to. |
| `alias_of` | On a deprecated GPL, LGPL, AGPL or GFDL spelling: the canonical id it means. `null` elsewhere. |
| `spdx_metadata` | Upstream flags, including `is_deprecated`. |
| `generated`, `spdx_list_version` | When the analysis that produced this record ran, and against which SPDX revision. Deterministic repairs derived from the record's own fields do not re-stamp it, so the stamp answers "when was this license analysed", not "when did this file last change". |

{: .note }
> If you have seen older ospac documentation referring to a single
> `ospac_license_database.json` with `category`, `permissions` and `conditions` fields, that
> describes the pre-1.2.0 layout and no longer applies. The fields are now `type`,
> `properties` and `requirements`, and the data is split per license. Two CLI formatters
> still read the old names. See the warnings in
> [Commands]({{ site.baseurl }}/commands/#data-show).

### Compatibility is stored sparsely

`compatibility/metadata.json` records `"format": "sparse"` and
`"default_status": "unknown"`. The writer's rule is that a pair resolving to `unknown` is
not written, and licenses are grouped into families in `categories.json` so that
`relationships/` can be split into one file per source family.

In practice the current data has no `unknown` statuses, so nothing is omitted and all 733
by 733 pairs are on disk: 537,289 of them, about 73 MB. "Sparse" describes the intent, not
today's file sizes. If you are consuming `relationships/` directly, read
[Data contract]({{ site.baseurl }}/data-contract/) first, which documents the pair shape.

The consequence worth internalising: a pair with no stored rule resolves to `unknown`, not
to compatible. Absence of a recorded conflict is not evidence of compatibility.

## Aliases

Every tool that normalizes a declared license ends up curating its own alias table, and
divergent tables are how the same SBOM gets different answers from different tools. The
dataset owns the aliases instead: each record carries its spellings, and
`ospac/data/aliases.json` flattens them into one lowercased map:

```python
import ospac
ospac.license_aliases()["expat"]        # "MIT"
ospac.license_aliases()["gpl-3.0+"]     # "GPL-3.0-or-later"
ospac.license_ambiguous()["gplv3"]      # ["GPL-3.0-only", "GPL-3.0-or-later"]
ospac.license_never_resolve()           # {"gpl", "bsd", "apache", ...}
```

Two rules keep the map honest. An alias claimed by more than one license resolves to
nothing, because a wrong confident answer is worse than none: SPDX's duplicate Standard
ML of New Jersey entries are the current example. And family names never resolve at
all: `bsd` is 2-clause or 3-clause and the choice changes obligations, `gpl` states
neither a version nor only/or-later, and the deprecated SPDX key resolved bare GPL to
GPL-1.0-or-later, which nobody writing GPL today means. `license_never_resolve()` lists
them so consumers refuse them deliberately rather than each inventing a guess.

Refusing to resolve is not the same as having nothing to say, though. `license_ambiguous()`
is the middle case: text that identifies a license and not which id, mapped to the ids it
could mean. The GNU families are the whole of it in practice, because their prose names
carry the version and not the grant: "GNU Lesser General Public License v2.1" is the SPDX
name of both `LGPL-2.1-only` and `LGPL-2.1-or-later`, and choosing between them asserts
something the document never said. It is derived rather than curated, from the SPDX names
with the grant word removed, so an SPDX release that adds a family adds its entries too. The
colliding aliases land here as well, with their candidates, instead of disappearing.
A validator reading this can tell a user which distinction is missing rather than report a
perfectly legible name as unrecognised.

`ospac data aliases` prints all three from the command line.

## How it is regenerated

The dataset is rebuilt from upstream SPDX by `ospac data generate`, implemented in
`ospac/pipeline/data_generator.py`. In normal operation you never run this. CI does, and
the result reaches you as a released version.

### The monthly pipeline

`.github/workflows/spdx-sync.yml` runs at 02:00 UTC on the first of each month, and can also
be triggered manually with `workflow_dispatch`. It does this:

1. **Preflight.** Construct the LLM provider before anything else, so a missing package
   or API key fails the job immediately instead of producing fabricated records.
2. **Check upstream.** Fetch SPDX `licenses.json`, diff the license IDs against the files in
   `ospac/data/licenses/json/`, and find both genuinely new IDs and existing records whose
   `is_deprecated` flag is now stale. If neither exists, the run stops here.
3. **Generate.** Run `ospac data generate --output-dir ospac/data --use-llm --llm-provider openai --force`.
   Only new licenses are analyzed; existing records are left alone unless
   `--force-reprocess` is passed. A record that had to fall back instead of being analyzed
   is deleted and fails the run, so a partly fabricated dataset cannot continue.
4. **Validate.** Run `python scripts/validate_data.py --data-dir ospac/data`, which checks
   every record for structural completeness, the restriction invariants, and spot-checks
   of well-known licenses. Errors fail the run.
5. **Upload the dataset as an artifact**, so a rejected run can still be reviewed record
   by record.
6. **Corpus quality gate**, on full regenerations: fail if decision fields are uniform
   across the corpus or any record matches a known fallback fingerprint, which is the
   failure mode per-record validation cannot see.
7. **Bump the patch version** in `pyproject.toml`.
8. **Open a pull request** labelled `data,automated`, with a body summarising the SPDX
   version, new license IDs, and deprecation flags changed, then enable auto-merge.

So dataset changes arrive as reviewable pull requests with a diff you can read. The commit
history shows them as `data: sync SPDX <version>, N new, M deprecated`. Deprecation
flagging (step 1b) happens without an LLM, since it only copies an upstream boolean.

### Where the LLM fits, and where it does not

An LLM reads license texts during generation to classify a license's family, permissions and
conditions. Providers are OpenAI, Anthropic Claude, and local Ollama
(`ospac/pipeline/llm_providers.py`); CI uses OpenAI. This is a maintainer-time step. The
installed tool never calls a model, and `pip install ospac` does not pull an LLM SDK. That
is what the `[llm]` extra is for.

Two mechanisms exist because raw LLM output was not trustworthy enough:

**Obligations are derived, not generated.** `obligations` and `key_requirements` are
computed deterministically from the `requirements` and `properties` booleans, because
LLM-written prose for these fields came back uniformly generic. `disclose_source: true`
always produces "Provide or offer access to complete source code", for every license, with
identical wording. So obligation text is a mechanical function of the structured fields. If
an obligation looks wrong, the underlying boolean is wrong.

**Known misclassifications are overridden.** A correction table pins fields that LLMs
repeatedly got wrong for well-known licenses. Apache-2.0 is the motivating case: it was
classified as copyleft with `same_license` and `disclose_source` set, which is simply false
and would have denied Apache-2.0 across copyleft policy rules. The table now pins
roughly forty licenses, including the LGPL and AGPL families, EPL, CDDL, EUPL, OSL, SSPL,
BUSL, Elastic, Parity, Aladdin and the CERN-OHL variants, and a deterministic layer
derives every restriction the identifier or name states outright: NC, ND and SA
components, Non-Profit and Reciprocal naming. The model cannot override either.

The design assumption is that the LLM is a useful first pass over hundreds of license texts and not
an authority. Validation, deterministic derivation, human PR review, and the correction
table all exist to catch it being wrong.

### Running it yourself

You would do this to test a pipeline change or to build a dataset with your own analysis.

```bash
pip install -e ".[llm]"

# Cheap trial: three licenses, local model, scratch directory
export OLLAMA_HOST=http://localhost:11434
ospac data generate --output-dir ./data --use-llm --llm-provider ollama --limit 3

# Always validate before trusting the result
python scripts/validate_data.py --data-dir ./data
```

Point ospac at your own dataset with `--data-dir`, which `obligations` accepts:

```bash
ospac obligations -l MIT -d ./data
```

Notes on cost and correctness. `--force-reprocess` reanalyzes every license and is the
expensive path; without it, generation is a delta over what already exists, and progress is
tracked so an interrupted run resumes. `--limit` bounds a trial run. Regenerating a record
does not preserve manual edits, so corrections belong in the correction table rather than in
the output files.

## Validating data

`scripts/validate_data.py` is the current validator and the one CI trusts:

```bash
$ python scripts/validate_data.py --data-dir ospac/data
────────────────────────────────────────────────────────────
  Total files  : 733
  Clean        : 728
  Warnings     : 5
  Errors       : 0

  PASS (strict=False)
```

Warnings do not fail the exit code unless you pass `--strict`; errors always do. `--json`
gives machine-readable output for a CI annotation.

`ospac data validate` runs the same rules from the installed package, so either entry
point gives the same verdict. For the corpus-level check that catches templated datasets,
run `scripts/corpus_quality.py`, described under the monthly pipeline above.
