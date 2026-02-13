"""AST wrapper and computation utilities for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.AST (Src/Core/API/Base/AST.cs) and
Microsoft.Formula.API.ASTConcr.

The C# code uses a generic ``AST<T>`` interface with ``Compute``,
``FindAny``, ``FindAll``, ``Substitute``, ``Print``, ``DeepClone``,
and ``SaveAs`` methods.  In Python we provide a concrete ``AST`` wrapper
that holds a root node and offers equivalent functionality.
"""

from __future__ import annotations

import io
from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
)

from formula.api.nodes import Node, Span
from formula.api.constants import NodeKind

T = TypeVar("T", bound=Node)
S = TypeVar("S")
R = TypeVar("R")


# ---------------------------------------------------------------------------
# ChildInfo -- describes a child's position within its parent
# ---------------------------------------------------------------------------

class ChildInfo:
    """Describes one step in a path from the root to a descendant node."""

    __slots__ = ("node", "child_index", "context")

    def __init__(self, node: Node, child_index: int = 0, context: Any = None):
        self.node = node
        self.child_index = child_index
        self.context = context

    def __repr__(self) -> str:
        return f"ChildInfo({self.node.node_kind.name}, index={self.child_index})"


# ---------------------------------------------------------------------------
# AST -- concrete wrapper
# ---------------------------------------------------------------------------

class AST:
    """A concrete AST wrapper around a single :class:`Node`.

    Provides utilities for tree computation, querying, printing, and cloning.
    Mirrors the ``AST<T>`` interface and ``ASTConcr<T>`` implementation in C#.
    """

    def __init__(self, node: Node, path: Optional[List[ChildInfo]] = None):
        self._node = node
        self._path: List[ChildInfo] = path if path is not None else []

    # -- Properties ---------------------------------------------------------

    @property
    def root(self) -> Node:
        """The node at the root of the original program tree (or *node* if no path)."""
        if self._path:
            return self._path[0].node
        return self._node

    @property
    def node(self) -> Node:
        """The node at the tip of the path."""
        return self._node

    @property
    def path(self) -> Sequence[ChildInfo]:
        return list(self._path)

    def get_path_parent(self, n: Optional[Node] = None, i: int = 0) -> Optional[Node]:
        """Return the *i*-th parent of the tip node, or the parent of *n* in the path."""
        if n is None:
            idx = len(self._path) - 1 - i
            return self._path[idx].node if 0 <= idx < len(self._path) else None
        for j, ci in enumerate(self._path):
            if ci.node is n and j > 0:
                return self._path[j - 1].node
        return None

    # -- Tree computation ---------------------------------------------------

    def compute(
        self,
        unfold: Callable[[Node], Iterable[Node]],
        fold: Callable[[Node, Iterable[S]], S],
    ) -> S:
        """Bottom-up tree computation starting from *self.node*.

        ``unfold(n)`` returns the children to recurse into.
        ``fold(n, child_results)`` combines child results.
        """
        return self._compute_impl(self._node, unfold, fold)

    def _compute_impl(
        self,
        node: Node,
        unfold: Callable[[Node], Iterable[Node]],
        fold: Callable[[Node, Iterable[S]], S],
    ) -> S:
        children = list(unfold(node))
        child_results = [self._compute_impl(c, unfold, fold) for c in children]
        return fold(node, child_results)

    # -- Query helpers ------------------------------------------------------

    def find_any(self, predicate: Callable[[Node], bool]) -> Optional["AST"]:
        """Return the first descendant (depth-first) satisfying *predicate*, or ``None``."""
        result = self._find_any_impl(self._node, predicate, list(self._path))
        return result

    def _find_any_impl(
        self,
        node: Node,
        predicate: Callable[[Node], bool],
        path: List[ChildInfo],
    ) -> Optional["AST"]:
        if predicate(node):
            return AST(node, list(path))
        for i, child in enumerate(node.children):
            path.append(ChildInfo(node, i))
            result = self._find_any_impl(child, predicate, path)
            if result is not None:
                return result
            path.pop()
        return None

    def find_all(
        self,
        predicate: Callable[[Node], bool],
        visitor: Callable[[Sequence[ChildInfo], Node], None],
    ) -> None:
        """Visit all descendants satisfying *predicate*."""
        self._find_all_impl(self._node, predicate, visitor, list(self._path))

    def _find_all_impl(
        self,
        node: Node,
        predicate: Callable[[Node], bool],
        visitor: Callable[[Sequence[ChildInfo], Node], None],
        path: List[ChildInfo],
    ) -> None:
        if predicate(node):
            visitor(list(path), node)
        for i, child in enumerate(node.children):
            path.append(ChildInfo(node, i))
            self._find_all_impl(child, predicate, visitor, path)
            path.pop()

    # -- Iteration ----------------------------------------------------------

    def __iter__(self) -> Iterator[Node]:
        """Pre-order traversal of the tree rooted at *self.node*."""
        stack: List[Node] = [self._node]
        while stack:
            n = stack.pop()
            yield n
            children = list(n.children)
            stack.extend(reversed(children))

    # -- Cloning ------------------------------------------------------------

    def deep_clone(self) -> "AST":
        """Return a deep clone of this AST (all sharing removed)."""
        return AST(self._node.deep_clone())

    # -- Printing -----------------------------------------------------------

    def print(self, writer: Optional[io.TextIOBase] = None) -> str:
        """Pretty-print this AST.  If *writer* is ``None``, return a string."""
        from formula.api.printing import print_node

        if writer is None:
            buf = io.StringIO()
            print_node(self._node, buf)
            return buf.getvalue()
        print_node(self._node, writer)
        return ""

    def save_as(self, filename: str) -> None:
        """Save this AST to a file."""
        with open(filename, "w", encoding="utf-8") as f:
            self.print(f)

    # -- Factory helpers ----------------------------------------------------

    @staticmethod
    def from_node(node: Node) -> "AST":
        return AST(node)

    def __repr__(self) -> str:
        return f"AST({self._node.node_kind.name})"
