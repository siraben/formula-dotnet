"""Result types for FORMULA 2.0 API operations.

Ported from Microsoft.Formula.API.Results (Src/Core/API/Results/*.cs).

Each result type captures the outcome (flags, success status) of a
particular API operation:  parse, install, solve, apply, query, etc.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from formula.api.constants import InstallKind, SeverityKind
from formula.api.nodes import Node, ProgramName, Span


# ---------------------------------------------------------------------------
# Flag -- a diagnostic message from any phase
# ---------------------------------------------------------------------------

class Flag:
    """A diagnostic flag (error, warning, or info) produced during an operation."""

    __slots__ = ("severity", "span", "message", "code", "program_name")

    def __init__(
        self,
        severity: SeverityKind,
        span: Span,
        message: str,
        code: int,
        program_name: Optional[ProgramName] = None,
    ):
        self.severity = severity
        self.span = span
        self.message = message
        self.code = code
        self.program_name = program_name

    def __str__(self) -> str:
        loc = ""
        if self.span and self.span.start_line:
            loc = f"({self.span.start_line},{self.span.start_col}): "
        return f"[{self.severity.name}] {loc}{self.message}"


# ---------------------------------------------------------------------------
# Base result mixin
# ---------------------------------------------------------------------------

class _FlagCollection:
    """Mixin that collects flags and tracks success."""

    def __init__(self) -> None:
        self._flags: List[Flag] = []
        self._succeeded: bool = True

    @property
    def flags(self) -> Sequence[Flag]:
        return list(self._flags)

    @property
    def succeeded(self) -> bool:
        return self._succeeded

    def add_flag(self, flag: Flag) -> None:
        if flag.severity == SeverityKind.Error:
            self._succeeded = False
        self._flags.append(flag)


# ---------------------------------------------------------------------------
# ParseResult
# ---------------------------------------------------------------------------

class ParseResult(_FlagCollection):
    """Result of a parse operation.

    Ported from Microsoft.Formula.API.ParseResult.
    """

    def __init__(self, program: Optional[Any] = None) -> None:
        super().__init__()
        if program is None:
            from formula.api.nodes import Program
            name = ProgramName("dummy.4ml")
            program = Program(name)
        self._program = program
        self._name: ProgramName = program.name

    @property
    def program(self) -> Any:
        return self._program

    @property
    def name(self) -> ProgramName:
        return self._name

    def clear_flags(self) -> None:
        self._flags.clear()
        self._succeeded = True


# ---------------------------------------------------------------------------
# InstallStatus
# ---------------------------------------------------------------------------

class InstallStatus:
    """Status of an individual program installation.

    Ported from Microsoft.Formula.API.InstallStatus.
    """

    def __init__(self, name: ProgramName, kind: InstallKind) -> None:
        self._name = name
        self._kind = kind

    @property
    def name(self) -> ProgramName:
        return self._name

    @property
    def kind(self) -> InstallKind:
        return self._kind

    def __repr__(self) -> str:
        return f"InstallStatus({self._name}, {self._kind.name})"


# ---------------------------------------------------------------------------
# InstallResult
# ---------------------------------------------------------------------------

class InstallResult(_FlagCollection):
    """Result of installing one or more programs.

    Ported from Microsoft.Formula.API.InstallResult.
    """

    def __init__(self) -> None:
        super().__init__()
        self._statuses: List[InstallStatus] = []

    @property
    def statuses(self) -> Sequence[InstallStatus]:
        return list(self._statuses)

    def add_status(self, status: InstallStatus) -> None:
        self._statuses.append(status)


# ---------------------------------------------------------------------------
# ApplyResult
# ---------------------------------------------------------------------------

class ApplyResult(_FlagCollection):
    """Result of applying a transform or query.

    Ported from Microsoft.Formula.API.ApplyResult.
    """

    def __init__(self) -> None:
        super().__init__()
        self._output_names: List[Any] = []
        self._was_cancelled: bool = False
        self._keep_derivations: bool = False

    @property
    def output_names(self) -> Sequence[Any]:
        return list(self._output_names)

    @property
    def was_cancelled(self) -> bool:
        return self._was_cancelled

    @property
    def keep_derivations(self) -> bool:
        return self._keep_derivations


# ---------------------------------------------------------------------------
# SolveResult
# ---------------------------------------------------------------------------

class SolveResult(_FlagCollection):
    """Result of a solve (constraint-satisfaction) operation.

    Ported from Microsoft.Formula.API.SolveResult.
    """

    def __init__(self) -> None:
        super().__init__()
        self._num_solutions: int = 0

    @property
    def num_solutions(self) -> int:
        return self._num_solutions


# ---------------------------------------------------------------------------
# QueryResult
# ---------------------------------------------------------------------------

class QueryResult(_FlagCollection):
    """Result of an AST query operation.

    Ported from Microsoft.Formula.API.QueryResult.
    """

    def __init__(self) -> None:
        super().__init__()


# ---------------------------------------------------------------------------
# GenerateResult
# ---------------------------------------------------------------------------

class GenerateResult(_FlagCollection):
    """Result of a code-generation operation.

    Ported from Microsoft.Formula.API.GenerateResult.
    """

    def __init__(self) -> None:
        super().__init__()


# ---------------------------------------------------------------------------
# RenderResult
# ---------------------------------------------------------------------------

class RenderResult(_FlagCollection):
    """Result of an AST render operation.

    Ported from Microsoft.Formula.API.RenderResult.
    """

    def __init__(self) -> None:
        super().__init__()


# ---------------------------------------------------------------------------
# ReloadResult
# ---------------------------------------------------------------------------

class ReloadResult(_FlagCollection):
    """Result of a program reload operation.

    Ported from Microsoft.Formula.API.ReloadResult.
    """

    def __init__(self) -> None:
        super().__init__()


# ---------------------------------------------------------------------------
# ObjectGraphResult
# ---------------------------------------------------------------------------

class ObjectGraphResult(_FlagCollection):
    """Result of creating an object graph from a model.

    Ported from Microsoft.Formula.API.ObjectGraphResult.
    """

    def __init__(self) -> None:
        super().__init__()
