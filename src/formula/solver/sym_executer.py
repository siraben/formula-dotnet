"""
Port of Src/Core/Solver/Execution/SymExecuter.cs

The symbolic executer computes a symbolic least fixed-point (LFP) of a
set of rules, encoding constraints in Z3, and then invokes the Z3 solver
to find satisfying assignments.
"""
from __future__ import annotations

import re
from collections import defaultdict
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

import z3

from formula.solver.activation import Activation
from formula.solver.sym_element import SymElement
from formula.solver.term_enc_index import TermEncIndex

if TYPE_CHECKING:
    from formula.common.rules import CoreRule, RuleTable
    from formula.common.terms import Symbol, Term, TermIndex
    from formula.solver.solver import Solver


class SymSubIndex:
    """
    Maps a pattern to the set of SymElements that unify with it, organised
    by projections of bound variables.
    """

    EMPTY_PROJECTION: Tuple["Term", ...] = ()

    def __init__(self, executer: "SymExecuter", pattern: "Term"):
        self.executer = executer
        self.pattern = pattern
        self._n_bound_vars = 0
        self._triggers: Dict[int, List[Tuple["CoreRule", int]]] = {}
        self._facts: Dict[Tuple["Term", ...], Set[SymElement]] = {}
        # TODO: integrate Matcher from common for full pattern matching
        # For now, use simplified matching

    def add_trigger(self, rule: "CoreRule", find_number: int) -> None:
        stratum = rule.stratum
        if stratum not in self._triggers:
            self._triggers[stratum] = []
        self._triggers[stratum].append((rule, find_number))

    def try_add(
        self,
        t: SymElement,
        pending: Optional[Set[Activation]],
        stratum: int,
    ) -> bool:
        """Try to add *t* to this sub-index. Pend triggered rules."""
        # Simplified: accept all terms whose head symbol matches the pattern
        if t.term.symbol != self.pattern.symbol:
            return False

        projection = self.EMPTY_PROJECTION

        if projection not in self._facts:
            self._facts[projection] = set()
        self._facts[projection].add(t)

        if pending is not None and stratum in self._triggers:
            for rule, find_num in self._triggers[stratum]:
                pending.add(Activation(rule, find_num, t))

        return True

    def pend_all(self, pending: Set[Activation], stratum: int) -> None:
        """Generate pending activations for all triggered rules in *stratum*."""
        if stratum not in self._triggers:
            return
        for _proj, elems in self._facts.items():
            for elem in elems:
                for rule, find_num in self._triggers[stratum]:
                    pending.add(Activation(rule, find_num, elem))

    def query(self, projection: Tuple["Term", ...] = ()) -> Iterable["Term"]:
        if not projection:
            for _proj, elems in self._facts.items():
                for e in elems:
                    yield e.term
        else:
            for e_key, elems in self._facts.items():
                for e in elems:
                    yield e.term

    def query_with_count(
        self,
        projection: Tuple["Term", ...],
    ) -> Tuple[Iterable["Term"], int]:
        if projection not in self._facts:
            return iter([]), 0
        elems = self._facts[projection]
        return (e.term for e in elems), len(elems)


class SymExecuter:
    """
    Executes rules symbolically, building up a LFP of SymElements with
    Z3 side constraints, then checks satisfiability.
    """

    PATTERN_VAR_BOUND_PREFIX = "^"
    PATTERN_VAR_UNBOUND_PREFIX = "*"

    def __init__(self, solver: "Solver"):
        self.solver: "Solver" = solver
        self.rules: "RuleTable" = solver.partial_model.rules
        self.index: "TermIndex" = solver.partial_model.index
        self.encoder = TermEncIndex(solver)
        self.keep_derivations: bool = True

        # Core data structures
        self._lfp: Dict["Term", SymElement] = {}
        self._facts: Dict["Term", set] = {}
        self._pending_constraints: List[z3.BoolRef] = []
        self._recursion_constraints: Dict[int, z3.BoolRef] = {}
        self._rule_cycles: Dict[int, int] = {}
        self._prev_solutions: List[Dict[z3.ExprRef, z3.ExprRef]] = []
        self._solution_strings: List[List[str]] = []

        # Indices
        self._trig_indices: Dict["Term", SymSubIndex] = {}
        self._compr_indices: Dict["Symbol", SymSubIndex] = {}
        self._symb_to_index_map: Dict["Symbol", List[SymSubIndex]] = {}
        self._untrig_rules: Dict[int, List["CoreRule"]] = {}
        self._types_to_triggers_map: Dict["Term", Set["Term"]] = {}

        # Constraint tracking
        self.var_to_type_map: Dict["Term", "Term"] = {}
        self._positive_constraint_terms: Set["Term"] = set()
        self._negative_constraint_terms: Set["Term"] = set()
        self._sym_count_map: Dict["Term", List["Term"]] = defaultdict(list)

        # Variable facts and alias map
        self._var_facts: Set["Term"] = set()
        self._alias_map: Dict[Any, "Term"] = {}

        # Initialise
        self._init_from_partial_model()
        self._initialize_executer()

    # ------------------------------------------------------------------
    # Public API used by external callers and SymElement
    # ------------------------------------------------------------------

    def get_symbolic_term(self, t: "Term") -> Optional[SymElement]:
        return self._lfp.get(t)

    def get_side_constraints(self, t: "Term") -> z3.BoolRef:
        e = self._lfp.get(t)
        if e is not None and e.has_constraints():
            sc = e.get_side_constraints(self)
            if sc is not None:
                return sc
        return z3.BoolVal(True, ctx=self.solver.context)

    def exists(self, t: "Term") -> bool:
        return t in self._lfp

    def pend_constraint(self, expr: z3.BoolRef) -> None:
        self._pending_constraints.append(expr)

    def pend_equality_constraint_terms(self, t1: "Term", t2: "Term") -> None:
        enc1, _ = self.encoder.get_term(t1)
        enc2, _ = self.encoder.get_term(t2)
        self.pend_equality_constraint(enc1, enc2)

    def pend_equality_constraint(self, e1: z3.ExprRef, e2: z3.ExprRef) -> None:
        self._pending_constraints.append(e1 == e2)

    def has_side_constraint(self, term: "Term") -> bool:
        e = self._lfp.get(term)
        return e is not None and e.has_constraints()

    def add_positive_constraint(self, t: "Term") -> None:
        e = self._lfp.get(t)
        if e is not None and e.has_constraints():
            self._positive_constraint_terms.add(t)

    def add_negative_constraint(self, t: "Term") -> bool:
        e = self._lfp.get(t)
        if e is not None and e.has_constraints():
            self._negative_constraint_terms.add(t)
            return True
        return False

    def get_symbolic_count_index(self, t: "Term") -> int:
        return len(self._sym_count_map.get(t, []))

    def get_symbolic_count_term(self, t: "Term", index: int) -> "Term":
        return self._sym_count_map[t][index]

    def add_symbolic_count_term(self, x: "Term", y: "Term") -> None:
        self._sym_count_map[x].append(y)

    # ------------------------------------------------------------------
    # Solve / GetSolution
    # ------------------------------------------------------------------

    def solve(self) -> bool:
        """Run the symbolic fixpoint then check Z3 satisfiability."""
        self.execute()

        solvable = False
        has_conforms = False
        has_requires = False
        requires_pattern = re.compile(r"_Query_\d+\.requires$")

        for key in self._lfp:
            name = key.symbol.printable_name
            if name.endswith("conforms"):
                has_conforms = True
            elif requires_pattern.search(name):
                has_requires = True

        if not (has_conforms and has_requires):
            return False

        assumptions: List[z3.BoolRef] = []
        conforms_pattern = re.compile(r"conforms\d+$")

        for key, elem in self._lfp.items():
            name = key.symbol.printable_name
            if conforms_pattern.search(name) or requires_pattern.search(name):
                sc = elem.get_side_constraints(self)
                if sc is not None:
                    assumptions.append(sc)

        for rec_c in self._recursion_constraints.values():
            assumptions.append(rec_c)

        # Assert-and-track each assumption
        idx = 1
        for assumption in assumptions:
            pname = f"P{idx}"
            idx += 1
            p = z3.Bool(pname, ctx=self.solver.context)
            self.solver.z3_solver.assert_and_track(assumption, p)

        status = self.solver.z3_solver.check()
        if str(status) == "sat":
            solvable = True
            model = self.solver.z3_solver.model()
            sol_map: Dict[z3.ExprRef, z3.ExprRef] = {}
            for symb, var_term in self._alias_map.items():
                if hasattr(var_term, "symbol") and var_term.symbol.kind == "UserCnstSymb":
                    t = var_term
                    if t in self.var_to_type_map:
                        expr = self.encoder.get_var_enc(t, self.var_to_type_map[t])
                        interp = model.evaluate(expr)
                        sol_map[expr] = interp
            self._prev_solutions.append(sol_map)
            self._solution_strings.append(self._get_new_kind_constructors(model))
        elif str(status) == "unsat":
            print("Model not solvable.")
            core = self.solver.z3_solver.unsat_core()
            for expr in core:
                print(f"Unsat core expr: {expr}")

        return solvable

    def get_solution(self, num: int) -> None:
        """Print or compute solution number *num*."""
        if num < len(self._solution_strings):
            print(f"Solution number {num}")
            for s in self._solution_strings[num]:
                print(s)
            print()
            return

        # Enumerate more solutions
        while len(self._solution_strings) <= num:
            prev = self._prev_solutions[len(self._solution_strings) - 1]
            negated = [k != v for k, v in prev.items()]
            self.solver.z3_solver.add(z3.Or(*negated))
            status = self.solver.z3_solver.check()
            if str(status) == "sat":
                model = self.solver.z3_solver.model()
                sol_map: Dict[z3.ExprRef, z3.ExprRef] = {}
                for symb, var_term in self._alias_map.items():
                    if hasattr(var_term, "symbol") and var_term.symbol.kind == "UserCnstSymb":
                        t = var_term
                        if t in self.var_to_type_map:
                            expr = self.encoder.get_var_enc(t, self.var_to_type_map[t])
                            interp = model.evaluate(expr)
                            sol_map[expr] = interp
                self._prev_solutions.append(sol_map)
                self._solution_strings.append(self._get_new_kind_constructors(model))
            else:
                break

        if num < len(self._solution_strings):
            print(f"Solution number {num}")
            for s in self._solution_strings[num]:
                print(s)
            print()
        else:
            print(f"Could not find solution {num}")

    # ------------------------------------------------------------------
    # Core fixpoint execution
    # ------------------------------------------------------------------

    def execute(self) -> None:
        """Run the stratified symbolic fixpoint computation."""
        max_depth = self.solver.recursion_bound

        for stratum in range(self.rules.stratification_depth):
            pending_act: Set[Activation] = set()

            # Untriggered rules
            if stratum in self._untrig_rules:
                for r in self._untrig_rules[stratum]:
                    false_enc, norm = self.encoder.get_term(self.index.false_value)
                    sym_false = SymElement(norm, false_enc, self.solver.context)
                    pending_act.add(Activation(r, -1, sym_false))

            # Pend from trigger indices
            for _pat, sub_idx in self._trig_indices.items():
                sub_idx.pend_all(pending_act, stratum)

            while pending_act:
                act = pending_act.pop()
                rule_id = act.rule.rule_id
                self._positive_constraint_terms.clear()
                self._negative_constraint_terms.clear()

                # Execute rule
                pending_facts: Dict["Term", set] = {}
                act.rule.execute(
                    act.binding1.term if act.binding1 else None,
                    act.find_number,
                    self,
                    self.keep_derivations,
                    pending_facts,
                )

                copy_constraints = True
                if rule_id in self._rule_cycles:
                    self._rule_cycles[rule_id] += 1
                    if self._rule_cycles[rule_id] > max_depth:
                        copy_constraints = False

                for term in pending_facts:
                    if copy_constraints:
                        if self._is_constraint_satisfiable(term):
                            elem = self._extend_lfp(term)
                            self._index_fact(elem, pending_act, stratum)
                    else:
                        self._add_recursion_constraint(rule_id)

                self._pending_constraints.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_from_partial_model(self) -> None:
        """Extract variable facts and aliases from the partial model."""
        pm = self.solver.partial_model
        self._var_facts, self._alias_map = pm.convert_symb_cnsts_to_vars()

        # Pre-register all aliases with the encoder
        for symb, var_term in self._alias_map.items():
            v_term = self.index.symb_cnst_to_var(symb)
            t_term = pm.get_symb_cnst_type(symb)
            if v_term not in self.var_to_type_map:
                self.var_to_type_map[v_term] = t_term
            self.encoder.get_var_enc(v_term, t_term)

    def _initialize_executer(self) -> None:
        opt_rules = self.rules.optimize()
        self._rule_cycles = self.rules.get_cycles(opt_rules)

        for r in opt_rules:
            for s in r.comprehension_symbols:
                self._register_comprehension(s)

            if r.trigger1 is None and r.trigger2 is None:
                self._register_untriggered(r)
                continue
            if r.trigger1 is not None:
                self._register_triggered(r, 0)
            if r.trigger2 is not None:
                self._register_triggered(r, 1)

        # Index initial variable facts
        for f in self._var_facts:
            self._index_fact(self._extend_lfp(f), None, -1)

    def _extend_lfp(self, t: "Term") -> SymElement:
        """Extend the LFP with a symbolic element equivalent to *t*."""
        e = self._lfp.get(t)
        if e is None:
            normalized = t
            enc = None
            if self.encoder.can_get_encoding(t):
                enc, normalized = self.encoder.get_term(t, self)
            e = SymElement(normalized, enc, self.solver.context)
            self._lfp[normalized] = e

        if (
            self._pending_constraints
            or self._positive_constraint_terms
            or self._negative_constraint_terms
        ):
            e.add_constraint_data(
                set(self._pending_constraints),
                set(self._positive_constraint_terms),
                set(self._negative_constraint_terms),
            )
        else:
            e.set_directly_provable()

        return e

    def _index_fact(
        self,
        t: SymElement,
        pending: Optional[Set[Activation]],
        stratum: int,
    ) -> None:
        sub_indices = self._symb_to_index_map.get(t.term.symbol)
        if sub_indices is None:
            return
        for idx in sub_indices:
            idx.try_add(t, pending, stratum)

    def _register_untriggered(self, rule: "CoreRule") -> None:
        stratum = rule.stratum
        if stratum not in self._untrig_rules:
            self._untrig_rules[stratum] = []
        self._untrig_rules[stratum].append(rule)

    def _register_triggered(self, rule: "CoreRule", find_number: int) -> None:
        trigger = rule.trigger1 if find_number == 0 else rule.trigger2
        if trigger is None:
            return

        if not trigger.symbol.is_variable:
            self._register_pattern(rule, trigger, find_number)
            return

        # Type-triggered: build patterns for each type member
        type_term = rule.find1.type_term if find_number == 0 else rule.find2.type_term
        if type_term in self._types_to_triggers_map:
            for p in self._types_to_triggers_map[type_term]:
                self._trig_indices[p].add_trigger(rule, find_number)
            return

        pattern_set: Set["Term"] = set()
        for s in self._get_trigger_symbols(type_term):
            pattern = self._mk_pattern(s, False)
            pattern_set.add(pattern)
            self._register_pattern(rule, pattern, find_number)
        self._types_to_triggers_map[type_term] = pattern_set

    def _register_pattern(
        self,
        rule: "CoreRule",
        trigger: "Term",
        find_number: int,
    ) -> None:
        if trigger not in self._trig_indices:
            sub = SymSubIndex(self, trigger)
            self._trig_indices[trigger] = sub
            sym = trigger.symbol
            if sym not in self._symb_to_index_map:
                self._symb_to_index_map[sym] = []
            self._symb_to_index_map[sym].append(sub)
        self._trig_indices[trigger].add_trigger(rule, find_number)

    def _register_comprehension(self, compr_symbol: "Symbol") -> None:
        if compr_symbol not in self._compr_indices:
            pattern = self._mk_pattern(compr_symbol, True)
            sub = SymSubIndex(self, pattern)
            self._compr_indices[compr_symbol] = sub
            if compr_symbol not in self._symb_to_index_map:
                self._symb_to_index_map[compr_symbol] = []
            self._symb_to_index_map[compr_symbol].append(sub)

    def _mk_pattern(self, s: "Symbol", is_compr: bool) -> "Term":
        idx = self.index
        args = []
        if is_compr:
            for i in range(s.arity - 1):
                args.append(idx.mk_var(f"{self.PATTERN_VAR_BOUND_PREFIX}{i}", True))
            args.append(idx.mk_var(f"{self.PATTERN_VAR_UNBOUND_PREFIX}0", True))
        else:
            for i in range(s.arity):
                args.append(idx.mk_var(f"{self.PATTERN_VAR_UNBOUND_PREFIX}{i}", True))
        return idx.mk_apply(s, args)

    @staticmethod
    def _get_trigger_symbols(type_term: "Term") -> Iterable["Symbol"]:
        """Yield data-constructor/constant symbols from a type union term."""
        from formula.common.terms import Term as T

        def _visit(t):
            if t.symbol.kind == "TypeUnionSymbol":
                for child in t.args:
                    yield from _visit(child)
            elif t.symbol.kind == "UserSortSymb":
                yield t.symbol.data_symbol
            elif t.symbol.is_data_constructor or t.symbol.is_non_var_constant:
                yield t.symbol
            else:
                yield t.symbol

        yield from _visit(type_term)

    def _is_constraint_satisfiable(self, term: "Term") -> bool:
        if not self._should_check_constraints(term):
            return True

        curr_constraint: Optional[z3.BoolRef] = None
        ctx = self.solver.context

        for t in self._positive_constraint_terms:
            e = self._lfp.get(t)
            if e is not None:
                nc = e.get_side_constraints(self)
                if nc is not None:
                    curr_constraint = z3.And(curr_constraint, nc) if curr_constraint else nc

        for t in self._negative_constraint_terms:
            e = self._lfp.get(t)
            if e is not None:
                nc = e.get_side_constraints(self)
                if nc is not None:
                    nc = z3.Not(nc)
                    curr_constraint = z3.And(curr_constraint, nc) if curr_constraint else nc

        for nc in self._pending_constraints:
            curr_constraint = z3.And(curr_constraint, nc) if curr_constraint else nc

        if curr_constraint is None:
            return True

        status = self.solver.z3_solver.check(curr_constraint)
        return str(status) != "unsat"

    def _should_check_constraints(self, t: "Term") -> bool:
        name = t.symbol.printable_name
        if name.endswith("conforms") or re.search(r"conforms\d+$", name):
            return False
        if (
            not self._pending_constraints
            and not self._positive_constraint_terms
            and not self._negative_constraint_terms
        ):
            return False
        return True

    def _add_recursion_constraint(self, rule_id: int) -> None:
        if not self._pending_constraints:
            return
        ctx = self.solver.context
        expr: Optional[z3.BoolRef] = None
        for c in self._pending_constraints:
            expr = z3.And(expr, c) if expr else c
        expr = z3.Not(expr)
        if rule_id in self._recursion_constraints:
            self._recursion_constraints[rule_id] = z3.And(
                self._recursion_constraints[rule_id], expr
            )
        else:
            self._recursion_constraints[rule_id] = expr

    def _get_new_kind_constructors(self, model) -> List[str]:
        strs: List[str] = []
        for key, elem in self._lfp.items():
            if (
                key.symbol.is_data_constructor
                and not getattr(key.symbol, "is_auto_gen", False)
                and self.encoder.can_get_encoding(key)
            ):
                sc = elem.get_side_constraints(self)
                if sc is not None:
                    evaluated = model.evaluate(sc)
                    if z3.is_true(evaluated):
                        strs.append(self._get_model_interpretation(key, model))
        return strs

    def _get_model_interpretation(self, t: "Term", model) -> str:
        """Recursively interpret a term under a Z3 model."""
        if t.groundness == "Ground":
            return str(t)

        def _interp(x: "Term") -> str:
            if x.symbol.arity == 0:
                if x.symbol.kind == "UserCnstSymb" and x.symbol.is_variable:
                    if x in self.var_to_type_map:
                        expr = self.encoder.get_var_enc(x, self.var_to_type_map[x])
                        interp = model.evaluate(expr)
                        emb = self.solver.type_embedder.get_embedding_by_sort(expr.sort())
                        if isinstance(emb, IntRangeEmbedding):
                            val = interp.arg(0).as_long() if interp.num_args() > 0 else 0
                            return str(emb.lower + val)
                        elif isinstance(emb, EnumEmbedding):
                            idx = interp.arg(0).as_long() if interp is not None and interp.num_args() > 0 else 0
                            return emb.get_symbol_at_index(idx)
                        elif interp is not None:
                            return str(interp)
                        else:
                            return str(emb.default_member[1])
                return x.symbol.printable_name
            elif x.symbol.is_data_constructor:
                child_strs = [_interp(arg) for arg in x.args]
                return f"{x.symbol.printable_name}({', '.join(child_strs)})"
            else:
                return str(x)

        return _interp(t)

    # ------------------------------------------------------------------
    # Query interface (used by rules during execution)
    # ------------------------------------------------------------------

    def query_compr(
        self,
        compr_term: "Term",
    ) -> Tuple[Iterable["Term"], int]:
        sub_index = self._compr_indices[compr_term.symbol]
        projection = tuple(compr_term.args[:-1])
        return sub_index.query_with_count(projection)

    def query_pattern(
        self,
        pattern: "Term",
        projection: Tuple["Term", ...],
    ) -> Iterable["Term"]:
        return self._trig_indices[pattern].query(projection)

    def query_type(
        self,
        type_term: "Term",
        binding: Optional["Term"] = None,
    ) -> Iterable["Term"]:
        patterns = self._types_to_triggers_map.get(type_term, set())
        if binding is not None:
            for p in patterns:
                if p.symbol == binding.symbol and self.exists(binding):
                    yield binding
                    return
            return

        for p in patterns:
            yield from self._trig_indices[p].query(())


# Needed for the _get_model_interpretation import
from formula.solver.type_embeddings import EnumEmbedding, IntRangeEmbedding
