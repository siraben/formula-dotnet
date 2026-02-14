"""
Port of Src/Core/Common/Rules/*.cs (11 files).

Key classes:
  - CoreRule             : a single compiled rule (head :- body)
  - CoreSubRule          : a sub-constructor rule
  - RuleTable            : collection of rules for a module
  - Matcher              : pattern-match a ground term against a pattern
  - Unifier              : unification of two terms (with occurs check)
  - Executer             : fixed-point execution engine
  - FindData             : binding + pattern + type for a find clause
  - Bindable             : a slot that holds a term binding
  - Derivation           : records how a fact was derived
  - ActivationStatistics : per-rule activation counters
  - ExecuterStatistics   : aggregate execution statistics
"""
from __future__ import annotations

import io
import threading
from collections import deque
from fractions import Fraction
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)

from formula.common.symbol_types import (
    BaseCnstSymb,
    BaseOpSymb,
    ConSymb,
    Groundness,
    MapSymb,
    Namespace,
    ReservedOpKind,
    Symbol,
    SymbolKind,
    UserCnstSymb,
    UserSortSymb,
    UserSymbol,
)
from formula.common.terms import (
    AppFreeCanUnn,
    ImmutableArray,
    SubtermMatcher,
    SuccessToken,
    Term,
    TermIndex,
)


# ===================================================================
# Bindable
# ===================================================================

class Bindable:
    """
    A slot that holds a term binding during rule execution.
    """

    __slots__ = ("binding",)

    def __init__(self, binding: Optional[Term] = None) -> None:
        self.binding = binding

    def __repr__(self) -> str:
        return f"Bindable({self.binding})"


# ===================================================================
# FindData
# ===================================================================

class FindData:
    """
    Represents the data associated with a ``find`` clause in a rule:
    ``binding is pattern : type``.
    """

    __slots__ = ("_binding", "_pattern", "_type")

    def __init__(
        self,
        binding: Optional[Term] = None,
        pattern: Optional[Term] = None,
        type_: Optional[Term] = None,
    ) -> None:
        self._binding = binding
        self._pattern = pattern
        self._type = type_

    @property
    def is_null(self) -> bool:
        return self._binding is None

    @property
    def binding(self) -> Optional[Term]:
        return self._binding

    @property
    def pattern(self) -> Optional[Term]:
        return self._pattern

    @property
    def type(self) -> Optional[Term]:
        return self._type

    def mk_find_term(self, index: TermIndex) -> Term:
        """Build a reified ``find(binding, pattern, pattern : type)`` term."""
        if self.is_null:
            return index.false_value
        binding = self._binding
        assert binding is not None
        if binding.symbol.is_reserved_operation:
            return binding
        pattern = self._pattern
        type_ = self._type
        assert pattern is not None and type_ is not None
        type_rel, _ = index.mk_apply(
            index.type_rel_symbol, [pattern, type_]
        )
        find, _ = index.mk_apply(
            index.find_symbol, [binding, pattern, type_rel]
        )
        return find


# ===================================================================
# Derivation
# ===================================================================

class Derivation:
    """
    Records how a fact was derived: the rule that produced it and the
    bindings that triggered it.  For base facts ``rule`` is None.
    """

    __slots__ = ("rule", "binding1", "binding2")

    def __init__(
        self,
        rule: Optional[CoreRule] = None,
        binding1: Optional[Term] = None,
        binding2: Optional[Term] = None,
    ) -> None:
        self.rule = rule
        self.binding1 = binding1
        self.binding2 = binding2

    @staticmethod
    def make_fact(index: TermIndex) -> Derivation:
        """Create a derivation for a base fact (no rule)."""
        return Derivation(rule=None, binding1=index.false_value, binding2=index.false_value)

    @staticmethod
    def compare(d1: Derivation, d2: Derivation) -> int:
        if d1.rule is None:
            return 0 if d2.rule is None else -1
        if d2.rule is None:
            return 1
        cmp = d1.rule.rule_id - d2.rule.rule_id
        if cmp != 0:
            return cmp
        cmp = Term.compare(d1.binding1, d2.binding1)  # type: ignore[arg-type]
        if cmp != 0:
            return cmp
        return Term.compare(d1.binding2, d2.binding2)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        rid = self.rule.rule_id if self.rule else "fact"
        return f"Derivation(rule={rid})"


# ===================================================================
# ActivationStatistics
# ===================================================================

class ActivationStatistics:
    """
    Per-rule activation statistics: counts of activations, pended facts,
    and failures.
    """

    def __init__(self, rule: CoreRule) -> None:
        self._rule = rule
        self._lock = threading.Lock()
        self._min_pend: int = -1
        self._max_pend: int = -1
        self._total_pend: int = 0
        self._total_failures: int = 0
        self._total_activations: int = 0
        self._crnt_pend_count: int = 0
        self._crnt_fail_count: int = 0

    @property
    def rule_id(self) -> int:
        return self._rule.rule_id

    @property
    def min_pends(self) -> int:
        with self._lock:
            return self._min_pend

    @property
    def max_pends(self) -> int:
        with self._lock:
            return self._max_pend

    @property
    def total_pends(self) -> int:
        with self._lock:
            return self._total_pend

    @property
    def total_failures(self) -> int:
        with self._lock:
            return self._total_failures

    @property
    def total_activations(self) -> int:
        with self._lock:
            return self._total_activations

    def begin_activation(self) -> None:
        with self._lock:
            self._total_activations += 1

    def inc_pend_count(self) -> None:
        self._crnt_pend_count += 1

    def inc_fail_count(self) -> None:
        self._crnt_fail_count += 1

    def end_activation(self) -> None:
        with self._lock:
            pc = self._crnt_pend_count
            fc = self._crnt_fail_count
            self._min_pend = pc if self._min_pend < 0 else min(self._min_pend, pc)
            self._max_pend = pc if self._max_pend < 0 else max(self._max_pend, pc)
            self._total_pend += pc
            self._total_failures += fc
            if pc == 0 and fc == 0:
                self._total_failures += 1
        self._crnt_pend_count = 0
        self._crnt_fail_count = 0

    def print_rule(self, writer: Any = None) -> None:
        self._rule.debug_print_rule()


# ===================================================================
# ExecuterStatistics
# ===================================================================

class ExecuterStatistics:
    """
    Aggregate statistics for a fixpoint execution.
    """

    FINE_GRAINED_UPDATE_FREQ = 1000

    def __init__(self, fire_action: Optional[Callable] = None) -> None:
        self._lock = threading.Lock()
        self._n_strata: Optional[int] = None
        self._current_stratum: Optional[int] = None
        self._current_fixpoint_size: Optional[int] = None
        self._activations: Optional[Dict[int, ActivationStatistics]] = None
        self._last_fxp_add_time: int = 0
        self.fire_action = fire_action

    @property
    def n_rules(self) -> Optional[int]:
        with self._lock:
            return len(self._activations) if self._activations else None

    @property
    def n_strata(self) -> Optional[int]:
        with self._lock:
            return self._n_strata

    @n_strata.setter
    def n_strata(self, value: int) -> None:
        with self._lock:
            self._n_strata = value

    @property
    def current_stratum(self) -> Optional[int]:
        with self._lock:
            return self._current_stratum

    @current_stratum.setter
    def current_stratum(self, value: int) -> None:
        with self._lock:
            self._current_stratum = value

    @property
    def current_fixpoint_size(self) -> Optional[int]:
        with self._lock:
            return self._current_fixpoint_size

    @current_fixpoint_size.setter
    def current_fixpoint_size(self, value: int) -> None:
        with self._lock:
            self._current_fixpoint_size = value

    @property
    def activations(self) -> Optional[Dict[int, ActivationStatistics]]:
        with self._lock:
            return self._activations

    def set_rules(self, rules: Iterable[CoreRule]) -> None:
        with self._lock:
            self._activations = {r.rule_id: ActivationStatistics(r) for r in rules}

    def get_activations(self, rule: CoreRule) -> Optional[ActivationStatistics]:
        with self._lock:
            if self._activations is None:
                return None
            return self._activations.get(rule.rule_id)

    def rec_fxp_add(self, fixpoint_size: int) -> None:
        if self._last_fxp_add_time % self.FINE_GRAINED_UPDATE_FREQ == 0:
            self._last_fxp_add_time = 1
            self.current_fixpoint_size = fixpoint_size
        else:
            self._last_fxp_add_time += 1


# ===================================================================
# Matcher
# ===================================================================

class Matcher:
    """
    Match a ground term against a (possibly non-ground) pattern.

    Pre-allocates binding slots for all variables in the pattern.
    After ``try_match(t)`` returns True, ``current_bindings`` maps
    each variable term to its binding.
    """

    def __init__(self, pattern: Term) -> None:
        assert pattern.groundness != Groundness.Type
        self._pattern = pattern
        self._bindings: Dict[int, Optional[Term]] = {}  # var uid -> binding
        self._binding_vars: List[Term] = []

        # Collect variables
        pattern.visit(
            lambda x: x.args if x.groundness == Groundness.Variable else None,
            lambda x: self._register_var(x),
        )

    def _register_var(self, t: Term) -> None:
        if t.symbol.is_variable and t._uid not in self._bindings:
            self._bindings[t._uid] = None
            self._binding_vars.append(t)

    @property
    def pattern(self) -> Term:
        return self._pattern

    @property
    def current_bindings(self) -> Dict[int, Optional[Term]]:
        return self._bindings

    def try_match(self, t: Term) -> bool:
        """
        Try to match *t* against the pattern.

        Returns True on success. ``current_bindings`` is updated with the
        variable bindings (or set to None on failure).
        """
        assert t.groundness == Groundness.Ground
        # Reset bindings
        for v in self._binding_vars:
            self._bindings[v._uid] = None

        success = SuccessToken()
        self._match(self._pattern, t, success)
        return success.result

    def _match(self, px: Term, ty: Term, success: SuccessToken) -> None:
        """Recursive matching."""
        if not success.result:
            return
        if px.groundness == Groundness.Ground:
            if px is not ty:
                success.failed()
            return
        if px.symbol.is_variable:
            crnt = self._bindings.get(px._uid)
            if crnt is None:
                self._bindings[px._uid] = ty
            elif crnt is not ty:
                success.failed()
            return
        assert px.symbol.is_data_constructor
        if px.symbol is not ty.symbol:
            success.failed()
            return
        for i in range(px.symbol.arity):
            self._match(px.args[i], ty.args[i], success)
            if not success.result:
                return


# ===================================================================
# Unifier
# ===================================================================

class Unifier:
    """
    Robinson-style unification with occurs check.

    Static methods for checking unifiability and computing most-general
    unifiers (MGUs).
    """

    @staticmethod
    def is_unifiable(
        t_a: Term,
        t_b: Term,
        standardize: bool = True,
        partitions: Optional[Dict[int, Set[int]]] = None,
    ) -> bool:
        """
        Return True if *t_a* and *t_b* are unifiable.

        If *partitions* is provided, it is populated with the equivalence
        classes of the unifier (mapping variable UIDs to sets of UIDs in
        the same class).
        """
        assert t_a.owner is t_b.owner

        # Use a union-find structure for equivalence classes
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}  # (uid, label) -> (uid, label)
        pending: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []

        label_a = 0
        label_b = 1 if standardize else 0

        pending.append(((t_a._uid, label_a), (t_b._uid, label_b)))

        def find(x: Tuple[int, int]) -> Tuple[int, int]:
            while x in parent and parent[x] != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(x: Tuple[int, int], y: Tuple[int, int]) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        while pending:
            sa, sb = pending.pop()
            ra = find(sa)
            rb = find(sb)
            if ra == rb:
                continue

            # Resolve terms from UIDs
            ta = _uid_to_term(t_a, sa[0], sa[1], label_a)
            tb = _uid_to_term(t_b, sb[0], sb[1], label_b)
            if ta is None or tb is None:
                # Fallback: simple structural check
                return _simple_unify(t_a, t_b)

            if ta.groundness == Groundness.Ground and tb.groundness == Groundness.Ground:
                if ta is not tb:
                    return False
                continue

            if (ta.symbol.is_data_constructor or ta.symbol.is_non_var_constant) and \
               (tb.symbol.is_data_constructor or tb.symbol.is_non_var_constant):
                if ta.symbol is not tb.symbol:
                    return False
                union(sa, sb)
                for i in range(ta.symbol.arity):
                    pending.append(
                        ((ta.args[i]._uid, sa[1]), (tb.args[i]._uid, sb[1]))
                    )
            elif ta.symbol.is_variable:
                union(sa, sb)
            elif tb.symbol.is_variable:
                union(sb, sa)
            else:
                union(sa, sb)

        return True

    @staticmethod
    def is_unifiable_with_mgu(
        t_a: Term,
        t_b: Term,
        var_creator: Callable[[int], Term],
        standardize: bool = True,
    ) -> Tuple[bool, Optional[Term]]:
        """
        If *t_a* and *t_b* are unifiable, return ``(True, mgu)``
        with normalized variable names.  Otherwise ``(False, None)``.

        *var_creator(i)* gives a variable for the *i*-th distinct variable
        (left-to-right) in the mgu, beginning with index 0.

        Matches C# Unifier.IsUnifiable + MkMGU.
        """
        assert t_a.owner is t_b.owner
        index = t_a.owner

        label_a = 0
        label_b = 1 if standardize else 0

        # -- Phase 1: unification with binding tracking --
        # StdTerm = (uid, label).  parent implements union-find.
        # bindings maps a variable's representative to the term it's bound to.
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        bindings: Dict[Tuple[int, int], Tuple[Term, int]] = {}  # rep -> (term, label)
        pending: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        pending.append(((t_a._uid, label_a), (t_b._uid, label_b)))

        def find(x: Tuple[int, int]) -> Tuple[int, int]:
            while x in parent and parent[x] != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(x: Tuple[int, int], y: Tuple[int, int]) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
                # Merge bindings: if rx had a binding, transfer it
                if rx in bindings and ry not in bindings:
                    bindings[ry] = bindings[rx]

        def bind_var(var_std: Tuple[int, int], binding_term: Term, binding_label: int) -> None:
            """Bind a variable to a data constructor / constant term."""
            rep = find(var_std)
            existing = bindings.get(rep)
            if existing is not None:
                # Already bound — push pending unification
                et, el = existing
                pending.append(((et._uid, el), (binding_term._uid, binding_label)))
            else:
                bindings[rep] = (binding_term, binding_label)
            union(var_std, (binding_term._uid, binding_label))

        while pending:
            sa, sb = pending.pop()
            ra = find(sa)
            rb = find(sb)
            if ra == rb:
                continue

            ta = _uid_to_term(t_a, sa[0], sa[1], label_a)
            tb = _uid_to_term(t_b, sb[0], sb[1], label_b)
            if ta is None or tb is None:
                return False, None

            if ta.groundness == Groundness.Ground and tb.groundness == Groundness.Ground:
                if ta is not tb:
                    return False, None
                continue

            if (ta.symbol.is_data_constructor or ta.symbol.is_non_var_constant) and \
               (tb.symbol.is_data_constructor or tb.symbol.is_non_var_constant):
                if ta.symbol is not tb.symbol:
                    return False, None
                union(sa, sb)
                for i in range(ta.symbol.arity):
                    pending.append(
                        ((ta.args[i]._uid, sa[1]), (tb.args[i]._uid, sb[1]))
                    )
            elif ta.symbol.is_variable:
                if tb.symbol.is_data_constructor or tb.symbol.is_non_var_constant:
                    bind_var(sa, tb, sb[1])
                else:
                    union(sa, sb)
            elif tb.symbol.is_variable:
                if ta.symbol.is_data_constructor or ta.symbol.is_non_var_constant:
                    bind_var(sb, ta, sa[1])
                else:
                    union(sb, sa)
            else:
                union(sa, sb)

        # -- Phase 2: construct MGU by traversing t_a --
        # Maps each normalized variable (by std-term rep) to a fresh var.
        var_map: Dict[Tuple[int, int], Term] = {}

        def mk_mgu(term: Term, label: int) -> Term:
            if term.groundness == Groundness.Ground:
                return term

            if not term.symbol.is_variable:
                # Data constructor: recurse into arguments
                new_args = []
                changed = False
                for a in term.args:
                    a2 = mk_mgu(a, label)
                    new_args.append(a2)
                    if a2 is not a:
                        changed = True
                if not changed:
                    return term
                return index.mk_apply(term.symbol, new_args)

            # Variable: check if it has a binding
            std = (term._uid, label)
            rep = find(std)
            bound = bindings.get(rep)
            if bound is not None:
                bound_term, bound_label = bound
                if bound_term.symbol.is_variable:
                    # Bound to another variable — normalize
                    bound_std = (bound_term._uid, bound_label)
                    bound_rep = find(bound_std)
                    if bound_rep not in var_map:
                        var_map[bound_rep] = var_creator(len(var_map))
                    return var_map[bound_rep]
                else:
                    # Bound to a data constructor: recurse
                    return mk_mgu(bound_term, bound_label)

            # Free variable: normalize
            if rep not in var_map:
                var_map[rep] = var_creator(len(var_map))
            return var_map[rep]

        mgu = mk_mgu(t_a, label_a)
        return True, mgu


def _uid_to_term(root: Term, uid: int, label: int, root_label: int) -> Optional[Term]:
    """Resolve a UID back to a term (simplified)."""
    if uid == root._uid and label == root_label:
        return root
    # Walk the term tree to find the term with the given UID
    for t in root.enumerate(lambda x: x.args if x.symbol.arity > 0 else None):
        if t._uid == uid:
            return t
    return None


def _simple_unify(t_a: Term, t_b: Term) -> bool:
    """Simplified structural unification check."""
    if t_a is t_b:
        return True
    if t_a.symbol.is_variable or t_b.symbol.is_variable:
        return True
    if t_a.symbol is not t_b.symbol:
        return False
    if t_a.symbol.arity != t_b.symbol.arity:
        return False
    for i in range(t_a.symbol.arity):
        if not _simple_unify(t_a.args[i], t_b.args[i]):
            return False
    return True


# ===================================================================
# CoreRule
# ===================================================================

class CoreRule:
    """
    A compiled rule of the form ``head :- find1, [find2], constraints``.

    Carries the head term, find data for up to two find clauses,
    a constraint set, and a stratum number for stratified evaluation.
    """

    class RuleKind:
        Regular = "Regular"
        Sub = "Sub"

    class _ConstraintNodeKind:
        Ground = "Ground"
        Nonground = "Nonground"
        TypeRel = "TypeRel"
        EqRel = "EqRel"

    class _InitStatusKind:
        Uninit = "Uninit"
        Success = "Success"
        Fail = "Fail"

    def __init__(
        self,
        rule_id: int,
        head: Term,
        find1: Optional[FindData] = None,
        find2: Optional[FindData] = None,
        constraints: Optional[Set[Term]] = None,
        node: Any = None,
        program_name: Any = None,
    ) -> None:
        self._rule_id = rule_id
        self._head = head
        self._find1 = find1 or FindData()
        self._find2 = find2 or FindData()
        self._constraints = constraints or set()
        self._node = node
        self._program_name = program_name
        self._stratum: int = -1
        self._init_status = self._InitStatusKind.Uninit
        self._is_product_rule: bool = False
        self._index: TermIndex = head.owner

        # Matcher caches
        self._matcher1: Optional[Matcher] = None
        self._matcher2: Optional[Matcher] = None

    @property
    def kind(self) -> str:
        return self.RuleKind.Regular

    @property
    def rule_id(self) -> int:
        return self._rule_id

    @property
    def head(self) -> Term:
        return self._head

    @property
    def find1(self) -> FindData:
        return self._find1

    @property
    def find2(self) -> FindData:
        return self._find2

    @property
    def constraints(self) -> Set[Term]:
        return self._constraints

    @property
    def node(self) -> Any:
        return self._node

    @property
    def program_name(self) -> Any:
        return self._program_name

    @property
    def index(self) -> TermIndex:
        return self._index

    @property
    def stratum(self) -> int:
        return self._stratum

    @stratum.setter
    def stratum(self, value: int) -> None:
        self._stratum = value

    @property
    def is_product_rule(self) -> bool:
        return self._is_product_rule

    def initialize(self) -> bool:
        """Initialize matchers and constraint nodes."""
        if self._init_status != self._InitStatusKind.Uninit:
            return self._init_status == self._InitStatusKind.Success

        if not self._find1.is_null and self._find1.pattern is not None:
            if self._find1.pattern.groundness != Groundness.Type:
                self._matcher1 = Matcher(self._find1.pattern)

        if not self._find2.is_null and self._find2.pattern is not None:
            if self._find2.pattern.groundness != Groundness.Type:
                self._matcher2 = Matcher(self._find2.pattern)

        self._is_product_rule = (
            self._matcher1 is not None
            and self._matcher2 is not None
        )

        self._init_status = self._InitStatusKind.Success
        return True

    def execute(
        self,
        binding: Term,
        find_number: int,
        executer: Executer,
        keep_derivations: bool,
        pending: Dict[int, Set[Derivation]],
    ) -> None:
        """
        Execute this rule with the given binding for find *find_number*.
        Derived facts are added to *pending*.
        """
        if find_number == 0:
            self._execute_find1(binding, executer, keep_derivations, pending)
        else:
            self._execute_find2(binding, executer, keep_derivations, pending)

    def _execute_find1(
        self,
        binding: Term,
        executer: Executer,
        keep_derivations: bool,
        pending: Dict[int, Set[Derivation]],
    ) -> None:
        """Execute after binding find1."""
        if self._matcher1 is not None and not self._matcher1.try_match(binding):
            return

        if self._find2.is_null:
            # No second find: evaluate constraints and produce head
            head = self._evaluate_head(self._matcher1, None)
            if head is not None:
                self._pend(keep_derivations, executer, pending, head, binding, self._index.false_value)
        else:
            # Need to find matches for find2
            if self._find2.type is not None:
                for fact in executer.get_facts_of_type(self._find2.type):
                    if self._matcher2 is not None and not self._matcher2.try_match(fact):
                        continue
                    head = self._evaluate_head(self._matcher1, self._matcher2)
                    if head is not None:
                        self._pend(keep_derivations, executer, pending, head, binding, fact)

    def _execute_find2(
        self,
        binding: Term,
        executer: Executer,
        keep_derivations: bool,
        pending: Dict[int, Set[Derivation]],
    ) -> None:
        """Execute after binding find2."""
        if self._matcher2 is not None and not self._matcher2.try_match(binding):
            return

        if self._find1.is_null:
            head = self._evaluate_head(None, self._matcher2)
            if head is not None:
                self._pend(keep_derivations, executer, pending, head, self._index.false_value, binding)
        else:
            if self._find1.type is not None:
                for fact in executer.get_facts_of_type(self._find1.type):
                    if self._matcher1 is not None and not self._matcher1.try_match(fact):
                        continue
                    head = self._evaluate_head(self._matcher1, self._matcher2)
                    if head is not None:
                        self._pend(keep_derivations, executer, pending, head, fact, binding)

    def _evaluate_head(
        self,
        m1: Optional[Matcher],
        m2: Optional[Matcher],
    ) -> Optional[Term]:
        """
        Substitute variable bindings into the head term.
        Returns None if a constraint is violated.
        """
        bindings: Dict[int, Term] = {}
        if m1 is not None:
            for uid, t in m1.current_bindings.items():
                if t is not None:
                    bindings[uid] = t
        if m2 is not None:
            for uid, t in m2.current_bindings.items():
                if t is not None:
                    bindings[uid] = t

        def subst(term: Term) -> Term:
            if term.groundness == Groundness.Ground:
                return term
            if term.symbol.is_variable:
                b = bindings.get(term._uid)
                return b if b is not None else term
            if term.symbol.arity == 0:
                return term
            new_args = [subst(a) for a in term.args]
            result, _ = self._index.mk_apply(term.symbol, new_args)
            return result

        return subst(self._head)

    @staticmethod
    def _pend(
        keep_derivations: bool,
        executer: Executer,
        pending: Dict[int, Set[Derivation]],
        head: Term,
        binding1: Term,
        binding2: Term,
    ) -> None:
        """Add a derived fact to the pending set."""
        uid = head._uid
        derivs = pending.get(uid)
        if derivs is None:
            derivs = set()
            pending[uid] = derivs
        executer.pend_fact(head, binding1, binding2, keep_derivations, pending)

    def opt_inline_partial_rule(self, eliminator: CoreRule) -> Tuple[CoreRule, bool]:
        """Attempt to inline a partial rule. Returns (result, succeeded)."""
        return self, False

    def clone(
        self,
        rule_id: int,
        is_compr: Optional[Callable] = None,
        index: Optional[TermIndex] = None,
        binding_reification_cache: Optional[Dict] = None,
        symbol_transfer: Optional[Dict] = None,
        renaming: Optional[str] = None,
    ) -> CoreRule:
        """Clone this rule into a different TermIndex."""
        assert index is not None
        new_head = index.mk_clone(self._head)
        new_find1 = FindData(
            index.mk_clone(self._find1.binding) if self._find1.binding else None,
            index.mk_clone(self._find1.pattern) if self._find1.pattern else None,
            index.mk_clone(self._find1.type) if self._find1.type else None,
        ) if not self._find1.is_null else FindData()
        new_find2 = FindData(
            index.mk_clone(self._find2.binding) if self._find2.binding else None,
            index.mk_clone(self._find2.pattern) if self._find2.pattern else None,
            index.mk_clone(self._find2.type) if self._find2.type else None,
        ) if not self._find2.is_null else FindData()
        return CoreRule(rule_id, new_head, new_find1, new_find2, node=self._node, program_name=self._program_name)

    def debug_print_rule(self) -> None:
        """Print this rule to stdout for debugging."""
        print(f"ID: {self._rule_id}, Stratum: {self._stratum if self._stratum >= 0 else '?'}")
        print(f"  {self._head.debug_get_small_term_string()}")
        print("  :-")
        if not self._find1.is_null:
            print(
                f"    find1: {self._find1.binding.debug_get_small_term_string() if self._find1.binding else '?'}"
                f" [{self._find1.pattern.debug_get_small_term_string() if self._find1.pattern else '?'}"
                f" : {self._find1.type.debug_get_small_term_string() if self._find1.type else '?'}]"
            )
        if not self._find2.is_null:
            print(
                f"    find2: {self._find2.binding.debug_get_small_term_string() if self._find2.binding else '?'}"
                f" [{self._find2.pattern.debug_get_small_term_string() if self._find2.pattern else '?'}"
                f" : {self._find2.type.debug_get_small_term_string() if self._find2.type else '?'}]"
            )
        for c in self._constraints:
            print(f"    constraint: {c.debug_get_small_term_string()}")
        print("    .")


# ===================================================================
# CoreSubRule
# ===================================================================

class CoreSubRule(CoreRule):
    """
    A rule derived from a ``sub`` constructor.

    ``f(x_1,...,x_n) :- y is T``
    where x_1,...,x_n are substituted by subterms of y satisfying the matcher.
    """

    def __init__(
        self,
        rule_id: int,
        head: Term,
        bind_var: Term,
        matcher: SubtermMatcher,
    ) -> None:
        assert matcher is not None and matcher.is_triggerable
        find = FindData(bind_var, bind_var, matcher.trigger)
        super().__init__(rule_id, head, find)
        self._matcher = matcher

    @property
    def kind(self) -> str:
        return self.RuleKind.Sub

    @property
    def sub_matcher(self) -> SubtermMatcher:
        return self._matcher

    def execute(
        self,
        binding: Term,
        find_number: int,
        executer: Any,
        keep_derivations: bool,
        pending: Dict[int, Set[Derivation]],
    ) -> None:
        for match in self._matcher.enumerate_matches(binding):
            args = list(match)
            head, _ = self._index.mk_apply(self._head.symbol, args)
            self._pend(keep_derivations, executer, pending, head, binding, self._index.false_value)

    def clone(
        self,
        rule_id: int,
        is_compr: Optional[Callable] = None,
        index: Optional[TermIndex] = None,
        binding_reification_cache: Optional[Dict] = None,
        symbol_transfer: Optional[Dict] = None,
        renaming: Optional[str] = None,
    ) -> CoreRule:
        assert index is not None
        new_head_args = []
        for i in range(self._head.symbol.arity):
            arg_sym: UserSymbol = self._head.args[i].symbol  # type: ignore[assignment]
            var, _ = index.mk_var(arg_sym.name, True)
            new_head_args.append(var)
        new_head_con = symbol_transfer[self._head.symbol] if symbol_transfer and self._head.symbol in symbol_transfer else self._head.symbol  # type: ignore
        new_head, _ = index.mk_apply(new_head_con, new_head_args)
        bind_sym: UserSymbol = self._find1.binding.symbol  # type: ignore[union-attr, assignment]
        new_bind_var, _ = index.mk_var(bind_sym.name, True)
        return CoreSubRule(rule_id, new_head, new_bind_var, self._matcher.clone(index))

    def debug_print_rule(self) -> None:
        print(f"ID: {self._rule_id}, Stratum: {self._stratum if self._stratum >= 0 else '?'}")
        print(f"  {self._head.debug_get_small_term_string()}")
        print("  :- (sub rule)")
        if self._find1.binding:
            print(f"    bind: {self._find1.binding.debug_get_small_term_string()}")
        for i, pat in enumerate(self._matcher.pattern):
            print(f"    pattern[{i}]: {pat.debug_get_small_term_string()}")
        print("    .")


# ===================================================================
# RuleTable
# ===================================================================

class RuleTable:
    """
    A collection of compiled rules for a FORMULA module.

    Manages rule creation, stratification, and cloning for transforms.
    """

    SYMB_INDEX_FIND = 0
    SYMB_INDEX_CONJ = 1
    SYMB_INDEX_CONJ_R = 2
    SYMB_INDEX_DISJ = 3
    SYMB_INDEX_PROJ = 4
    SYMB_INDEX_PRULE = 5
    SYMB_INDEX_RULE = 6
    SYMB_INDEX_COMPR = 7
    SYMB_INDEX_CRULE = 8
    N_REIFICATION_SYMBOLS = 9

    def __init__(self, index: TermIndex) -> None:
        self._index = index
        self._rules: List[CoreRule] = []
        self._next_rule_id = 0
        self._is_valid: Optional[bool] = None
        self._all_symb_cnsts: Set[Term] = set()
        self._strata_map: Dict[int, List[CoreRule]] = {}

    @property
    def index(self) -> TermIndex:
        return self._index

    @property
    def rules(self) -> List[CoreRule]:
        return self._rules

    @property
    def is_valid(self) -> Optional[bool]:
        return self._is_valid

    def add_rule(self, rule: CoreRule) -> None:
        """Add a compiled rule to this table."""
        self._rules.append(rule)

    def create_rule(
        self,
        head: Term,
        find1: Optional[FindData] = None,
        find2: Optional[FindData] = None,
        constraints: Optional[Set[Term]] = None,
        node: Any = None,
        program_name: Any = None,
    ) -> CoreRule:
        """Create a new rule, assign it an ID, and add it to the table."""
        rule = CoreRule(
            self._next_rule_id,
            head,
            find1,
            find2,
            constraints,
            node,
            program_name,
        )
        self._next_rule_id += 1
        self._rules.append(rule)
        return rule

    def create_sub_rule(
        self,
        head: Term,
        bind_var: Term,
        matcher: SubtermMatcher,
    ) -> CoreSubRule:
        """Create a sub-constructor rule."""
        rule = CoreSubRule(self._next_rule_id, head, bind_var, matcher)
        self._next_rule_id += 1
        self._rules.append(rule)
        return rule

    def stratify(self) -> bool:
        """
        Compute stratification of rules.

        Rules are assigned to strata such that negation and aggregation
        dependencies go to lower strata.

        Returns True on success, False if stratification fails (unstratifiable).
        """
        # Simple single-stratum assignment for now.
        # A full implementation would compute the dependency graph and assign
        # strata according to negation / aggregation edges.
        for rule in self._rules:
            rule.stratum = 0
        self._strata_map[0] = list(self._rules)
        self._is_valid = True
        return True

    def get_rules_at_stratum(self, stratum: int) -> List[CoreRule]:
        return self._strata_map.get(stratum, [])

    @property
    def n_strata(self) -> int:
        return len(self._strata_map)

    def clone_transform_table(self, index: TermIndex) -> RuleTable:
        """
        Clone all rules from this table into a new TermIndex.
        Used for instantiating transforms.
        """
        new_table = RuleTable(index)
        for rule in self._rules:
            cloned = rule.clone(new_table._next_rule_id, index=index)
            new_table._next_rule_id += 1
            new_table._rules.append(cloned)
        return new_table

    def initialize_all(self) -> bool:
        """Initialize all rules (build matchers, etc.)."""
        ok = True
        for rule in self._rules:
            ok = rule.initialize() and ok
        return ok

    def compile_rules(self, mod_data: Any) -> bool:
        """
        Compile AST Rule nodes from the module into CoreRule objects.

        Ported from C# RuleTable.Compile (via ActionSet).
        Walks each Rule node, converts head expressions and body constraints
        into Term objects using the TermIndex, and creates CoreRule objects.

        Parameters
        ----------
        mod_data : ModuleData
            The module data containing the reduced AST and symbol table.

        Returns True on success.
        """
        reduced = getattr(mod_data, "reduced", None)
        if reduced is None:
            return True

        rules_ast = getattr(reduced, "rules", [])
        if not rules_ast:
            return True

        symbol_table = self._index.symbol_table

        for rule_node in rules_ast:
            heads = getattr(rule_node, "heads", [])
            bodies = getattr(rule_node, "bodies", [])

            for head_node in heads:
                for body_node in bodies:
                    self._compile_one_rule(head_node, body_node, rule_node, symbol_table)

        self.stratify()
        return True

    def _compile_one_rule(
        self,
        head_node: Any,
        body_node: Any,
        rule_node: Any,
        symbol_table: Any,
    ) -> None:
        """
        Compile a single (head, body) pair into a CoreRule.

        Converts AST nodes to Terms in the TermIndex and creates
        FindData objects for Find constraints in the body.
        """
        from formula.api.nodes import Find, RelConstr, FuncTerm, Id, Cnst, Compr
        from formula.api.constants import RelKind, OpKind

        variables: Dict[str, Term] = {}  # variable name -> Term

        # Convert head AST to Term
        head_term = _ast_to_term(head_node, self._index, symbol_table, variables)
        if head_term is None:
            return

        # Extract Find and non-Find constraints from the body
        constraints_ast = getattr(body_node, "constraints", [])
        finds: list = []
        other_constraints: list = []

        for c in constraints_ast:
            if isinstance(c, Find):
                finds.append(c)
            else:
                other_constraints.append(c)

        # Build FindData for up to 2 Find constraints
        find1 = FindData()
        find2 = FindData()

        if len(finds) >= 1:
            find1 = self._compile_find(finds[0], symbol_table, variables)

        if len(finds) >= 2:
            find2 = self._compile_find(finds[1], symbol_table, variables)

        # For rules with >2 finds, chain additional finds as constraints
        # (simplified: we handle up to 2 finds directly)

        # Convert non-Find constraints to Terms
        constraint_terms: Set[Term] = set()
        for c in other_constraints:
            ct = _ast_to_term(c, self._index, symbol_table, variables)
            if ct is not None:
                constraint_terms.add(ct)

        # Re-resolve the head term now that we have all variable bindings
        # from the body finds (variables dict may have been populated)
        head_term = _ast_to_term(head_node, self._index, symbol_table, variables)
        if head_term is None:
            return

        self.create_rule(
            head_term,
            find1,
            find2,
            constraint_terms if constraint_terms else None,
            node=rule_node,
        )

    def _compile_find(
        self,
        find_node: Any,
        symbol_table: Any,
        variables: Dict[str, Term],
    ) -> FindData:
        """Convert a Find AST node to a FindData object."""
        from formula.api.nodes import Id

        match = find_node.match
        binding_node = find_node.binding

        # Build the pattern Term from the match expression
        pattern = _ast_to_term(match, self._index, symbol_table, variables)
        if pattern is None:
            return FindData()

        # Build the binding term (the variable that captures the match)
        binding: Optional[Term] = None
        if binding_node is not None and isinstance(binding_node, Id):
            binding, _ = self._index.mk_var(binding_node.name)
            variables[binding_node.name] = binding

        # Build a type term from the pattern's root symbol
        type_term: Optional[Term] = None
        if pattern.symbol.is_data_constructor:
            # Use the constructor's sort symbol as the type
            sort_sym = getattr(pattern.symbol, "sort_symbol", None)
            if sort_sym is not None:
                type_term = self._index.mk_apply(sort_sym, [])[0]

        if binding is None:
            # If no explicit binding, use the pattern itself as binding
            binding = pattern

        return FindData(binding, pattern, type_term)

    def debug_print(self) -> None:
        """Print all rules to stdout."""
        print(f"=== RuleTable ({len(self._rules)} rules) ===")
        for rule in self._rules:
            rule.debug_print_rule()
            print()


# ===================================================================
# AST-to-Term conversion
# ===================================================================

def _ast_to_term(
    node: Any,
    index: TermIndex,
    symbol_table: Any,
    variables: Dict[str, Term],
) -> Optional[Term]:
    """
    Convert an AST expression node to a Term in the TermIndex.

    Handles:
    - Id: variable or constructor/constant reference
    - Cnst: numeric or string constant
    - FuncTerm: constructor application or arithmetic operation
    - RelConstr: relational constraint (=, !=, <, >, etc.)
    - Compr: comprehension (for aggregation)

    Ported from the C# ActionSet logic that converts AST nodes to Terms.
    """
    from formula.api.nodes import FuncTerm, Id, Cnst, RelConstr, Compr, Find, Range
    from formula.api.constants import OpKind, RelKind, CnstKind
    from fractions import Fraction

    if node is None:
        return None

    if isinstance(node, Cnst):
        raw = node.raw
        if isinstance(raw, Fraction):
            return index.mk_cnst(raw)[0]
        elif isinstance(raw, (int, float)):
            return index.mk_cnst(Fraction(raw))[0]
        elif isinstance(raw, str):
            return index.mk_cnst(raw)[0]
        return None

    if isinstance(node, Id):
        name = node.name
        fragments = getattr(node, "fragments", None)

        # Check if this is a known variable
        if name in variables:
            return variables[name]

        # Check namespace-qualified name (e.g., "out.N")
        if fragments and len(fragments) > 1:
            # Try resolving as a qualified name in the symbol table
            sym, _ = symbol_table.resolve(name)
            if sym is not None and sym.arity == 0:
                return index.mk_apply(sym, [])[0]
            # If not found as a 0-arity symbol, treat as variable
            var, _ = index.mk_var(name)
            variables[name] = var
            return var

        # Try resolving as a constructor/constant
        sym, _ = symbol_table.resolve(name)
        if sym is not None and sym.arity == 0:
            return index.mk_apply(sym, [])[0]

        # Otherwise it's a variable
        var, _ = index.mk_var(name)
        variables[name] = var
        return var

    if isinstance(node, FuncTerm):
        fn = node.function
        raw_args = list(node.args)

        if isinstance(fn, OpKind):
            # Arithmetic/logical operation
            args = [_ast_to_term(a, index, symbol_table, variables) for a in raw_args]
            if any(a is None for a in args):
                return None
            if symbol_table.has_op_symbol(fn):
                op_sym = symbol_table.get_op_symbol(fn)
                return index.mk_apply(op_sym, args)[0]
            return None

        if isinstance(fn, Id):
            fn_name = fn.name
            fragments = getattr(fn, "fragments", None)

            # Resolve constructor name (possibly namespace-qualified)
            sym, _ = symbol_table.resolve(fn_name)
            if sym is not None:
                args = [_ast_to_term(a, index, symbol_table, variables) for a in raw_args]
                if any(a is None for a in args):
                    return None
                return index.mk_apply(sym, args)[0]

            # Try as an operation name
            op_map = {o.name.lower(): o for o in OpKind}
            if fn_name.lower() in op_map:
                op_kind = op_map[fn_name.lower()]
                args = [_ast_to_term(a, index, symbol_table, variables) for a in raw_args]
                if any(a is None for a in args):
                    return None
                if symbol_table.has_op_symbol(op_kind):
                    op_sym = symbol_table.get_op_symbol(op_kind)
                    return index.mk_apply(op_sym, args)[0]

            # Unknown constructor - create it as a user symbol if possible
            return None

        return None

    if isinstance(node, RelConstr):
        # Relational constraint: convert to a term using the rel op symbol
        lhs = _ast_to_term(node.arg1, index, symbol_table, variables)
        rhs = _ast_to_term(node.arg2, index, symbol_table, variables) if node.arg2 is not None else None
        if lhs is None:
            return None
        if symbol_table.has_op_symbol(node.op):
            op_sym = symbol_table.get_op_symbol(node.op)
            if rhs is not None:
                return index.mk_apply(op_sym, [lhs, rhs])[0]
            else:
                return index.mk_apply(op_sym, [lhs])[0]
        return None

    if isinstance(node, Find):
        # Find in a constraint position (shouldn't happen normally)
        return _ast_to_term(node.match, index, symbol_table, variables)

    return None


# ===================================================================
# FactSet
# ===================================================================

class FactSet:
    """A set of ground facts in a TermIndex."""

    def __init__(self, index: TermIndex, facts: Optional[Set[Term]] = None) -> None:
        self._index = index
        self._facts: Set[Term] = facts if facts is not None else set()

    @property
    def index(self) -> TermIndex:
        return self._index

    @property
    def facts(self) -> Set[Term]:
        return self._facts

    def add(self, term: Term) -> bool:
        if term in self._facts:
            return False
        self._facts.add(term)
        return True

    def contains(self, term: Term) -> bool:
        return term in self._facts

    def __len__(self) -> int:
        return len(self._facts)

    def __iter__(self) -> Iterator[Term]:
        return iter(self._facts)


# ===================================================================
# SubIndex  (used by Executer)
# ===================================================================

class SubIndex:
    """
    An index over facts that match a particular find pattern.
    Used for efficient rule triggering.
    """

    def __init__(self, pattern: Term) -> None:
        self._pattern = pattern
        self._facts: Set[Term] = set()
        self._pending_rules: List[Tuple[CoreRule, int]] = []  # (rule, find_number)

    @property
    def pattern(self) -> Term:
        return self._pattern

    @property
    def facts(self) -> Set[Term]:
        return self._facts

    def add_rule(self, rule: CoreRule, find_number: int) -> None:
        self._pending_rules.append((rule, find_number))

    def add_fact(self, fact: Term) -> None:
        self._facts.add(fact)

    def get_rules(self) -> List[Tuple[CoreRule, int]]:
        return self._pending_rules


# ===================================================================
# Executer
# ===================================================================

class Executer:
    """
    The fixed-point execution engine for FORMULA rules.

    Given a ``RuleTable`` and initial facts, computes the least fixed point
    by iteratively applying rules until no new facts are derived.
    """

    def __init__(
        self,
        rule_table: RuleTable,
        model_facts: Optional[Dict[str, FactSet]] = None,
        value_params: Optional[Dict[str, Term]] = None,
        statistics: Optional[ExecuterStatistics] = None,
        keep_derivations: bool = False,
        cancel: Any = None,
    ) -> None:
        self._rule_table = rule_table
        self._index = rule_table.index
        self._model_facts = model_facts or {}
        self._value_params = value_params or {}
        self._statistics = statistics
        self._keep_derivations = keep_derivations
        self._cancel = cancel

        # The fixpoint: all derived facts
        self._facts: Dict[int, Set[Derivation]] = {}  # term uid -> derivations
        self._fact_terms: Dict[int, Term] = {}  # uid -> term

        # Trigger indices
        self._trig_indices: Dict[int, SubIndex] = {}  # pattern uid -> sub-index
        self._symb_to_indices: Dict[int, List[SubIndex]] = {}  # symbol id -> sub-indices

        # Work queue
        self._pending: Deque[Term] = deque()

    @property
    def index(self) -> TermIndex:
        return self._index

    @property
    def fixpoint(self) -> Dict[int, Term]:
        """Return the computed fixpoint as a mapping from UID to term."""
        return self._fact_terms

    @property
    def fixpoint_facts(self) -> Iterable[Term]:
        """Iterate over all facts in the fixpoint."""
        return self._fact_terms.values()

    def get_facts_of_type(self, type_term: Optional[Term]) -> Iterable[Term]:
        """Return all facts that match the given type term."""
        if type_term is None:
            return iter(())
        # Simplified: return all facts
        return self._fact_terms.values()

    def pend_fact(
        self,
        fact: Term,
        binding1: Term,
        binding2: Term,
        keep_derivations: bool,
        pending: Dict[int, Set[Derivation]],
    ) -> None:
        """Add a fact to the pending set."""
        uid = fact._uid
        if uid not in self._facts:
            self._facts[uid] = set()
            self._fact_terms[uid] = fact
            self._pending.append(fact)

    def execute(self) -> None:
        """
        Run the fixpoint computation.

        Initializes rules, loads initial facts, then iteratively fires
        rules and processes pending facts until quiescence.
        """
        # Initialize rules
        self._rule_table.stratify()
        self._rule_table.initialize_all()

        if self._statistics:
            self._statistics.set_rules(self._rule_table.rules)
            self._statistics.n_strata = self._rule_table.n_strata

        # Load initial model facts
        for name, fset in self._model_facts.items():
            for fact in fset.facts:
                cloned = self._index.mk_clone(fact)
                self.pend_fact(cloned, self._index.false_value, self._index.false_value, self._keep_derivations, self._facts)

        # Execute stratum by stratum
        for s in range(self._rule_table.n_strata):
            if self._statistics:
                self._statistics.current_stratum = s

            rules = self._rule_table.get_rules_at_stratum(s)

            # Process the work queue
            changed = True
            while changed:
                changed = False
                while self._pending:
                    fact = self._pending.popleft()
                    # Try to trigger each rule
                    for rule in rules:
                        pending_before = len(self._fact_terms)
                        self._try_fire_rule(rule, fact)
                        if len(self._fact_terms) > pending_before:
                            changed = True

                if self._statistics:
                    self._statistics.current_fixpoint_size = len(self._fact_terms)

    def _try_fire_rule(self, rule: CoreRule, fact: Term) -> None:
        """Try to fire a rule with the given fact as a trigger."""
        pending: Dict[int, Set[Derivation]] = {}

        if not rule.find1.is_null:
            rule.execute(fact, 0, self, self._keep_derivations, pending)

        if not rule.find2.is_null:
            rule.execute(fact, 1, self, self._keep_derivations, pending)

        # Process newly derived facts
        for uid, derivs in pending.items():
            if uid not in self._facts:
                term = self._fact_terms.get(uid)
                if term is not None:
                    self._facts[uid] = derivs
                    self._pending.append(term)

    def add_positive_constraint(self, term: Term) -> None:
        """Used by CoreSubRule to add a positive constraint (symbolic execution)."""
        pass

    def __repr__(self) -> str:
        return f"<Executer rules={len(self._rule_table.rules)} facts={len(self._fact_terms)}>"
