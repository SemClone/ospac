"""ospac ships its PEP 561 marker (issue #104).

ospac is largely annotated, but without `py.typed` in the installed package a
type checker will not read those annotations, and every consumer sees it as
untyped:

    error: Skipping analyzing "ospac.runtime.loader": module is installed,
           but missing library stubs or py.typed marker  [import-untyped]

The failure this guards against is not a missing file in the repository but a
marker that never reaches the installed package: setuptools silently ignores a
package-data glob that matches nothing.
"""

from pathlib import Path

import ospac


def test_the_marker_sits_in_the_installed_package():
    """Located through the imported package, not the source tree.

    Under a real install that is site-packages, so a marker that was not
    packaged fails here rather than passing on the repository copy.
    """
    assert (Path(ospac.__file__).parent / "py.typed").is_file()


def test_the_marker_is_declared_as_package_data():
    """Without this the file exists in the tree and never ships."""
    root = Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text()
    assert '"py.typed",' in pyproject
