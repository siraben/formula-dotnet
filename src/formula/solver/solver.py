"""
Port of Src/Core/Solver/Solver.cs

The ``Solver`` class orchestrates the full model-finding workflow:

1. Create a Z3 Context and Solver.
2. Build type embeddings via :class:`TypeEmbedder`.
3. Optionally instantiate a search strategy (default: OAT).
4. Delegate rule execution and constraint solving to :class:`SymExecuter`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import z3

from formula.solver.sym_executer import SymExecuter
from formula.solver.type_embedder import TypeEmbedder

if TYPE_CHECKING:
    from formula.common.terms import TermIndex, UserSymbol


# ---------------------------------------------------------------------------
# ISolver protocol
# ---------------------------------------------------------------------------

class ISolver:
    """
    Python equivalent of the ``ISolver`` C# interface.

    Concrete implementations must provide:

    * ``configuration`` -- the :class:`Configuration` for the module being solved.
    * ``symbol_table`` -- the :class:`SymbolTable` for the module being solved.
    * ``cardinalities`` -- the :class:`CardSystem` instance.
    * ``get_state(dofs)`` -- returns a :class:`SearchState` for a given set
      of degrees-of-freedom.
    """

    @property
    def configuration(self):  # -> Configuration
        raise NotImplementedError

    @property
    def symbol_table(self):  # -> SymbolTable
        raise NotImplementedError

    @property
    def cardinalities(self):  # -> CardSystem
        raise NotImplementedError

    def get_state(self, dofs):  # -> SearchState
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ISearchStrategy protocol
# ---------------------------------------------------------------------------

class ISearchStrategy:
    """
    Python equivalent of the ``ISearchStrategy`` C# interface.

    A search strategy guides model enumeration by choosing which
    degrees-of-freedom (DOFs) to increment at each step.
    """

    @property
    def description(self) -> str:
        raise NotImplementedError

    @property
    def suggested_settings(self) -> List[Tuple[str, str, str]]:
        """Return ``[(setting_name, kind, description), ...]``."""
        raise NotImplementedError

    def create_instance(self, module, collection_name: str, instance_name: str) -> "ISearchStrategy":
        raise NotImplementedError

    def begin(self, solver: "ISolver", flags: List) -> Optional["ISearchStrategy"]:
        """
        Begin enumeration.  Returns a new strategy instance bound to
        *solver*, or ``None`` on failure.  Diagnostic flags are appended
        to *flags*.
        """
        raise NotImplementedError

    def get_next_cmd(self):
        """
        Return the next set of DOF assignments, or ``None`` to stop.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SearchState
# ---------------------------------------------------------------------------

class SearchState:
    """Placeholder for search-state information returned by :meth:`ISolver.get_state`."""

    pass


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

class Solver(ISolver):
    """
    Top-level solver that coordinates Z3, type embedding and symbolic
    execution.

    Parameters
    ----------
    partial_model : FactSet
        The partial model (set of ground facts) for the module.
    source : Model
        The AST model node being solved.
    env : Env
        The FORMULA environment handle.
    cancel_token : optional
        A threading token for cooperative cancellation (not yet wired).
    """

    DEFAULT_RECURSION_BOUND: int = 10

    def __init__(
        self,
        partial_model,
        source,
        env=None,
        cancel_token=None,
    ):
        self._partial_model = partial_model
        self._source = source
        self._env = env
        self._cancel = cancel_token

        self._solver_flags: List = []
        self._card_inequalities: List[List] = []
        self._solvable: bool = False

        # ---- Cardinality system (currently commented out, as in C#) ----
        self._cardinalities = None  # CardSystem(partial_model) once ready

        # ---- Z3 ----
        self._context: Optional[z3.Context] = None
        self._z3_solver: Optional[z3.Solver] = None
        self._create_context_and_solver()

        # ---- Type embedder ----
        self._type_embedder: Optional[TypeEmbedder] = None
        self._create_type_embedder()

        # ---- Search strategy ----
        self._strategy: Optional[ISearchStrategy] = self._create_strategy(self._solver_flags)

        # ---- Recursion bound ----
        self._recursion_bound: int = self.DEFAULT_RECURSION_BOUND
        self._set_recursion_bound()

        # ---- Symbolic executer ----
        self._executer = SymExecuter(self)

    # ==================================================================
    # ISolver properties
    # ==================================================================

    @property
    def configuration(self):
        """Return the :class:`Configuration` for the source model."""
        return getattr(self._source, "config_compiler_data", None)

    @property
    def symbol_table(self):
        return self._partial_model.index.symbol_table

    @property
    def cardinalities(self):
        return self._cardinalities

    # ==================================================================
    # Additional public properties
    # ==================================================================

    @property
    def card_inequalities(self) -> List[List]:
        return self._card_inequalities

    @property
    def env(self):
        return self._env

    @property
    def recursion_bound(self) -> int:
        return self._recursion_bound

    @property
    def flags(self):
        return self._solver_flags

    @property
    def partial_model(self):
        return self._partial_model

    @property
    def source(self):
        return self._source

    @property
    def context(self) -> z3.Context:
        assert self._context is not None
        return self._context

    @property
    def z3_solver(self) -> z3.Solver:
        assert self._z3_solver is not None
        return self._z3_solver

    @property
    def type_embedder(self) -> TypeEmbedder:
        assert self._type_embedder is not None
        return self._type_embedder

    @property
    def index(self) -> "TermIndex":
        return self._partial_model.index

    # ==================================================================
    # Public API
    # ==================================================================

    def solve(self) -> bool:
        """
        Run the symbolic executor to find a satisfying model.

        Returns ``True`` if a model was found, ``False`` otherwise.
        """
        self._solvable = self._executer.solve()
        return self._solvable

    def get_solution(self, num: int) -> None:
        """Enumerate the *num*-th additional solution."""
        self._executer.get_solution(num)

    def get_state(self, dofs):
        """
        Return a :class:`SearchState` for the given DOF configuration.

        .. note:: Not yet implemented.
        """
        raise NotImplementedError("get_state is not yet implemented")

    def get_model(self) -> bool:
        """Return ``True`` if the strategy can still produce models."""
        if self._strategy is None:
            return False
        return True

    # ==================================================================
    # Context manager (replaces IDisposable)
    # ==================================================================

    def close(self) -> None:
        """Release the Z3 context and solver."""
        self._context = None
        self._z3_solver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _create_context_and_solver(self) -> None:
        """
        Create the Z3 context and solver with default parameters.
        """
        self._context = z3.Context(
            unsat_core="true",
            proof="true",
            model="true",
        )
        self._z3_solver = z3.Solver(ctx=self._context)

        # Core minimisation options
        self._z3_solver.set("core.minimize", True)
        self._z3_solver.set("core.minimize_partial", True)

    def _create_type_embedder(self) -> None:
        """
        Build the :class:`TypeEmbedder` using base-sort cost settings
        from the configuration, or sensible defaults.
        """
        cost_map: Dict[str, int] = {}
        conf = self.configuration

        _DEFAULTS = {
            "Real": 10,
            "String": 10,
            "Integer": 11,
            "Natural": 12,
            "PosInteger": 13,
            "NegInteger": 13,
        }

        for sort_name, default_cost in _DEFAULTS.items():
            setting_name = f"Solver_{sort_name}Cost"
            cost = default_cost
            if conf is not None:
                val = getattr(conf, "try_get_setting", lambda _: None)(setting_name)
                if val is not None:
                    try:
                        cost = int(val)
                    except (TypeError, ValueError):
                        pass
            cost_map[sort_name] = cost

        self._type_embedder = TypeEmbedder(
            self._partial_model.index,
            self._context,
            cost_map,
        )

    def _create_strategy(self, flags: List) -> Optional[ISearchStrategy]:
        """
        Instantiate the search strategy.

        Currently returns the OAT strategy by default.  When the
        cardinality system is enabled this will also check for unsat.
        """
        # Lazy import to avoid circular dependency
        from formula.solver.strategies import OATStrategy

        strategy: ISearchStrategy = OATStrategy.the_factory_instance()

        inst = strategy.begin(self, flags)
        return inst

    def _set_recursion_bound(self) -> None:
        """
        Read the recursion bound from the configuration, or fall back to
        :data:`DEFAULT_RECURSION_BOUND`.
        """
        conf = self.configuration
        if conf is not None:
            val = getattr(conf, "try_get_setting", lambda _: None)(
                "Solver_RecursionBound"
            )
            if val is not None:
                try:
                    self._recursion_bound = int(val)
                    return
                except (TypeError, ValueError):
                    pass
        self._recursion_bound = self.DEFAULT_RECURSION_BOUND
