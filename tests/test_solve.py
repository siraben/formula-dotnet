"""Solve integration tests.

Converted from: Src/Tests/SolveTests.cs

These tests require the full CLI/solver pipeline to be functional.
They are marked with pytest.mark.integration so they can be skipped
during early development.
"""

import os

import pytest

from tests.conftest import symbolic_path


# All solve tests need the full pipeline
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def ci_fixture():
    """Module-scoped CommandInterface fixture."""
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    yield fix
    fix.dispose()


def _load_and_check(ci_fixture, filename: str):
    """Helper: load a .4ml file and assert compilation succeeded."""
    path = symbolic_path(filename)
    if not os.path.isfile(path):
        pytest.skip(f"{filename} not found")
    ci_fixture.run_command(f"load {path}", f"Load command for {filename} failed.")
    assert ci_fixture.get_load_result(), f"Loading {filename} failed."


def test_solving_mapping_example(ci_fixture):
    _load_and_check(ci_fixture, "MappingExample.4ml")
    ci_fixture.run_command(
        "solve pm 1 Mapping.conforms",
        "Solve command for MappingExample.4ml failed.",
    )
    assert ci_fixture.get_solve_result(), \
        "No solutions found for partial model pm in MappingExample.4ml."


def test_solving_send_more_money(ci_fixture):
    _load_and_check(ci_fixture, "SendMoreMoney.4ml")
    ci_fixture.run_command(
        "solve pm 1 Money.conforms",
        "Solve command for SendMoreMoney.4ml failed.",
    )
    assert ci_fixture.get_solve_result(), \
        "No solutions found for partial model pm in SendMoreMoney.4ml."


def test_solving_symbolic_aggregation(ci_fixture):
    _load_and_check(ci_fixture, "SymbolicAggregation.4ml")
    ci_fixture.run_command(
        "solve pm 1 SymbolicAggregation.conforms",
        "Solve command for SymbolicAggregation.4ml failed.",
    )
    assert ci_fixture.get_solve_result(), \
        "No solutions found for partial model pm in SymbolicAggregation.4ml."


def test_solving_symbolic_max(ci_fixture):
    _load_and_check(ci_fixture, "SymbolicMax.4ml")
    ci_fixture.run_command(
        "solve pm 1 SymbolicMax.conforms",
        "Solve command for SymbolicMax.4ml failed.",
    )
    assert ci_fixture.get_solve_result(), \
        "No solutions found for partial model pm in SymbolicMax.4ml."


def test_symbolic_olp(ci_fixture):
    _load_and_check(ci_fixture, "SymbolicOLP.4ml")
    ci_fixture.run_command(
        "solve pm 1 SymbolicOLP.conforms",
        "Solve command for SymbolicOLP.4ml failed.",
    )
    # Note: C# test asserts False here – no solution expected
    assert not ci_fixture.get_solve_result(), \
        "Unexpected solution found for partial model pm in SymbolicOLP.4ml."


def test_simple_olp(ci_fixture):
    _load_and_check(ci_fixture, "SimpleOLP.4ml")
    ci_fixture.run_command(
        "solve pm1 1 SimpleOLP.conforms",
        "Solve command for SimpleOLP.4ml failed.",
    )
    # Note: C# test asserts False here
    assert not ci_fixture.get_solve_result(), \
        "Unexpected solution found for partial model pm1 in SimpleOLP.4ml."


def test_simple_olp2(ci_fixture):
    _load_and_check(ci_fixture, "SimpleOLP2.4ml")
    ci_fixture.run_command(
        "solve pm2 1 SimpleOLP2.conforms",
        "Solve command for SimpleOLP2.4ml failed.",
    )
    # Note: C# test asserts False here
    assert not ci_fixture.get_solve_result(), \
        "Unexpected solution found for partial model pm2 in SimpleOLP2.4ml."
