"""
Pins the published data export contract.

docs/data-contract.md tells consumers which files and fields they may rely on and
promises that nothing there disappears without a major version bump. A promise with
no test behind it is a comment, so every field named in that document is asserted
here. If one of these fails, either the removal is intentional and the contract needs
a major bump and a documented deprecation, or it is the accident this file exists to
catch.

Field lists are duplicated from the doc on purpose. Deriving them from the data would
assert only that the data equals itself.
"""

import json
from pathlib import Path

import jsonschema
import pytest

import ospac
from ospac.dataset import DATA_SCHEMA_VERSION
from ospac.utils.data_validation import VALID_CONTAMINATION, VALID_TYPES

DATA_DIR = Path(ospac.__file__).parent / "data"
SCHEMA_FILE = Path(__file__).parent.parent / "schemas" / "license_schema.json"

INDEX_KEYS = {"version", "generated", "spdx_list_version", "total_licenses", "licenses"}
INDEX_RECORD_KEYS = {"name", "category", "file", "is_deprecated", "obligations_count"}
ALIASES_KEYS = {"version", "spdx_list_version", "aliases", "ambiguous", "never_resolve"}
COMPAT_METADATA_KEYS = {"version", "generated", "total_licenses", "format",
                        "default_status", "statuses"}
LICENSE_RECORD_KEYS = {
    "id", "name", "type", "spdx_id", "properties", "requirements", "limitations",
    "compatibility", "obligations", "key_requirements", "aliases", "alias_of",
    "spdx_metadata", "generated", "spdx_list_version",
}


def _load(*parts):
    with open(DATA_DIR.joinpath(*parts)) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def index():
    return _load("index.json")


@pytest.fixture(scope="module")
def aliases_payload():
    return _load("aliases.json")


@pytest.fixture(scope="module")
def license_schema():
    with open(SCHEMA_FILE) as f:
        return json.load(f)


class TestPublicFiles:
    """The four published files exist where the contract says they do."""

    @pytest.mark.parametrize("relative", [
        "index.json",
        "aliases.json",
        "compatibility/metadata.json",
        "compatibility/categories.json",
    ])
    def test_file_is_present(self, relative):
        assert (DATA_DIR / relative).is_file(), f"published file missing: {relative}"

    def test_relationships_directory_is_populated(self):
        relationships = sorted((DATA_DIR / "compatibility" / "relationships").glob("*.json"))
        assert relationships, "compatibility/relationships is empty"

    def test_every_family_in_categories_has_a_relationship_file(self):
        categories = _load("compatibility", "categories.json")
        relationships = {p.stem for p in
                         (DATA_DIR / "compatibility" / "relationships").glob("*.json")}
        assert set(categories) <= relationships, (
            f"families with no relationship file: {sorted(set(categories) - relationships)}")


class TestIndex:
    def test_top_level_keys(self, index):
        assert set(index) == INDEX_KEYS

    def test_record_keys(self, index):
        offenders = [lid for lid, entry in index["licenses"].items()
                     if set(entry) != INDEX_RECORD_KEYS]
        assert not offenders, f"index record surface changed: {offenders[:5]}"

    def test_total_licenses_matches_the_map(self, index):
        assert index["total_licenses"] == len(index["licenses"])

    def test_every_indexed_file_exists(self, index):
        missing = [entry["file"] for entry in index["licenses"].values()
                   if not (DATA_DIR / entry["file"]).is_file()]
        assert not missing, f"index points at absent files: {missing[:5]}"

    def test_category_is_the_documented_domain(self, index):
        categories = {entry["category"] for entry in index["licenses"].values()}
        assert categories <= VALID_TYPES, f"undocumented categories: {categories - VALID_TYPES}"


class TestAliases:
    def test_top_level_keys(self, aliases_payload):
        assert set(aliases_payload) == ALIASES_KEYS

    def test_accessors_read_the_published_keys(self, aliases_payload):
        assert ospac.license_aliases() == aliases_payload["aliases"]
        assert ospac.license_ambiguous() == aliases_payload["ambiguous"]
        assert ospac.license_never_resolve() == set(aliases_payload["never_resolve"])

    def test_aliases_resolve_to_indexed_ids(self, aliases_payload, index):
        unknown = sorted({v for v in aliases_payload["aliases"].values()
                          if v not in index["licenses"]})
        assert not unknown, f"aliases resolve to ids absent from the index: {unknown[:5]}"

    def test_ambiguous_candidates_are_indexed_ids(self, aliases_payload, index):
        unknown = sorted({i for ids in aliases_payload["ambiguous"].values()
                          for i in ids if i not in index["licenses"]})
        assert not unknown, f"ambiguous names offer ids absent from the index: {unknown[:5]}"

    def test_ambiguous_always_offers_a_choice(self, aliases_payload):
        # One candidate is not an ambiguity, it is an alias. A consumer reporting
        # "could be X" for a single X has been handed a resolution in the wrong field.
        thin = {n: ids for n, ids in aliases_payload["ambiguous"].items() if len(ids) < 2}
        assert not thin, f"ambiguous entries with fewer than two candidates: {thin}"

    def test_the_three_tables_do_not_overlap(self, aliases_payload):
        # Each string gets exactly one answer: an id, a choice, or nothing. A string in
        # two tables makes the answer depend on which one the consumer reads first.
        aliases = set(aliases_payload["aliases"])
        ambiguous = set(aliases_payload["ambiguous"])
        never = set(aliases_payload["never_resolve"])
        assert not aliases & ambiguous, sorted(aliases & ambiguous)[:5]
        assert not aliases & never, sorted(aliases & never)[:5]
        assert not ambiguous & never, sorted(ambiguous & never)[:5]


class TestCompatibilityMetadata:
    def test_top_level_keys(self):
        assert set(_load("compatibility", "metadata.json")) == COMPAT_METADATA_KEYS

    def test_interned_format_and_unknown_default_are_still_the_contract(self):
        metadata = _load("compatibility", "metadata.json")
        # A consumer that treats an absent pair as compatible is wrong, and the doc
        # says so. If either value ever changes, that reasoning changes with it.
        assert metadata["format"] == "interned"
        assert metadata["default_status"] == "unknown"


class TestCompatibilityRelationships:
    """
    The contract describes the pair store's shape, so the shape is pinned.

    Not its size. `relationships/` is a full 733x733 enumeration today because no pair
    resolves to `unknown`, and asserting the pair count would fail on the first monthly
    refresh that adds a license. The doc says as much and quotes the number as an
    observation rather than a promise.
    """

    @pytest.fixture(scope="class")
    def relationships(self):
        loaded = {}
        for path in sorted((DATA_DIR / "compatibility" / "relationships").glob("*.json")):
            with open(path) as f:
                loaded[path.stem] = json.load(f)
        return loaded

    def test_pairs_use_the_three_documented_contexts(self, relationships):
        statuses = _load("compatibility", "metadata.json")["statuses"]
        found = {frozenset(status) for status in statuses}
        expected = {frozenset({"static_linking", "dynamic_linking", "distribution"})}
        assert found == expected, f"pair context keys changed: {[sorted(k) for k in found]}"

    def test_every_pair_is_an_index_into_the_status_table(self, relationships):
        statuses = _load("compatibility", "metadata.json")["statuses"]
        for family, tree in relationships.items():
            for source, targets in tree.items():
                for target, stored in targets.items():
                    assert isinstance(stored, int) and not isinstance(stored, bool), (
                        f"{family}: {source} -> {target} is {type(stored).__name__}, "
                        f"not an index")
                    assert 0 <= stored < len(statuses), (
                        f"{family}: {source} -> {target} indexes outside the table")

    def test_the_store_has_not_degenerated_back_to_writing_each_pair_out(
            self, relationships):
        """
        The pairs are a complete 733x733 enumeration, because the one compaction rule
        was to omit a pair resolving to `unknown` and no pair ever does. That is fine
        while a pair costs an index; it cost 76 MB when each one was written out in
        full, of which other.json alone was 59 MB.

        The number of pairs is not asserted, because it grows with every SPDX refresh.
        What is asserted is that they stay indexes into a table far smaller than they
        are, which is the property that made the size collapse.
        """
        statuses = _load("compatibility", "metadata.json")["statuses"]
        pairs = sum(len(targets) for tree in relationships.values()
                    for targets in tree.values())

        assert len(statuses) < 100, (
            f"{len(statuses)} distinct statuses: the table is meant to be the few "
            f"values the pairs actually take")
        assert pairs > len(statuses) * 100, (
            "far fewer pairs than expected per distinct status, which is what a store "
            "writing each pair out in full would look like")

        installed = sum(path.stat().st_size for path in
                        (DATA_DIR / "compatibility" / "relationships").glob("*.json"))
        assert installed < 40_000_000, (
            f"relationships/ is {installed / 1e6:.0f} MB; it was 76 MB when each pair "
            f"carried its own status object and 9 MB after they became indexes")

    def test_distribution_context_is_unique_to_the_pair_store(self):
        # The doc warns that the pair rules carry a third context the per-license record
        # does not. If any record grows one, that warning becomes misleading, so this
        # checks all of them rather than a sample.
        offenders = []
        for path in sorted((DATA_DIR / "licenses" / "json").glob("*.json")):
            with open(path) as f:
                if "distribution" in json.load(f)["license"]["compatibility"]:
                    offenders.append(path.name)
        assert not offenders, f"records grew a distribution context: {offenders[:5]}"

    def test_sources_and_targets_are_indexed_ids(self, relationships, index):
        referenced = set()
        for family in relationships.values():
            referenced |= set(family)
            for targets in family.values():
                referenced |= set(targets)
        unknown = sorted(referenced - set(index["licenses"]))
        assert not unknown, f"pair store references unindexed ids: {unknown[:5]}"


class TestDeprecationPointers:
    def test_non_null_alias_of_always_resolves(self, index):
        # The contract promises that `alias_of`, when present, resolves. It deliberately
        # does not promise `alias_of` is non-null on a deprecated record, because 15 of
        # them are null: SPDX replaced those ids with something other than one plain id.
        dangling = []
        for path in sorted((DATA_DIR / "licenses" / "json").glob("*.json")):
            with open(path) as f:
                record = json.load(f)["license"]
            target = record["alias_of"]
            if target is not None and target not in index["licenses"]:
                dangling.append(f"{record['id']} -> {target}")
        assert not dangling, f"alias_of points at unindexed ids: {dangling[:5]}"

    def test_aliases_is_empty_exactly_when_alias_of_is_set(self):
        # The normative schema states this as a biconditional, so it is pinned as one.
        # Stating it against `is_deprecated` instead would be wrong: 15 deprecated
        # records have `alias_of: null` and keep their own spellings, because SPDX
        # replaced them with something other than one plain id to move them to.
        offenders = []
        for path in sorted((DATA_DIR / "licenses" / "json").glob("*.json")):
            with open(path) as f:
                record = json.load(f)["license"]
            has_target = record["alias_of"] is not None
            is_empty = not record["aliases"]
            if has_target != is_empty:
                offenders.append(
                    f"{record['id']}: alias_of={record['alias_of']!r} "
                    f"aliases={len(record['aliases'])}")
        assert not offenders, "aliases/alias_of correlation broke:\n" + "\n".join(offenders[:10])

    def test_alias_of_is_null_or_a_string(self):
        for path in sorted((DATA_DIR / "licenses" / "json").glob("*.json")):
            with open(path) as f:
                record = json.load(f)["license"]
            assert record["alias_of"] is None or isinstance(record["alias_of"], str), path.name


class TestSchemaVersion:
    def test_all_published_files_carry_the_same_schema_version(self, index, aliases_payload):
        metadata = _load("compatibility", "metadata.json")
        assert index["version"] == DATA_SCHEMA_VERSION
        assert aliases_payload["version"] == DATA_SCHEMA_VERSION
        assert metadata["version"] == DATA_SCHEMA_VERSION

    def test_version_is_a_three_part_string(self):
        # Not a float, and not a two-part string: "1.10" sorts below "1.9" under both,
        # which is the hazard the documented scheme exists to remove.
        assert isinstance(DATA_SCHEMA_VERSION, str)
        parts = DATA_SCHEMA_VERSION.split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts)

    def test_data_version_reports_the_index_metadata(self, index):
        reported = ospac.data_version()
        assert reported.schema_version == index["version"]
        assert reported.generated == index["generated"]
        assert reported.spdx_list_version == index["spdx_list_version"]
        assert reported.total_licenses == index["total_licenses"]

    def test_schema_version_info_compares_numerically(self):
        # Derived from the constant, not a literal: the point of the test is that the
        # parts are integers, and a literal here fails on every legitimate bump.
        expected = tuple(int(part) for part in DATA_SCHEMA_VERSION.split("."))
        assert ospac.data_version().schema_version_info == expected
        assert (1, 9, 0) < (1, 10, 0)  # the ordering the string form gets wrong


class TestLicenseRecordSchema:
    """`schemas/license_schema.json` is normative, so it has to match the data."""

    def test_schema_type_enum_tracks_the_validation_rules(self, license_schema):
        enum = license_schema["properties"]["license"]["properties"]["type"]["enum"]
        assert set(enum) == VALID_TYPES, "schema type enum drifted from VALID_TYPES"

    def test_schema_contamination_enum_tracks_the_validation_rules(self, license_schema):
        compatibility = license_schema["properties"]["license"]["properties"]["compatibility"]
        enum = compatibility["properties"]["contamination_effect"]["enum"]
        assert set(enum) == VALID_CONTAMINATION, "schema drifted from VALID_CONTAMINATION"

    def test_schema_requires_every_documented_field(self, license_schema):
        required = license_schema["properties"]["license"]["required"]
        assert set(required) == LICENSE_RECORD_KEYS

    def test_schema_itself_is_valid_draft_07(self, license_schema):
        jsonschema.Draft7Validator.check_schema(license_schema)

    def test_every_shipped_record_validates(self, license_schema):
        validator = jsonschema.Draft7Validator(license_schema)
        failures = []
        for path in sorted((DATA_DIR / "licenses" / "json").glob("*.json")):
            with open(path) as f:
                record = json.load(f)
            for error in validator.iter_errors(record):
                failures.append(f"{path.name}: {error.message}")
        assert not failures, "records violate the normative schema:\n" + "\n".join(failures[:10])

    def test_every_record_has_exactly_the_documented_keys(self):
        # The schema deliberately allows extra fields so an additive minor release does
        # not break consumer validation. This asserts the actual surface, so a silent
        # addition or removal still fails here and forces a contract decision.
        offenders = []
        for path in sorted((DATA_DIR / "licenses" / "json").glob("*.json")):
            with open(path) as f:
                wrapper = json.load(f)
            if set(wrapper) != {"license"}:
                offenders.append(f"{path.name}: wrapper keys {sorted(wrapper)}")
                continue
            keys = set(wrapper["license"])
            if keys != LICENSE_RECORD_KEYS:
                added = sorted(keys - LICENSE_RECORD_KEYS)
                removed = sorted(LICENSE_RECORD_KEYS - keys)
                offenders.append(f"{path.name}: added={added} removed={removed}")
        assert not offenders, "record surface changed:\n" + "\n".join(offenders[:10])


class TestPythonSurface:
    def test_documented_names_are_exported(self):
        for name in ("PolicyRuntime", "License", "Policy", "ComplianceResult",
                     "license_aliases", "license_ambiguous", "license_never_resolve",
                     "data_version",
                     "DataVersion", "DATA_SCHEMA_VERSION"):
            assert name in ospac.__all__, f"{name} dropped from ospac.__all__"
            assert hasattr(ospac, name)

    def test_data_version_is_immutable(self):
        reported = ospac.data_version()
        with pytest.raises(Exception):
            reported.schema_version = "9.9.9"


class TestPropertiesTheResolutionPathRelieson:
    """
    Two facts about the shipped data that code elsewhere assumes and nothing checked.
    Both were verified by hand while fixing the resolution path, which is exactly the
    kind of assumption that stops being true on a monthly refresh with nobody looking.
    """

    def test_every_shipped_id_resolves_from_its_lowercased_spelling(self):
        import ospac

        # Callers reach a record through matchable_license_id, which returns the input
        # unchanged when the data cannot settle it. A lower-cased id therefore has to
        # resolve, or it falls through to a path built from the caller's casing and the
        # answer starts depending on whether the filesystem is case-sensitive.
        aliases = ospac.license_aliases()
        ambiguous = ospac.license_ambiguous()
        never = ospac.license_never_resolve()
        unreachable = sorted(
            license_id for license_id in ospac.dataset.known_license_ids()
            if license_id.lower() not in aliases
            or license_id.lower() in ambiguous
            or license_id.lower() in never)
        assert unreachable == [], (
            f"ids whose lowercased spelling does not resolve: {unreachable}")

    def test_no_comma_bearing_name_has_two_resolving_halves(self):
        import ospac

        # The CLI separates licenses with a comma and joins fragments back together when
        # the join names something. That is only unambiguous while no key's two halves
        # each name a license on their own; one that did would make "A, B" a coin flip
        # between one declaration and two.
        tables = dict(ospac.license_aliases())
        tables.update({name: ids for name, ids in ospac.license_ambiguous().items()})
        coin_flips = []
        for name in tables:
            if "," not in name:
                continue
            head, _, tail = name.partition(",")
            if (ospac.resolve_license(head.strip()).status != "unresolved"
                    and ospac.resolve_license(tail.strip()).status != "unresolved"):
                coin_flips.append(name)
        assert coin_flips == [], (
            f"comma-bearing names whose halves both resolve: {coin_flips}")

    def test_incompatible_with_names_every_spelling_of_the_other_licence(self):
        import json

        import ospac

        # check compares a resolved id against the incompatible_with list by exact
        # string. A record naming only one spelling of a licence that ships several
        # would let the other spelling read as clean, silently.
        data_dir = Path(__file__).parent.parent / "ospac" / "data" / "licenses" / "json"
        records = {}
        for path in data_dir.glob("*.json"):
            record = json.loads(path.read_text())["license"]
            records[record["id"]] = record

        # Ids that mean the same licence: a deprecated spelling and what it maps to.
        same = {}
        for license_id, record in records.items():
            canonical = record.get("alias_of") or license_id
            same.setdefault(canonical, set()).add(license_id)
            same[canonical].add(canonical)

        gaps = []
        for license_id, record in records.items():
            named = set((record.get("compatibility", {})
                         .get("static_linking", {}).get("incompatible_with", [])))
            for other in sorted(named):
                group = same.get(records.get(other, {}).get("alias_of") or other, set())
                missing = sorted(spelling for spelling in group
                                 if spelling in records and spelling not in named)
                if missing:
                    gaps.append((license_id, other, missing))
        assert gaps == [], f"incompatible_with lists naming only some spellings: {gaps}"


class TestTheSchemaAndTheValidatorDescribeOneRecord:
    """
    schemas/license_schema.json is normative and ospac/utils/data_validation.py is
    documented as the single source of truth for the dataset rules. Both were true of a
    different field list: the schema required requirements.include_notice and
    compatibility.notes and the validator's sets did not, so validate_data.py passed a
    record the schema then rejected. In the monthly sync that is a green gate followed by
    a red one whose message names the schema, when the fault is in the generator.

    #85 pinned the two enums to each other and left the required-key sets unpinned, which
    is why they drifted without anyone noticing.
    """

    @staticmethod
    def _required(schema, node):
        """The required keys of a node, following a $ref rather than stopping at it."""
        while "$ref" in node:
            ref = node["$ref"].lstrip("#/").split("/")
            node = schema
            for part in ref:
                node = node[part]
        return set(node.get("required", []))

    def test_required_key_sets_agree(self):
        from ospac.utils import data_validation as dv

        schema = json.loads(
            (Path(__file__).parent.parent / "schemas" / "license_schema.json").read_text())
        blocks = schema["properties"]["license"]["properties"]

        # The top level too. Comparing only the nested blocks left aliases, alias_of,
        # generated and spdx_list_version required by the schema and absent from the
        # validator, which is the same drift one level up from the one this test was
        # written for: a record missing aliases passed validate_data.py and the schema
        # rejected it.
        assert self._required(schema, schema["properties"]["license"]) == (
            dv.REQUIRED_TOP_FIELDS), (
            "top level: schema and validator disagree on which keys are required")

        for name, constant in (("properties", dv.REQUIRED_PROPERTIES),
                               ("requirements", dv.REQUIRED_REQUIREMENTS),
                               ("limitations", dv.REQUIRED_LIMITATIONS),
                               ("compatibility", dv.REQUIRED_COMPAT_KEYS),
                               ("spdx_metadata", dv.REQUIRED_SPDX_METADATA)):
            assert self._required(schema, blocks[name]) == constant, (
                f"{name}: schema and validator disagree on which keys are required")

        linking = blocks["compatibility"]["properties"]
        for context in ("static_linking", "dynamic_linking"):
            assert self._required(schema, linking[context]) == dv.REQUIRED_COMPAT_LINK_KEYS, (
                f"compatibility.{context}: schema and validator disagree")

    def test_the_ref_is_actually_followed(self):
        # The linking contexts state their required keys through a $ref. A test that read
        # the node directly would find no `required`, compare an empty set, and pass
        # while proving nothing.
        schema = json.loads(
            (Path(__file__).parent.parent / "schemas" / "license_schema.json").read_text())
        node = (schema["properties"]["license"]["properties"]["compatibility"]
                ["properties"]["static_linking"])
        assert "$ref" in node and "required" not in node
        assert self._required(schema, node) == {
            "compatible_with", "incompatible_with", "requires_review"}

    def test_a_missing_required_inner_key_is_an_error(self):
        from ospac.utils.data_validation import validate_license

        # The gate that runs first in the sync is the one that knows which license and
        # which field is at fault. Reporting it as a warning meant it said nothing, since
        # warnings do not affect the exit code without --strict.
        record = json.loads(
            (Path(__file__).parent.parent / "ospac" / "data" / "licenses" / "json"
             / "MIT.json").read_text())["license"]
        assert validate_license("MIT", record)[0] == []

        del record["requirements"]["include_notice"]
        errors = validate_license("MIT", record)[0]
        assert any("include_notice" in e for e in errors), errors

        record = json.loads(
            (Path(__file__).parent.parent / "ospac" / "data" / "licenses" / "json"
             / "MIT.json").read_text())["license"]
        del record["compatibility"]["notes"]
        errors = validate_license("MIT", record)[0]
        assert any("notes" in e for e in errors), errors
