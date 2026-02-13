"""Entry point for the FORMULA 2.0 interactive CLI.

Port of the .NET FORMULA command-line front end.
"""

from __future__ import annotations

import sys

from .command_interface import EXIT_COMMAND, EXIT_SHORT_COMMAND, CommandInterface
from .interfaces import ConsoleSink, ConsoleChooser, SeverityKind


_PROMPT = ">>> "
_BANNER = "FORMULA 2.0 interactive shell (Python port). Type 'help' for commands."


def main() -> None:
    """Run the interactive FORMULA REPL."""
    sink = ConsoleSink()
    chooser = ConsoleChooser()
    ci = CommandInterface(sink, chooser)

    sink.write_message_line(_BANNER)

    # Try to enable readline for history / line editing
    try:
        import readline  # noqa: F401
    except ImportError:
        pass

    while True:
        try:
            line = input(_PROMPT)
        except (EOFError, KeyboardInterrupt):
            sink.write_message_line("")
            break

        stripped = line.strip()
        if stripped in (EXIT_COMMAND, EXIT_SHORT_COMMAND):
            break

        ci.do_command(stripped)


if __name__ == "__main__":
    main()
