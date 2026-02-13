"""Environment for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.Env (Src/Core/API/Base/Env.cs).

The ``Env`` class is the main entry point for managing FORMULA programs:
installing, compiling, querying, solving, and applying transforms.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from formula.api.ast import AST
from formula.api.constants import (
    InstallKind,
    SeverityKind,
    BAD_FILE,
    OP_CANCELLED,
    UNDEFINED_SYMBOL,
    ALREADY_INSTALLED_ERROR,
    UNINSTALL_ERROR,
)
from formula.api.nodes import Folder, Node, Program, ProgramName, Span
from formula.api.results import (
    ApplyResult,
    Flag,
    GenerateResult,
    InstallResult,
    InstallStatus,
    ObjectGraphResult,
    ParseResult,
    QueryResult,
    ReloadResult,
    SolveResult,
)


# ---------------------------------------------------------------------------
# EnvParams -- environment parameters
# ---------------------------------------------------------------------------

class EnvParams:
    """Environment parameter bag.

    Ported from Microsoft.Formula.API.EnvParams.
    """

    def __init__(self) -> None:
        self.msgs_suppress_paths: bool = True
        self.printer_reference_print_kind: int = 0  # Verbatim


# ---------------------------------------------------------------------------
# Env -- the FORMULA environment
# ---------------------------------------------------------------------------

class Env:
    """The FORMULA environment that manages installed programs.

    Ported from Microsoft.Formula.API.Env.

    Programs are parsed and installed via ``install``. After installation
    the environment can be used for compilation, querying, solving, etc.
    """

    def __init__(self, env_params: Optional[EnvParams] = None) -> None:
        self._params = env_params if env_params is not None else EnvParams()
        self._programs: Dict[ProgramName, Program] = {}
        self._file_root = AST(Folder("/"))
        self._env_root = AST(Folder("/"))
        self._lock = threading.Lock()
        self._is_busy = False
        self._next_guid = 0

    # -- Properties ---------------------------------------------------------

    @property
    def parameters(self) -> EnvParams:
        return self._params

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    @property
    def file_root(self) -> AST:
        return self._file_root

    @property
    def env_root(self) -> AST:
        return self._env_root

    @property
    def programs(self) -> Dict[ProgramName, Program]:
        return dict(self._programs)

    # -- Install / uninstall ------------------------------------------------

    def install(self, program_text: str, program_name: ProgramName) -> Tuple[bool, InstallResult]:
        """Parse and install a program from source text.

        Returns (started, InstallResult).
        """
        result = InstallResult()

        if program_name in self._programs:
            flag = Flag(
                SeverityKind.Error,
                Span(),
                ALREADY_INSTALLED_ERROR.format(str(program_name)),
                ALREADY_INSTALLED_ERROR.code,
                program_name,
            )
            result.add_flag(flag)
            result.add_status(InstallStatus(program_name, InstallKind.Failed))
            return True, result

        from formula.api.parser.parser import Parser

        parser = Parser()
        ok, pr = parser.parse_text(program_name, program_text)
        for f in pr.flags:
            result.add_flag(f)

        if not ok:
            result.add_status(InstallStatus(program_name, InstallKind.Failed))
            return True, result

        self._programs[program_name] = pr.program
        result.add_status(InstallStatus(program_name, InstallKind.Compiled))
        return True, result

    def install_file(self, program_name: ProgramName) -> Tuple[bool, InstallResult]:
        """Parse and install a program from a file.

        Returns (started, InstallResult).
        """
        result = InstallResult()

        if program_name in self._programs:
            flag = Flag(
                SeverityKind.Error,
                Span(),
                ALREADY_INSTALLED_ERROR.format(str(program_name)),
                ALREADY_INSTALLED_ERROR.code,
                program_name,
            )
            result.add_flag(flag)
            result.add_status(InstallStatus(program_name, InstallKind.Failed))
            return True, result

        from formula.api.parser.parser import Parser

        parser = Parser()
        ok, pr = parser.parse_file(program_name)
        for f in pr.flags:
            result.add_flag(f)

        if not ok:
            result.add_status(InstallStatus(program_name, InstallKind.Failed))
            return True, result

        self._programs[program_name] = pr.program
        result.add_status(InstallStatus(program_name, InstallKind.Compiled))
        return True, result

    def uninstall(self, program_name: ProgramName) -> Tuple[bool, InstallResult]:
        """Uninstall a program.

        Returns (started, InstallResult).
        """
        result = InstallResult()

        if program_name not in self._programs:
            flag = Flag(
                SeverityKind.Error,
                Span(),
                UNINSTALL_ERROR.format(str(program_name)),
                UNINSTALL_ERROR.code,
                program_name,
            )
            result.add_flag(flag)
            return True, result

        del self._programs[program_name]
        result.add_status(InstallStatus(program_name, InstallKind.Uninstalled))
        return True, result

    # -- Query helpers ------------------------------------------------------

    def try_get_program(self, name: ProgramName) -> Tuple[bool, Optional[Program]]:
        """Try to retrieve an installed program by name."""
        prog = self._programs.get(name)
        if prog is None:
            return False, None
        return True, prog

    # -- Cancel -------------------------------------------------------------

    def cancel(self) -> None:
        """Request cancellation of the current operation."""
        pass

    # -- GUID generation ----------------------------------------------------

    def next_guid(self) -> int:
        with self._lock:
            g = self._next_guid
            self._next_guid += 1
            return g
