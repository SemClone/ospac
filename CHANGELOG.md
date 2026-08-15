# Changelog

All notable changes to OSPAC (Open Source Policy as Code) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-08-15

### Added

**License aliases, owned by the dataset** (#63)
- Every tool normalizing a declared license curated its own alias table, and divergent
  tables are how one SBOM gets different answers from different tools. Each record now
  carries an `aliases` list and deprecated spellings carry `alias_of`, flattened into
  `ospac/data/aliases.json` and exposed as `ospac.license_aliases()`, a lowercased alias
  to SPDX id map covering official names, deprecated spellings mapped forward, and
  curated ecosystem spellings such as `expat` for MIT and `apache2` for Apache-2.0.
- `ospac.license_never_resolve()` lists family names that must not resolve: `bsd` is
  2-clause or 3-clause and the choice changes obligations, `gpl` states neither a
  version nor only/or-later, and the deprecated SPDX key resolved bare GPL to
  GPL-1.0-or-later, which nobody writing GPL today means.
- An alias claimed by more than one license resolves to nothing, since a wrong confident
  answer is worse than none. `ospac data aliases` prints the map from the CLI, and the
  reproducibility test pins the alias fields alongside everything else.
- The canonical-identifier mapping gained the GFDL family, whose deprecated bare
  spellings follow the same pattern as GPL.

**`check` accepts the standard input style** (#18)
- `check` took only two positional arguments while `evaluate` and `obligations` take
  `-l "A,B"`, so the input style had to be remembered per command. `check -l "MIT,GPL-3.0"`
  now works, positionals still work, and mixing the two styles is rejected with a clear
  message.

## [1.4.5] - 2026-08-15

An independent review of the v1.4.1 to v1.4.4 diff found three defects in the
compatibility work; all are fixed and each fix is pinned by tests.

### Fixed

**The known-incompatible table missed the deprecated + spellings**
- `GPL-3.0+` is the deprecated alias of `GPL-3.0-or-later`, but only the modern
  spellings sat in the 4-clause BSD exception, so the generated data called
  `GPL-3.0+` with `BSD-4-Clause` compatible. Both + spellings are in the pair now.

**The runtime never enforced the known-incompatible table**
- `check` answered from policy rules alone, and the policy only enumerated some of
  the pairs, so `GPL-2.0` with `BSD-4-Clause` reported compliant while the records
  named each other incompatible: 30 of 48 pair directions passed. The dataset's
  named incompatibilities now outrank category-level approvals in
  `check_compatibility`, the same precedence named exceptions get in
  `License.is_compatible_with`, and a test sweeps every table direction through the
  runtime. All 60 directions now deny.

**Alias spellings of one license were reported as a pair needing review**
- `GPL-2.0` and `GPL-2.0-only` are the same license in two spellings, but the
  relationships tree marked them `review_required` and `is_compatible_with`
  returned false. A canonical-identifier helper resolves the deprecated bare and
  `+` GPL-family spellings, and both consumers treat alias-equal identifiers as
  identical. Five records and the tree rebuilt.

## [1.4.4] - 2026-08-15

Clears the remaining known defects from the session ledger.

### Fixed

**The bundled policy carried one more rule that could never execute**
- `gpl_dev_tools` approved GPL for development-only use by matching on a `usage`
  field that no evaluation path provides, the same never-executes shape as the
  removed `decision_tree` and compatibility sections. Removed. A test now pins the
  vocabulary: every `when` key in the bundled policy and in the generated templates
  must be a field the CLI actually sets, so this class of dead rule cannot return.

**`check` reported an empty `licenses_checked`**
- `check_compatibility` always returned `licenses_checked: []` even though it
  checked exactly two licenses. It now names them.

**0BSD asked for attribution and license text**
- The zero-clause BSD requires nothing at all; the analysis kept asking for
  copyright retention and license inclusion anyway. Pinned in the correction table
  and the record rebuilt: obligations are now empty, matching Unlicense and CC0.

### Changed

- The `generated` and `spdx_list_version` fields are documented as recording when
  the analysis that produced a record ran, against which SPDX revision.
  Deterministic repairs derived from a record's own fields do not re-stamp it,
  deliberately: re-stamping would make the reproducibility check impossible, and
  the stamp answers "when was this license analysed", not "when did this file last
  change".

## [1.4.3] - 2026-08-14

Recovers four review findings that were deferred during the 1.4.x work and lost:
none had been filed anywhere, and an audit of the session ledger found them.

### Fixed

**The aggregate discarded the winning rule's reason**
- Every decision reported `Evaluated N rules` instead of the message the matching
  rule's author wrote, so a GPL denial surfaced with no mention of copyleft in any
  output format. The aggregate now carries the most restrictive rule's own message,
  and the per-license map continues to attribute it.

**`check -c static_linking` never reached linking rules**
- The compatibility context was stored under a key no rule matches on, and
  `linking_type` was never set, so `check MIT MPL-2.0 -c static_linking` answered
  as if no context had been given. The pair context now derives `linking_type`
  exactly as `evaluate` does, so weak copyleft under static linking is flagged for
  review on pairs too.

**Multi-restriction licenses headlined only the dominant restriction**
- CC-BY-NC-SA carried `Commercial use not permitted` and dropped the share-alike
  term from `key_requirements` entirely; CC-BY-NC-ND likewise dropped
  no-derivatives. The derivation now appends the lines the category headline does
  not already state. 26 records updated.

**The relationships tree still carried the model's wrong claims**
- `ospac/data/compatibility/relationships/` was rebuilt during 1.4.1 from the
  model-generated lists, one release before 1.4.2 derived them, so it shipped
  claiming MIT is statically incompatible with GPL-3.0 and that CC-BY-NC-4.0 is
  compatible with 494 licenses. The category fallback behind it also called
  permissive-into-copyleft incompatible and guessed the distribution dimension
  independently, reporting GPL-2.0 with Apache-2.0 as distributable together.
- The fallback now mirrors the derivation semantics, review wildcards resolve
  instead of falling through, the distribution dimension follows the static
  verdict so known-incompatible pairs propagate, and the tree is rebuilt from the
  derived records. Tests pin the tree's soundness alongside the records'.

## [1.4.2] - 2026-08-12

### Fixed

**The record-level compatibility lists were model-generated and systematically wrong**
- 540 of 733 records typed permissive or public domain declared themselves incompatible
  with GPL or strong copyleft, which inverts how permissive licensing works: permissive
  code can be incorporated into copyleft works, and that is the point of it. MPL-2.0
  claimed incompatibility with the GPL it is expressly designed to combine with, and
  pairs disagreed with each other, BSD-3-Clause calling GPL-3.0 incompatible while
  GPL-3.0 called BSD-3-Clause compatible.
- The policy engine was unaffected: `ospac check` answers from rules and was correct
  throughout. The wrong lists were served raw in every record, and read by
  `License.is_compatible_with`.
- Compatibility between categories is a derivable fact, so it is now derived from the
  record's final category plus a table of known license-level exceptions, applied on
  every path that writes a record and pinned by the reproducibility test. The model
  contributes only the prose notes. All 733 blocks rebuilt; the known exceptions,
  GPL-2.0 with Apache-2.0, GPL-2.0 with GPL-3.0, and 4-clause BSD with any GPL, land in
  both records of each pair so the claims stay symmetric.
- Tests now assert no permissive record claims copyleft incompatibility beyond the
  exception table, that pairwise claims never contradict each other, and that the known
  pairs are mutually incompatible.

**`License.is_compatible_with` never matched category entries**
- Dataset entries use `category:<type>` specifiers, but the method compared the other
  license's bare type against them, so category entries never matched and most lists
  were silently inert. It also consulted `compatible_with` before `incompatible_with`,
  which would have let a category match hide a named exception once the lists worked.
  Category specifiers and `category:any` now resolve, and incompatibility is checked
  first.

## [1.4.0] - 2026-08-11

Clears the three items 1.3.0 left open, and repairs a licence dataset that had
never actually been analysed.

### Fixed

**An explicit approval could be reported as `allow`**
- A policy rule that states no action falls back to `ALLOW`, and the aggregate ranked
  `ALLOW` above `APPROVE`, so a single actionless rule made the whole evaluation report
  `allow` even when another rule had explicitly approved the licenses.
- That contradicts the documented meaning of the field, where `allow` indicates that no
  rule matched and is worth treating as a policy bug. A correct policy mixing an explicit
  `approve` rule with an actionless one therefore looked broken, and CI written against the
  documented values would fail on it.
- Between `ALLOW` and `APPROVE` neither is more restrictive, so the more informative one
  now wins. `DENY`, `CONTAMINATE` and `FLAG_FOR_REVIEW` still outrank both. An evaluation
  where nothing matches returns `flag_for_review`, described under its own entry below.

**`LGPLLR` was classified as strong copyleft**
- Its properties, requirements, limitations and contamination effect are all identical to
  `LGPL-2.1`, so typing it `copyleft_strong` while `LGPL-2.1` is `copyleft_weak` was
  inconsistent on the dataset's own terms. It is also, by name and design, the lesser
  licence for linguistic resources.
- Corrected in the record and in `index.json`, added to the pipeline correction table so
  regeneration keeps it, and pinned in the validator spot checks as a deliberate decision.

**The LLM analysis had never run, and its fallback fabricated permissive data**
- `.github/workflows/spdx-sync.yml` installs with `pip install -e ".[llm]" 2>/dev/null || pip
  install -e . openai`, but the `[llm]` extra contained only `strands-agents`, so the first
  command succeeded and the fallback that installs `openai` never ran. The package the
  provider imports was never present.
- The provider caught the `ImportError`, set itself unavailable, and every licence fell
  through to `_get_fallback_analysis()`, which hardcoded `category: "permissive"` with
  `commercial_use: True` and every copyleft condition false. The job exited zero, the
  validator passed, the pull request auto-merged and published.
- 683 of 733 records carry that fingerprint. The 50 that do not are the GPL, LGPL, MPL and
  public domain families, which a deterministic name matcher already handled. No record in
  the dataset was ever produced by an actual model.
- Provider construction now raises instead of degrading, so an explicitly requested
  provider that cannot initialise aborts the run before any licence is processed, and the
  workflow gained a preflight step that fails immediately on a missing package or secret.
- The fallback now fails closed rather than open: category `unknown`, every permission
  denied, obligations that ask for manual legal review. A run that produced any fallback
  record reports the identifiers and exits non-zero, so a partly fabricated dataset cannot
  be published.
- The `[llm]` extra now installs `openai`, `anthropic` and `ollama`, which are what the
  three providers actually import. `strands-agents` was imported nowhere and was dropped.

**Every NonCommercial licence was marked commercially usable**
- A consequence of the fallback above. `ospac evaluate -l CC-BY-NC-3.0-IGO -d commercial`
  returned `allow`, which is the most dangerous direction for a compliance tool to be wrong
  in. OSPAC's own dataset licence, CC BY-NC-SA 4.0, was described as permissive and
  commercially usable, contradicting `DATA_LICENSE`.
- 43 records repaired: 26 NonCommercial licences that permitted commercial use, 13
  NoDerivatives licences that permitted modification, and 21 ShareAlike licences that
  carried no same-licence requirement.
- Creative Commons states these terms in the identifier itself, so the pipeline now derives
  them rather than asking a model. Matching is on hyphen-delimited identifier components,
  with a punctuation-insensitive name check that also catches `NCGL-UK-2.0` and
  `PolyForm-Noncommercial-1.0.0`, neither of which has an `NC` component.
- The validator gained the matching invariants as errors, so the class cannot ship again.
- The bundled enterprise policy now denies NonCommercial licences for commercial, SaaS,
  embedded, mobile, desktop, web, cloud and API distribution, and flags them for review
  elsewhere. Repairing the data alone was not enough, since no rule covered them.

**An unmatched evaluation reported `allow`**
- When no rule matched, the result was `action: allow` with `No policies matched`. A policy
  with no rule for a case has not approved it, it has no answer, and reporting those
  identically meant a policy whose rules had silently stopped matching read as a clean pass.
- Unmatched evaluations now return `flag_for_review` with a warning severity and a
  remediation suggesting either a rule for the case or an explicit approval after review.
- This is a behaviour change for anyone whose CI treated `allow` as success. Uncovered cases
  now arrive as `flag_for_review`.

**The bundled policy denied copyleft by enumerated identifier only**
- `no_gpl_in_products` and `no_agpl_in_services` list individual licenses, so a copyleft
  license nobody had listed fell through every rule. `AGPL-3.0` evaluated for commercial
  distribution came back permitted.
- Added category rules for strong copyleft in distributed products, network copyleft in
  hosted services, and weak copyleft under static linking. These match on `license_type`,
  which only began working earlier in this release.

**Permissive licenses were approved only if individually listed**
- The rule approving permissive and public domain licenses by category existed solely in the
  policy's `decision_tree` section, which the runtime never reads: it evaluates `rules` only.
  So `MIT`, `Apache-2.0` and `BSD` passed because they are enumerated, while `ISC`, `Zlib`
  and several hundred others matched nothing at all. Invisible while unmatched meant `allow`.
- Ported that rule into `rules` as `approve_permissive`, and removed the `decision_tree`
  section. Its other entries duplicated rules that already exist, and config that looks
  authoritative while never executing is how several defects here went unnoticed.

**One license in a set could answer for all of them**
- Evaluation ran once over the whole license list, so a rule matched by any license
  produced a result and the no-match fail-safe never ran for the others.
  `evaluate -l "MIT,AGPL-3.0"` was approved: MIT fired the permissive rule, AGPL matched
  nothing, and nothing spoke for it. Real dependency lists almost always contain a
  permissive license, so the fail-safe was inert exactly where it mattered.
- Each license is now evaluated independently and the verdicts aggregate with
  most-restrictive-wins. A license that matches no rule falls to the fail-safe on its own,
  so `MIT,MPL-2.0` reports `flag_for_review` and `MIT,AGPL-3.0` reports `deny`. The JSON
  output gains a `per_license` map showing each license's own verdict.

**`ospac check` reported a license as incompatible with itself**
- The fail-safe applied to compatibility checks too, and the check context carries no
  distribution type, so no category rule could match, nothing matched at all, and the
  review answer surfaced as `compatible: false` with empty violations for 80 licenses,
  including `check GPL-3.0-only GPL-3.0-only`.
- A compatibility question asks whether a conflict is known, so no conflict rule matching
  now answers "no known conflicts" rather than "needs review". The review default remains
  for `evaluate`, where an unmatched case genuinely is an unanswered question.
- `check` output gains `requires_review` and `warnings`, and warns when a license id does
  not resolve in the dataset instead of letting a typo read as clean compatibility.

**The policy's compatibility matrix was dead config**
- The `compatibility:` section in the bundled policy was never read by the runtime, so
  `ospac check BSD-4-Clause GPL-3.0-only` reported compatible while the policy's own file
  declared that pair incompatible. Its pairs are now real rules, including both directions
  of the BSD-4-Clause advertising-clause conflict and the one-way MIT into GPL-2.0 and
  Apache-2.0 into GPL-3.0 combinations, and the dead section is removed.

**Weak copyleft had no passing path**
- The category rules added for weak copyleft could deny and review but nothing ever
  approved, so `MPL-2.0` had no outcome other than review in any context. A category rule
  now approves weak copyleft under dynamic linking with the containment requirements, and
  the general context stays a review because the tool cannot see how the component is
  linked.

**`-o markdown` rendered every approval as Denied**
- The renderer treated only the literal action `allow` as good, so `approve` printed
  `❌ Denied` and the text renderer coloured it red. Category approval moved 645 licenses
  from `allow` to `approve`, turning a latent bug into "Denied" for Zlib and ISC in
  anything that pasted the markdown into a report. Both renderers now map every action to
  an honest status, including `⚠️ Requires review`.

**`data generate` without `--use-llm` wrote an inverted dataset**
- With the fallback now failing closed, the no-provider path produced records claiming
  0BSD forbids commercial use and requires source disclosure, printed a green checkmark
  and exited zero. The command now refuses to run without `--use-llm`, since every record
  on that path is a placeholder, and the shipped package already contains real data.
- When the fallback gate does trip on an LLM run, the fabricated records are now deleted
  before exiting, because delta processing treats on-disk files as complete and a rerun
  would have skipped the poisoned records while reporting a clean dataset.

**Restrictions stated in license names and identifiers are now derived, not hand edits**
- The ShareAlike retypes shipped earlier in this release existed only as edited JSON: the
  pipeline would have written `permissive` back over them on the next regeneration, and
  the validator would have accepted it. The same silent-revert failure this release
  diagnoses elsewhere, one field over.
- The pipeline now retypes ShareAlike and reciprocal licenses out of `permissive` itself,
  types NoDerivatives records as `no_derivatives`, and forces `noncommercial` regardless
  of what the analysis claimed. Name stems catch Non-Profit, Reciprocal and copyleft
  naming, adding `NPOSL-3.0`, `MS-RL`, `RPL`, `CERN-OHL` and the `copyleft-next` family.
- Mainstream licenses the fabricated data recorded as freely permissive are pinned in the
  correction table with what their texts actually say: EPL, CDDL, EUPL, OSL, SSPL, CAL,
  BUSL, Elastic, Parity, Aladdin, ODbL and CDLA-Sharing. `SSPL-1.0` for SaaS now denies.
- A test asserts every shipped record is exactly what the pipeline reproduces for it, so a
  repair that exists only as a hand edit can no longer ship.
- Validator invariants strengthened accordingly: `commercial_use` false requires the
  `noncommercial` type, `modification` false and `same_license` true each contradict
  `permissive`. 86 records were re-repaired under these rules, and compatibility
  descriptors on retyped records no longer describe them as permissive.

### Added

**A corpus-level quality gate**
- Per-record validation cannot see that a whole dataset is templated, which is exactly how
  years of fabricated records shipped: each record was individually well formed.
  `scripts/corpus_quality.py` fails when decision fields are uniform across the corpus or
  when any record matches a known fallback fingerprint, and runs in the sync workflow on
  full regenerations.

**A `no_derivatives` license type**
- NoDerivatives licenses permit verbatim redistribution, including commercially, but
  forbid distributing modified versions. They sat in `permissive` with
  `modification: false`, which the category approval rule blessed for commercial
  distribution without surfacing the restriction. The bundled policy flags them for a
  human to confirm the component is unmodified.

**A `noncommercial` license type**
- Licences that permit use, modification and redistribution but withhold commercial use had
  no honest category. `permissive` is a contradiction, `source_available` describes source
  visibility, and `proprietary` means all rights reserved. Because policy rules match on
  `license_type`, leaving them in `permissive` is what let a permissive-allow rule approve
  them for commercial distribution.
- ShareAlike licences still typed `permissive` were moved to `copyleft_weak`, since a
  share-alike term binds derivative works.

### Changed

**CI coverage now actually runs**
- `pytest-cov` was installed and `coverage.xml` was uploaded to Codecov, but no `--cov`
  flag was ever passed, so the file was never written and the upload silently did nothing.
  This is why coverage being pointed at the `osslili` package went unnoticed for so long,
  and why an earlier README could claim full coverage.
- The test job now passes `--cov=ospac` with terminal and XML reports. A `codecov.yml`
  marks both the project and patch statuses as informational, so coverage is reported and
  commented but can never fail a pull request. Enforcing a target remains a separate
  decision. Coverage measures 54% in CI. It reads higher on a developer machine that has
  the optional LLM SDKs installed, because the pipeline modules then take import branches
  the runner does not, so the CI figure is the one to trust.

## [1.3.0] - 2026-08-11

This release repairs a group of defects left behind by the v1.2.0 migration from YAML to
JSON. That migration updated the dataset layout and the main evaluation paths, but several
peripheral code paths kept reading the old schema and the old file locations. The most
serious of them caused policy evaluation to fail open.

Minor rather than patch, because the fail-open fix changes evaluation outcomes: a policy
that previously returned `allow` may now correctly return `deny`, so builds that passed on
1.2.11 can legitimately start failing.

### Fixed

**Policy templates matched nothing and approved everything (fail-open)**
- Policies created by `ospac policy init` match on `license_type`, but `ospac evaluate`
  never placed `license_type` in the evaluation context. Rules naming an absent context
  field are skipped, so every generated template matched no rules and returned `allow`.
- A mobile policy written to deny GPL therefore approved GPL. The result was permissive
  rather than an error, so nothing surfaced the problem in CI.
- `evaluate` now resolves each license's type from the dataset, and `license_type` matching
  accepts any evaluated license, mirroring the existing behaviour of the `license` key.
  Evaluating several licenses at once involves more than one type, so a single scalar could
  not express the case.
- `check_compatibility()` was missing the same context field and can now drive
  `license_type` rules.

**Crash on `action: review`**
- The bundled enterprise policy and the desktop and server templates use `action: review`,
  but `ActionType` defines only `FLAG_FOR_REVIEW`, so `ActionType["REVIEW"]` raised
  `KeyError` and the CLI exited with `Error: 'REVIEW'`. `review` is now accepted as
  shorthand for `flag_for_review`. The fail-open bug had prevented those rules from ever
  firing, which is why the crash was never observed.

**`ospac data validate` could not validate the shipped dataset**
- It looked only for `licenses/spdx/*.yaml`, the pre-1.2.0 layout, which no longer ships,
  and always exited with `SPDX directory not found`. It now validates the JSON dataset,
  defaults to the packaged data directory, and supports `--strict`.

**`ospac data show -f text` printed empty output**
- The text formatter read `category`, `permissions` and `conditions`, which the JSON schema
  renamed to `type`, `properties` and `requirements`, so it printed `Category: None` and
  empty sections. It now shows type, permissions, conditions, limitations, obligations, key
  requirements and SPDX metadata, marks deprecated identifiers, and renders false booleans
  visibly instead of omitting them. JSON and YAML output are unchanged.

**`PolicyRuntime.get_obligations()` always returned an empty dict**
- It read `obligations` from the top level of a record that wraps its contents in a
  `license` key, so the lookup always missed.

**Obligation enrichment never ran for installed users**
- `_enhance_result_with_obligations()` resolved a working-directory-relative `data/` path
  instead of the packaged data directory, so it silently did nothing unless the process
  happened to run beside a `data/` folder. It now resolves through
  `PolicyRuntime.resolve_data_dir()`.

**Aggregated requirements were not reproducible**
- `PolicyResult.aggregate()` deduplicated through a set, so `requirements` came back in a
  different order on every run, which broke diffing evaluation output and storing it as
  compliance evidence. Deduplication now preserves first-seen order.

**Incorrect command name in a hint**
- The default-policy notice suggested `ospac init`, which does not exist. It now says
  `ospac policy init`.

**Six LGPL identifiers were classified as strong copyleft**
- `LGPL-2.0`, `LGPL-2.0+`, `LGPL-2.1`, `LGPL-2.1+`, `LGPL-3.0` and `LGPL-3.0+` were typed
  `copyleft_strong`, while the modern identifiers they are deprecated aliases of
  (`LGPL-2.0-only`, `LGPL-2.1-only` and so on) were correctly `copyleft_weak`. An alias must
  classify identically to the identifier it aliases, so these were wrong.
- The correction table in the data pipeline already declared LGPL as weak copyleft, but
  listed only the modern spellings, so the deprecated ones kept the misclassification. Those
  bare spellings are also the ones that appear most often in real package metadata.
- Consequence: policy rules matching `license_type: copyleft_strong` denied these
  identifiers where the modern spelling was only flagged for review. The `desktop` and
  `server` templates denied `LGPL-2.1` and reviewed `LGPL-3.0-only`, which are the same
  obligation in practice.
- This was inert until the `license_type` fix above, because no rule matching on
  `license_type` ever fired. Fixing evaluation made the data defect start affecting
  decisions, so both are fixed together.
- `type` and the derived `key_requirements` are corrected in the six records and in
  `index.json`, the aliases are added to the pipeline's correction table so regeneration
  keeps them, and a test asserts the invariant directly against the shipped dataset for
  every deprecated alias, not just LGPL.

### Changed

- `__version__` is read from installed package metadata, making `pyproject.toml` the single
  source of truth. The SPDX sync workflow bumps only `pyproject.toml`, so the previous
  hardcoded literal fell behind every month, and `ospac --version` and `ospac.__version__`
  could disagree.
- License record validation moved into `ospac.utils.data_validation`, shared by the
  `data validate` command and `scripts/validate_data.py` instead of being duplicated.
- Coverage configuration pointed at the `osslili` package rather than `ospac`. The dead
  `[tool.pytest.ini_options]` block in `pyproject.toml`, shadowed by `pytest.ini`, was
  removed so there is one source of truth.
- `MANIFEST.in` referenced a nonexistent `ospac/ospac/data` path and an `obligations`
  directory that does not exist, and omitted the dataset's CC BY-NC-SA notice.

### Added

- `tests/test_cli.py`, the first CLI-level tests in the project. The absence of any test
  exercising the CLI's own context construction is what allowed the fail-open defect to
  ship with a green suite: the existing tests hand-build contexts that already contain
  `license_type`, so nothing covered the code that has to derive it.
- Documentation site at https://semclone.github.io/ospac/ built from `docs/`.

## [1.2.6] - 2026-01-28

### Fixed

**License Data Lookup**
- Fixed incorrect file path in `PolicyRuntime.lookup_license_data()` method
- License JSON files are now correctly loaded from `./data/licenses/json/` directory
- Resolves issue where license data lookups were failing due to incorrect path construction
- Aligns runtime engine with the actual directory structure used throughout the codebase

## [1.2.5] - 2026-01-15

### Security

**Path Traversal Vulnerability Fix (CVE-TBD)**
- **Critical**: Fixed path traversal vulnerability in license ID input validation (CWE-22)
- Added comprehensive input validation to prevent arbitrary file reads via malicious license IDs
- Vulnerability allowed attackers to read arbitrary JSON files by exploiting unchecked `license_id` parameters
- Attack examples: `ospac obligations -l "../../../etc/passwd"`, `ospac data show "../../secrets/api_keys"`

**Affected Components (Fixed)**
- `PolicyRuntime.lookup_license_data()` - Core license data lookup function
- `ospac data show` CLI command - License information display
- `ospac obligations` CLI command - License obligation retrieval
- `ospac evaluate` CLI command - Policy evaluation with obligations
- All functions using `license_id` to construct file paths

**Security Measures Implemented**
- Created `ospac.utils.validation` module with security-focused input validation
- `validate_license_id()`: Validates SPDX license identifier format
  - Rejects path separators (`/`, `\`)
  - Blocks relative path components (`.`, `..`, `./`, `../`)
  - Enforces alphanumeric start character
  - Allows only: `A-Z`, `a-z`, `0-9`, `.`, `-`, `+`
- `validate_license_path()`: Defense-in-depth path verification to ensure resolved paths stay within base directory
- Applied validation to all 7 user-facing code paths accepting license ID input
- Added path resolution checks to prevent symlink-based directory escapes

**Test Coverage**
- Added 12 comprehensive security tests covering:
  - Path traversal attack prevention
  - Invalid character rejection
  - Relative path component blocking
  - Symlink escape protection
  - Integration tests for all vulnerable code paths
- All 59 existing tests continue passing (zero regressions)

**Impact**
- **Severity**: Medium (arbitrary file read limited to .json files)
- **CVSS v3.1 Estimate**: 5.3 (AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N)
- **Affected versions**: All versions prior to 1.2.5
- **Fixed in**: 1.2.5
- **Credit**: Internal security review

### Fixed

**Input Validation**
- License IDs now properly validated against SPDX identifier format across all CLI commands
- Invalid license IDs produce clear error messages instead of attempting file operations
- Enhanced error handling for malformed input

**Code Quality**
- Centralized input validation logic in dedicated utility module
- Improved code maintainability with reusable validation functions
- Added comprehensive docstrings with security considerations

## [1.2.3] - 2025-11-10

### Added

**Policy Format Support**
- Added `--format` option to `ospac policy init` command supporting both YAML and JSON output
- Default output filename now automatically uses selected format extension
- JSON policy format fully supported for all policy operations and evaluations

### Changed

**Policy Templates - Enhanced Copyleft Restrictions**
- Updated all policy templates with more consistent and strict copyleft handling
- Strong copyleft licenses (GPL, AGPL) now set to `deny` across all templates
- Weak copyleft licenses (LGPL) handling improved:
  - Mobile template: LGPL now `deny` (app store compliance)
  - Embedded template: LGPL now `deny` (device distribution complexity)
  - Web template: LGPL changed from `review` to `deny` (compliance simplification)
  - Library template: LGPL changed from `review` to `deny` (user restriction prevention)
  - Desktop template: LGPL remains `review` (dynamic linking flexibility)
  - Server template: LGPL remains `review` (backend service flexibility)
- Permissive licenses (MIT, Apache-2.0, BSD) remain `approve` in all templates
- Added comprehensive remediation messages for all denied licenses

**Policy Command Improvements**
- Policy init command now generates format-appropriate output files
- Enhanced validation to work seamlessly with both YAML and JSON formats
- Improved consistency across all policy template rules

## [1.2.2] - 2025-11-07

### Fixed

**Data Show Command**
- Fixed `ospac data show` command to use package data directory instead of relative path
- Command now works correctly regardless of current working directory
- Added JSON file support as primary data source with YAML fallback
- Improved error messages when license is not found

## [1.2.1] - 2025-11-07

### Fixed

**Package Data Distribution**
- Fixed data files not being included in installed package
- Moved data directory from `ospac/data/` to `ospac/ospac/data/` to ensure proper packaging
- Updated all code paths to use package-relative data directory paths instead of relative to current working directory
- CLI commands now work correctly regardless of which directory the tool is run from
- Updated MANIFEST.in to reflect new data location

**Code Improvements**
- Updated `ospac.cli.commands` to use `Path(__file__).parent.parent / "data"` for data resolution
- Updated `ospac.runtime.engine.PolicyRuntime.get_obligations()` to use package-relative paths
- Updated `ospac.core.compatibility_matrix.CompatibilityMatrix` to use package-relative paths
- Made data_dir parameter optional (defaults to None) across all affected functions

## [1.2.0] - 2024-11-06

### Added

**JSON Dataset Format**
- Migrated license dataset from YAML to JSON format for improved parsing reliability
- Added comprehensive JSON schema validation for license data structure
- Enhanced data loading performance and reduced parsing errors
- Support for 712 SPDX licenses in structured JSON format with complete metadata

**Enhanced Data Structure**
- Complete license information including properties, requirements, limitations, and obligations
- Detailed compatibility matrices for static and dynamic linking scenarios
- Comprehensive obligation tracking with license-specific requirements
- Structured contamination effect and compatibility notes

**Improved API Integration**
- JSON-first design optimized for MCP (Model Context Protocol) integration
- Clean, machine-readable output perfect for external system consumption
- Backward compatibility with YAML fallback for legacy support
- Enhanced library API for programmatic usage

### Changed

**Dataset Architecture**
- Primary license data format changed from YAML to JSON
- Reduced dataset size from 5.6MB to 2.8MB (50% reduction)
- Eliminated duplicate data structures and simplified maintenance
- Streamlined file structure for better package distribution

**Policy Evaluation Enhancement**
- Fixed policy aggregation to preserve remediation and requirements data
- Added comprehensive license obligations to policy evaluation results
- Improved compatibility checking with explicit incompatible license pairs
- Enhanced mobile/embedded distribution recognition in default policy

**Test Coverage**
- Achieved 100% test success rate with comprehensive validation suite
- Added dataset integrity validation for all 712 license files
- Enhanced CLI command testing across all options and scenarios
- Improved library API testing for external system integration

### Fixed
- Resolved GPL-2.0 + Apache-2.0 compatibility checking issue
- Fixed missing remediation data in policy aggregation results
- Corrected empty requirements field for denied licenses
- Enhanced mobile distribution type recognition in default policies
- Improved error handling for edge cases in license data loading

### Technical Improvements
- Added JSON schema for license data validation
- Implemented fallback mechanism from JSON to YAML for compatibility
- Enhanced data loading with proper error handling and validation
- Optimized file structure and removed redundant datasets
- Improved package size and distribution efficiency

## [1.1.5] - 2025-11-05

### Added

**Default Enterprise Policy**
- Embedded comprehensive default enterprise policy for immediate use without configuration
- Automatic policy loading when no custom policy is specified
- Default policy includes rules for GPL, AGPL, LGPL, permissive licenses, and public domain
- Support for different distribution types: commercial, SaaS, embedded, internal
- Context-aware evaluation for static vs dynamic linking

**CLI Enhancements**
- Added detailed examples to all CLI commands via help text
- New `-o/--output` option for `check` command supporting JSON and text formats
- Improved main help text with common use cases
- User notification when using default policy (in text output mode)

### Changed

**Output Format**
- JSON is now the default output format for all commands (previously text)
- Consistent JSON structure across all commands for better programmatic parsing
- Added `using_default_policy` field to JSON output for transparency
- Proper serialization of enums and complex types in JSON output

**Policy Loading**
- Modified PolicyRuntime to automatically load default policy when:
  - No policy directory is specified
  - Specified directory doesn't exist
  - Policy directory is empty
- Package now includes embedded default policy file in `ospac/defaults/`

### Fixed
- Improved rule matching logic for license evaluation
- Fixed JSON serialization errors with ActionType enums
- Enhanced context handling for linking types and distribution modes

## [1.1.0] - 2025-11-05

### Added

**Dual Licensing Implementation**
- Introduced dual licensing structure for the project
- Added CC BY-NC-SA 4.0 license for the OSPAC license database
- Created DATA_LICENSE file with full Creative Commons license text
- Added LICENSE file to ospac/data/ directory for clarity

### Changed

**License Structure**
- Software code remains under Apache-2.0 license
- License database now protected under CC BY-NC-SA 4.0 for non-commercial use only
- Updated README with comprehensive dual licensing explanation
- Clear separation between software and data licensing terms

### Documentation
- Enhanced README license section with detailed breakdown of dual licensing
- Added guidance for commercial vs non-commercial usage
- Clarified attribution and share-alike requirements for database usage

## [1.0.4] - 2025-11-04

### Fixed

**CLI Command Improvements**
- Fixed `ospac obligations` command returning no output
- Corrected policy loader integration for obligation data retrieval
- Updated get_obligations method to properly traverse nested policy structure
- Resolved obligation policy path resolution for CLI commands

**GitHub Actions Workflow**
- Removed duplicate release workflow causing PyPI publishing conflicts
- Consolidated to standard python-publish.yml workflow
- Fixed action errors during release process

### Changed

**Internal Architecture**
- Improved PolicyRuntime obligation handling for nested policy files
- Enhanced policy loader to correctly map obligation policies
- Standardized workflow configuration to prevent CI/CD conflicts

## [1.0.3] - 2025-11-04

### Fixed

**Critical Data Quality Corrections**
- Fixed systematic license limitation value errors across all 712 SPDX licenses
- Corrected liability and warranty limitation semantics (false = license disclaims, not provides)
- Fixed Apache-2.0 license classification as permissive (removed incorrect copyleft requirements)
- Corrected MIT license patent grant status (false, as MIT provides no explicit patent grant)
- Fixed Apache-2.0 patent grant status (true, as Apache-2.0 provides explicit patent grants)

**Data Generation Pipeline Improvements**
- Fixed fallback analysis methods in LLM analyzer and provider modules
- Improved LLM prompt clarity for limitation field semantics
- Enhanced license-specific handling for Apache, MIT, GPL, LGPL, and AGPL families
- Standardized copyleft vs permissive license requirement patterns

**AGPL License Data Corrections**
- Fixed inconsistent license compatibility data across all AGPL license variants
- Corrected AGPL-3.0.yaml incompatible licenses list (MIT-LICENSED → MIT)
- Fixed AGPL-3.0-or-later.yaml limitation values and same_license requirements
- Updated contamination_effect values for strong copyleft licenses (module → full)
- Standardized incompatible license naming (Proprietary → proprietary)

**Database Integrity**
- Regenerated complete license database with corrected pipeline logic
- Ensured consistent data structure and semantics across all license definitions
- Maintained compatibility with existing CLI functionality and policy evaluation
- Verified all 712 SPDX licenses have accurate legal metadata

### Technical Details
- Root cause identified in fallback analysis methods with incorrect default values
- Fixed semantic interpretation of limitation fields in license analysis
- Improved license categorization logic for permissive vs copyleft licenses
- Enhanced compatibility matrix generation with corrected license relationships

## [1.0.2] - 2025-11-04

### Added
- Complete SPDX license database coverage (712/712 licenses)
- All Apache family licenses now included (Apache-1.0, Apache-1.1, Apache-2.0)
- Enhanced data generation process for comprehensive license coverage

### Fixed
- Critical issue where Apache-2.0 and other licenses were missing from the main database
- Data generation process bug that excluded previously processed licenses from master database
- YAML format conversion issues between individual license files and database generation
- Database completeness ensuring all 712 SPDX licenses are accessible via CLI

### Changed
- Updated data generation flow to include all processed licenses instead of incremental updates only
- Improved license database structure to support complete SPDX license set
- Enhanced compatibility checking to work with full license catalog

### Technical Details
- Fixed `ospac/pipeline/data_generator.py` to use all analyzed licenses in master database generation
- Added `_convert_yaml_format()` function to transform YAML license data to expected database format
- Updated database from 638 to 712 licenses with complete metadata and compatibility rules

## [1.0.1] - 2025-11-05

### Added
- Package now includes all default data files in distribution
  - 700+ SPDX license files
  - Compatibility matrices and relationships
  - Pre-generated obligation database
- MANIFEST.in for proper source distribution packaging

### Changed
- Data directory moved to `ospac/data/` for wheel distribution compatibility
- Updated pyproject.toml with comprehensive package-data configuration

### Fixed
- Default data now ships with PyPI package installation
- Users can use the tool immediately without generating data first

## [0.1.0] - 2025-11-04

### Added
- Initial release of OSPAC - Open Source Policy as Code engine
- Core features:
  - Policy-as-code framework for OSS license compliance
  - SPDX license database integration (712 licenses)
  - License compatibility checking system
  - Obligation tracking and enforcement
  - CLI tool for policy evaluation

- Data generation pipeline:
  - SPDX license processor
  - LLM-enhanced analysis support (OpenAI, Ollama)
  - Compatibility matrix generation
  - Split matrix architecture for efficient storage

- Runtime engine:
  - YAML-based policy definitions
  - Rule evaluation system
  - Context-aware compliance checking
  - Decision tree support

- CLI commands:
  - `ospac evaluate` - Evaluate licenses against policies
  - `ospac check-compat` - Check compatibility between licenses
  - `ospac data generate` - Generate license database
  - `ospac data show` - Display license information
  - `ospac data download-spdx` - Download SPDX dataset

### Technical Details
- Python 3.9+ support
- Async/await architecture for LLM operations
- Efficient sparse matrix storage for compatibility data
- Comprehensive test suite (52 tests)
- GitHub Actions CI/CD pipeline

### Known Issues
- 13 SPDX licenses return 404 from API (fallback data provided)
- LLM analysis optional but recommended for enhanced accuracy

[1.2.5]: https://github.com/SemClone/ospac/releases/tag/v1.2.5
[1.2.3]: https://github.com/SemClone/ospac/releases/tag/v1.2.3
[1.2.2]: https://github.com/SemClone/ospac/releases/tag/v1.2.2
[1.2.1]: https://github.com/SemClone/ospac/releases/tag/v1.2.1
[1.2.0]: https://github.com/SemClone/ospac/releases/tag/v1.2.0
[1.1.5]: https://github.com/SemClone/ospac/releases/tag/v1.1.5
[1.1.0]: https://github.com/SemClone/ospac/releases/tag/v1.1.0
[1.0.4]: https://github.com/SemClone/ospac/releases/tag/v1.0.4
[1.0.3]: https://github.com/SemClone/ospac/releases/tag/v1.0.3
[1.0.2]: https://github.com/SemClone/ospac/releases/tag/v1.0.2
[1.0.1]: https://github.com/SemClone/ospac/releases/tag/v1.0.1
[0.1.0]: https://github.com/SemClone/ospac/releases/tag/v0.1.0