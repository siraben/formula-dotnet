"""
Port of Src/Core/Solver/Execution/SymElement.cs

A symbolic element is a term, possibly with symbolic constants, that exists
in the LFP of the program only for those valuations where the side constraint
is satisfied.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

import z3

if TYPE_CHECKING:
    from formula.common.terms import Term
    from formula.solver.sym_executer import SymExecuter


class ConstraintData:
    """Holds a set of direct Z3 constraints and positive/negative term constraints."""

    def __init__(
        self,
        dir_constraints: Set[z3.BoolRef],
        pos_constraints: Set["Term"],
        neg_constraints: Set["Term"],
    ):
        self.dir_constraints: Set[z3.BoolRef] = set(dir_constraints)
        self.pos_constraints: Set["Term"] = set(pos_constraints)
        self.neg_constraints: Set["Term"] = set(neg_constraints)

    def is_same_constraint_data(
        self,
        exprs: Set[z3.BoolRef],
        pos_terms: Set["Term"],
        neg_terms: Set["Term"],
    ) -> bool:
        return (
            self.dir_constraints == exprs
            and self.pos_constraints == pos_terms
            and self.neg_constraints == neg_terms
        )


class SymElement:
    """
    A symbolic element is a term, possibly with symbolic constants, that exists
    in the LFP of the program only for those valuations where the side
    constraint is satisfied. For backtracking purposes, side constraints map
    from a state index to a side constraint. The overall side constraint is a
    disjunction of the map's image.
    """

    def __init__(
        self,
        term: "Term",
        encoding: Optional[z3.ExprRef],
        context: z3.Context,
    ):
        assert term is not None
        self.term: "Term" = term
        self.encoding: Optional[z3.ExprRef] = encoding
        self.side_constraints: Dict[int, z3.BoolRef] = {}
        self.is_directly_provable: bool = False
        self._constraint_data: List[ConstraintData] = []
        self._cached_constraints: Set[z3.BoolRef] = set()

    # ------------------------------------------------------------------
    # Constraint data management
    # ------------------------------------------------------------------

    def has_constraints(self) -> bool:
        return len(self._constraint_data) > 0

    def set_directly_provable(self) -> None:
        self.is_directly_provable = True

    def add_constraint_data(
        self,
        exprs: Set[z3.BoolRef],
        pos_terms: Set["Term"],
        neg_terms: Set["Term"],
    ) -> None:
        for item in self._constraint_data:
            if item.is_same_constraint_data(exprs, pos_terms, neg_terms):
                return
        self._constraint_data.append(ConstraintData(exprs, pos_terms, neg_terms))

    def contains_constraint(self, expr: z3.BoolRef) -> bool:
        return expr in self._cached_constraints

    # ------------------------------------------------------------------
    # Side-constraint computation
    # ------------------------------------------------------------------

    def _create_and_cache_constraint(
        self,
        ctx: z3.Context,
        curr: Optional[z3.BoolRef],
        next_c: z3.BoolRef,
    ) -> z3.BoolRef:
        self._cached_constraints.add(next_c)
        if curr is None:
            return next_c
        return z3.And(curr, next_c, ctx=ctx)

    def _get_side_constraints_recursive(
        self,
        executer: "SymExecuter",
        processed: Set["Term"],
    ) -> Optional[z3.BoolRef]:
        ctx = executer.solver.context
        t = self.term
        processed.add(t)

        if self.is_directly_provable:
            return z3.BoolVal(True, ctx=ctx)

        top_constraint: Optional[z3.BoolRef] = None

        for constraint in self._constraint_data:
            curr_constraint: Optional[z3.BoolRef] = None
            local_processed = set(processed)

            # Positive constraints
            for pos_term in constraint.pos_constraints:
                if pos_term not in local_processed:
                    next_elem = executer.get_symbolic_term(pos_term)
                    if next_elem is not None:
                        next_c = next_elem._get_side_constraints_recursive(
                            executer, local_processed
                        )
                        if next_c is not None:
                            curr_constraint = self._create_and_cache_constraint(
                                ctx, curr_constraint, next_c
                            )

            # Negative constraints
            local_processed = set(processed)
            for neg_term in constraint.neg_constraints:
                if neg_term not in processed:
                    next_elem = executer.get_symbolic_term(neg_term)
                    if next_elem is not None:
                        next_c = next_elem._get_side_constraints_recursive(
                            executer, local_processed
                        )
                        if next_c is not None:
                            next_c = z3.Not(next_c, ctx=ctx)
                            curr_constraint = self._create_and_cache_constraint(
                                ctx, curr_constraint, next_c
                            )

            # Direct Z3 constraints
            for next_c in constraint.dir_constraints:
                curr_constraint = self._create_and_cache_constraint(
                    ctx, curr_constraint, next_c
                )

            if top_constraint is None:
                top_constraint = curr_constraint
            elif curr_constraint is not None:
                top_constraint = z3.Or(top_constraint, curr_constraint, ctx=ctx)

        return top_constraint

    def get_side_constraints(
        self,
        executer: "SymExecuter",
    ) -> Optional[z3.BoolRef]:
        """
        Compute the disjunction of all side constraint paths for this element.
        Returns a Z3 BoolRef or ``None``.
        """
        ctx = executer.solver.context
        t = self.term

        if self.is_directly_provable:
            return z3.BoolVal(True, ctx=ctx)

        top_constraint: Optional[z3.BoolRef] = None

        for constraint in self._constraint_data:
            curr_constraint: Optional[z3.BoolRef] = None

            # Positive constraints
            for pos_term in constraint.pos_constraints:
                processed: Set["Term"] = set()
                processed.add(t)
                next_elem = executer.get_symbolic_term(pos_term)
                if next_elem is not None:
                    next_c = next_elem._get_side_constraints_recursive(
                        executer, processed
                    )
                    if next_c is not None:
                        curr_constraint = self._create_and_cache_constraint(
                            ctx, curr_constraint, next_c
                        )

            # Negative constraints
            for neg_term in constraint.neg_constraints:
                processed = set()
                processed.add(t)
                next_elem = executer.get_symbolic_term(neg_term)
                if next_elem is not None:
                    next_c = next_elem._get_side_constraints_recursive(
                        executer, processed
                    )
                    if next_c is not None:
                        next_c = z3.Not(next_c, ctx=ctx)
                        curr_constraint = self._create_and_cache_constraint(
                            ctx, curr_constraint, next_c
                        )

            # Direct Z3 constraints
            for next_c in constraint.dir_constraints:
                curr_constraint = self._create_and_cache_constraint(
                    ctx, curr_constraint, next_c
                )

            if top_constraint is None:
                top_constraint = curr_constraint
            elif curr_constraint is not None:
                top_constraint = z3.Or(top_constraint, curr_constraint, ctx=ctx)

        return top_constraint

    # ------------------------------------------------------------------
    # Side-constraint contraction (for back-tracking)
    # ------------------------------------------------------------------

    def contract_side_constraint(self, index: int) -> None:
        """Remove all constraints introduced at or after *index*."""
        keys_to_remove = [k for k in self.side_constraints if k >= index]
        for k in keys_to_remove:
            del self.side_constraints[k]

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @staticmethod
    def compare(e1: Optional["SymElement"], e2: Optional["SymElement"]) -> int:
        """``None`` is the smallest symbolic element."""
        if e1 is None and e2 is None:
            return 0
        if e1 is None:
            return -1
        if e2 is None:
            return 1
        return Term.compare(e1.term, e2.term)

    def debug_print(self) -> None:
        print(self.term.debug_get_small_term_string())
