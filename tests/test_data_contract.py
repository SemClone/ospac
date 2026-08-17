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
ALIASES_KEYS = {"version", "spdx_list_version", "aliases", "never_resolve"}
COMPAT_METADATA_KEYS = {"version", "generated", "total_licenses", "format", "default_status"}
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
        # Sampled across the alphabet rather than every record; the schema test below
        # covers all 733 license files exhaustively.
        for license_id in ("MIT", "Apache-2.0", "GPL-3.0-only", "CC-BY-NC-4.0"):
            assert set(index["licenses"][license_id]) == INDEX_RECORD_KEYS, license_id

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
        assert ospac.license_never_resolve() == set(aliases_payload["never_resolve"])

    def test_aliases_resolve_to_indexed_ids(self, aliases_payload, index):
        unknown = sorted({v for v in aliases_payload["aliases"].values()
                          if v not in index["licenses"]})
        assert not unknown, f"aliases resolve to ids absent from the index: {unknown[:5]}"


class TestCompatibilityMetadata:
    def test_top_level_keys(self):
        assert set(_load("compatibility", "metadata.json")) == COMPAT_METADATA_KEYS

    def test_sparse_format_and_unknown_default_are_still_the_contract(self):
        metadata = _load("compatibility", "metadata.json")
        # A consumer that treats an absent pair as compatible is wrong, and the doc
        # says so. If either value ever changes, that reasoning changes with it.
        assert metadata["format"] == "sparse"
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
        found = set()
        for family in relationships.values():
            for targets in family.values():
                for pair in targets.values():
                    found.add(frozenset(pair))
        expected = {frozenset({"static_linking", "dynamic_linking", "distribution"})}
        assert found == expected, f"pair context keys changed: {[sorted(k) for k in found]}"

    def test_distribution_context_is_unique_to_the_pair_store(self):
        # The doc warns that the pair rules carry a third context the per-license record
        # does not. If a record ever grows one, that warning becomes misleading.
        with open(DATA_DIR / "licenses" / "json" / "MIT.json") as f:
            compatibility = json.load(f)["license"]["compatibility"]
        assert "distribution" not in compatibility

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
        assert ospac.data_version().schema_version_info == (1, 0, 0)
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
                     "license_aliases", "license_never_resolve", "data_version",
                     "DataVersion", "DATA_SCHEMA_VERSION"):
            assert name in ospac.__all__, f"{name} dropped from ospac.__all__"
            assert hasattr(ospac, name)

    def test_data_version_is_immutable(self):
        reported = ospac.data_version()
        with pytest.raises(Exception):
            reported.schema_version = "9.9.9"
