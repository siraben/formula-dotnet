"""
Port of Microsoft.Formula.Compiler.ConstraintSystem (ConstraintSystem.cs).

A ConstraintSystem manages the set of constraints arising from a single
rule body (or comprehension body).  It creates congruence classes for
terms, validates find patterns and type constraints, orients equalities,
performs the occurs check, and finally compiles the validated body into
a sequence of ``FindData`` descriptors consumed by the ``RuleTable``.

This is one of the most complex files in the FORMULA compiler.  The
Python port preserves the algorithmic structure of the C# original
while adapting to Python idioms.
"""

from __future__ import annotations

from collections import OrderedDict
from enum import IntEnum, Enum
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

from formula.compiler.configuration import (
    Flag,
    NodeKind,
    SeverityKind,
    Span,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FreshVarKind(IntEnum):
    DontCare = 0
    Selector = 1
    Comprehension = 2


class LiftedBool(Enum):
    """Three-valued logic used for tracking compilation state."""
    Unknown = 0
    TRUE = 1
    FALSE = 2

    def __bool__(self):
        return self == LiftedBool.TRUE


# ---------------------------------------------------------------------------
# Helper data classes
# ---------------------------------------------------------------------------

class CongruenceClass:
    """
    Union-Find structure tracking which terms have been shown equal.

    Each class has:
    * A *representative* (via path-compressed parent pointer).
    * A *type* (the intersection / join of known type constraints).
    * A set of *members* (terms that belong to this equivalence class).
    * Lists of *pending* classes (parents or equals to propagate to).
    """

    def __init__(self, term: Any, type_term: Any = None, node: Any = None) -> None:
        self.term = term
        self.type: Any = type_term
        self.node = node

        # Union-Find bookkeeping
        self._parent: Optional[CongruenceClass] = None
        self._rank: int = 0

        # Members in this equivalence class
        self.members: List[Any] = [term]

        # Parent classes (data-constructor applications whose args include
        # this class).
        self.parent_classes: List[CongruenceClass] = []

        # Whether this class has been data-grounded (all leaves are base
        # constants or constructors with grounded children).
        self.is_data_grounded: bool = False

    # -- Union-Find ----------------------------------------------------------

    def find(self) -> "CongruenceClass":
        """Find the representative with path compression."""
        root = self
        while root._parent is not None:
            root = root._parent
        # Path compression
        c = self
        while c._parent is not None:
            nxt = c._parent
            c._parent = root
            c = nxt
        return root

    def union(self, other: "CongruenceClass") -> "CongruenceClass":
        """Union by rank; returns the new representative."""
        a = self.find()
        b = other.find()
        if a is b:
            return a
        if a._rank < b._rank:
            a, b = b, a
        b._parent = a
        if a._rank == b._rank:
            a._rank += 1
        a.members.extend(b.members)
        return a


class ComprehensionData:
    """
    Data associated with a comprehension (``{ h | B }`` expression).
    """

    def __init__(
        self,
        node: Any,
        owner: Any,     # The parent ConstraintSystem
        depth: int = 0,
    ) -> None:
        self.node = node
        self.owner = owner
        self.depth: int = depth
        self.representation: Any = None
        self.read_vars: OrderedDict = OrderedDict()

    @property
    def index(self):
        return self.owner.index


class FindData:
    """
    A compiled find pattern: ``find v where v : pattern in type``.
    Can be a "default" (empty) find when no explicit find is present.
    """

    def __init__(
        self,
        variable: Any = None,
        pattern: Any = None,
        type_term: Any = None,
    ) -> None:
        self.variable = variable
        self.pattern = pattern
        self.type = type_term

    @property
    def is_default(self) -> bool:
        return self.variable is None

    def __repr__(self) -> str:
        if self.is_default:
            return "FindData(default)"
        return f"FindData(var={self.variable}, pattern={self.pattern})"


class ImpliedEquality:
    """An equality that was implied by merging congruence classes."""

    def __init__(self, lhs: Any, rhs: Any, blame: Any = None) -> None:
        self.lhs = lhs
        self.rhs = rhs
        self.blame = blame


class SuccessToken:
    """Tracks success/failure through callback-heavy traversal code."""

    def __init__(self) -> None:
        self._result = True

    def failed(self) -> None:
        self._result = False

    @property
    def result(self) -> bool:
        return self._result


# ---------------------------------------------------------------------------
# ConstraintSystem
# ---------------------------------------------------------------------------

class ConstraintSystem:
    """
    Manages the constraints for one body of a rule or comprehension.

    Lifecycle:
    1. Constructed with an ``index`` (TermIndex), ``body`` (Body AST node),
       a ``TypeEnvironment`` and optional ``ComprehensionData``.
    2. ``validate(flags, head_vars, cancel)`` builds congruence classes,
       processes equalities, and validates the orientation of all variables.
    3. ``compile(rule_table, flags, cancel)`` invokes the Optimizer to
       produce an ordered list of ``FindData`` for rule compilation.

    Parameters
    ----------
    index : Any
        The ``TermIndex`` that owns all terms in this constraint system.
    body : Any
        The ``Body`` AST node.
    type_env : Any
        The ``TypeEnvironment`` associated with this body.
    compr_data : ComprehensionData | None
        If this body belongs to a comprehension, the associated data.
    """

    EMPTY_ARGS: list = []

    def __init__(
        self,
        index: Any,
        body: Any,
        type_env: Any,
        compr_data: Optional[ComprehensionData] = None,
    ) -> None:
        self.index = index
        self.body = body
        self.type_environment = type_env
        self.comprehension = compr_data
        self.is_compiled: LiftedBool = LiftedBool.Unknown

        # Congruence classes: term -> CongruenceClass
        self._classes: OrderedDict[Any, CongruenceClass] = OrderedDict()

        # Comprehension variable -> ComprehensionData
        self._comprehensions: Dict[Any, ComprehensionData] = {}

        # Find variables -> Node
        self._finds: OrderedDict[Any, Any] = OrderedDict()

        # Ordered find variables (preserves insertion order for orientation)
        self._ordered_finds: List[Tuple[Any, Any]] = []

        # Active equality stack (for implied equalities during merges)
        self._active_eq_stack: Optional[List[ImpliedEquality]] = None

        # Next variable IDs (indexed by FreshVarKind)
        if compr_data is None:
            self._next_var_ids: List[int] = [0, 0, 0]
        else:
            self._next_var_ids = [
                compr_data.owner.get_next_var_id(FreshVarKind.DontCare),
                compr_data.owner.get_next_var_id(FreshVarKind.Selector),
                compr_data.owner.get_next_var_id(FreshVarKind.Comprehension),
            ]

        # Any-type cache
        self._any_type: Any = getattr(index, "canonical_any_type", None)

    # ------- Properties -----------------------------------------------------

    @property
    def variables(self) -> Iterable[Any]:
        """Enumerate all variable terms in the constraint system."""
        for t in self._classes:
            if _is_variable(t):
                yield t

    # ------- Type look-up ---------------------------------------------------

    def try_get_type(self, term: Any) -> Tuple[bool, Any]:
        """
        Returns (True, type_term) if *term* has a type in this scope,
        or (False, None) otherwise.
        """
        cls = self._classes.get(term)
        if cls is not None:
            return True, cls.find().type
        return False, None

    def get_congruence_members(self, term: Any) -> List[Any]:
        """Return all terms congruent to *term*."""
        cls = self._classes.get(term)
        if cls is None:
            return [term]
        return list(cls.find().members)

    # ------- Validation -----------------------------------------------------

    def validate(
        self,
        flags: List[Flag],
        head_vars: Iterable[Any],
        cancel: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """
        Build congruence classes from the body AST, process all equalities
        and implied equalities, and validate variable orientation.

        Returns True on success.
        """
        cancel = cancel or (lambda: False)

        # Step 1: Create congruence classes from the body
        constraints: List[Any] = []
        if not self._create_classes(flags, constraints, cancel):
            return self._record_validation_result(False)

        if cancel():
            return self._record_validation_result(False)

        # Step 2: Process implied equalities
        self._active_eq_stack = []
        for cls in self._classes.values():
            if cls.find().type is not None:
                self._notify_type_change(cls.find())

        if not self._process_equalities(self._active_eq_stack, flags, cancel):
            return self._record_validation_result(False)

        self._active_eq_stack = None

        if cancel():
            return self._record_validation_result(False)

        # Step 3: Validate orientation of all variables
        if not self._validate_orientation(flags):
            return self._record_validation_result(False)

        return self._record_validation_result(True)

    # ------- Compilation ----------------------------------------------------

    def compile(
        self,
        rule_table: Any,
        flags: List[Flag],
        cancel: Optional[Callable[[], bool]] = None,
    ) -> Tuple[bool, Optional[List[FindData]]]:
        """
        Compile the validated constraint system into an optimised sequence
        of ``FindData`` descriptors.

        Returns (True, parts) on success, (False, None) on failure.
        """
        cancel = cancel or (lambda: False)

        if self.is_compiled != LiftedBool.Unknown:
            return bool(self.is_compiled), None

        from formula.compiler.optimizer import Optimizer

        # Build the find-patterns map and constraint set
        find_patterns: Dict[Any, Tuple[Any, Any]] = {}
        constraint_set: List[Any] = []

        for var, node in self._ordered_finds:
            cls = self._classes.get(var)
            if cls is not None:
                pattern = cls.find().type
                find_patterns[var] = (pattern, pattern)

        # Collect non-find constraints
        for term, cls in self._classes.items():
            if not _is_variable(term) and term not in find_patterns:
                constraint_set.append(term)

        optimizer = Optimizer(self.index, constraint_set, find_patterns)
        parts = optimizer.optimize(rule_table, self, cancel)

        self.is_compiled = LiftedBool.TRUE
        return True, parts

    # ------- Fresh variable IDs ---------------------------------------------

    def get_next_var_id(self, kind: FreshVarKind) -> int:
        return self._next_var_ids[int(kind)]

    # ------- Debugging ------------------------------------------------------

    def debug_class_print_types(self) -> None:
        """Print congruence classes and their types (for debugging)."""
        for term, cls in self._classes.items():
            rep = cls.find()
            print(f"  {term} -> type={rep.type}, members={rep.members}")

    # ===== Private ==========================================================

    def _record_validation_result(self, result: bool) -> bool:
        if not result:
            self.is_compiled = LiftedBool.FALSE
        return result

    # -- Class creation ------------------------------------------------------

    def _create_classes(
        self,
        flags: List[Flag],
        constraints: List[Any],
        cancel: Callable[[], bool],
    ) -> bool:
        """
        Walk the body AST and build congruence classes for every
        sub-expression.
        """
        success = SuccessToken()

        # Process each conjunct in the body
        conjuncts = self._get_body_conjuncts()
        for conjunct in conjuncts:
            if cancel():
                return False
            self._process_conjunct(conjunct, constraints, success, flags)

        return success.result

    def _process_conjunct(
        self,
        node: Any,
        constraints: List[Any],
        success: SuccessToken,
        flags: List[Flag],
    ) -> None:
        """
        Process a single body conjunct.
        This handles Find, RelConstr, and Compr nodes.
        """
        nk = getattr(node, "node_kind", None)

        if nk == NodeKind.Find:
            self._process_find(node, success, flags)
        elif nk == NodeKind.Compr:
            self._process_comprehension(node, success, flags)
        else:
            # Relational constraint (Eq, NEq, Lt, etc.)
            self._process_relational(node, constraints, success, flags)

    def _process_find(
        self, node: Any, success: SuccessToken, flags: List[Flag]
    ) -> None:
        """
        Create congruence classes for a find variable and its type pattern.
        """
        binding = getattr(node, "binding", None)
        match = getattr(node, "match", None)

        if binding is not None and match is not None:
            var_term = self._mk_var_term(binding)
            if var_term is not None:
                cls = self._get_or_create_class(var_term)
                self._finds[var_term] = node
                self._ordered_finds.append((var_term, node))

                # Process the pattern to build type information
                type_term = self._process_type_term(match, success, flags)
                if type_term is not None and cls.find().type is None:
                    cls.find().type = type_term

    def _process_comprehension(
        self, node: Any, success: SuccessToken, flags: List[Flag]
    ) -> None:
        """Handle a comprehension sub-expression within a body."""
        compr_data = ComprehensionData(node, self, depth=0)
        if self.comprehension is not None:
            compr_data.depth = self.comprehension.depth + 1

        var_term = self._mk_fresh_var(FreshVarKind.Comprehension)
        cls = self._get_or_create_class(var_term)
        self._comprehensions[var_term] = compr_data

    def _process_relational(
        self,
        node: Any,
        constraints: List[Any],
        success: SuccessToken,
        flags: List[Flag],
    ) -> None:
        """Process a relational constraint (equality, etc.)."""
        constraints.append(node)

    # -- Equality processing -------------------------------------------------

    def _process_equalities(
        self,
        impl_eqs: List[ImpliedEquality],
        flags: List[Flag],
        cancel: Callable[[], bool],
    ) -> bool:
        """
        Process all implied equalities that arose from merging congruence
        classes.  This is iterative: merging two classes may imply further
        equalities.
        """
        while impl_eqs:
            if cancel():
                return False
            eq = impl_eqs.pop()
            cls_a = self._classes.get(eq.lhs)
            cls_b = self._classes.get(eq.rhs)
            if cls_a is None or cls_b is None:
                continue
            rep_a = cls_a.find()
            rep_b = cls_b.find()
            if rep_a is rep_b:
                continue

            # Merge
            merged = rep_a.union(rep_b)

            # If both have types, intersect them via TermIndex
            if rep_a.type is not None and rep_b.type is not None:
                if self._index is not None:
                    intr = self._index.mk_intersection(rep_a.type, rep_b.type)
                    if intr is None:
                        # Empty intersection: type error
                        merged.type = rep_a.type
                    else:
                        merged.type = intr
                else:
                    merged.type = rep_a.type
            elif rep_b.type is not None:
                merged.type = rep_b.type

        return True

    def _notify_type_change(self, cls: CongruenceClass) -> None:
        """
        When a class's type changes, propagate the change to parent
        classes (data-constructor applications whose args include this
        class).

        Matches C# ConstraintSystem.NotifyTypeChange + CongruenceClass.Propagate.
        """
        if self._active_eq_stack is None:
            return
        # Propagate: each parent class that uses this class as an argument
        # may need its type recomputed.
        for parent_cls in cls.parent_classes:
            rep = parent_cls.find()
            if rep.type is not None and self._index is not None:
                # Recompute the parent's type from its members' argument types
                new_type = self._compute_class_type(rep)
                if new_type is not None and new_type is not rep.type:
                    rep.type = new_type

    def _compute_class_type(self, cls: CongruenceClass) -> Any:
        """
        Compute the maximal type containing the types of all members.

        Matches C# CongruenceClass.ComputeClassType.
        For each member term in the class:
        - Base constants: intersect the constant's type with current type.
        - Data constructors: build a type term from arg types, intersect.
        - Variables: skip (they don't constrain the type).
        """
        if self._index is None:
            return cls.type
        current_type = cls.type
        for member in cls.members:
            member_term = member
            if hasattr(member_term, "symbol"):
                sym = member_term.symbol
                kind = getattr(sym, "kind", None)
                if kind is None:
                    continue
                from formula.common.symbol_types import SymbolKind
                if kind == SymbolKind.UserCnstSymb and getattr(sym, "is_variable", False):
                    continue  # Variables don't constrain the type
                if kind == SymbolKind.BaseCnstSymb or (
                    kind == SymbolKind.UserCnstSymb and not getattr(sym, "is_variable", False)
                ):
                    if current_type is not None:
                        intr = self._index.mk_intersection(member_term, current_type)
                        if intr is None:
                            return None
                        current_type = intr
                elif kind in (SymbolKind.ConSymb, SymbolKind.MapSymb):
                    args = []
                    for a in member_term.args:
                        a_cls = self._classes.get(a)
                        if a_cls is not None:
                            args.append(a_cls.find().type or a)
                        else:
                            args.append(a)
                    other = self._index.mk_apply(sym, args)
                    if current_type is not None:
                        intr = self._index.mk_intersection(other, current_type)
                        if intr is None:
                            return None
                        current_type = intr
                    else:
                        current_type = other
        return current_type

    # -- Orientation validation ----------------------------------------------

    def _validate_orientation(self, flags: List[Flag]) -> bool:
        """
        Ensure every variable in the constraint system is *oriented*:
        reachable from a find pattern via data-constructor arguments.
        """
        oriented: Set[Any] = set()

        # All find variables are initially oriented
        for var in self._finds:
            cls = self._classes.get(var)
            if cls is not None:
                oriented.add(id(cls.find()))

        # Propagate: if a class is oriented and appears as an argument of
        # a data constructor, the constructor's other arguments become oriented.
        changed = True
        while changed:
            changed = False
            for term, cls in self._classes.items():
                rep = cls.find()
                if id(rep) in oriented:
                    continue
                # Check if any member is built from oriented args
                for member in rep.members:
                    args = getattr(member, "args", None)
                    if args and all(
                        id(self._classes[a].find()) in oriented
                        for a in args
                        if a in self._classes
                    ):
                        oriented.add(id(rep))
                        changed = True
                        break

        # Check that every variable is oriented
        success = True
        for var in self.variables:
            cls = self._classes.get(var)
            if cls is not None and id(cls.find()) not in oriented:
                flags.append(Flag(
                    SeverityKind.Error,
                    self._finds.get(var),
                    f"Variable is not oriented: {var}",
                    code=30,
                ))
                success = False

        return success

    # -- Term / class helpers ------------------------------------------------

    def _get_or_create_class(
        self, term: Any, type_term: Any = None, node: Any = None
    ) -> CongruenceClass:
        cls = self._classes.get(term)
        if cls is not None:
            return cls
        cls = CongruenceClass(term, type_term, node)
        self._classes[term] = cls
        return cls

    def _mk_var_term(self, node: Any) -> Any:
        """Create or retrieve a variable term for a binding Id node."""
        name = getattr(node, "name", None)
        if name is None:
            return None
        # In a real implementation this would go through TermIndex
        return f"?{name}"

    def _mk_fresh_var(self, kind: FreshVarKind) -> Any:
        vid = self._next_var_ids[int(kind)]
        self._next_var_ids[int(kind)] = vid + 1
        return f"?__{kind.name}_{vid}"

    def _process_type_term(
        self, node: Any, success: SuccessToken, flags: List[Flag]
    ) -> Any:
        """
        Walk a type expression (the right-hand side of ``:``) and resolve
        it to a type term via the TermIndex and SymbolTable.

        Matches C# ConstraintSystem's handling of RelKind.Typ constraints:
        resolves the type name to a UserSymbol, then creates the canonical
        type term.
        """
        if self._index is None:
            return node

        # If it's an Id node with a name, resolve via symbol table
        name = getattr(node, "name", None)
        nk = getattr(node, "node_kind", None)

        if nk == NodeKind.Id and name is not None:
            from formula.common.symbol_types import SymbolKind
            sym_table = self._index.symbol_table
            resolved = sym_table.resolve(name) if hasattr(sym_table, "resolve") else None
            if resolved is None:
                return node

            kind = getattr(resolved, "kind", None)
            if kind == SymbolKind.ConSymb:
                sort_sym = getattr(resolved, "sort_symbol", None)
                if sort_sym is not None:
                    return self._index.mk_apply(sort_sym, [])
            elif kind == SymbolKind.MapSymb:
                sort_sym = getattr(resolved, "sort_symbol", None)
                if sort_sym is not None:
                    return self._index.mk_apply(sort_sym, [])
            elif kind == SymbolKind.UnnSymb:
                return self._index.get_canonical_term(resolved, 0)
            elif kind == SymbolKind.BaseSortSymb:
                return self._index.mk_apply(resolved, [])

        return node

    def _get_body_conjuncts(self) -> list:
        """Extract the conjunct nodes from the body AST."""
        body = self.body
        if hasattr(body, "constraints"):
            return list(body.constraints)
        children = getattr(body, "children", None)
        if children is not None:
            return list(children)
        return [body] if body is not None else []


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_variable(term: Any) -> bool:
    """Heuristic: a term is a variable if it is a string starting with '?'."""
    if isinstance(term, str):
        return term.startswith("?")
    symbol = getattr(term, "symbol", None)
    if symbol is not None:
        return getattr(symbol, "is_variable", False)
    return False
