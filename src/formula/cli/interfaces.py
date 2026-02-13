"""Port of Src/CommandLine/IMessageSink.cs and Src/CommandLine/IChooser.cs.

Provides the message sink and chooser abstractions used by the CLI layer.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from enum import IntEnum
from io import StringIO
from typing import TextIO, Tuple


class SeverityKind(IntEnum):
    """Severity levels for messages (mirrors API.SeverityKind)."""
    Info = 0
    Warning = 1
    Error = 2


class DigitChoiceKind(IntEnum):
    """Digit choices 0-9, used by IChooser."""
    Zero = 0
    One = 1
    Two = 2
    Three = 3
    Four = 4
    Five = 5
    Six = 6
    Seven = 7
    Eight = 8
    Nine = 9


class IMessageSink(ABC):
    """Abstract message sink -- mirrors the C# IMessageSink interface."""

    @property
    @abstractmethod
    def writer(self) -> TextIO:
        """The underlying text writer."""
        ...

    @abstractmethod
    def reset_printed_error(self) -> None:
        """Reset the printed-error flag."""
        ...

    @abstractmethod
    def write_message(self, msg: str, severity: SeverityKind | None = None) -> None:
        """Write a message (no newline) with optional severity colouring."""
        ...

    @abstractmethod
    def write_message_line(self, msg: str, severity: SeverityKind | None = None) -> None:
        """Write a message followed by a newline."""
        ...


class IChooser(ABC):
    """Abstract chooser -- mirrors the C# IChooser interface."""

    @property
    @abstractmethod
    def interactive(self) -> bool:
        ...

    @interactive.setter
    @abstractmethod
    def interactive(self, value: bool) -> None:
        ...

    @abstractmethod
    def get_choice(self) -> Tuple[bool, DigitChoiceKind]:
        """Return (success, choice).  ``success`` is False when the user
        did not provide a valid digit."""
        ...


# ── ANSI colour helpers ──────────────────────────────────────────────

_ANSI_RESET = "\033[0m"
_ANSI_RED = "\033[31m"
_ANSI_YELLOW = "\033[33m"
_ANSI_CYAN = "\033[36m"

_SEVERITY_COLOUR = {
    SeverityKind.Info: _ANSI_CYAN,
    SeverityKind.Warning: _ANSI_YELLOW,
    SeverityKind.Error: _ANSI_RED,
}


# ── Concrete implementations ─────────────────────────────────────────

class ConsoleSink(IMessageSink):
    """Concrete message sink that writes to *stdout* with ANSI colours."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._writer: TextIO = stream if stream is not None else sys.stdout
        self._printed_error: bool = False

    # -- public helpers ------------------------------------------------

    @property
    def printed_error(self) -> bool:
        return self._printed_error

    # -- IMessageSink --------------------------------------------------

    @property
    def writer(self) -> TextIO:
        return self._writer

    def reset_printed_error(self) -> None:
        self._printed_error = False

    def write_message(self, msg: str, severity: SeverityKind | None = None) -> None:
        if severity is not None and severity == SeverityKind.Error:
            self._printed_error = True
        text = msg
        if severity is not None and severity in _SEVERITY_COLOUR:
            text = f"{_SEVERITY_COLOUR[severity]}{msg}{_ANSI_RESET}"
        self._writer.write(text)
        self._writer.flush()

    def write_message_line(self, msg: str, severity: SeverityKind | None = None) -> None:
        if severity is not None and severity == SeverityKind.Error:
            self._printed_error = True
        text = msg
        if severity is not None and severity in _SEVERITY_COLOUR:
            text = f"{_SEVERITY_COLOUR[severity]}{msg}{_ANSI_RESET}"
        self._writer.write(text + "\n")
        self._writer.flush()


class ConsoleChooser(IChooser):
    """Concrete chooser that reads a single digit from *stdin*."""

    def __init__(self) -> None:
        self._interactive: bool = True

    @property
    def interactive(self) -> bool:
        return self._interactive

    @interactive.setter
    def interactive(self, value: bool) -> None:
        self._interactive = value

    def get_choice(self) -> Tuple[bool, DigitChoiceKind]:
        """Read a line from stdin and attempt to interpret the first
        character as a digit 0-9.  Returns ``(True, digit)`` on success
        or ``(False, DigitChoiceKind.Zero)`` on failure."""
        if not self._interactive:
            return False, DigitChoiceKind.Zero
        try:
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            return False, DigitChoiceKind.Zero

        if len(line) == 0:
            return False, DigitChoiceKind.Zero

        ch = line[0]
        if ch.isdigit():
            val = int(ch)
            if 0 <= val <= 9:
                return True, DigitChoiceKind(val)
        return False, DigitChoiceKind.Zero
