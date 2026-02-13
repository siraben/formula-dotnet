"""FORMULA Jupyter kernel engine.

Converted from: Src/Kernel/InteractiveKernel/KernelEngine.cs

Implements the ipykernel-based execution engine that processes
FORMULA commands within a Jupyter notebook cell.
"""

from __future__ import annotations

import io
import os
import re
import threading
from typing import Optional

from formula.api.constants import SeverityKind
from formula.cli.command_interface import CommandInterface
from formula.cli.interfaces import IMessageSink, IChooser, DigitChoiceKind


# ---------------------------------------------------------------------------
# KernelSink -- captures output for Jupyter display
# ---------------------------------------------------------------------------

class KernelSink(IMessageSink):
    """Message sink that captures stdout/stderr for Jupyter cells.

    Converted from: Src/Kernel/InteractiveKernel/Sink.cs
    """

    def __init__(self) -> None:
        self._stdout_buf = io.StringIO()
        self._stderr_buf = io.StringIO()
        self._printed_error = False
        self._lock = threading.Lock()
        self._stream_callback = None  # set by kernel for live output

    # -- public properties ---------------------------------------------------

    @property
    def printed_error(self) -> bool:
        with self._lock:
            return self._printed_error

    @property
    def writer(self):
        return self._stdout_buf

    def set_stream_callback(self, callback) -> None:
        """Set callback for live streaming output to Jupyter."""
        self._stream_callback = callback

    # -- stdout / stderr access ----------------------------------------------

    def get_stdout(self) -> str:
        return self._stdout_buf.getvalue()

    def get_stderr(self) -> str:
        return self._stderr_buf.getvalue()

    def clear(self) -> None:
        self._stdout_buf = io.StringIO()
        self._stderr_buf = io.StringIO()
        with self._lock:
            self._printed_error = False

    # -- IMessageSink implementation -----------------------------------------

    def reset_printed_error(self) -> None:
        with self._lock:
            self._printed_error = False

    def write_message(self, msg: str,
                      severity: Optional[SeverityKind] = None) -> None:
        if severity is not None and severity in (
            SeverityKind.Warning, SeverityKind.Error
        ):
            if severity == SeverityKind.Error:
                with self._lock:
                    self._printed_error = True
            self._stderr_buf.write(msg)
        else:
            self._stdout_buf.write(msg)

    def write_message_line(self, msg: str,
                           severity: Optional[SeverityKind] = None) -> None:
        if severity is not None and severity in (
            SeverityKind.Warning, SeverityKind.Error
        ):
            if severity == SeverityKind.Error:
                with self._lock:
                    self._printed_error = True
            self._stderr_buf.write(msg + "\n")
        else:
            self._stdout_buf.write(msg + "\n")


# ---------------------------------------------------------------------------
# KernelChooser -- non-interactive chooser for Jupyter
# ---------------------------------------------------------------------------

class KernelChooser(IChooser):
    """Chooser that uses Jupyter's input mechanism.

    Converted from: Src/Kernel/InteractiveKernel/Chooser.cs

    In the C# version this communicated via ZMQ stdin messages.
    Here we use ipykernel's built-in input_request mechanism.
    """

    def __init__(self) -> None:
        self._interactive = True
        self._input_func = None  # set by kernel to raw_input proxy

    @property
    def interactive(self) -> bool:
        return self._interactive

    @interactive.setter
    def interactive(self, value: bool) -> None:
        self._interactive = value

    def set_input_func(self, func) -> None:
        """Set the function used to request input from the Jupyter client."""
        self._input_func = func

    def get_choice(self):
        if not self._interactive or self._input_func is None:
            return True, DigitChoiceKind.Zero

        try:
            reply = self._input_func("Input selection: ")
            digit = int(reply.strip())
            if 0 <= digit <= 9:
                return True, DigitChoiceKind(digit)
        except (ValueError, EOFError):
            pass

        return False, DigitChoiceKind.Zero


# ---------------------------------------------------------------------------
# KernelEngine -- main execution engine
# ---------------------------------------------------------------------------

# Regex for detecting load commands
_LOAD_RE = re.compile(r"^(load|l)\s", re.IGNORECASE)


class KernelEngine:
    """Wraps CommandInterface for use in a Jupyter kernel.

    Converted from: Src/Kernel/InteractiveKernel/KernelEngine.cs
    """

    def __init__(self) -> None:
        self.sink = KernelSink()
        self.chooser = KernelChooser()
        self._ci = CommandInterface(self.sink, self.chooser)
        self._initialized = False

    def execute(self, code: str):
        """Execute a FORMULA command string.

        Returns:
            tuple: (status, stdout, stderr) where status is 'ok' or 'error'.
        """
        if not self._initialized:
            self._ci.do_command("wait on")
            self.sink.clear()
            self._initialized = True

        # Handle load commands: extract directory from path
        # C# version: "load <file> <dir>" → chdir(dir), exec "load <file>"
        match = _LOAD_RE.match(code)
        if match:
            parts = code.split(None, 2)
            if len(parts) == 3:
                os.chdir(parts[2])
                code = f"{parts[0]} {parts[1]}"

        self._ci.do_command(code)

        stdout = self.sink.get_stdout()
        stderr = self.sink.get_stderr()
        had_error = self.sink.printed_error

        self.sink.clear()

        status = "error" if had_error else "ok"
        return status, stdout, stderr
