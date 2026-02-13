"""Proof tree for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.ProofTree (Src/Core/API/Base/ProofTree.cs).

A ``ProofTree`` records the derivation of a conclusion from premises
via rules in a FORMULA model.  It is produced by the solver/executer
when ``keep_derivations`` is enabled.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from formula.api.nodes import Node, Span


# ---------------------------------------------------------------------------
# Locator -- base class for proof locations
# ---------------------------------------------------------------------------

class Locator:
    """Base class for proof-tree location information.

    A locator describes a position in the AST and/or term index that
    corresponds to a (sub)proof.
    """

    def __init__(self, span: Optional[Span] = None):
        self._span = span if span is not None else Span()

    @property
    def span(self) -> Span:
        return self._span

    def __getitem__(self, index: int) -> "Locator":
        """Return a child locator at *index* (for composite locators)."""
        raise IndexError(f"No child locator at index {index}")


class NodeTermLocator(Locator):
    """Locator pairing an AST node with a term.

    Ported from the C# ``NodeTermLocator`` helper.
    """

    def __init__(self, node: Node, term: Any):
        super().__init__(node.span if node else Span())
        self._node = node
        self._term = term

    @property
    def node(self) -> Node:
        return self._node

    @property
    def term(self) -> Any:
        return self._term

    @staticmethod
    def choose_representative_node(node: Node, term: Any) -> Node:
        """Heuristic: choose a child node whose span best matches *term*."""
        return node

    def __repr__(self) -> str:
        return f"NodeTermLocator({self._node.node_kind.name})"


class CompositeLocator(Locator):
    """Locator composed of multiple child locators.

    Represents a proof location that is the product of argument locations.
    """

    def __init__(self, span: Span, children: Sequence[Locator]):
        super().__init__(span)
        self._children: List[Locator] = list(children)

    @property
    def children(self) -> Sequence[Locator]:
        return list(self._children)

    def __getitem__(self, index: int) -> Locator:
        return self._children[index]

    def __repr__(self) -> str:
        return f"CompositeLocator({len(self._children)} children)"


class ModelFactLocator(Locator):
    """Locator pointing to a specific model fact."""

    def __init__(self, fact_node: Node, term: Any):
        super().__init__(fact_node.span if fact_node else Span())
        self._fact_node = fact_node
        self._term = term

    @property
    def fact_node(self) -> Node:
        return self._fact_node

    @property
    def term(self) -> Any:
        return self._term


# ---------------------------------------------------------------------------
# ProofTree
# ---------------------------------------------------------------------------

class ProofTree:
    """A proof tree showing how a conclusion was derived.

    Ported from Microsoft.Formula.API.ProofTree.

    Each ``ProofTree`` has a *conclusion* (term), an optional *rule*
    (AST node), and zero or more *premises* mapping bound variables
    to sub-proofs.
    """

    DEFAULT_MAX_LOCATIONS = 100

    def __init__(
        self,
        conclusion: Any,
        rule: Optional[Node] = None,
        core_rule: Any = None,
    ):
        self._conclusion = conclusion
        self._rule = rule
        self._core_rule = core_rule
        self._premises: List[Tuple[str, "ProofTree"]] = []
        self._max_locations = self.DEFAULT_MAX_LOCATIONS

    # -- Properties ---------------------------------------------------------

    @property
    def conclusion(self) -> Any:
        """The term that was derived."""
        return self._conclusion

    @property
    def rule(self) -> Optional[Node]:
        """The AST node of the rule that produced this conclusion (None if it is a fact)."""
        return self._rule

    @property
    def core_rule(self) -> Any:
        """Internal core rule object (if available)."""
        return self._core_rule

    @property
    def premises(self) -> Iterator[Tuple[str, "ProofTree"]]:
        """Iterate over (bound_var_name, sub_proof) pairs."""
        return iter(self._premises)

    @property
    def rule_classes(self) -> Sequence[str]:
        """Return the rule classes associated with this proof step."""
        if self._core_rule is not None and hasattr(self._core_rule, "rule_classes"):
            return list(self._core_rule.rule_classes or [])
        return []

    # -- Mutators -----------------------------------------------------------

    def add_subproof(self, bound_var_name: str, subproof: "ProofTree") -> None:
        """Attach a sub-proof for a bound variable."""
        self._premises.append((bound_var_name, subproof))

    # -- Queries ------------------------------------------------------------

    def has_rule_class(self, cls: str) -> bool:
        """Check if this proof step belongs to rule class *cls*."""
        return cls in self.rule_classes

    def compute_locators(self) -> List[Locator]:
        """Compute source locators for this proof.

        Returns a list of :class:`Locator` objects describing where in
        the source AST this derivation comes from.

        Note: full locator computation requires the compiler internals
        (FactSet, TermIndex).  This stub returns a single locator for
        the rule node.
        """
        if self._rule is not None:
            return [NodeTermLocator(self._rule, self._conclusion)]
        return [Locator(Span())]

    # -- Debug printing -----------------------------------------------------

    def debug_print(self, indent: int = 0) -> None:
        """Print a human-readable representation of the proof tree."""
        prefix = "   " * indent
        conclusion_str = str(self._conclusion)
        rule_str = "fact" if self._rule is None else f"({self._rule.span.start_line},{self._rule.span.start_col})"
        print(f"{prefix}{conclusion_str} :- {rule_str}")
        for var_name, sub in self._premises:
            print(f"{prefix}  {var_name} equals")
            sub.debug_print(indent + 1)
        print(f"{prefix}.")
