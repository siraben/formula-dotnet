"""AST printing utilities for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.Printing (Src/Core/API/Base/Printing.cs).

Provides ``print_node`` which renders a FORMULA AST back into textual
FORMULA source code.
"""

from __future__ import annotations

import io
from fractions import Fraction
from typing import Any, List, Optional, TextIO

from formula.api.constants import (
    CnstKind,
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


def print_node(node: Node, writer: TextIO, indent: int = 0) -> None:
    """Recursively print *node* as FORMULA source to *writer*.

    This is a simplified but faithful port of the C# ``Printing.Print``
    method that dispatches per ``NodeKind``.
    """
    kind = node.node_kind
    _PRINTERS.get(kind, _print_unknown)(node, writer, indent)


def node_to_string(node: Node, indent: int = 0) -> str:
    """Render *node* as FORMULA source and return as a string."""
    buf = io.StringIO()
    print_node(node, buf, indent)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_INDENT_STR = "   "


def _ind(level: int) -> str:
    return _INDENT_STR * level


def _format_rational(val: Fraction) -> str:
    if val.denominator == 1:
        return str(val.numerator)
    return f"{val.numerator}/{val.denominator}"


def _rel_symbol(kind: RelKind) -> str:
    return {
        RelKind.Eq: "=",
        RelKind.Neq: "!=",
        RelKind.Le: "<=",
        RelKind.Lt: "<",
        RelKind.Ge: ">=",
        RelKind.Gt: ">",
        RelKind.Typ: "is",
        RelKind.No: "no",
    }.get(kind, "?")


def _contract_keyword(kind: ContractKind) -> str:
    return {
        ContractKind.ConformsProp: "conforms",
        ContractKind.EnsuresProp: "ensures",
        ContractKind.RequiresProp: "requires",
        ContractKind.RequiresSome: "some",
        ContractKind.RequiresAtLeast: "atleast",
        ContractKind.RequiresAtMost: "atmost",
    }.get(kind, "?")


def _map_kind_keyword(kind: MapKind) -> str:
    return {
        MapKind.Fun: "fun",
        MapKind.Inj: "inj",
        MapKind.Bij: "bij",
        MapKind.Sur: "sur",
    }.get(kind, "fun")


def _compose_keyword(kind: ComposeKind) -> str:
    if kind == ComposeKind.Includes:
        return "includes"
    if kind == ComposeKind.Extends:
        return "extends"
    return ""


# ---------------------------------------------------------------------------
# Per-NodeKind printers
# ---------------------------------------------------------------------------

def _print_program(node: Program, writer: TextIO, indent: int) -> None:
    if node.config and node.config.settings:
        _print_config(node.config, writer, indent)
        writer.write("\n")
    for mod in node.modules:
        print_node(mod, writer, indent)


def _print_folder(node: Folder, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}//// Folder {node.name}\n")
    for child in node.children:
        print_node(child, writer, indent + 1)


def _print_domain(node: Domain, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}domain {node.name}")
    if node.compose_kind != ComposeKind.Non and node.compositions:
        writer.write(f" {_compose_keyword(node.compose_kind)}")
        for i, comp in enumerate(node.compositions):
            writer.write(" ")
            _print_mod_ref(comp, writer, 0)
            if i < len(node.compositions) - 1:
                writer.write(",")
    writer.write(f"\n{_ind(indent)}{{\n")
    if node.config and node.config.settings:
        _print_config(node.config, writer, indent + 1)
    for td in node.type_decls:
        print_node(td, writer, indent + 1)
    for rl in node.rules:
        print_node(rl, writer, indent + 1)
    for cf in node.conforms:
        print_node(cf, writer, indent + 1)
    writer.write(f"{_ind(indent)}}}\n\n")


def _print_transform(node: Transform, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}transform {node.name} (")
    for i, inp in enumerate(node.inputs):
        _print_param(inp, writer, 0)
        if i < len(node.inputs) - 1:
            writer.write(", ")
    writer.write(")")
    if node.outputs:
        writer.write(f"\n{_ind(indent)}returns (")
        for i, outp in enumerate(node.outputs):
            _print_param(outp, writer, 0)
            if i < len(node.outputs) - 1:
                writer.write(", ")
        writer.write(")")
    writer.write(f"\n{_ind(indent)}{{\n")
    if node.config and node.config.settings:
        _print_config(node.config, writer, indent + 1)
    for ci in node.contracts:
        print_node(ci, writer, indent + 1)
    for td in node.type_decls:
        print_node(td, writer, indent + 1)
    for rl in node.rules:
        print_node(rl, writer, indent + 1)
    writer.write(f"{_ind(indent)}}}\n\n")


def _print_tsystem(node: TSystem, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}transform system {node.name} (")
    for i, inp in enumerate(node.inputs):
        _print_param(inp, writer, 0)
        if i < len(node.inputs) - 1:
            writer.write(", ")
    writer.write(")")
    if node.outputs:
        writer.write(f"\n{_ind(indent)}returns (")
        for i, outp in enumerate(node.outputs):
            _print_param(outp, writer, 0)
            if i < len(node.outputs) - 1:
                writer.write(", ")
        writer.write(")")
    writer.write(f"\n{_ind(indent)}{{\n")
    if node.config and node.config.settings:
        _print_config(node.config, writer, indent + 1)
    for stp in node.steps:
        print_node(stp, writer, indent + 1)
    writer.write(f"{_ind(indent)}}}\n\n")


def _print_model(node: Model, writer: TextIO, indent: int) -> None:
    prefix = "partial model" if node.is_partial else "model"
    writer.write(f"{_ind(indent)}{prefix} {node.name} of ")
    _print_mod_ref(node.domain, writer, 0)
    if node.compose_kind != ComposeKind.Non and node.compositions:
        writer.write(f" {_compose_keyword(node.compose_kind)}")
        for i, comp in enumerate(node.compositions):
            writer.write(" ")
            _print_mod_ref(comp, writer, 0)
            if i < len(node.compositions) - 1:
                writer.write(",")
    writer.write(f"\n{_ind(indent)}{{\n")
    if node.config and node.config.settings:
        _print_config(node.config, writer, indent + 1)
    for ci in node.contracts:
        print_node(ci, writer, indent + 1)
    for fact in node.facts:
        print_node(fact, writer, indent + 1)
    writer.write(f"{_ind(indent)}}}\n\n")


def _print_machine(node: Machine, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}machine {node.name}")
    if node.state_domains:
        writer.write(" of ")
        for i, sd in enumerate(node.state_domains):
            _print_mod_ref(sd, writer, 0)
            if i < len(node.state_domains) - 1:
                writer.write(", ")
    writer.write(f" (")
    for i, inp in enumerate(node.inputs):
        _print_param(inp, writer, 0)
        if i < len(node.inputs) - 1:
            writer.write(", ")
    writer.write(f")\n{_ind(indent)}{{\n")
    if node.config and node.config.settings:
        _print_config(node.config, writer, indent + 1)
    for stp in node.boot_sequence:
        writer.write(f"{_ind(indent + 1)}boot\n")
        print_node(stp, writer, indent + 2)
    for u in node.initials:
        print_node(u, writer, indent + 1)
    for u in node.nexts:
        print_node(u, writer, indent + 1)
    for prop in node.properties:
        print_node(prop, writer, indent + 1)
    writer.write(f"{_ind(indent)}}}\n\n")


def _print_config(node: Config, writer: TextIO, indent: int) -> None:
    for setting in node.settings:
        _print_setting(setting, writer, indent)


def _print_setting(node: Setting, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}[")
    _print_id(node.key, writer, 0)
    writer.write(" = ")
    _print_cnst(node.value, writer, 0)
    writer.write("]\n")


def _print_mod_ref(node: ModRef, writer: TextIO, indent: int) -> None:
    if node.location:
        writer.write(f"{node.name} at \"{node.location}\"")
    else:
        writer.write(node.name)
    if node.rename:
        writer.write(f" as {node.rename}")


def _print_id(node: Id, writer: TextIO, indent: int) -> None:
    writer.write(node.name)


def _print_cnst(node: Cnst, writer: TextIO, indent: int) -> None:
    if node.cnst_kind == CnstKind.String:
        escaped = node.raw.replace("\\", "\\\\").replace('"', '\\"')
        writer.write(f'"{escaped}"')
    else:
        writer.write(_format_rational(node.raw))


def _print_con_decl(node: ConDecl, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}{node.name} ::= ")
    if node.is_new:
        writer.write("new ")
    if node.is_sub:
        writer.write("sub ")
    writer.write("(")
    fields = node.fields
    for i, fld in enumerate(fields):
        _print_field(fld, writer, 0)
        if i < len(fields) - 1:
            writer.write(", ")
    writer.write(").\n")


def _print_map_decl(node: MapDecl, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}{node.name} ::= ")
    writer.write(f"{_map_kind_keyword(node.map_kind)} (")
    dom_fields = node.dom
    for i, fld in enumerate(dom_fields):
        _print_field(fld, writer, 0)
        if i < len(dom_fields) - 1:
            writer.write(", ")
    writer.write(" -> ")
    cod_fields = node.cod
    for i, fld in enumerate(cod_fields):
        _print_field(fld, writer, 0)
        if i < len(cod_fields) - 1:
            writer.write(", ")
    writer.write(").\n")


def _print_unn_decl(node: UnnDecl, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}{node.name} ::= ")
    _print_type_term(node.body, writer, 0)
    writer.write(".\n")


def _print_field(node: Field, writer: TextIO, indent: int) -> None:
    if node.name:
        writer.write(f"{node.name}: ")
    if node.is_any:
        writer.write("any ")
    _print_type_term(node.type, writer, 0)


def _print_type_term(node: Node, writer: TextIO, indent: int) -> None:
    if node is None:
        writer.write("?")
        return
    if node.node_kind == NodeKind.Id:
        writer.write(node.name)
    elif node.node_kind == NodeKind.Enum:
        writer.write("{")
        elems = node.elements
        for i, elem in enumerate(elems):
            if elem.node_kind == NodeKind.Cnst:
                _print_cnst(elem, writer, 0)
            elif elem.node_kind == NodeKind.Id:
                _print_id(elem, writer, 0)
            elif elem.node_kind == NodeKind.Range:
                _print_range(elem, writer, 0)
            if i < len(elems) - 1:
                writer.write(", ")
        writer.write("}")
    elif node.node_kind == NodeKind.Union:
        components = node.components
        for i, comp in enumerate(components):
            _print_type_term(comp, writer, 0)
            if i < len(components) - 1:
                writer.write(" + ")
    else:
        writer.write("?")


def _print_range(node: Range, writer: TextIO, indent: int) -> None:
    writer.write(f"{_format_rational(node.lower)}..{_format_rational(node.upper)}")


def _print_rule(node: Rule, writer: TextIO, indent: int) -> None:
    writer.write(_ind(indent))
    heads = node.heads
    for i, head in enumerate(heads):
        _print_func_or_atom(head, writer, 0)
        if i < len(heads) - 1:
            writer.write(", ")
    bodies = node.bodies
    if bodies:
        writer.write(" :- ")
        for i, body in enumerate(bodies):
            _print_body(body, writer, 0)
            if i < len(bodies) - 1:
                writer.write("; ")
    writer.write(".\n")


def _print_body(node: Body, writer: TextIO, indent: int) -> None:
    constraints = node.constraints
    for i, constr in enumerate(constraints):
        _print_constraint(constr, writer, 0)
        if i < len(constraints) - 1:
            writer.write(", ")


def _print_constraint(node: Node, writer: TextIO, indent: int) -> None:
    if node.node_kind == NodeKind.Find:
        _print_find(node, writer, indent)
    elif node.node_kind == NodeKind.RelConstr:
        _print_rel_constr(node, writer, indent)
    elif node.node_kind == NodeKind.FuncTerm:
        _print_func_term(node, writer, indent)
    elif node.node_kind == NodeKind.Id:
        _print_id(node, writer, indent)
    elif node.node_kind == NodeKind.Compr:
        _print_compr(node, writer, indent)
    else:
        _print_func_or_atom(node, writer, indent)


def _print_find(node: Find, writer: TextIO, indent: int) -> None:
    if node.binding:
        _print_id(node.binding, writer, 0)
        writer.write(" is ")
    _print_func_or_atom(node.match, writer, 0)


def _print_rel_constr(node: RelConstr, writer: TextIO, indent: int) -> None:
    if node.op == RelKind.No:
        writer.write("no ")
        _print_func_or_atom(node.arg1, writer, 0)
        return
    _print_func_or_atom(node.arg1, writer, 0)
    writer.write(f" {_rel_symbol(node.op)} ")
    if node.arg2 is not None:
        _print_func_or_atom(node.arg2, writer, 0)


def _print_func_term(node: FuncTerm, writer: TextIO, indent: int) -> None:
    func = node.function
    if isinstance(func, OpKind):
        writer.write(func.name.lower())
    else:
        _print_id(func, writer, 0)
    args = node.args
    if args:
        writer.write("(")
        for i, arg in enumerate(args):
            _print_func_or_atom(arg, writer, 0)
            if i < len(args) - 1:
                writer.write(", ")
        writer.write(")")


def _print_func_or_atom(node: Node, writer: TextIO, indent: int) -> None:
    if node.node_kind == NodeKind.FuncTerm:
        _print_func_term(node, writer, indent)
    elif node.node_kind == NodeKind.Id:
        _print_id(node, writer, indent)
    elif node.node_kind == NodeKind.Cnst:
        _print_cnst(node, writer, indent)
    elif node.node_kind == NodeKind.Quote:
        _print_quote(node, writer, indent)
    elif node.node_kind == NodeKind.Compr:
        _print_compr(node, writer, indent)
    else:
        writer.write(f"<{node.node_kind.name}>")


def _print_quote(node: Quote, writer: TextIO, indent: int) -> None:
    writer.write("`")
    for item in node.contents:
        if item.node_kind == NodeKind.QuoteRun:
            writer.write(item.text)
        else:
            writer.write("${")
            _print_func_or_atom(item, writer, 0)
            writer.write("}")
    writer.write("`")


def _print_compr(node: Compr, writer: TextIO, indent: int) -> None:
    writer.write("{")
    heads = node.heads
    for i, head in enumerate(heads):
        _print_func_or_atom(head, writer, 0)
        if i < len(heads) - 1:
            writer.write(", ")
    bodies = node.bodies
    if bodies:
        writer.write(" | ")
        for i, body in enumerate(bodies):
            _print_body(body, writer, 0)
            if i < len(bodies) - 1:
                writer.write("; ")
    writer.write("}")


def _print_model_fact(node: ModelFact, writer: TextIO, indent: int) -> None:
    writer.write(_ind(indent))
    if node.binding:
        _print_id(node.binding, writer, 0)
        writer.write(" is ")
    _print_func_or_atom(node.match, writer, 0)
    writer.write(".\n")


def _print_contract_item(node: ContractItem, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}{_contract_keyword(node.contract_kind)} ")
    specs = node.specification
    for i, spec in enumerate(specs):
        if spec.node_kind == NodeKind.Body:
            _print_body(spec, writer, 0)
        elif spec.node_kind == NodeKind.CardPair:
            _print_card_pair(spec, writer, 0)
        else:
            _print_func_or_atom(spec, writer, 0)
        if i < len(specs) - 1:
            writer.write(", ")
    writer.write(".\n")


def _print_card_pair(node: CardPair, writer: TextIO, indent: int) -> None:
    _print_id(node.type_id, writer, 0)
    writer.write(f" {node.cardinality}")


def _print_step(node: Step, writer: TextIO, indent: int) -> None:
    writer.write(_ind(indent))
    lhs = node.lhs
    if lhs:
        for i, lhs_id in enumerate(lhs):
            _print_id(lhs_id, writer, 0)
            if i < len(lhs) - 1:
                writer.write(", ")
        writer.write(" = ")
    _print_mod_apply(node.rhs, writer, 0)
    writer.write(".\n")


def _print_mod_apply(node: ModApply, writer: TextIO, indent: int) -> None:
    _print_mod_ref(node.module, writer, 0)
    writer.write("(")
    args = node.args
    for i, arg in enumerate(args):
        _print_func_or_atom(arg, writer, 0)
        if i < len(args) - 1:
            writer.write(", ")
    writer.write(")")


def _print_update(node: Update, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}update ")
    for i, state in enumerate(node.states):
        _print_id(state, writer, 0)
        if i < len(node.states) - 1:
            writer.write(", ")
    if node.choices:
        writer.write(" choice ")
        for i, choice in enumerate(node.choices):
            _print_mod_apply(choice, writer, 0)
            if i < len(node.choices) - 1:
                writer.write(", ")
    writer.write(".\n")


def _print_property(node: Property, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}{node.name} = ")
    _print_func_or_atom(node.definition, writer, 0)
    writer.write(".\n")


def _print_param(node: Param, writer: TextIO, indent: int) -> None:
    if node.name:
        writer.write(f"{node.name} :: ")
    type_node = node.type
    if type_node is not None:
        if type_node.node_kind == NodeKind.ModRef:
            _print_mod_ref(type_node, writer, 0)
        else:
            _print_type_term(type_node, writer, 0)


def _print_unknown(node: Node, writer: TextIO, indent: int) -> None:
    writer.write(f"{_ind(indent)}<{node.node_kind.name}>\n")


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_PRINTERS = {
    NodeKind.Program: _print_program,
    NodeKind.Folder: _print_folder,
    NodeKind.Domain: _print_domain,
    NodeKind.Transform: _print_transform,
    NodeKind.TSystem: _print_tsystem,
    NodeKind.Model: _print_model,
    NodeKind.Machine: _print_machine,
    NodeKind.Config: _print_config,
    NodeKind.Setting: _print_setting,
    NodeKind.ModRef: _print_mod_ref,
    NodeKind.Id: _print_id,
    NodeKind.Cnst: _print_cnst,
    NodeKind.ConDecl: _print_con_decl,
    NodeKind.MapDecl: _print_map_decl,
    NodeKind.UnnDecl: _print_unn_decl,
    NodeKind.Field: _print_field,
    NodeKind.Enum: _print_type_term,
    NodeKind.Union: _print_type_term,
    NodeKind.Range: _print_range,
    NodeKind.Rule: _print_rule,
    NodeKind.Body: _print_body,
    NodeKind.Find: _print_find,
    NodeKind.FuncTerm: _print_func_term,
    NodeKind.RelConstr: _print_rel_constr,
    NodeKind.Quote: _print_quote,
    NodeKind.QuoteRun: lambda n, w, i: w.write(n.text),
    NodeKind.Compr: _print_compr,
    NodeKind.ModelFact: _print_model_fact,
    NodeKind.ContractItem: _print_contract_item,
    NodeKind.CardPair: _print_card_pair,
    NodeKind.Step: _print_step,
    NodeKind.ModApply: _print_mod_apply,
    NodeKind.Update: _print_update,
    NodeKind.Property: _print_property,
    NodeKind.Param: _print_param,
}
