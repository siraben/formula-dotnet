"""
Port of Src/Core/Common/Symbols/SymbolTypes/*.cs and Symbol.cs, Constants.cs.

Defines the Symbol type hierarchy for FORMULA 2.0:
  Symbol (ABC)
    +-- BaseCnstSymb   (numeric/string constants)
    +-- BaseOpSymb      (built-in operators)
    +-- BaseSortSymb    (base sorts: Integer, Real, String, etc.)
    +-- UserSortSymb    (sort symbol for a user-defined constructor/map)
    +-- UserSymbol (ABC)
          +-- UserCnstSymb (user constants / variables)
          +-- ConSymb      (data constructors)
          +-- MapSymb      (map constructors)
          +-- UnnSymb      (union types)
                +-- UnnSortSymb (union type wrapping a base sort)
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from fractions import Fraction
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)


# ---------------------------------------------------------------------------
# Enums ported from Constants.cs
# ---------------------------------------------------------------------------

class Groundness(enum.Enum):
    """Whether a term is ground, a variable, or a type."""
    Ground = 0
    Variable = 1
    Type = 2


class SymbolKind(enum.Enum):
    """Discriminator for the concrete Symbol sub-classes."""
    BaseSortSymb = 0
    BaseCnstSymb = 1
    BaseOpSymb = 2
    UserCnstSymb = 3
    UserSortSymb = 4
    UnnSymb = 5
    ConSymb = 6
    MapSymb = 7


class BaseSortKind(enum.Enum):
    """The built-in numeric / string sorts."""
    NegInteger = 0
    PosInteger = 1
    Natural = 2
    Integer = 3
    Real = 4
    String = 5


class UserCnstSymbKind(enum.Enum):
    """Classifies a user constant symbol."""
    New = 0
    Derived = 1
    Variable = 2


class CnstKind(enum.Enum):
    """Classifies a base constant symbol."""
    Numeric = 0
    String = 1


class ReservedOpKind(enum.Enum):
    """Reserved (internal) operator kinds."""
    Range = 0
    TypeUnn = 1
    Select = 2
    Relabel = 3
    Find = 4
    TypeRel = 5


class OpKind(enum.Enum):
    """User-facing operator kinds."""
    Add = 0
    Sub = 1
    Mul = 2
    Div = 3
    Mod = 4
    Neg = 5
    Count = 6
    No = 7
    Max = 8
    Min = 9
    ToList = 10
    ToOrdinal = 11
    Sign = 12
    GCD = 13
    GCDAll = 14
    LCM = 15
    LCMAll = 16
    Qtnt = 17
    SymAnd = 18
    SymAndAll = 19
    SymCount = 20
    SymMax = 21
    IsSubstring = 22
    StrAfter = 23
    StrBefore = 24
    StrFind = 25
    StrGetAt = 26
    StrJoin = 27
    StrLength = 28
    StrLower = 29
    StrReplace = 30
    StrReverse = 31
    StrUpper = 32
    ToNatural = 33
    ToString = 34
    ToSymbol = 35
    RflIsMember = 36
    AndAll = 37
    Impl = 38
    NotImpl = 39


class RelKind(enum.Enum):
    """Relational operator kinds (constraints)."""
    Eq = 0
    Neq = 1
    Lt = 2
    Le = 3
    Gt = 4
    Ge = 5
    No = 6
    Typ = 7


class MapKind(enum.Enum):
    """Classifies map constructors."""
    Bij = 0
    Fun = 1
    Inj = 2
    Sur = 3


class SizeExprKind(enum.Enum):
    """Kind of a size expression."""
    Infinity = 0
    Prod = 1
    Sum = 2
    Count = 3


# ---------------------------------------------------------------------------
# SizeExpr - ported from Src/Core/Common/Symbols/SizeExpr.cs
# ---------------------------------------------------------------------------

class SizeExpr:
    """Represents a symbolic size expression for cardinality computations."""

    _infinity: Optional[SizeExpr] = None

    def __init__(
        self,
        kind: SizeExprKind = SizeExprKind.Infinity,
        raw: Any = None,
    ):
        self.kind = kind
        self.raw = raw

    @classmethod
    def make_infinity(cls) -> SizeExpr:
        if cls._infinity is None:
            cls._infinity = SizeExpr(SizeExprKind.Infinity, None)
        return cls._infinity

    @classmethod
    def make_count(cls, name: str) -> SizeExpr:
        return SizeExpr(SizeExprKind.Count, name)

    @classmethod
    def make_sum(cls, n_new_constants: int, exprs: List[SizeExpr]) -> SizeExpr:
        return SizeExpr(SizeExprKind.Sum, (n_new_constants, exprs))

    @classmethod
    def make_prod(cls, args: List[SizeExpr]) -> SizeExpr:
        return SizeExpr(SizeExprKind.Prod, args)

    def clone(self, renaming: Optional[str] = None) -> SizeExpr:
        if not renaming:
            return self
        if self.kind == SizeExprKind.Infinity:
            return self
        elif self.kind == SizeExprKind.Count:
            return SizeExpr(SizeExprKind.Count, f"{renaming}.{self.raw}")
        elif self.kind == SizeExprKind.Sum:
            n, exprs = self.raw
            return SizeExpr.make_sum(n, [e.clone(renaming) for e in exprs])
        elif self.kind == SizeExprKind.Prod:
            return SizeExpr.make_prod([a.clone(renaming) for a in self.raw])
        raise NotImplementedError

    def debug_str(self) -> str:
        if self.kind == SizeExprKind.Infinity:
            return "<INFTY>"
        elif self.kind == SizeExprKind.Count:
            return f"|{self.raw}|"
        elif self.kind == SizeExprKind.Sum:
            n, exprs = self.raw
            s = f"({n}"
            for e in exprs:
                s += f" + {e.debug_str()}"
            return s + ")"
        elif self.kind == SizeExprKind.Prod:
            return " * ".join(a.debug_str() for a in self.raw)
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"SizeExpr({self.debug_str()})"


# ---------------------------------------------------------------------------
# Symbol  (abstract base)
# ---------------------------------------------------------------------------

class Symbol(ABC):
    """
    Abstract base class for all FORMULA symbols.

    Each concrete symbol is assigned a unique integer ``id`` when it is fully
    constructed and registered with the symbol table.
    """

    def __init__(self) -> None:
        self._id: int = -1

    # -- abstract ----------------------------------------------------------
    @property
    @abstractmethod
    def kind(self) -> SymbolKind: ...

    @property
    @abstractmethod
    def arity(self) -> int: ...

    @property
    @abstractmethod
    def printable_name(self) -> str: ...

    # -- virtual boolean flags (default False) -----------------------------
    @property
    def is_variable(self) -> bool:
        return False

    @property
    def is_reserved_operation(self) -> bool:
        return False

    @property
    def is_derived_constant(self) -> bool:
        return False

    @property
    def is_new_constant(self) -> bool:
        return False

    @property
    def is_non_var_constant(self) -> bool:
        return False

    @property
    def is_type_unn(self) -> bool:
        return False

    @property
    def is_range(self) -> bool:
        return False

    @property
    def is_select(self) -> bool:
        return False

    @property
    def is_relabel(self) -> bool:
        return False

    @property
    def is_sym_count(self) -> bool:
        return False

    @property
    def is_sym_and(self) -> bool:
        return False

    @property
    def is_sym_and_all(self) -> bool:
        return False

    @property
    def is_sym_max(self) -> bool:
        return False

    # -- concrete helpers --------------------------------------------------
    @property
    def is_data_constructor(self) -> bool:
        return self.kind in (SymbolKind.ConSymb, SymbolKind.MapSymb)

    @property
    def id(self) -> int:
        assert self._id >= 0, "Symbol has not been assigned an ID yet"
        return self._id

    @id.setter
    def id(self, value: int) -> None:
        assert value >= 0
        assert self._id == -1, "Symbol ID already assigned"
        self._id = value

    @property
    def is_fully_constructed(self) -> bool:
        return self._id >= 0

    @staticmethod
    def compare(s1: Symbol, s2: Symbol) -> int:
        return s1.id - s2.id

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.printable_name}>"


# ---------------------------------------------------------------------------
# BaseCnstSymb
# ---------------------------------------------------------------------------

class BaseCnstSymb(Symbol):
    """A base constant: either a Rational number or a string literal."""

    def __init__(self, value: Any) -> None:
        super().__init__()
        if isinstance(value, (int, float, Fraction)):
            self.cnst_kind = CnstKind.Numeric
            self.raw: Any = Fraction(value) if not isinstance(value, Fraction) else value
        elif isinstance(value, str):
            self.cnst_kind = CnstKind.String
            self.raw = value
        else:
            raise TypeError(f"Unexpected base constant type: {type(value)}")

    @property
    def kind(self) -> SymbolKind:
        return SymbolKind.BaseCnstSymb

    @property
    def is_new_constant(self) -> bool:
        return True

    @property
    def is_non_var_constant(self) -> bool:
        return True

    @property
    def printable_name(self) -> str:
        if self.cnst_kind == CnstKind.Numeric:
            return str(self.raw)
        else:
            return f'"{self.raw}"'

    @property
    def arity(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# BaseOpSymb
# ---------------------------------------------------------------------------

class BaseOpSymb(Symbol):
    """
    A built-in operator symbol (arithmetic, relational, or reserved).

    Carries callables for:
    - ``validator``      : syntax validation
    - ``upward_approx``  : upward type approximation
    - ``downward_approx``: downward type approximation
    - ``evaluator``      : concrete evaluation
    - ``app_constrainer``: additional implicit constraints
    - ``sym_evaluator``  : symbolic evaluation (optional)
    """

    def __init__(
        self,
        op_kind: Any,  # OpKind | RelKind | ReservedOpKind
        arity: int,
        validator: Optional[Callable] = None,
        upward_approx: Optional[Callable] = None,
        downward_approx: Optional[Callable] = None,
        evaluator: Optional[Callable] = None,
        app_constrainer: Optional[Callable] = None,
        sym_evaluator: Optional[Callable] = None,
    ) -> None:
        super().__init__()
        self.op_kind = op_kind
        self._arity = arity
        self.validator = validator
        self.upward_approx = upward_approx
        self.downward_approx = downward_approx
        self.evaluator = evaluator
        self.app_constrainer = app_constrainer or BaseOpSymb._empty_constrainer
        self.sym_evaluator = sym_evaluator

    @property
    def kind(self) -> SymbolKind:
        return SymbolKind.BaseOpSymb

    @property
    def arity(self) -> int:
        return self._arity

    @property
    def is_select(self) -> bool:
        return isinstance(self.op_kind, ReservedOpKind) and self.op_kind == ReservedOpKind.Select

    @property
    def is_type_unn(self) -> bool:
        return isinstance(self.op_kind, ReservedOpKind) and self.op_kind == ReservedOpKind.TypeUnn

    @property
    def is_range(self) -> bool:
        return isinstance(self.op_kind, ReservedOpKind) and self.op_kind == ReservedOpKind.Range

    @property
    def is_relabel(self) -> bool:
        return isinstance(self.op_kind, ReservedOpKind) and self.op_kind == ReservedOpKind.Relabel

    @property
    def is_sym_and(self) -> bool:
        return isinstance(self.op_kind, OpKind) and self.op_kind == OpKind.SymAnd

    @property
    def is_sym_and_all(self) -> bool:
        return isinstance(self.op_kind, OpKind) and self.op_kind == OpKind.SymAndAll

    @property
    def is_sym_count(self) -> bool:
        return isinstance(self.op_kind, OpKind) and self.op_kind == OpKind.SymCount

    @property
    def is_sym_max(self) -> bool:
        return isinstance(self.op_kind, OpKind) and self.op_kind == OpKind.SymMax

    @property
    def is_reserved_operation(self) -> bool:
        return isinstance(self.op_kind, ReservedOpKind)

    @property
    def printable_name(self) -> str:
        if isinstance(self.op_kind, OpKind):
            return _OP_KIND_NAMES.get(self.op_kind, self.op_kind.name)
        elif isinstance(self.op_kind, RelKind):
            return _REL_KIND_NAMES.get(self.op_kind, self.op_kind.name)
        elif isinstance(self.op_kind, ReservedOpKind):
            return _RESERVED_OP_NAMES.get(self.op_kind, self.op_kind.name)
        return str(self.op_kind)

    @staticmethod
    def _empty_constrainer(index: Any, args: Any) -> Iterable:
        return iter(())


# Readable name tables for operators
_OP_KIND_NAMES: Dict[OpKind, str] = {
    OpKind.Add: "+",
    OpKind.Sub: "-",
    OpKind.Mul: "*",
    OpKind.Div: "/",
    OpKind.Mod: "%",
    OpKind.Neg: "-",
    OpKind.Count: "count",
    OpKind.No: "no",
    OpKind.Max: "max",
    OpKind.Min: "min",
    OpKind.ToList: "toList",
    OpKind.ToOrdinal: "toOrdinal",
    OpKind.Sign: "sign",
    OpKind.GCD: "gcd",
    OpKind.GCDAll: "gcdAll",
    OpKind.LCM: "lcm",
    OpKind.LCMAll: "lcmAll",
    OpKind.Qtnt: "qtnt",
    OpKind.SymAnd: "symAnd",
    OpKind.SymAndAll: "symAndAll",
    OpKind.SymCount: "symCount",
    OpKind.SymMax: "symMax",
    OpKind.IsSubstring: "isSubstring",
    OpKind.StrAfter: "strAfter",
    OpKind.StrBefore: "strBefore",
    OpKind.StrFind: "strFind",
    OpKind.StrGetAt: "strGetAt",
    OpKind.StrJoin: "strJoin",
    OpKind.StrLength: "strLength",
    OpKind.StrLower: "strLower",
    OpKind.StrReplace: "strReplace",
    OpKind.StrReverse: "strReverse",
    OpKind.StrUpper: "strUpper",
    OpKind.ToNatural: "toNatural",
    OpKind.ToString: "toString",
    OpKind.ToSymbol: "toSymbol",
    OpKind.RflIsMember: "rflIsMember",
    OpKind.AndAll: "andAll",
    OpKind.Impl: "impl",
    OpKind.NotImpl: "notImpl",
}

_REL_KIND_NAMES: Dict[RelKind, str] = {
    RelKind.Eq: "=",
    RelKind.Neq: "!=",
    RelKind.Lt: "<",
    RelKind.Le: "<=",
    RelKind.Gt: ">",
    RelKind.Ge: ">=",
    RelKind.No: "no",
    RelKind.Typ: ":",
}

_RESERVED_OP_NAMES: Dict[ReservedOpKind, str] = {
    ReservedOpKind.Range: "..",
    ReservedOpKind.TypeUnn: "+",
    ReservedOpKind.Select: ".",
    ReservedOpKind.Relabel: "~relabel",
    ReservedOpKind.Find: "~find",
    ReservedOpKind.TypeRel: "~type",
}


# ---------------------------------------------------------------------------
# BaseSortSymb
# ---------------------------------------------------------------------------

# Mapping from BaseSortKind to the canonical sort name
_SORT_KIND_NAMES: Dict[BaseSortKind, str] = {
    BaseSortKind.NegInteger: "NegInteger",
    BaseSortKind.PosInteger: "PosInteger",
    BaseSortKind.Natural: "Natural",
    BaseSortKind.Integer: "Integer",
    BaseSortKind.Real: "Real",
    BaseSortKind.String: "String",
}


class BaseSortSymb(Symbol):
    """A built-in sort symbol such as ``Integer``, ``Real``, ``String``."""

    def __init__(self, sort_kind: BaseSortKind) -> None:
        super().__init__()
        self.sort_kind = sort_kind

    @property
    def kind(self) -> SymbolKind:
        return SymbolKind.BaseSortSymb

    @property
    def arity(self) -> int:
        return 0

    @property
    def printable_name(self) -> str:
        return _SORT_KIND_NAMES.get(self.sort_kind, self.sort_kind.name)


# ---------------------------------------------------------------------------
# UserSymbol (abstract)
# ---------------------------------------------------------------------------

class UserSymbol(Symbol, ABC):
    """
    Abstract base for symbols defined by the user (or auto-generated by the
    compiler): constants, constructors, maps, and unions.
    """

    MANGLE_PREFIX: str = "~"

    def __init__(
        self,
        namespace: Namespace,
        name: str,
        is_autogen: bool,
    ) -> None:
        super().__init__()
        self._namespace = namespace
        self._name = name
        self._is_autogen = is_autogen
        ns_full = namespace.full_name if namespace else ""
        self._full_name = name if not ns_full else f"{ns_full}.{name}"
        self._canonical_form: Optional[List[Any]] = None  # List[AppFreeCanUnn]

    @property
    def is_mangled(self) -> bool:
        return self._name.startswith(self.MANGLE_PREFIX)

    @property
    def is_autogen(self) -> bool:
        return self._is_autogen

    @property
    def name(self) -> str:
        return self._name

    @property
    def full_name(self) -> str:
        return self._full_name

    @property
    def printable_name(self) -> str:
        return self._full_name

    @property
    def namespace(self) -> Namespace:
        return self._namespace

    @property
    def canonical_form(self) -> Optional[List[Any]]:
        return self._canonical_form

    def set_canonical_form(self, can: List[Any]) -> None:
        assert self._canonical_form is None, "Canonical form already set"
        self._canonical_form = can

    # -- abstract / virtual protocol for the compiler ----------------------
    @property
    @abstractmethod
    def definitions(self) -> List[Any]:
        """Return the list of AST definitions for this symbol."""
        ...

    def is_compatible_definition(self, other: UserSymbol) -> bool:
        raise NotImplementedError

    def merge_symbol_definition(self, other: UserSymbol) -> None:
        raise NotImplementedError

    def resolve_types(self, table: Any, flags: List[Any], cancel: Any = None) -> bool:
        raise NotImplementedError

    def canonize(self, flags: List[Any], cancel: Any = None) -> bool:
        raise NotImplementedError

    def copy_canonical_form(self, span: Any = None, renaming: Optional[str] = None) -> Any:
        raise NotImplementedError

    def clone_symbol(self, space: Namespace, span: Any = None, renaming: Optional[str] = None) -> UserSymbol:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# UserCnstSymb
# ---------------------------------------------------------------------------

class UserCnstSymb(UserSymbol):
    """
    A user-defined constant symbol.  It may be a ``New`` constant (part of a
    model), a ``Derived`` constant (defined by rules), or a ``Variable`` (a
    logic variable in rule bodies / heads).
    """

    def __init__(
        self,
        namespace: Namespace,
        name: str,
        user_cnst_kind: UserCnstSymbKind,
        is_autogen: bool = False,
        definition: Any = None,
    ) -> None:
        super().__init__(namespace, name, is_autogen)
        self.user_cnst_kind = user_cnst_kind
        self._definitions: List[Any] = []
        if definition is not None:
            self._definitions.append(definition)

    @property
    def kind(self) -> SymbolKind:
        return SymbolKind.UserCnstSymb

    @property
    def arity(self) -> int:
        return 0

    @property
    def is_new_constant(self) -> bool:
        return self.user_cnst_kind == UserCnstSymbKind.New

    @property
    def is_derived_constant(self) -> bool:
        return self.user_cnst_kind == UserCnstSymbKind.Derived

    @property
    def is_non_var_constant(self) -> bool:
        return self.user_cnst_kind != UserCnstSymbKind.Variable

    @property
    def is_variable(self) -> bool:
        return self.user_cnst_kind == UserCnstSymbKind.Variable

    @property
    def is_type_constant(self) -> bool:
        return len(self._name) > 0 and self._name[0] == "#"

    @property
    def is_symbolic_constant(self) -> bool:
        return len(self._name) > 0 and self._name[0] == "%"

    @property
    def definitions(self) -> List[Any]:
        return self._definitions

    def is_compatible_definition(self, other: UserSymbol) -> bool:
        if not isinstance(other, UserCnstSymb):
            return False
        return (
            other.user_cnst_kind == self.user_cnst_kind
            and other.is_autogen == self.is_autogen
        )

    def merge_symbol_definition(self, other: UserSymbol) -> None:
        for d in other.definitions:
            self._definitions.append(d)

    def resolve_types(self, table: Any, flags: List[Any], cancel: Any = None) -> bool:
        # For user constants the canonical form is just a singleton union of self
        from formula.common.terms import AppFreeCanUnn
        self.set_canonical_form([AppFreeCanUnn.from_user_cnst(table, self)])
        return True

    def canonize(self, flags: List[Any], cancel: Any = None) -> bool:
        return True

    def clone_symbol(self, space: Namespace, span: Any = None, renaming: Optional[str] = None) -> UserSymbol:
        return UserCnstSymb(space, self._name, self.user_cnst_kind, self.is_autogen)


# ---------------------------------------------------------------------------
# ConSymb
# ---------------------------------------------------------------------------

class ConSymb(UserSymbol):
    """
    A data constructor symbol, e.g. ``Node(label, left, right)``.

    Carries field attributes (any-flag, label) and optionally a sort symbol.
    """

    def __init__(
        self,
        namespace: Namespace,
        name: str,
        arity: int,
        is_new: bool = True,
        is_sub: bool = False,
        is_autogen: bool = False,
        definition: Any = None,
    ) -> None:
        super().__init__(namespace, name, is_autogen)
        self._arity = arity
        self._is_new = is_new
        self._is_sub = is_sub
        self._definitions: List[Any] = []
        if definition is not None:
            self._definitions.append(definition)
        self._fld_attrs: List[Tuple[bool, str]] = [(False, "")] * arity
        self._label_map: Dict[str, int] = {}
        self.sort_symbol: Optional[UserSortSymb] = None
        self._is_sub_rule_generated = is_sub

    @property
    def kind(self) -> SymbolKind:
        return SymbolKind.ConSymb

    @property
    def arity(self) -> int:
        return self._arity

    @property
    def is_new(self) -> bool:
        return self._is_new

    @property
    def is_sub(self) -> bool:
        return self._is_sub

    @property
    def is_sub_rule_generated(self) -> bool:
        return self._is_sub_rule_generated

    @property
    def definitions(self) -> List[Any]:
        return self._definitions

    def get_label_index(self, label: str) -> Optional[int]:
        """If this constructor has an argument with *label*, return its index."""
        return self._label_map.get(label)

    def is_any_arg(self, index: int) -> bool:
        """Return True if the *index*-th argument is an 'any'-kind argument."""
        assert self._is_new
        assert 0 <= index < self._arity
        return self._fld_attrs[index][0]

    def set_field_attr(self, index: int, is_any: bool, label: str) -> None:
        """Set the field attribute for a given index."""
        self._fld_attrs[index] = (is_any, label)
        if label:
            self._label_map[label] = index

    def do_not_gen_sub_rule(self) -> None:
        assert self._is_sub
        self._is_sub_rule_generated = False

    def is_compatible_definition(self, other: UserSymbol) -> bool:
        if not isinstance(other, ConSymb):
            return False
        return (
            other.is_autogen == self.is_autogen
            and other.is_new == self.is_new
            and other.is_sub == self.is_sub
            and other.arity == self.arity
        )

    def merge_symbol_definition(self, other: UserSymbol) -> None:
        for d in other.definitions:
            self._definitions.append(d)

    def resolve_types(self, table: Any, flags: List[Any], cancel: Any = None) -> bool:
        # Placeholder: type resolution requires the full compiler pipeline
        return True

    def canonize(self, flags: List[Any], cancel: Any = None) -> bool:
        return True

    def clone_symbol(self, space: Namespace, span: Any = None, renaming: Optional[str] = None) -> UserSymbol:
        clone = ConSymb(
            space,
            self._name,
            self._arity,
            self._is_new,
            self._is_sub,
            self.is_autogen,
        )
        clone._is_sub_rule_generated = self._is_sub_rule_generated
        return clone


# ---------------------------------------------------------------------------
# MapSymb
# ---------------------------------------------------------------------------

class MapSymb(UserSymbol):
    """
    A map constructor symbol, e.g. ``Edge :: (Node, Node) -> Node``.

    Carries domain / codomain field attributes and optionally a sort symbol.
    """

    def __init__(
        self,
        namespace: Namespace,
        name: str,
        dom_arity: int,
        cod_arity: int,
        map_kind: MapKind = MapKind.Fun,
        is_partial: bool = False,
        is_autogen: bool = False,
        definition: Any = None,
    ) -> None:
        super().__init__(namespace, name, is_autogen)
        self._dom_arity = dom_arity
        self._cod_arity = cod_arity
        self._arity = dom_arity + cod_arity
        self._map_kind = map_kind
        self._is_partial = is_partial
        self._definitions: List[Any] = []
        if definition is not None:
            self._definitions.append(definition)
        self._dom_attrs: List[Tuple[bool, str]] = [(False, "")] * dom_arity
        self._cod_attrs: List[Tuple[bool, str]] = [(False, "")] * cod_arity
        self._label_map: Dict[str, int] = {}
        self.sort_symbol: Optional[UserSortSymb] = None

    @property
    def kind(self) -> SymbolKind:
        return SymbolKind.MapSymb

    @property
    def arity(self) -> int:
        return self._arity

    @property
    def dom_arity(self) -> int:
        return self._dom_arity

    @property
    def cod_arity(self) -> int:
        return self._cod_arity

    @property
    def map_kind(self) -> MapKind:
        return self._map_kind

    @property
    def is_partial(self) -> bool:
        return self._is_partial

    @property
    def definitions(self) -> List[Any]:
        return self._definitions

    def get_label_index(self, label: str) -> Optional[int]:
        return self._label_map.get(label)

    def is_any_arg(self, index: int) -> bool:
        assert 0 <= index < self._arity
        if index < self._dom_arity:
            return self._dom_attrs[index][0]
        else:
            return self._cod_attrs[index - self._dom_arity][0]

    def set_dom_attr(self, index: int, is_any: bool, label: str) -> None:
        self._dom_attrs[index] = (is_any, label)
        if label:
            self._label_map[label] = index

    def set_cod_attr(self, index: int, is_any: bool, label: str) -> None:
        self._cod_attrs[index] = (is_any, label)
        if label:
            self._label_map[label] = index + self._dom_arity

    def is_compatible_definition(self, other: UserSymbol) -> bool:
        if not isinstance(other, MapSymb):
            return False
        return (
            other.is_autogen == self.is_autogen
            and other.dom_arity == self.dom_arity
            and other.cod_arity == self.cod_arity
            and other.map_kind == self.map_kind
            and other.is_partial == self.is_partial
        )

    def merge_symbol_definition(self, other: UserSymbol) -> None:
        for d in other.definitions:
            self._definitions.append(d)

    def resolve_types(self, table: Any, flags: List[Any], cancel: Any = None) -> bool:
        return True

    def canonize(self, flags: List[Any], cancel: Any = None) -> bool:
        return True

    def clone_symbol(self, space: Namespace, span: Any = None, renaming: Optional[str] = None) -> UserSymbol:
        return MapSymb(
            space,
            self._name,
            self._dom_arity,
            self._cod_arity,
            self._map_kind,
            self._is_partial,
            self.is_autogen,
        )


# ---------------------------------------------------------------------------
# UnnSymb
# ---------------------------------------------------------------------------

class UnnSymb(UserSymbol):
    """
    A user-defined union type, e.g. ``Expr ::= Var + Const + BinOp``.
    """

    def __init__(
        self,
        namespace: Namespace,
        name: str,
        is_autogen: bool = False,
        definition: Any = None,
    ) -> None:
        super().__init__(namespace, name, is_autogen)
        self._definitions: List[Any] = []
        if definition is not None:
            self._definitions.append(definition)

    @property
    def kind(self) -> SymbolKind:
        return SymbolKind.UnnSymb

    @property
    def arity(self) -> int:
        return 0

    @property
    def definitions(self) -> List[Any]:
        return self._definitions

    def is_compatible_definition(self, other: UserSymbol) -> bool:
        return (
            other.kind == self.kind
            and other.is_autogen == self.is_autogen
        )

    def merge_symbol_definition(self, other: UserSymbol) -> None:
        for d in other.definitions:
            self._definitions.append(d)

    def resolve_types(self, table: Any, flags: List[Any], cancel: Any = None) -> bool:
        return True

    def canonize(self, flags: List[Any], cancel: Any = None) -> bool:
        return True

    def clone_symbol(self, space: Namespace, span: Any = None, renaming: Optional[str] = None) -> UserSymbol:
        return UnnSymb(space, self._name, self.is_autogen)


# ---------------------------------------------------------------------------
# UnnSortSymb
# ---------------------------------------------------------------------------

class UnnSortSymb(UnnSymb):
    """
    A union type that wraps a single base sort.  Created automatically by the
    symbol table for each ``BaseSortKind``.
    """

    def __init__(
        self,
        namespace: Namespace,
        sort: BaseSortSymb,
    ) -> None:
        name = _SORT_KIND_NAMES.get(sort.sort_kind, sort.sort_kind.name)
        super().__init__(namespace, name, is_autogen=True)
        self.sort = sort

    @property
    def printable_name(self) -> str:
        return self.sort.printable_name

    def is_compatible_definition(self, other: UserSymbol) -> bool:
        return isinstance(other, UnnSortSymb) and other.sort is self.sort

    def merge_symbol_definition(self, other: UserSymbol) -> None:
        pass

    def resolve_types(self, table: Any, flags: List[Any], cancel: Any = None) -> bool:
        from formula.common.terms import AppFreeCanUnn
        self.set_canonical_form([AppFreeCanUnn.from_base_sort(table, self.sort)])
        return True

    def canonize(self, flags: List[Any], cancel: Any = None) -> bool:
        return True


# ---------------------------------------------------------------------------
# UserSortSymb
# ---------------------------------------------------------------------------

class UserSortSymb(Symbol):
    """
    A sort symbol that wraps a user-defined data constructor or map symbol.
    Every ``ConSymb`` and ``MapSymb`` gets a companion ``UserSortSymb``.
    """

    def __init__(self, data_symbol: UserSymbol) -> None:
        super().__init__()
        assert data_symbol is not None
        self.data_symbol = data_symbol
        self._size: Optional[SizeExpr] = None

    @property
    def kind(self) -> SymbolKind:
        return SymbolKind.UserSortSymb

    @property
    def arity(self) -> int:
        return 0

    @property
    def printable_name(self) -> str:
        return self.data_symbol.printable_name

    @property
    def size(self) -> Optional[SizeExpr]:
        return self._size

    @size.setter
    def size(self, value: SizeExpr) -> None:
        assert self._size is None, "Size already set"
        self._size = value


# ---------------------------------------------------------------------------
# Namespace
# ---------------------------------------------------------------------------

class Namespace:
    """
    A hierarchical namespace that contains user-defined symbols and child
    namespaces.  The root namespace has ``name == ""`` and ``parent is None``.
    """

    _EMPTY_SUFFIX: List[str] = []

    def __init__(
        self,
        symbol_table: Optional[Any] = None,
        name: str = "",
        parent: Optional[Namespace] = None,
    ) -> None:
        self._symbol_table = symbol_table
        self._name = name
        self._parent = parent
        self._depth = 0 if parent is None else parent.depth + 1
        self._symbols: Dict[str, UserSymbol] = {}
        self._children: Dict[str, Namespace] = {}
        self._next_anon_symbolic_constant = 0

        if parent is None or not parent.full_name:
            self._full_name = name
        else:
            self._full_name = f"{parent.full_name}.{name}"

    # -- properties --------------------------------------------------------
    @property
    def symbol_table(self) -> Any:
        return self._symbol_table

    @property
    def parent(self) -> Optional[Namespace]:
        return self._parent

    @property
    def children(self) -> Dict[str, Namespace]:
        return self._children

    @property
    def symbols(self) -> Dict[str, UserSymbol]:
        return self._symbols

    @property
    def name(self) -> str:
        return self._name

    @property
    def full_name(self) -> str:
        return self._full_name

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def descendant_symbols(self) -> Iterable[UserSymbol]:
        """BFS enumeration of all symbols in this namespace and its children."""
        from collections import deque
        queue: deque[Namespace] = deque()
        queue.append(self)
        while queue:
            ns = queue.popleft()
            yield from ns._symbols.values()
            for child in ns._children.values():
                queue.append(child)

    # -- lookup ------------------------------------------------------------
    def try_get_symbol(self, name: str) -> Optional[UserSymbol]:
        return self._symbols.get(name)

    def try_get_child(self, name: str) -> Optional[Namespace]:
        return self._children.get(name)

    def exists_symbol(self, name: str) -> bool:
        if name in self._symbols:
            return True
        return any(child.exists_symbol(name) for child in self._children.values())

    # -- mutators ----------------------------------------------------------
    def try_add_namespace(self, name: str, flags: Optional[List[Any]] = None) -> Optional[Namespace]:
        """Get or create a child namespace with the given *name*."""
        if name in self._children:
            return self._children[name]
        child = Namespace(self._symbol_table, name, self)
        self._children[name] = child
        return child

    def try_add_symbol(
        self,
        symbol: UserSymbol,
        id_getter: Callable[[], int],
        flags: Optional[List[Any]] = None,
        size_expr: Optional[SizeExpr] = None,
    ) -> bool:
        """
        Add *symbol* to this namespace.  If a compatible symbol already
        exists the definitions are merged.  Returns True on success.
        """
        if flags is None:
            flags = []
        existing = self._symbols.get(symbol.name)
        if existing is None:
            symbol.id = id_getter()
            self._symbols[symbol.name] = symbol
            # Auto-create sort symbols for constructors and maps
            if symbol.kind == SymbolKind.ConSymb:
                cs: ConSymb = symbol  # type: ignore[assignment]
                usr_sort = UserSortSymb(symbol)
                usr_sort.id = id_getter()
                cs.sort_symbol = usr_sort
                if size_expr is not None:
                    usr_sort.size = size_expr
            elif symbol.kind == SymbolKind.MapSymb:
                ms: MapSymb = symbol  # type: ignore[assignment]
                usr_sort = UserSortSymb(symbol)
                usr_sort.id = id_getter()
                ms.sort_symbol = usr_sort
                if size_expr is not None:
                    usr_sort.size = size_expr
            return True

        if not existing.is_compatible_definition(symbol):
            flags.append(
                f"Error: Duplicate incompatible definition of symbol '{symbol.name}'"
            )
            return False

        existing.merge_symbol_definition(symbol)
        return True

    def add_model_constant(self, name: str, sid: int) -> None:
        """Register a model variable with a symbolic constant name ``%name``."""
        smb_name = f"%{name}"
        assert smb_name not in self._symbols
        sym = UserCnstSymb(self, smb_name, UserCnstSymbKind.New, is_autogen=True)
        sym.id = sid
        self._symbols[smb_name] = sym

    def add_fresh_symbolic_constant(self, name: str) -> Tuple[UserCnstSymb, str]:
        """Create and register a fresh symbolic constant ``%name``."""
        smb_name = f"%{name}"
        assert smb_name not in self._symbols
        sym = UserCnstSymb(self, smb_name, UserCnstSymbKind.New, is_autogen=True)
        sym.id = len(self._symbols)
        self._symbols[smb_name] = sym
        return sym, smb_name

    def add_anon_model_constant(self, sid: int) -> UserCnstSymb:
        """Create an anonymous symbolic constant for ``_`` in a partial model."""
        smb_name = f"%~sym{self._next_anon_symbolic_constant}"
        self._next_anon_symbolic_constant += 1
        assert smb_name not in self._symbols
        sym = UserCnstSymb(self, smb_name, UserCnstSymbKind.New, is_autogen=True)
        sym.id = sid
        self._symbols[smb_name] = sym
        return sym

    # -- namespace splitting -----------------------------------------------
    def try_get_prefix(self, other: Namespace) -> Optional[Namespace]:
        """Return the deepest common ancestor of *self* and *other*, or None."""
        if other is self:
            return self
        if other.depth < self.depth:
            return other.try_get_prefix(self)
        spaces: set = set()
        crnt: Optional[Namespace] = self
        while crnt is not None:
            spaces.add(id(crnt))
            crnt = crnt.parent
        crnt = other
        while crnt is not None:
            if id(crnt) in spaces:
                return crnt
            crnt = crnt.parent
        return None

    def split_suffix(self, prefix: Optional[Namespace]) -> Optional[List[str]]:
        """
        If self is ``prefix.lbl1. ... . lbln``, return ``[lbl1, ..., lbln]``.
        If prefix is self, return ``[]``.
        If prefix is None, return the full path.
        """
        if prefix is self:
            return []
        if prefix is None:
            suffix: List[str] = [""] * (self.depth + 1)
            crnt: Optional[Namespace] = self
            i = self.depth
            while crnt is not None:
                suffix[i] = crnt.name
                i -= 1
                crnt = crnt.parent
            return suffix
        if prefix is not None and prefix.depth >= self.depth:
            return None
        suffix = [""] * (self.depth - prefix.depth)
        crnt = self
        for i in range(len(suffix) - 1, -1, -1):
            if crnt is None:
                return None
            suffix[i] = crnt.name
            crnt = crnt.parent
        return suffix if crnt is prefix else None

    @staticmethod
    def compare(n1: Namespace, n2: Namespace) -> int:
        f1 = n1.full_name
        f2 = n2.full_name
        return (f1 > f2) - (f1 < f2)

    def __repr__(self) -> str:
        return f"<Namespace '{self._full_name}'>"
