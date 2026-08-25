"""Day 1 smoke test — proves the package imports and the harness runs.

Real coverage starts with W1-09 (pydantic model parse tests against
committed fixtures). This file exists so `make check` is green on an
empty implementation, per the Day 1 verification plan.
"""

import radar


def test_package_imports():
    assert radar.__version__
