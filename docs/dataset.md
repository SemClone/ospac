---
layout: default
title: The dataset
nav_order: 4
description: How the license data is shaped, how it ships with the package, and how it is regenerated from SPDX.
---

# The dataset

ospac's decisions are only as good as its license data, so it is worth knowing what that
data is, where it comes from, and what it does and does not claim.

The short version: 729 SPDX licenses, one JSON file each, bundled inside the installed
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
│       ├── MIT.json              # one file per license, 729 total
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
729 files:

```json
{
  "version": "1.0",
  "generated": "2026-06-10T20:08:59.408681",
  "spdx_list_version": "3dfd9aa",
  "total_licenses": 729,
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

### The dataset is licensed separately from the code

ospac is dual-licensed, and this trips people up. The code is Apache-2.0. The dataset in
`ospac/data/` is **CC BY-NC-SA 4.0** — non-commercial, attribution required, share-alike.
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
      "liability": false,
      "warranty": false,
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
      "notes": "Permissive license with minimal restrictions"
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
    "generated": "2026-06-10T20:08:59.287920",
    "spdx_list_version": "3dfd9aa"
  }
}
```

| Field | Meaning |
|:--|:--|
| `type` | Family: `permissive`, `copyleft_weak`, `copyleft_strong`, `proprietary`, `public_domain`. Policy rules match on this via `license_type`. |
| `properties` | What the license lets you do. |
| `requirements` | Conditions you must satisfy. The booleans here drive `obligations`. |
| `limitations` | What the license withholds — warranty, liability, trademark grant. |
| `compatibility` | Per-linking-context rules. `category:any` means compatible with every family. |
| `contamination_effect` | How far copyleft reaches: `none`, `file`, `library`, `project`. |
| `obligations` | Human-readable duties, derived from `requirements`. |
| `spdx_metadata` | Upstream flags, including `is_deprecated`. |

{: .note }
> If you have seen older ospac documentation referring to a single
> `ospac_license_database.json` with `category`, `permissions` and `conditions` fields, that
> describes the pre-1.2.0 layout and no longer applies. The fields are now `type`,
> `properties` and `requirements`, and the data is split per license. Two CLI formatters
> still read the old names — see the warnings in
> [Commands]({{ site.baseurl }}/commands/#data-show).

### Compatibility is stored sparsely

`compatibility/metadata.json` records `"format": "sparse"` and
`"default_status": "unknown"`. Pairs are not enumerated — 729 licenses would mean over
265,000 pairs. Instead, licenses are grouped into families in `categories.json`, and only
the rules *between* families are stored, in `relationships/`. A lookup resolves each
license to its family and consults that rule.

The consequence worth internalising: a pair with no stored rule resolves to `unknown`, not
to compatible. Absence of a recorded conflict is not evidence of compatibility.

## How it is regenerated

The dataset is rebuilt from upstream SPDX by `ospac data generate`, implemented in
`ospac/pipeline/data_generator.py`. In normal operation you never run this — CI does, and
the result reaches you as a released version.

### The monthly pipeline

`.github/workflows/spdx-sync.yml` runs at 02:00 UTC on the first of each month, and can also
be triggered manually with `workflow_dispatch`. It does this:

1. **Check upstream.** Fetch SPDX `licenses.json`, diff the license IDs against the files in
   `ospac/data/licenses/json/`, and find both genuinely new IDs and existing records whose
   `is_deprecated` flag is now stale. If neither exists, the run stops here.
2. **Generate.** Run `ospac data generate --output-dir ospac/data --use-llm --llm-provider openai --force`.
   Only new licenses are analyzed; existing records are left alone unless
   `--force-reprocess` is passed.
3. **Validate.** Run `python scripts/validate_data.py --data-dir ospac/data`, which checks
   every record for structural completeness and semantic correctness and spot-checks
   well-known licenses. Errors fail the run.
4. **Bump the patch version** in `pyproject.toml`.
5. **Open a pull request** labelled `data,automated`, with a body summarising the SPDX
   version, new license IDs, and deprecation flags changed, then enable auto-merge.

So dataset changes arrive as reviewable pull requests with a diff you can read — the commit
history shows them as `data: sync SPDX <version> — N new, M deprecated`. Deprecation
flagging (step 1b) happens without an LLM, since it only copies an upstream boolean.

### Where the LLM fits, and where it does not

An LLM reads license texts during generation to classify a license's family, permissions and
conditions. Providers are OpenAI, Anthropic Claude, and local Ollama
(`ospac/pipeline/llm_providers.py`); CI uses OpenAI. This is a maintainer-time step. The
installed tool never calls a model, and `pip install ospac` does not pull an LLM SDK — that
is what the `[llm]` extra is for.

Two mechanisms exist because raw LLM output was not trustworthy enough:

**Obligations are derived, not generated.** `obligations` and `key_requirements` are
computed deterministically from the `requirements` and `properties` booleans, because
LLM-written prose for these fields came back uniformly generic. `disclose_source: true`
always produces "Provide or offer access to complete source code", for every license, with
identical wording. So obligation text is a mechanical function of the structured fields — if
an obligation looks wrong, the underlying boolean is wrong.

**Known misclassifications are overridden.** A correction table pins fields that LLMs
repeatedly got wrong for well-known licenses. Apache-2.0 is the motivating case: it was
classified as copyleft with `same_license` and `disclose_source` set, which is simply false
and would have denied Apache-2.0 across copyleft policy rules. The table also covers
MPL-2.0 and CC0-1.0.

The design assumption is that the LLM is a useful first pass over 729 license texts and not
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

Notes on cost and correctness. `--force-reprocess` reanalyzes all 729 licenses and is the
expensive path; without it, generation is a delta over what already exists, and progress is
tracked so an interrupted run resumes. `--limit` bounds a trial run. Regenerating a record
does not preserve manual edits, so corrections belong in the correction table rather than in
the output files.

## Validating data

`scripts/validate_data.py` is the current validator and the one CI trusts:

```bash
$ python scripts/validate_data.py --data-dir ospac/data
────────────────────────────────────────────────────────────
  Total files  : 729
  Clean        : 728
  Warnings     : 1
  Errors       : 0

  PASS (strict=False)
```

Warnings do not fail the exit code unless you pass `--strict`; errors always do. `--json`
gives machine-readable output for a CI annotation.

Prefer this over `ospac data validate`, which still expects the pre-1.2.0 YAML layout and
fails against the shipped dataset.
