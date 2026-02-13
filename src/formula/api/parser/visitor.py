"""Port of Src/Core/API/Parser/FormulaVisitor.cs

ANTLR visitor that builds AST nodes from FORMULA parse trees.
"""

from __future__ import annotations

from fractions import Fraction
from typing import List, Optional

from formula.api.parser.FormulaParserVisitor import FormulaParserVisitor
from formula.api.parser.FormulaParser import FormulaParser
from formula.api.constants import (
    ASTSchema,
    ComposeKind,
    ContractKind,
    MapKind,
    NodeKind,
    OpKind,
    RelKind,
    SeverityKind,
)
from formula.api.constants import BAD_FILE, BAD_NUMERIC, OP_CANCELLED
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


# -----------------------------------------------------------------------
# Flag (lightweight class for parse errors/warnings)
# -----------------------------------------------------------------------

class Flag:
    """A diagnostic flag produced during parsing."""

    __slots__ = ("severity", "span", "message", "code", "program_name")

    def __init__(
        self,
        severity: SeverityKind,
        span: Span,
        message: str,
        code: int,
        program_name: Optional[ProgramName] = None,
    ):
        self.severity = severity
        self.span = span
        self.message = message
        self.code = code
        self.program_name = program_name

    def __str__(self) -> str:
        loc = ""
        if self.span and self.span.start_line:
            loc = f"({self.span.start_line},{self.span.start_col}): "
        return f"[{self.severity.name}] {loc}{self.message}"


# -----------------------------------------------------------------------
# ParseResult
# -----------------------------------------------------------------------

class ParseResult:
    """Result of a parse operation. Holds the AST Program and any flags."""

    def __init__(self, program: Optional[Program] = None):
        if program is None:
            name = ProgramName("dummy.4ml")
            program = Program(name)
        self._program = program
        self._name = program.name
        self._flags: List[Flag] = []
        self._succeeded = True

    @property
    def program(self) -> Program:
        return self._program

    @property
    def name(self) -> ProgramName:
        return self._name

    @property
    def flags(self) -> List[Flag]:
        return list(self._flags)

    @property
    def succeeded(self) -> bool:
        return self._succeeded

    def add_flag(self, flag: Flag) -> None:
        if flag.severity == SeverityKind.Error:
            self._succeeded = False
        self._flags.append(flag)

    def clear_flags(self) -> None:
        self._flags.clear()
        self._succeeded = True


# -----------------------------------------------------------------------
# Internal ApplyInfo classes
# -----------------------------------------------------------------------

class _ApplyInfo:
    """Base for apply info stack entries."""

    __slots__ = ("app_kind", "span")

    def __init__(self, app_kind: NodeKind, span: Span):
        self.app_kind = app_kind
        self.span = span

    @property
    def arity(self) -> int:
        raise NotImplementedError

    def inc_arity(self) -> None:
        raise NotImplementedError


class _FuncApplyInfo(_ApplyInfo):
    __slots__ = ("func_name", "_arity")

    def __init__(self, func_name, span: Optional[Span] = None):
        if isinstance(func_name, Id):
            super().__init__(NodeKind.FuncTerm, func_name.span)
            self.func_name = func_name
        elif isinstance(func_name, OpKind):
            super().__init__(NodeKind.FuncTerm, span)
            self.func_name = func_name
        else:
            raise TypeError(f"Unexpected func_name type: {type(func_name)}")
        self._arity = 0

    @property
    def arity(self) -> int:
        return self._arity

    def inc_arity(self) -> None:
        self._arity += 1


class _RelApplyInfo(_ApplyInfo):
    __slots__ = ("opcode",)

    def __init__(self, opcode: RelKind, span: Span):
        super().__init__(NodeKind.RelConstr, span)
        self.opcode = opcode

    @property
    def arity(self) -> int:
        return 2

    def inc_arity(self) -> None:
        raise RuntimeError("Cannot increment arity on RelApplyInfo")


class _ComprApplyInfo(_ApplyInfo):
    __slots__ = ("comprehension", "current_body", "_arity")

    def __init__(self, compr: Compr):
        super().__init__(NodeKind.Compr, compr.span)
        self.comprehension = compr
        self.current_body: Optional[Body] = None
        self._arity = 0

    @property
    def arity(self) -> int:
        return self._arity

    def inc_arity(self) -> None:
        self._arity += 1


class _ModApplyInfo(_ApplyInfo):
    __slots__ = ("mod_ref", "_arity")

    def __init__(self, mod_ref: ModRef):
        super().__init__(NodeKind.ModApply, mod_ref.span)
        self.mod_ref = mod_ref
        self._arity = 0

    @property
    def arity(self) -> int:
        return self._arity

    def inc_arity(self) -> None:
        self._arity += 1


# -----------------------------------------------------------------------
# ModRefState
# -----------------------------------------------------------------------

class _ModRefState:
    Non = 0
    ModApply = 1
    Input = 2
    Output = 3
    Other = 4


# -----------------------------------------------------------------------
# FormulaVisitor
# -----------------------------------------------------------------------

class FormulaVisitor(FormulaParserVisitor):
    """Builds a FORMULA AST from an ANTLR parse tree.

    Port of Microsoft.Formula.API.FormulaVisitor (FormulaVisitor.cs, 2663 lines).
    """

    def __init__(self):
        self._parse_result: Optional[ParseResult] = None
        self._current_module: Optional[Node] = None

        # State for building terms
        self._app_stack: List[_ApplyInfo] = []
        self._arg_stack: List[Node] = []
        self._quote_stack: List[Quote] = []

        # State for building rules, contracts, and comprehensions
        self._crnt_rule: Optional[Rule] = None
        self._crnt_contract: Optional[ContractItem] = None
        self._crnt_body: Optional[Body] = None

        # State for building types and type declarations
        self._crnt_type_decl_name: Optional[str] = None
        self._crnt_type_decl_span: Span = Span()
        self._crnt_type_decl: Optional[Node] = None
        self._crnt_type_term: Optional[Node] = None
        self._current_enum: Optional[Enum] = None

        # State for ModRefs, steps, and updates
        self._crnt_mod_ref: Optional[ModRef] = None
        self._crnt_step: Optional[Step] = None
        self._crnt_update: Optional[Update] = None
        self._crnt_mod_ref_state: int = _ModRefState.Non

        # State for sentence configs
        self._crnt_sent_conf: Optional[Config] = None

        # Flags
        self._is_building_next = False
        self._is_building_update = False
        self._is_building_cod = False

        # String buffer
        self._string_buffer: List[str] = []

    # -- Public entry points ------------------------------------------------

    @property
    def parse_result(self) -> ParseResult:
        return self._parse_result

    def init_parse_result(self, program: Program) -> ParseResult:
        self._parse_result = ParseResult(program)
        self._reset_state()
        return self._parse_result

    # -- Private helpers (mirrors C# private methods) -----------------------

    def _to_span(self, token) -> Span:
        if token is None:
            return Span()
        return Span(
            token.line,
            token.column,
            token.line,
            token.stop,
            self._parse_result.name,
        )

    def _reset_state(self) -> None:
        self._current_module = None
        self._parse_result.clear_flags()
        self._app_stack.clear()
        self._arg_stack.clear()
        self._quote_stack.clear()
        self._crnt_rule = None
        self._crnt_contract = None
        self._crnt_body = None
        self._crnt_type_decl_name = None
        self._crnt_type_decl_span = Span()
        self._crnt_type_decl = None
        self._crnt_type_term = None
        self._current_enum = None
        self._crnt_mod_ref = None
        self._crnt_step = None
        self._crnt_update = None
        self._crnt_mod_ref_state = _ModRefState.Non
        self._crnt_sent_conf = None
        self._is_building_next = False
        self._is_building_update = False
        self._is_building_cod = False

    # -- Numeric parsing ---

    def _parse_numeric(self, s: str, is_fraction: bool = False, span: Span = None) -> Cnst:
        if span is None:
            span = Span()
        try:
            if is_fraction:
                val = Fraction(s)
            else:
                val = Fraction(s)
        except (ValueError, ZeroDivisionError):
            flag = Flag(
                SeverityKind.Error, span,
                BAD_NUMERIC.format(s), BAD_NUMERIC.code,
                self._parse_result.program.name,
            )
            self._parse_result.add_flag(flag)
            return Cnst(span, Fraction(0))
        return Cnst(span, val)

    def _parse_numeric_value(self, s: str, span: Span = None) -> Fraction:
        if span is None:
            span = Span()
        try:
            return Fraction(s)
        except (ValueError, ZeroDivisionError):
            flag = Flag(
                SeverityKind.Error, span,
                BAD_NUMERIC.format(s), BAD_NUMERIC.code,
                self._parse_result.program.name,
            )
            self._parse_result.add_flag(flag)
            return Fraction(0)

    def _parse_int(self, s: str, span: Span = None) -> int:
        if span is None:
            span = Span()
        try:
            return int(s)
        except ValueError:
            flag = Flag(
                SeverityKind.Error, span,
                BAD_NUMERIC.format(s), BAD_NUMERIC.code,
                self._parse_result.program.name,
            )
            self._parse_result.add_flag(flag)
            return 0

    def _get_string(self, span: Span) -> Cnst:
        return Cnst(span, "".join(self._string_buffer))

    # -- Stack operations ---

    def _push_symbol_id(self) -> None:
        func_name = self._arg_stack.pop()
        assert func_name.node_kind == NodeKind.Id
        self._app_stack.append(_FuncApplyInfo(func_name))

    def _push_symbol_op(self, opcode: OpKind, span: Span) -> None:
        self._app_stack.append(_FuncApplyInfo(opcode, span))

    def _push_symbol_rel(self, opcode: RelKind, span: Span) -> None:
        self._app_stack.append(_RelApplyInfo(opcode, span))

    def _push_compr_symbol(self, span: Span) -> None:
        self._app_stack.append(_ComprApplyInfo(Compr(span)))

    def _push_arg(self, n: Node) -> None:
        self._arg_stack.append(n)

    def _inc_arity(self) -> None:
        if not self._app_stack:
            return
        self._app_stack[-1].inc_arity()

    def _append_quote_run(self, s: str, span: Span) -> None:
        self._quote_stack[-1].add_item(QuoteRun(span, s))

    def _append_quote_escape(self, s: str, span: Span) -> None:
        self._quote_stack[-1].add_item(QuoteRun(span, s[1] if len(s) == 2 else s))

    def _append_unquote(self) -> None:
        self._quote_stack[-1].add_item(self._arg_stack.pop())

    def _push_quote(self, span: Span) -> None:
        self._quote_stack.append(Quote(span))

    def _end_compr_heads(self) -> None:
        compr_info = self._app_stack[-1]
        assert isinstance(compr_info, _ComprApplyInfo)
        for _ in range(compr_info.arity):
            compr_info.comprehension.add_head(self._arg_stack.pop(), False)

    def _pop_quote(self) -> Quote:
        return self._quote_stack.pop()

    def _mk_term(self, arity: int = -1) -> Node:
        func_info = self._app_stack.pop()
        assert isinstance(func_info, _FuncApplyInfo)
        if arity < 0:
            arity = func_info.arity

        if isinstance(func_info.func_name, OpKind):
            data = FuncTerm(func_info.span, func_info.func_name)
        else:
            data = FuncTerm(func_info.span, func_info.func_name)

        for _ in range(arity):
            data.add_arg(self._arg_stack.pop(), False)
        return data

    def _mk_compr(self) -> Compr:
        compr_info = self._app_stack.pop()
        assert isinstance(compr_info, _ComprApplyInfo)
        return compr_info.comprehension

    def _mk_mod_apply(self) -> ModApply:
        mod_info = self._app_stack.pop()
        assert isinstance(mod_info, _ModApplyInfo)
        mod_app = ModApply(mod_info.span, mod_info.mod_ref)
        for _ in range(mod_info.arity):
            mod_app.add_arg(self._arg_stack.pop(), False)
        return mod_app

    # -- Type term and declaration building ---

    def _start_enum(self, span: Span) -> None:
        self._current_enum = Enum(span)

    def _append_enum(self, n: Node) -> None:
        self._current_enum.add_element(n)

    def _append_union(self, n: Node) -> None:
        if self._crnt_type_term is None:
            self._crnt_type_term = n
        elif self._crnt_type_term.node_kind == NodeKind.Union:
            self._crnt_type_term.add_component(n)
        else:
            unn = Union(self._crnt_type_term.span)
            unn.add_component(self._crnt_type_term)
            unn.add_component(n)
            self._crnt_type_term = unn

    def _end_enum(self) -> None:
        if self._crnt_type_term is None:
            self._crnt_type_term = self._current_enum
        elif self._crnt_type_term.node_kind == NodeKind.Union:
            self._crnt_type_term.add_component(self._current_enum)
        else:
            unn = Union(self._crnt_type_term.span)
            unn.add_component(self._crnt_type_term)
            unn.add_component(self._current_enum)
            self._crnt_type_term = unn
        self._current_enum = None

    def _save_type_decl_name(self, name: str, span: Span) -> None:
        self._crnt_type_decl_name = name
        self._crnt_type_decl_span = span

    def _end_unn_decl(self) -> None:
        unn_decl = UnnDecl(self._crnt_type_decl_span, self._crnt_type_decl_name, self._crnt_type_term)
        self._crnt_type_term = None
        self._crnt_type_decl_name = None
        self._crnt_type_decl_span = Span()

        if self._current_module.node_kind == NodeKind.Domain:
            self._current_module.add_type_decl(unn_decl)
        elif self._current_module.node_kind == NodeKind.Transform:
            self._current_module.add_type_decl(unn_decl)

        if self._crnt_sent_conf is not None:
            unn_decl.set_config(self._crnt_sent_conf)
            self._crnt_sent_conf = None

    def _start_con_decl(self, is_new: bool, is_sub: bool) -> None:
        self._crnt_type_decl = ConDecl(self._crnt_type_decl_span, self._crnt_type_decl_name, is_new, is_sub)
        if self._crnt_sent_conf is not None:
            self._crnt_type_decl.set_config(self._crnt_sent_conf)
            self._crnt_sent_conf = None

    def _start_map_decl(self, kind: MapKind) -> None:
        self._crnt_type_decl = MapDecl(self._crnt_type_decl_span, self._crnt_type_decl_name, kind, True)
        if self._crnt_sent_conf is not None:
            self._crnt_type_decl.set_config(self._crnt_sent_conf)
            self._crnt_sent_conf = None

    def _end_type_decl(self) -> None:
        if self._current_module.node_kind == NodeKind.Domain:
            self._current_module.add_type_decl(self._crnt_type_decl)
        elif self._current_module.node_kind == NodeKind.Transform:
            self._current_module.add_type_decl(self._crnt_type_decl)
        self._is_building_cod = False
        self._crnt_type_decl = None

    def _save_map_partiality(self, is_partial: bool) -> None:
        self._crnt_type_decl.is_partial = is_partial
        self._is_building_cod = True

    def _set_mod_ref_state(self, state: int) -> None:
        self._crnt_mod_ref_state = state

    def _append_field(self, name: Optional[str], is_any: bool, span: Span) -> None:
        fld = Field(span, name, self._crnt_type_term, is_any)
        self._crnt_type_term = None
        if self._crnt_type_decl.node_kind == NodeKind.ConDecl:
            self._crnt_type_decl.add_field(fld)
        elif self._crnt_type_decl.node_kind == NodeKind.MapDecl:
            if self._is_building_cod:
                self._crnt_type_decl.add_cod_field(fld)
            else:
                self._crnt_type_decl.add_dom_field(fld)

    def _set_compose(self, kind: ComposeKind) -> None:
        self._current_module.set_compose(kind)

    def _append_mod_ref(self, mod_ref: ModRef) -> None:
        self._crnt_mod_ref = mod_ref
        state = self._crnt_mod_ref_state
        if state == _ModRefState.Input:
            nk = self._current_module.node_kind
            if nk == NodeKind.Transform:
                self._current_module.add_input(Param(mod_ref.span, None, mod_ref))
            elif nk == NodeKind.TSystem:
                self._current_module.add_input(Param(mod_ref.span, None, mod_ref))
            elif nk == NodeKind.Machine:
                self._current_module.add_input(Param(mod_ref.span, None, mod_ref))
            elif nk == NodeKind.Model:
                self._current_module.add_compose(mod_ref)
        elif state == _ModRefState.Output:
            nk = self._current_module.node_kind
            if nk == NodeKind.Transform:
                self._current_module.add_output(Param(mod_ref.span, None, mod_ref))
            elif nk == NodeKind.TSystem:
                self._current_module.add_output(Param(mod_ref.span, None, mod_ref))
        elif state == _ModRefState.Other:
            nk = self._current_module.node_kind
            if nk == NodeKind.Domain:
                self._current_module.add_compose(mod_ref)
            elif nk == NodeKind.Model:
                self._current_module.set_domain(mod_ref)
            elif nk == NodeKind.Machine:
                self._current_module.add_state_domain(mod_ref)
        elif state == _ModRefState.ModApply:
            self._app_stack.append(_ModApplyInfo(mod_ref))

    def _append_param(self, name: str, span: Span) -> None:
        state = self._crnt_mod_ref_state
        if state == _ModRefState.Input:
            nk = self._current_module.node_kind
            if nk == NodeKind.Transform:
                self._current_module.add_input(Param(span, name, self._crnt_type_term))
            elif nk == NodeKind.TSystem:
                self._current_module.add_input(Param(span, name, self._crnt_type_term))
            elif nk == NodeKind.Machine:
                self._current_module.add_input(Param(span, name, self._crnt_type_term))
        elif state == _ModRefState.Output:
            nk = self._current_module.node_kind
            if nk == NodeKind.Transform:
                self._current_module.add_output(Param(span, name, self._crnt_type_term))
            elif nk == NodeKind.TSystem:
                self._current_module.add_output(Param(span, name, self._crnt_type_term))
        self._crnt_type_term = None

    def _start_domain(self, name: str, kind: ComposeKind, span: Span) -> None:
        dom = Domain(span, name, kind)
        self._parse_result.program.add_module(dom)
        self._current_module = dom
        self._crnt_mod_ref_state = _ModRefState.Other

    def _end_module(self) -> None:
        self._current_module = None
        self._crnt_mod_ref_state = _ModRefState.Non

    def _start_transform(self, name: str, span: Span) -> None:
        trans = Transform(span, name)
        self._parse_result.program.add_module(trans)
        self._crnt_mod_ref_state = _ModRefState.Input
        self._current_module = trans

    def _start_tsystem(self, name: str, span: Span) -> None:
        tsys = TSystem(span, name)
        self._parse_result.program.add_module(tsys)
        self._crnt_mod_ref_state = _ModRefState.Input
        self._current_module = tsys

    def _start_model(self, name: str, is_partial: bool, span: Span) -> None:
        self._current_module = Model(span, name, is_partial)
        self._parse_result.program.add_module(self._current_module)
        self._crnt_mod_ref_state = _ModRefState.Other

    def _start_machine(self, name: str, span: Span) -> None:
        mach = Machine(span, name)
        self._parse_result.program.add_module(mach)
        self._current_module = mach
        self._crnt_mod_ref_state = _ModRefState.Input

    def _start_sentence_config(self, span: Span) -> None:
        self._crnt_sent_conf = Config(span)

    def _append_setting(self) -> None:
        value = self._arg_stack.pop()
        assert value.node_kind == NodeKind.Cnst
        setting_id = self._arg_stack.pop()
        assert setting_id.node_kind == NodeKind.Id

        if self._current_module is None:
            self._parse_result.program.config.add_setting(Setting(setting_id.span, setting_id, value))
            return
        elif self._crnt_sent_conf is not None:
            self._crnt_sent_conf.add_setting(Setting(setting_id.span, setting_id, value))
            return

        nk = self._current_module.node_kind
        if nk in (NodeKind.Model, NodeKind.Domain, NodeKind.Transform, NodeKind.TSystem, NodeKind.Machine):
            self._current_module.config.add_setting(Setting(setting_id.span, setting_id, value))

    def _start_prop_contract(self, kind: ContractKind, span: Span) -> None:
        self._crnt_contract = ContractItem(span, kind)
        nk = self._current_module.node_kind
        if nk == NodeKind.Model:
            self._current_module.add_contract(self._crnt_contract)
        elif nk == NodeKind.Transform:
            self._current_module.add_contract(self._crnt_contract)
        elif nk == NodeKind.Domain:
            self._current_module.add_conforms(self._crnt_contract)

        if self._crnt_sent_conf is not None:
            self._crnt_contract.set_config(self._crnt_sent_conf)
            self._crnt_sent_conf = None

    def _append_card_contract(self, kind_str: str, cardinality: int, span: Span) -> None:
        if cardinality < 0:
            flag = Flag(
                SeverityKind.Error, span,
                BAD_NUMERIC.format(cardinality), BAD_NUMERIC.code,
                self._parse_result.program.name,
            )
            self._parse_result.add_flag(flag)
            cardinality = 0
        ci = ContractItem(span, self._to_contract_kind(kind_str))
        ci.add_specification(CardPair(span, self._arg_stack.pop(), cardinality))
        if self._current_module.node_kind == NodeKind.Model:
            self._current_module.add_contract(ci)
        if self._crnt_sent_conf is not None:
            ci.set_config(self._crnt_sent_conf)
            self._crnt_sent_conf = None

    def _append_fact(self, p: ModelFact) -> None:
        self._current_module.add_fact(p)

    def _append_step(self) -> None:
        self._crnt_step.set_rhs(self._arg_stack.pop())
        if self._current_module.node_kind == NodeKind.TSystem:
            self._current_module.add_step(self._crnt_step)
        elif self._current_module.node_kind == NodeKind.Machine:
            self._current_module.add_boot_step(self._crnt_step)
        self._crnt_step = None

    def _append_choice(self) -> None:
        self._crnt_update.add_choice(self._arg_stack.pop())

    def _append_lhs(self) -> None:
        id_node = self._arg_stack.pop()
        if self._is_building_update:
            if self._crnt_update is None:
                self._crnt_update = Update(id_node.span)
                if self._crnt_sent_conf is not None:
                    self._crnt_update.set_config(self._crnt_sent_conf)
                    self._crnt_sent_conf = None
            self._crnt_update.add_state(id_node)
        else:
            if self._crnt_step is None:
                self._crnt_step = Step(id_node.span)
                if self._crnt_sent_conf is not None:
                    self._crnt_step.set_config(self._crnt_sent_conf)
                    self._crnt_sent_conf = None
            self._crnt_step.add_lhs(id_node)

    def _append_constraint(self, n: Node) -> None:
        if self._app_stack and isinstance(self._app_stack[-1], _ComprApplyInfo):
            cmpr_info = self._app_stack[-1]
            if cmpr_info.current_body is None:
                cmpr_info.current_body = Body(n.span)
            cmpr_info.current_body.add_constraint(n)
        else:
            if self._crnt_body is None:
                self._crnt_body = Body(n.span)
            self._crnt_body.add_constraint(n)

    def _mk_find(self, is_bound: bool, span: Span) -> Find:
        match = self._arg_stack.pop()
        binding = self._arg_stack.pop() if is_bound else None
        return Find(span, binding, match)

    def _mk_fact(self, is_bound: bool, span: Span) -> ModelFact:
        match = self._arg_stack.pop()
        binding = self._arg_stack.pop() if is_bound else None
        mf = ModelFact(span, binding, match)
        if self._crnt_sent_conf is not None:
            mf.set_config(self._crnt_sent_conf)
            self._crnt_sent_conf = None
        return mf

    def _mk_rel_constr(self) -> RelConstr:
        app = self._app_stack.pop()
        assert isinstance(app, _RelApplyInfo)
        arg2 = self._arg_stack.pop()
        arg1 = self._arg_stack.pop()
        return RelConstr(app.span, app.opcode, arg1, arg2)

    def _mk_no_constr(self, span: Span) -> RelConstr:
        return RelConstr(span, RelKind.No, self._arg_stack.pop())

    def _mk_no_constr_with_binding(self, span: Span, has_binding: bool) -> RelConstr:
        compr = Compr(span)
        body = Body(span)
        if has_binding:
            arg = self._arg_stack.pop()
            binding = self._arg_stack.pop()
        else:
            binding = None
            arg = self._arg_stack.pop()
        body.add_constraint(Find(span, binding, arg))
        compr.add_body(body)
        compr.add_head(Id(span, ASTSchema.get_instance().const_name_true))
        return RelConstr(span, RelKind.No, compr)

    def _end_heads(self, span: Span) -> None:
        self._crnt_rule = Rule(span)
        while self._arg_stack:
            self._crnt_rule.add_head(self._arg_stack.pop(), False)
        if self._crnt_sent_conf is not None:
            self._crnt_rule.set_config(self._crnt_sent_conf)
            self._crnt_sent_conf = None

    @staticmethod
    def _to_contract_kind(s: str) -> ContractKind:
        if s == "some":
            return ContractKind.RequiresSome
        elif s == "atleast":
            return ContractKind.RequiresAtLeast
        elif s == "atmost":
            return ContractKind.RequiresAtMost
        raise ValueError(f"Unknown contract kind: {s}")

    def _append_body(self) -> None:
        if self._app_stack and isinstance(self._app_stack[-1], _ComprApplyInfo):
            app_info = self._app_stack[-1]
            assert app_info.current_body is not None
            app_info.comprehension.add_body(app_info.current_body)
            app_info.current_body = None
        elif self._crnt_rule is not None:
            assert self._crnt_body is not None
            self._crnt_rule.add_body(self._crnt_body)
            self._crnt_body = None
        elif self._crnt_contract is not None:
            assert self._crnt_body is not None
            self._crnt_contract.add_specification(self._crnt_body)
            self._crnt_body = None

    def _append_rule(self) -> None:
        if self._current_module.node_kind == NodeKind.Domain:
            self._current_module.add_rule(self._crnt_rule)
        elif self._current_module.node_kind == NodeKind.Transform:
            self._current_module.add_rule(self._crnt_rule)
        self._crnt_rule = None

    # -- String utilities ---

    def _get_single_string(self, s: str) -> str:
        result = []
        arr = s[1:-1]  # Strip surrounding quotes
        i = 0
        while i < len(arr):
            c = arr[i]
            if c == '\\' and i < len(arr) - 1:
                i += 1
                nxt = arr[i]
                if nxt == 'r':
                    result.append('\r')
                elif nxt == 'n':
                    result.append('\n')
                elif nxt == 't':
                    result.append('\t')
                else:
                    result.append(nxt)
            else:
                result.append(c)
            i += 1
        return "".join(result)

    # ===================================================================
    # ANTLR visitor methods
    # ===================================================================

    def visitProgram(self, ctx: FormulaParser.ProgramContext):
        if ctx.config():
            self.visitConfig(ctx.config())
        if ctx.moduleList():
            self.visitModuleList(ctx.moduleList())
        return None

    def visitConfig(self, ctx: FormulaParser.ConfigContext):
        self.visitSettingList(ctx.settingList())
        return None

    def visitSettingList(self, ctx: FormulaParser.SettingListContext):
        self.visitSetting(ctx.setting())
        if ctx.settingList():
            self.visitSettingList(ctx.settingList())
        return None

    def visitSetting(self, ctx: FormulaParser.SettingContext):
        self.visitId(ctx.id_())
        self.visitConstant(ctx.constant())
        self._append_setting()
        return None

    def visitModuleList(self, ctx: FormulaParser.ModuleListContext):
        for module in ctx.module():
            self.visitModule(module)
            self._end_module()
        return None

    def visitModule(self, ctx: FormulaParser.ModuleContext):
        if ctx.domain():
            self.visitDomain(ctx.domain())
        elif ctx.model():
            self.visitModel(ctx.model())
        elif ctx.transform():
            self.visitTransform(ctx.transform())
        elif ctx.tSystem():
            self.visitTSystem(ctx.tSystem())
        else:
            self.visitMachine(ctx.machine())
        return None

    def visitDomain(self, ctx: FormulaParser.DomainContext):
        self.visitDomainSigConfig(ctx.domainSigConfig())
        if ctx.domSentences():
            self.visitDomSentences(ctx.domSentences())
        return None

    def visitDomainSigConfig(self, ctx: FormulaParser.DomainSigConfigContext):
        self.visitDomainSig(ctx.domainSig())
        if ctx.config():
            self.visitConfig(ctx.config())
        return None

    def visitDomainSig(self, ctx: FormulaParser.DomainSigContext):
        dom_name = ctx.BAREID().getText()
        if ctx.EXTENDS():
            compose_kind = ComposeKind.Extends
        elif ctx.INCLUDES():
            compose_kind = ComposeKind.Includes
        else:
            compose_kind = ComposeKind.Non
        self._start_domain(dom_name, compose_kind, self._to_span(ctx.start))
        if ctx.modRefs():
            self.visitModRefs(ctx.modRefs())
        return None

    def visitDomSentences(self, ctx: FormulaParser.DomSentencesContext):
        self.visitDomSentenceConfig(ctx.domSentenceConfig())
        if ctx.domSentences():
            self.visitDomSentences(ctx.domSentences())
        return None

    def visitDomSentenceConfig(self, ctx: FormulaParser.DomSentenceConfigContext):
        if ctx.sentenceConfig():
            self.visitSentenceConfig(ctx.sentenceConfig())
        self.visitDomSentence(ctx.domSentence())
        return None

    def visitDomSentence(self, ctx: FormulaParser.DomSentenceContext):
        if ctx.ruleItem():
            self.visitRuleItem(ctx.ruleItem())
        elif ctx.typeDecl():
            self.visitTypeDecl(ctx.typeDecl())
        else:
            self._start_prop_contract(ContractKind.ConformsProp, self._to_span(ctx.start))
            self.visitBodyList(ctx.bodyList())
        return None

    def visitModel(self, ctx: FormulaParser.ModelContext):
        self.visitModelSigConfig(ctx.modelSigConfig())
        if ctx.modelBody():
            self.visitModelBody(ctx.modelBody())
        return None

    def visitModelSigConfig(self, ctx: FormulaParser.ModelSigConfigContext):
        self.visitModelSig(ctx.modelSig())
        self._set_mod_ref_state(_ModRefState.Non)
        if ctx.config():
            self.visitConfig(ctx.config())
        return None

    def visitModelSig(self, ctx: FormulaParser.ModelSigContext):
        self.visitModelIntro(ctx.modelIntro())
        if ctx.INCLUDES():
            self._set_compose(ComposeKind.Includes)
            self._set_mod_ref_state(_ModRefState.Input)
            self.visitModRefs(ctx.modRefs())
        elif ctx.EXTENDS():
            self._set_compose(ComposeKind.Extends)
            self._set_mod_ref_state(_ModRefState.Input)
            self.visitModRefs(ctx.modRefs())
        return None

    def visitModelIntro(self, ctx: FormulaParser.ModelIntroContext):
        name = ctx.BAREID().getText()
        partial = False
        span = self._to_span(ctx.MODEL().symbol)
        if ctx.PARTIAL():
            partial = True
            span = self._to_span(ctx.PARTIAL().symbol)
        self._start_model(name, partial, span)
        self.visitModRef(ctx.modRef())
        return None

    def visitModelBody(self, ctx: FormulaParser.ModelBodyContext):
        for sentence in ctx.modelSentence():
            self.visitModelSentence(sentence)
        return None

    def visitModelSentence(self, ctx: FormulaParser.ModelSentenceContext):
        if ctx.modelFactList():
            self.visitModelFactList(ctx.modelFactList())
        else:
            self.visitModelContractConf(ctx.modelContractConf())
        return None

    def visitModelFactList(self, ctx: FormulaParser.ModelFactListContext):
        if ctx.sentenceConfig():
            self.visitSentenceConfig(ctx.sentenceConfig())
        self.visitModelFact(ctx.modelFact())
        if ctx.modelFactList():
            self.visitModelFactList(ctx.modelFactList())
        return None

    def visitModelFact(self, ctx: FormulaParser.ModelFactContext):
        if ctx.IS():
            self._push_arg(Id(self._to_span(ctx.BAREID().symbol), ctx.BAREID().getText()))
            self.visitFuncTerm(ctx.funcTerm())
            self._append_fact(self._mk_fact(True, self._to_span(ctx.BAREID().symbol)))
        else:
            self.visitFuncTerm(ctx.funcTerm())
            self._append_fact(self._mk_fact(False, self._to_span(ctx.start)))
        return None

    def visitModelContractConf(self, ctx: FormulaParser.ModelContractConfContext):
        if ctx.sentenceConfig():
            self.visitSentenceConfig(ctx.sentenceConfig())
        self.visitModelContract(ctx.modelContract())
        return None

    def visitModelContract(self, ctx: FormulaParser.ModelContractContext):
        if ctx.ENSURES():
            self._start_prop_contract(ContractKind.EnsuresProp, self._to_span(ctx.ENSURES().symbol))
            self.visitBodyList(ctx.bodyList())
        elif ctx.cardSpec():
            self.visitCardSpec(ctx.cardSpec())
            digits = ctx.DIGITS().getText()
            cardspec = ctx.cardSpec().getText()
            self.visitId(ctx.id_())
            self._append_card_contract(
                cardspec,
                self._parse_int(digits, self._to_span(ctx.DIGITS().symbol)),
                self._to_span(ctx.REQUIRES().symbol),
            )
        else:
            self._start_prop_contract(ContractKind.RequiresProp, self._to_span(ctx.REQUIRES().symbol))
            self.visitBodyList(ctx.bodyList())
        return None

    def visitTransform(self, ctx: FormulaParser.TransformContext):
        name = ctx.BAREID().getText()
        self._start_transform(name, self._to_span(ctx.TRANSFORM().symbol))
        self.visitTransformRest(ctx.transformRest())
        return None

    def visitTransformRest(self, ctx: FormulaParser.TransformRestContext):
        self.visitTransformSigConfig(ctx.transformSigConfig())
        if ctx.transBody():
            self.visitTransBody(ctx.transBody())
        return None

    def visitTransBody(self, ctx: FormulaParser.TransBodyContext):
        self.visitTransSentenceConfig(ctx.transSentenceConfig())
        if ctx.transBody():
            self.visitTransBody(ctx.transBody())
        return None

    def visitTransSentenceConfig(self, ctx: FormulaParser.TransSentenceConfigContext):
        if ctx.sentenceConfig():
            self.visitSentenceConfig(ctx.sentenceConfig())
        self.visitTransSentence(ctx.transSentence())
        return None

    def visitTransSentence(self, ctx: FormulaParser.TransSentenceContext):
        if ctx.ruleItem():
            self.visitRuleItem(ctx.ruleItem())
        elif ctx.typeDecl():
            self.visitTypeDecl(ctx.typeDecl())
        elif ctx.ENSURES():
            self._start_prop_contract(ContractKind.EnsuresProp, self._to_span(ctx.ENSURES().symbol))
            self.visitBodyList(ctx.bodyList())
        else:
            self._start_prop_contract(ContractKind.RequiresProp, self._to_span(ctx.REQUIRES().symbol))
            self.visitBodyList(ctx.bodyList())
        return None

    def visitTransformSigConfig(self, ctx: FormulaParser.TransformSigConfigContext):
        self.visitTransformSig(ctx.transformSig())
        self._set_mod_ref_state(_ModRefState.Non)
        if ctx.config():
            self.visitConfig(ctx.config())
        return None

    def visitTransformSig(self, ctx: FormulaParser.TransformSigContext):
        self.visitTransSigIn(ctx.transSigIn())
        self._set_mod_ref_state(_ModRefState.Output)
        self.visitModelParamList(ctx.modelParamList())
        return None

    def visitModelParamList(self, ctx: FormulaParser.ModelParamListContext):
        self.visitModRefRename(ctx.modRefRename())
        if ctx.modelParamList():
            self.visitModelParamList(ctx.modelParamList())
        return None

    def visitTransSigIn(self, ctx: FormulaParser.TransSigInContext):
        if ctx.vomParamList():
            self.visitVomParamList(ctx.vomParamList())
        return None

    def visitVomParamList(self, ctx: FormulaParser.VomParamListContext):
        self.visitValOrModelParam(ctx.valOrModelParam())
        if ctx.vomParamList():
            self.visitVomParamList(ctx.vomParamList())
        return None

    def visitValOrModelParam(self, ctx: FormulaParser.ValOrModelParamContext):
        if ctx.unnBody():
            self.visitUnnBody(ctx.unnBody())
            self._append_param(ctx.BAREID().getText(), self._to_span(ctx.BAREID().symbol))
        else:
            self.visitModRefRename(ctx.modRefRename())
        return None

    def visitTSystem(self, ctx: FormulaParser.TSystemContext):
        self._start_tsystem(ctx.BAREID().getText(), self._to_span(ctx.TRANSFORM().symbol))
        self.visitTSystemRest(ctx.tSystemRest())
        return None

    def visitTSystemRest(self, ctx: FormulaParser.TSystemRestContext):
        self.visitTransformSigConfig(ctx.transformSigConfig())
        if ctx.transSteps():
            self._is_building_update = False
            self._set_mod_ref_state(_ModRefState.ModApply)
            self.visitTransSteps(ctx.transSteps())
        return None

    def visitTransSteps(self, ctx: FormulaParser.TransStepsContext):
        self.visitTransStepConfig(ctx.transStepConfig())
        if ctx.transSteps():
            self.visitTransSteps(ctx.transSteps())
        return None

    def visitTransStepConfig(self, ctx: FormulaParser.TransStepConfigContext):
        if ctx.sentenceConfig():
            self.visitSentenceConfig(ctx.sentenceConfig())
        self.visitStep(ctx.step())
        return None

    def visitStep(self, ctx: FormulaParser.StepContext):
        self.visitStepOrUpdateLHS(ctx.stepOrUpdateLHS())
        self.visitModApply(ctx.modApply())
        self._append_step()
        return None

    def visitModApply(self, ctx: FormulaParser.ModApplyContext):
        self.visitModRef(ctx.modRef())
        if ctx.modArgList():
            self.visitModArgList(ctx.modArgList())
        self._push_arg(self._mk_mod_apply())
        return None

    def visitModArgList(self, ctx: FormulaParser.ModArgListContext):
        self.visitModAppArg(ctx.modAppArg())
        self._inc_arity()
        if ctx.modArgList():
            self.visitModArgList(ctx.modArgList())
        return None

    def visitModAppArg(self, ctx: FormulaParser.ModAppArgContext):
        if ctx.funcTerm():
            self.visitFuncTerm(ctx.funcTerm())
        else:
            self._push_arg(ModRef(
                self._to_span(ctx.BAREID().symbol),
                ctx.BAREID().getText(),
                None,
                self._get_single_string(ctx.str_().getText()),
            ))
        return None

    def visitStepOrUpdateLHS(self, ctx: FormulaParser.StepOrUpdateLHSContext):
        self.visitId(ctx.id_())
        self._append_lhs()
        if ctx.stepOrUpdateLHS():
            self.visitStepOrUpdateLHS(ctx.stepOrUpdateLHS())
        return None

    def visitMachine(self, ctx: FormulaParser.MachineContext):
        self.visitMachineSigConfig(ctx.machineSigConfig())
        if ctx.machineBody():
            self.visitMachineBody(ctx.machineBody())
        return None

    def visitMachineSigConfig(self, ctx):
        self.visitMachineSig(ctx.machineSig())
        if ctx.config():
            self.visitConfig(ctx.config())
        return None

    def visitMachineSig(self, ctx):
        name = ctx.BAREID().getText()
        self._start_machine(name, self._to_span(ctx.MACHINE().symbol))
        self.visitMachineSigIn(ctx.machineSigIn())
        self._set_mod_ref_state(_ModRefState.Other)
        self.visitModRefs(ctx.modRefs())
        return None

    def visitMachineSigIn(self, ctx):
        if ctx.vomParamList():
            self.visitVomParamList(ctx.vomParamList())
        return None

    def visitMachineBody(self, ctx):
        for sentence in ctx.machineSentenceConf():
            self.visitMachineSentenceConf(sentence)
        return None

    def visitMachineSentenceConf(self, ctx):
        if ctx.sentenceConfig():
            self.visitSentenceConfig(ctx.sentenceConfig())
        self.visitMachineSentence(ctx.machineSentence())
        return None

    def visitMachineSentence(self, ctx):
        if ctx.machineProp():
            self.visitMachineProp(ctx.machineProp())
        elif ctx.BOOT():
            self._set_mod_ref_state(_ModRefState.ModApply)
            self._is_building_update = False
            self.visitStep(ctx.step())
        elif ctx.INITIALLY():
            self._set_mod_ref_state(_ModRefState.ModApply)
            self._is_building_update = True
            self.visitUpdate(ctx.update())
        elif ctx.NEXT():
            self._set_mod_ref_state(_ModRefState.ModApply)
            self._is_building_update = True
            self._is_building_next = True
            self.visitUpdate(ctx.update())
        return None

    def visitMachineProp(self, ctx):
        name = ctx.BAREID().getText()
        self.visitFuncTerm(ctx.funcTerm())
        defn = self._arg_stack.pop()
        prop = Property(self._to_span(ctx.BAREID().symbol), name, defn)
        if self._crnt_sent_conf is not None:
            prop.set_config(self._crnt_sent_conf)
            self._crnt_sent_conf = None
        self._current_module.add_property(prop)
        return None

    def visitUpdate(self, ctx):
        self.visitStepOrUpdateLHS(ctx.stepOrUpdateLHS())
        self.visitChoiceList(ctx.choiceList())
        if self._is_building_next:
            self._current_module.add_update(self._crnt_update, is_initial=False)
        else:
            self._current_module.add_update(self._crnt_update, is_initial=True)
        self._crnt_update = None
        self._is_building_next = False
        return None

    def visitChoiceList(self, ctx):
        self.visitModApply(ctx.modApply())
        self._append_choice()
        if ctx.choiceList():
            self.visitChoiceList(ctx.choiceList())
        return None

    # -- Type declarations --

    def visitTypeDecl(self, ctx: FormulaParser.TypeDeclContext):
        name = ctx.BAREID().getText()
        self._save_type_decl_name(name, self._to_span(ctx.start))
        self.visitTypeDeclBody(ctx.typeDeclBody())
        return None

    def visitTypeDeclBody(self, ctx: FormulaParser.TypeDeclBodyContext):
        if ctx.unnBody():
            self.visitUnnBody(ctx.unnBody())
            self._end_unn_decl()
        elif ctx.SUB():
            self._start_con_decl(False, True)
            self.visitFields(ctx.fields(0))
            self._end_type_decl()
        elif ctx.NEW():
            self._start_con_decl(True, False)
            self.visitFields(ctx.fields(0))
            self._end_type_decl()
        elif ctx.funDecl():
            self.visitFunDecl(ctx.funDecl())
            self.visitFields(ctx.fields(0))
            self.visitMapArrow(ctx.mapArrow())
            self.visitFields(ctx.fields(1))
            self._end_type_decl()
        else:
            self._start_con_decl(False, False)
            self.visitFields(ctx.fields(0))
            self._end_type_decl()
        return None

    def visitFunDecl(self, ctx: FormulaParser.FunDeclContext):
        if ctx.INJ():
            self._start_map_decl(MapKind.Inj)
        elif ctx.BIJ():
            self._start_map_decl(MapKind.Bij)
        elif ctx.SUR():
            self._start_map_decl(MapKind.Sur)
        else:
            self._start_map_decl(MapKind.Fun)
        return None

    def visitFields(self, ctx: FormulaParser.FieldsContext):
        self.visitField(ctx.field())
        if ctx.fields():
            self.visitFields(ctx.fields())
        return None

    def visitField(self, ctx: FormulaParser.FieldContext):
        if ctx.BAREID():
            if ctx.ANY():
                self.visitUnnBody(ctx.unnBody())
                self._append_field(ctx.BAREID().getText(), True, self._to_span(ctx.start))
            else:
                self.visitUnnBody(ctx.unnBody())
                self._append_field(ctx.BAREID().getText(), False, self._to_span(ctx.start))
        elif ctx.ANY():
            self.visitUnnBody(ctx.unnBody())
            self._append_field(None, True, self._to_span(ctx.start))
        else:
            self.visitUnnBody(ctx.unnBody())
            self._append_field(None, False, self._to_span(ctx.start))
        return None

    def visitUnnBody(self, ctx: FormulaParser.UnnBodyContext):
        self.visitUnnCmp(ctx.unnCmp())
        if ctx.unnBody():
            self.visitUnnBody(ctx.unnBody())
        return None

    def visitUnnCmp(self, ctx: FormulaParser.UnnCmpContext):
        if ctx.typeId():
            self.visitTypeId(ctx.typeId())
        else:
            self._start_enum(self._to_span(ctx.start))
            self.visitEnumList(ctx.enumList())
            self._end_enum()
        return None

    def visitTypeId(self, ctx: FormulaParser.TypeIdContext):
        name = ctx.getText()
        self._append_union(Id(self._to_span(ctx.start), name))
        return None

    def visitEnumList(self, ctx: FormulaParser.EnumListContext):
        self.visitEnumCnst(ctx.enumCnst())
        if ctx.enumList():
            self.visitEnumList(ctx.enumList())
        return None

    def visitEnumCnst(self, ctx: FormulaParser.EnumCnstContext):
        if ctx.BAREID():
            self._append_enum(Id(self._to_span(ctx.start), ctx.BAREID().getText()))
        elif ctx.DIGITS():
            digits_list = ctx.DIGITS()
            pre_one = ""
            pre_two = ""
            minus_list = ctx.MINUS()
            minus_count = len(minus_list) if minus_list else 0
            if minus_count > 0:
                pre_one = "-"
                if minus_count == 2:
                    pre_two = "-"
            if ctx.RANGE():
                self._append_enum(Range(
                    self._to_span(ctx.start),
                    self._parse_numeric_value(pre_one + digits_list[0].getText()),
                    self._parse_numeric_value(pre_two + digits_list[1].getText()),
                ))
            else:
                self._append_enum(self._parse_numeric(pre_one + digits_list[0].getText(), False, self._to_span(ctx.start)))
        elif ctx.REAL():
            self._append_enum(self._parse_numeric(ctx.REAL().getText(), False, self._to_span(ctx.start)))
        elif ctx.FRAC():
            self._append_enum(self._parse_numeric(ctx.FRAC().getText(), True, self._to_span(ctx.start)))
        elif ctx.str_():
            self.visitStr(ctx.str_())
            self._append_enum(self._get_string(self._to_span(ctx.start)))
        else:
            self._append_enum(Id(self._to_span(ctx.start), ctx.QUALID().getText()))
        return None

    def visitMapArrow(self, ctx: FormulaParser.MapArrowContext):
        if ctx.WEAKARROW():
            self._save_map_partiality(True)
        else:
            self._save_map_partiality(False)
        return None

    # -- Rules and constraints --

    def visitRuleItem(self, ctx: FormulaParser.RuleItemContext):
        self.visitFuncTermList(ctx.funcTermList())
        self._end_heads(self._to_span(ctx.start))
        if ctx.bodyList():
            self.visitBodyList(ctx.bodyList())
        self._append_rule()
        return None

    def visitBodyList(self, ctx: FormulaParser.BodyListContext):
        self.visitBody(ctx.body())
        self._append_body()
        if ctx.bodyList():
            self.visitBodyList(ctx.bodyList())
        return None

    def visitBody(self, ctx: FormulaParser.BodyContext):
        self.visitConstraint(ctx.constraint())
        if ctx.body():
            self.visitBody(ctx.body())
        return None

    def visitConstraint(self, ctx: FormulaParser.ConstraintContext):
        if ctx.NO():
            if ctx.compr():
                self.visitCompr(ctx.compr())
                self._append_constraint(self._mk_no_constr(self._to_span(ctx.start)))
            elif ctx.IS():
                self.visitId(ctx.id_())
                self.visitFuncTerm(ctx.funcTerm(0))
                self._append_constraint(self._mk_no_constr_with_binding(self._to_span(ctx.start), True))
            else:
                self.visitFuncTerm(ctx.funcTerm(0))
                self._append_constraint(self._mk_no_constr_with_binding(self._to_span(ctx.start), False))
        elif ctx.IS():
            self.visitId(ctx.id_())
            self.visitFuncTerm(ctx.funcTerm(0))
            self._append_constraint(self._mk_find(True, self._to_span(ctx.start)))
        elif ctx.relOp():
            self.visitFuncTerm(ctx.funcTerm(0))
            self.visitRelOp(ctx.relOp())
            self.visitFuncTerm(ctx.funcTerm(1))
            self._append_constraint(self._mk_rel_constr())
        else:
            self.visitFuncTerm(ctx.funcTerm(0))
            self._append_constraint(self._mk_find(False, self._to_span(ctx.start)))
        return None

    def visitCompr(self, ctx: FormulaParser.ComprContext):
        self._push_compr_symbol(self._to_span(ctx.start))
        self.visitFuncTermList(ctx.funcTermList())
        self.visitComprRest(ctx.comprRest())
        return None

    def visitComprRest(self, ctx: FormulaParser.ComprRestContext):
        self._end_compr_heads()
        if ctx.bodyList():
            self.visitBodyList(ctx.bodyList())
        self._push_arg(self._mk_compr())
        return None

    def visitFuncTermList(self, ctx: FormulaParser.FuncTermListContext):
        self.visitFuncOrCompr(ctx.funcOrCompr())
        self._inc_arity()
        if ctx.funcTermList():
            self.visitFuncTermList(ctx.funcTermList())
        return None

    def visitFuncOrCompr(self, ctx: FormulaParser.FuncOrComprContext):
        if ctx.funcTerm():
            self.visitFuncTerm(ctx.funcTerm())
        else:
            self.visitCompr(ctx.compr())
        return None

    def visitFuncTerm(self, ctx: FormulaParser.FuncTermContext):
        if ctx.atom():
            self.visitAtom(ctx.atom())
        elif ctx.MINUS() and ctx.funcTerm(1) is None:
            # Unary negation
            self._push_symbol_op(OpKind.Neg, self._to_span(ctx.start))
            self.visitFuncTerm(ctx.funcTerm(0))
            self._push_arg(self._mk_term(1))
        elif ctx.MUL():
            self.visitFuncTerm(ctx.funcTerm(0))
            self._push_symbol_op(OpKind.Mul, self._to_span(ctx.MUL().symbol))
            self.visitFuncTerm(ctx.funcTerm(1))
            self._push_arg(self._mk_term(2))
        elif ctx.DIV():
            self.visitFuncTerm(ctx.funcTerm(0))
            self._push_symbol_op(OpKind.Div, self._to_span(ctx.DIV().symbol))
            self.visitFuncTerm(ctx.funcTerm(1))
            self._push_arg(self._mk_term(2))
        elif ctx.MOD():
            self.visitFuncTerm(ctx.funcTerm(0))
            self._push_symbol_op(OpKind.Mod, self._to_span(ctx.MOD().symbol))
            self.visitFuncTerm(ctx.funcTerm(1))
            self._push_arg(self._mk_term(2))
        elif ctx.PLUS():
            self.visitFuncTerm(ctx.funcTerm(0))
            self._push_symbol_op(OpKind.Add, self._to_span(ctx.PLUS().symbol))
            self.visitFuncTerm(ctx.funcTerm(1))
            self._push_arg(self._mk_term(2))
        elif ctx.MINUS():
            # Binary subtraction (two funcTerms)
            self.visitFuncTerm(ctx.funcTerm(0))
            self._push_symbol_op(OpKind.Sub, self._to_span(ctx.MINUS().symbol))
            self.visitFuncTerm(ctx.funcTerm(1))
            self._push_arg(self._mk_term(2))
        elif ctx.funcTermList():
            self.visitId(ctx.id_())
            self._push_symbol_id()
            self.visitFuncTermList(ctx.funcTermList())
            self._push_arg(self._mk_term())
        elif ctx.quoteList():
            self._push_quote(self._to_span(ctx.start))
            self.visitQuoteList(ctx.quoteList())
            self._push_arg(self._pop_quote())
        else:
            # Parenthesized expression
            self.visitFuncTerm(ctx.funcTerm(0))
        return None

    def visitQuoteList(self, ctx: FormulaParser.QuoteListContext):
        self.visitQuoteItem(ctx.quoteItem())
        if ctx.quoteList():
            self.visitQuoteList(ctx.quoteList())
        return None

    def visitQuoteItem(self, ctx: FormulaParser.QuoteItemContext):
        if ctx.QRUN():
            self._append_quote_run(ctx.QRUN().getText(), self._to_span(ctx.start))
        elif ctx.QESC():
            self._append_quote_escape(ctx.QESC().getText(), self._to_span(ctx.start))
        else:
            self.visitFuncTerm(ctx.funcTerm())
            self._append_unquote()
        return None

    def visitAtom(self, ctx: FormulaParser.AtomContext):
        if ctx.id_():
            self.visitId(ctx.id_())
        else:
            self.visitConstant(ctx.constant())
        return None

    def visitId(self, ctx: FormulaParser.IdContext):
        if ctx.BAREID():
            id_text = ctx.BAREID().getText()
        else:
            id_text = ctx.QUALID().getText()
        self._push_arg(Id(self._to_span(ctx.start), id_text))
        return None

    def visitConstant(self, ctx: FormulaParser.ConstantContext):
        if ctx.str_():
            self.visitStr(ctx.str_())
            self._push_arg(self._get_string(self._to_span(ctx.start)))
        else:
            is_fraction = ctx.FRAC() is not None
            self._push_arg(self._parse_numeric(ctx.getText(), is_fraction, self._to_span(ctx.start)))
        return None

    def visitRelOp(self, ctx: FormulaParser.RelOpContext):
        span = self._to_span(ctx.start)
        if ctx.EQ():
            kind = RelKind.Eq
        elif ctx.NE():
            kind = RelKind.Neq
        elif ctx.LT():
            kind = RelKind.Lt
        elif ctx.LE():
            kind = RelKind.Le
        elif ctx.GT():
            kind = RelKind.Gt
        elif ctx.GE():
            kind = RelKind.Ge
        elif ctx.COLON():
            kind = RelKind.Typ
        else:
            kind = RelKind.Eq
        self._push_symbol_rel(kind, span)
        return None

    def visitStr(self, ctx: FormulaParser.StrContext):
        self._string_buffer.clear()
        if ctx.STRING():
            s = ctx.STRING().getText()
            arr = s[1:-1]
            i = 0
            while i < len(arr):
                c = arr[i]
                if c == '\\' and i < len(arr) - 1:
                    i += 1
                    nxt = arr[i]
                    if nxt == 'r':
                        self._string_buffer.append('\r')
                    elif nxt == 'n':
                        self._string_buffer.append('\n')
                    elif nxt == 't':
                        self._string_buffer.append('\t')
                    else:
                        self._string_buffer.append(nxt)
                else:
                    self._string_buffer.append(c)
                i += 1
        else:
            s = ctx.STRINGMUL().getText()
            arr = s[2:-2]
            i = 0
            while i < len(arr):
                c = arr[i]
                if c == "'" and i < len(arr) - 3:
                    if arr[i + 1] == "'" and arr[i + 2] == '"' and arr[i + 3] == '"':
                        self._string_buffer.append("'\"")
                        i += 4
                        continue
                    else:
                        self._string_buffer.append("'")
                elif c == '"' and i < len(arr) - 3:
                    if arr[i + 1] == '"' and arr[i + 2] == "'" and arr[i + 3] == "'":
                        self._string_buffer.append("\"'")
                        i += 4
                        continue
                    else:
                        self._string_buffer.append('"')
                else:
                    self._string_buffer.append(c)
                i += 1
        return None

    def visitSentenceConfig(self, ctx: FormulaParser.SentenceConfigContext):
        self._start_sentence_config(self._to_span(ctx.start))
        self.visitSettingList(ctx.settingList())
        return None

    def visitModRefs(self, ctx: FormulaParser.ModRefsContext):
        self.visitModRef(ctx.modRef())
        if ctx.modRefs():
            self.visitModRefs(ctx.modRefs())
        return None

    def visitModRef(self, ctx: FormulaParser.ModRefContext):
        if ctx.modRefRename():
            self.visitModRefRename(ctx.modRefRename())
        else:
            self.visitModRefNoRename(ctx.modRefNoRename())
        return None

    def visitModRefRename(self, ctx: FormulaParser.ModRefRenameContext):
        rename = ctx.BAREID(0).getText()
        name = ctx.BAREID(1).getText()
        loc = None if not ctx.AT() else self._get_single_string(ctx.str_().getText())
        self._append_mod_ref(ModRef(self._to_span(ctx.BAREID(0).symbol), name, rename, loc))
        return None

    def visitModRefNoRename(self, ctx: FormulaParser.ModRefNoRenameContext):
        name = ctx.BAREID().getText()
        loc = None if not ctx.AT() else self._get_single_string(ctx.str_().getText())
        self._append_mod_ref(ModRef(self._to_span(ctx.BAREID().symbol), name, None, loc))
        return None

    def visitCardSpec(self, ctx: FormulaParser.CardSpecContext):
        return None
