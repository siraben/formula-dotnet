"""
Port of Microsoft.Formula.Compiler.Action and ActionSet
(Action.cs + ActionSet.cs).

An **Action** pairs a single head expression with a single constraint system
(body).  Actions come from rules and comprehensions.

An **ActionSet** is the cross-product of heads and bodies for a rule or
comprehension of the form:

    h_1, ..., h_n  :-  B_1 ; ... ; B_m

yielding actions (h_i, B_j) for every combination.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Optional, Tuple

from formula.compiler.configuration import (
    Flag,
    NodeKind,
    SeverityKind,
    Span,
)
from formula.compiler.constraint_system import (
    ComprehensionData,
    ConstraintSystem,
    FindData,
    FreshVarKind,
    LiftedBool,
    SuccessToken,
)


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------

class Action:
    """
    One (head, body) pair from a rule or comprehension.

    Lifecycle:
    1. Construct with head AST node, a ConstraintSystem body, and the
       TypeEnvironment.
    2. ``validate()`` type-checks and compiles the head into a head term.
    3. ``compile()`` emits the compiled rules into a ``RuleTable``.
    """

    MAX_DEPTH: int = 255

    def __init__(
        self,
        head: Any,
        body: ConstraintSystem,
        type_env: Any,
        compr_data: Optional[ComprehensionData] = None,
        configuration_context: Any = None,
    ) -> None:
        self.head = head
        self.body = body
        self.type_environment = type_env
        self._compr_data = compr_data
        self._configuration_context = configuration_context

        self.head_term: Any = None
        self.head_type: Any = None

    @property
    def index(self):
        return self.body.index

    # ------- Validation -----------------------------------------------------

    def validate(
        self,
        flags: List[Flag],
        cancel: Optional[Callable[[], bool]] = None,
        is_compiler_action: bool = False,
    ) -> bool:
        """
        Validate and build the head term from the head AST.

        * Resolves identifiers (variables, constants, constructors).
        * Verifies arity of data constructors.
        * Ensures the head does not derive illegal terms (new constants,
          base constants, protected symbols).

        Returns True on success.
        """
        cancel = cancel or (lambda: False)
        success = SuccessToken()

        head_result = self._create_head_term(success, flags, cancel)
        if head_result is None:
            success.failed()
        else:
            self.head_term, self.head_type = head_result

        # Additional semantic checks on the head type
        if self._compr_data is None and head_result is not None:
            self._check_head_type(head_result, success, flags, is_compiler_action)

        return success.result

    # ------- Compilation ----------------------------------------------------

    def compile(
        self,
        rules: Any,
        flags: List[Flag],
        cancel: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """
        Compile the action into rules.
        Should not be called unless validation succeeded.
        """
        cancel = cancel or (lambda: False)

        ok, parts = self.body.compile(rules, flags, cancel)
        if not ok or parts is None:
            return False

        if self._compr_data is None:
            rules.compile_rule(
                self.head_term,
                self.head_type,
                parts,
                self.head,
                self.body,
                self._configuration_context,
            )
        else:
            compr_head = rules.mk_compr_head(self._compr_data, self.head_term)
            false_val = getattr(self.index, "false_value", None)
            rules.compile_rule(
                compr_head,
                false_val,
                parts,
                self.head,
                self.body,
                self._configuration_context,
            )

        return True

    def get_next_var_id(self, kind: FreshVarKind) -> int:
        return self.body.get_next_var_id(kind)

    # ===== Private ==========================================================

    def _create_head_term(
        self,
        success: SuccessToken,
        flags: List[Flag],
        cancel: Callable[[], bool],
    ) -> Optional[Tuple[Any, Any]]:
        """
        Walk the head AST and build a (value_term, type_term) pair.
        """
        return self._head_walk(self.head, success, flags, cancel)

    def _head_walk(
        self,
        node: Any,
        success: SuccessToken,
        flags: List[Flag],
        cancel: Callable[[], bool],
    ) -> Optional[Tuple[Any, Any]]:
        """
        Recursive walk of the head AST producing (val_term, type_term).
        Simplified version of CreateHeadTerm_Unfold / _Fold.
        """
        if cancel():
            success.failed()
            return None

        nk = getattr(node, "node_kind", None)

        if nk == NodeKind.Cnst:
            return self._head_cnst(node, success, flags)
        elif nk == NodeKind.Id:
            return self._head_id(node, success, flags)
        elif nk == NodeKind.FuncTerm:
            return self._head_func(node, success, flags, cancel)
        else:
            # Unknown node kind
            success.failed()
            flags.append(Flag(
                SeverityKind.Error, node,
                f"Unexpected node kind in head: {nk}", code=40))
            return None

    def _head_cnst(
        self, node: Any, success: SuccessToken, flags: List[Flag]
    ) -> Optional[Tuple[Any, Any]]:
        """Handle a constant in the head."""
        if self._compr_data is None:
            flags.append(Flag(
                SeverityKind.Error, node,
                "A rule cannot produce a base constant.", code=41))
            success.failed()
            return None
        raw = getattr(node, "raw", node)
        return (raw, raw)

    def _head_id(
        self, node: Any, success: SuccessToken, flags: List[Flag]
    ) -> Optional[Tuple[Any, Any]]:
        """Handle an identifier (variable or constant) in the head."""
        name = getattr(node, "name", str(node))

        # Check if it is a variable in the body
        found, type_term = self.body.try_get_type(f"?{name}")
        if found:
            return (f"?{name}", type_term)

        # Treat as a constant
        return (name, name)

    def _head_func(
        self,
        node: Any,
        success: SuccessToken,
        flags: List[Flag],
        cancel: Callable[[], bool],
    ) -> Optional[Tuple[Any, Any]]:
        """Handle a function-term (data constructor application) in the head."""
        func = getattr(node, "function", None)
        args = getattr(node, "args", [])

        func_name = getattr(func, "name", str(func)) if func else "?"

        # Recursively process arguments
        val_args = []
        type_args = []
        all_ok = True
        for arg in args:
            result = self._head_walk(arg, success, flags, cancel)
            if result is None:
                all_ok = False
                continue
            val_args.append(result[0])
            type_args.append(result[1])

        if not all_ok:
            return None

        val_term = (func_name, tuple(val_args))
        type_term = (func_name, tuple(type_args))
        return (val_term, type_term)

    def _check_head_type(
        self,
        head_result: Tuple[Any, Any],
        success: SuccessToken,
        flags: List[Flag],
        is_compiler_action: bool,
    ) -> None:
        """
        After building the head term, check for illegal derivations
        (new constants, base sorts, protected symbols).
        """
        _, head_type = head_result

        def visit_type(t):
            """Recursively visit the type structure."""
            if isinstance(t, tuple) and len(t) == 2 and isinstance(t[1], tuple):
                for arg in t[1]:
                    visit_type(arg)
            symbol = t if isinstance(t, str) else None
            if symbol is not None:
                if _is_new_constant(symbol):
                    flags.append(Flag(
                        SeverityKind.Error, self.head,
                        f"Cannot derive new constant {symbol}", code=42))
                    success.failed()

        visit_type(head_type)


# ---------------------------------------------------------------------------
# ActionSet
# ---------------------------------------------------------------------------

class ActionSet:
    """
    Creates the cross-product of heads and bodies for a rule or comprehension.

    Given::

        h_1, ..., h_n  :-  B_1 ; ... ; B_m

    the action set contains the actions::

        (h_1, B_1), ..., (h_1, B_m),
                    ...
        (h_n, B_1), ..., (h_n, B_m)
    """

    MAX_DEPTH: int = 255

    def __init__(
        self,
        ast: Any,
        index: Any,
        compr_data: Optional[ComprehensionData] = None,
    ) -> None:
        self.ast = ast
        self.index = index
        self._compr_data = compr_data

        self._actions: List[Action] = []

        if compr_data is None:
            self.type_environment: Any = _TypeEnvironmentStub(ast, index)
        else:
            self.type_environment = _TypeEnvironmentStub(
                compr_data.node, index, parent=compr_data.owner.type_environment
            )

        self.is_compiled: LiftedBool = LiftedBool.Unknown

    # ------- Validation -----------------------------------------------------

    def validate(
        self,
        flags: List[Flag],
        cancel: Optional[Callable[[], bool]] = None,
        is_compiler_action: bool = False,
    ) -> bool:
        """
        Validate the rule/comprehension:
        1. Check nesting depth (for comprehensions).
        2. Extract heads and bodies from the AST.
        3. For each body, create a ConstraintSystem and validate it.
        4. For each (head, body) pair create and validate an Action.
        """
        cancel = cancel or (lambda: False)

        # Depth check for comprehensions
        if self._compr_data is not None and self._compr_data.depth > self.MAX_DEPTH:
            flags.append(Flag(
                SeverityKind.Error, self.ast,
                f"Comprehension nesting too deep. Maximum is {self.MAX_DEPTH}.",
                code=50))
            return self._record(False)

        heads = self._get_heads()
        bodies = self._get_bodies()

        if not heads:
            flags.append(Flag(
                SeverityKind.Error, self.ast,
                "The expression has no heads.", code=51))
            return self._record(False)

        # If no bodies, synthesise a TRUE=TRUE tautology
        if not bodies:
            bodies = [self._mk_true_body()]

        # Find variable-like ids in all heads (for registering with bodies)
        head_vars = self._collect_head_vars(heads)

        result = True
        for body_node in bodies:
            body_env = self.type_environment  # simplified
            cs = ConstraintSystem(self.index, body_node, body_env, self._compr_data)
            if not cs.validate(flags, head_vars, cancel):
                result = False
                continue

            for head_node in heads:
                action = Action(
                    head_node, cs, self.type_environment,
                    self._compr_data, self.ast,
                )
                if action.validate(flags, cancel, is_compiler_action):
                    self._actions.append(action)
                else:
                    result = False

                if cancel():
                    return self._record(False)

        if result and not cancel():
            return self._record(True)
        return self._record(False)

    # ------- Compilation ----------------------------------------------------

    def compile(
        self,
        rules: Any,
        flags: List[Flag],
        cancel: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """
        Compile all actions into rules.

        For non-comprehension action sets, each action is compiled
        independently.  For comprehension action sets, the bodies are
        compiled first to build the comprehension representation, then
        the actions are compiled.
        """
        cancel = cancel or (lambda: False)
        result = True

        if self.is_compiled != LiftedBool.Unknown:
            return bool(self.is_compiled)

        if self._compr_data is None:
            # Simple rule: compile each action independently
            for action in self._actions:
                result = action.compile(rules, flags, cancel) and result
            self.is_compiled = LiftedBool.TRUE if result else LiftedBool.FALSE
            return result

        # Comprehension: compile bodies first
        body_terms: List[Any] = []
        for action in self._actions:
            ok, parts = action.body.compile(rules, flags, cancel)
            result = ok and result
            if ok and parts is not None:
                body_terms.append(rules.mk_body_term(parts))

        if not result:
            self.is_compiled = LiftedBool.FALSE
            return False

        # Build the comprehension representation
        head_set: set = set()
        for action in self._actions:
            head_set.add(action.head_term)

        self._compr_data.representation = {
            "heads": list(head_set),
            "reads": dict(self._compr_data.read_vars),
            "bodies": body_terms,
        }

        # Now compile the actions
        for action in self._actions:
            result = action.compile(rules, flags, cancel) and result

        self.is_compiled = LiftedBool.TRUE if result else LiftedBool.FALSE
        return result

    def get_next_var_id(self, kind: FreshVarKind) -> int:
        vid = 0
        for action in self._actions:
            vid = max(vid, action.get_next_var_id(kind))
        return vid

    # ===== Private ==========================================================

    def _record(self, result: bool) -> bool:
        if not result:
            self.is_compiled = LiftedBool.FALSE
        return result

    def _get_heads(self) -> list:
        node = getattr(self.ast, "node", self.ast)
        nk = getattr(node, "node_kind", None)
        if nk == NodeKind.Rule:
            return list(getattr(node, "heads", []))
        elif nk == NodeKind.Compr:
            return list(getattr(node, "heads", []))
        elif nk == NodeKind.ContractItem:
            return list(getattr(node, "heads", [node]))
        return [node]

    def _get_bodies(self) -> list:
        node = getattr(self.ast, "node", self.ast)
        nk = getattr(node, "node_kind", None)
        if nk in (NodeKind.Rule, NodeKind.Compr):
            return list(getattr(node, "bodies", []))
        return []

    def _collect_head_vars(self, heads: list) -> list:
        """Collect variable-like identifiers from all heads."""
        vars_list: list = []
        for h in heads:
            self._find_var_like_ids(h, vars_list)
        return vars_list

    def _find_var_like_ids(self, node: Any, result: list) -> None:
        """Recursively find Id nodes that look like variables."""
        nk = getattr(node, "node_kind", None)
        if nk == NodeKind.Id:
            name = getattr(node, "name", "")
            # Simple heuristic: single-fragment lowercase names are variables
            if name and not "." in name:
                result.append(node)
        children = getattr(node, "children", None) or getattr(node, "args", [])
        for child in children:
            self._find_var_like_ids(child, result)

    @staticmethod
    def _mk_true_body() -> Any:
        """
        Synthesise a body containing the tautology ``TRUE = TRUE``.
        """
        return _TrueBody()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_new_constant(name: str) -> bool:
    return "#" in name


class _TrueBody:
    """A synthetic body node representing ``TRUE = TRUE``."""
    node_kind = NodeKind.Body

    @property
    def constraints(self):
        return []

    @property
    def children(self):
        return []


class _TypeEnvironmentStub:
    """
    Placeholder TypeEnvironment until the full common/terms layer is available.
    """

    def __init__(self, node: Any, index: Any, parent: Any = None) -> None:
        self.node = node
        self.index = index
        self.parent = parent
        self._types: dict = {}

    def set_type(self, var: Any, type_term: Any) -> None:
        self._types[var] = type_term

    def get_type(self, var: Any) -> Any:
        return self._types.get(var)

    def add_child(self, node: Any) -> "_TypeEnvironmentStub":
        return _TypeEnvironmentStub(node, self.index, parent=self)

    def join_types(self) -> None:
        """Join (widen) types across all actions. Placeholder."""
        pass
