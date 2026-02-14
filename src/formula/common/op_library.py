"""
Port of Src/Core/Common/Symbols/OpLibrary.cs.

Provides the built-in FORMULA operator library:
  - Arithmetic:  +, -, *, /, mod, neg, qtnt, gcd, lcm, sign, ...
  - Relational:  =, !=, <, <=, >, >=
  - Reserved:    range (..), type union (+), select (.), relabel, find, typerel
  - String:      strJoin, strLength, strFind, strGetAt, strLower, strUpper, ...
  - Aggregators: count, no, max, min, toList, toOrdinal, andAll, gcdAll, lcmAll
  - Symbolic:    symAnd, symAndAll, symCount, symMax

Each operator has:
  - validator       : checks syntactic correctness
  - upward_approx   : conservative over-approximation of the result type
  - downward_approx : conservative under-approximation of argument types
  - evaluator       : concrete ground evaluation
  - app_constrainer : optional implicit constraints (e.g., y != 0 for x / y)
  - sym_evaluator   : optional symbolic evaluation

This module also exports ``register_ops(symbol_table)`` which populates a
``SymbolTable`` with all built-in operator symbols.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
)

from formula.common.symbol_types import (
    BaseOpSymb,
    BaseSortKind,
    OpKind,
    RelKind,
    ReservedOpKind,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Types that distinguish at least this many numbers are widened into an
# infinite set of integers.
NUM_WIDENING_WIDTH = 101


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _validate_always(_node: Any, _flags: List[Any]) -> bool:
    """Accept any syntactic application."""
    return True


def _validate_numeric_args(node: Any, flags: List[Any]) -> bool:
    """Validate that arguments are numeric."""
    # In a full implementation this would check the AST node.
    return True


def _validate_string_args(node: Any, flags: List[Any]) -> bool:
    return True


def _validate_rel_args(node: Any, flags: List[Any]) -> bool:
    return True


# ---------------------------------------------------------------------------
# Type approximation helpers
# ---------------------------------------------------------------------------

def _approx_identity(index: Any, args: Sequence[Any]) -> List[Any]:
    """Identity approximation: return args unchanged."""
    return list(args)


def _approx_numeric_binary(index: Any, args: Sequence[Any]) -> List[Any]:
    """Approximate the result type of a binary numeric operation."""
    return list(args)


def _approx_numeric_unary(index: Any, args: Sequence[Any]) -> List[Any]:
    return list(args)


def _approx_boolean(index: Any, args: Sequence[Any]) -> List[Any]:
    return list(args)


def _approx_string_result(index: Any, args: Sequence[Any]) -> List[Any]:
    return list(args)


def _no_approx(index: Any, args: Sequence[Any]) -> List[Any]:
    return list(args)


# ---------------------------------------------------------------------------
# Evaluators  (concrete ground evaluation)
# ---------------------------------------------------------------------------

def _eval_add(executer: Any, bindables: List[Any]) -> Any:
    """Evaluate addition."""
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is None or b is None:
        return None
    return _mk_cnst_term(executer, a + b)


def _eval_sub(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is None or b is None:
        return None
    return _mk_cnst_term(executer, a - b)


def _eval_mul(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is None or b is None:
        return None
    return _mk_cnst_term(executer, a * b)


def _eval_div(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is None or b is None or b == 0:
        return None
    return _mk_cnst_term(executer, Fraction(a, b))


def _eval_mod(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is None or b is None or b == 0:
        return None
    if a.denominator != 1 or b.denominator != 1:
        return None
    return _mk_cnst_term(executer, Fraction(a.numerator % b.numerator))


def _eval_neg(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    if a is None:
        return None
    return _mk_cnst_term(executer, -a)


def _eval_qtnt(executer: Any, bindables: List[Any]) -> Any:
    """Integer quotient (truncated toward zero)."""
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is None or b is None or b == 0:
        return None
    if a.denominator != 1 or b.denominator != 1:
        return None
    return _mk_cnst_term(executer, Fraction(int(a.numerator / b.numerator)))


def _eval_sign(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    if a is None:
        return None
    if a > 0:
        return _mk_cnst_term(executer, Fraction(1))
    elif a < 0:
        return _mk_cnst_term(executer, Fraction(-1))
    else:
        return _mk_cnst_term(executer, Fraction(0))


def _eval_gcd(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is None or b is None:
        return None
    if a.denominator != 1 or b.denominator != 1:
        return None
    return _mk_cnst_term(executer, Fraction(math.gcd(abs(a.numerator), abs(b.numerator))))


def _eval_lcm(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is None or b is None:
        return None
    if a.denominator != 1 or b.denominator != 1:
        return None
    g = math.gcd(abs(a.numerator), abs(b.numerator))
    if g == 0:
        return _mk_cnst_term(executer, Fraction(0))
    return _mk_cnst_term(executer, Fraction(abs(a.numerator * b.numerator) // g))


def _eval_to_natural(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    if a is None:
        return None
    if a.denominator != 1:
        return None
    n = abs(a.numerator)
    return _mk_cnst_term(executer, Fraction(n))


def _eval_count(executer: Any, bindables: List[Any]) -> Any:
    """count is an aggregation op; handled by the executer."""
    return None


def _eval_no(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_max(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_min(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_to_list(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_to_ordinal(executer: Any, bindables: List[Any]) -> Any:
    return None


# -- relational evaluators ------------------------------------------------

def _eval_eq(executer: Any, bindables: List[Any]) -> Any:
    a = bindables[0].binding
    b = bindables[1].binding
    if a is b:
        return _mk_true(executer)
    return None


def _eval_neq(executer: Any, bindables: List[Any]) -> Any:
    a = bindables[0].binding
    b = bindables[1].binding
    if a is not b:
        return _mk_true(executer)
    return None


def _eval_lt(executer: Any, bindables: List[Any]) -> Any:
    """Matches C# Evaluator_Lt: uses lexicographic compare."""
    a = bindables[0].binding
    b = bindables[1].binding
    cmp = a.lexicographic_compare(b) if hasattr(a, 'lexicographic_compare') else 0
    return _mk_true(executer) if cmp < 0 else _mk_false(executer)


def _eval_le(executer: Any, bindables: List[Any]) -> Any:
    a = bindables[0].binding
    b = bindables[1].binding
    cmp = a.lexicographic_compare(b) if hasattr(a, 'lexicographic_compare') else 0
    return _mk_true(executer) if cmp <= 0 else _mk_false(executer)


def _eval_gt(executer: Any, bindables: List[Any]) -> Any:
    a = bindables[0].binding
    b = bindables[1].binding
    cmp = a.lexicographic_compare(b) if hasattr(a, 'lexicographic_compare') else 0
    return _mk_true(executer) if cmp > 0 else _mk_false(executer)


def _eval_ge(executer: Any, bindables: List[Any]) -> Any:
    a = bindables[0].binding
    b = bindables[1].binding
    cmp = a.lexicographic_compare(b) if hasattr(a, 'lexicographic_compare') else 0
    return _mk_true(executer) if cmp >= 0 else _mk_false(executer)


# -- string evaluators ----------------------------------------------------

def _eval_str_join(executer: Any, bindables: List[Any]) -> Any:
    a = _to_string(bindables[0].binding)
    b = _to_string(bindables[1].binding)
    if a is None or b is None:
        return None
    return _mk_str_term(executer, a + b)


def _eval_str_length(executer: Any, bindables: List[Any]) -> Any:
    a = _to_string(bindables[0].binding)
    if a is None:
        return None
    return _mk_cnst_term(executer, Fraction(len(a)))


def _eval_str_find(executer: Any, bindables: List[Any]) -> Any:
    haystack = _to_string(bindables[0].binding)
    needle = _to_string(bindables[1].binding)
    if haystack is None or needle is None:
        return None
    idx = haystack.find(needle)
    return _mk_cnst_term(executer, Fraction(idx))


def _eval_str_get_at(executer: Any, bindables: List[Any]) -> Any:
    s = _to_string(bindables[0].binding)
    i = _to_fraction(bindables[1].binding)
    if s is None or i is None:
        return None
    idx = int(i)
    if 0 <= idx < len(s):
        return _mk_str_term(executer, s[idx])
    return None


def _eval_str_lower(executer: Any, bindables: List[Any]) -> Any:
    a = _to_string(bindables[0].binding)
    if a is None:
        return None
    return _mk_str_term(executer, a.lower())


def _eval_str_upper(executer: Any, bindables: List[Any]) -> Any:
    a = _to_string(bindables[0].binding)
    if a is None:
        return None
    return _mk_str_term(executer, a.upper())


def _eval_str_reverse(executer: Any, bindables: List[Any]) -> Any:
    a = _to_string(bindables[0].binding)
    if a is None:
        return None
    return _mk_str_term(executer, a[::-1])


def _eval_str_after(executer: Any, bindables: List[Any]) -> Any:
    s = _to_string(bindables[0].binding)
    i = _to_fraction(bindables[1].binding)
    if s is None or i is None:
        return None
    idx = int(i)
    if 0 <= idx <= len(s):
        return _mk_str_term(executer, s[idx:])
    return None


def _eval_str_before(executer: Any, bindables: List[Any]) -> Any:
    s = _to_string(bindables[0].binding)
    i = _to_fraction(bindables[1].binding)
    if s is None or i is None:
        return None
    idx = int(i)
    if 0 <= idx <= len(s):
        return _mk_str_term(executer, s[:idx])
    return None


def _eval_str_replace(executer: Any, bindables: List[Any]) -> Any:
    s = _to_string(bindables[0].binding)
    old = _to_string(bindables[1].binding)
    new = _to_string(bindables[2].binding)
    if s is None or old is None or new is None:
        return None
    return _mk_str_term(executer, s.replace(old, new))


def _eval_is_substring(executer: Any, bindables: List[Any]) -> Any:
    haystack = _to_string(bindables[0].binding)
    needle = _to_string(bindables[1].binding)
    if haystack is None or needle is None:
        return None
    if needle in haystack:
        return _mk_true(executer)
    return None


# -- reserved operation evaluators ----------------------------------------

def _eval_reserved(executer: Any, bindables: List[Any]) -> Any:
    """Reserved ops (Range, TypeUnn, Find, Conj, etc.) should never be evaluated.

    In C# these throw InvalidOperationException.
    """
    raise RuntimeError("Reserved operation should never be evaluated at runtime")


def _eval_select(executer: Any, bindables: List[Any]) -> Any:
    """Evaluate selector: target.label -> target.args[index].

    Matches C# OpLibrary.Evaluator_Select: looks up the label string
    in the target's data constructor and returns the corresponding argument.
    """
    from formula.common.symbol_types import BaseCnstSymb, CnstKind, ConSymb, MapSymb, SymbolKind
    target = bindables[0].binding
    if not target.symbol.is_data_constructor:
        return None
    label_sym = bindables[1].binding.symbol
    if not isinstance(label_sym, BaseCnstSymb) or label_sym.cnst_kind != CnstKind.String:
        return None
    label = label_sym.raw
    sym = target.symbol
    if sym.kind == SymbolKind.ConSymb:
        index = sym.get_label_index(label)
    elif sym.kind == SymbolKind.MapSymb:
        index = sym.get_label_index(label)
    else:
        return None
    if index is None:
        return None
    return target.args[index]


def _eval_relabel(executer: Any, bindables: List[Any]) -> Any:
    """Evaluate relabel(from, to, term).

    Matches C# OpLibrary.Evaluator_Relabel: recursively walks the term tree
    and relabels user symbols by substituting the from-prefix with to-prefix.
    """
    from formula.common.symbol_types import BaseCnstSymb, CnstKind, SymbolKind
    from_sym = bindables[0].binding.symbol
    to_sym = bindables[1].binding.symbol
    if (not isinstance(from_sym, BaseCnstSymb) or from_sym.cnst_kind != CnstKind.String or
            not isinstance(to_sym, BaseCnstSymb) or to_sym.cnst_kind != CnstKind.String):
        return None
    from_prefix = from_sym.raw
    to_prefix = to_sym.raw
    index = executer.index if hasattr(executer, 'index') else executer
    table = index.symbol_table

    def relabel_term(t):
        sym = t.symbol
        if sym.kind == SymbolKind.BaseCnstSymb:
            return t
        if t.args:
            new_args = [relabel_term(a) for a in t.args]
        else:
            new_args = []
        if sym.kind in (SymbolKind.ConSymb, SymbolKind.MapSymb, SymbolKind.UserCnstSymb):
            full_name = sym.full_name if hasattr(sym, 'full_name') else sym.name
            if full_name.startswith(from_prefix):
                new_name = to_prefix + full_name[len(from_prefix):]
                resolved = table.resolve(new_name)
                if resolved is not None:
                    sym = resolved
        result = index.mk_apply(sym, new_args)
        return result

    return relabel_term(bindables[2].binding)


# -- boolean evaluators ---------------------------------------------------

def _eval_and(executer: Any, bindables: List[Any]) -> Any:
    b1 = _to_bool(executer, bindables[0].binding)
    b2 = _to_bool(executer, bindables[1].binding)
    if b1 is None or b2 is None:
        return None
    return _mk_true(executer) if (b1 and b2) else _mk_false(executer)


def _eval_or(executer: Any, bindables: List[Any]) -> Any:
    b1 = _to_bool(executer, bindables[0].binding)
    b2 = _to_bool(executer, bindables[1].binding)
    if b1 is None or b2 is None:
        return None
    return _mk_true(executer) if (b1 or b2) else _mk_false(executer)


def _eval_not(executer: Any, bindables: List[Any]) -> Any:
    b1 = _to_bool(executer, bindables[0].binding)
    if b1 is None:
        return None
    return _mk_false(executer) if b1 else _mk_true(executer)


def _eval_impl(executer: Any, bindables: List[Any]) -> Any:
    b1 = _to_bool(executer, bindables[0].binding)
    b2 = _to_bool(executer, bindables[1].binding)
    if b1 is None or b2 is None:
        return None
    return _mk_true(executer) if (not b1 or b2) else _mk_false(executer)


# -- aggregation evaluators -----------------------------------------------

def _eval_count(executer: Any, bindables: List[Any]) -> Any:
    """count(compr): count matching results.

    Matches C# OpLibrary.Evaluator_Count: calls executer.query().
    """
    n_results = _query_count(executer, bindables[0].binding)
    return _mk_cnst_term(executer, Fraction(n_results))


def _eval_no(executer: Any, bindables: List[Any]) -> Any:
    """no(compr): true if no matching results."""
    n_results = _query_count(executer, bindables[0].binding)
    return _mk_true(executer) if n_results == 0 else _mk_false(executer)


def _eval_sum(executer: Any, bindables: List[Any]) -> Any:
    """sum(default, compr): sum the last arg of each result."""
    results = _query_results(executer, bindables[1].binding)
    if not results:
        return bindables[0].binding
    acc = Fraction(0)
    has_numeric = False
    for t in results:
        val = _to_fraction(t.args[t.symbol.arity - 1]) if t.args else None
        if val is not None:
            has_numeric = True
            acc += val
    return _mk_cnst_term(executer, acc) if has_numeric else bindables[0].binding


def _eval_prod(executer: Any, bindables: List[Any]) -> Any:
    """prod(default, compr): product of the last arg of each result."""
    results = _query_results(executer, bindables[1].binding)
    if not results:
        return bindables[0].binding
    acc = Fraction(1)
    has_numeric = False
    for t in results:
        val = _to_fraction(t.args[t.symbol.arity - 1]) if t.args else None
        if val is not None:
            has_numeric = True
            acc *= val
    return _mk_cnst_term(executer, acc) if has_numeric else bindables[0].binding


def _eval_max(executer: Any, bindables: List[Any]) -> Any:
    """max(a, b): lexicographic max of two terms."""
    a = bindables[0].binding
    b = bindables[1].binding
    cmp = a.lexicographic_compare(b) if hasattr(a, 'lexicographic_compare') else 0
    return a if cmp >= 0 else b


def _eval_min(executer: Any, bindables: List[Any]) -> Any:
    """min(a, b): lexicographic min of two terms."""
    a = bindables[0].binding
    b = bindables[1].binding
    cmp = a.lexicographic_compare(b) if hasattr(a, 'lexicographic_compare') else 0
    return a if cmp <= 0 else b


def _eval_max_all(executer: Any, bindables: List[Any]) -> Any:
    """maxAll(default, compr): max of the last arg of each result."""
    results = _query_results(executer, bindables[1].binding)
    if not results:
        return bindables[0].binding
    best = results[0].args[results[0].symbol.arity - 1] if results[0].args else results[0]
    for t in results[1:]:
        candidate = t.args[t.symbol.arity - 1] if t.args else t
        if hasattr(candidate, 'lexicographic_compare') and candidate.lexicographic_compare(best) > 0:
            best = candidate
    return best


def _eval_min_all(executer: Any, bindables: List[Any]) -> Any:
    """minAll(default, compr): min of the last arg of each result."""
    results = _query_results(executer, bindables[1].binding)
    if not results:
        return bindables[0].binding
    best = results[0].args[results[0].symbol.arity - 1] if results[0].args else results[0]
    for t in results[1:]:
        candidate = t.args[t.symbol.arity - 1] if t.args else t
        if hasattr(candidate, 'lexicographic_compare') and candidate.lexicographic_compare(best) < 0:
            best = candidate
    return best


def _eval_gcd_all(executer: Any, bindables: List[Any]) -> Any:
    """gcdAll(default, compr): GCD of the last arg of each result."""
    results = _query_results(executer, bindables[1].binding)
    if not results:
        return bindables[0].binding
    acc = None
    for t in results:
        val = _to_fraction(t.args[t.symbol.arity - 1]) if t.args else None
        if val is not None and val.denominator == 1:
            v = abs(val.numerator)
            acc = v if acc is None else math.gcd(acc, v)
    return _mk_cnst_term(executer, Fraction(acc)) if acc is not None else bindables[0].binding


def _eval_lcm_all(executer: Any, bindables: List[Any]) -> Any:
    """lcmAll(default, compr): LCM of the last arg of each result."""
    results = _query_results(executer, bindables[1].binding)
    if not results:
        return bindables[0].binding
    acc = None
    for t in results:
        val = _to_fraction(t.args[t.symbol.arity - 1]) if t.args else None
        if val is not None and val.denominator == 1:
            v = abs(val.numerator)
            if acc is None:
                acc = v
            else:
                g = math.gcd(acc, v)
                acc = abs(acc * v) // g if g != 0 else 0
    return _mk_cnst_term(executer, Fraction(acc)) if acc is not None else bindables[0].binding


def _eval_and_all(executer: Any, bindables: List[Any]) -> Any:
    """andAll(default, compr): AND of the last arg of each result."""
    results = _query_results(executer, bindables[1].binding)
    if not results:
        return bindables[0].binding
    for t in results:
        last = t.args[t.symbol.arity - 1] if t.args else t
        b = _to_bool(executer, last)
        if b is not None and not b:
            return _mk_false(executer)
    return _mk_true(executer)


def _eval_or_all(executer: Any, bindables: List[Any]) -> Any:
    """orAll(default, compr): OR of the last arg of each result."""
    results = _query_results(executer, bindables[1].binding)
    if not results:
        return bindables[0].binding
    for t in results:
        last = t.args[t.symbol.arity - 1] if t.args else t
        b = _to_bool(executer, last)
        if b is not None and b:
            return _mk_true(executer)
    return _mk_false(executer)


def _eval_to_list(executer: Any, bindables: List[Any]) -> Any:
    """toList(cons, nil, compr): build a list from query results."""
    # cons = bindables[0], nil = bindables[1], compr = bindables[2]
    return None  # List construction requires deep integration with term creation


def _eval_to_ordinal(executer: Any, bindables: List[Any]) -> Any:
    """toOrdinal(cons, nil, compr): build an ordinal-indexed list."""
    return None  # Ordinal construction requires deep integration with term creation


def _eval_to_string(executer: Any, bindables: List[Any]) -> Any:
    """toString(term): convert a term to its string representation."""
    t = bindables[0].binding
    return _mk_str_term(executer, str(t))


def _eval_to_symbol(executer: Any, bindables: List[Any]) -> Any:
    """toSymbol(string): convert a string to a symbolic constant."""
    s = _to_string(bindables[0].binding)
    if s is None:
        return None
    # Would need to look up or create a UserCnstSymb with this name
    return None


# -- reflection evaluators ------------------------------------------------

def _eval_rfl_is_member(executer: Any, bindables: List[Any]) -> Any:
    """rflIsMember(term, type): check if term is a member of type."""
    return None  # Requires type membership checking infrastructure


def _eval_rfl_is_subtype(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_rfl_get_arg_type(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_rfl_get_arity(executer: Any, bindables: List[Any]) -> Any:
    """rflGetArity(term): get the arity of a term's constructor."""
    t = bindables[0].binding
    if t is not None and t.symbol.is_data_constructor:
        return _mk_cnst_term(executer, Fraction(t.symbol.arity))
    return None


# -- list evaluators -------------------------------------------------------

def _eval_lst_length(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_lst_reverse(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_lst_find(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_lst_find_all(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_lst_find_all_not(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_lst_get_at(executer: Any, bindables: List[Any]) -> Any:
    return None


# -- symbolic evaluators --------------------------------------------------

def _eval_sym_and(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_sym_and_all(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_sym_count(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_sym_max(executer: Any, bindables: List[Any]) -> Any:
    return None


# -- app constrainers -----------------------------------------------------

def _constrain_div(index: Any, args: Sequence[Any]) -> Iterable[Tuple[RelKind, Any, Any]]:
    """Division implies the divisor is nonzero."""
    zero, _ = index.mk_cnst(Fraction(0))
    yield (RelKind.Neq, args[1], zero)


def _constrain_mod(index: Any, args: Sequence[Any]) -> Iterable[Tuple[RelKind, Any, Any]]:
    zero, _ = index.mk_cnst(Fraction(0))
    yield (RelKind.Neq, args[1], zero)


def _constrain_qtnt(index: Any, args: Sequence[Any]) -> Iterable[Tuple[RelKind, Any, Any]]:
    zero, _ = index.mk_cnst(Fraction(0))
    yield (RelKind.Neq, args[1], zero)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _to_fraction(term: Any) -> Optional[Fraction]:
    """Extract a Fraction from a term, or None."""
    if term is None:
        return None
    from formula.common.symbol_types import BaseCnstSymb, CnstKind
    sym = term.symbol
    if isinstance(sym, BaseCnstSymb) and sym.cnst_kind == CnstKind.Numeric:
        return sym.raw
    return None


def _to_string(term: Any) -> Optional[str]:
    """Extract a string from a term, or None."""
    if term is None:
        return None
    from formula.common.symbol_types import BaseCnstSymb, CnstKind
    sym = term.symbol
    if isinstance(sym, BaseCnstSymb) and sym.cnst_kind == CnstKind.String:
        return sym.raw
    return None


def _mk_cnst_term(executer: Any, value: Fraction) -> Any:
    """Create a constant term via the executer's index."""
    index = executer.index if hasattr(executer, 'index') else executer
    t, _ = index.mk_cnst(value)
    return t


def _mk_str_term(executer: Any, value: str) -> Any:
    index = executer.index if hasattr(executer, 'index') else executer
    t, _ = index.mk_cnst(value)
    return t


def _mk_true(executer: Any) -> Any:
    index = executer.index if hasattr(executer, 'index') else executer
    return index.true_value


def _mk_false(executer: Any) -> Any:
    index = executer.index if hasattr(executer, 'index') else executer
    return index.false_value


def _to_bool(executer: Any, term: Any) -> Optional[bool]:
    """Convert a term to a boolean (True/False), or None if not boolean."""
    if term is None:
        return None
    index = executer.index if hasattr(executer, 'index') else executer
    if term is index.true_value:
        return True
    if term is index.false_value:
        return False
    return None


def _query_count(executer: Any, compr_term: Any) -> int:
    """Query the executer for matching results and return the count.

    Matches C# facts.Query(). Falls back to 0 if query is not available.
    """
    if hasattr(executer, 'query'):
        results, count = executer.query(compr_term)
        return count
    return 0


def _query_results(executer: Any, compr_term: Any) -> List[Any]:
    """Query the executer for matching results and return the list.

    Matches C# facts.Query(). Falls back to empty list if query is not available.
    """
    if hasattr(executer, 'query'):
        results, _ = executer.query(compr_term)
        return list(results)
    return []


# ---------------------------------------------------------------------------
# Operator registration
# ---------------------------------------------------------------------------

# Operator definitions: (kind, arity, validator, up_approx, down_approx,
#                        evaluator, app_constrainer, sym_evaluator)

_ARITHMETIC_OPS: List[Tuple[OpKind, int, Any, Any, Any, Any, Any, Any]] = [
    (OpKind.Add,       2, _validate_numeric_args, _approx_numeric_binary, _approx_numeric_binary, _eval_add,       None,            None),
    (OpKind.Sub,       2, _validate_numeric_args, _approx_numeric_binary, _approx_numeric_binary, _eval_sub,       None,            None),
    (OpKind.Mul,       2, _validate_numeric_args, _approx_numeric_binary, _approx_numeric_binary, _eval_mul,       None,            None),
    (OpKind.Div,       2, _validate_numeric_args, _approx_numeric_binary, _approx_numeric_binary, _eval_div,       _constrain_div,  None),
    (OpKind.Mod,       2, _validate_numeric_args, _approx_numeric_binary, _approx_numeric_binary, _eval_mod,       _constrain_mod,  None),
    (OpKind.Neg,       1, _validate_numeric_args, _approx_numeric_unary,  _approx_numeric_unary,  _eval_neg,       None,            None),
    (OpKind.Qtnt,      2, _validate_numeric_args, _approx_numeric_binary, _approx_numeric_binary, _eval_qtnt,      _constrain_qtnt, None),
    (OpKind.Sign,      1, _validate_numeric_args, _approx_numeric_unary,  _approx_numeric_unary,  _eval_sign,      None,            None),
    (OpKind.GCD,       2, _validate_numeric_args, _approx_numeric_binary, _approx_numeric_binary, _eval_gcd,       None,            None),
    (OpKind.LCM,       2, _validate_numeric_args, _approx_numeric_binary, _approx_numeric_binary, _eval_lcm,       None,            None),
    (OpKind.ToNatural, 1, _validate_numeric_args, _approx_numeric_unary,  _approx_numeric_unary,  _eval_to_natural, None,           None),
]

_AGGREGATOR_OPS: List[Tuple[OpKind, int, Any, Any, Any, Any, Any, Any]] = [
    (OpKind.Count,      1, _validate_always, _approx_boolean,  _no_approx, _eval_count,      None, None),
    (OpKind.No,         1, _validate_always, _approx_boolean,  _no_approx, _eval_no,         None, None),
    (OpKind.Max,        2, _validate_always, _approx_boolean,  _no_approx, _eval_max,        None, None),
    (OpKind.Min,        2, _validate_always, _approx_boolean,  _no_approx, _eval_min,        None, None),
    (OpKind.Sum,        2, _validate_always, _approx_boolean,  _no_approx, _eval_sum,        None, None),
    (OpKind.Prod,       2, _validate_always, _approx_boolean,  _no_approx, _eval_prod,       None, None),
    (OpKind.MaxAll,     2, _validate_always, _approx_boolean,  _no_approx, _eval_max_all,    None, None),
    (OpKind.MinAll,     2, _validate_always, _approx_boolean,  _no_approx, _eval_min_all,    None, None),
    (OpKind.ToList,     3, _validate_always, _approx_boolean,  _no_approx, _eval_to_list,    None, None),
    (OpKind.ToOrdinal,  3, _validate_always, _approx_boolean,  _no_approx, _eval_to_ordinal, None, None),
    (OpKind.GCDAll,     2, _validate_always, _approx_boolean,  _no_approx, _eval_gcd_all,    None, None),
    (OpKind.LCMAll,     2, _validate_always, _approx_boolean,  _no_approx, _eval_lcm_all,    None, None),
    (OpKind.AndAll,     2, _validate_always, _approx_boolean,  _no_approx, _eval_and_all,    None, None),
    (OpKind.OrAll,      2, _validate_always, _approx_boolean,  _no_approx, _eval_or_all,     None, None),
]

_BOOLEAN_OPS: List[Tuple[OpKind, int, Any, Any, Any, Any, Any, Any]] = [
    (OpKind.And,        2, _validate_always, _approx_boolean,  _approx_boolean, _eval_and,   None, None),
    (OpKind.Or,         2, _validate_always, _approx_boolean,  _approx_boolean, _eval_or,    None, None),
    (OpKind.Not,        1, _validate_always, _approx_boolean,  _approx_boolean, _eval_not,   None, None),
    (OpKind.Impl,       2, _validate_always, _approx_boolean,  _approx_boolean, _eval_impl,  None, None),
]

_CONVERSION_OPS: List[Tuple[OpKind, int, Any, Any, Any, Any, Any, Any]] = [
    (OpKind.ToString,   1, _validate_always, _approx_string_result, _no_approx, _eval_to_string,   None, None),
    (OpKind.ToSymbol,   1, _validate_always, _no_approx,            _no_approx, _eval_to_symbol,   None, None),
]

_REFLECTION_OPS: List[Tuple[OpKind, int, Any, Any, Any, Any, Any, Any]] = [
    (OpKind.RflIsMember,    2, _validate_always, _approx_boolean, _no_approx, _eval_rfl_is_member,    None, None),
    (OpKind.RflIsSubtype,   2, _validate_always, _approx_boolean, _no_approx, _eval_rfl_is_subtype,   None, None),
    (OpKind.RflGetArgType,  2, _validate_always, _no_approx,      _no_approx, _eval_rfl_get_arg_type, None, None),
    (OpKind.RflGetArity,    1, _validate_always, _no_approx,      _no_approx, _eval_rfl_get_arity,    None, None),
]

_LIST_OPS: List[Tuple[OpKind, int, Any, Any, Any, Any, Any, Any]] = [
    (OpKind.LstLength,      2, _validate_always, _no_approx, _no_approx, _eval_lst_length,       None, None),
    (OpKind.LstReverse,     2, _validate_always, _no_approx, _no_approx, _eval_lst_reverse,      None, None),
    (OpKind.LstFind,        4, _validate_always, _no_approx, _no_approx, _eval_lst_find,         None, None),
    (OpKind.LstFindAll,     3, _validate_always, _no_approx, _no_approx, _eval_lst_find_all,     None, None),
    (OpKind.LstFindAllNot,  3, _validate_always, _no_approx, _no_approx, _eval_lst_find_all_not, None, None),
    (OpKind.LstGetAt,       3, _validate_always, _no_approx, _no_approx, _eval_lst_get_at,       None, None),
]

_STRING_OPS: List[Tuple[OpKind, int, Any, Any, Any, Any, Any, Any]] = [
    (OpKind.StrJoin,       2, _validate_string_args,  _approx_string_result, _no_approx, _eval_str_join,       None, None),
    (OpKind.StrLength,     1, _validate_string_args,  _approx_string_result, _no_approx, _eval_str_length,     None, None),
    (OpKind.StrFind,       2, _validate_string_args,  _approx_string_result, _no_approx, _eval_str_find,       None, None),
    (OpKind.StrGetAt,      2, _validate_always,       _approx_string_result, _no_approx, _eval_str_get_at,     None, None),
    (OpKind.StrLower,      1, _validate_string_args,  _approx_string_result, _no_approx, _eval_str_lower,      None, None),
    (OpKind.StrUpper,      1, _validate_string_args,  _approx_string_result, _no_approx, _eval_str_upper,      None, None),
    (OpKind.StrReverse,    1, _validate_string_args,  _approx_string_result, _no_approx, _eval_str_reverse,    None, None),
    (OpKind.StrAfter,      2, _validate_always,       _approx_string_result, _no_approx, _eval_str_after,      None, None),
    (OpKind.StrBefore,     2, _validate_always,       _approx_string_result, _no_approx, _eval_str_before,     None, None),
    (OpKind.StrReplace,    3, _validate_string_args,  _approx_string_result, _no_approx, _eval_str_replace,    None, None),
    (OpKind.IsSubstring,   2, _validate_string_args,  _approx_boolean,       _no_approx, _eval_is_substring,   None, None),
]

_SYMBOLIC_OPS: List[Tuple[OpKind, int, Any, Any, Any, Any, Any, Any]] = [
    (OpKind.SymAnd,    2, _validate_always, _no_approx, _no_approx, _eval_sym_and,     None, _eval_sym_and),
    (OpKind.SymAndAll, 1, _validate_always, _no_approx, _no_approx, _eval_sym_and_all, None, _eval_sym_and_all),
    (OpKind.SymCount,  1, _validate_always, _no_approx, _no_approx, _eval_sym_count,   None, _eval_sym_count),
    (OpKind.SymMax,    1, _validate_always, _no_approx, _no_approx, _eval_sym_max,     None, _eval_sym_max),
]

_RELATIONAL_OPS: List[Tuple[RelKind, int, Any, Any, Any, Any]] = [
    (RelKind.Eq,  2, _validate_rel_args, _approx_boolean, _approx_boolean, _eval_eq),
    (RelKind.Neq, 2, _validate_rel_args, _approx_boolean, _approx_boolean, _eval_neq),
    (RelKind.Lt,  2, _validate_rel_args, _approx_boolean, _approx_boolean, _eval_lt),
    (RelKind.Le,  2, _validate_rel_args, _approx_boolean, _approx_boolean, _eval_le),
    (RelKind.Gt,  2, _validate_rel_args, _approx_boolean, _approx_boolean, _eval_gt),
    (RelKind.Ge,  2, _validate_rel_args, _approx_boolean, _approx_boolean, _eval_ge),
    (RelKind.No,  1, _validate_always,   _approx_boolean, _approx_boolean, _eval_no),
    (RelKind.Typ, 2, _validate_always,   _approx_boolean, _approx_boolean, _eval_reserved),
]

_RESERVED_OPS: List[Tuple[ReservedOpKind, int, Any, Any, Any, Any]] = [
    (ReservedOpKind.Range,   2, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.TypeUnn, 2, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.Select,  2, _validate_always, _no_approx, _no_approx, _eval_select),
    (ReservedOpKind.Relabel, 3, _validate_always, _no_approx, _no_approx, _eval_relabel),
    (ReservedOpKind.Find,    3, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.TypeRel, 2, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.Conj,    2, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.ConjR,   2, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.Disj,    2, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.Proj,    2, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.PRule,   3, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.CRule,   3, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.Rule,    2, _validate_always, _no_approx, _no_approx, _eval_reserved),
    (ReservedOpKind.Compr,   3, _validate_always, _no_approx, _no_approx, _eval_reserved),
]


def register_ops(symbol_table: Any) -> None:
    """
    Register all built-in operators with *symbol_table*.

    Call this once when creating a new ``SymbolTable`` to populate it
    with the standard FORMULA operator library.
    """
    # Arithmetic ops
    for kind, arity, val, up, down, ev, constr, sym_ev in _ARITHMETIC_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
            app_constrainer=constr,
            sym_evaluator=sym_ev,
        )
        symbol_table.register_op_symbol(sym)

    # Aggregator ops
    for kind, arity, val, up, down, ev, constr, sym_ev in _AGGREGATOR_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
            app_constrainer=constr,
            sym_evaluator=sym_ev,
        )
        symbol_table.register_op_symbol(sym)

    # String ops
    for kind, arity, val, up, down, ev, constr, sym_ev in _STRING_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
            app_constrainer=constr,
            sym_evaluator=sym_ev,
        )
        symbol_table.register_op_symbol(sym)

    # Boolean ops
    for kind, arity, val, up, down, ev, constr, sym_ev in _BOOLEAN_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
            app_constrainer=constr,
            sym_evaluator=sym_ev,
        )
        symbol_table.register_op_symbol(sym)

    # Conversion ops
    for kind, arity, val, up, down, ev, constr, sym_ev in _CONVERSION_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
            app_constrainer=constr,
            sym_evaluator=sym_ev,
        )
        symbol_table.register_op_symbol(sym)

    # Reflection ops
    for kind, arity, val, up, down, ev, constr, sym_ev in _REFLECTION_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
            app_constrainer=constr,
            sym_evaluator=sym_ev,
        )
        symbol_table.register_op_symbol(sym)

    # List ops
    for kind, arity, val, up, down, ev, constr, sym_ev in _LIST_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
            app_constrainer=constr,
            sym_evaluator=sym_ev,
        )
        symbol_table.register_op_symbol(sym)

    # Symbolic ops
    for kind, arity, val, up, down, ev, constr, sym_ev in _SYMBOLIC_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
            app_constrainer=constr,
            sym_evaluator=sym_ev,
        )
        symbol_table.register_op_symbol(sym)

    # Relational ops
    for kind, arity, val, up, down, ev in _RELATIONAL_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
        )
        symbol_table.register_op_symbol(sym)

    # Reserved ops
    for kind, arity, val, up, down, ev in _RESERVED_OPS:
        sym = BaseOpSymb(
            op_kind=kind,
            arity=arity,
            validator=val,
            upward_approx=up,
            downward_approx=down,
            evaluator=ev,
        )
        symbol_table.register_op_symbol(sym)


# Convenience: list of all operator kinds
ALL_OP_KINDS: List[Any] = (
    [k for k, *_ in _ARITHMETIC_OPS]
    + [k for k, *_ in _AGGREGATOR_OPS]
    + [k for k, *_ in _BOOLEAN_OPS]
    + [k for k, *_ in _CONVERSION_OPS]
    + [k for k, *_ in _REFLECTION_OPS]
    + [k for k, *_ in _LIST_OPS]
    + [k for k, *_ in _STRING_OPS]
    + [k for k, *_ in _SYMBOLIC_OPS]
)

ALL_REL_KINDS: List[RelKind] = [k for k, *_ in _RELATIONAL_OPS]

ALL_RESERVED_KINDS: List[ReservedOpKind] = [k for k, *_ in _RESERVED_OPS]
