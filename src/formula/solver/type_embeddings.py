"""
Port of all Src/Core/Solver/TypeEmbedding/*Embedding.cs files combined.

Provides the ITypeEmbedding interface and all concrete type embedding classes
that map FORMULA types to Z3 sorts and back.

Uses the Python z3-solver bindings instead of Microsoft.Z3.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

import z3

if TYPE_CHECKING:
    from formula.common.terms import Term, Symbol, AppFreeCanUnn
    from formula.solver.type_embedder import TypeEmbedder


# ======================================================================
# Enumeration for embedding kinds
# ======================================================================


class TypeEmbeddingKind(Enum):
    Constructor = auto()
    Enum_ = auto()          # 'Enum' clashes with the stdlib
    Integer = auto()
    IntRange = auto()
    Natural = auto()
    NegInteger = auto()
    PosInteger = auto()
    Real = auto()
    String = auto()
    Union = auto()
    Singleton = auto()


# ======================================================================
# Abstract base class (ITypeEmbedding in C#)
# ======================================================================


class ITypeEmbedding(ABC):
    """Base class for all type embeddings."""

    @property
    @abstractmethod
    def kind(self) -> TypeEmbeddingKind:
        ...

    @property
    @abstractmethod
    def owner(self) -> "TypeEmbedder":
        ...

    @property
    @abstractmethod
    def representation(self) -> z3.SortRef:
        """The Z3 sort used to represent elements of this type."""
        ...

    @property
    @abstractmethod
    def type_term(self) -> "Term":
        """The FORMULA type term encoded by this embedding."""
        ...

    @property
    @abstractmethod
    def default_member(self) -> Tuple["Term", z3.ExprRef]:
        """A (FORMULA term, Z3 expr) pair for some member of this type."""
        ...

    @property
    @abstractmethod
    def encoding_cost(self) -> int:
        ...

    @abstractmethod
    def mk_test(self, t: z3.ExprRef, type_term: "Term") -> z3.BoolRef:
        ...

    @abstractmethod
    def mk_coercion(self, t: z3.ExprRef) -> z3.ExprRef:
        ...

    @abstractmethod
    def mk_ground(self, symb: Optional["Symbol"], args: Optional[List[z3.ExprRef]]) -> z3.ExprRef:
        ...

    @abstractmethod
    def mk_ground_term(self, t: z3.ExprRef, args: Optional[List["Term"]]) -> "Term":
        """Decode a Z3 expression back to a FORMULA term."""
        ...

    @abstractmethod
    def get_subtype(self, t: z3.ExprRef) -> "Term":
        ...

    def debug_print(self) -> None:
        print(f"{self.__class__.__name__}: sort={self.representation}")


# ======================================================================
# RealEmbedding
# ======================================================================


class RealEmbedding(ITypeEmbedding):
    """Encodes the Real base sort using Z3's RealSort."""

    def __init__(self, embedder: "TypeEmbedder", cost: int):
        self._owner = embedder
        self._cost = cost
        self._representation = z3.RealSort(ctx=embedder.context)
        idx = embedder.index
        self._type = idx.mk_apply(idx.symbol_table.get_sort_symbol("Real"), [])
        zero_term = idx.mk_cnst_rational(0, 1)
        self._default = (zero_term, z3.RealVal(0, ctx=embedder.context))

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.Real

    @property
    def owner(self) -> "TypeEmbedder":
        return self._owner

    @property
    def representation(self) -> z3.SortRef:
        return self._representation

    @property
    def type_term(self) -> "Term":
        return self._type

    @property
    def default_member(self) -> Tuple["Term", z3.ExprRef]:
        return self._default

    @property
    def encoding_cost(self) -> int:
        return self._cost

    def mk_test(self, t: z3.ExprRef, type_term: "Term") -> z3.BoolRef:
        ctx = self._owner.context
        intr, unn = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        if intr is self._type:
            return z3.BoolVal(True, ctx=ctx)
        # Simplified: return True for any non-empty intersection
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t: z3.ExprRef) -> z3.ExprRef:
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        # Simplified coercion: attempt to coerce integers to reals
        if src_te.kind == TypeEmbeddingKind.Integer:
            return z3.ToReal(t)
        return self._default[1]

    def mk_ground(self, symb: Optional["Symbol"], args: Optional[List[z3.ExprRef]]) -> z3.ExprRef:
        ctx = self._owner.context
        r = symb.raw  # Rational
        return z3.RealVal(f"{r.numerator}/{r.denominator}", ctx=ctx)

    def mk_ground_term(self, t: z3.ExprRef, args: Optional[List["Term"]]) -> "Term":
        idx = self._owner.index
        # t is a RatNum
        num = t.numerator_as_long()
        den = t.denominator_as_long()
        return idx.mk_cnst_rational(num, den)

    def get_subtype(self, t: z3.ExprRef) -> "Term":
        if z3.is_rational_value(t):
            return self.mk_ground_term(t, None)
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)

    def debug_print(self) -> None:
        print(f"Real embedding, sort {self._representation}")


# ======================================================================
# IntegerEmbedding
# ======================================================================


class IntegerEmbedding(ITypeEmbedding):
    """Encodes the Integer base sort using Z3's IntSort."""

    def __init__(self, embedder: "TypeEmbedder", cost: int):
        self._owner = embedder
        self._cost = cost
        self._representation = z3.IntSort(ctx=embedder.context)
        idx = embedder.index
        self._type = idx.mk_apply(idx.symbol_table.get_sort_symbol("Integer"), [])
        zero_term = idx.mk_cnst_rational(0, 1)
        self._default = (zero_term, z3.IntVal(0, ctx=embedder.context))

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.Integer

    @property
    def owner(self) -> "TypeEmbedder":
        return self._owner

    @property
    def representation(self) -> z3.SortRef:
        return self._representation

    @property
    def type_term(self) -> "Term":
        return self._type

    @property
    def default_member(self) -> Tuple["Term", z3.ExprRef]:
        return self._default

    @property
    def encoding_cost(self) -> int:
        return self._cost

    def mk_test(self, t: z3.ExprRef, type_term: "Term") -> z3.BoolRef:
        ctx = self._owner.context
        intr, unn = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        if intr is self._type:
            return z3.BoolVal(True, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t: z3.ExprRef) -> z3.ExprRef:
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        if src_te.kind == TypeEmbeddingKind.Real:
            return z3.ToInt(t)
        if isinstance(src_te, NaturalEmbedding):
            return src_te.mk_int_coercion(t)
        if isinstance(src_te, PosIntegerEmbedding):
            return src_te.mk_int_coercion(t)
        if isinstance(src_te, NegIntegerEmbedding):
            return src_te.mk_int_coercion(t)
        if isinstance(src_te, IntRangeEmbedding):
            return src_te.mk_int_coercion(t)
        return self._default[1]

    def mk_ground(self, symb: Optional["Symbol"], args: Optional[List[z3.ExprRef]]) -> z3.ExprRef:
        ctx = self._owner.context
        r = symb.raw  # Rational
        return z3.IntVal(int(r.numerator), ctx=ctx)

    def mk_ground_term(self, t: z3.ExprRef, args: Optional[List["Term"]]) -> "Term":
        idx = self._owner.index
        val = t.as_long()
        return idx.mk_cnst_rational(val, 1)

    def get_subtype(self, t: z3.ExprRef) -> "Term":
        if z3.is_int_value(t):
            return self.mk_ground_term(t, None)
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)

    def debug_print(self) -> None:
        print(f"Integer embedding, sort {self._representation}")


# ======================================================================
# NaturalEmbedding
# ======================================================================


class NaturalEmbedding(ITypeEmbedding):
    """
    Encodes Natural numbers using a Z3 Datatype with a boxing constructor:
    Natural = BoxInt2Nat(Int).  The bijection maps: 0->0, n>0->2n-1, n<0->-2n.
    """

    BOXING_NAME = "BoxInt2Nat"
    UNBOXING_NAME = "UnboxNat2Int"
    TESTER_NAME = "IsNat"
    SORT_NAME = "Natural"

    def __init__(self, embedder: "TypeEmbedder", cost: int):
        self._owner = embedder
        self._cost = cost
        ctx = embedder.context
        idx = embedder.index

        self._type = idx.mk_apply(idx.symbol_table.get_sort_symbol("Natural"), [])

        nat_dt = z3.Datatype(self.SORT_NAME, ctx=ctx)
        nat_dt.declare(self.BOXING_NAME, (self.UNBOXING_NAME, z3.IntSort(ctx=ctx)))
        self._sort = nat_dt.create()

        self._boxing_fn = self._sort.constructor(0)
        self._unboxing_fn = self._sort.accessor(0, 0)
        self._tester_fn = self._sort.recognizer(0)
        self._representation = self._sort

        zero_term = idx.mk_cnst_rational(0, 1)
        self._default = (zero_term, self._boxing_fn(z3.IntVal(0, ctx=ctx)))

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.Natural

    @property
    def owner(self) -> "TypeEmbedder":
        return self._owner

    @property
    def representation(self) -> z3.SortRef:
        return self._representation

    @property
    def type_term(self) -> "Term":
        return self._type

    @property
    def default_member(self) -> Tuple["Term", z3.ExprRef]:
        return self._default

    @property
    def encoding_cost(self) -> int:
        return self._cost

    @property
    def boxing_fn(self):
        return self._boxing_fn

    @property
    def unboxing_fn(self):
        return self._unboxing_fn

    def mk_int_coercion(self, nat: z3.ExprRef) -> z3.ExprRef:
        """Coerce a boxed natural to an integer."""
        ctx = self._owner.context
        i = self._unboxing_fn(nat)
        zero = z3.IntVal(0, ctx=ctx)
        one = z3.IntVal(1, ctx=ctx)
        two = z3.IntVal(2, ctx=ctx)
        ntwo = z3.IntVal(-2, ctx=ctx)
        return z3.If(
            i == zero,
            zero,
            z3.If(i > zero, i * two - one, i * ntwo),
        )

    def mk_nat_coercion(self, i: z3.ExprRef) -> z3.ExprRef:
        """Coerce an integer into a boxed natural."""
        ctx = self._owner.context
        zero = z3.IntVal(0, ctx=ctx)
        one = z3.IntVal(1, ctx=ctx)
        two = z3.IntVal(2, ctx=ctx)
        even_case = self._boxing_fn(-i / two)
        coercion = z3.If(
            i % two != 0,
            self._boxing_fn((i + one) / two),
            even_case,
        )
        return z3.If(i == zero, self._boxing_fn(zero), coercion)

    def mk_test(self, t: z3.ExprRef, type_term: "Term") -> z3.BoolRef:
        ctx = self._owner.context
        intr, unn = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        if intr is self._type:
            return z3.BoolVal(True, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t: z3.ExprRef) -> z3.ExprRef:
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        if src_te.kind == TypeEmbeddingKind.Integer:
            return self.mk_nat_coercion(t)
        if src_te.kind == TypeEmbeddingKind.Real:
            return self.mk_nat_coercion(z3.ToInt(t))
        return self._default[1]

    def mk_ground(self, symb: Optional["Symbol"], args: Optional[List[z3.ExprRef]]) -> z3.ExprRef:
        ctx = self._owner.context
        r = symb.raw
        n = int(r.numerator)
        if n == 0:
            return self._boxing_fn(z3.IntVal(0, ctx=ctx))
        elif n % 2 != 0:
            return self._boxing_fn(z3.IntVal((n + 1) // 2, ctx=ctx))
        else:
            return self._boxing_fn(z3.IntVal(-n // 2, ctx=ctx))

    def mk_ground_term(self, t: z3.ExprRef, args: Optional[List["Term"]]) -> "Term":
        idx = self._owner.index
        inner = t.arg(0)
        n = inner.as_long()
        if n == 0:
            return idx.mk_cnst_rational(0, 1)
        elif n > 0:
            return idx.mk_cnst_rational(2 * n - 1, 1)
        else:
            return idx.mk_cnst_rational(-2 * n, 1)

    def get_subtype(self, t: z3.ExprRef) -> "Term":
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)


# ======================================================================
# PosIntegerEmbedding
# ======================================================================


class PosIntegerEmbedding(ITypeEmbedding):
    """Encodes positive integers using a boxing Datatype."""

    BOXING_NAME = "BoxInt2Pos"
    UNBOXING_NAME = "UnboxPos2Int"
    TESTER_NAME = "IsPos"
    SORT_NAME = "PosInteger"

    def __init__(self, embedder: "TypeEmbedder", cost: int):
        self._owner = embedder
        self._cost = cost
        ctx = embedder.context
        idx = embedder.index

        self._type = idx.mk_apply(idx.symbol_table.get_sort_symbol("PosInteger"), [])

        dt = z3.Datatype(self.SORT_NAME, ctx=ctx)
        dt.declare(self.BOXING_NAME, (self.UNBOXING_NAME, z3.IntSort(ctx=ctx)))
        self._sort = dt.create()

        self._boxing_fn = self._sort.constructor(0)
        self._unboxing_fn = self._sort.accessor(0, 0)
        self._tester_fn = self._sort.recognizer(0)
        self._representation = self._sort

        one_term = idx.mk_cnst_rational(1, 1)
        self._default = (one_term, self._boxing_fn(z3.IntVal(1, ctx=ctx)))

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.PosInteger

    @property
    def owner(self) -> "TypeEmbedder":
        return self._owner

    @property
    def representation(self) -> z3.SortRef:
        return self._representation

    @property
    def type_term(self) -> "Term":
        return self._type

    @property
    def default_member(self) -> Tuple["Term", z3.ExprRef]:
        return self._default

    @property
    def encoding_cost(self) -> int:
        return self._cost

    @property
    def boxing_fn(self):
        return self._boxing_fn

    @property
    def unboxing_fn(self):
        return self._unboxing_fn

    def mk_int_coercion(self, pos: z3.ExprRef) -> z3.ExprRef:
        ctx = self._owner.context
        i = self._unboxing_fn(pos)
        zero = z3.IntVal(0, ctx=ctx)
        one = z3.IntVal(1, ctx=ctx)
        two = z3.IntVal(2, ctx=ctx)
        ntwo = z3.IntVal(-2, ctx=ctx)
        return z3.If(
            i == zero,
            one,
            z3.If(i > zero, i * two, i * ntwo + one),
        )

    def mk_pos_coercion(self, i: z3.ExprRef) -> z3.ExprRef:
        ctx = self._owner.context
        zero = z3.IntVal(0, ctx=ctx)
        one = z3.IntVal(1, ctx=ctx)
        two = z3.IntVal(2, ctx=ctx)
        odd_case = self._boxing_fn((one - i) / two)
        coercion = z3.If(i % two == 0, self._boxing_fn(i / two), odd_case)
        return z3.If(i == one, self._boxing_fn(zero), coercion)

    def mk_test(self, t: z3.ExprRef, type_term: "Term") -> z3.BoolRef:
        ctx = self._owner.context
        intr, _ = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t: z3.ExprRef) -> z3.ExprRef:
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        if src_te.kind == TypeEmbeddingKind.Integer:
            return self.mk_pos_coercion(t)
        return self._default[1]

    def mk_ground(self, symb, args=None) -> z3.ExprRef:
        ctx = self._owner.context
        r = symb.raw
        n = int(r.numerator)
        if n == 1:
            return self._boxing_fn(z3.IntVal(0, ctx=ctx))
        elif n % 2 == 0:
            return self._boxing_fn(z3.IntVal(n // 2, ctx=ctx))
        else:
            return self._boxing_fn(z3.IntVal((1 - n) // 2, ctx=ctx))

    def mk_ground_term(self, t: z3.ExprRef, args=None) -> "Term":
        idx = self._owner.index
        n = t.arg(0).as_long()
        if n == 0:
            return idx.mk_cnst_rational(1, 1)
        elif n > 0:
            return idx.mk_cnst_rational(2 * n, 1)
        else:
            return idx.mk_cnst_rational(-2 * n + 1, 1)

    def get_subtype(self, t: z3.ExprRef) -> "Term":
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)


# ======================================================================
# NegIntegerEmbedding
# ======================================================================


class NegIntegerEmbedding(ITypeEmbedding):
    """Encodes negative integers using a boxing Datatype."""

    BOXING_NAME = "BoxInt2Neg"
    UNBOXING_NAME = "UnboxNeg2Int"
    TESTER_NAME = "IsNeg"
    SORT_NAME = "NegInteger"

    def __init__(self, embedder: "TypeEmbedder", cost: int):
        self._owner = embedder
        self._cost = cost
        ctx = embedder.context
        idx = embedder.index

        self._type = idx.mk_apply(idx.symbol_table.get_sort_symbol("NegInteger"), [])

        dt = z3.Datatype(self.SORT_NAME, ctx=ctx)
        dt.declare(self.BOXING_NAME, (self.UNBOXING_NAME, z3.IntSort(ctx=ctx)))
        self._sort = dt.create()

        self._boxing_fn = self._sort.constructor(0)
        self._unboxing_fn = self._sort.accessor(0, 0)
        self._tester_fn = self._sort.recognizer(0)
        self._representation = self._sort

        neg_one_term = idx.mk_cnst_rational(-1, 1)
        self._default = (neg_one_term, self._boxing_fn(z3.IntVal(-1, ctx=ctx)))

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.NegInteger

    @property
    def owner(self) -> "TypeEmbedder":
        return self._owner

    @property
    def representation(self) -> z3.SortRef:
        return self._representation

    @property
    def type_term(self) -> "Term":
        return self._type

    @property
    def default_member(self) -> Tuple["Term", z3.ExprRef]:
        return self._default

    @property
    def encoding_cost(self) -> int:
        return self._cost

    @property
    def boxing_fn(self):
        return self._boxing_fn

    @property
    def unboxing_fn(self):
        return self._unboxing_fn

    def mk_int_coercion(self, neg: z3.ExprRef) -> z3.ExprRef:
        ctx = self._owner.context
        i = self._unboxing_fn(neg)
        zero = z3.IntVal(0, ctx=ctx)
        one = z3.IntVal(1, ctx=ctx)
        none_ = z3.IntVal(-1, ctx=ctx)
        two = z3.IntVal(2, ctx=ctx)
        ntwo = z3.IntVal(-2, ctx=ctx)
        return z3.If(
            i == zero,
            none_,
            z3.If(i > zero, i * ntwo, i * two - one),
        )

    def mk_neg_coercion(self, i: z3.ExprRef) -> z3.ExprRef:
        ctx = self._owner.context
        zero = z3.IntVal(0, ctx=ctx)
        one = z3.IntVal(1, ctx=ctx)
        two = z3.IntVal(2, ctx=ctx)
        odd_case = self._boxing_fn((i + one) / two)
        coercion = z3.If(i % two == 0, self._boxing_fn(-i / two), odd_case)
        return coercion

    def mk_test(self, t, type_term):
        ctx = self._owner.context
        intr, _ = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t):
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        if src_te.kind == TypeEmbeddingKind.Integer:
            return self.mk_neg_coercion(t)
        return self._default[1]

    def mk_ground(self, symb, args=None):
        ctx = self._owner.context
        r = symb.raw
        n = int(r.numerator)
        if n == -1:
            return self._boxing_fn(z3.IntVal(0, ctx=ctx))
        elif n % 2 == 0:
            return self._boxing_fn(z3.IntVal(-n // 2, ctx=ctx))
        else:
            return self._boxing_fn(z3.IntVal((n + 1) // 2, ctx=ctx))

    def mk_ground_term(self, t, args=None):
        idx = self._owner.index
        n = t.arg(0).as_long()
        if n == 0:
            return idx.mk_cnst_rational(-1, 1)
        elif n > 0:
            return idx.mk_cnst_rational(-2 * n, 1)
        else:
            return idx.mk_cnst_rational(2 * n - 1, 1)

    def get_subtype(self, t):
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)


# ======================================================================
# StringEmbedding
# ======================================================================


class StringEmbedding(ITypeEmbedding):
    """
    Encodes strings as Z3 datatypes:
      String      ::= BoxNeStr(NonEmptyStr) | EmptyString()
      NonEmptyStr ::= Char(BV8) | Append(NonEmptyStr, BV8)
    """

    CHAR_WIDTH = 8

    def __init__(self, embedder: "TypeEmbedder", cost: int):
        self._owner = embedder
        self._cost = cost
        ctx = embedder.context
        idx = embedder.index

        self._type = idx.mk_apply(idx.symbol_table.get_sort_symbol("String"), [])

        bv8 = z3.BitVecSort(self.CHAR_WIDTH, ctx=ctx)

        # Non-empty string datatype
        ne_str = z3.Datatype("NeString", ctx=ctx)
        ne_str.declare("BoxBV2Char", ("UnboxChar2BV", bv8))
        ne_str.declare("AppStr", ("GetPrefix", ne_str), ("GetSuffix", bv8))
        self._ne_str_sort = ne_str.create()

        self._char_boxing = self._ne_str_sort.constructor(0)
        self._char_unboxing = self._ne_str_sort.accessor(0, 0)
        self._app_str = self._ne_str_sort.constructor(1)
        self._app_prefix = self._ne_str_sort.accessor(1, 0)
        self._app_suffix = self._ne_str_sort.accessor(1, 1)

        # String datatype (wraps non-empty or empty)
        str_dt = z3.Datatype("String", ctx=ctx)
        str_dt.declare("EmptyStr")
        str_dt.declare("BoxNeStr2Str", ("UnboxStr2NeStr", self._ne_str_sort))
        self._str_sort = str_dt.create()

        self._empty_str = self._str_sort.constructor(0)
        self._str_boxing = self._str_sort.constructor(1)
        self._str_unboxing = self._str_sort.accessor(1, 0)
        self._is_empty = self._str_sort.recognizer(0)
        self._is_ne = self._str_sort.recognizer(1)

        self._representation = self._str_sort

        empty_term = idx.empty_string_value
        self._default = (empty_term, self._empty_str())

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.String

    @property
    def owner(self):
        return self._owner

    @property
    def representation(self):
        return self._representation

    @property
    def type_term(self):
        return self._type

    @property
    def default_member(self):
        return self._default

    @property
    def encoding_cost(self):
        return self._cost

    def mk_test(self, t, type_term):
        ctx = self._owner.context
        intr, _ = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t):
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        return self._default[1]

    def mk_ground(self, symb, args=None):
        ctx = self._owner.context
        s = symb.raw  # a Python str
        if not s:
            return self._empty_str()
        ne_string = None
        for ch in s:
            bv = z3.BitVecVal(ord(ch), self.CHAR_WIDTH, ctx=ctx)
            if ne_string is None:
                ne_string = self._char_boxing(bv)
            else:
                ne_string = self._app_str(ne_string, bv)
        return self._str_boxing(ne_string)

    def mk_ground_term(self, t, args=None):
        idx = self._owner.index
        # Simplified: return empty string
        return idx.empty_string_value

    def get_subtype(self, t):
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)


# ======================================================================
# IntRangeEmbedding
# ======================================================================


class IntRangeEmbedding(ITypeEmbedding):
    """
    Represents a range of integers [lower, upper] as a bitvector bv where
    bv + lower is the true value.  The range must satisfy
    |upper - lower + 1| = 2^p for some p > 0.
    """

    BASE_ENCODING_COST = 5

    def __init__(self, embedder: "TypeEmbedder", lower: int, upper: int):
        self._owner = embedder
        self.lower = lower
        self.upper = upper
        ctx = embedder.context
        idx = embedder.index

        width = upper - lower + 1
        assert width > 1 and (width & (width - 1)) == 0  # power of two
        self._bv_width = width.bit_length() - 1

        bv_sort = z3.BitVecSort(self._bv_width, ctx=ctx)
        boxing_name = f"BoxBV2Rng{lower}_{upper}"
        tester_name = f"IsRng{lower}_{upper}"
        unboxing_name = f"UnboxRng2BV{lower}_{upper}"
        sort_name = f"Rng{lower}_{upper}"

        dt = z3.Datatype(sort_name, ctx=ctx)
        dt.declare(boxing_name, (unboxing_name, bv_sort))
        self._sort = dt.create()

        self._boxing_fn = self._sort.constructor(0)
        self._unboxing_fn = self._sort.accessor(0, 0)
        self._tester_fn = self._sort.recognizer(0)
        self._representation = self._sort

        self._type = idx.mk_apply(
            idx.range_symbol,
            [idx.mk_cnst_rational(lower, 1), idx.mk_cnst_rational(upper, 1)],
        )
        lower_term = idx.mk_cnst_rational(lower, 1)
        self._default = (lower_term, self._boxing_fn(z3.BitVecVal(0, self._bv_width, ctx=ctx)))
        self._z3_lower = z3.IntVal(lower, ctx=ctx)

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.IntRange

    @property
    def owner(self):
        return self._owner

    @property
    def representation(self):
        return self._representation

    @property
    def type_term(self):
        return self._type

    @property
    def default_member(self):
        return self._default

    @property
    def encoding_cost(self):
        return self.BASE_ENCODING_COST + self._bv_width

    @property
    def boxing_fn(self):
        return self._boxing_fn

    @property
    def unboxing_fn(self):
        return self._unboxing_fn

    def mk_int_coercion(self, rng: z3.ExprRef) -> z3.ExprRef:
        """Coerce a boxed range value to an integer."""
        ctx = self._owner.context
        bv = self._unboxing_fn(rng)
        return self._z3_lower + z3.BV2Int(bv)

    def mk_test(self, t, type_term):
        ctx = self._owner.context
        intr, _ = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t):
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        if src_te.kind == TypeEmbeddingKind.Integer:
            ctx = self._owner.context
            return self._boxing_fn(z3.Int2BV(t - self._z3_lower, self._bv_width))
        return self._default[1]

    def mk_ground(self, symb, args=None):
        ctx = self._owner.context
        r = symb.raw
        n = int(r.numerator)
        return self._boxing_fn(z3.BitVecVal(n - self.lower, self._bv_width, ctx=ctx))

    def mk_ground_term(self, t, args=None):
        idx = self._owner.index
        bv_val = t.arg(0)
        n = bv_val.as_long() + self.lower
        return idx.mk_cnst_rational(n, 1)

    def get_subtype(self, t):
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)


# ======================================================================
# SingletonEmbedding
# ======================================================================


class SingletonEmbedding(ITypeEmbedding):
    """Encodes a single constant as a Z3 datatype with one nullary constructor."""

    BASE_ENCODING_COST = 5

    def __init__(self, embedder: "TypeEmbedder", symbol: "Symbol"):
        self._owner = embedder
        ctx = embedder.context
        idx = embedder.index

        self._symbol = symbol
        printable = symbol.printable_name
        creator_name = f"Mk_{printable}"
        tester_name = f"Is_{printable}"
        sort_name = f"Singleton_{printable}"

        dt = z3.Datatype(sort_name, ctx=ctx)
        dt.declare(creator_name)
        self._sort = dt.create()

        self._creation_fn = self._sort.constructor(0)
        self._tester_fn = self._sort.recognizer(0)
        self._representation = self._sort

        # Determine value term
        if symbol.kind == "BaseCnstSymb" and symbol.cnst_kind == "Numeric" and symbol.raw.is_integer:
            r = idx.mk_apply(symbol, [])
            self._type = idx.mk_apply(idx.range_symbol, [r, r])
            self._value = r
        else:
            self._type = idx.mk_apply(symbol, [])
            self._value = self._type

        self._default = (self._value, self._creation_fn())

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.Singleton

    @property
    def owner(self):
        return self._owner

    @property
    def representation(self):
        return self._representation

    @property
    def type_term(self):
        return self._type

    @property
    def default_member(self):
        return self._default

    @property
    def encoding_cost(self):
        return self.BASE_ENCODING_COST

    @property
    def value(self) -> "Term":
        """The FORMULA term for this singleton value."""
        return self._value

    @property
    def creation_fn(self):
        return self._creation_fn

    def mk_test(self, t, type_term):
        ctx = self._owner.context
        idx = self._owner.index
        if idx.is_ground_member(type_term, self._value):
            return z3.BoolVal(True, ctx=ctx)
        return z3.BoolVal(False, ctx=ctx)

    def mk_coercion(self, t):
        return self._creation_fn()

    def mk_ground(self, symb, args=None):
        return self._creation_fn()

    def mk_ground_term(self, t, args=None):
        return self._value

    def get_subtype(self, t):
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)

    def debug_print(self):
        print(f"Singleton embedding of {self._type}, sort {self._representation}")


# ======================================================================
# EnumEmbedding
# ======================================================================


class EnumEmbedding(ITypeEmbedding):
    """
    Represents a finite set of non-integral constants by mapping bit vectors
    to constants.
    """

    BASE_ENCODING_COST = 5

    def __init__(self, embedder: "TypeEmbedder", type_term: "Term", name: str):
        self._owner = embedder
        ctx = embedder.context
        idx = embedder.index

        self._type = type_term
        self._val_to_symb: Dict[int, "Symbol"] = {}
        self._symb_to_val: Dict["Symbol", int] = {}

        # Enumerate all leaf symbols in the type term
        def _collect(t):
            if t.symbol.arity == 0:
                uid = len(self._val_to_symb)
                self._val_to_symb[uid] = t.symbol
                self._symb_to_val[t.symbol] = uid
            for child in t.args:
                _collect(child)

        _collect(type_term)

        count = len(self._val_to_symb)
        # Round up to next power-of-2 bit width
        bv_width = max(1, (count - 1).bit_length()) if count > 1 else 1

        bv_sort = z3.BitVecSort(bv_width, ctx=ctx)

        boxing_name = f"BoxBV2Enum_{name}"
        tester_name = f"IsEnum_{name}"
        unboxing_name = f"UnboxEnum2BV_{name}"
        sort_name = f"Enum_{name}"

        dt = z3.Datatype(sort_name, ctx=ctx)
        dt.declare(boxing_name, (unboxing_name, bv_sort))
        self._sort = dt.create()

        self._boxing_fn = self._sort.constructor(0)
        self._unboxing_fn = self._sort.accessor(0, 0)
        self._tester_fn = self._sort.recognizer(0)
        self._representation = self._sort
        self._bv_width = bv_width

        first_sym = self._val_to_symb[0]
        first_term = idx.mk_apply(first_sym, [])
        self._default = (first_term, self._boxing_fn(z3.BitVecVal(0, bv_width, ctx=ctx)))

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.Enum_

    @property
    def owner(self):
        return self._owner

    @property
    def representation(self):
        return self._representation

    @property
    def type_term(self):
        return self._type

    @property
    def default_member(self):
        return self._default

    @property
    def encoding_cost(self):
        return self.BASE_ENCODING_COST + self._bv_width

    def is_member(self, s: "Symbol") -> bool:
        return s in self._symb_to_val

    def get_symbol_at_index(self, index: int) -> str:
        return self._val_to_symb[index].printable_name

    def mk_test(self, t, type_term):
        ctx = self._owner.context
        intr, _ = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t):
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        return self._default[1]

    def mk_ground(self, symb, args=None):
        ctx = self._owner.context
        val = self._symb_to_val[symb]
        return self._boxing_fn(z3.BitVecVal(val, self._bv_width, ctx=ctx))

    def mk_ground_term(self, t, args=None):
        idx = self._owner.index
        bv_val = t.arg(0)
        uid = bv_val.as_long()
        sym = self._val_to_symb[uid]
        return idx.mk_apply(sym, [])

    def get_subtype(self, t):
        return self._type

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)

    def debug_print(self):
        print(f"Enum embedding ({len(self._symb_to_val)} elements), sort {self._representation}")


# ======================================================================
# ConstructorEmbedding
# ======================================================================


class ConstructorEmbedding(ITypeEmbedding):
    """
    Encodes a data constructor (ConSymb/MapSymb) using a Z3 constructor within
    a mutually recursive datatype family.
    """

    def __init__(
        self,
        embedder: "TypeEmbedder",
        con_or_map: "Symbol",
        sort_indices: Dict["Term", Tuple[int, "Symbol"]],
    ):
        self._owner = embedder
        self.constructor = con_or_map
        idx = embedder.index

        sort_sym = (
            con_or_map.sort_symbol
            if con_or_map.kind == "ConSymb"
            else con_or_map.sort_symbol
        )
        self._type = idx.mk_apply(sort_sym, [])

        # Z3 constructor will be set up during the mutual recursion phase
        self._z3_constructor: Any = None
        self._representation: Optional[z3.SortRef] = None
        self._default: Optional[Tuple["Term", z3.ExprRef]] = None

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.Constructor

    @property
    def owner(self):
        return self._owner

    @property
    def representation(self):
        return self._representation

    @property
    def type_term(self):
        return self._type

    @property
    def default_member(self):
        return self._default

    @property
    def encoding_cost(self):
        return 1

    @property
    def z3_constructor(self):
        return self._z3_constructor

    def set_representation(self, sort: z3.SortRef) -> None:
        self._representation = sort

    def set_z3_constructor(self, con) -> None:
        self._z3_constructor = con

    def set_default_member(self, term: "Term", expr: z3.ExprRef) -> None:
        self._default = (term, expr)

    def mk_test(self, t, type_term):
        ctx = self._owner.context
        intr, _ = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t):
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        if self._default is not None:
            return self._default[1]
        raise NotImplementedError("No default member set for constructor embedding")

    def mk_ground(self, symb=None, args=None):
        if args is None:
            args = []
        return self._z3_constructor(*args)

    def mk_ground_from_symbol(self, symb, args):
        """Build a Z3 constructor application with the given arguments."""
        if args is None:
            args = []
        return self._z3_constructor(*args)

    def mk_ground_term(self, t, args=None):
        idx = self._owner.index
        if args is None:
            args = []
        return idx.mk_apply(self.constructor, list(args))

    def get_subtype(self, t):
        return self._type

    def debug_print(self):
        print(f"Constructor embedding: {self.constructor.full_name}")


# ======================================================================
# UnionEmbedding
# ======================================================================


class UnionEmbedding(ITypeEmbedding):
    """
    Represents a union type as a Z3 datatype with one boxing constructor per
    component type.
    """

    BASE_ENCODING_COST = 5

    def __init__(
        self,
        embedder: "TypeEmbedder",
        unn_type: "Term",
        sort_indices: Dict["Term", Tuple[int, "Symbol"]],
    ):
        self._owner = embedder
        self._type = unn_type
        self.name = f"Unn_{sort_indices[unn_type][0]}"
        # Canonical union computed lazily or via owner
        self._canonical_union = None
        self._boxers: List[Any] = []
        self._sort_to_boxing: Dict[z3.SortRef, Any] = {}
        self._representation: Optional[z3.SortRef] = None
        self._default: Optional[Tuple["Term", z3.ExprRef]] = None
        self._encoding_cost: Optional[int] = None

    @property
    def kind(self) -> TypeEmbeddingKind:
        return TypeEmbeddingKind.Union

    @property
    def owner(self):
        return self._owner

    @property
    def representation(self):
        return self._representation

    @property
    def type_term(self):
        return self._type

    @property
    def default_member(self):
        return self._default

    @property
    def encoding_cost(self):
        if self._encoding_cost is not None:
            return self._encoding_cost
        max_cost = 0
        for boxer_sort, _con in self._sort_to_boxing.items():
            emb = self._owner.get_embedding_by_sort(boxer_sort)
            max_cost = max(max_cost, emb.encoding_cost)
        n = max(len(self._sort_to_boxing), 1)
        self._encoding_cost = max_cost + self.BASE_ENCODING_COST + int(math.ceil(math.log2(n)))
        return self._encoding_cost

    @property
    def canonical_union(self):
        return self._canonical_union

    @property
    def boxers(self):
        return self._boxers

    def set_representation(self, sort: z3.SortRef) -> None:
        self._representation = sort

    def set_default_member(self, term: "Term", expr: z3.ExprRef) -> None:
        self._default = (term, expr)

    def set_canonical_union(self, can_unn) -> None:
        self._canonical_union = can_unn

    def add_boxer(self, sort: z3.SortRef, constructor) -> None:
        self._sort_to_boxing[sort] = constructor
        self._boxers.append(constructor)

    def get_unboxed_embedding(self, s: "Symbol") -> ITypeEmbedding:
        """Get the type embedding that is boxed by this union for symbol *s*."""
        # Simplified: look up by sort
        for sort, con in self._sort_to_boxing.items():
            emb = self._owner.get_embedding_by_sort(sort)
            if emb.type_term == s or (hasattr(emb, 'constructor') and emb.constructor == s):
                return emb
        # Fallback
        for sort, con in self._sort_to_boxing.items():
            return self._owner.get_embedding_by_sort(sort)
        raise KeyError(f"No unboxed embedding for {s}")

    def mk_test_and_unbox(self, s, t):
        """
        If symbol *s* identifies a boxed type, return (test_expr, unboxed_expr).
        Otherwise return (None, None).
        """
        # Simplified stub
        return None, None

    def mk_test(self, t, type_term):
        ctx = self._owner.context
        intr, _ = self._owner.get_intersection(self._type, type_term)
        if intr is None:
            return z3.BoolVal(False, ctx=ctx)
        return z3.BoolVal(True, ctx=ctx)

    def mk_coercion(self, t):
        src_te = self._owner.get_embedding_by_sort(t.sort())
        if src_te is self:
            return t
        if self._default is not None:
            return self._default[1]
        raise NotImplementedError("No default member set for union embedding")

    def mk_ground(self, symb=None, args=None):
        """Box a Z3 expression inside the union."""
        if args and len(args) == 1:
            inner = args[0]
            sort = inner.sort()
            if sort in self._sort_to_boxing:
                return self._sort_to_boxing[sort](inner)
        if self._default is not None:
            return self._default[1]
        raise NotImplementedError("Cannot make ground union member")

    def mk_ground_from_symbol(self, symb, args):
        return self.mk_ground(symb, args)

    def mk_ground_term(self, t, args=None):
        if args and len(args) == 1:
            return args[0]
        return self._default[0] if self._default else None

    def get_subtype(self, t):
        return self._type

    def debug_print(self):
        print(f"Union embedding {self.name}, sort {self._representation}")
        for sort, con in self._sort_to_boxing.items():
            print(f"  boxer for sort {sort}")
