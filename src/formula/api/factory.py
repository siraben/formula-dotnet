"""Node factory for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.Factory (Src/Core/API/Base/Factory.cs).

Provides a singleton ``Factory`` with convenience methods for creating
FORMULA AST nodes wrapped in :class:`AST` objects.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Optional, Sequence

from formula.api.ast import AST
from formula.api.constants import (
    ComposeKind,
    ContractKind,
    MapKind,
    NodeKind,
    OpKind,
    RelKind,
)
from formula.api.nodes import (
    Body,
    CardPair,
    Cnst,
    Compr,
    ConDecl,
    Config,
    ContractItem,
    Domain,
    Enum,
    Field,
    Find,
    Folder,
    FuncTerm,
    Id,
    Machine,
    MapDecl,
    Model,
    ModApply,
    ModRef,
    ModelFact,
    Node,
    Param,
    Program,
    ProgramName,
    Property,
    Quote,
    QuoteRun,
    Range,
    RelConstr,
    Rule,
    Setting,
    Span,
    Step,
    TSystem,
    Transform,
    Union,
    UnnDecl,
    Update,
)


class Factory:
    """Singleton factory for creating FORMULA AST nodes.

    Ported from Microsoft.Formula.API.Factory.
    """

    _instance: Optional["Factory"] = None

    @classmethod
    def instance(cls) -> "Factory":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- Leaf node constructors ---------------------------------------------

    def mk_cnst(self, value, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        if isinstance(value, str):
            return AST(Cnst(span, value))
        return AST(Cnst(span, Fraction(value)))

    def mk_id(self, name: str, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Id(span, name))

    def mk_range(self, end1: Fraction, end2: Fraction, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Range(span, end1, end2))

    def mk_mod_ref(self, name: str, rename: Optional[str] = None, location: Optional[str] = None, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(ModRef(span, name, rename, location))

    # -- Composite node constructors ----------------------------------------

    def mk_func_term(self, function, span: Optional[Span] = None, *args: AST) -> AST:
        if span is None:
            span = Span()
        if isinstance(function, AST):
            ft = FuncTerm(span, function.node)
        elif isinstance(function, OpKind):
            ft = FuncTerm(span, function)
        else:
            ft = FuncTerm(span, function)
        for a in args:
            ft.add_arg(a.node if isinstance(a, AST) else a)
        return AST(ft)

    def mk_rel_constr(self, op: RelKind, arg1: AST, arg2: AST, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(RelConstr(span, op, arg1.node, arg2.node))

    def mk_no(self, compr: AST, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(RelConstr(span, RelKind.No, compr.node))

    def mk_find(self, match: AST, binding: Optional[AST] = None, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        b = binding.node if binding else None
        return AST(Find(span, b, match.node))

    def mk_model_fact(self, match: AST, binding: Optional[AST] = None, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        b = binding.node if binding else None
        return AST(ModelFact(span, b, match.node))

    def mk_body(self, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Body(span))

    def mk_rule(self, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Rule(span))

    def mk_config(self, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Config(span))

    def mk_compr(self, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Compr(span))

    def mk_quote(self, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Quote(span))

    def mk_quote_run(self, text: str, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(QuoteRun(span, text))

    def mk_mod_apply(self, module: AST, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(ModApply(span, module.node))

    def mk_card_pair(self, type_id: AST, cardinality: int, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(CardPair(span, type_id.node, cardinality))

    # -- Module constructors ------------------------------------------------

    def mk_domain(self, name: str, compose_kind: ComposeKind = ComposeKind.Non, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Domain(span, name, compose_kind))

    def mk_model(self, name: str, domain: AST, is_partial: bool = False, compose_kind: ComposeKind = ComposeKind.Non, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Model(span, name, is_partial, domain.node, compose_kind))

    def mk_transform(self, name: str, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Transform(span, name))

    def mk_tsystem(self, name: str, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(TSystem(span, name))

    def mk_machine(self, name: str, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(Machine(span, name))

    def mk_program(self, name: ProgramName) -> AST:
        return AST(Program(name))

    def mk_folder(self, name: str) -> AST:
        return AST(Folder(name))

    # -- Type declaration constructors --------------------------------------

    def mk_con_decl(self, name: str, is_new: bool = True, is_sub: bool = False, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(ConDecl(span, name, is_new, is_sub))

    def mk_map_decl(self, name: str, kind: MapKind = MapKind.Fun, is_partial: bool = True, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        return AST(MapDecl(span, name, kind, is_partial))

    def mk_unn_decl(self, name: str, body, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        b = body.node if isinstance(body, AST) else body
        return AST(UnnDecl(span, name, b))

    def mk_field(self, name: Optional[str], type_term, is_any: bool = False, span: Optional[Span] = None) -> AST:
        if span is None:
            span = Span()
        t = type_term.node if isinstance(type_term, AST) else type_term
        return AST(Field(span, name, t, is_any))

    # -- Wrap helpers -------------------------------------------------------

    def to_ast(self, node: Node) -> AST:
        """Wrap an existing node in an AST."""
        return AST(node)
