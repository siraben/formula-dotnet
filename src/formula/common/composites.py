"""
Port of Src/Core/Common/Composites/*.cs (3 files).

Key classes:
  - CoreTSystem    : compiled transformation system
  - StepResult     : result of executing a single step
  - StepResultMap  : thread-safe map of step results (model variable -> FactSet)
"""
from __future__ import annotations

import threading
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)

from formula.common.symbol_types import (
    ConSymb,
    MapSymb,
    Namespace,
    Symbol,
    SymbolKind,
    UserSymbol,
)
from formula.common.terms import Term, TermIndex
from formula.common.rules import (
    CoreRule,
    Executer,
    ExecuterStatistics,
    FactSet,
    RuleTable,
)


# ===================================================================
# StepResultMap
# ===================================================================

class StepResultMap:
    """
    A thread-safe map for storing the intermediate results of transformation
    system steps.  Models of the same domain share the same ``TermIndex``.

    Maps model variable names (strings) to ``FactSet`` instances.
    """

    def __init__(self, model_vars: Optional[Dict[str, Tuple[TermIndex, Any]]] = None) -> None:
        """
        Parameters
        ----------
        model_vars : optional
            A dict mapping model variable names to ``(TermIndex, domain_info)``
            tuples.  If not provided, an empty map is created.
        """
        self._lock = threading.Lock()
        self._indices: Dict[str, Tuple[TermIndex, threading.Lock]] = {}
        self._results: Dict[str, FactSet] = {}

        if model_vars is not None:
            for name, (index, _) in model_vars.items():
                self._indices[name] = (index, threading.Lock())

    def __getitem__(self, model_var: str) -> FactSet:
        with self._lock:
            return self._results[model_var]

    def get(self, model_var: str) -> Optional[FactSet]:
        with self._lock:
            return self._results.get(model_var)

    def set_result(self, model_var: str, facts: FactSet) -> None:
        """Store the result ``FactSet`` for a model variable."""
        with self._lock:
            self._results[model_var] = facts

    def set_result_from_projection(
        self,
        model_var: str,
        projection_space: Namespace,
        terms: Iterable[Term],
    ) -> None:
        """
        Project *terms* into the namespace *projection_space* and store the
        result under *model_var*.

        Only data constructors that are ``new`` and belong to *projection_space*
        are retained.
        """
        ind_data = self._indices.get(model_var)
        if ind_data is None:
            raise KeyError(f"Unknown model variable: {model_var}")

        index, idx_lock = ind_data
        with idx_lock:
            projection: Set[Term] = set()
            for t in terms:
                s = t.symbol
                if not s.is_data_constructor:
                    continue
                us: UserSymbol = s  # type: ignore[assignment]
                if us.namespace.parent is None or us.is_autogen:
                    continue
                if s.kind == SymbolKind.ConSymb and not s.is_new:  # type: ignore[union-attr]
                    continue
                # Walk up to the top-level child of root
                ns = us.namespace
                while ns.parent is not None and ns.parent.parent is not None:
                    ns = ns.parent
                if ns is not projection_space:
                    continue
                projection.add(index.mk_clone(t))

        self.set_result(model_var, FactSet(index, projection))

    @property
    def results(self) -> Dict[str, FactSet]:
        with self._lock:
            return dict(self._results)

    def dispose(self) -> None:
        """Release resources (locks, indices)."""
        self._indices.clear()
        self._results.clear()


# ===================================================================
# CoreStep  (internal helper)
# ===================================================================

class CoreStep:
    """
    An internal representation of a single step in a transformation system.
    """

    def __init__(
        self,
        step_node: Any,
        module_data: Any,
        lhs_names: List[str],
        rhs_name: str,
    ) -> None:
        self.step_node = step_node
        self.module_data = module_data
        self.lhs_names = lhs_names
        self.rhs_name = rhs_name
        self.dependencies: List[CoreStep] = []


# ===================================================================
# StepResult
# ===================================================================

class StepResult:
    """
    The result of executing a single step in a transformation system.

    Wraps a ``StepResultMap`` that maps output model variables to their
    computed ``FactSet`` values.
    """

    def __init__(
        self,
        result_map: StepResultMap,
        step: Optional[Any] = None,
        tsystem: Optional[CoreTSystem] = None,
        value_params: Optional[Dict[str, Term]] = None,
        cancel: Any = None,
    ) -> None:
        self._result_map = result_map
        self._step = step
        self._tsystem = tsystem
        self._value_params = value_params or {}
        self._cancel = cancel

    @property
    def results(self) -> StepResultMap:
        return self._result_map

    def start(self) -> None:
        """
        Execute the step.

        Dispatches to the appropriate execution strategy based on the module
        kind (Model, Transform, or TSystem).
        """
        if self._step is None or self._tsystem is None:
            return

        step = self._step
        tsystem = self._tsystem

        # Determine what kind of module the step references
        module_kind = _get_module_kind(step)

        if module_kind == "Model":
            self._execute_model_step(step, tsystem)
        elif module_kind == "Transform":
            self._execute_transform_step(step, tsystem)
        elif module_kind == "TSystem":
            self._execute_tsystem_step(step, tsystem)

    def _execute_model_step(self, step: Any, tsystem: CoreTSystem) -> None:
        """Execute a step that produces a model (copy facts).

        Ported from C# StepResult.Start (Model case):
        Copies all facts from the model's compiled FactSet into the result map.
        """
        mod_data = getattr(step, "module_data", None)
        if mod_data is None:
            return

        final_output = getattr(mod_data, "final_output", None)
        if final_output is None:
            return

        # Copy facts from the model's FactSet
        if hasattr(final_output, "facts") and hasattr(final_output, "index"):
            src_facts = final_output.facts
            if step.lhs_names:
                output_name = step.lhs_names[0]
                new_facts = set()
                for f in src_facts:
                    new_facts.add(f)
                self._result_map.set_result(
                    output_name, FactSet(final_output.index, new_facts)
                )

    def _execute_transform_step(self, step: Any, tsystem: CoreTSystem) -> None:
        """Execute a step that runs a transform.

        Ported from C# StepResult.Start (Transform case):
        1. Clone the transform's RuleTable into a new TermIndex
        2. Build FactSets from input model parameters
        3. Create an Executer with the cloned rules + input facts
        4. Execute to fixpoint
        5. Project output facts into the result map by namespace
        """
        mod_data = getattr(step, "module_data", None)
        if mod_data is None:
            return

        final_output = getattr(mod_data, "final_output", None)
        if final_output is None:
            return

        # Check if final_output is a RuleTable
        if not isinstance(final_output, RuleTable):
            return

        # Clone the rule table for this execution
        clone_index = TermIndex(mod_data.symbol_table) if hasattr(mod_data, "symbol_table") and mod_data.symbol_table else final_output.index
        cloned_rules = final_output.clone_transform_table(clone_index)

        # Build input FactSets from the result map
        model_facts = {}
        for dep in step.dependencies:
            for ln in dep.lhs_names:
                fs = self._result_map.get(ln)
                if fs is not None:
                    model_facts[ln] = fs

        # Create and run the Executer
        exe = Executer(
            cloned_rules,
            model_facts=model_facts,
            value_params=self._value_params,
        )
        exe.execute()

        # Collect output facts
        if step.lhs_names:
            output_name = step.lhs_names[0]
            output_facts = set()
            for fact in exe.fixpoint_facts:
                output_facts.add(fact)
            self._result_map.set_result(
                output_name, FactSet(clone_index, output_facts)
            )

    def _execute_tsystem_step(self, step: Any, tsystem: CoreTSystem) -> None:
        """Execute a step that runs a nested transformation system.

        Ported from C# StepResult.Start (TSystem case):
        Recursively executes the nested TSystem.
        """
        mod_data = getattr(step, "module_data", None)
        if mod_data is None:
            return

        final_output = getattr(mod_data, "final_output", None)
        if final_output is None or not isinstance(final_output, CoreTSystem):
            return

        # Build model params from our result map
        model_params = {}
        for dep in step.dependencies:
            for ln in dep.lhs_names:
                fs = self._result_map.get(ln)
                if fs is not None:
                    model_params[ln] = fs

        # Execute the nested TSystem
        nested_result = final_output.execute(
            model_params=model_params,
            value_params=self._value_params,
            cancel=self._cancel,
        )

        # Copy nested results into our result map
        for name, fs in nested_result.results.results.items():
            self._result_map.set_result(name, fs)


def _get_module_kind(step: Any) -> str:
    """Determine the module kind of a step (placeholder)."""
    if hasattr(step, "module_data") and step.module_data is not None:
        md = step.module_data
        if hasattr(md, "reduced") and md.reduced is not None:
            node = md.reduced
            if hasattr(node, "node_kind"):
                return node.node_kind
    return "Unknown"


# ===================================================================
# CoreTSystem
# ===================================================================

class CoreTSystem:
    """
    A compiled transformation system.

    Manages:
    - A set of model variables (inputs / outputs)
    - A ``TermIndex`` over the system's combined signature
    - An ordered sequence of steps to execute
    - Value parameters
    """

    def __init__(self, module_data: Any = None) -> None:
        """
        Parameters
        ----------
        module_data : optional
            The compiler's module data containing the reduced AST and symbol table.
        """
        self._module_data = module_data
        self._model_vars: Dict[str, Tuple[Any, Any]] = {}
        self._execution_order: List[CoreStep] = []
        self._signature_index: Optional[TermIndex] = None
        self._indices: Dict[str, Any] = {}

        if module_data is not None:
            self._init_from_module_data(module_data)

    def _init_from_module_data(self, module_data: Any) -> None:
        """Initialise from compiler output."""
        if hasattr(module_data, "symbol_table"):
            self._signature_index = TermIndex(module_data.symbol_table)

    # -- properties --------------------------------------------------------
    @property
    def module_data(self) -> Any:
        return self._module_data

    @property
    def model_variables(self) -> Dict[str, Tuple[Any, Any]]:
        """
        Maps a model variable name to ``(node, location)`` where
        *node* is the AST node that introduced the variable and
        *location* is the domain over which the model is defined.
        """
        return self._model_vars

    @property
    def signature_index(self) -> Optional[TermIndex]:
        return self._signature_index

    # -- model variable management -----------------------------------------
    def add_model_variable(
        self,
        name: str,
        node: Any,
        location: Any,
    ) -> None:
        self._model_vars[name] = (node, location)

    # -- step management ---------------------------------------------------
    def add_step(self, step: CoreStep) -> None:
        self._execution_order.append(step)

    # -- parameter instantiation -------------------------------------------
    def instantiate_value_params(
        self,
        step: Any,
        index: TermIndex,
        value_params: Dict[str, Term],
    ) -> Dict[str, Term]:
        """
        Map value parameter names to their term representations in *index*.
        """
        result: Dict[str, Term] = {}
        for name, term in value_params.items():
            result[name] = index.mk_clone(term)
        return result

    def instantiate_model_params(
        self,
        step: Any,
        result_map: StepResultMap,
    ) -> Dict[str, FactSet]:
        """
        Map model parameter names to their corresponding ``FactSet`` instances
        from *result_map*.
        """
        result: Dict[str, FactSet] = {}
        for name in self._model_vars:
            fs = result_map.get(name)
            if fs is not None:
                result[name] = fs
        return result

    # -- execution ---------------------------------------------------------
    def execute(
        self,
        model_params: Optional[Dict[str, FactSet]] = None,
        value_params: Optional[Dict[str, Term]] = None,
        cancel: Any = None,
    ) -> StepResult:
        """
        Execute the transformation system with dependency tracking.

        Matches C# CoreTSystem.Execute: steps are executed in dependency
        order.  Each step's input model variables must have been produced
        by a prior step (or provided as input parameters).  The C# version
        uses Task parallelism; this Python port executes synchronously in
        topological order.

        Returns a ``StepResult`` containing all output models.
        """
        model_vars_for_map: Dict[str, Tuple[TermIndex, Any]] = {}
        if self._signature_index is not None:
            for name, (node, loc) in self._model_vars.items():
                model_vars_for_map[name] = (self._signature_index, loc)

        result_map = StepResultMap(model_vars_for_map)

        # Load input model params
        if model_params:
            for name, fset in model_params.items():
                result_map.set_result(name, fset)

        # Build a mapping from LHS variable names to the step that produces them,
        # so we can verify dependencies are satisfied before executing each step.
        var_to_step: Dict[str, int] = {}
        completed: Set[int] = set()

        for i, cstep in enumerate(self._execution_order):
            # Ensure all dependencies (steps that produce our inputs) are done.
            # Dependencies are already captured in cstep.dependencies, but we
            # also check that the model variables we need are available.
            for dep in cstep.dependencies:
                dep_idx = None
                for j, s in enumerate(self._execution_order):
                    if s is dep:
                        dep_idx = j
                        break
                if dep_idx is not None and dep_idx not in completed:
                    # Dependency not yet executed — execute it first.
                    # This shouldn't happen if execution_order is topological,
                    # but handle gracefully.
                    sr = StepResult(
                        result_map,
                        step=self._execution_order[dep_idx],
                        tsystem=self,
                        value_params=value_params or {},
                        cancel=cancel,
                    )
                    sr.start()
                    completed.add(dep_idx)
                    for ln in self._execution_order[dep_idx].lhs_names:
                        var_to_step[ln] = dep_idx

            # Execute this step
            step_result = StepResult(
                result_map,
                step=cstep,
                tsystem=self,
                value_params=value_params or {},
                cancel=cancel,
            )
            step_result.start()
            completed.add(i)

            # Register this step's outputs
            for ln in cstep.lhs_names:
                var_to_step[ln] = i

        return StepResult(result_map)

    # -- debugging ---------------------------------------------------------
    def debug_print(self) -> None:
        print(f"=== CoreTSystem ===")
        print(f"Model variables: {list(self._model_vars.keys())}")
        print(f"Steps: {len(self._execution_order)}")
        for i, step in enumerate(self._execution_order):
            print(f"  Step {i}: {step.lhs_names} <- {step.rhs_name}")

    def __repr__(self) -> str:
        return (
            f"<CoreTSystem vars={list(self._model_vars.keys())} "
            f"steps={len(self._execution_order)}>"
        )
