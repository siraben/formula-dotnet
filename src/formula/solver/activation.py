"""
Port of Src/Core/Solver/Execution/Activation.cs

An Activation binds a CoreRule to one or two SymElements, representing
a pending rule execution within the symbolic fixpoint computation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from formula.common.rules import CoreRule
    from formula.solver.sym_element import SymElement


class Activation:
    """Represents an activation record for a rule execution."""

    def __init__(
        self,
        rule: "CoreRule",
        find_number: int,
        binding1: Optional["SymElement"] = None,
        binding2: Optional["SymElement"] = None,
    ):
        self.rule: "CoreRule" = rule
        self.find_number: int = find_number
        self.binding1: Optional["SymElement"] = binding1
        self.binding2: Optional["SymElement"] = binding2

    @staticmethod
    def compare(a1: "Activation", a2: "Activation") -> int:
        from formula.solver.sym_element import SymElement

        cmp = SymElement.compare(a1.binding1, a2.binding1)
        if cmp != 0:
            return cmp
        cmp = SymElement.compare(a1.binding2, a2.binding2)
        if cmp != 0:
            return cmp
        return a1.rule.rule_id - a2.rule.rule_id

    def __lt__(self, other: "Activation") -> bool:
        return Activation.compare(self, other) < 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Activation):
            return NotImplemented
        return Activation.compare(self, other) == 0

    def __hash__(self) -> int:
        return hash((
            id(self.binding1) if self.binding1 is not None else 0,
            id(self.binding2) if self.binding2 is not None else 0,
            self.rule.rule_id,
        ))
