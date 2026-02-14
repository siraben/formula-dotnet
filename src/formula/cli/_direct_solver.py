"""Direct Z3 solver for FORMULA specifications.

Walks Domain and partial Model AST nodes, translates conformance
constraints into Z3 assertions, then checks satisfiability.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict, List, Optional, Set, Tuple

import z3

from formula.api.constants import (
    CnstKind,
    ContractKind,
    NodeKind,
    OpKind,
    RelKind,
    SeverityKind,
)
from formula.api.nodes import (
    Body,
    Cnst,
    Compr,
    ConDecl,
    Config,
    ContractItem,
    Domain,
    Field,
    Find,
    FuncTerm,
    Id,
    Model,
    ModelFact,
    Node,
    Range,
    RelConstr,
    Rule,
    Setting,
    UnnDecl,
)


# ── Data structures ──────────────────────────────────────────────

class FieldTypeInfo:
    """Type information for a constructor field, matching C# TypeEmbedder."""
    __slots__ = ("type_name", "range_min", "range_max")

    def __init__(self, type_name: str = "Integer", range_min: Optional[int] = None, range_max: Optional[int] = None):
        self.type_name = type_name
        self.range_min = range_min
        self.range_max = range_max


class CtorInfo:
    """Constructor metadata extracted from domain."""
    __slots__ = ("name", "fields", "is_new")

    def __init__(self, name: str, fields: List[Tuple[Optional[str], FieldTypeInfo]], is_new: bool):
        self.name = name
        self.fields = fields
        self.is_new = is_new

    def field_index(self, field_name: str) -> int:
        for i, (fn, _) in enumerate(self.fields):
            if fn == field_name:
                return i
        return -1


class Ref:
    """Reference to another model fact by binding name."""
    __slots__ = ("target",)

    def __init__(self, target: str):
        self.target = target


class Binding:
    """An instance (model fact or derived) with Z3 field values."""
    __slots__ = ("ctor", "fields", "bname", "cond")

    def __init__(self, ctor: str, fields: list, bname: Optional[str] = None, cond: Any = True):
        self.ctor = ctor
        self.fields = fields
        self.bname = bname
        self.cond = cond


# ── Solver context ───────────────────────────────────────────────

class Ctx:
    """Holds all state for constraint generation."""

    def __init__(self):
        self.ctors: Dict[str, CtorInfo] = {}
        self.base: Dict[str, List[Binding]] = {}
        self.derived: Dict[str, List[Binding]] = {}
        self.by_bname: Dict[str, Binding] = {}
        self.z3_vars: Dict[str, z3.ExprRef] = {}
        self.type_constraints: List[z3.BoolRef] = []
        self.rules_by_head: Dict[str, List[Rule]] = {}

    def all_of(self, ctor: str) -> List[Binding]:
        return list(self.base.get(ctor, [])) + list(self.derived.get(ctor, []))

    def get_field(self, b: Binding, fname: str) -> Any:
        ci = self.ctors.get(b.ctor)
        if ci is None:
            return None
        idx = ci.field_index(fname)
        if idx < 0 or idx >= len(b.fields):
            return None
        v = b.fields[idx]
        if isinstance(v, Ref):
            return self.by_bname.get(v.target)
        return v


# ── Type helpers ──────────────────────────────────────────────────

def _extract_type_info(type_node: Node) -> FieldTypeInfo:
    """Extract type info from a field's type AST node."""
    if isinstance(type_node, Id):
        return FieldTypeInfo(type_node.name)
    if isinstance(type_node, Range):
        return FieldTypeInfo("IntRange", int(type_node.lower), int(type_node.upper))
    return FieldTypeInfo("Any")


def _make_z3_var(name: str, type_info: FieldTypeInfo) -> Tuple[z3.ExprRef, Optional[z3.BoolRef]]:
    """Create a Z3 variable matching C# TypeEmbedder behavior.

    Returns (z3_var, type_constraint_or_None).
    """
    tn = type_info.type_name
    if tn == "Real":
        return z3.Real(name), None
    if tn == "Natural":
        v = z3.Int(name)
        return v, v >= 0
    if tn == "PosInteger":
        v = z3.Int(name)
        return v, v >= 1
    if tn == "NegInteger":
        v = z3.Int(name)
        return v, v < 0
    if tn == "IntRange" and type_info.range_min is not None:
        v = z3.Int(name)
        constraints = [v >= type_info.range_min]
        if type_info.range_max is not None:
            constraints.append(v <= type_info.range_max)
        return v, z3.And(*constraints) if len(constraints) > 1 else constraints[0]
    # Default: Integer (also covers String mapped to Int, etc.)
    return z3.Int(name), None


# ── Context building ─────────────────────────────────────────────

def _build_ctx(domain: Domain, model: Model) -> Ctx:
    ctx = Ctx()

    # Extract constructors
    for td in domain.type_decls:
        if isinstance(td, ConDecl):
            fields = []
            for f in td.fields:
                fields.append((f.name, _extract_type_info(f.type)))
            ctx.ctors[td.name] = CtorInfo(td.name, fields, td.is_new)

    # Add derived ctors from rule heads (if not already declared)
    for rule in domain.rules:
        for h in rule.heads:
            if isinstance(h, FuncTerm) and isinstance(h.function, Id):
                nm = h.function.name
                if nm not in ctx.ctors:
                    ctx.ctors[nm] = CtorInfo(nm, [(None, FieldTypeInfo("Any"))] * len(list(h.args)), False)

    # Index rules by head name
    for rule in domain.rules:
        for h in rule.heads:
            nm = h.name if isinstance(h, Id) else (
                h.function.name if isinstance(h, FuncTerm) and isinstance(h.function, Id) else None
            )
            if nm:
                ctx.rules_by_head.setdefault(nm, []).append(rule)

    # Collect binding names from model
    binding_names: Set[str] = set()
    for fact in model.facts:
        if fact.binding is not None:
            binding_names.add(fact.binding.name)

    # Extract model facts
    for fact in model.facts:
        match = fact.match
        if not (isinstance(match, FuncTerm) and isinstance(match.function, Id)):
            continue

        ctor_name = match.function.name
        bname = fact.binding.name if fact.binding else None
        ci = ctx.ctors.get(ctor_name)
        fields: list = []

        for i, arg in enumerate(match.args):
            if isinstance(arg, Cnst):
                fields.append(_cnst_to_z3(arg))
            elif isinstance(arg, Id):
                nm = arg.name
                if nm in binding_names:
                    fields.append(Ref(nm))
                else:
                    # Symbolic variable - infer type from constructor field
                    fti = FieldTypeInfo("Integer")
                    if ci and i < len(ci.fields):
                        _, fti = ci.fields[i]
                    if nm not in ctx.z3_vars:
                        var, constraint = _make_z3_var(nm, fti)
                        ctx.z3_vars[nm] = var
                        if constraint is not None:
                            ctx.type_constraints.append(constraint)
                    fields.append(ctx.z3_vars[nm])
            else:
                fields.append(None)

        b = Binding(ctor_name, fields, bname)
        ctx.base.setdefault(ctor_name, []).append(b)
        if bname:
            ctx.by_bname[bname] = b

    return ctx


def _cnst_to_z3(node: Cnst) -> Any:
    if node.cnst_kind == CnstKind.Numeric:
        v = node.raw
        if isinstance(v, Fraction):
            return z3.IntVal(int(v)) if v.denominator == 1 else z3.RealVal(float(v))
        if isinstance(v, int):
            return z3.IntVal(v)
        if isinstance(v, float):
            return z3.RealVal(v)
        try:
            return z3.IntVal(int(v))
        except (TypeError, ValueError):
            return z3.RealVal(float(v))
    return z3.StringVal(str(node.raw))


# ── Expression resolution ────────────────────────────────────────

def _resolve(node: Node, env: dict, ctx: Ctx) -> Any:
    """Resolve an AST expression to a Z3 value, Binding, or None."""
    if isinstance(node, Cnst):
        return _cnst_to_z3(node)

    if isinstance(node, Id):
        name = node.name
        if "." in name:
            base_name, field_name = name.split(".", 1)
            base = env.get(base_name)
            if isinstance(base, Binding):
                return ctx.get_field(base, field_name)
            if base_name in ctx.by_bname:
                return ctx.get_field(ctx.by_bname[base_name], field_name)
            return None
        if name in env:
            return env[name]
        if name in ctx.z3_vars:
            return ctx.z3_vars[name]
        return None

    if isinstance(node, FuncTerm):
        fn = node.function
        raw_args = list(node.args)

        if isinstance(fn, OpKind):
            return _eval_op(fn, raw_args, env, ctx)
        if isinstance(fn, Id):
            op_map = {o.name.lower(): o for o in OpKind}
            if fn.name.lower() in op_map:
                return _eval_op(op_map[fn.name.lower()], raw_args, env, ctx)
            if fn.name in ctx.ctors:
                args = [_resolve(a, env, ctx) for a in raw_args]
                return Binding(fn.name, args)
        return None

    return None


def _eval_op(op: OpKind, raw_args: list, env: dict, ctx: Ctx) -> Any:
    if op in (OpKind.Add, OpKind.Sub, OpKind.Mul, OpKind.Div, OpKind.Mod):
        a = _resolve(raw_args[0], env, ctx) if len(raw_args) > 0 else None
        b = _resolve(raw_args[1], env, ctx) if len(raw_args) > 1 else None
        a, b = _coerce(a, b)
        if a is None or b is None:
            return None
        if op == OpKind.Add: return a + b
        if op == OpKind.Sub: return a - b
        if op == OpKind.Mul: return a * b
        if op == OpKind.Div: return a / b
        if op == OpKind.Mod: return a % b

    if op == OpKind.Neg:
        a = _resolve(raw_args[0], env, ctx) if raw_args else None
        return -a if a is not None else None

    if op in (OpKind.Max, OpKind.Min):
        a = _resolve(raw_args[0], env, ctx) if len(raw_args) > 0 else None
        b = _resolve(raw_args[1], env, ctx) if len(raw_args) > 1 else None
        a, b = _coerce(a, b)
        if a is None or b is None:
            return None
        return z3.If(a >= b, a, b) if op == OpKind.Max else z3.If(a <= b, a, b)

    if op == OpKind.Sum:
        return _eval_sum(raw_args, env, ctx)

    if op in (OpKind.Count, OpKind.SymCount):
        return _eval_count(raw_args, env, ctx)

    return None


def _coerce(a: Any, b: Any) -> Tuple[Any, Any]:
    if a is None or b is None:
        return None, None
    if isinstance(a, z3.ArithRef) and isinstance(b, z3.ArithRef):
        a_real = a.sort() == z3.RealSort()
        b_real = b.sort() == z3.RealSort()
        if a_real and not b_real:
            b = z3.ToReal(b)
        elif b_real and not a_real:
            a = z3.ToReal(a)
    return a, b


def _eval_sum(raw_args: list, env: dict, ctx: Ctx) -> Any:
    """sum(init, { head | body })"""
    if len(raw_args) < 2:
        return None
    init = _resolve(raw_args[0], env, ctx)
    compr = raw_args[1]
    if not isinstance(compr, Compr) or not compr.heads or not compr.bodies:
        return init

    head_node = compr.heads[0]
    body = compr.bodies[0]
    total = init

    for benv, cond in _enumerate_body(body, env, ctx):
        merged = dict(env)
        merged.update(benv)
        head_val = _resolve(head_node, merged, ctx)
        if head_val is None or total is None:
            continue
        total_c, head_c = _coerce(total, head_val)
        if total_c is None or head_c is None:
            continue
        if isinstance(cond, z3.BoolRef):
            zero = z3.RealVal(0) if head_c.sort() == z3.RealSort() else z3.IntVal(0)
            total = total_c + z3.If(cond, head_c, zero)
        elif cond is True:
            total = total_c + head_c
        # cond is False → skip

    return total


def _eval_count(raw_args: list, env: dict, ctx: Ctx) -> Any:
    """count({ head | body })"""
    if not raw_args:
        return None
    compr = raw_args[0]
    if not isinstance(compr, Compr) or not compr.bodies:
        return z3.IntVal(0)

    body = compr.bodies[0]
    total = z3.IntVal(0)

    for benv, cond in _enumerate_body(body, env, ctx):
        if isinstance(cond, z3.BoolRef):
            total = total + z3.If(cond, z3.IntVal(1), z3.IntVal(0))
        elif cond is True:
            total = total + z3.IntVal(1)

    return total


# ── Body enumeration & constraint evaluation ─────────────────────

def _enumerate_body(body: Body, outer_env: dict, ctx: Ctx):
    """Enumerate valid bindings for a body, evaluating all constraints.

    Yields (env_dict, condition) where condition is True/z3.BoolRef.
    Entries with condition False are filtered out.
    """
    finds = [c for c in body.constraints if isinstance(c, Find)]
    others = [c for c in body.constraints if not isinstance(c, Find)]

    for find_env, find_cond in _enumerate_finds(finds, outer_env, ctx):
        merged = dict(outer_env)
        merged.update(find_env)

        constraint_cond = _eval_constraints_seq(others, merged, ctx)
        combined = _and(find_cond, constraint_cond)

        if combined is not False:
            yield merged, combined


def _enumerate_finds(finds: list, env: dict, ctx: Ctx):
    """Enumerate all bindings from Find constraints.

    Yields (binding_dict, combined_instance_condition).
    """
    if not finds:
        yield {}, True
        return

    find = finds[0]
    rest = finds[1:]
    match = find.match
    bname = find.binding.name if find.binding else None

    if isinstance(match, Id):
        ctor_name = match.name
        instances = ctx.all_of(ctor_name)
        if not instances:
            return
        for inst in instances:
            entry: dict = {}
            if bname:
                entry[bname] = inst
            for rest_entry, rest_cond in _enumerate_finds(rest, _m(env, entry), ctx):
                combined = _and(inst.cond, rest_cond)
                if combined is not False:
                    yield {**entry, **rest_entry}, combined

    elif isinstance(match, FuncTerm) and isinstance(match.function, Id):
        ctor_name = match.function.name
        pat_args = list(match.args)
        instances = ctx.all_of(ctor_name)
        if not instances:
            return
        for inst in instances:
            entry: dict = {}
            if bname:
                entry[bname] = inst
            ok = True
            merged_check = _m(env, entry)
            for j, pa in enumerate(pat_args):
                if j >= len(inst.fields):
                    ok = False
                    break
                if isinstance(pa, Id):
                    existing = merged_check.get(pa.name) or entry.get(pa.name)
                    if existing is not None:
                        if not _field_matches(existing, inst.fields[j], ctx):
                            ok = False
                            break
                    else:
                        v = inst.fields[j]
                        if isinstance(v, Ref):
                            target = ctx.by_bname.get(v.target)
                            entry[pa.name] = target if target else v
                        else:
                            entry[pa.name] = v
            if not ok:
                continue
            for rest_entry, rest_cond in _enumerate_finds(rest, _m(env, entry), ctx):
                combined = _and(inst.cond, rest_cond)
                if combined is not False:
                    yield {**entry, **rest_entry}, combined
    else:
        for rest_entry, rest_cond in _enumerate_finds(rest, env, ctx):
            yield rest_entry, rest_cond


def _field_matches(bound_val: Any, inst_field: Any, ctx: Ctx) -> bool:
    """Check if a bound value matches an instance field."""
    if isinstance(inst_field, Ref):
        if isinstance(bound_val, Binding):
            return bound_val.bname is not None and bound_val.bname == inst_field.target
        return False
    if isinstance(bound_val, Binding):
        return False
    # Both are Z3 values: assume match (Z3 solver handles equality)
    return True


def _eval_constraints_seq(constraints: list, env: dict, ctx: Ctx) -> Any:
    """Evaluate non-Find constraints sequentially with variable binding.

    When encountering `var = expr` where var is unbound, binds var
    to the evaluated expr in env (mutated in place).

    Returns True, False, or z3.BoolRef.
    """
    conds: list = []

    for c in constraints:
        if not isinstance(c, RelConstr):
            continue

        # Handle variable binding: var = expr
        if c.op == RelKind.Eq and isinstance(c.arg1, Id):
            name = c.arg1.name
            if name not in env and name not in ctx.z3_vars and "." not in name:
                rhs = _resolve(c.arg2, env, ctx)
                if rhs is not None:
                    env[name] = rhs
                    continue

        result = _eval_rel(c, env, ctx)
        if result is None:
            continue
        if isinstance(result, bool):
            if not result:
                return False
        elif isinstance(result, z3.BoolRef):
            conds.append(result)

    if not conds:
        return True
    return conds[0] if len(conds) == 1 else z3.And(*conds)


def _eval_rel(rel: RelConstr, env: dict, ctx: Ctx) -> Any:
    """Evaluate a RelConstr to True/False/z3.BoolRef/None."""
    if rel.op == RelKind.No:
        return _eval_no(rel.arg1, env, ctx)
    if rel.op == RelKind.Typ:
        return True

    lhs = _resolve(rel.arg1, env, ctx)
    rhs = _resolve(rel.arg2, env, ctx) if rel.arg2 is not None else None
    if lhs is None or rhs is None:
        return None
    lhs, rhs = _coerce(lhs, rhs)
    if lhs is None or rhs is None:
        return None

    if rel.op == RelKind.Eq: return lhs == rhs
    if rel.op == RelKind.Neq: return lhs != rhs
    if rel.op == RelKind.Le: return lhs <= rhs
    if rel.op == RelKind.Lt: return lhs < rhs
    if rel.op == RelKind.Ge: return lhs >= rhs
    if rel.op == RelKind.Gt: return lhs > rhs
    return None


def _eval_no(arg: Node, env: dict, ctx: Ctx) -> Any:
    """Evaluate `no <expr>` constraint."""
    if isinstance(arg, Compr):
        if not arg.bodies:
            return True
        body = arg.bodies[0]
        fire: list = []
        for _, cond in _enumerate_body(body, env, ctx):
            if isinstance(cond, bool):
                if cond:
                    return False
            elif isinstance(cond, z3.BoolRef):
                fire.append(cond)
        if not fire:
            return True
        return z3.Not(fire[0]) if len(fire) == 1 else z3.Not(z3.Or(*fire))

    if isinstance(arg, Id):
        return _no_rule(arg.name, ctx)

    return True


# ── Helpers ──────────────────────────────────────────────────────

def _m(a: dict, b: dict) -> dict:
    r = dict(a)
    r.update(b)
    return r


def _and(a: Any, b: Any) -> Any:
    if a is True:
        return b
    if b is True:
        return a
    if a is False or b is False:
        return False
    if isinstance(a, z3.BoolRef) and isinstance(b, z3.BoolRef):
        return z3.And(a, b)
    if isinstance(a, z3.BoolRef):
        return a
    if isinstance(b, z3.BoolRef):
        return b
    return True


def _val_key(v: Any) -> Any:
    if isinstance(v, z3.ExprRef):
        return v.sexpr()
    if isinstance(v, Ref):
        return ("ref", v.target)
    return str(v)


def _fields_key(fields: list) -> tuple:
    return tuple(_val_key(f) for f in fields)


# ── Rule derivation ──────────────────────────────────────────────

def _node_has_aggregation(node: Node) -> bool:
    """Check if a node tree contains count or sum operators."""
    if isinstance(node, FuncTerm):
        if isinstance(node.function, OpKind) and node.function in (
            OpKind.Count, OpKind.SymCount, OpKind.Sum,
        ):
            return True
        for arg in node.args:
            if _node_has_aggregation(arg):
                return True
    if isinstance(node, RelConstr):
        if node.arg1 and _node_has_aggregation(node.arg1):
            return True
        if node.arg2 and _node_has_aggregation(node.arg2):
            return True
    if isinstance(node, Find):
        if _node_has_aggregation(node.match):
            return True
    if isinstance(node, Compr):
        for b in node.bodies:
            for c in b.constraints:
                if _node_has_aggregation(c):
                    return True
    return False


def _rule_has_aggregation(rule: Rule) -> bool:
    """Check if any body constraint in a rule contains count or sum."""
    for body in rule.bodies:
        for c in body.constraints:
            if _node_has_aggregation(c):
                return True
    return False


def _derive_instances(ctx: Ctx, recursion_bound: int) -> None:
    """Derive instances from rules.

    Rules with aggregation (count/sum) are excluded from derivation;
    they are evaluated on-the-fly during conforms to ensure they see
    the fully-derived set of structural instances.
    """
    # Exclude heads whose rules use aggregation
    derivable: Set[str] = set()
    for name, rules in ctx.rules_by_head.items():
        if not any(_rule_has_aggregation(r) for r in rules):
            derivable.add(name)

    # Unified fixed-point loop: all derivable rules together
    for _ in range(recursion_bound):
        added = False
        for name in sorted(derivable):
            new = _derive_for(name, ctx)
            if new:
                ctx.derived.setdefault(name, []).extend(new)
                added = True
        if not added:
            break


def _derive_for(name: str, ctx: Ctx) -> List[Binding]:
    """Try to derive new instances for a given constructor/rule head."""
    existing_keys: Set[tuple] = set()
    for inst in ctx.all_of(name):
        existing_keys.add(_fields_key(inst.fields))

    new_insts: List[Binding] = []

    for rule in ctx.rules_by_head.get(name, []):
        for head in rule.heads:
            head_name = None
            if isinstance(head, FuncTerm) and isinstance(head.function, Id):
                head_name = head.function.name
            elif isinstance(head, Id):
                head_name = head.name
            if head_name != name:
                continue

            for body in rule.bodies:
                for benv, cond in _enumerate_body(body, {}, ctx):
                    if not isinstance(head, FuncTerm):
                        continue
                    fields = [_resolve(a, benv, ctx) for a in head.args]
                    if any(f is None for f in fields):
                        continue
                    key = _fields_key(fields)
                    if key not in existing_keys:
                        existing_keys.add(key)
                        new_insts.append(Binding(name, fields, None, cond))

    return new_insts


def _collect_deps(node: Node, dep_set: Set[str], known: Set[str]) -> None:
    if isinstance(node, Find):
        mn = None
        if isinstance(node.match, Id):
            mn = node.match.name
        elif isinstance(node.match, FuncTerm) and isinstance(node.match.function, Id):
            mn = node.match.function.name
        if mn and mn in known:
            dep_set.add(mn)
    elif isinstance(node, RelConstr):
        if node.arg1:
            _collect_deps_expr(node.arg1, dep_set, known)
        if node.arg2:
            _collect_deps_expr(node.arg2, dep_set, known)


def _collect_deps_expr(node: Node, dep_set: Set[str], known: Set[str]) -> None:
    if isinstance(node, Id):
        if node.name in known:
            dep_set.add(node.name)
    elif isinstance(node, FuncTerm):
        if isinstance(node.function, Id) and node.function.name in known:
            dep_set.add(node.function.name)
        for arg in node.args:
            _collect_deps_expr(arg, dep_set, known)
    elif isinstance(node, Compr):
        for body in node.bodies:
            for c in body.constraints:
                _collect_deps(c, dep_set, known)


def _has_cycle(start: str, current: str, deps: Dict[str, Set[str]], visited: Set[str]) -> bool:
    if current in visited:
        return False
    visited = visited | {current}
    for nxt in deps.get(current, set()):
        if nxt == start:
            return True
        if _has_cycle(start, nxt, deps, visited):
            return True
    return False


# ── Conforms evaluation ──────────────────────────────────────────

def _no_rule(rule_name: str, ctx: Ctx) -> Any:
    """Constraint that ensures the named rule cannot fire."""
    rules = ctx.rules_by_head.get(rule_name, [])
    if not rules:
        return True

    fire: list = []
    for rule in rules:
        for body in rule.bodies:
            for _, cond in _enumerate_body(body, {}, ctx):
                if isinstance(cond, bool):
                    if cond:
                        return False
                elif isinstance(cond, z3.BoolRef):
                    fire.append(cond)
    if not fire:
        return True
    return z3.Not(fire[0]) if len(fire) == 1 else z3.Not(z3.Or(*fire))


def _rule_fires(rule_name: str, ctx: Ctx) -> Any:
    """Constraint that ensures a rule/constructor is derivable."""
    # Check derived instances first
    instances = ctx.all_of(rule_name)
    if instances:
        conds: list = []
        for inst in instances:
            if isinstance(inst.cond, bool):
                if inst.cond:
                    return True
            elif isinstance(inst.cond, z3.BoolRef):
                conds.append(inst.cond)
            else:
                return True
        if conds:
            return conds[0] if len(conds) == 1 else z3.Or(*conds)

    # Try evaluating rule bodies directly
    rules = ctx.rules_by_head.get(rule_name, [])
    if not rules:
        return False

    fire: list = []
    for rule in rules:
        for body in rule.bodies:
            for _, cond in _enumerate_body(body, {}, ctx):
                if isinstance(cond, bool):
                    if cond:
                        return True
                elif isinstance(cond, z3.BoolRef):
                    fire.append(cond)
    if not fire:
        return False
    return fire[0] if len(fire) == 1 else z3.Or(*fire)


def _eval_conforms(domain: Domain, ctx: Ctx) -> List[Any]:
    """Evaluate all conforms clauses. Returns Z3 constraints."""
    constraints: list = []

    for ci in domain.conforms:
        if ci.contract_kind != ContractKind.ConformsProp:
            continue
        for spec in ci.specification:
            if isinstance(spec, Body):
                for c in spec.constraints:
                    r = _eval_conforms_item(c, ctx)
                    if r is not None:
                        constraints.append(r)

    return constraints


def _eval_conforms_item(constraint: Node, ctx: Ctx) -> Any:
    """Evaluate a single conforms constraint."""
    if isinstance(constraint, RelConstr) and constraint.op == RelKind.No:
        arg = constraint.arg1
        if isinstance(arg, Compr):
            for body in arg.bodies:
                for c in body.constraints:
                    if isinstance(c, Find):
                        nm = None
                        if isinstance(c.match, Id):
                            nm = c.match.name
                        elif isinstance(c.match, FuncTerm) and isinstance(c.match.function, Id):
                            nm = c.match.function.name
                        if nm:
                            return _no_rule(nm, ctx)
        elif isinstance(arg, Id):
            return _no_rule(arg.name, ctx)

    elif isinstance(constraint, Find):
        match = constraint.match
        if isinstance(match, Id):
            return _rule_fires(match.name, ctx)
        elif isinstance(match, FuncTerm) and isinstance(match.function, Id):
            return _rule_fires(match.function.name, ctx)

    return None


# ── Config extraction ────────────────────────────────────────────

def _get_recursion_bound(model: Model) -> int:
    bound = 10
    for s in model.config.settings:
        if hasattr(s, "key") and s.key.name == "solver_RecursionBound":
            try:
                bound = int(s.value.raw)
            except (TypeError, ValueError):
                pass
    return bound


# ── Main entry point ─────────────────────────────────────────────

def direct_solve(domain_node, model_node, max_sols, sink) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Solve a partial model against a domain's conformance specification.

    Returns (success, solution_data) where solution_data is a dict mapping
    variable names to their solved values, or None if unsat.
    """
    sink.write_message_line("Starting direct Z3 solver...", SeverityKind.Info)

    ctx = _build_ctx(domain_node, model_node)

    sink.write_message_line(
        "  Constructors: %s" % list(ctx.ctors.keys()), SeverityKind.Info
    )
    sink.write_message_line(
        "  Rules: %s" % list(ctx.rules_by_head.keys()), SeverityKind.Info
    )
    sink.write_message_line(
        "  Facts: %d, Symbolic vars: %s"
        % (sum(len(v) for v in ctx.base.values()), set(ctx.z3_vars.keys())),
        SeverityKind.Info,
    )

    # Derive instances from rules
    recursion_bound = _get_recursion_bound(model_node)
    _derive_instances(ctx, recursion_bound)

    derived_count = sum(len(v) for v in ctx.derived.values())
    if derived_count > 0:
        sink.write_message_line("  Derived %d instances" % derived_count, SeverityKind.Info)

    # Evaluate conforms clauses
    constraints = _eval_conforms(domain_node, ctx)

    # Build Z3 solver
    solver = z3.Solver()
    solver.set("timeout", 30000)

    # Add type membership constraints (Natural >= 0, PosInteger >= 1, etc.)
    for tc in ctx.type_constraints:
        solver.add(tc)

    for c in constraints:
        if isinstance(c, z3.BoolRef):
            solver.add(c)
        elif isinstance(c, bool):
            if not c:
                sink.write_message_line("  Trivially UNSAT", SeverityKind.Info)
                return False, None

    sink.write_message_line("  Checking satisfiability...", SeverityKind.Info)

    solutions: List[Dict[str, str]] = []
    sol_count = 0

    while sol_count < max_sols:
        result = solver.check()

        if result == z3.sat:
            model = solver.model()
            sol_count += 1
            sink.write_message_line(
                "  SAT - Solution %d found!" % sol_count, SeverityKind.Info
            )
            solution: Dict[str, str] = {}
            block_clause = []
            for vn in sorted(ctx.z3_vars.keys()):
                zvar = ctx.z3_vars[vn]
                val = model.evaluate(zvar)
                sink.write_message_line("    %s = %s" % (vn, val), SeverityKind.Info)
                solution[vn] = str(val)
                block_clause.append(zvar != val)
            solutions.append(solution)

            if sol_count < max_sols:
                # Block this solution to find the next one
                solver.add(z3.Or(*block_clause))
        elif result == z3.unsat:
            if sol_count == 0:
                sink.write_message_line("  UNSAT - No solution", SeverityKind.Info)
            else:
                sink.write_message_line(
                    "  No more solutions (%d total)" % sol_count, SeverityKind.Info
                )
            break
        else:
            sink.write_message_line(
                "  UNKNOWN - Solver inconclusive", SeverityKind.Warning
            )
            break

    if solutions:
        return True, solutions[0]
    return False, None
