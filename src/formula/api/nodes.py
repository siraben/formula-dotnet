"""
AST node types for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.Nodes (Src/Core/API/Nodes/*.cs).

Every concrete node class mirrors a C# sealed class from the original
FORMULA codebase.  The abstract ``Node`` base class provides the common
interface (``node_kind``, ``span``, ``children``, ``deep_clone``).
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Iterator, List, Optional, Sequence, Union as TypingUnion
from urllib.parse import urlparse

from formula.api.constants import (
    CnstKind,
    ComposeKind,
    ContractKind,
    MapKind,
    NodeKind,
    OpKind,
    RelKind,
)


# ---------------------------------------------------------------------------
# ProgramName
# ---------------------------------------------------------------------------

class ProgramName:
    """Identifies a FORMULA program by name and URI.

    Ported from Microsoft.Formula.API.ProgramName.

    Constructors:
      - ProgramName()           -> api error name (unknown caller)
      - ProgramName("path")     -> file-based program name
      - ProgramName("u", pn)    -> resolved relative to another ProgramName
    """

    _API_ERROR_URI = "api://unknowncaller.4ml"

    def __init__(
        self,
        uri_string: Optional[str] = None,
        relative_to: Optional["ProgramName"] = None,
    ):
        import os
        if uri_string is None:
            # No-arg: API error name
            self._uri = self._API_ERROR_URI
            self._abs_path: Optional[str] = None
        elif uri_string.startswith("env://") or uri_string.startswith("file://"):
            self._uri = uri_string
            if uri_string.startswith("file://"):
                self._abs_path = uri_string[len("file://"):]
            else:
                self._abs_path = None
        else:
            # Treat as a file path
            abs_path = os.path.abspath(uri_string)
            self._uri = "file://" + abs_path
            self._abs_path = abs_path

    @property
    def uri(self) -> str:
        return self._uri

    @property
    def abs_path(self) -> Optional[str]:
        """Returns the absolute filesystem path if this is a file-based program name."""
        return self._abs_path

    @property
    def is_file_program_name(self) -> bool:
        return self._uri.startswith("file://")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProgramName):
            return NotImplemented
        return self._uri.lower() == other._uri.lower()

    def __hash__(self) -> int:
        return hash(self._uri.lower())

    def __repr__(self) -> str:
        return f"ProgramName({self._uri!r})"

    def __str__(self) -> str:
        if self._abs_path:
            return self._abs_path
        return self._uri


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------

@dataclass
class Span:
    """Source location span.

    Ported from Microsoft.Formula.API.Span (Src/Core/API/Base/Span.cs).
    All fields default to 0; ``program`` defaults to ``None``.
    """

    start_line: int = 0
    start_col: int = 0
    end_line: int = 0
    end_col: int = 0
    program: Optional[ProgramName] = None

    @staticmethod
    def compare(s: "Span", t: "Span") -> int:
        """Three-way comparison matching the C# Span.Compare semantics."""
        if s.program != t.program:
            sp = str(s.program) if s.program else ""
            tp = str(t.program) if t.program else ""
            if sp < tp:
                return -1
            if sp > tp:
                return 1
        for a, b in [
            (s.start_line, t.start_line),
            (s.start_col, t.start_col),
            (s.end_line, t.end_line),
            (s.end_col, t.end_col),
        ]:
            if a != b:
                return -1 if a < b else 1
        return 0


# ---------------------------------------------------------------------------
# Abstract base node
# ---------------------------------------------------------------------------

class Node(ABC):
    """Abstract base class for all FORMULA AST nodes.

    Ported from Microsoft.Formula.API.Nodes.Node.
    """

    def __init__(self, span: Optional[Span] = None):
        self._span = span if span is not None else Span()
        self.compiler_data: Any = None

    # -- abstract interface --------------------------------------------------

    @property
    @abstractmethod
    def node_kind(self) -> NodeKind:
        ...

    @property
    @abstractmethod
    def children(self) -> Iterator["Node"]:
        ...

    @abstractmethod
    def deep_clone(self) -> "Node":
        ...

    # -- concrete helpers ----------------------------------------------------

    @property
    def span(self) -> Span:
        return self._span

    @span.setter
    def span(self, value: Span) -> None:
        self._span = value

    @property
    def child_count(self) -> int:
        return sum(1 for _ in self.children)

    # convenience predicates (mirrors C# properties)

    @property
    def is_atom(self) -> bool:
        return self.node_kind in (NodeKind.Id, NodeKind.Cnst)

    @property
    def is_func_or_atom(self) -> bool:
        return self.node_kind in (
            NodeKind.Id,
            NodeKind.Cnst,
            NodeKind.FuncTerm,
            NodeKind.Compr,
            NodeKind.Quote,
        )

    @property
    def is_quote_item(self) -> bool:
        return self.is_func_or_atom or self.node_kind == NodeKind.QuoteRun

    @property
    def is_contract_spec(self) -> bool:
        return self.node_kind in (NodeKind.Body, NodeKind.CardPair)

    @property
    def is_param_type(self) -> bool:
        return self.is_type_term or self.node_kind == NodeKind.ModRef

    @property
    def is_type_term(self) -> bool:
        return self.node_kind == NodeKind.Union or self.is_union_component

    @property
    def is_union_component(self) -> bool:
        return self.node_kind in (NodeKind.Id, NodeKind.Enum)

    @property
    def is_enum_element(self) -> bool:
        return self.node_kind in (NodeKind.Id, NodeKind.Cnst, NodeKind.Range)

    @property
    def is_mod_app_arg(self) -> bool:
        return self.node_kind in (
            NodeKind.Id,
            NodeKind.Cnst,
            NodeKind.FuncTerm,
            NodeKind.ModRef,
            NodeKind.Quote,
        )

    @property
    def is_dom_or_trans(self) -> bool:
        return self.node_kind in (NodeKind.Domain, NodeKind.Transform)

    @property
    def is_module(self) -> bool:
        return self.node_kind in (
            NodeKind.Domain,
            NodeKind.Transform,
            NodeKind.TSystem,
            NodeKind.Model,
            NodeKind.Machine,
        )

    @property
    def is_type_decl(self) -> bool:
        return self.node_kind in (
            NodeKind.ConDecl,
            NodeKind.MapDecl,
            NodeKind.UnnDecl,
        )

    @property
    def is_constraint(self) -> bool:
        return self.node_kind in (NodeKind.Find, NodeKind.RelConstr)

    @property
    def is_config_settable(self) -> bool:
        return self.node_kind in (
            NodeKind.Rule,
            NodeKind.Step,
            NodeKind.Update,
            NodeKind.Property,
            NodeKind.ContractItem,
            NodeKind.ModelFact,
            NodeKind.ConDecl,
            NodeKind.MapDecl,
            NodeKind.UnnDecl,
        )

    def can_have_contract(self, kind: ContractKind) -> bool:
        if kind == ContractKind.ConformsProp:
            return self.node_kind == NodeKind.Domain
        if kind in (ContractKind.EnsuresProp, ContractKind.RequiresProp):
            return self.node_kind in (NodeKind.Transform, NodeKind.Model)
        if kind in (
            ContractKind.RequiresSome,
            ContractKind.RequiresAtLeast,
            ContractKind.RequiresAtMost,
        ):
            return self.node_kind == NodeKind.Model
        return False

    @staticmethod
    def print_tree(node: "Node", depth: int = 0) -> None:
        """Debug helper: recursively prints the AST."""
        prefix = " " * depth
        kind_name = node.node_kind.name
        extra = ""
        if hasattr(node, "name") and node.name is not None:
            extra = f", {node.name}"
        print(f"{prefix}{kind_name}{extra}")
        for child in node.children:
            Node.print_tree(child, depth + 4)


# ---------------------------------------------------------------------------
# Concrete leaf nodes
# ---------------------------------------------------------------------------

class Cnst(Node):
    """A constant value (numeric or string).

    Ported from Microsoft.Formula.API.Nodes.Cnst.
    """

    def __init__(self, span: Span, value: TypingUnion[Fraction, int, float, str]):
        super().__init__(span)
        if isinstance(value, str):
            self._raw = value
            self._cnst_kind = CnstKind.String
        else:
            # Normalise to Fraction for numeric values
            if isinstance(value, Fraction):
                self._raw = value
            else:
                self._raw = Fraction(value)
            self._cnst_kind = CnstKind.Numeric

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Cnst

    @property
    def cnst_kind(self) -> CnstKind:
        return self._cnst_kind

    @property
    def raw(self) -> TypingUnion[Fraction, str]:
        return self._raw

    def get_numeric_value(self) -> Fraction:
        assert self._cnst_kind == CnstKind.Numeric
        return self._raw

    def get_string_value(self) -> str:
        assert self._cnst_kind == CnstKind.String
        return self._raw

    @property
    def children(self) -> Iterator[Node]:
        return iter(())

    def deep_clone(self) -> "Cnst":
        c = Cnst(copy.copy(self._span), self._raw)
        return c


class Id(Node):
    """An identifier node.

    Ported from Microsoft.Formula.API.Nodes.Id.
    """

    def __init__(self, span: Span, name: str):
        super().__init__(span)
        self._name = name
        self._fragments: List[str] = name.split(".")

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Id

    @property
    def name(self) -> str:
        return self._name

    @property
    def fragments(self) -> List[str]:
        return list(self._fragments)

    @property
    def is_qualified(self) -> bool:
        return len(self._fragments) > 1

    @property
    def children(self) -> Iterator[Node]:
        return iter(())

    def deep_clone(self) -> "Id":
        return Id(copy.copy(self._span), self._name)

    def unqualify(self) -> "Id":
        if len(self._fragments) <= 1:
            return self
        return Id(self._span, ".".join(self._fragments[1:]))


class Range(Node):
    """An integer range ``[lower..upper]``.

    Ported from Microsoft.Formula.API.Nodes.Range.
    """

    def __init__(self, span: Span, end1: Fraction, end2: Fraction):
        super().__init__(span)
        if end1 <= end2:
            self._lower = Fraction(end1)
            self._upper = Fraction(end2)
        else:
            self._lower = Fraction(end2)
            self._upper = Fraction(end1)

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Range

    @property
    def lower(self) -> Fraction:
        return self._lower

    @property
    def upper(self) -> Fraction:
        return self._upper

    @property
    def children(self) -> Iterator[Node]:
        return iter(())

    def deep_clone(self) -> "Range":
        return Range(copy.copy(self._span), self._lower, self._upper)


class QuoteRun(Node):
    """A run of literal text inside a quotation.

    Ported from Microsoft.Formula.API.Nodes.QuoteRun.
    """

    def __init__(self, span: Span, text: Optional[str] = None):
        super().__init__(span)
        self._text = text if text is not None else ""

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.QuoteRun

    @property
    def text(self) -> str:
        return self._text

    @property
    def children(self) -> Iterator[Node]:
        return iter(())

    def deep_clone(self) -> "QuoteRun":
        return QuoteRun(copy.copy(self._span), self._text)


class ModRef(Node):
    """A module reference.

    Ported from Microsoft.Formula.API.Nodes.ModRef.
    """

    def __init__(
        self,
        span: Span,
        name: str,
        rename: Optional[str] = None,
        location: Optional[str] = None,
    ):
        super().__init__(span)
        self._name = name
        self._rename = rename
        self._location = location

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.ModRef

    @property
    def name(self) -> str:
        return self._name

    @property
    def rename(self) -> Optional[str]:
        return self._rename

    @property
    def location(self) -> Optional[str]:
        return self._location

    @property
    def children(self) -> Iterator[Node]:
        return iter(())

    def deep_clone(self) -> "ModRef":
        return ModRef(copy.copy(self._span), self._name, self._rename, self._location)


class CardPair(Node):
    """A cardinality pair ``(type_id, cardinality)``.

    Ported from Microsoft.Formula.API.Nodes.CardPair.
    """

    def __init__(self, span: Span, type_id: "Id", cardinality: int):
        super().__init__(span)
        self._type_id = type_id
        self._cardinality = cardinality

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.CardPair

    @property
    def type_id(self) -> "Id":
        return self._type_id

    @property
    def cardinality(self) -> int:
        return self._cardinality

    @property
    def children(self) -> Iterator[Node]:
        yield self._type_id

    def deep_clone(self) -> "CardPair":
        return CardPair(
            copy.copy(self._span),
            self._type_id.deep_clone(),
            self._cardinality,
        )


# ---------------------------------------------------------------------------
# Composite term nodes
# ---------------------------------------------------------------------------

class FuncTerm(Node):
    """A function application term.

    ``function`` is either an :class:`Id` (user-defined) or an
    :class:`OpKind` (built-in operator).

    Ported from Microsoft.Formula.API.Nodes.FuncTerm.
    """

    # Mapping from operator name strings to OpKind values.
    _OP_NAME_MAP = {op.name.lower(): op for op in OpKind}

    def __init__(
        self,
        span: Span,
        function_node: TypingUnion["Id", OpKind],
    ):
        super().__init__(span)
        if isinstance(function_node, Id):
            # Try to resolve the name to a built-in OpKind
            lower = function_node.name.lower()
            if lower in self._OP_NAME_MAP:
                self._function: TypingUnion[Id, OpKind] = self._OP_NAME_MAP[lower]
            else:
                self._function = function_node
        else:
            self._function = function_node
        self._args: List[Node] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.FuncTerm

    @property
    def function(self) -> TypingUnion["Id", OpKind]:
        return self._function

    @property
    def args(self) -> Sequence[Node]:
        return list(self._args)

    def add_arg(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._args.append(node)
        else:
            self._args.insert(0, node)

    @property
    def children(self) -> Iterator[Node]:
        if isinstance(self._function, Id):
            yield self._function
        yield from self._args

    def deep_clone(self) -> "FuncTerm":
        if isinstance(self._function, Id):
            clone = FuncTerm(copy.copy(self._span), self._function.deep_clone())
        else:
            clone = FuncTerm(copy.copy(self._span), self._function)
        for a in self._args:
            clone.add_arg(a.deep_clone())
        return clone


class Quote(Node):
    """A quotation (list of quote items).

    Ported from Microsoft.Formula.API.Nodes.Quote.
    """

    def __init__(self, span: Span):
        super().__init__(span)
        self._contents: List[Node] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Quote

    @property
    def contents(self) -> Sequence[Node]:
        return list(self._contents)

    def add_item(self, item: Node, add_last: bool = True) -> None:
        if add_last:
            self._contents.append(item)
        else:
            self._contents.insert(0, item)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._contents

    def deep_clone(self) -> "Quote":
        clone = Quote(copy.copy(self._span))
        for c in self._contents:
            clone.add_item(c.deep_clone())
        return clone


# ---------------------------------------------------------------------------
# Constraint / body / rule nodes
# ---------------------------------------------------------------------------

class Find(Node):
    """A find constraint: ``binding is match``.

    Ported from Microsoft.Formula.API.Nodes.Find.
    """

    def __init__(self, span: Span, binding: Optional["Id"], match: Node):
        super().__init__(span)
        self._binding = binding
        self._match = match

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Find

    @property
    def binding(self) -> Optional["Id"]:
        return self._binding

    @property
    def match(self) -> Node:
        return self._match

    @property
    def children(self) -> Iterator[Node]:
        if self._binding is not None:
            yield self._binding
        yield self._match

    def deep_clone(self) -> "Find":
        return Find(
            copy.copy(self._span),
            self._binding.deep_clone() if self._binding else None,
            self._match.deep_clone(),
        )


class RelConstr(Node):
    """A relational constraint (e.g. ``x = y``, ``x : T``).

    Ported from Microsoft.Formula.API.Nodes.RelConstr.
    """

    def __init__(
        self,
        span: Span,
        op: RelKind,
        arg1: Node,
        arg2: Optional[Node] = None,
    ):
        super().__init__(span)
        self._op = op
        self._arg1 = arg1
        self._arg2 = arg2

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.RelConstr

    @property
    def op(self) -> RelKind:
        return self._op

    @property
    def arg1(self) -> Node:
        return self._arg1

    @property
    def arg2(self) -> Optional[Node]:
        return self._arg2

    @property
    def children(self) -> Iterator[Node]:
        yield self._arg1
        if self._arg2 is not None:
            yield self._arg2

    def deep_clone(self) -> "RelConstr":
        return RelConstr(
            copy.copy(self._span),
            self._op,
            self._arg1.deep_clone(),
            self._arg2.deep_clone() if self._arg2 else None,
        )


class Body(Node):
    """A rule body (conjunction of constraints).

    Ported from Microsoft.Formula.API.Nodes.Body.
    """

    def __init__(self, span: Span):
        super().__init__(span)
        self._constraints: List[Node] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Body

    @property
    def constraints(self) -> Sequence[Node]:
        return list(self._constraints)

    def add_constraint(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._constraints.append(node)
        else:
            self._constraints.insert(0, node)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._constraints

    def deep_clone(self) -> "Body":
        clone = Body(copy.copy(self._span))
        for c in self._constraints:
            clone.add_constraint(c.deep_clone())
        return clone


class Compr(Node):
    """A set comprehension.

    Ported from Microsoft.Formula.API.Nodes.Compr.
    """

    def __init__(self, span: Span):
        super().__init__(span)
        self._heads: List[Node] = []
        self._bodies: List["Body"] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Compr

    @property
    def heads(self) -> Sequence[Node]:
        return list(self._heads)

    @property
    def bodies(self) -> Sequence["Body"]:
        return list(self._bodies)

    def add_head(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._heads.append(node)
        else:
            self._heads.insert(0, node)

    def add_body(self, body: "Body", add_last: bool = True) -> None:
        if add_last:
            self._bodies.append(body)
        else:
            self._bodies.insert(0, body)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._heads
        yield from self._bodies

    def deep_clone(self) -> "Compr":
        clone = Compr(copy.copy(self._span))
        for h in self._heads:
            clone.add_head(h.deep_clone())
        for b in self._bodies:
            clone.add_body(b.deep_clone())
        return clone


class Rule(Node):
    """A derivation rule.

    Ported from Microsoft.Formula.API.Nodes.Rule.
    """

    def __init__(self, span: Span):
        super().__init__(span)
        self._heads: List[Node] = []
        self._bodies: List["Body"] = []
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Rule

    @property
    def heads(self) -> Sequence[Node]:
        return list(self._heads)

    @property
    def bodies(self) -> Sequence["Body"]:
        return list(self._bodies)

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    @property
    def is_fact(self) -> bool:
        return len(self._bodies) == 0

    def add_head(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._heads.append(node)
        else:
            self._heads.insert(0, node)

    def add_body(self, body: "Body", add_last: bool = True) -> None:
        if add_last:
            self._bodies.append(body)
        else:
            self._bodies.insert(0, body)

    def set_config(self, config: "Config") -> None:
        self._config = config

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        yield from self._heads
        yield from self._bodies

    def deep_clone(self) -> "Rule":
        clone = Rule(copy.copy(self._span))
        if self._config:
            clone.set_config(self._config.deep_clone())
        for h in self._heads:
            clone.add_head(h.deep_clone())
        for b in self._bodies:
            clone.add_body(b.deep_clone())
        return clone


class ModelFact(Node):
    """A fact in a model.

    Ported from Microsoft.Formula.API.Nodes.ModelFact.
    """

    def __init__(self, span: Span, binding: Optional["Id"], match: Node):
        super().__init__(span)
        self._binding = binding
        self._match = match
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.ModelFact

    @property
    def binding(self) -> Optional["Id"]:
        return self._binding

    @property
    def match(self) -> Node:
        return self._match

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def set_config(self, config: "Config") -> None:
        self._config = config

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        if self._binding is not None:
            yield self._binding
        yield self._match

    def deep_clone(self) -> "ModelFact":
        clone = ModelFact(
            copy.copy(self._span),
            self._binding.deep_clone() if self._binding else None,
            self._match.deep_clone(),
        )
        if self._config:
            clone.set_config(self._config.deep_clone())
        return clone


class ContractItem(Node):
    """A contract specification item.

    Ported from Microsoft.Formula.API.Nodes.ContractItem.
    """

    def __init__(self, span: Span, contract_kind: ContractKind):
        super().__init__(span)
        self._contract_kind = contract_kind
        self._specification: List[Node] = []
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.ContractItem

    @property
    def contract_kind(self) -> ContractKind:
        return self._contract_kind

    @property
    def specification(self) -> Sequence[Node]:
        return list(self._specification)

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def set_config(self, config: "Config") -> None:
        self._config = config

    def add_specification(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._specification.append(node)
        else:
            self._specification.insert(0, node)

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        yield from self._specification

    def deep_clone(self) -> "ContractItem":
        clone = ContractItem(copy.copy(self._span), self._contract_kind)
        if self._config:
            clone.set_config(self._config.deep_clone())
        for s in self._specification:
            clone.add_specification(s.deep_clone())
        return clone


# ---------------------------------------------------------------------------
# Config / Setting
# ---------------------------------------------------------------------------

class Setting(Node):
    """A configuration key/value setting.

    Ported from Microsoft.Formula.API.Nodes.Setting.
    """

    def __init__(self, span: Span, key: "Id", value: "Cnst"):
        super().__init__(span)
        self._key = key
        self._value = value

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Setting

    @property
    def key(self) -> "Id":
        return self._key

    @property
    def value(self) -> "Cnst":
        return self._value

    @property
    def children(self) -> Iterator[Node]:
        yield self._key
        yield self._value

    def deep_clone(self) -> "Setting":
        return Setting(
            copy.copy(self._span),
            self._key.deep_clone(),
            self._value.deep_clone(),
        )


class Config(Node):
    """A configuration block (list of settings).

    Ported from Microsoft.Formula.API.Nodes.Config.
    """

    def __init__(self, span: Span):
        super().__init__(span)
        self._settings: List["Setting"] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Config

    @property
    def settings(self) -> Sequence["Setting"]:
        return list(self._settings)

    def add_setting(self, setting: "Setting", add_last: bool = True) -> None:
        if add_last:
            self._settings.append(setting)
        else:
            self._settings.insert(0, setting)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._settings

    def deep_clone(self) -> "Config":
        clone = Config(copy.copy(self._span))
        for s in self._settings:
            clone.add_setting(s.deep_clone())
        return clone


# ---------------------------------------------------------------------------
# Type declaration nodes
# ---------------------------------------------------------------------------

class Field(Node):
    """A field in a constructor or map declaration.

    Ported from Microsoft.Formula.API.Nodes.Field.
    """

    def __init__(
        self,
        span: Span,
        name: Optional[str],
        type_node: Node,
        is_any: bool = False,
    ):
        super().__init__(span)
        self._name = name
        self._type = type_node
        self._is_any = is_any

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Field

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def type(self) -> Node:
        return self._type

    @property
    def is_any(self) -> bool:
        return self._is_any

    @property
    def children(self) -> Iterator[Node]:
        yield self._type

    def deep_clone(self) -> "Field":
        return Field(
            copy.copy(self._span),
            self._name,
            self._type.deep_clone(),
            self._is_any,
        )


class Enum(Node):
    """An enumeration type ``{ e1, e2, ... }``.

    Ported from Microsoft.Formula.API.Nodes.Enum.
    """

    def __init__(self, span: Span):
        super().__init__(span)
        self._elements: List[Node] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Enum

    @property
    def elements(self) -> Sequence[Node]:
        return list(self._elements)

    def add_element(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._elements.append(node)
        else:
            self._elements.insert(0, node)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._elements

    def deep_clone(self) -> "Enum":
        clone = Enum(copy.copy(self._span))
        for e in self._elements:
            clone.add_element(e.deep_clone())
        return clone


class Union(Node):
    """A union type ``T1 + T2 + ...``.

    Ported from Microsoft.Formula.API.Nodes.Union.
    """

    def __init__(self, span: Span):
        super().__init__(span)
        self._components: List[Node] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Union

    @property
    def components(self) -> Sequence[Node]:
        return list(self._components)

    def add_component(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._components.append(node)
        else:
            self._components.insert(0, node)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._components

    def deep_clone(self) -> "Union":
        clone = Union(copy.copy(self._span))
        for c in self._components:
            clone.add_component(c.deep_clone())
        return clone


class UnnDecl(Node):
    """A union type declaration.

    Ported from Microsoft.Formula.API.Nodes.UnnDecl.
    """

    def __init__(self, span: Span, name: str, body: Node):
        super().__init__(span)
        self._name = name
        self._body = body
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.UnnDecl

    @property
    def name(self) -> str:
        return self._name

    @property
    def body(self) -> Node:
        return self._body

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def set_config(self, config: "Config") -> None:
        self._config = config

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        yield self._body

    def deep_clone(self) -> "UnnDecl":
        clone = UnnDecl(copy.copy(self._span), self._name, self._body.deep_clone())
        if self._config:
            clone.set_config(self._config.deep_clone())
        return clone


class ConDecl(Node):
    """A constructor declaration.

    Ported from Microsoft.Formula.API.Nodes.ConDecl.
    """

    def __init__(
        self,
        span: Span,
        name: str,
        is_new: bool = False,
        is_sub: bool = False,
    ):
        super().__init__(span)
        self._name = name
        self._is_new = is_new
        self._is_sub = is_sub
        self._fields: List["Field"] = []
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.ConDecl

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_new(self) -> bool:
        return self._is_new

    @property
    def is_sub(self) -> bool:
        return self._is_sub

    @property
    def fields(self) -> Sequence["Field"]:
        return list(self._fields)

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def set_config(self, config: "Config") -> None:
        self._config = config

    def add_field(self, field_node: "Field", add_last: bool = True) -> None:
        if add_last:
            self._fields.append(field_node)
        else:
            self._fields.insert(0, field_node)

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        yield from self._fields

    def deep_clone(self) -> "ConDecl":
        clone = ConDecl(
            copy.copy(self._span), self._name, self._is_new, self._is_sub
        )
        if self._config:
            clone.set_config(self._config.deep_clone())
        for f in self._fields:
            clone.add_field(f.deep_clone())
        return clone


class MapDecl(Node):
    """A map (function) declaration.

    Ported from Microsoft.Formula.API.Nodes.MapDecl.
    """

    def __init__(
        self,
        span: Span,
        name: str,
        map_kind: MapKind = MapKind.Fun,
        is_partial: bool = False,
    ):
        super().__init__(span)
        self._name = name
        self._map_kind = map_kind
        self._is_partial = is_partial
        self._dom: List["Field"] = []
        self._cod: List["Field"] = []
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.MapDecl

    @property
    def name(self) -> str:
        return self._name

    @property
    def map_kind(self) -> MapKind:
        return self._map_kind

    @property
    def is_partial(self) -> bool:
        return self._is_partial

    @is_partial.setter
    def is_partial(self, value: bool) -> None:
        self._is_partial = value

    @property
    def dom(self) -> Sequence["Field"]:
        return list(self._dom)

    @property
    def cod(self) -> Sequence["Field"]:
        return list(self._cod)

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def set_config(self, config: "Config") -> None:
        self._config = config

    def add_dom_field(self, field_node: "Field", add_last: bool = True) -> None:
        if add_last:
            self._dom.append(field_node)
        else:
            self._dom.insert(0, field_node)

    def add_cod_field(self, field_node: "Field", add_last: bool = True) -> None:
        if add_last:
            self._cod.append(field_node)
        else:
            self._cod.insert(0, field_node)

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        yield from self._dom
        yield from self._cod

    def deep_clone(self) -> "MapDecl":
        clone = MapDecl(
            copy.copy(self._span),
            self._name,
            self._map_kind,
            self._is_partial,
        )
        if self._config:
            clone.set_config(self._config.deep_clone())
        for f in self._dom:
            clone.add_dom_field(f.deep_clone())
        for f in self._cod:
            clone.add_cod_field(f.deep_clone())
        return clone


# ---------------------------------------------------------------------------
# Module-level nodes
# ---------------------------------------------------------------------------

class Domain(Node):
    """A domain definition.

    Ported from Microsoft.Formula.API.Nodes.Domain.
    """

    def __init__(self, span: Span, name: str, compose_kind: ComposeKind = ComposeKind.Non):
        super().__init__(span)
        self._name = name
        self._compose_kind = compose_kind
        self._compositions: List["ModRef"] = []
        self._rules: List["Rule"] = []
        self._type_decls: List[Node] = []
        self._conforms: List["ContractItem"] = []
        self._config = Config(span)

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Domain

    @property
    def name(self) -> str:
        return self._name

    @property
    def compose_kind(self) -> ComposeKind:
        return self._compose_kind

    @property
    def compositions(self) -> Sequence["ModRef"]:
        return list(self._compositions)

    @property
    def rules(self) -> Sequence["Rule"]:
        return list(self._rules)

    @property
    def type_decls(self) -> Sequence[Node]:
        return list(self._type_decls)

    @property
    def conforms(self) -> Sequence["ContractItem"]:
        return list(self._conforms)

    @property
    def config(self) -> "Config":
        return self._config

    def add_compose(self, mod_ref: "ModRef", add_last: bool = True) -> None:
        if add_last:
            self._compositions.append(mod_ref)
        else:
            self._compositions.insert(0, mod_ref)

    def add_rule(self, rule: "Rule", add_last: bool = True) -> None:
        if add_last:
            self._rules.append(rule)
        else:
            self._rules.insert(0, rule)

    def add_type_decl(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._type_decls.append(node)
        else:
            self._type_decls.insert(0, node)

    def add_conforms(self, ci: "ContractItem", add_last: bool = True) -> None:
        if add_last:
            self._conforms.append(ci)
        else:
            self._conforms.insert(0, ci)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._compositions
        yield self._config
        yield from self._type_decls
        yield from self._rules
        yield from self._conforms

    def deep_clone(self) -> "Domain":
        clone = Domain(copy.copy(self._span), self._name, self._compose_kind)
        clone._config = self._config.deep_clone()
        for c in self._compositions:
            clone.add_compose(c.deep_clone())
        for t in self._type_decls:
            clone.add_type_decl(t.deep_clone())
        for r in self._rules:
            clone.add_rule(r.deep_clone())
        for cf in self._conforms:
            clone.add_conforms(cf.deep_clone())
        return clone


class Model(Node):
    """A model definition.

    Ported from Microsoft.Formula.API.Nodes.Model.
    """

    def __init__(
        self,
        span: Span,
        name: str,
        is_partial: bool = False,
        domain: Optional["ModRef"] = None,
        compose_kind: ComposeKind = ComposeKind.Non,
    ):
        super().__init__(span)
        self._name = name
        self._is_partial = is_partial
        self._domain = domain if domain is not None else ModRef(span, "?", None, None)
        self._compose_kind = compose_kind
        self._compositions: List["ModRef"] = []
        self._contracts: List["ContractItem"] = []
        self._facts: List["ModelFact"] = []
        self._config = Config(span)

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Model

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_partial(self) -> bool:
        return self._is_partial

    @property
    def domain(self) -> "ModRef":
        return self._domain

    @property
    def compose_kind(self) -> ComposeKind:
        return self._compose_kind

    @property
    def compositions(self) -> Sequence["ModRef"]:
        return list(self._compositions)

    @property
    def contracts(self) -> Sequence["ContractItem"]:
        return list(self._contracts)

    @property
    def facts(self) -> Sequence["ModelFact"]:
        return list(self._facts)

    @property
    def config(self) -> "Config":
        return self._config

    def set_domain(self, mod_ref: "ModRef") -> None:
        self._domain = mod_ref

    def set_compose(self, kind: ComposeKind) -> None:
        self._compose_kind = kind

    def add_compose(self, mod_ref: "ModRef", add_last: bool = True) -> None:
        if add_last:
            self._compositions.append(mod_ref)
        else:
            self._compositions.insert(0, mod_ref)

    def add_fact(self, fact: "ModelFact", add_last: bool = True) -> None:
        if add_last:
            self._facts.append(fact)
        else:
            self._facts.insert(0, fact)

    def add_contract(self, ci: "ContractItem", add_last: bool = True) -> None:
        if add_last:
            self._contracts.append(ci)
        else:
            self._contracts.insert(0, ci)

    @property
    def children(self) -> Iterator[Node]:
        yield self._domain
        yield from self._compositions
        yield self._config
        yield from self._contracts
        yield from self._facts

    def deep_clone(self) -> "Model":
        clone = Model(
            copy.copy(self._span),
            self._name,
            self._is_partial,
            self._domain.deep_clone(),
            self._compose_kind,
        )
        clone._config = self._config.deep_clone()
        for c in self._compositions:
            clone.add_compose(c.deep_clone())
        for ci in self._contracts:
            clone.add_contract(ci.deep_clone())
        for f in self._facts:
            clone.add_fact(f.deep_clone())
        return clone


class Transform(Node):
    """A transform definition.

    Ported from Microsoft.Formula.API.Nodes.Transform.
    """

    def __init__(self, span: Span, name: str):
        super().__init__(span)
        self._name = name
        self._inputs: List["Param"] = []
        self._outputs: List["Param"] = []
        self._contracts: List["ContractItem"] = []
        self._rules: List["Rule"] = []
        self._type_decls: List[Node] = []
        self._config = Config(span)

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Transform

    @property
    def name(self) -> str:
        return self._name

    @property
    def inputs(self) -> Sequence["Param"]:
        return list(self._inputs)

    @property
    def outputs(self) -> Sequence["Param"]:
        return list(self._outputs)

    @property
    def contracts(self) -> Sequence["ContractItem"]:
        return list(self._contracts)

    @property
    def rules(self) -> Sequence["Rule"]:
        return list(self._rules)

    @property
    def type_decls(self) -> Sequence[Node]:
        return list(self._type_decls)

    @property
    def config(self) -> "Config":
        return self._config

    def add_input(self, param: "Param", add_last: bool = True) -> None:
        if add_last:
            self._inputs.append(param)
        else:
            self._inputs.insert(0, param)

    def add_output(self, param: "Param", add_last: bool = True) -> None:
        if add_last:
            self._outputs.append(param)
        else:
            self._outputs.insert(0, param)

    def add_contract(self, ci: "ContractItem", add_last: bool = True) -> None:
        if add_last:
            self._contracts.append(ci)
        else:
            self._contracts.insert(0, ci)

    def add_rule(self, rule: "Rule", add_last: bool = True) -> None:
        if add_last:
            self._rules.append(rule)
        else:
            self._rules.insert(0, rule)

    def add_type_decl(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._type_decls.append(node)
        else:
            self._type_decls.insert(0, node)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._inputs
        yield from self._outputs
        yield self._config
        yield from self._contracts
        yield from self._type_decls
        yield from self._rules

    def deep_clone(self) -> "Transform":
        clone = Transform(copy.copy(self._span), self._name)
        clone._config = self._config.deep_clone()
        for p in self._inputs:
            clone.add_input(p.deep_clone())
        for p in self._outputs:
            clone.add_output(p.deep_clone())
        for ci in self._contracts:
            clone.add_contract(ci.deep_clone())
        for t in self._type_decls:
            clone.add_type_decl(t.deep_clone())
        for r in self._rules:
            clone.add_rule(r.deep_clone())
        return clone


class TSystem(Node):
    """A transform system.

    Ported from Microsoft.Formula.API.Nodes.TSystem.
    """

    def __init__(self, span: Span, name: str):
        super().__init__(span)
        self._name = name
        self._inputs: List["Param"] = []
        self._outputs: List["Param"] = []
        self._steps: List["Step"] = []
        self._config = Config(span)

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.TSystem

    @property
    def name(self) -> str:
        return self._name

    @property
    def inputs(self) -> Sequence["Param"]:
        return list(self._inputs)

    @property
    def outputs(self) -> Sequence["Param"]:
        return list(self._outputs)

    @property
    def steps(self) -> Sequence["Step"]:
        return list(self._steps)

    @property
    def config(self) -> "Config":
        return self._config

    def add_input(self, param: "Param", add_last: bool = True) -> None:
        if add_last:
            self._inputs.append(param)
        else:
            self._inputs.insert(0, param)

    def add_output(self, param: "Param", add_last: bool = True) -> None:
        if add_last:
            self._outputs.append(param)
        else:
            self._outputs.insert(0, param)

    def add_step(self, step: "Step", add_last: bool = True) -> None:
        if add_last:
            self._steps.append(step)
        else:
            self._steps.insert(0, step)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._inputs
        yield from self._outputs
        yield self._config
        yield from self._steps

    def deep_clone(self) -> "TSystem":
        clone = TSystem(copy.copy(self._span), self._name)
        clone._config = self._config.deep_clone()
        for p in self._inputs:
            clone.add_input(p.deep_clone())
        for p in self._outputs:
            clone.add_output(p.deep_clone())
        for s in self._steps:
            clone.add_step(s.deep_clone())
        return clone


class Machine(Node):
    """A machine definition.

    Ported from Microsoft.Formula.API.Nodes.Machine.
    """

    def __init__(self, span: Span, name: str):
        super().__init__(span)
        self._name = name
        self._inputs: List["Param"] = []
        self._state_domains: List["ModRef"] = []
        self._boot_sequence: List["Step"] = []
        self._initials: List["Update"] = []
        self._nexts: List["Update"] = []
        self._properties: List["Property"] = []
        self._config = Config(span)

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Machine

    @property
    def name(self) -> str:
        return self._name

    @property
    def inputs(self) -> Sequence["Param"]:
        return list(self._inputs)

    @property
    def state_domains(self) -> Sequence["ModRef"]:
        return list(self._state_domains)

    @property
    def boot_sequence(self) -> Sequence["Step"]:
        return list(self._boot_sequence)

    @property
    def initials(self) -> Sequence["Update"]:
        return list(self._initials)

    @property
    def nexts(self) -> Sequence["Update"]:
        return list(self._nexts)

    @property
    def properties(self) -> Sequence["Property"]:
        return list(self._properties)

    @property
    def config(self) -> "Config":
        return self._config

    def add_input(self, param: "Param", add_last: bool = True) -> None:
        if add_last:
            self._inputs.append(param)
        else:
            self._inputs.insert(0, param)

    def add_state_domain(self, mod: "ModRef", add_last: bool = True) -> None:
        if add_last:
            self._state_domains.append(mod)
        else:
            self._state_domains.insert(0, mod)

    def add_boot_step(self, step: "Step", add_last: bool = True) -> None:
        if add_last:
            self._boot_sequence.append(step)
        else:
            self._boot_sequence.insert(0, step)

    def add_update(
        self, update: "Update", is_initial: bool, add_last: bool = True
    ) -> None:
        target = self._initials if is_initial else self._nexts
        if add_last:
            target.append(update)
        else:
            target.insert(0, update)

    def add_property(self, prop: "Property", add_last: bool = True) -> None:
        if add_last:
            self._properties.append(prop)
        else:
            self._properties.insert(0, prop)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._inputs
        yield from self._state_domains
        yield self._config
        yield from self._boot_sequence
        yield from self._initials
        yield from self._nexts
        yield from self._properties

    def deep_clone(self) -> "Machine":
        clone = Machine(copy.copy(self._span), self._name)
        clone._config = self._config.deep_clone()
        for p in self._inputs:
            clone.add_input(p.deep_clone())
        for sd in self._state_domains:
            clone.add_state_domain(sd.deep_clone())
        for s in self._boot_sequence:
            clone.add_boot_step(s.deep_clone())
        for u in self._initials:
            clone.add_update(u.deep_clone(), is_initial=True)
        for u in self._nexts:
            clone.add_update(u.deep_clone(), is_initial=False)
        for p in self._properties:
            clone.add_property(p.deep_clone())
        return clone


# ---------------------------------------------------------------------------
# Step / Update / Param / ModApply / Property
# ---------------------------------------------------------------------------

class ModApply(Node):
    """A module application.

    Ported from Microsoft.Formula.API.Nodes.ModApply.
    """

    def __init__(self, span: Span, module: "ModRef"):
        super().__init__(span)
        self._module = module
        self._args: List[Node] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.ModApply

    @property
    def module(self) -> "ModRef":
        return self._module

    @property
    def args(self) -> Sequence[Node]:
        return list(self._args)

    def add_arg(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._args.append(node)
        else:
            self._args.insert(0, node)

    @property
    def children(self) -> Iterator[Node]:
        yield self._module
        yield from self._args

    def deep_clone(self) -> "ModApply":
        clone = ModApply(copy.copy(self._span), self._module.deep_clone())
        for a in self._args:
            clone.add_arg(a.deep_clone())
        return clone


class Step(Node):
    """A step in a transform system or boot sequence.

    Ported from Microsoft.Formula.API.Nodes.Step.
    """

    def __init__(self, span: Span, rhs: Optional["ModApply"] = None):
        super().__init__(span)
        self._lhs: List["Id"] = []
        self._rhs = rhs if rhs is not None else ModApply(span, ModRef(span, "?", None, None))
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Step

    @property
    def lhs(self) -> Sequence["Id"]:
        return list(self._lhs)

    @property
    def rhs(self) -> "ModApply":
        return self._rhs

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def add_lhs(self, id_node: "Id", add_last: bool = True) -> None:
        if add_last:
            self._lhs.append(id_node)
        else:
            self._lhs.insert(0, id_node)

    def set_rhs(self, mod_apply: "ModApply") -> None:
        self._rhs = mod_apply

    def set_config(self, config: "Config") -> None:
        self._config = config

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        yield from self._lhs
        yield self._rhs

    def deep_clone(self) -> "Step":
        clone = Step(copy.copy(self._span), self._rhs.deep_clone())
        if self._config:
            clone.set_config(self._config.deep_clone())
        for lhs_id in self._lhs:
            clone.add_lhs(lhs_id.deep_clone())
        return clone


class Update(Node):
    """A state update in a machine.

    Ported from Microsoft.Formula.API.Nodes.Update.
    """

    def __init__(self, span: Span):
        super().__init__(span)
        self._states: List["Id"] = []
        self._choices: List["ModApply"] = []
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Update

    @property
    def states(self) -> Sequence["Id"]:
        return list(self._states)

    @property
    def choices(self) -> Sequence["ModApply"]:
        return list(self._choices)

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def set_config(self, config: "Config") -> None:
        self._config = config

    def add_state(self, id_node: "Id", add_last: bool = True) -> None:
        if add_last:
            self._states.append(id_node)
        else:
            self._states.insert(0, id_node)

    def add_choice(self, mod_apply: "ModApply", add_last: bool = True) -> None:
        if add_last:
            self._choices.append(mod_apply)
        else:
            self._choices.insert(0, mod_apply)

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        yield from self._states
        yield from self._choices

    def deep_clone(self) -> "Update":
        clone = Update(copy.copy(self._span))
        if self._config:
            clone.set_config(self._config.deep_clone())
        for s in self._states:
            clone.add_state(s.deep_clone())
        for c in self._choices:
            clone.add_choice(c.deep_clone())
        return clone


class Param(Node):
    """A parameter declaration.

    Ported from Microsoft.Formula.API.Nodes.Param.
    """

    def __init__(self, span: Span, name: Optional[str], type_node: Node):
        super().__init__(span)
        self._name = name
        self._type = type_node

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Param

    @property
    def name(self) -> Optional[str]:
        return self._name

    @property
    def type(self) -> Node:
        return self._type

    @property
    def is_value_param(self) -> bool:
        return self._type.node_kind != NodeKind.ModRef

    @property
    def children(self) -> Iterator[Node]:
        yield self._type

    def deep_clone(self) -> "Param":
        return Param(copy.copy(self._span), self._name, self._type.deep_clone())


class Property(Node):
    """A property definition in a machine.

    Ported from Microsoft.Formula.API.Nodes.Property.
    """

    def __init__(self, span: Span, name: str, definition: Node):
        super().__init__(span)
        self._name = name
        self._definition = definition
        self._config: Optional["Config"] = None

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Property

    @property
    def name(self) -> str:
        return self._name

    @property
    def definition(self) -> Node:
        return self._definition

    @property
    def config(self) -> Optional["Config"]:
        return self._config

    def set_config(self, config: "Config") -> None:
        self._config = config

    @property
    def children(self) -> Iterator[Node]:
        if self._config is not None:
            yield self._config
        yield self._definition

    def deep_clone(self) -> "Property":
        clone = Property(
            copy.copy(self._span), self._name, self._definition.deep_clone()
        )
        if self._config:
            clone.set_config(self._config.deep_clone())
        return clone


# ---------------------------------------------------------------------------
# Top-level nodes: Folder & Program
# ---------------------------------------------------------------------------

class Folder(Node):
    """A folder node containing sub-folders and programs.

    Ported from Microsoft.Formula.API.Nodes.Folder.
    """

    def __init__(self, name: str):
        super().__init__(Span())
        self._name = name
        self._sub_folders: List["Folder"] = []
        self._programs: List["Program"] = []

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Folder

    @property
    def name(self) -> str:
        return self._name

    @property
    def sub_folders(self) -> Sequence["Folder"]:
        return list(self._sub_folders)

    @property
    def programs(self) -> Sequence["Program"]:
        return list(self._programs)

    def add_sub_folder(self, folder: "Folder") -> None:
        self._sub_folders.append(folder)

    def add_program(self, program: "Program") -> None:
        self._programs.append(program)

    @property
    def children(self) -> Iterator[Node]:
        yield from self._sub_folders
        yield from self._programs

    def deep_clone(self) -> "Folder":
        clone = Folder(self._name)
        for f in self._sub_folders:
            clone.add_sub_folder(f.deep_clone())
        for p in self._programs:
            clone.add_program(p.deep_clone())
        return clone


class Program(Node):
    """A FORMULA program (the top-level compilation unit).

    Ported from Microsoft.Formula.API.Nodes.Program.
    """

    def __init__(self, name: "ProgramName"):
        super().__init__(Span())
        self._name = name
        self._modules: List[Node] = []
        self._config = Config(Span())

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.Program

    @property
    def name(self) -> "ProgramName":
        return self._name

    @property
    def modules(self) -> Sequence[Node]:
        return list(self._modules)

    @property
    def config(self) -> "Config":
        return self._config

    def add_module(self, node: Node, add_last: bool = True) -> None:
        if add_last:
            self._modules.append(node)
        else:
            self._modules.insert(0, node)

    @property
    def children(self) -> Iterator[Node]:
        yield self._config
        yield from self._modules

    def deep_clone(self) -> "Program":
        clone = Program(self._name)
        clone._config = self._config.deep_clone()
        for m in self._modules:
            clone.add_module(m.deep_clone())
        return clone
