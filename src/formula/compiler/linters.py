"""
Port of Microsoft.Formula.Compiler.Linters.RuleLinter (RuleLinter.cs).

The RuleLinter validates structural properties of rule bodies that the
main type-checking pass does not cover.  Currently it checks that every
*qualified identifier* (e.g. ``v.field``) used inside a body refers to
a variable that has a corresponding ``find`` binding.
"""

from __future__ import annotations

from typing import Any, List, Set, Tuple

from formula.compiler.configuration import (
    NodeKind,
)


# ---------------------------------------------------------------------------
# RuleLinter
# ---------------------------------------------------------------------------

class RuleLinter:
    """
    Static linter checks for FORMULA rule bodies.

    All methods are ``@staticmethod`` so the linter can be used without
    instantiation, mirroring the C# sealed-class design.
    """

    # ------- Public API -----------------------------------------------------

    @staticmethod
    def validate_body_qualified_ids(body: Any) -> Tuple[bool, List[str]]:
        """
        Check that every qualified identifier (``v.field``) appearing in
        the arguments of a body has a matching ``find`` binding for the
        leading variable ``v``.

        Parameters
        ----------
        body : Any
            A ``Body`` AST node.

        Returns
        -------
        (valid, unbound_vars) : (bool, list[str])
            ``valid`` is True when all qualified ids are properly bound.
            ``unbound_vars`` lists the leading variable fragments that
            lack a corresponding find binding.
        """
        # Step 1: Collect all qualified variable references in args
        qualified_var_ids: Set[str] = set()
        _walk_for_qualified_ids(body, qualified_var_ids)

        # Step 2: Collect all binding variables from Find nodes
        binding_vars: Set[str] = set()
        _walk_for_find_bindings(body, binding_vars)

        # Step 3: Check that every qualified id has a binding
        unbound: List[str] = []
        for var_id in sorted(qualified_var_ids):
            if var_id not in binding_vars:
                unbound.append(var_id)

        return (len(unbound) == 0), unbound


# ---------------------------------------------------------------------------
# Internal tree-walking helpers
# ---------------------------------------------------------------------------

def _walk_for_qualified_ids(node: Any, result: Set[str]) -> None:
    """
    Recursively find Id nodes in argument context that are qualified
    (i.e. contain a dot: ``v.field``).  Collect the leading fragment
    (``v``) of each.
    """
    nk = getattr(node, "node_kind", None)

    if nk == NodeKind.Id:
        name: str = getattr(node, "name", "")
        is_qualified = getattr(node, "is_qualified", None)
        if is_qualified is None:
            # Fallback: check for dots
            is_qualified = "." in name
        if is_qualified:
            fragments = _get_fragments(node, name)
            if fragments:
                result.add(fragments[0])
    else:
        # Recurse into children / args
        for child in _iter_children(node):
            _walk_for_qualified_ids(child, result)


def _walk_for_find_bindings(node: Any, result: Set[str]) -> None:
    """
    Recursively find ``Find`` nodes.  For each that is a *constraint
    find* (``is_constraint`` is True, has a binding, and its match is
    a type term), collect the binding's name.
    """
    nk = getattr(node, "node_kind", None)

    if nk == NodeKind.Find:
        is_constraint = getattr(node, "is_constraint", True)
        binding = getattr(node, "binding", None)
        match = getattr(node, "match", None)
        is_type_term = getattr(match, "is_type_term", False) if match else False

        if is_constraint and binding is not None and is_type_term:
            name = _get_name(binding)
            if name:
                result.add(name)
    else:
        for child in _iter_children(node):
            _walk_for_find_bindings(child, result)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _get_fragments(node: Any, name: str) -> List[str]:
    """
    Return the dot-separated fragments of an Id node.
    Uses the ``fragments`` attribute if available, otherwise splits on ``"."``.
    """
    fragments = getattr(node, "fragments", None)
    if fragments is not None:
        return list(fragments)
    return name.split(".")


def _get_name(node: Any) -> str:
    """Extract the ``name`` string attribute from a node."""
    name = getattr(node, "name", None)
    if name is not None:
        return str(name)
    # Try the generic string attribute accessor
    try:
        ok, val = node.try_get_string_attribute("Name")
        if ok:
            return val
    except (AttributeError, TypeError):
        pass
    return ""


def _iter_children(node: Any):
    """Yield all children of a node, trying several common accessors."""
    children = getattr(node, "children", None)
    if children is not None:
        yield from children
        return
    args = getattr(node, "args", None)
    if args is not None:
        yield from args
        return
    # Try iterating directly
    try:
        yield from node
    except TypeError:
        pass
