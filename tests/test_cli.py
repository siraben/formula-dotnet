"""CLI tests.

Converted from: Src/Tests/CommandLineTests.cs (partially)
"""

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
