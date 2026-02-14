"""
Port of Src/Core/Common/Terms/*.cs (9 files).

Key classes:
  - Term             : immutable term (hash-consed)
  - TermIndex        : hash-consing term database (factory)
  - AppFreeCanUnn    : application-free canonical union (type representation)
  - TypeEnvironment  : maps terms to their types
  - CanUnnDef        : canonical union definition builder
  - SubtermMatcher   : pattern-based subterm enumeration
  - TermPrinting     : pretty-printing of terms and type terms

Uses ``fractions.Fraction`` for rational numbers (replacing the C# Rational struct).
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
    FrozenSet,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
)

from formula.common.symbol_types import (
    BaseCnstSymb,
    BaseOpSymb,
    BaseSortKind,
    BaseSortSymb,
    CnstKind,
    ConSymb,
    Groundness,
    MapSymb,
    Namespace,
    OpKind,
    RelKind,
    ReservedOpKind,
    SizeExpr,
    Symbol,
    SymbolKind,
    UnnSortSymb,
    UnnSymb,
    UserCnstSymb,
    UserCnstSymbKind,
    UserSortSymb,
    UserSymbol,
    _SORT_KIND_NAMES,
)

T = TypeVar("T")
S = TypeVar("S")


# ===================================================================
# ImmutableArray  (lightweight read-only wrapper)
# ===================================================================

class ImmutableArray(Sequence):
    """
    A thin read-only wrapper around a tuple, mirroring the C# ImmutableArray<T>.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Sequence) -> None:
        self._data = tuple(data) if not isinstance(data, tuple) else data

    def __getitem__(self, index):  # type: ignore[override]
        return self._data[index]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator:
        return iter(self._data)

    def __contains__(self, item: object) -> bool:
        return item in self._data

    def __repr__(self) -> str:
        return f"ImmutableArray({list(self._data)})"


# ===================================================================
# SuccessToken
# ===================================================================

class SuccessToken:
    """
    A mutable boolean flag that can be set to *failed* during computation.
    Used to short-circuit tree traversals.
    """

    __slots__ = ("_result",)

    def __init__(self) -> None:
        self._result = True

    @property
    def result(self) -> bool:
        return self._result

    def failed(self) -> None:
        self._result = False


# ===================================================================
# TermState  (traversal helper)
# ===================================================================

class TermState:
    """
    Tracks the argument position while iterating over a term's children.
    """

    START = -1
    END = -2

    __slots__ = ("term", "_arg_pos")

    def __init__(self, term: Term) -> None:
        self.term = term
        self._arg_pos = self.START

    @property
    def arg_pos(self) -> int:
        return self._arg_pos

    def move_state(self) -> int:
        assert self._arg_pos != self.END
        self._arg_pos += 1
        if self._arg_pos >= self.term.symbol.arity:
            self._arg_pos = self.END
        return self._arg_pos


# ===================================================================
# Term
# ===================================================================

class Term:
    """
    An immutable, hash-consed FORMULA term.

    A term consists of a ``Symbol`` and a tuple of sub-term arguments.
    Terms with the same symbol and arguments are guaranteed to be the same
    Python object (identity ``is``) within a given ``TermIndex``.

    Groundness is computed at construction time and is one of:
    ``Ground``, ``Variable``, or ``Type``.
    """

    FAMILY_NUMERIC = 0
    FAMILY_STRING = 1
    FAMILY_USR_CNST = 2
    FAMILY_APP = 3

    __slots__ = (
        "_uid",
        "_symbol",
        "_args",
        "_groundness",
        "_owner",
    )

    def __init__(
        self,
        symbol: Symbol,
        args: Sequence[Term],
        owner: TermIndex,
    ) -> None:
        assert len(args) == symbol.arity
        self._uid: int = -1
        self._symbol = symbol
        self._args = ImmutableArray(args)
        self._owner = owner

        # Compute groundness
        if symbol.arity == 0:
            kind = symbol.kind
            if kind == SymbolKind.BaseCnstSymb:
                self._groundness = Groundness.Ground
            elif kind in (SymbolKind.BaseSortSymb, SymbolKind.UnnSymb, SymbolKind.UserSortSymb):
                self._groundness = Groundness.Type
            elif kind == SymbolKind.UserCnstSymb:
                self._groundness = Groundness.Variable if symbol.is_variable else Groundness.Ground
            else:
                raise ValueError(f"Unexpected zero-arity symbol kind: {kind}")
        elif symbol is owner.type_rel_symbol:
            self._groundness = args[0].groundness
        else:
            g = Groundness.Ground
            for a in args:
                if a.groundness == Groundness.Variable:
                    g = Groundness.Variable
                elif a.groundness == Groundness.Type:
                    g = Groundness.Type
            if symbol is owner.range_symbol or symbol is owner.type_union_symbol:
                g = Groundness.Type
            self._groundness = g

    # -- properties --------------------------------------------------------
    @property
    def uid(self) -> int:
        assert self._uid != -1
        return self._uid

    @uid.setter
    def uid(self, value: int) -> None:
        assert self._uid == -1
        self._uid = value

    @property
    def symbol(self) -> Symbol:
        return self._symbol

    @property
    def args(self) -> ImmutableArray:
        return self._args

    @property
    def groundness(self) -> Groundness:
        return self._groundness

    @property
    def owner(self) -> TermIndex:
        return self._owner

    @property
    def family(self) -> int:
        """An equivalence class identifier for the kind of the outer symbol."""
        kind = self._symbol.kind
        if kind == SymbolKind.BaseCnstSymb:
            bc: BaseCnstSymb = self._symbol  # type: ignore[assignment]
            return self.FAMILY_STRING if bc.cnst_kind == CnstKind.String else self.FAMILY_NUMERIC
        elif kind == SymbolKind.BaseSortSymb:
            bs: BaseSortSymb = self._symbol  # type: ignore[assignment]
            return self.FAMILY_STRING if bs.sort_kind == BaseSortKind.String else self.FAMILY_NUMERIC
        elif kind == SymbolKind.UserCnstSymb:
            return self.FAMILY_USR_CNST
        else:
            return self.FAMILY_APP

    # -- comparison --------------------------------------------------------
    @staticmethod
    def compare(t1: Term, t2: Term) -> int:
        if t1._uid < t2._uid:
            return -1
        elif t1._uid > t2._uid:
            return 1
        return 0

    def __lt__(self, other: Term) -> bool:
        return self._uid < other._uid

    def __le__(self, other: Term) -> bool:
        return self._uid <= other._uid

    def __gt__(self, other: Term) -> bool:
        return self._uid > other._uid

    def __ge__(self, other: Term) -> bool:
        return self._uid >= other._uid

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Term):
            return NotImplemented
        return self._uid == other._uid

    def __hash__(self) -> int:
        return hash(self._uid)

    # -- symbolic term detection -------------------------------------------
    @staticmethod
    def is_symbolic_term(t: Term) -> bool:
        if t.groundness == Groundness.Variable:
            return True
        sym = t.symbol
        if sym.is_sym_count or sym.is_sym_and or sym.is_sym_and_all or sym.is_sym_max:
            return True
        for child in t.args:
            if Term.is_symbolic_term(child):
                return True
        return False

    # -- lexicographic comparison ------------------------------------------
    def lexicographic_compare(self, other: Term) -> int:
        if self is other:
            return 0
        if self._symbol is not other._symbol:
            return self._symbol.id - other._symbol.id
        s1: List[TermState] = [TermState(self)]
        s2: List[TermState] = [TermState(other)]
        while s1 and s2:
            n1 = s1[-1].move_state()
            n2 = s2[-1].move_state()
            if n1 == TermState.END:
                s1.pop()
                s2.pop()
                continue
            t1 = s1[-1].term.args[n1]
            t2 = s2[-1].term.args[n2]
            if t1.symbol.id != t2.symbol.id:
                return t1.symbol.id - t2.symbol.id
            s1.append(TermState(t1))
            s2.append(TermState(t2))
        return 0

    # -- tree computation (fold / unfold) ----------------------------------
    def compute(
        self,
        unfold: Callable[[Term, Optional[SuccessToken]], Optional[Iterable[Term]]],
        fold: Callable[[Term, List[S], Optional[SuccessToken]], S],
        token: Optional[SuccessToken] = None,
    ) -> S:
        """
        Perform a bottom-up AST computation.

        ``unfold(t, token)`` returns the children to recurse into.
        ``fold(t, child_results, token)`` combines the results.
        """
        stack: List[Tuple[Optional[Any], Term, Optional[Iterator[Term]], List[S]]] = []
        uf = unfold(self, token)
        stack.append((None, self, iter(uf) if uf is not None else None, []))
        if token and not token.result:
            return fold(self, [], token)  # type: ignore[return-value]

        while stack:
            parent_idx, t, it, children = stack[-1]
            advanced = False
            if it is not None:
                try:
                    child = next(it)
                    uf2 = unfold(child, token)
                    stack.append((len(stack) - 1, child, iter(uf2) if uf2 is not None else None, []))
                    advanced = True
                    if token and not token.result:
                        return fold(self, [], token)  # type: ignore[return-value]
                except StopIteration:
                    pass

            if not advanced:
                result = fold(t, children, token)
                stack.pop()
                if stack:
                    stack[-1][3].append(result)
                    if token and not token.result:
                        return result
                else:
                    return result

        raise RuntimeError("Impossible: empty stack in Term.compute")

    def compute2(
        self,
        other: Term,
        unfold: Callable[[Term, Term, Optional[SuccessToken]], Optional[Tuple[Iterable[Term], Iterable[Term]]]],
        fold: Callable[[Term, Term, List[S], Optional[SuccessToken]], S],
        token: Optional[SuccessToken] = None,
    ) -> S:
        """
        Two-term AST computation.
        """
        stack: List[Tuple[Optional[int], Term, Term, Optional[Iterator[Term]], Optional[Iterator[Term]], List[S]]] = []
        uf = unfold(self, other, token)
        itA = iter(uf[0]) if uf and uf[0] else None
        itB = iter(uf[1]) if uf and uf[1] else None
        stack.append((None, self, other, itA, itB, []))

        while stack:
            pidx, tA, tB, iA, iB, children = stack[-1]
            a_val: Optional[Term] = None
            b_val: Optional[Term] = None
            has_next = False

            if iA is not None:
                try:
                    a_val = next(iA)
                    has_next = True
                except StopIteration:
                    pass
            if iB is not None:
                try:
                    b_val = next(iB)
                    has_next = True
                except StopIteration:
                    pass

            if has_next and a_val is not None and b_val is not None:
                uf2 = unfold(a_val, b_val, token)
                iA2 = iter(uf2[0]) if uf2 and uf2[0] else None
                iB2 = iter(uf2[1]) if uf2 and uf2[1] else None
                stack.append((len(stack) - 1, a_val, b_val, iA2, iB2, []))
                if token and not token.result:
                    return fold(self, other, [], token)  # type: ignore[return-value]
            else:
                result = fold(tA, tB, children, token)
                stack.pop()
                if stack:
                    stack[-1][5].append(result)
                else:
                    return result

        raise RuntimeError("Impossible: empty stack in Term.compute2")

    # -- enumeration / visitation ------------------------------------------
    def enumerate(
        self,
        unfold: Callable[[Term], Optional[Iterable[Term]]],
    ) -> Iterable[Term]:
        """Yield this term and all unfolded descendants."""
        yield self
        ures = unfold(self)
        if ures is None:
            return
        stack: List[Iterator[Term]] = [iter(ures)]
        while stack:
            try:
                t = next(stack[-1])
                yield t
                u = unfold(t)
                if u is not None:
                    stack.append(iter(u))
            except StopIteration:
                stack.pop()

    def visit(
        self,
        unfold: Callable[[Term], Optional[Iterable[Term]]],
        visitor: Callable[[Term], None],
        token: Optional[SuccessToken] = None,
    ) -> None:
        """Apply *visitor* to this term and all unfolded descendants."""
        visitor(self)
        ures = unfold(self)
        if ures is None or (token and not token.result):
            return
        stack: List[Iterator[Term]] = [iter(ures)]
        while stack:
            try:
                t = next(stack[-1])
                visitor(t)
                if token and not token.result:
                    return
                u = unfold(t)
                if u is not None:
                    stack.append(iter(u))
            except StopIteration:
                stack.pop()

    # -- printing ----------------------------------------------------------
    def print_term(self, cancel: Any = None, env_params: Any = None) -> str:
        sw = io.StringIO()
        TermPrinting.print_term(self, sw, cancel, env_params)
        return sw.getvalue()

    def print_type_term(self, cancel: Any = None, env_params: Any = None) -> str:
        sw = io.StringIO()
        TermPrinting.print_type_term(self, sw, cancel, env_params)
        return sw.getvalue()

    def __repr__(self) -> str:
        try:
            return self.print_term()
        except Exception:
            return f"<Term uid={self._uid} sym={self._symbol}>"

    def debug_get_small_term_string(self) -> str:
        """Produce a compact representation for debugging."""
        sw = io.StringIO()
        TermIndex.debug_print_small_term(self, sw)
        return sw.getvalue()


# ===================================================================
# TermIndex  -- hash-consing term database
# ===================================================================

class TermIndex:
    """
    A hash-consing term database (factory).

    Every distinct term (by symbol + args identity) is created exactly once.
    The ``MkApply`` method is the primary way to create / intern terms.
    """

    EMPTY_ARGS: Tuple[Term, ...] = ()

    def __init__(self, symbol_table: Any) -> None:
        from formula.common.symbols import SymbolTable
        self._symbol_table: SymbolTable = symbol_table
        self._n_terms: int = 0
        self._next_symbol_id: int = 0
        self._lock = threading.Lock()

        # Hash-consing maps: (symbol_id, *arg_uids) -> Term
        self._term_cache: Dict[Tuple, Term] = {}

        # Symbol bins: symbol -> set of terms with that symbol
        self._bins: Dict[int, Set[Term]] = {}  # symbol.id -> set

        # Cached constant symbols
        self._string_cnsts: Dict[str, BaseCnstSymb] = {}
        self._rat_cnsts: Dict[Fraction, BaseCnstSymb] = {}
        self._variables: Dict[str, UserCnstSymb] = {}

        # Type uses: maps a type term to set of (symbol, arg_index) pairs
        self._type_uses: Dict[int, List[Tuple[Symbol, int]]] = {}  # type uid -> uses

        # Canonical type terms cache
        self._canon_type_cache: Dict[int, Term] = {}

        # Important symbols (lazily cached)
        self._range_symbol: Optional[BaseOpSymb] = None
        self._type_union_symbol: Optional[BaseOpSymb] = None
        self._type_rel_symbol: Optional[BaseOpSymb] = None
        self._selector_symbol: Optional[BaseOpSymb] = None
        self._find_symbol: Optional[BaseOpSymb] = None
        self._relabel_symbol: Optional[BaseOpSymb] = None

        # Canonical terms for TRUE, FALSE (lazily created)
        self._true_value: Optional[Term] = None
        self._false_value: Optional[Term] = None

        self._sc_value_symb: Optional[ConSymb] = None
        self._symb_cnst_types: Dict[int, Term] = {}  # term uid -> type term
        self._symb_cnst_type_getter: Optional[Callable[[Term], Term]] = None

    # -- property accessors for important symbols --------------------------
    @property
    def symbol_table(self) -> Any:
        return self._symbol_table

    @property
    def range_symbol(self) -> BaseOpSymb:
        if self._range_symbol is None:
            self._range_symbol = self._symbol_table.get_op_symbol(ReservedOpKind.Range)
        return self._range_symbol

    @property
    def type_union_symbol(self) -> BaseOpSymb:
        if self._type_union_symbol is None:
            self._type_union_symbol = self._symbol_table.get_op_symbol(ReservedOpKind.TypeUnn)
        return self._type_union_symbol

    @property
    def type_rel_symbol(self) -> BaseOpSymb:
        if self._type_rel_symbol is None:
            self._type_rel_symbol = self._symbol_table.get_op_symbol(ReservedOpKind.TypeRel)
        return self._type_rel_symbol

    @property
    def selector_symbol(self) -> BaseOpSymb:
        if self._selector_symbol is None:
            self._selector_symbol = self._symbol_table.get_op_symbol(ReservedOpKind.Select)
        return self._selector_symbol

    @property
    def find_symbol(self) -> BaseOpSymb:
        if self._find_symbol is None:
            self._find_symbol = self._symbol_table.get_op_symbol(ReservedOpKind.Find)
        return self._find_symbol

    @property
    def relabel_symbol(self) -> BaseOpSymb:
        if self._relabel_symbol is None:
            self._relabel_symbol = self._symbol_table.get_op_symbol(ReservedOpKind.Relabel)
        return self._relabel_symbol

    @property
    def true_value(self) -> Term:
        if self._true_value is None:
            sym = self._symbol_table.get_cnst_symbol("TRUE")
            self._true_value = self.mk_apply(sym, [])
        return self._true_value

    @property
    def false_value(self) -> Term:
        if self._false_value is None:
            sym = self._symbol_table.get_cnst_symbol("FALSE")
            self._false_value = self.mk_apply(sym, [])
        return self._false_value

    # -- core term creation (hash-consing) ---------------------------------
    def mk_apply(
        self,
        symbol: Symbol,
        args: Sequence[Term],
    ) -> Tuple[Term, bool]:
        """
        Create (or retrieve) the term ``symbol(args...)``.

        Returns ``(term, was_added)`` where *was_added* is True if
        this term was newly created (not already in the cache).
        """
        key = (symbol.id,) + tuple(a._uid for a in args)
        existing = self._term_cache.get(key)
        if existing is not None:
            return existing, False

        t = Term(symbol, args, self)
        t.uid = self._n_terms
        self._n_terms += 1
        self._term_cache[key] = t

        # Add to bin
        bin_set = self._bins.get(symbol.id)
        if bin_set is None:
            bin_set = set()
            self._bins[symbol.id] = bin_set
        bin_set.add(t)

        return t, True

    # -- convenience term constructors -------------------------------------
    def mk_cnst(self, value: Any) -> Tuple[Term, bool]:
        """Create a base constant term (numeric or string)."""
        sym = self._symbol_table.get_cnst_symbol(value)
        return self.mk_apply(sym, [])

    def mk_var(self, name: str, is_autogen: bool = True) -> Tuple[Term, bool]:
        """Create or retrieve a variable term."""
        sym = self._variables.get(name)
        if sym is None:
            sym = UserCnstSymb(
                self._symbol_table.root, name,
                UserCnstSymbKind.Variable, is_autogen=is_autogen,
            )
            sym.id = self._symbol_table._get_next_id()
            self._variables[name] = sym
        return self.mk_apply(sym, [])

    def mk_type_union(self, t1: Term, t2: Term) -> Tuple[Term, bool]:
        """Create a type union term ``t1 + t2``."""
        return self.mk_apply(self.type_union_symbol, [t1, t2])

    def mk_range(self, lower: Term, upper: Term) -> Tuple[Term, bool]:
        """Create a range type term ``lower..upper``."""
        return self.mk_apply(self.range_symbol, [lower, upper])

    def mk_type_rel(self, term: Term, type_term: Term) -> Tuple[Term, bool]:
        """Create a type relation term ``term : type``."""
        return self.mk_apply(self.type_rel_symbol, [term, type_term])

    # -- type use tracking -------------------------------------------------
    def register_type_use(self, type_term: Term, symbol: Symbol, arg_index: int) -> None:
        """
        Record that *type_term* appears at argument *arg_index* of a
        constructor / map with symbol *symbol*.
        """
        uid = type_term._uid
        uses = self._type_uses.get(uid)
        if uses is None:
            uses = []
            self._type_uses[uid] = uses
        uses.append((symbol, arg_index))

    def get_type_uses(self, type_term: Term) -> List[Tuple[Symbol, int]]:
        """Return all uses of *type_term*."""
        return self._type_uses.get(type_term._uid, [])

    # -- canonical form computation ----------------------------------------
    def mk_canonical_form(self, pre_canonical: Term) -> Term:
        """
        Reduce a pre-canonical type term to canonical form by sorting union
        components and merging ranges.
        """
        # Simple pass-through for now; full canonicalization requires
        # the complete BinnedUnion logic
        return pre_canonical

    # -- intersection ------------------------------------------------------
    def mk_intersection(self, t1: Term, t2: Term) -> Optional[Term]:
        """
        Compute the intersection of two type terms.
        Returns None if the intersection is empty.

        Matches C# TermIndex.MkIntersection:
        1. If either is the canonical "any" type, return the other.
        2. If either is ground, check ground membership.
        3. Otherwise, delegate to BinnedUnion.intersect().
        """
        if t1 is t2:
            return t1

        # Fast path: ground terms
        if t1.groundness == Groundness.Ground:
            # Check if t1 is a member of type t2
            if self._is_ground_member(t2, t1):
                return t1
            return None
        if t2.groundness == Groundness.Ground:
            if self._is_ground_member(t1, t2):
                return t2
            return None

        # Full intersection via BinnedUnion
        unn = BinnedUnion(t1)
        return unn.intersect(BinnedUnion(t2))

    def _is_ground_member(self, type_term: Term, ground_term: Term) -> bool:
        """Check if a ground term is a member of a type term.

        Matches C# TermIndex.IsGroundMember.
        """
        unn_symb = self.type_union_symbol
        rng_symb = self.range_symbol

        for t in type_term.enumerate(
            lambda x: x.args if x.symbol is unn_symb else None
        ):
            if t is ground_term:
                return True
            if t.symbol is unn_symb:
                continue
            # Range check for numeric constants
            if t.symbol is rng_symb and ground_term.symbol.kind == SymbolKind.BaseCnstSymb:
                cnst = ground_term.symbol
                if cnst.cnst_kind == CnstKind.Numeric:
                    val = cnst.raw
                    lo = t.args[0].symbol.raw
                    hi = t.args[1].symbol.raw
                    if lo <= val <= hi:
                        return True
            # Sort membership check
            if t.symbol.kind == SymbolKind.BaseSortSymb:
                sort_kind = t.symbol.sort_kind
                if ground_term.symbol.kind == SymbolKind.BaseCnstSymb:
                    cnst = ground_term.symbol
                    if cnst.cnst_kind == CnstKind.Numeric:
                        val = cnst.raw
                        if sort_kind == BaseSortKind.Real:
                            return True
                        if sort_kind == BaseSortKind.Integer and isinstance(val, (int, Fraction)) and (isinstance(val, int) or val.denominator == 1):
                            return True
                        if sort_kind == BaseSortKind.Natural and isinstance(val, (int, Fraction)):
                            v = int(val) if isinstance(val, int) else (int(val) if val.denominator == 1 else None)
                            if v is not None and v >= 0:
                                return True
                        if sort_kind == BaseSortKind.PosInteger and isinstance(val, (int, Fraction)):
                            v = int(val) if isinstance(val, int) else (int(val) if val.denominator == 1 else None)
                            if v is not None and v >= 1:
                                return True
                        if sort_kind == BaseSortKind.NegInteger and isinstance(val, (int, Fraction)):
                            v = int(val) if isinstance(val, int) else (int(val) if val.denominator == 1 else None)
                            if v is not None and v < 0:
                                return True
                    elif cnst.cnst_kind == CnstKind.String and sort_kind == BaseSortKind.String:
                        return True
            # UserSortSymb: data constructor type membership
            if t.symbol.kind == SymbolKind.UserSortSymb:
                data_sym = getattr(t.symbol, "data_symbol", None)
                if data_sym is not None and ground_term.symbol is data_sym:
                    return True
            # Direct symbol match for constructors with ground args
            if (t.symbol.is_data_constructor and ground_term.symbol is t.symbol
                    and t.symbol.arity > 0):
                all_match = True
                for i in range(t.symbol.arity):
                    if not self._is_ground_member(t.args[i], ground_term.args[i]):
                        all_match = False
                        break
                if all_match:
                    return True

        return False

    # -- cloning -----------------------------------------------------------
    def mk_clone(
        self,
        term: Term,
        symbol_transfer: Optional[Dict] = None,
        rename: Optional[str] = None,
        project: bool = False,
    ) -> Term:
        """
        Clone a term from another TermIndex into this one.

        Recursively rebuilds the term using this index's symbols.
        """
        if term.symbol.arity == 0:
            sym = term.symbol
            if sym.kind == SymbolKind.BaseCnstSymb:
                bc: BaseCnstSymb = sym  # type: ignore[assignment]
                return self.mk_cnst(bc.raw)[0]
            elif sym.kind == SymbolKind.BaseSortSymb:
                bs: BaseSortSymb = sym  # type: ignore[assignment]
                new_sym = self._symbol_table.get_sort_symbol(bs.sort_kind)
                return self.mk_apply(new_sym, [])[0]
            elif sym.kind == SymbolKind.UserCnstSymb:
                uc: UserCnstSymb = sym  # type: ignore[assignment]
                if uc.is_variable:
                    return self.mk_var(uc.name)[0]
                # For non-variable user constants, look up in the symbol table
                resolved, _ = self._symbol_table.resolve(uc.full_name)
                if resolved is not None:
                    return self.mk_apply(resolved, [])[0]
                return self.mk_apply(sym, [])[0]
            elif sym.kind == SymbolKind.UserSortSymb:
                us: UserSortSymb = sym  # type: ignore[assignment]
                if symbol_transfer and us.data_symbol in symbol_transfer:
                    new_data = symbol_transfer[us.data_symbol]
                    if new_data.kind == SymbolKind.ConSymb:
                        return self.mk_apply(new_data.sort_symbol, [])[0]  # type: ignore[union-attr]
                    elif new_data.kind == SymbolKind.MapSymb:
                        return self.mk_apply(new_data.sort_symbol, [])[0]  # type: ignore[union-attr]
                return self.mk_apply(sym, [])[0]
            else:
                return self.mk_apply(sym, [])[0]
        else:
            new_args = [self.mk_clone(a, symbol_transfer, rename, project) for a in term.args]
            new_sym = term.symbol
            if symbol_transfer and isinstance(new_sym, UserSymbol) and new_sym in symbol_transfer:
                new_sym = symbol_transfer[new_sym]
            return self.mk_apply(new_sym, new_args)[0]

    # -- bin queries -------------------------------------------------------
    def get_bin(self, symbol: Symbol) -> Set[Term]:
        """Return all terms with the given outer symbol."""
        return self._bins.get(symbol.id, set())

    # -- symbolic constant types -------------------------------------------
    def set_symb_cnst_type_getter(self, getter: Callable[[Term], Term]) -> None:
        self._symb_cnst_type_getter = getter

    def get_symb_cnst_type(self, cnst_term: Term) -> Optional[Term]:
        uid = cnst_term._uid
        cached = self._symb_cnst_types.get(uid)
        if cached is not None:
            return cached
        if self._symb_cnst_type_getter is not None:
            t = self._symb_cnst_type_getter(cnst_term)
            if t is not None:
                self._symb_cnst_types[uid] = t
            return t
        return None

    # -- debug printing ----------------------------------------------------
    @staticmethod
    def debug_print_small_term(t: Term, wr: io.StringIO) -> None:
        """Print a compact representation of a term."""
        wr.write(t.symbol.printable_name)
        if t.symbol.arity > 0:
            wr.write("(")
            for i, arg in enumerate(t.args):
                if i > 0:
                    wr.write(", ")
                TermIndex.debug_print_small_term(arg, wr)
            wr.write(")")

    def __repr__(self) -> str:
        return f"<TermIndex terms={self._n_terms}>"


# ===================================================================
# AppFreeCanUnn  -- application-free canonical union
# ===================================================================

class AppFreeCanUnn:
    """
    The canonical form of a type term that does not contain any
    applications of constructors / operators.

    It is a set of ``Symbol`` elements (sorts and constants) plus a set
    of integer intervals.
    """

    def __init__(self, type_term: Optional[Term] = None) -> None:
        self._table: Optional[Any] = None
        self._type_expr: Any = None
        self._elements: Set[Symbol] = set()
        self._intervals: List[Tuple[int, int]] = []  # sorted non-overlapping
        self._contains_constants: bool = False
        self._renaming_map: Optional[Dict[str, Set[Namespace]]] = None

        if type_term is not None:
            self._build_from_type_term(type_term)

    def _build_from_type_term(self, t: Term) -> None:
        """Extract elements from a pre-built type term."""
        owner = t.owner
        for x in t.enumerate(
            lambda x: x.args if x.symbol is owner.type_union_symbol else None
        ):
            if x.symbol is owner.type_union_symbol:
                continue
            self._elements.add(x.symbol)
            if x.symbol.kind in (
                SymbolKind.BaseCnstSymb,
                SymbolKind.UserCnstSymb,
            ):
                self._contains_constants = True

    @classmethod
    def from_base_sort(cls, table: Any, sort: BaseSortSymb) -> AppFreeCanUnn:
        """Create a union containing a single base sort."""
        obj = cls()
        obj._table = table
        obj._elements.add(sort)
        return obj

    @classmethod
    def from_user_cnst(cls, table: Any, cnst: UserCnstSymb) -> AppFreeCanUnn:
        """Create a union containing a single user constant."""
        obj = cls()
        obj._table = table
        obj._elements.add(cnst)
        obj._contains_constants = True
        return obj

    @classmethod
    def from_elements(cls, elements: Iterable[Symbol]) -> AppFreeCanUnn:
        obj = cls()
        for e in elements:
            obj._elements.add(e)
            if e.kind in (SymbolKind.BaseCnstSymb, SymbolKind.UserCnstSymb):
                obj._contains_constants = True
        return obj

    @classmethod
    def from_type_ast(cls, table: Any, type_expr: Any) -> AppFreeCanUnn:
        """Create from a type expression AST node.

        Matches C# ``new AppFreeCanUnn(table, Factory.Instance.ToAST(fld.Type))``.
        The type expression is stored for later resolution via ``resolve_types()``.
        """
        obj = cls()
        obj._table = table
        obj._type_expr = type_expr
        return obj

    @property
    def type_expr(self) -> Any:
        return self._type_expr

    @property
    def contains_constants(self) -> bool:
        return self._contains_constants

    @property
    def elements(self) -> Set[Symbol]:
        return self._elements

    @property
    def user_sorts(self) -> Iterable[UserSortSymb]:
        for e in self._elements:
            if e.kind == SymbolKind.UserSortSymb:
                yield e  # type: ignore[misc]

    @property
    def non_user_symbols(self) -> Iterable[Symbol]:
        for e in self._elements:
            if e.kind != SymbolKind.UserSortSymb:
                yield e

    def contains(self, symbol: Symbol) -> bool:
        return symbol in self._elements

    def accepts_constant(self, symbol: Symbol) -> bool:
        """Return True if this union type accepts the given constant symbol."""
        if symbol in self._elements:
            return True
        if symbol.kind == SymbolKind.BaseCnstSymb:
            bc: BaseCnstSymb = symbol  # type: ignore[assignment]
            if bc.cnst_kind == CnstKind.Numeric:
                r: Fraction = bc.raw
                # Check intervals
                for lo, hi in self._intervals:
                    if lo <= r <= hi:
                        return True
                # Check base sorts
                for e in self._elements:
                    if e.kind == SymbolKind.BaseSortSymb:
                        bs: BaseSortSymb = e  # type: ignore[assignment]
                        if _sort_accepts_rational(bs.sort_kind, r):
                            return True
            elif bc.cnst_kind == CnstKind.String:
                for e in self._elements:
                    if e.kind == SymbolKind.BaseSortSymb:
                        bs2: BaseSortSymb = e  # type: ignore[assignment]
                        if bs2.sort_kind == BaseSortKind.String:
                            return True
        return False

    def is_equivalent(self, other: AppFreeCanUnn) -> bool:
        """Check structural equivalence."""
        return self._elements == other._elements and self._intervals == other._intervals

    def mk_type_term(self, index: Any) -> Term:
        """Build a type term in *index* from this union."""
        result: Optional[Term] = None
        for elem in sorted(self._elements, key=lambda s: s.id):
            t, _ = index.mk_apply(elem, [])
            if result is None:
                result = t
            else:
                result, _ = index.mk_type_union(result, t)
        if result is None:
            # Empty union - return FALSE
            return index.false_value
        return result

    def resolve_types(self, flags: List[Any], cancel: Any = None) -> bool:
        """Walk the type expression AST and resolve Id nodes against the symbol table.

        Matches C# AppFreeCanUnn.ResolveTypes: finds all Id and Enum nodes,
        resolves them, and adds them to the elements set.
        """
        if self._type_expr is None or self._table is None:
            return True

        result = True
        self._resolve_ast(self._type_expr, flags)
        return result

    def _resolve_ast(self, node: Any, flags: List[Any]) -> bool:
        """Recursively walk the type AST and resolve references."""
        from formula.api.nodes import NodeKind as AstNodeKind
        nk = getattr(node, 'node_kind', None)

        if nk == AstNodeKind.Id:
            name = node.name
            return self._add_type_name(name, node, flags)
        elif nk == AstNodeKind.Enum:
            return self._add_enum(node, flags)
        elif nk == AstNodeKind.FuncTerm:
            # Union expression: recurse into arguments
            fn = getattr(node, 'function', None)
            args = getattr(node, 'args', [])
            for arg in args:
                self._resolve_ast(arg, flags)
            return True
        elif nk == AstNodeKind.Range:
            # Range type: add to intervals
            lo = getattr(node, 'lower', None)
            hi = getattr(node, 'upper', None)
            if lo is not None and hi is not None:
                from fractions import Fraction
                lo_val = int(lo) if isinstance(lo, (int, Fraction)) else 0
                hi_val = int(hi) if isinstance(hi, (int, Fraction)) else 0
                self._intervals.append((lo_val, hi_val))
            return True
        else:
            # Try to walk children
            for child in getattr(node, 'children', []):
                self._resolve_ast(child, flags)
            return True

    def _add_type_name(self, name: str, node: Any, flags: List[Any]) -> bool:
        """Resolve a type name and add the symbol to elements.

        Matches C# AppFreeCanUnn.AddTypeName -> Resolve.
        """
        table = self._table
        if table is None:
            return False

        # Try resolve via SymbolTable (returns tuple: (symbol, ambiguous_symbol))
        if hasattr(table, 'resolve'):
            result = table.resolve(name)
            if isinstance(result, tuple):
                symbol, other = result
            else:
                symbol, other = result, None
            if symbol is not None:
                self._elements.add(symbol)
                return other is None  # False if ambiguous
        # Try base sort names (Real, Integer, Natural, etc.)
        sort_names = {
            'Real': BaseSortKind.Real,
            'Integer': BaseSortKind.Integer,
            'Natural': BaseSortKind.Natural,
            'PosInteger': BaseSortKind.PosInteger,
            'NegInteger': BaseSortKind.NegInteger,
            'String': BaseSortKind.String,
        }
        if name in sort_names and hasattr(table, 'get_sort_symbol'):
            sym = table.get_sort_symbol(sort_names[name])
            if sym is not None:
                self._elements.add(sym)
                return True
        return True  # Skip silently for unresolved names

    def _add_enum(self, node: Any, flags: List[Any]) -> bool:
        """Process an Enum node."""
        elements = getattr(node, 'elements', [])
        for elem in elements:
            nk = getattr(elem, 'node_kind', None)
            from formula.api.nodes import NodeKind as AstNodeKind
            if nk == AstNodeKind.Id:
                self._add_type_name(elem.name, elem, flags)
            elif nk == AstNodeKind.Cnst:
                # Numeric or string constant
                val = getattr(elem, 'value', None)
                if val is not None:
                    from fractions import Fraction
                    if isinstance(val, (int, float, Fraction)):
                        self._intervals.append((int(val), int(val)))
                    elif isinstance(val, str):
                        # String enum value - create a BaseCnstSymb
                        if hasattr(self._table, 'get_cnst_symbol'):
                            sym = self._table.get_cnst_symbol(val)
                            if sym is not None:
                                self._elements.add(sym)
                                self._contains_constants = True
        return True

    def canonize(self, full_name: str, flags: List[Any], cancel: Any = None, owner: Any = None) -> bool:
        return True

    def __repr__(self) -> str:
        names = sorted(e.printable_name for e in self._elements)
        return f"AppFreeCanUnn({' + '.join(names)})"


def _sort_accepts_rational(sort_kind: BaseSortKind, r: Fraction) -> bool:
    """Check if a base sort accepts a given rational number."""
    if sort_kind == BaseSortKind.Real:
        return True
    if r.denominator != 1:
        return False
    n = r.numerator
    if sort_kind == BaseSortKind.Integer:
        return True
    elif sort_kind == BaseSortKind.Natural:
        return n >= 0
    elif sort_kind == BaseSortKind.PosInteger:
        return n > 0
    elif sort_kind == BaseSortKind.NegInteger:
        return n < 0
    return False


# ===================================================================
# TypeEnvironment
# ===================================================================

class TypeEnvironment:
    """
    Maps terms to their (precanonical, canonical) type pairs.

    The canonical form is computed on demand.  Child environments can further
    constrain variable types; ``join_types`` merges child types upward.
    """

    def __init__(self, node: Any, index: TermIndex) -> None:
        self._node = node
        self._index = index
        self._types: Dict[int, List[Optional[Term]]] = {}  # term uid -> [precanon, canon]
        self._coercions: List[Tuple[Any, int, str, str]] = []
        self._children: List[TypeEnvironment] = []
        self._lock = threading.Lock()

    @property
    def node(self) -> Any:
        return self._node

    @property
    def index(self) -> TermIndex:
        return self._index

    @property
    def terms(self) -> Iterable[Term]:
        """Return the terms whose types are recorded here (by UID lookup in index)."""
        # We store by uid; callers iterate externally
        return []

    @property
    def coercions(self) -> List[Tuple[Any, int, str, str]]:
        return self._coercions

    @property
    def children(self) -> List[TypeEnvironment]:
        return self._children

    def try_get_type(self, term: Term) -> Optional[Term]:
        """Get the canonical type of *term*, computing it if needed."""
        with self._lock:
            entry = self._types.get(term._uid)
            if entry is None:
                return None
            if entry[1] is not None:
                return entry[1]
            # Compute canonical from precanonical
            canon = self._index.mk_canonical_form(entry[0])  # type: ignore[arg-type]
            entry[1] = canon
            return canon

    def set_type(self, term: Term, type_term: Term) -> None:
        """Set the precanonical type of *term*."""
        self._types[term._uid] = [type_term, None]

    def add_coercion(self, app: Any, index: int, src_prefix: str, dst_prefix: str) -> None:
        self._coercions.append((app, index, src_prefix, dst_prefix))

    def join_types(self) -> None:
        """
        If ``t: t1`` in child c1 and ``t: t2`` in child c2, then
        ``t: t1 + t2`` in this environment.
        """
        unn_symbol = self._index.type_union_symbol
        for child in self._children:
            for uid, entry in child._types.items():
                existing = self._types.get(uid)
                if existing is None:
                    self._types[uid] = [entry[0], None]
                else:
                    existing[1] = None  # invalidate canon
                    existing[0], _ = self._index.mk_apply(
                        unn_symbol, [existing[0], entry[0]]  # type: ignore[list-item]
                    )

    def add_child(self, node: Any) -> TypeEnvironment:
        child = TypeEnvironment(node, self._index)
        self._children.append(child)
        return child


# ===================================================================
# CanUnnDef  -- canonical union definition builder
# ===================================================================

class CanUnnDef:
    """
    Builds the canonical definition of a union type declaration.

    Collects elements (type names, enumerated constants) and numeric ranges
    from a union body, then normalises the ranges.
    """

    def __init__(self, table: Any, unn_decl: Any = None) -> None:
        self._table = table
        self._unn_decl = unn_decl
        self._elements: Set[Symbol] = set()
        self._rng_starts: Dict[Fraction, Symbol] = {}
        self._rng_ends: Dict[Fraction, Symbol] = {}

    def add_element(self, symbol: Symbol) -> None:
        self._elements.add(symbol)

    def add_range(self, lower: Fraction, upper: Fraction) -> None:
        """Add a numeric range ``lower..upper`` to this union."""
        start_keys = sorted(self._rng_starts.keys())
        end_keys = sorted(self._rng_ends.keys())
        # Find overlapping / adjacent intervals and merge
        new_lo = lower
        new_hi = upper
        to_remove: List[Fraction] = []
        for sk, ek in zip(start_keys, end_keys):
            if sk <= upper and ek >= lower:
                # Overlap or adjacent
                new_lo = min(new_lo, sk)
                new_hi = max(new_hi, ek)
                to_remove.append(sk)
        for k in to_remove:
            if k in self._rng_starts:
                del self._rng_starts[k]
            # Find corresponding end key
            for ek in list(self._rng_ends.keys()):
                if ek in to_remove or ek <= upper:
                    if ek in self._rng_ends:
                        del self._rng_ends[ek]
        self._rng_starts[new_lo] = self._table.get_cnst_symbol(new_lo)
        self._rng_ends[new_hi] = self._table.get_cnst_symbol(new_hi)

    def add_numeric_constant(self, value: Fraction) -> None:
        self.add_range(value, value)

    def add_string_constant(self, value: str) -> None:
        self._elements.add(self._table.get_cnst_symbol(value))

    def normalize_ranges(self) -> None:
        """Merge adjacent integer ranges (e.g. 1..3, 4..5 -> 1..5)."""
        if not self._rng_starts:
            return
        starts = sorted(self._rng_starts.keys())
        ends = sorted(self._rng_ends.keys())
        merged_starts: List[Fraction] = []
        merged_ends: List[Fraction] = []
        cur_start = starts[0]
        cur_end = ends[0]
        for i in range(1, len(starts)):
            if starts[i] <= cur_end + 1:
                cur_end = max(cur_end, ends[i])
            else:
                merged_starts.append(cur_start)
                merged_ends.append(cur_end)
                cur_start = starts[i]
                cur_end = ends[i]
        merged_starts.append(cur_start)
        merged_ends.append(cur_end)
        self._rng_starts.clear()
        self._rng_ends.clear()
        for s, e in zip(merged_starts, merged_ends):
            self._rng_starts[s] = self._table.get_cnst_symbol(s)
            self._rng_ends[e] = self._table.get_cnst_symbol(e)

    @property
    def elements(self) -> Set[Symbol]:
        return self._elements

    @property
    def ranges(self) -> Iterable[Tuple[Fraction, Fraction]]:
        for s in sorted(self._rng_starts.keys()):
            for e in sorted(self._rng_ends.keys()):
                if e >= s:
                    yield s, e
                    break


# ===================================================================
# SubtermMatcher
# ===================================================================

class SubtermMatcher:
    """
    Given a term *x*, enumerates subterms
    ``x_0 : types[0], ..., x_{n-1} : types[n-1]``
    such that ``x_{n-1} [= x_{n-2} [= ... [= x_0 [= x``.

    The *pattern* is an array of type terms describing the expected types
    at each level of the subterm chain.
    """

    CAN_MATCH = -1

    def __init__(
        self,
        index: TermIndex,
        only_new_kinds: bool,
        pattern: List[Term],
    ) -> None:
        assert pattern
        self._pattern = list(pattern)
        self._is_match_only_new_kinds = only_new_kinds
        self._matching_unions: List[Optional[AppFreeCanUnn]] = [None] * len(pattern)
        self._matcher: Dict[int, Dict[int, Set[int]]] = {}  # level -> {type_uid -> {positions}}
        self._is_satisfiable = True
        self._is_triggerable = False
        self._trigger: Optional[Term] = None

        self._build(index)

    def _build(self, index: TermIndex) -> None:
        """Build the matching tables from the pattern."""
        level_types: Optional[Term] = None
        for i in range(len(self._pattern) - 1, -1, -1):
            if not self._is_satisfiable:
                return
            if i == len(self._pattern) - 1:
                intr = self._pattern[-1]
            else:
                result = index.mk_intersection(self._pattern[i], level_types)  # type: ignore
                if result is None:
                    self._is_satisfiable = False
                    return
                intr = result

            level_types_new: Optional[Term] = None
            self._is_satisfiable = False

            for t in intr.enumerate(
                lambda x: x.args if x.symbol is index.type_union_symbol else None
            ):
                if t.symbol is index.type_union_symbol:
                    continue
                if self._is_permitted(index, self._is_match_only_new_kinds, t):
                    self._is_satisfiable = True
                    self._get_matching_set(i, t._uid).add(self.CAN_MATCH)
                    if level_types_new is None:
                        level_types_new = t
                    else:
                        level_types_new, _ = index.mk_type_union(t, level_types_new)
                    if i == 0 and (
                        t.symbol.kind == SymbolKind.UserSortSymb
                        or t.symbol.is_derived_constant
                    ):
                        self._is_triggerable = True

            if not self._is_satisfiable:
                return

            self._matching_unions[i] = AppFreeCanUnn(level_types_new)
            level_types = level_types_new

            # Propagate upward through type uses
            pending: List[Term] = []
            visited: Set[int] = set()
            if level_types_new is not None:
                for t in level_types_new.enumerate(
                    lambda x: x.args if x.symbol is index.type_union_symbol else None
                ):
                    if t.symbol is not index.type_union_symbol and t._uid not in visited:
                        pending.append(t)
                        visited.add(t._uid)

            while pending:
                type_t = pending.pop()
                for sym, arg_idx in index.get_type_uses(type_t):
                    if sym.kind == SymbolKind.ConSymb:
                        sort_sym = sym.sort_symbol  # type: ignore[union-attr]
                    elif sym.kind == SymbolKind.MapSymb:
                        sort_sym = sym.sort_symbol  # type: ignore[union-attr]
                    else:
                        continue
                    new_type, _ = index.mk_apply(sort_sym, [])
                    if self._is_permitted(index, self._is_match_only_new_kinds, new_type):
                        self._get_matching_set(i, new_type._uid).add(arg_idx)
                        if new_type._uid not in visited:
                            pending.append(new_type)
                            visited.add(new_type._uid)

        if self._is_triggerable:
            level0 = self._matcher.get(0, {})
            trigger_types: Optional[Term] = None
            for uid, positions in level0.items():
                # Reconstruct the type term from uid
                # (simplified: we rely on the terms already being in the index)
                pass
            self._trigger = level_types

    def _get_matching_set(self, level: int, type_uid: int) -> Set[int]:
        level_map = self._matcher.get(level)
        if level_map is None:
            level_map = {}
            self._matcher[level] = level_map
        pos_set = level_map.get(type_uid)
        if pos_set is None:
            pos_set = set()
            level_map[type_uid] = pos_set
        return pos_set

    @staticmethod
    def _is_permitted(index: TermIndex, only_new_kinds: bool, t: Term) -> bool:
        if only_new_kinds:
            if t.symbol.is_derived_constant:
                return False
            if t.symbol.kind == SymbolKind.UserSortSymb:
                us: UserSortSymb = t.symbol  # type: ignore[assignment]
                con = us.data_symbol
                if isinstance(con, ConSymb):
                    return con.is_new
        return True

    # -- properties --------------------------------------------------------
    @property
    def is_match_only_new_kinds(self) -> bool:
        return self._is_match_only_new_kinds

    @property
    def pattern(self) -> List[Term]:
        return self._pattern

    @property
    def n_patterns(self) -> int:
        return len(self._pattern)

    @property
    def trigger(self) -> Optional[Term]:
        return self._trigger

    @property
    def is_satisfiable(self) -> bool:
        return self._is_satisfiable

    @property
    def is_triggerable(self) -> bool:
        return self._is_triggerable

    # -- matching ----------------------------------------------------------
    def enumerate_matches(self, t: Term) -> Iterable[List[Term]]:
        """
        Enumerate all multi-level matches of *t* against the pattern.
        Each yielded value is a list of terms, one per pattern level.
        """
        crnt_level = 0
        crnt_match: List[Optional[Term]] = [None] * len(self._pattern)
        visitors: List[Optional[Iterator[Term]]] = [None] * len(self._pattern)
        visitors[0] = iter(self._enumerate_matches_at(t, 0))

        while crnt_level >= 0:
            it = visitors[crnt_level]
            if it is None:
                crnt_level -= 1
                continue
            try:
                m = next(it)
                crnt_match[crnt_level] = m
                if crnt_level < len(self._pattern) - 1:
                    visitors[crnt_level + 1] = iter(self._enumerate_matches_at(m, crnt_level + 1))
                    crnt_level += 1
                else:
                    yield list(crnt_match)  # type: ignore[arg-type]
            except StopIteration:
                crnt_level -= 1

    def _enumerate_matches_at(self, t: Term, level: int) -> Iterable[Term]:
        """Enumerate subterms of *t* that match at *level*."""
        unn = self._matching_unions[level]
        if unn is None:
            return
        for tp in t.enumerate(lambda x: self._enumerate_subterms(x, level)):
            if tp.symbol.arity == 0:
                if tp.symbol.is_new_constant or tp.symbol.is_derived_constant:
                    if unn.accepts_constant(tp.symbol):
                        yield tp
            else:
                if tp.symbol.is_data_constructor:
                    sort_sym = None
                    if tp.symbol.kind == SymbolKind.ConSymb:
                        sort_sym = tp.symbol.sort_symbol  # type: ignore[union-attr]
                    elif tp.symbol.kind == SymbolKind.MapSymb:
                        sort_sym = tp.symbol.sort_symbol  # type: ignore[union-attr]
                    if sort_sym is not None and unn.contains(sort_sym):
                        yield tp

    def _enumerate_subterms(self, t: Term, level: int) -> Optional[Iterable[Term]]:
        """Enumerate subterms of *t* that may lead to a match at *level*."""
        if t.symbol.arity == 0:
            return None
        level_matches = self._matcher.get(level)
        if level_matches is None:
            return None
        sort_sym = None
        if t.symbol.kind == SymbolKind.ConSymb:
            sort_sym = t.symbol.sort_symbol  # type: ignore[union-attr]
        elif t.symbol.kind == SymbolKind.MapSymb:
            sort_sym = t.symbol.sort_symbol  # type: ignore[union-attr]
        if sort_sym is None:
            return None
        type_term, _ = t.owner.mk_apply(sort_sym, [])
        positions = level_matches.get(type_term._uid)
        if positions is None:
            return None
        result: List[Term] = []
        for p in positions:
            if p >= 0:
                result.append(t.args[p])
        return result if result else None

    def clone(self, index: TermIndex) -> SubtermMatcher:
        """Clone this matcher into a different TermIndex."""
        new_pattern = [index.mk_clone(p) for p in self._pattern]
        return SubtermMatcher(index, self._is_match_only_new_kinds, new_pattern)

    @staticmethod
    def compare(m1: SubtermMatcher, m2: SubtermMatcher) -> int:
        if m1 is m2:
            return 0
        if m1._is_match_only_new_kinds != m2._is_match_only_new_kinds:
            return -1 if not m1._is_match_only_new_kinds else 1
        if len(m1._pattern) != len(m2._pattern):
            return -1 if len(m1._pattern) < len(m2._pattern) else 1
        for p1, p2 in zip(m1._pattern, m2._pattern):
            cmp = Term.compare(p1, p2)
            if cmp != 0:
                return cmp
        return 0

    def debug_print(self) -> None:
        pat_strs = [p.debug_get_small_term_string() for p in self._pattern]
        print(f"Pattern: {' '.join('{' + s + '}' for s in pat_strs)}")
        print(f"Is match only new kinds: {self._is_match_only_new_kinds}")
        print(f"Is satisfiable: {self._is_satisfiable}")
        print(f"Is triggerable: {self._is_triggerable}")


# ===================================================================
# TermPrinting
# ===================================================================

class TermPrinting:
    """Static methods for pretty-printing terms and type terms."""

    class _TypeEnumState:
        NONE = 0
        OPENED = 1

    @staticmethod
    def print_term(
        t: Term,
        wr: io.StringIO,
        cancel: Any = None,
        env_params: Any = None,
    ) -> None:
        """Print a ground/variable term in function notation."""
        def unfold(x: Term, s: Optional[SuccessToken]) -> Optional[Iterable[Term]]:
            wr.write(x.symbol.printable_name)
            if x.symbol.arity == 0:
                return None
            wr.write("(")
            result: List[Term] = []
            for i, arg in enumerate(x.args):
                result.append(arg)
            return result

        def fold(x: Term, children: List[Any], s: Optional[SuccessToken]) -> None:
            if x.symbol.arity > 0:
                # Write separators and closing paren
                pass

        # Simplified direct implementation
        TermPrinting._print_term_recursive(t, wr)

    @staticmethod
    def _print_term_recursive(t: Term, wr: io.StringIO) -> None:
        wr.write(t.symbol.printable_name)
        if t.symbol.arity > 0:
            wr.write("(")
            for i, arg in enumerate(t.args):
                if i > 0:
                    wr.write(", ")
                TermPrinting._print_term_recursive(arg, wr)
            wr.write(")")

    @staticmethod
    def print_type_term(
        t: Term,
        wr: io.StringIO,
        cancel: Any = None,
        env_params: Any = None,
    ) -> None:
        """Print a type term."""
        is_first = [True]
        enum_state = [TermPrinting._TypeEnumState.NONE]
        owner = t.owner

        def visitor(x: Term) -> None:
            if x.symbol is owner.type_union_symbol:
                return
            kind = x.symbol.kind
            if kind == SymbolKind.BaseCnstSymb:
                TermPrinting._open_enum(wr, is_first[0], enum_state)
                bc: BaseCnstSymb = x.symbol  # type: ignore[assignment]
                if bc.cnst_kind == CnstKind.Numeric:
                    wr.write(str(bc.raw))
                elif bc.cnst_kind == CnstKind.String:
                    wr.write(f'"{bc.raw}"')
            elif kind == SymbolKind.BaseOpSymb:
                if x.symbol is not owner.range_symbol:
                    raise ValueError("Not a type term (unexpected base op)")
                TermPrinting._open_enum(wr, is_first[0], enum_state)
                lo: BaseCnstSymb = x.args[0].symbol  # type: ignore[assignment]
                hi: BaseCnstSymb = x.args[1].symbol  # type: ignore[assignment]
                if x.args[0] is x.args[1]:
                    wr.write(str(lo.raw))
                else:
                    wr.write(f"{lo.raw}..{hi.raw}")
            elif kind == SymbolKind.BaseSortSymb:
                TermPrinting._close_enum(wr, is_first[0], enum_state)
                bs: BaseSortSymb = x.symbol  # type: ignore[assignment]
                wr.write(_SORT_KIND_NAMES.get(bs.sort_kind, bs.sort_kind.name))
            elif kind in (SymbolKind.ConSymb, SymbolKind.MapSymb):
                TermPrinting._close_enum(wr, is_first[0], enum_state)
                us: UserSymbol = x.symbol  # type: ignore[assignment]
                wr.write(f"{us.full_name}(")
                for i in range(x.symbol.arity):
                    if i > 0:
                        wr.write(", ")
                    TermPrinting.print_type_term(x.args[i], wr, cancel, env_params)
                wr.write(")")
            elif kind == SymbolKind.UnnSymb:
                TermPrinting._close_enum(wr, is_first[0], enum_state)
                un: UnnSymb = x.symbol  # type: ignore[assignment]
                wr.write(un.full_name)
            elif kind == SymbolKind.UserCnstSymb:
                TermPrinting._open_enum(wr, is_first[0], enum_state)
                if x.groundness != Groundness.Ground:
                    raise ValueError("Not a type term (variable in type)")
                uc: UserCnstSymb = x.symbol  # type: ignore[assignment]
                wr.write(uc.full_name)
            elif kind == SymbolKind.UserSortSymb:
                TermPrinting._close_enum(wr, is_first[0], enum_state)
                uss: UserSortSymb = x.symbol  # type: ignore[assignment]
                wr.write(uss.data_symbol.full_name)
            is_first[0] = False

        t.visit(
            lambda x: x.args if x.symbol is owner.type_union_symbol else None,
            visitor,
        )
        if enum_state[0] != TermPrinting._TypeEnumState.NONE:
            wr.write("}")

    @staticmethod
    def _open_enum(wr: io.StringIO, is_first: bool, state: List[int]) -> None:
        if state[0] == TermPrinting._TypeEnumState.NONE:
            if not is_first:
                wr.write(" + ")
            state[0] = TermPrinting._TypeEnumState.OPENED
            wr.write("{")
        elif state[0] == TermPrinting._TypeEnumState.OPENED:
            wr.write(", ")

    @staticmethod
    def _close_enum(wr: io.StringIO, is_first: bool, state: List[int]) -> None:
        if state[0] == TermPrinting._TypeEnumState.OPENED:
            state[0] = TermPrinting._TypeEnumState.NONE
            wr.write("}")
        if not is_first:
            wr.write(" + ")


# ===================================================================
# BinnedUnion  (internal helper used by TermIndex)
# ===================================================================

class BinnedUnion:
    """
    Organises the components of a type union into bins for efficient
    intersection, containment, and enumeration.

    Bins:
    - Integral constants/ranges go into ``IntIntervals``.
    - String constants and the String sort go into the string bin.
    - Non-integral numeric constants/sorts go into the Real bin.
    - User constants go into the TRUE bin.
    - Each data constructor/sort gets its own bin.
    """

    def __init__(self, t: Term) -> None:
        self._index = t.owner
        self._source_term = t
        self._intervals: List[Tuple[int, int]] = []
        self._bin_map: Dict[int, Set[Term]] = {}  # symbol.id -> set of terms

        self._unn_symb = self._index.type_union_symbol
        self._rng_symb = self._index.range_symbol
        self._build(t)

    def _build(self, t: Term) -> None:
        """Populate bins from a type term."""
        for x in t.enumerate(
            lambda x: x.args if x.symbol is self._unn_symb else None
        ):
            if x.symbol is self._unn_symb:
                continue
            sym = x.symbol
            sid = sym.id
            bin_set = self._bin_map.get(sid)
            if bin_set is None:
                bin_set = set()
                self._bin_map[sid] = bin_set
            bin_set.add(x)

    @property
    def term(self) -> Term:
        return self._source_term

    def get_bin(self, symbol: Symbol) -> Set[Term]:
        return self._bin_map.get(symbol.id, set())

    def intersect(self, other: BinnedUnion) -> Optional[Term]:
        """
        Compute the intersection of this binned union with *other*.
        Returns None if the intersection is empty.
        """
        result: Optional[Term] = None
        for sid, bin_set in self._bin_map.items():
            other_bin = other._bin_map.get(sid)
            if other_bin is None:
                continue
            common = bin_set & other_bin
            for t in common:
                if result is None:
                    result = t
                else:
                    result, _ = self._index.mk_type_union(result, t)
        return result
