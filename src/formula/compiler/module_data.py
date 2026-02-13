"""
Port of Microsoft.Formula.Compiler.ModuleData (ModuleData.cs).

ModuleData tracks the compilation state of a single module (domain, model,
transform, or TSystem) as it progresses through the compiler pipeline:

    Reduced  ->  TypesDefined  ->  Compiled

At each phase transition the relevant compiler artefact (SymbolTable, FactSet,
RuleTable, etc.) is attached to the ModuleData.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Optional

from formula.compiler.configuration import Location


# ---------------------------------------------------------------------------
# Phase enumeration
# ---------------------------------------------------------------------------

class PhaseKind(IntEnum):
    """Tracks which compilation phase the module has completed."""
    Reduced = 0
    TypesDefined = 1
    Compiled = 2


# ---------------------------------------------------------------------------
# ModuleData
# ---------------------------------------------------------------------------

class ModuleData:
    """
    Carries the per-module compiler state through the pipeline.

    Attributes
    ----------
    env : Any
        Reference to the compiler ``Env``.
    source : Location
        The original (un-reduced) AST location.
    reduced : Any
        The AST after quotation elimination (phase >= Reduced).
    phase : PhaseKind
        The most recently completed phase.
    symbol_table : Any | None
        The ``SymbolTable`` produced after *TypesDefined*.
    final_output : Any | None
        The artefact produced after *Compiled* (e.g. FactSet, RuleTable).
    is_query_container : bool
        True when this module exists solely to hold a query.
    """

    def __init__(
        self,
        env: Any,
        source: Location,
        reduced: Any,
        is_query_container: bool = False,
    ) -> None:
        assert source is not None and reduced is not None and env is not None
        self.env = env
        self.source: Location = source
        self.reduced: Any = reduced
        self.phase: PhaseKind = PhaseKind.Reduced
        self.symbol_table: Any = None
        self.final_output: Any = None
        self.is_query_container: bool = is_query_container

    # ------- Phase progression ----------------------------------------------

    def passed_phase(self, phase: PhaseKind, compiler_obj: Any = None) -> None:
        """
        Record that the module has completed *phase*, attaching the
        corresponding compiler artefact.

        Parameters
        ----------
        phase : PhaseKind
            Must be exactly one step above the current phase.
        compiler_obj : Any
            For *TypesDefined* this must be a SymbolTable.
            For *Compiled* this is the final output (FactSet, RuleTable, etc.).
        """
        assert int(phase) == int(self.phase) + 1, (
            f"Expected phase {PhaseKind(int(self.phase) + 1).name}, "
            f"got {phase.name}"
        )

        if phase == PhaseKind.TypesDefined:
            # compiler_obj is expected to be a SymbolTable
            self.symbol_table = compiler_obj
        elif phase == PhaseKind.Compiled:
            self.final_output = compiler_obj
        else:
            raise NotImplementedError(f"Unexpected phase: {phase}")

        self.phase = phase

    # ------- Convenience queries --------------------------------------------

    @property
    def is_reduced(self) -> bool:
        return self.phase >= PhaseKind.Reduced

    @property
    def is_types_defined(self) -> bool:
        return self.phase >= PhaseKind.TypesDefined

    @property
    def is_compiled(self) -> bool:
        return self.phase >= PhaseKind.Compiled

    def __repr__(self) -> str:
        name = getattr(getattr(self.source, "ast", None), "name", "<?>")
        return f"ModuleData(phase={self.phase.name}, source={name})"
