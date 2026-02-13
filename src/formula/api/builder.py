"""AST builder for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.Builder (Src/Core/API/Base/Builder.cs).

Provides a stack-based builder for programmatically constructing FORMULA
ASTs.  Nodes are pushed and assembled using the same protocol as the C#
``Builder`` class.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Tuple

from formula.api.ast import AST
from formula.api.constants import (
    AttributeKind,
    BuilderResultKind,
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


# ---------------------------------------------------------------------------
# BuilderRef -- opaque reference to a stored node
# ---------------------------------------------------------------------------

class BuilderRef:
    """An opaque handle to a node stored on the builder's heap."""

    __slots__ = ("_id",)

    def __init__(self, ref_id: int):
        self._id = ref_id

    @property
    def id(self) -> int:
        return self._id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BuilderRef):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"BuilderRef({self._id})"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class Builder:
    """Stack-based builder for constructing FORMULA ASTs.

    Ported from Microsoft.Formula.API.Builder.

    Nodes are pushed onto a stack, composed via ``Add*`` operations,
    and finally extracted via ``close()`` / ``get_asts()``.
    """

    def __init__(self) -> None:
        self._stack: List[Node] = []
        self._heap: Dict[BuilderRef, Node] = {}
        self._next_ref_id: int = 1
        self._is_closed: bool = False
        self._final_asts: Optional[List[AST]] = None

    # -- State queries ------------------------------------------------------

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    # -- Memory operations --------------------------------------------------

    def pop(self) -> BuilderResultKind:
        if self._is_closed or not self._stack:
            return BuilderResultKind.Fail_BadArgs
        self._stack.pop()
        return BuilderResultKind.Success

    def store(self) -> Tuple[BuilderResultKind, Optional[BuilderRef]]:
        if self._is_closed or not self._stack:
            return BuilderResultKind.Fail_BadArgs, None
        bref = BuilderRef(self._next_ref_id)
        self._next_ref_id += 1
        self._heap[bref] = self._stack.pop()
        return BuilderResultKind.Success, bref

    def load(self, bref: BuilderRef) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        node = self._heap.get(bref)
        if node is None:
            return BuilderResultKind.Fail_BadArgs
        self._stack.append(node)
        return BuilderResultKind.Success

    def clear(self, bref: BuilderRef) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        self._heap.pop(bref, None)
        return BuilderResultKind.Success

    # -- Peek operations ----------------------------------------------------

    def get_stack_count(self) -> Tuple[BuilderResultKind, int]:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed, 0
        return BuilderResultKind.Success, len(self._stack)

    def peek_node_kind(self) -> Tuple[BuilderResultKind, NodeKind]:
        if self._is_closed or not self._stack:
            return BuilderResultKind.Fail_BadArgs, NodeKind.AnyNodeKind
        return BuilderResultKind.Success, self._stack[-1].node_kind

    def peek_child_count(self) -> Tuple[BuilderResultKind, int]:
        if self._is_closed or not self._stack:
            return BuilderResultKind.Fail_BadArgs, 0
        return BuilderResultKind.Success, self._stack[-1].child_count

    # -- Push operations ----------------------------------------------------

    def push_cnst(self, value, span: Span = None) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        if span is None:
            span = Span()
        if isinstance(value, str):
            self._stack.append(Cnst(span, value))
        elif isinstance(value, (int, float, Fraction)):
            self._stack.append(Cnst(span, Fraction(value)))
        else:
            return BuilderResultKind.Fail_BadArgs
        return BuilderResultKind.Success

    def push_id(self, name: str, span: Span = None) -> BuilderResultKind:
        if self._is_closed or name is None:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        self._stack.append(Id(span, name))
        return BuilderResultKind.Success

    def push_func_term(self, span: Span = None) -> BuilderResultKind:
        """Pop an Id from stack and push a FuncTerm using it as the function name."""
        if self._is_closed or not self._stack:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Id:
            return BuilderResultKind.Fail_BadArgs
        self._stack.pop()
        self._stack.append(FuncTerm(span, top))
        return BuilderResultKind.Success

    def push_func_term_op(self, op_kind: OpKind, span: Span = None) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        if span is None:
            span = Span()
        self._stack.append(FuncTerm(span, op_kind))
        return BuilderResultKind.Success

    def push_range(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        arg2 = self._stack.pop()
        arg1 = self._stack.pop()
        if arg1.node_kind != NodeKind.Cnst or arg2.node_kind != NodeKind.Cnst:
            return BuilderResultKind.Fail_BadArgs
        self._stack.append(Range(span, arg1.raw, arg2.raw))
        return BuilderResultKind.Success

    def push_mod_ref(self, name: str, rename: Optional[str], loc: Optional[str], span: Span = None) -> BuilderResultKind:
        if self._is_closed or not name:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        self._stack.append(ModRef(span, name, rename, loc))
        return BuilderResultKind.Success

    def push_mod_apply(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed or not self._stack:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        top = self._stack[-1]
        if top.node_kind != NodeKind.ModRef:
            return BuilderResultKind.Fail_BadArgs
        self._stack.pop()
        self._stack.append(ModApply(span, top))
        return BuilderResultKind.Success

    def push_rel_constr(self, rel_kind: RelKind, span: Span = None) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        arg2 = self._stack.pop()
        arg1 = self._stack.pop()
        self._stack.append(RelConstr(span, rel_kind, arg1, arg2))
        return BuilderResultKind.Success

    def push_find(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        match = self._stack.pop()
        binding = self._stack.pop()
        if binding.node_kind != NodeKind.Id:
            return BuilderResultKind.Fail_BadArgs
        self._stack.append(Find(span, binding, match))
        return BuilderResultKind.Success

    def push_find_no_binding(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed or not self._stack:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        match = self._stack.pop()
        self._stack.append(Find(span, None, match))
        return BuilderResultKind.Success

    def push_model_fact(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed or not self._stack:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        match = self._stack.pop()
        binding = None
        if self._stack and self._stack[-1].node_kind == NodeKind.Id:
            binding = self._stack.pop()
        self._stack.append(ModelFact(span, binding, match))
        return BuilderResultKind.Success

    def push_body(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        if span is None:
            span = Span()
        self._stack.append(Body(span))
        return BuilderResultKind.Success

    def push_rule(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        if span is None:
            span = Span()
        self._stack.append(Rule(span))
        return BuilderResultKind.Success

    def push_config(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        if span is None:
            span = Span()
        self._stack.append(Config(span))
        return BuilderResultKind.Success

    def push_compr(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        if span is None:
            span = Span()
        self._stack.append(Compr(span))
        return BuilderResultKind.Success

    def push_quote(self, span: Span = None) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        if span is None:
            span = Span()
        self._stack.append(Quote(span))
        return BuilderResultKind.Success

    def push_quote_run(self, text: str, span: Span = None) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        if span is None:
            span = Span()
        self._stack.append(QuoteRun(span, text))
        return BuilderResultKind.Success

    def push_domain(self, name: str, compose_kind: ComposeKind = ComposeKind.Non, span: Span = None) -> BuilderResultKind:
        if self._is_closed or not name:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        self._stack.append(Domain(span, name, compose_kind))
        return BuilderResultKind.Success

    def push_model(self, name: str, is_partial: bool = False, compose_kind: ComposeKind = ComposeKind.Non, span: Span = None) -> BuilderResultKind:
        if self._is_closed or not name:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        mod_ref = None
        if self._stack and self._stack[-1].node_kind == NodeKind.ModRef:
            mod_ref = self._stack.pop()
        self._stack.append(Model(span, name, is_partial, mod_ref, compose_kind))
        return BuilderResultKind.Success

    def push_transform(self, name: str, span: Span = None) -> BuilderResultKind:
        if self._is_closed or not name:
            return BuilderResultKind.Fail_BadArgs
        if span is None:
            span = Span()
        self._stack.append(Transform(span, name))
        return BuilderResultKind.Success

    def push_program(self, name: ProgramName) -> BuilderResultKind:
        if self._is_closed:
            return BuilderResultKind.Fail_Closed
        self._stack.append(Program(name))
        return BuilderResultKind.Success

    # -- Add operations (attach children to the top node) --------------------

    def add_func_term_arg(self) -> BuilderResultKind:
        """Pop arg and add it to the FuncTerm below it on the stack."""
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        arg = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.FuncTerm:
            self._stack.append(arg)
            return BuilderResultKind.Fail_BadArgs
        top.add_arg(arg)
        return BuilderResultKind.Success

    def add_mod_apply_arg(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        arg = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.ModApply:
            self._stack.append(arg)
            return BuilderResultKind.Fail_BadArgs
        top.add_arg(arg)
        return BuilderResultKind.Success

    def add_body_constr(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        constr = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Body:
            self._stack.append(constr)
            return BuilderResultKind.Fail_BadArgs
        top.add_constraint(constr)
        return BuilderResultKind.Success

    def add_rule_head(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        head = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Rule:
            self._stack.append(head)
            return BuilderResultKind.Fail_BadArgs
        top.add_head(head)
        return BuilderResultKind.Success

    def add_rule_body(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        body = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Rule:
            self._stack.append(body)
            return BuilderResultKind.Fail_BadArgs
        top.add_body(body)
        return BuilderResultKind.Success

    def add_model_fact(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        fact = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind == NodeKind.Model:
            if fact.node_kind != NodeKind.ModelFact:
                fact = ModelFact(fact.span, None, fact)
            top.add_fact(fact)
            return BuilderResultKind.Success
        self._stack.append(fact)
        return BuilderResultKind.Fail_BadArgs

    def add_domain_type_decl(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        decl = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Domain:
            self._stack.append(decl)
            return BuilderResultKind.Fail_BadArgs
        top.add_type_decl(decl)
        return BuilderResultKind.Success

    def add_domain_rule(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        rule = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Domain:
            self._stack.append(rule)
            return BuilderResultKind.Fail_BadArgs
        top.add_rule(rule)
        return BuilderResultKind.Success

    def add_quote_item(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        item = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Quote:
            self._stack.append(item)
            return BuilderResultKind.Fail_BadArgs
        top.add_item(item)
        return BuilderResultKind.Success

    def add_setting(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 3:
            return BuilderResultKind.Fail_BadArgs
        value = self._stack.pop()
        key = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Config:
            self._stack.append(key)
            self._stack.append(value)
            return BuilderResultKind.Fail_BadArgs
        top.add_setting(Setting(key.span, key, value))
        return BuilderResultKind.Success

    def add_program_module(self) -> BuilderResultKind:
        if self._is_closed or len(self._stack) < 2:
            return BuilderResultKind.Fail_BadArgs
        module = self._stack.pop()
        top = self._stack[-1]
        if top.node_kind != NodeKind.Program:
            self._stack.append(module)
            return BuilderResultKind.Fail_BadArgs
        top.add_module(module)
        return BuilderResultKind.Success

    # -- Close and extract --------------------------------------------------

    def close(self) -> int:
        """Close the builder and return the number of items remaining on the stack."""
        if self._is_closed:
            return 0
        self._is_closed = True
        self._final_asts = [AST(n) for n in self._stack]
        return len(self._stack)

    def get_asts(self) -> Tuple[bool, Optional[List[AST]]]:
        """Return the ASTs produced by this builder.

        Returns (True, asts) if the builder is closed, else (False, None).
        """
        if not self._is_closed or self._final_asts is None:
            return False, None
        return True, list(self._final_asts)
