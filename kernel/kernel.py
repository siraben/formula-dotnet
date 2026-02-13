"""FORMULA Jupyter kernel.

Converted from:
  - Src/Kernel/InteractiveKernel/Program.cs
  - Src/Kernel/InteractiveKernel/KernelProperties.cs

Implements a Jupyter kernel for the FORMULA specification language
using the ipykernel framework.
"""

from __future__ import annotations

from ipykernel.kernelbase import Kernel

from kernel.engine import KernelEngine


class FormulaKernel(Kernel):
    """Jupyter kernel for the FORMULA specification language."""

    implementation = "Formula"
    implementation_version = "2.0.0"
    language = "formula"
    language_version = "2.0"
    language_info = {
        "name": "formula",
        "mimetype": "text/plain",
        "file_extension": ".4ml",
    }
    banner = "FORMULA 2.0 - Formal Specifications for Verification and Synthesis"
    help_links = [
        {
            "text": "FORMULA Documentation",
            "url": "https://github.com/VUISIS/formula-dotnet",
        }
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._engine = KernelEngine()
        # Wire up the Jupyter input mechanism for the chooser
        self._engine.chooser.set_input_func(self._input_request)

    def _input_request(self, prompt: str) -> str:
        """Request input from the Jupyter client."""
        return self.raw_input(prompt)

    def do_execute(
        self,
        code: str,
        silent: bool,
        store_history: bool = True,
        user_expressions=None,
        allow_stdin: bool = False,
    ):
        """Execute a FORMULA command."""
        code = code.strip()
        if not code:
            return {
                "status": "ok",
                "execution_count": self.execution_count,
                "payload": [],
                "user_expressions": {},
            }

        status, stdout, stderr = self._engine.execute(code)

        if not silent:
            if stdout:
                self.send_response(
                    self.iopub_socket,
                    "stream",
                    {"name": "stdout", "text": stdout},
                )
            if stderr:
                self.send_response(
                    self.iopub_socket,
                    "stream",
                    {"name": "stderr", "text": stderr},
                )

        if status == "error":
            return {
                "status": "error",
                "execution_count": self.execution_count,
                "ename": "FormulaError",
                "evalue": stderr.strip().split("\n")[-1] if stderr else "Unknown error",
                "traceback": [],
            }

        return {
            "status": "ok",
            "execution_count": self.execution_count,
            "payload": [],
            "user_expressions": {},
        }

    def do_is_complete(self, code: str):
        """Check if input is a complete FORMULA command."""
        # FORMULA commands are single-line, always complete
        return {"status": "complete"}

    def do_complete(self, code: str, cursor_pos: int):
        """Provide tab completion for FORMULA commands."""
        # Basic command completion
        commands = [
            "load", "unload", "reload", "query", "solve", "apply",
            "extract", "print", "render", "types", "set", "del",
            "list", "help", "exit", "wait", "verbose", "interactive",
            "ls", "tunload",
        ]
        token = code[:cursor_pos].split()[-1] if code[:cursor_pos].strip() else ""
        matches = [c for c in commands if c.startswith(token)]

        return {
            "matches": matches,
            "cursor_start": cursor_pos - len(token),
            "cursor_end": cursor_pos,
            "metadata": {},
            "status": "ok",
        }


# ---------------------------------------------------------------------------
# Entry point for `python -m kernel`
# ---------------------------------------------------------------------------

def main():
    """Launch the FORMULA Jupyter kernel."""
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=FormulaKernel)


if __name__ == "__main__":
    main()
