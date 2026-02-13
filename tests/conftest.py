"""Pytest fixtures for FORMULA tests.

Converted from: Src/Tests/Fixtures.cs
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Optional

import pytest

from formula.api.constants import SeverityKind


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_TST_DIR = Path(__file__).resolve().parent.parent / "Tst"
SYMBOLIC_DIR = _TST_DIR / "Tests" / "Symbolic"


def symbolic_path(name: str) -> str:
    """Return full path to a .4ml file in Tst/Tests/Symbolic/."""
    return str(SYMBOLIC_DIR / name)


# ---------------------------------------------------------------------------
# TestSink – captures messages instead of printing
# ---------------------------------------------------------------------------

class TestSink:
    """A message sink that captures output for assertions."""

    def __init__(self):
        self._buf = io.StringIO()
        self.command: str = ""
        self.printed_error: bool = False

    @property
    def output(self) -> list[str]:
        return self._buf.getvalue().split("\n")

    def clear_output(self):
        self._buf = io.StringIO()

    def reset_printed_error(self):
        self.printed_error = False

    def write_message(self, msg: str, severity: Optional[SeverityKind] = None):
        self._buf.write(msg)

    def write_message_line(self, msg: str, severity: Optional[SeverityKind] = None):
        self._buf.write(msg + "\n")

    @property
    def writer(self):
        return self._buf


# ---------------------------------------------------------------------------
# TestChooser – non-interactive chooser
# ---------------------------------------------------------------------------

class TestChooser:
    """A chooser that always returns Zero (non-interactive)."""

    def __init__(self):
        self.interactive = False

    def get_choice(self):
        return True, 0


# ---------------------------------------------------------------------------
# FormulaFixture – wraps CommandInterface for integration tests
# ---------------------------------------------------------------------------

class FormulaFixture:
    """Test fixture providing a CommandInterface instance.

    Mirrors the C# FormulaFixture class.
    """

    def __init__(self):
        self.chooser = TestChooser()
        self.sink = TestSink()
        self._ci = None

        # Lazy import – CLI may not be fully available yet
        try:
            from formula.cli.command_interface import CommandInterface
            self._ci = CommandInterface(self.sink, self.chooser)
            self.run_command("interactive off")
            self.run_command("wait on")
            self.run_command("verbose on")
        except ImportError:
            pass

    def run_command(self, command: str, assert_msg: str = ""):
        """Execute a command through the CommandInterface."""
        if self._ci is None:
            pytest.skip("CommandInterface not available")

        args = command.split()
        if args[0] == "load":
            self.sink.command = command
            assert self._ci.do_command("unload *"), "unload failed"
            self.sink.clear_output()
            result = self._ci.do_command(command)
            assert result, assert_msg or f"Command failed: {command}"
        else:
            self.sink.command = command
            result = self._ci.do_command(command)
            assert result, assert_msg or f"Command failed: {command}"

    def get_load_result(self) -> bool:
        """Check if the last load produced a '(Compiled)' message."""
        output = self.sink.output
        self.sink.clear_output()
        for line in output:
            if re.search(r"\(Compiled\)", line):
                return True
        return False

    def get_solve_result(self) -> bool:
        """Check if the last solve task succeeded."""
        self.sink.clear_output()
        assert self._ci.do_command("ls tasks"), "ls tasks failed"
        output = self.sink.output
        self.sink.clear_output()
        assert self._ci.do_command("tunload *"), "tunload failed"
        self.sink.clear_output()
        for line in output:
            if re.search(r"^\s+0\s+\|\s+Solve\s+\|\s+Done\s+\|\s+true", line):
                return True
        return False

    def get_set_result(self) -> bool:
        output = self.sink.output
        self.sink.clear_output()
        return any("=" in line for line in output)

    def get_del_result(self) -> bool:
        output = self.sink.output
        self.sink.clear_output()
        return any(re.search(r"Deleted\svariable", line) for line in output)

    def get_list_result(self) -> bool:
        output = self.sink.output
        self.sink.clear_output()
        return any(re.search(r"Environment\svariables", line) for line in output)

    def get_help_result(self) -> bool:
        output = self.sink.output
        self.sink.clear_output()
        return any(
            re.search(r"apply\s+\(ap\)\s+\-\s+Start\s+an\s+apply\s+task", line)
            for line in output
        )

    def dispose(self):
        if self._ci is not None:
            try:
                self._ci.cancel()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def formula_fixture():
    """Session-scoped FormulaFixture."""
    fix = FormulaFixture()
    yield fix
    fix.dispose()
