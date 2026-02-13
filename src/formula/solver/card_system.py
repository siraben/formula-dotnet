"""
Port of Src/Core/Solver/CardSystem.cs, Cardinality.cs, and CardRange.cs

Provides the ``Cardinality``, ``CardRange``, and ``CardSystem`` classes that
give lower/upper bounds on the l.f.p. of a partial model subject to
cardinality constraints.
"""
from __future__ import annotations

import math
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)

if TYPE_CHECKING:
    from formula.common.terms import Symbol, Term, UserSymbol


# ======================================================================
# Cardinality
# ======================================================================


class Cardinality:
    """
    Represents the cardinality of a set.  A cardinality can be a finite
    non-negative integer or the value *infinity*.  All infinite sets are
    treated as the same size.
    """

    _INFINITY_SENTINEL = -1

    def __init__(self, value: int = 0):
        """
        Parameters
        ----------
        value : int
            A non-negative integer, or -1 to represent infinity.
        """
        if value < 0 and value != self._INFINITY_SENTINEL:
            raise ValueError("Cardinality must be >= 0 or Infinity")
        self._value = value

    # -- Class-level constants (created after the class body) --

    @classmethod
    def infinity(cls) -> "Cardinality":
        return _INFINITY

    @classmethod
    def zero(cls) -> "Cardinality":
        return _ZERO

    @classmethod
    def one(cls) -> "Cardinality":
        return _ONE

    # -- Properties --

    @property
    def is_infinity(self) -> bool:
        return self._value == self._INFINITY_SENTINEL

    @property
    def value(self) -> int:
        if self.is_infinity:
            raise ValueError("Cannot get finite value of infinity")
        return self._value

    # -- Comparisons --

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return not self.is_infinity and self._value == other
        if not isinstance(other, Cardinality):
            return NotImplemented
        return self._value == other._value

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: "Cardinality | int") -> bool:
        if isinstance(other, int):
            return not self.is_infinity and self._value < other
        if self.is_infinity:
            return False
        if other.is_infinity:
            return True
        return self._value < other._value

    def __le__(self, other: "Cardinality | int") -> bool:
        if isinstance(other, int):
            return not self.is_infinity and self._value <= other
        if self.is_infinity:
            return other.is_infinity
        if other.is_infinity:
            return True
        return self._value <= other._value

    def __gt__(self, other: "Cardinality | int") -> bool:
        if isinstance(other, int):
            return self.is_infinity or self._value > other
        if other.is_infinity:
            return False
        if self.is_infinity:
            return True
        return self._value > other._value

    def __ge__(self, other: "Cardinality | int") -> bool:
        if isinstance(other, int):
            return self.is_infinity or self._value >= other
        if other.is_infinity:
            return self.is_infinity
        if self.is_infinity:
            return True
        return self._value >= other._value

    # -- Arithmetic --

    def __add__(self, other: "Cardinality | int") -> "Cardinality":
        if isinstance(other, int):
            return Cardinality(self._value + other) if not self.is_infinity else _INFINITY
        if self.is_infinity or other.is_infinity:
            return _INFINITY
        return Cardinality(self._value + other._value)

    def __radd__(self, other: int) -> "Cardinality":
        return self.__add__(other)

    def __sub__(self, other: "Cardinality | int") -> "Cardinality":
        if self.is_infinity:
            return _INFINITY
        if isinstance(other, int):
            return Cardinality(self._value - other)
        return Cardinality(self._value - other._value)

    def __mul__(self, other: "Cardinality | int") -> "Cardinality":
        if isinstance(other, int):
            if self._value == 0 or other == 0:
                return _ZERO
            return _INFINITY if self.is_infinity else Cardinality(self._value * other)
        if self._value == 0 or other._value == 0:
            return _ZERO
        if self.is_infinity or other.is_infinity:
            return _INFINITY
        return Cardinality(self._value * other._value)

    def __rmul__(self, other: int) -> "Cardinality":
        return self.__mul__(other)

    def __floordiv__(self, other: "Cardinality | int") -> "Cardinality":
        if isinstance(other, int):
            return Cardinality(self._value // other)
        return Cardinality(self._value // other._value)

    def __truediv__(self, other: "Cardinality | int") -> "Cardinality":
        return self.__floordiv__(other)

    # -- Min / Max --

    @staticmethod
    def min(v1: "Cardinality", v2: "Cardinality") -> "Cardinality":
        return v1 if v1 <= v2 else v2

    @staticmethod
    def max(v1: "Cardinality", v2: "Cardinality") -> "Cardinality":
        return v1 if v1 >= v2 else v2

    # -- Conversion --

    def __int__(self) -> int:
        if self.is_infinity:
            raise ValueError("Cannot convert infinity to int")
        return self._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return "INFTY" if self.is_infinity else str(self._value)

    __str__ = __repr__


# Module-level constants
_INFINITY = Cardinality.__new__(Cardinality)
_INFINITY._value = Cardinality._INFINITY_SENTINEL

_ZERO = Cardinality.__new__(Cardinality)
_ZERO._value = 0

_ONE = Cardinality.__new__(Cardinality)
_ONE._value = 1


# ======================================================================
# CardRange
# ======================================================================


class CardRange:
    """A closed interval ``[lower, upper]`` of cardinalities."""

    def __init__(self, lower: Cardinality, upper: Cardinality):
        self.lower = lower
        self.upper = upper

    # -- Class-level constants --

    @classmethod
    def all(cls) -> "CardRange":
        return CardRange(Cardinality.zero(), Cardinality.infinity())

    @classmethod
    def none(cls) -> "CardRange":
        return CardRange(Cardinality.zero(), Cardinality.zero())

    # -- Operations --

    def try_intersect(self, r: "CardRange") -> Optional["CardRange"]:
        lo = Cardinality.max(self.lower, r.lower)
        hi = Cardinality.min(self.upper, r.upper)
        if hi < lo:
            return None
        return CardRange(lo, hi)

    def bisect(self, shift_lower: bool) -> "CardRange":
        mid = (self.lower + self.upper) / 2
        if shift_lower:
            return CardRange(mid, self.upper)
        return CardRange(self.lower, mid)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CardRange):
            return NotImplemented
        return self.lower == other.lower and self.upper == other.upper

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __mul__(self, other: "CardRange") -> "CardRange":
        return CardRange(self.lower * other.lower, self.upper * other.upper)

    def __add__(self, other: "CardRange") -> "CardRange":
        return CardRange(self.lower + other.lower, self.upper + other.upper)

    def __hash__(self) -> int:
        return hash((self.lower, self.upper))

    def __repr__(self) -> str:
        return f"[{self.lower}, {self.upper}]"


# ======================================================================
# CardExpr hierarchy
# ======================================================================


class CardExpr:
    """Base class for cardinality expressions."""

    class ExprKind:
        CNST = "Cnst"
        VAR = "Var"
        UNN = "Unn"
        PROD = "Prod"

    @property
    def kind(self) -> str:
        raise NotImplementedError

    @property
    def arity(self) -> int:
        return 0

    def __getitem__(self, index: int) -> "CardExpr":
        raise IndexError

    @property
    def is_infinity(self) -> bool:
        return False

    @property
    def is_one(self) -> bool:
        return False

    @property
    def is_zero(self) -> bool:
        return False

    def __add__(self, other: Optional["CardExpr"]) -> "CardExpr":
        if other is None:
            return self
        if self.is_zero:
            return other
        if other.is_zero:
            return self
        if self.is_infinity or other.is_infinity:
            return CardCnst(Cardinality.infinity())
        if self.kind == CardExpr.ExprKind.CNST and other.kind == CardExpr.ExprKind.CNST:
            return CardCnst(self.value + other.value)
        return CardDisjUnion(self, other)

    def __radd__(self, other):
        if other is None:
            return self
        return self.__add__(other)

    def __mul__(self, other: Optional["CardExpr"]) -> "CardExpr":
        if other is None:
            return self
        if self.is_one:
            return other
        if other.is_one:
            return self
        if self.is_zero or other.is_zero:
            return CardCnst(Cardinality.zero())
        if self.kind == CardExpr.ExprKind.CNST and other.kind == CardExpr.ExprKind.CNST:
            return CardCnst(self.value * other.value)
        return CardCartProd(self, other)

    def __rmul__(self, other):
        if other is None:
            return self
        return self.__mul__(other)


class CardCnst(CardExpr):
    """A constant cardinality expression."""

    def __init__(self, value: Cardinality):
        self.value = value
        self.value_as_range = CardRange(value, value)

    @property
    def kind(self) -> str:
        return CardExpr.ExprKind.CNST

    @property
    def is_infinity(self) -> bool:
        return self.value == Cardinality.infinity()

    @property
    def is_one(self) -> bool:
        return self.value == Cardinality.one()

    @property
    def is_zero(self) -> bool:
        return self.value == Cardinality.zero()

    def __repr__(self) -> str:
        return str(self.value)


class CardVar(CardExpr):
    """A cardinality variable bound to a UserSymbol."""

    def __init__(self, symbol: "UserSymbol", is_lfp_card: bool):
        self.symbol: "UserSymbol" = symbol
        self.is_lfp_card: bool = is_lfp_card
        self.range: CardRange = CardRange.all()

    @property
    def kind(self) -> str:
        return CardExpr.ExprKind.VAR

    @staticmethod
    def compare(v1: "CardVar", v2: "CardVar") -> int:
        if v1 is v2:
            return 0
        cmp = id(v1.symbol) - id(v2.symbol)
        if cmp != 0:
            return -1 if cmp < 0 else 1
        if v1.is_lfp_card == v2.is_lfp_card:
            return 0
        return -1 if not v1.is_lfp_card else 1

    def __repr__(self) -> str:
        if self.is_lfp_card:
            return f"|lfp({self.symbol.full_name})|"
        return f"|{self.symbol.full_name}|"

    def __hash__(self) -> int:
        return hash((id(self.symbol), self.is_lfp_card))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CardVar):
            return NotImplemented
        return self.symbol is other.symbol and self.is_lfp_card == other.is_lfp_card


class CardDisjUnion(CardExpr):
    """Disjoint union of two cardinality expressions (addition)."""

    def __init__(self, expr1: CardExpr, expr2: CardExpr):
        self.expr1 = expr1
        self.expr2 = expr2

    @property
    def kind(self) -> str:
        return CardExpr.ExprKind.UNN

    @property
    def arity(self) -> int:
        return 2

    def __getitem__(self, index: int) -> CardExpr:
        if index == 0:
            return self.expr1
        if index == 1:
            return self.expr2
        raise IndexError

    def __repr__(self) -> str:
        return f"{self.expr1} + {self.expr2}"


class CardCartProd(CardExpr):
    """Cartesian product of two cardinality expressions (multiplication)."""

    def __init__(self, expr1: CardExpr, expr2: CardExpr):
        self.expr1 = expr1
        self.expr2 = expr2

    @property
    def kind(self) -> str:
        return CardExpr.ExprKind.PROD

    @property
    def arity(self) -> int:
        return 2

    def __getitem__(self, index: int) -> CardExpr:
        if index == 0:
            return self.expr1
        if index == 1:
            return self.expr2
        raise IndexError

    def __repr__(self) -> str:
        e1 = f"({self.expr1})" if self.expr1.kind == CardExpr.ExprKind.UNN else str(self.expr1)
        e2 = f"({self.expr2})" if self.expr2.kind == CardExpr.ExprKind.UNN else str(self.expr2)
        return f"{e1} * {e2}"


# ======================================================================
# CardConstraint
# ======================================================================


class CardConstraint:
    """A constraint of the form ``lhs <= rhs`` or ``lhs >= rhs``."""

    class OpKind:
        LEQ = "LEq"
        GEQ = "GEq"

    def __init__(self, op: str, lhs: CardVar, rhs: CardExpr):
        self.op = op
        self.lhs = lhs
        self.rhs = rhs
        self.is_queued = False
        self.rhs_vars: Set[CardVar] = set()
        self._collect_rhs_vars(rhs)

    def _collect_rhs_vars(self, expr: CardExpr) -> None:
        if expr.kind == CardExpr.ExprKind.VAR:
            self.rhs_vars.add(expr)
        else:
            for i in range(expr.arity):
                self._collect_rhs_vars(expr[i])

    def __repr__(self) -> str:
        op_str = "<=" if self.op == self.OpKind.LEQ else ">="
        return f"{self.lhs} {op_str} {self.rhs}"


# ======================================================================
# CardSystem
# ======================================================================


class CardSystem:
    """
    Gives lower/upper-bounds on the l.f.p. of a partial model subject to
    additional cardinality constraints.

    NOT THREAD-SAFE -- private to an instantiated search strategy.
    """

    def __init__(self, facts: Any = None):
        self._var_map: Dict["UserSymbol", Tuple[Any, CardVar, CardVar]] = {}
        self._forced_dofs: Dict["UserSymbol", int] = {}
        self._use_lists: Dict[CardVar, List[CardConstraint]] = {}
        self._solver_state: List[Dict[CardVar, CardRange]] = []
        self._constraints: List[CardConstraint] = []
        self.is_unsat: bool = False
        self.facts = facts

        if facts is not None:
            self._build_type_system_constraints()
            self._build_partial_model_lower_bounds()
            self._solver_state.append({})
            for v in self._use_lists:
                if not self._propagate(v):
                    self.is_unsat = True
                    break

    # -- Public properties --

    @property
    def solver_state(self) -> List[Dict[CardVar, CardRange]]:
        return self._solver_state

    @property
    def forced_dofs(self) -> Dict["UserSymbol", int]:
        return self._forced_dofs

    @property
    def constraints(self) -> List[CardConstraint]:
        return self._constraints

    # -- Range management --

    def _get_range(self, cvar: CardVar) -> CardRange:
        for valuations in reversed(self._solver_state):
            if cvar in valuations:
                return valuations[cvar]
        return CardRange.all()

    def _update_range(self, cvar: CardVar, new_range: CardRange) -> None:
        if self._solver_state:
            self._solver_state[-1][cvar] = new_range

    # -- Constraint management --

    def _add_constraint(self, con: CardConstraint) -> None:
        self._constraints.append(con)
        self._get_use_list(con.lhs).append(con)
        for v in con.rhs_vars:
            self._get_use_list(v).append(con)

    def _get_use_list(self, cvar: CardVar) -> List[CardConstraint]:
        if cvar not in self._use_lists:
            self._use_lists[cvar] = []
        return self._use_lists[cvar]

    # -- Evaluation --

    def _eval_range(self, expr: CardExpr) -> CardRange:
        if expr.kind == CardExpr.ExprKind.CNST:
            return expr.value_as_range
        if expr.kind == CardExpr.ExprKind.VAR:
            return self._get_range(expr)
        if expr.kind == CardExpr.ExprKind.PROD:
            return self._eval_range(expr[0]) * self._eval_range(expr[1])
        if expr.kind == CardExpr.ExprKind.UNN:
            return self._eval_range(expr[0]) + self._eval_range(expr[1])
        raise NotImplementedError

    def _eval_point(
        self,
        expr: CardExpr,
        cvar: CardVar,
        val: Cardinality,
        eval_on_lower: bool,
    ) -> Cardinality:
        if expr.kind == CardExpr.ExprKind.CNST:
            return expr.value
        if expr.kind == CardExpr.ExprKind.VAR:
            if expr is cvar:
                return val
            rng = self._get_range(expr)
            return rng.lower if eval_on_lower else rng.upper
        if expr.kind == CardExpr.ExprKind.PROD:
            return self._eval_point(expr[0], cvar, val, eval_on_lower) * self._eval_point(
                expr[1], cvar, val, eval_on_lower
            )
        if expr.kind == CardExpr.ExprKind.UNN:
            return self._eval_point(expr[0], cvar, val, eval_on_lower) + self._eval_point(
                expr[1], cvar, val, eval_on_lower
            )
        raise NotImplementedError

    # -- Propagation --

    def _propagate(self, cvar: CardVar) -> bool:
        stack: List[CardConstraint] = []
        self._enqueue_constraints(cvar, stack)
        while stack:
            con = stack.pop()
            con.is_queued = False
            lhs = self._get_range(con.lhs)
            rhs = self._eval_range(con.rhs)

            if con.op == CardConstraint.OpKind.LEQ:
                cd = Cardinality.min(lhs.upper, rhs.upper)
                if cd != lhs.upper:
                    if cd < lhs.lower:
                        return False
                    self._update_range(con.lhs, CardRange(lhs.lower, cd))
                    self._enqueue_constraints(con.lhs, stack)
            elif con.op == CardConstraint.OpKind.GEQ:
                cd = Cardinality.max(lhs.lower, rhs.lower)
                if cd != lhs.lower:
                    if cd > lhs.upper:
                        return False
                    self._update_range(con.lhs, CardRange(cd, lhs.upper))
                    self._enqueue_constraints(con.lhs, stack)

        return True

    def _enqueue_constraints(self, cvar: CardVar, stack: List[CardConstraint]) -> None:
        for c in self._use_lists.get(cvar, []):
            if not c.is_queued:
                c.is_queued = True
                stack.append(c)

    # -- Building constraints --

    def _build_type_system_constraints(self) -> None:
        """Build cardinality constraints from the type system."""
        # Simplified: in a full port this would walk the symbol table,
        # build dependency SCCs, and create CardVar/CardConstraint entries.
        pass

    def _build_partial_model_lower_bounds(self) -> None:
        """Compute lower bounds from the partial model facts."""
        # Simplified: in a full port this would bin facts by symbol and
        # compute minimal elements to derive lower bounds.
        pass

    # -- Debug --

    def debug_print_solver_state(self) -> None:
        for v in self._use_lists:
            rng = self._get_range(v)
            print(f"{v} : {rng}")

    def debug_print_constraints(self) -> None:
        for c in self._constraints:
            print(c)
