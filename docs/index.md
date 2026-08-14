---
layout: default
title: Overview
nav_order: 1
description: What ospac does, how to install it, and how to run it for the first time.
permalink: /
---

# ospac

ospac answers a narrow question: given a set of licenses and something you intend to do
with them, is that allowed? It reads the licenses, applies a policy you can keep in Git,
and returns an action (approve, deny, or flag for review) along with the obligations
you take on if you proceed.

The point is that the answer lives in a policy file, not in ospac's code. Compliance
rules differ between a mobile app and an internal service, and they change as legal
guidance changes. ospac treats those rules as data: versioned, reviewable in a pull
request, and testable.

It ships with a complete SPDX license dataset, so it works offline the moment it is
installed. Nothing needs to be generated or downloaded first.

## Installing

```bash
pip install ospac
```

ospac needs Python 3.10 or later. The license dataset is bundled in the wheel.

Optional extras pull in things only some workflows need:

```bash
pip install "ospac[semcl]"   # osslili + upmex, for scanning real projects
pip install "ospac[llm]"     # LLM providers, only needed to regenerate the dataset
pip install "ospac[all]"     # both
```

To work on ospac itself, install from a checkout in editable mode:

```bash
git clone https://github.com/SemClone/ospac.git
cd ospac
pip install -e ".[dev]"
```

## First run

Ask whether two licenses can be combined:

```bash
$ ospac check GPL-2.0 Apache-2.0
Using default enterprise policy. Create a custom policy with 'ospac policy init' to customize.
✗ GPL-2.0 and Apache-2.0 are incompatible

Violations:
  - GPL-2.0 and Apache-2.0 are incompatible due to patent clause conflicts
```

Ask whether a set of licenses is acceptable for how you ship:

```bash
$ ospac evaluate -l "GPL-3.0,MIT" -d commercial -o text
Evaluating licenses: GPL-3.0, MIT
--------------------------------------------------
Action: deny
Message: GPL licenses not allowed in commercial products due to viral copyleft requirements

Requirements:
  • Preserve copyright notice
  • Include MIT license text
```

The same licenses can produce a different answer under a different distribution type.
That is the whole idea. `-d mobile` is stricter than `-d internal`, because the policy
says so, not because ospac hard-codes it.

And ask what you owe if you do ship something:

```bash
$ ospac obligations -l MIT -f checklist

MIT:
----------------------------------------
  ☐ Retain copyright notices
  ☐ Include license text
```

## Two things worth knowing early

**There is always a policy in play.** With no `--policy-dir`, ospac loads a bundled
default enterprise policy and says so on stderr. That default is opinionated: it denies
GPL for commercial distribution and flags LGPL static linking for review. Treat it as a
starting point to copy, not as neutral ground. `ospac policy init` writes one you own.

**ospac is offline.** Evaluation reads the bundled dataset and your policy files; it makes
no network calls and consults no model. LLMs appear in exactly one place, regenerating the
dataset, a maintainer task described in [The dataset]({{ site.baseurl }}/dataset/). The tool
you install does not use them.

Decisions are reproducible, so the same inputs give byte-identical output run to run.

## Where to go next

| Page | What it covers |
|:--|:--|
| [Commands]({{ site.baseurl }}/commands/) | Every CLI command and flag, with real output |
| [Policies]({{ site.baseurl }}/policies/) | Rule schema, matching, and the build-target templates |
| [The dataset]({{ site.baseurl }}/dataset/) | How the license data is shaped, shipped, and regenerated |
| [Python API]({{ site.baseurl }}/api/) | Using ospac as a library |
| [Integration]({{ site.baseurl }}/integration/) | CI, the SEMCL.ONE toolchain, and MCP |
