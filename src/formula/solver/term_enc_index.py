"""
Port of Src/Core/Solver/Execution/TermEncIndex.cs

An index of encodings from FORMULA terms to Z3 expressions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import z3

if TYPE_CHECKING:
    from formula.common.terms import Term, Symbol
    from formula.solver.solver import Solver
    from formula.solver.sym_executer import SymExecuter


class TermEncIndex:
    """Maps FORMULA terms to their Z3 encodings."""

    def __init__(self, solver: "Solver"):
        self.solver: "Solver" = solver
        self._encodings: Dict["Term", z3.ExprRef] = {}

    # ------------------------------------------------------------------
    # Variable encoding
    # ------------------------------------------------------------------

    def get_var_enc(self, v: "Term", type_term: "Term") -> z3.ExprRef:
        """
        Return (or create) the Z3 encoding for variable *v* with the given
        *type_term*.
        """
        if v in self._encodings:
            return self._encodings[v]

        typ_emb = self.solver.type_embedder.choose_representation(type_term)
        var_enc = z3.Const(v.symbol.full_name, typ_emb.representation)
        self._encodings[v] = var_enc
        return var_enc

    # ------------------------------------------------------------------
    # Encoding feasibility check
    # ------------------------------------------------------------------

    def can_get_encoding(self, t: "Term") -> bool:
        """Check whether a full encoding is obtainable for *t*."""
        if t in self._encodings:
            return True

        has_encoding = True

        def _check(x: "Term") -> None:
            nonlocal has_encoding
            if not has_encoding:
                return
            if x.symbol.kind == "ConSymb":
                if x.symbol.sort_symbol is None:
                    has_encoding = False
                    return
                for child in x.args:
                    _check(child)
            elif x.symbol.kind == "UserCnstSymb" and getattr(x.symbol, "is_mangled", False):
                name = x.symbol.name
                if len(name) > 1 and name[1].isdigit():
                    has_encoding = False

        _check(t)
        return has_encoding

    # ------------------------------------------------------------------
    # Term encoding
    # ------------------------------------------------------------------

    def get_term(
        self,
        t: "Term",
        facts: Optional["SymExecuter"] = None,
    ) -> Tuple[z3.ExprRef, "Term"]:
        """
        Return an encoding of *t*, possibly after applying some normalizing
        rewrites.  Returns ``(z3_expr, normalized_term)``.
        """
        normalized = self._normalize(t)
        if normalized in self._encodings:
            return self._encodings[normalized], normalized

        enc = self._encode_recursive(normalized, facts)
        return enc, normalized

    def _encode_recursive(
        self,
        t: "Term",
        facts: Optional["SymExecuter"],
    ) -> z3.ExprRef:
        """Recursively encode a term to a Z3 expression."""
        if t in self._encodings:
            return self._encodings[t]

        ctx = self.solver.context

        # Ground terms without symbolic parts
        if t.groundness == "Ground" and not t.is_symbolic_term():
            typ_emb = self.solver.type_embedder.choose_representation(t)
            enc = self.solver.type_embedder.mk_ground(t, typ_emb)
            self._encodings[t] = enc
            return enc

        # Data constructors
        if t.symbol.is_data_constructor:
            child_encs = [self._encode_recursive(arg, facts) for arg in t.args]
            con_emb = self._get_constructor_embedding(t)
            args = []
            for i, child_enc in enumerate(child_encs):
                field_sort = con_emb.z3_constructor.accessor(i).range()
                field_emb = self.solver.type_embedder.get_embedding_by_sort(field_sort)
                args.append(field_emb.mk_coercion(child_enc))
            enc = con_emb.mk_ground_from_symbol(t.symbol, args)
            self._encodings[t] = enc
            return enc

        # Base operations (+, -, *, /, relational ops, etc.)
        if t.symbol.kind == "BaseOpSymb":
            child_encs = [self._encode_recursive(arg, facts) for arg in t.args]
            enc = self._encode_base_op(t, child_encs, facts)
            self._encodings[t] = enc
            return enc

        raise NotImplementedError(
            f"Cannot encode term with symbol kind {t.symbol.kind}"
        )

    def _get_constructor_embedding(self, t: "Term"):
        """Retrieve the ConstructorEmbedding for a data constructor term."""
        from formula.solver.type_embeddings import ConstructorEmbedding

        if t.symbol.kind == "ConSymb":
            sort_symbol = t.symbol.sort_symbol
        else:
            sort_symbol = t.symbol.sort_symbol

        sort_term = self.solver.index.mk_apply(sort_symbol, [])
        return self.solver.type_embedder.get_embedding(sort_term)

    def _encode_base_op(
        self,
        t: "Term",
        child_encs: List[z3.ExprRef],
        facts: Optional["SymExecuter"],
    ) -> z3.ExprRef:
        """Encode an arithmetic or relational base operation."""
        ctx = self.solver.context
        op = t.symbol.op_kind

        if op == "Add":
            return child_encs[0] + child_encs[1]
        elif op == "Sub":
            return child_encs[0] - child_encs[1]
        elif op == "Mul":
            return child_encs[0] * child_encs[1]
        elif op == "Div":
            return child_encs[0] / child_encs[1]
        elif op == "Lt":
            return child_encs[0] < child_encs[1]
        elif op == "Le":
            return child_encs[0] <= child_encs[1]
        elif op == "Gt":
            return child_encs[0] > child_encs[1]
        elif op == "Ge":
            return child_encs[0] >= child_encs[1]
        elif op == "Neq":
            return child_encs[0] != child_encs[1]
        elif op == "SymCount":
            return self._get_sym_count_expr(facts, t, child_encs)
        elif op == "SymAnd":
            t_val, _ = self.get_term(facts.index.true_value)
            f_val, _ = self.get_term(facts.index.false_value)
            return z3.If(
                t_val == child_encs[0],
                z3.If(t_val == child_encs[1], t_val, f_val),
                f_val,
            )
        elif op == "SymAndAll":
            t_enc, _ = self.get_term(facts.index.true_value)
            f_enc, _ = self.get_term(facts.index.false_value)
            bool_exprs = [t_enc == c for c in child_encs]
            curr_expr = None
            for be in bool_exprs:
                if curr_expr is None:
                    curr_expr = z3.If(be, t_enc, f_enc)
                else:
                    curr_expr = z3.If(be, curr_expr, f_enc)
            self._encodings[t] = curr_expr
            return curr_expr
        elif op == "SymMax":
            return z3.If(child_encs[0] > child_encs[1], child_encs[0], child_encs[1])
        else:
            raise NotImplementedError(f"Base operation {op} not implemented")

    def _get_sym_count_expr(
        self,
        facts: "SymExecuter",
        t: "Term",
        child_encs: List[z3.ExprRef],
    ) -> z3.ExprRef:
        """Build a symbolic count expression."""
        ctx = self.solver.context
        exprs: List[z3.ArithRef] = [child_encs[0]]

        index = int(t.args[1].symbol.raw)
        compr_terms = facts.get_symbolic_count_term(t.args[2], index)
        all_bool_exprs: List[z3.BoolRef] = []

        for i in range(2, len(compr_terms.args)):
            bool_expr = facts.get_side_constraints(compr_terms.args[i])
            all_bool_exprs.append(bool_expr)
            exprs.append(z3.If(bool_expr, z3.IntVal(1), z3.IntVal(0)))

        # Equality decrements
        for i in range(len(all_bool_exprs)):
            for j in range(i + 1, len(all_bool_exprs)):
                e1_term = compr_terms.args[i + 2].args[0]
                e2_term = compr_terms.args[j + 2].args[0]
                e1_enc, _ = self.get_term(e1_term, facts)
                e2_enc, _ = self.get_term(e2_term, facts)
                cond = z3.And(
                    e1_enc == e2_enc,
                    all_bool_exprs[i],
                    all_bool_exprs[j],
                )
                exprs.append(z3.If(cond, z3.IntVal(-1), z3.IntVal(0)))

        return z3.Sum(exprs)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(t: "Term") -> "Term":
        """Apply normalizing rewrites. Currently the identity."""
        return t

    def debug_print(self) -> None:
        for term, enc in self._encodings.items():
            emb = self.solver.type_embedder.get_embedding_by_sort(enc.sort())
            print(f"Entry: {term.debug_get_small_term_string()}")
            print(f"   Representation: {emb.type_term.debug_get_small_term_string()}")
            print(f"   Encoding: {enc}")
