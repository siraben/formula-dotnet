"""AST query predicates and schema utilities for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.ASTQueries (Src/Core/API/ASTQueries/ASTSchema.cs).

Provides ``NodePred`` for describing path-based queries into FORMULA ASTs,
and ``NodePredFactory`` for constructing them.
"""

from __future__ import annotations

from enum import IntEnum, auto
from typing import Any, Callable, List, Optional, Sequence, Set, Tuple

from formula.api.constants import (
    ChildContextKind,
    ComposeKind,
    NodeKind,
    NodePredicateKind,
)
from formula.api.nodes import Node


# ---------------------------------------------------------------------------
# NodePredAtom -- a single predicate on (NodeKind, ChildContextKind)
# ---------------------------------------------------------------------------

class NodePredAtom:
    """An atomic predicate that matches a node kind in a specific child context.

    Ported from Microsoft.Formula.API.ASTQueries.NodePredAtom.
    """

    def __init__(
        self,
        target_kind: NodeKind,
        child_context: ChildContextKind = ChildContextKind.AnyChildContext,
        is_any_kind: bool = False,
    ):
        self._target_kind = target_kind
        self._child_context = child_context
        self._is_any_kind = is_any_kind

    @property
    def target_kind(self) -> NodeKind:
        return self._target_kind

    @property
    def child_context(self) -> ChildContextKind:
        return self._child_context

    @property
    def is_any_kind(self) -> bool:
        return self._is_any_kind

    def matches(self, node: Node, context: ChildContextKind = ChildContextKind.AnyChildContext) -> bool:
        """Return True if *node* satisfies this predicate in the given context."""
        if self._is_any_kind:
            return True
        kind_ok = node.node_kind == self._target_kind
        ctx_ok = (
            self._child_context == ChildContextKind.AnyChildContext
            or context == ChildContextKind.AnyChildContext
            or self._child_context == context
        )
        return kind_ok and ctx_ok

    def __repr__(self) -> str:
        if self._is_any_kind:
            return "NodePredAtom(*)"
        return f"NodePredAtom({self._target_kind.name}, {self._child_context.name})"


# ---------------------------------------------------------------------------
# NodePred -- composite predicate (atom, false, star, or)
# ---------------------------------------------------------------------------

class NodePred:
    """A predicate that can be composed (OR, star) to describe path queries.

    Ported from Microsoft.Formula.API.ASTQueries.NodePred.
    """

    def __init__(
        self,
        kind: NodePredicateKind = NodePredicateKind.Atom,
        atom: Optional[NodePredAtom] = None,
        children: Optional[List["NodePred"]] = None,
    ):
        self._kind = kind
        self._atom = atom
        self._children = children if children is not None else []

    @property
    def pred_kind(self) -> NodePredicateKind:
        return self._kind

    @property
    def atom(self) -> Optional[NodePredAtom]:
        return self._atom

    @property
    def children(self) -> Sequence["NodePred"]:
        return list(self._children)

    def matches(self, node: Node, context: ChildContextKind = ChildContextKind.AnyChildContext) -> bool:
        """Evaluate this predicate against *node*."""
        if self._kind == NodePredicateKind.false_:
            return False
        if self._kind == NodePredicateKind.Star:
            return True
        if self._kind == NodePredicateKind.Atom:
            return self._atom.matches(node, context) if self._atom else False
        if self._kind == NodePredicateKind.Or:
            return any(c.matches(node, context) for c in self._children)
        return False

    def __repr__(self) -> str:
        return f"NodePred({self._kind.name})"


# ---------------------------------------------------------------------------
# NodePredFactory -- convenience constructors
# ---------------------------------------------------------------------------

class NodePredFactory:
    """Factory for common NodePred instances.

    Ported from ASTSchema helper methods.
    """

    @staticmethod
    def mk_pred_true() -> NodePred:
        """Match any node (star / wildcard)."""
        return NodePred(kind=NodePredicateKind.Star)

    @staticmethod
    def mk_pred_false() -> NodePred:
        """Match no node."""
        return NodePred(kind=NodePredicateKind.false_)

    @staticmethod
    def mk_pred_atom(
        target_kind: NodeKind,
        child_context: ChildContextKind = ChildContextKind.AnyChildContext,
    ) -> NodePred:
        """Match a node of *target_kind* in *child_context*."""
        return NodePred(
            kind=NodePredicateKind.Atom,
            atom=NodePredAtom(target_kind, child_context),
        )

    @staticmethod
    def mk_pred_or(*preds: NodePred) -> NodePred:
        """Disjunction of several predicates."""
        return NodePred(kind=NodePredicateKind.Or, children=list(preds))


# ---------------------------------------------------------------------------
# ASTSchema utilities (query helpers)
# ---------------------------------------------------------------------------

class ASTSchemaQueries:
    """Utility methods matching ASTSchema's query-building helpers.

    The main ``ASTSchema`` class lives in ``constants.py``; this companion
    provides methods that depend on the query predicate types defined here.
    """

    @staticmethod
    def compose_kind_to_string(kind: ComposeKind) -> str:
        if kind == ComposeKind.Includes:
            return "includes"
        if kind == ComposeKind.Extends:
            return "extends"
        return ""
