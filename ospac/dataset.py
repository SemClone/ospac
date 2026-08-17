"""
Dataset version metadata.

The shipped JSON carries its own schema version, and a consumer pinning against
that shape needs one place to read it from and one place that says what a bump
means. Left undocumented, every consumer parses `index.json` by hand and invents
its own idea of what `version` promised, which is the same divergence the alias
table was moved into the dataset to avoid.

The contract itself is written down in docs/data-contract.md. This module is the
programmatic half of it.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

# Version of the shipped data layout, not of the ospac package. MAJOR.MINOR.PATCH:
# MAJOR for a removal or an incompatible change to a documented field, MINOR for a
# purely additive field, PATCH for a correction to the contract that does not change
# the shape. A monthly SPDX refresh changes `generated` and `spdx_list_version` and
# leaves this alone.
DATA_SCHEMA_VERSION = "1.0.0"

_INDEX_FILE = Path(__file__).parent / "data" / "index.json"


@dataclass(frozen=True)
class DataVersion:
    """
    What the bundled dataset says about itself.

    `schema_version` is the shape of the files. `spdx_list_version` is the upstream
    SPDX commit the records were built from, and `generated` is when that build ran,
    so the two provenance fields answer staleness and the schema field answers
    compatibility. They move independently and conflating them is the mistake this
    type exists to prevent.
    """

    schema_version: str
    generated: str
    spdx_list_version: str
    total_licenses: int

    @property
    def schema_version_info(self) -> Tuple[int, ...]:
        """
        `schema_version` as integers, for comparison.

        Compare on this rather than on the string. Lexicographic ordering puts
        "1.10.0" below "1.9.0", which is wrong the first time the minor version
        reaches double digits.
        """
        return tuple(int(part) for part in self.schema_version.split("."))


def data_version() -> DataVersion:
    """
    Read the bundled dataset's version metadata.

    Assert compatibility once at import rather than hoping the shape held:

        import ospac
        assert ospac.data_version().schema_version_info[0] == 1, "ospac data schema changed"
    """
    with open(_INDEX_FILE) as f:
        index = json.load(f)

    return DataVersion(
        schema_version=index["version"],
        generated=index["generated"],
        spdx_list_version=index["spdx_list_version"],
        total_licenses=index["total_licenses"],
    )
