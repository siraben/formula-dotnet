"""
Port of Microsoft.Formula.Compiler.Loader (Loader.cs).

The Loader is responsible for resolving and loading all FORMULA program files
that are transitively referenced from an initial program AST.  It discovers
references via ModRef nodes and Setting nodes (``defaults`` / ``modules``
registrations), queues parse tasks, and collects the results into a single
InstallResult.

In the Python port, file parsing is synchronous (no Task-based concurrency),
but the algorithm and data flow mirror the original C# version.
"""

from __future__ import annotations

import os
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

from formula.compiler.configuration import (
    Configuration,
    CnstKind,
    Flag,
    NodeKind,
    SeverityKind,
    Span,
)


# ---------------------------------------------------------------------------
# Lightweight stand-in types
# ---------------------------------------------------------------------------

class ProgramName:
    """
    Thin wrapper around a resolved file path.
    In the .NET version this normalises URIs; here we normalise FS paths.
    """

    def __init__(self, name: str, relative_to: Optional["ProgramName"] = None) -> None:
        if relative_to is not None and not os.path.isabs(name):
            base_dir = os.path.dirname(relative_to.uri)
            self.uri: str = os.path.normpath(os.path.join(base_dir, name))
        else:
            self.uri = os.path.normpath(name)

    def __eq__(self, other):
        if isinstance(other, ProgramName):
            return self.uri == other.uri
        return NotImplemented

    def __hash__(self):
        return hash(self.uri)

    def __repr__(self):
        return f"ProgramName({self.uri!r})"

    @staticmethod
    def compare(a: "ProgramName", b: "ProgramName") -> int:
        return (a.uri > b.uri) - (a.uri < b.uri)


class InstallKind:
    Cached = "cached"
    Compiled = "compiled"
    Failed = "failed"


class InstallResult:
    """Accumulates compilation outcomes for a set of programs."""

    def __init__(self) -> None:
        self.succeeded: bool = True
        self._touched: List[Any] = []        # list of TouchedProgram
        self._flags: Dict[Any, List[Flag]] = {}

    @property
    def touched(self):
        return self._touched

    def add_touched(self, program_ast: Any, kind: str) -> None:
        self._touched.append(TouchedProgram(program_ast, kind))

    def add_flags(self, source: Any, flags_or_result=None) -> None:
        if flags_or_result is None:
            return
        if isinstance(flags_or_result, list):
            self._flags.setdefault(id(source), []).extend(flags_or_result)
        elif hasattr(flags_or_result, "flags"):
            self._flags.setdefault(id(source), []).extend(flags_or_result.flags)

    def add_flag(self, source: Any, flag: Flag) -> None:
        self._flags.setdefault(id(source), []).append(flag)

    def get_flags(self, source: Any) -> List[Flag]:
        return self._flags.get(id(source), [])


class TouchedProgram:
    def __init__(self, program: Any, status: str) -> None:
        self.program = program
        self.status = status


class ParseResult:
    """Result of parsing a single .4ml file."""

    def __init__(self, program: Any = None) -> None:
        self.program = program
        self.succeeded: bool = True
        self.flags: List[Flag] = []

    def add_flag(self, flag: Flag) -> None:
        self.flags.append(flag)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class Loader:
    """
    Transitively loads all programs reachable from an initial AST.

    Algorithm:
    1. Seed the work queue with references found in the initial program.
    2. For each unvisited reference, parse the file and scan for further refs.
    3. Collect parse results and mark each program as Compiled / Failed / Cached.

    Parameters
    ----------
    env : Any
        The compiler environment (carries global parameters and the program
        cache ``env.programs``).
    initial : Any
        The root AST<Program> that seeds the loading process.
    iresult : InstallResult
        Accumulator for touched programs and flags.
    cancel : callable or None
        A callable returning True when cancellation is requested; ``None``
        means never cancel.
    """

    def __init__(
        self,
        env: Any,
        initial: Any,
        iresult: InstallResult,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.env = env
        self.initial = initial
        self.iresult = iresult
        self._cancel = cancel or (lambda: False)

        # Map from ProgramName -> parsed AST (or ParseResult)
        self._programs: Dict[ProgramName, Any] = {}

    # ------- public API -----------------------------------------------------

    def load(self) -> bool:
        """
        Execute the transitive loading algorithm.
        Returns ``True`` if all referenced programs were loaded successfully.
        """
        initial_name = self._program_name(self.initial)
        self._programs[initial_name] = self.initial

        # Discover references from the initial program
        work_queue: deque[Tuple[ProgramName, str, Span]] = deque()
        self._enqueue_programs(self.initial, None, work_queue)

        if self._cancel():
            return False

        if not work_queue:
            return self.iresult.succeeded

        # Process the work queue
        while work_queue:
            if self._cancel():
                self.iresult.succeeded = False
                break

            item = work_queue.popleft()
            prog_name, ref_source_str, ref_span = item

            if prog_name in self._programs:
                continue

            # Check if already in the environment cache
            env_programs = getattr(self.env, "programs", {})
            if prog_name in env_programs:
                cached_ast = env_programs[prog_name]
                self.iresult.add_touched(cached_ast, InstallKind.Cached)
                self._programs[prog_name] = cached_ast
                continue

            # Parse the file
            parse_result = self._parse_file(prog_name, ref_source_str, ref_span)
            self._programs[prog_name] = parse_result

            if self._cancel():
                break

            if parse_result.succeeded and parse_result.program is not None:
                # Scan new program for further references
                self._enqueue_programs(parse_result.program, parse_result, work_queue)

        # Collect results
        for pname, value in self._programs.items():
            if isinstance(value, ParseResult):
                pr: ParseResult = value
                if not pr.succeeded:
                    self.iresult.add_touched(pr.program, InstallKind.Failed)
                    self.iresult.succeeded = False
                else:
                    self.iresult.add_touched(pr.program, InstallKind.Compiled)
                self.iresult.add_flags(pr.program, pr)

        if self._cancel():
            self.iresult.succeeded = False

        return self.iresult.succeeded

    # ------- private helpers ------------------------------------------------

    def _enqueue_programs(
        self,
        source: Any,
        parse_result: Optional[ParseResult],
        queue: deque,
    ) -> None:
        """
        Scan *source* AST for ModRef and Setting nodes that reference other
        files and add them to the work *queue*.
        """
        nodes = self._find_references(source)
        for node in nodes:
            nk = self._node_kind(node)
            if nk == NodeKind.ModRef:
                location = getattr(node, "location", None)
                if location:
                    self._try_enqueue(location, source, self._node_span(node),
                                      parse_result, queue)
            elif nk == NodeKind.Setting:
                value = getattr(node, "value", None)
                if value is None:
                    continue
                v_kind = getattr(value, "cnst_kind", None)
                if v_kind != CnstKind.String:
                    continue
                key = getattr(node, "key", None)
                key_name = getattr(key, "name", "") if key else ""
                key_fragments = key_name.split(".") if key_name else []

                if key_name == Configuration.DEFAULTS_SETTING:
                    self._try_enqueue(
                        value.get_string_value(), source,
                        self._node_span(value), parse_result, queue)
                elif (
                    len(key_fragments) == 2
                    and key_fragments[0] == Configuration.MODULES_COLLECTION_NAME
                ):
                    ref_str = value.get_string_value()
                    # Try to extract the location from "name at file.4ml"
                    loc = self._extract_location(ref_str)
                    if loc:
                        self._try_enqueue(
                            loc, source, self._node_span(value),
                            parse_result, queue)

    def _try_enqueue(
        self,
        name: str,
        ref_source: Any,
        ref_span: Span,
        parse_result: Optional[ParseResult],
        queue: deque,
    ) -> None:
        if not name or not name.strip():
            return
        try:
            source_name = self._program_name(ref_source)
            prog_name = ProgramName(name, source_name)
            queue.append((prog_name, str(source_name.uri), ref_span))
        except Exception as exc:
            flag = Flag(
                SeverityKind.Error,
                ref_span,
                f"Bad file reference: {exc}",
                code=20,
            )
            if parse_result is None:
                self.iresult.add_flag(ref_source, flag)
            else:
                parse_result.add_flag(flag)

    def _parse_file(
        self,
        prog_name: ProgramName,
        ref_source_str: str,
        ref_span: Span,
    ) -> ParseResult:
        """
        Parse a FORMULA source file.
        This delegates to the environment's parser. A placeholder implementation
        is provided that reads the file and returns an empty AST if parsing is
        not yet wired up.
        """
        parser = getattr(self.env, "parse_file", None)
        if parser is not None:
            return parser(prog_name, ref_source_str, ref_span)

        # Fallback: check file exists; wrap in ParseResult
        result = ParseResult()
        path = prog_name.uri
        if not os.path.isfile(path):
            result.succeeded = False
            result.add_flag(Flag(
                SeverityKind.Error,
                ref_span,
                f"File not found: {path}",
                code=21,
            ))
        else:
            # Actual parsing would happen here
            result.program = _StubProgram(prog_name)
        return result

    # ------- AST traversal adapters ----------------------------------------

    @staticmethod
    def _find_references(program_ast: Any) -> list:
        """
        Return all ModRef and Setting nodes reachable from *program_ast*.
        """
        if hasattr(program_ast, "find_all_references"):
            return list(program_ast.find_all_references())
        # Walk children recursively using a generic visitor
        results: list = []
        _walk(program_ast, results)
        return results

    @staticmethod
    def _node_kind(node: Any) -> Optional[NodeKind]:
        nk = getattr(node, "node_kind", None)
        if isinstance(nk, NodeKind):
            return nk
        return None

    @staticmethod
    def _node_span(node: Any) -> Span:
        return getattr(node, "span", Span())

    @staticmethod
    def _program_name(ast: Any) -> ProgramName:
        """Extract or synthesise a ProgramName from an AST."""
        if isinstance(ast, ProgramName):
            return ast
        name = getattr(ast, "name", None)
        if isinstance(name, ProgramName):
            return name
        if isinstance(name, str):
            return ProgramName(name)
        node = getattr(ast, "node", ast)
        name = getattr(node, "name", None)
        if isinstance(name, ProgramName):
            return name
        if isinstance(name, str):
            return ProgramName(name)
        return ProgramName("<unknown>")

    @staticmethod
    def _extract_location(ref_str: str) -> Optional[str]:
        """
        Given a module reference like ``"ModuleName at file.4ml"``, return
        the file part.
        """
        if " at " in ref_str:
            return ref_str.split(" at ", 1)[1].strip()
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _walk(node: Any, results: list) -> None:
    """Generic recursive child walker collecting ModRef/Setting nodes."""
    nk = getattr(node, "node_kind", None)
    if nk == NodeKind.ModRef or nk == NodeKind.Setting:
        results.append(node)
    children = getattr(node, "children", None)
    if children is not None:
        for ch in children:
            _walk(ch, results)


class _StubProgram:
    """Minimal stand-in for a parsed program AST during early bootstrap."""

    def __init__(self, prog_name: ProgramName) -> None:
        self.name = prog_name
        self.children: list = []
        self.node_kind = NodeKind.Program
