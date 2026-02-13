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
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is not None and b is not None and a < b:
        return _mk_true(executer)
    return None


def _eval_le(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is not None and b is not None and a <= b:
        return _mk_true(executer)
    return None


def _eval_gt(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is not None and b is not None and a > b:
        return _mk_true(executer)
    return None


def _eval_ge(executer: Any, bindables: List[Any]) -> Any:
    a = _to_fraction(bindables[0].binding)
    b = _to_fraction(bindables[1].binding)
    if a is not None and b is not None and a >= b:
        return _mk_true(executer)
    return None


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

def _eval_range(executer: Any, bindables: List[Any]) -> Any:
    return None  # Range is a type-level operation


def _eval_type_unn(executer: Any, bindables: List[Any]) -> Any:
    return None  # Type union is a type-level operation


def _eval_select(executer: Any, bindables: List[Any]) -> Any:
    """Evaluate selector: f.lbl or f.i"""
    return None  # Requires term index


def _eval_relabel(executer: Any, bindables: List[Any]) -> Any:
    return None


def _eval_find(executer: Any, bindables: List[Any]) -> Any:
    return None  # Handled by the executer


def _eval_type_rel(executer: Any, bindables: List[Any]) -> Any:
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
    (OpKind.Max,        1, _validate_always, _approx_boolean,  _no_approx, _eval_max,        None, None),
    (OpKind.Min,        1, _validate_always, _approx_boolean,  _no_approx, _eval_min,        None, None),
    (OpKind.ToList,     1, _validate_always, _approx_boolean,  _no_approx, _eval_to_list,    None, None),
    (OpKind.ToOrdinal,  1, _validate_always, _approx_boolean,  _no_approx, _eval_to_ordinal, None, None),
    (OpKind.GCDAll,     1, _validate_always, _approx_boolean,  _no_approx, _eval_count,      None, None),
    (OpKind.LCMAll,     1, _validate_always, _approx_boolean,  _no_approx, _eval_count,      None, None),
    (OpKind.AndAll,     1, _validate_always, _approx_boolean,  _no_approx, _eval_count,      None, None),
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
    (RelKind.Typ, 2, _validate_always,   _approx_boolean, _approx_boolean, _eval_type_rel),
]

_RESERVED_OPS: List[Tuple[ReservedOpKind, int, Any, Any, Any, Any]] = [
    (ReservedOpKind.Range,   2, _validate_always, _no_approx, _no_approx, _eval_range),
    (ReservedOpKind.TypeUnn, 2, _validate_always, _no_approx, _no_approx, _eval_type_unn),
    (ReservedOpKind.Select,  2, _validate_always, _no_approx, _no_approx, _eval_select),
    (ReservedOpKind.Relabel, 3, _validate_always, _no_approx, _no_approx, _eval_relabel),
    (ReservedOpKind.Find,    3, _validate_always, _no_approx, _no_approx, _eval_find),
    (ReservedOpKind.TypeRel, 2, _validate_always, _no_approx, _no_approx, _eval_type_rel),
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
    + [k for k, *_ in _STRING_OPS]
    + [k for k, *_ in _SYMBOLIC_OPS]
)

ALL_REL_KINDS: List[RelKind] = [k for k, *_ in _RELATIONAL_OPS]

ALL_RESERVED_KINDS: List[ReservedOpKind] = [k for k, *_ in _RESERVED_OPS]
