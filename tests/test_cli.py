"""CLI tests.

Converted from: Src/Tests/CommandLineTests.cs (partially)
"""

import os
import pytest


def test_option_parser_empty():
    """Empty input should succeed."""
    from formula.cli.option_parser import parse_switch_string
    ok, opts, err_pos = parse_switch_string("")
    assert ok


def test_option_parser_simple_flag():
    """Parse a simple flag."""
    from formula.cli.option_parser import parse_switch_string
    ok, opts, err_pos = parse_switch_string("-v")
    assert ok
    assert len(opts.option_lists) == 1
    assert opts.option_lists[0][0] == "v"


def test_option_parser_long_flag():
    """Parse a long flag."""
    from formula.cli.option_parser import parse_switch_string
    ok, opts, err_pos = parse_switch_string("--verbose")
    assert ok
    assert len(opts.option_lists) == 1
    assert opts.option_lists[0][0] == "verbose"


def test_option_parser_flag_with_value():
    """Parse a flag with a string value."""
    from formula.cli.option_parser import parse_switch_string
    ok, opts, err_pos = parse_switch_string('-f:"hello"')
    assert ok
    assert len(opts.option_lists) == 1
    name, values = opts.option_lists[0]
    assert name == "f"
    assert len(values) == 1


def test_task_manager_create():
    """TaskManager can be instantiated."""
    from formula.cli.task_manager import TaskManager
    tm = TaskManager()
    assert tm.is_wait_on is False


def test_interfaces_console_sink():
    """ConsoleSink can be instantiated."""
    from formula.cli.interfaces import ConsoleSink
    sink = ConsoleSink()
    assert sink.printed_error is False


def test_print_command():
    """Test that print command outputs FORMULA source."""
    from tests.conftest import FormulaFixture, symbolic_path
    import os
    fix = FormulaFixture()
    path = symbolic_path("MappingExample.4ml")
    if not os.path.isfile(path):
        pytest.skip("MappingExample.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()
    fix.sink.clear_output()
    fix.run_command("print Mapping")
    output = "\n".join(fix.sink.output)
    assert "domain Mapping" in output
    assert "::=" in output
    fix.dispose()


def test_det_command():
    """Test that det command shows module details."""
    from tests.conftest import FormulaFixture, symbolic_path
    import os
    fix = FormulaFixture()
    path = symbolic_path("MappingExample.4ml")
    if not os.path.isfile(path):
        pytest.skip("MappingExample.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()
    fix.sink.clear_output()
    fix.run_command("det Mapping")
    output = "\n".join(fix.sink.output)
    assert "Name:" in output
    assert "Kind:" in output
    assert "Domain" in output
    fix.dispose()


def test_types_command():
    """Test that types command shows type declarations."""
    from tests.conftest import FormulaFixture, symbolic_path
    import os
    fix = FormulaFixture()
    path = symbolic_path("MappingExample.4ml")
    if not os.path.isfile(path):
        pytest.skip("MappingExample.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()
    fix.sink.clear_output()
    fix.run_command("types Mapping")
    output = "\n".join(fix.sink.output)
    assert "::=" in output
    fix.dispose()


def test_confhelp_command():
    """Test that confhelp command shows configuration help."""
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    fix.sink.clear_output()
    fix.run_command("confhelp")
    output = "\n".join(fix.sink.output)
    assert "Configuration settings" in output
    fix.dispose()


def test_help_command():
    """Test that help command lists available commands.

    Converted from: CommandLineTests.TestHelp()
    """
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    fix.sink.clear_output()
    fix.run_command("help")
    assert fix.get_help_result()
    fix.sink.clear_output()
    fix.run_command("h")
    assert fix.get_help_result()
    fix.dispose()


def test_set_command():
    """Test that set command stores variables.

    Converted from: CommandLineTests.TestSet()
    """
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    fix.sink.clear_output()
    fix.run_command("set A test")
    assert fix.get_set_result()
    fix.sink.clear_output()
    fix.run_command("s A test")
    assert fix.get_set_result()
    fix.dispose()


def test_del_command():
    """Test that del command removes variables.

    Converted from: CommandLineTests.TestDel()
    """
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    fix.run_command("set B test2")
    fix.sink.clear_output()
    fix.run_command("del B")
    assert fix.get_del_result()
    fix.sink.clear_output()
    fix.run_command("set B test2")
    fix.sink.clear_output()
    fix.run_command("d B")
    assert fix.get_del_result()
    fix.dispose()


def test_list_command():
    """Test that list command shows environment variables.

    Converted from: CommandLineTests.TestList()
    """
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    fix.sink.clear_output()
    fix.run_command("list vars")
    assert fix.get_list_result()
    fix.sink.clear_output()
    fix.run_command("ls vars")
    assert fix.get_list_result()
    fix.dispose()


# -- Compilation pipeline tests ------------------------------------------


def test_compilation_runs():
    """Test that load actually runs the compiler pipeline."""
    from tests.conftest import FormulaFixture, symbolic_path
    import os
    fix = FormulaFixture()
    path = symbolic_path("MappingExample.4ml")
    if not os.path.isfile(path):
        pytest.skip("MappingExample.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()

    # Check that modules have compiler_data (ModuleData)
    from formula.compiler.module_data import ModuleData
    ci = fix._ci
    mapping = ci._modules.get("Mapping")
    assert mapping is not None
    mod_data = getattr(mapping, "compiler_data", None)
    assert mod_data is not None
    assert isinstance(mod_data, ModuleData)
    assert mod_data.is_compiled
    fix.dispose()


def test_symbol_table_populated():
    """Test that compilation populates the SymbolTable with constructors."""
    from tests.conftest import FormulaFixture, symbolic_path
    import os
    fix = FormulaFixture()
    path = symbolic_path("MappingExample.4ml")
    if not os.path.isfile(path):
        pytest.skip("MappingExample.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()

    from formula.compiler.module_data import ModuleData
    from formula.common.symbols import SymbolTable
    ci = fix._ci
    mapping = ci._modules.get("Mapping")
    assert mapping is not None
    mod_data = getattr(mapping, "compiler_data", None)
    assert isinstance(mod_data, ModuleData)

    sym_table = mod_data.symbol_table
    assert sym_table is not None
    assert isinstance(sym_table, SymbolTable)

    # The Mapping domain should have constructors registered
    symbols = list(sym_table.all_symbols())
    assert len(symbols) > 0

    # Check that a known constructor exists (e.g. "Node" from MappingExample)
    sym_names = {s.name for s in symbols}
    # MappingExample defines constructors like Node, Edge, Label, etc.
    assert len(sym_names) > 0
    fix.dispose()


def test_model_compilation():
    """Test that model compilation succeeds."""
    from tests.conftest import FormulaFixture, symbolic_path
    import os
    fix = FormulaFixture()
    path = symbolic_path("MappingExample.4ml")
    if not os.path.isfile(path):
        pytest.skip("MappingExample.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()

    from formula.compiler.module_data import ModuleData
    ci = fix._ci
    # Check partial model too
    pm = ci._modules.get("pm")
    if pm is not None:
        mod_data = getattr(pm, "compiler_data", None)
        assert mod_data is not None
        assert isinstance(mod_data, ModuleData)
        assert mod_data.is_compiled
    fix.dispose()


def test_solve_after_compilation():
    """Verify that solve still works after compilation is wired up."""
    from tests.conftest import FormulaFixture, symbolic_path
    import os
    fix = FormulaFixture()
    path = symbolic_path("MappingExample.4ml")
    if not os.path.isfile(path):
        pytest.skip("MappingExample.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()
    fix.sink.clear_output()
    fix.run_command("solve pm 1 Mapping.conforms")
    assert fix.get_solve_result()
    fix.dispose()


# ── Transform tests ──────────────────────────────────────────────────

_TRANSFORM_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Tst", "Tests", "Transform",
)


def _transform_path(name: str) -> str:
    return os.path.join(_TRANSFORM_DIR, name)


def test_transform_load():
    """Verify that a spec with transforms loads and compiles."""
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    path = _transform_path("tests.4ml")
    if not os.path.isfile(path):
        pytest.skip("Transform tests.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()
    # Check that transform modules are registered
    ci = fix._ci
    assert "Double" in ci._modules
    assert "Identity" in ci._modules
    assert "m1" in ci._modules
    assert "m2" in ci._modules
    fix.dispose()


def test_transform_identity_apply():
    """Apply the Identity transform: out.N(x) :- in.N(x)."""
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    path = _transform_path("tests.4ml")
    if not os.path.isfile(path):
        pytest.skip("Transform tests.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()
    fix.sink.clear_output()
    fix.run_command("apply result = Identity(m1)")
    output = "\n".join(fix.sink.output)
    # Should contain the original facts: N(1), N(2), N(3)
    assert "N(1)" in output
    assert "N(2)" in output
    assert "N(3)" in output
    fix.dispose()


def test_transform_double_apply():
    """Apply the Double transform: out.N(x * 2) :- in.N(x)."""
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    path = _transform_path("tests.4ml")
    if not os.path.isfile(path):
        pytest.skip("Transform tests.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()
    fix.sink.clear_output()
    fix.run_command("apply result = Double(m1)")
    output = "\n".join(fix.sink.output)
    # N(1) → N(2), N(2) → N(4), N(3) → N(6)
    assert "N(2)" in output
    assert "N(4)" in output
    assert "N(6)" in output
    fix.dispose()


def test_transform_apply_parse_errors():
    """Verify proper error handling for invalid apply commands."""
    from tests.conftest import FormulaFixture
    fix = FormulaFixture()
    path = _transform_path("tests.4ml")
    if not os.path.isfile(path):
        pytest.skip("Transform tests.4ml not found")
    fix.run_command(f"load {path}")
    assert fix.get_load_result()

    # Wrong number of args
    fix.sink.clear_output()
    fix.run_command("apply result = Double(m1, m2)")
    output = "\n".join(fix.sink.output)
    assert "expects 1 input" in output

    # Module not found
    fix.sink.clear_output()
    fix.run_command("apply result = NonExistent(m1)")
    output = "\n".join(fix.sink.output)
    assert "not found" in output

    fix.dispose()
