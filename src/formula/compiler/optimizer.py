"""
Port of Microsoft.Formula.Compiler.Optimizer (Optimizer.cs).

The Optimizer takes a set of find patterns and constraints from a
validated ConstraintSystem and produces an optimised evaluation order.
It uses connected-component analysis and greedy variable-orientation
heuristics to minimise redundant work during rule execution.

Algorithm overview:
1. Register use-lists (which variables appear in which item).
2. Partition items into connected components via union-find on shared
   variables.
3. Within each component, greedily order the find variables by how many
   other variables/constraints they orient.
4. Return an array of ``FindData`` descriptors (one per component)
   that the ``RuleTable`` can compile into executable rules.
"""

from __future__ import annotations

from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)

from formula.compiler.constraint_system import FindData


# ---------------------------------------------------------------------------
# ItemKind
# ---------------------------------------------------------------------------

class ItemKind(Enum):
    Find = 0
    Compr = 1
    Constraint = 2


# ---------------------------------------------------------------------------
# OrientationData  (helper for equality constraints)
# ---------------------------------------------------------------------------

class OrientationData:
    """Tracks whether an equality constraint can orient variables."""

    def __init__(self, lhs_vars: Set[Any], rhs_vars: Set[Any]) -> None:
        self.lhs_vars = lhs_vars
        self.rhs_vars = rhs_vars

    def debug_print(self) -> None:
        print(f"  lhs_vars={self.lhs_vars}, rhs_vars={self.rhs_vars}")


# ---------------------------------------------------------------------------
# ItemData
# ---------------------------------------------------------------------------

class ItemData:
    """
    Metadata for a single item (find pattern or constraint) in the
    optimiser.
    """

    NO_ORDER_ID: int = -1
    NO_COMPONENT_ID: int = -1

    _next_id: int = 0

    def __init__(
        self,
        item: Any,
        pattern: Any = None,
    ) -> None:
        self.item = item
        self.pattern = pattern  # For find items, the match pattern
        self._uid = ItemData._next_id
        ItemData._next_id += 1

        # Determine kind
        if pattern is not None:
            self.kind: ItemKind = ItemKind.Find
        else:
            self.kind = ItemKind.Constraint

        # Variables appearing in this item
        self.variables: Set[Any] = self._extract_variables(item)
        if pattern is not None:
            self.variables |= self._extract_variables(pattern)

        # Equality orientation data (for equality constraints)
        self.eq_data: Optional[OrientationData] = None

        self.component_id: int = self.NO_COMPONENT_ID
        self.order_id: int = self.NO_ORDER_ID

    # -- Ground constraint orientations --------------------------------------

    def add_grnd_cnstr_orients(self, oriented: Set[Any]) -> None:
        """
        If this constraint equates a variable to a ground term, mark
        that variable as grounded.
        """
        if self.eq_data is not None:
            if not self.eq_data.lhs_vars and self.eq_data.rhs_vars:
                oriented.update(self.eq_data.rhs_vars)
            elif not self.eq_data.rhs_vars and self.eq_data.lhs_vars:
                oriented.update(self.eq_data.lhs_vars)

    # -- Triggering ----------------------------------------------------------

    def is_triggerable(
        self, oriented_vars: Set[Any], var_stack: List[Any]
    ) -> bool:
        """
        Returns True if all variables of this item are in *oriented_vars*,
        meaning the item is ready to be evaluated.  As a side-effect,
        pushes newly oriented variables onto *var_stack*.
        """
        for v in self.variables:
            if v not in oriented_vars:
                return False

        # All vars oriented => push any new orientations from this item
        return True

    # -- Comparison ----------------------------------------------------------

    @staticmethod
    def compare(a: "ItemData", b: "ItemData") -> int:
        return (a._uid > b._uid) - (a._uid < b._uid)

    def __lt__(self, other):
        return self._uid < other._uid

    def __eq__(self, other):
        if isinstance(other, ItemData):
            return self._uid == other._uid
        return NotImplemented

    def __hash__(self):
        return self._uid

    # -- Variable extraction -------------------------------------------------

    @staticmethod
    def _extract_variables(term: Any) -> Set[Any]:
        """
        Extract variable symbols from a term representation.
        """
        result: Set[Any] = set()
        _collect_vars(term, result)
        return result


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class Optimizer:
    """
    Optimises the evaluation order of find patterns and constraints.

    Parameters
    ----------
    index : Any
        The ``TermIndex`` that owns the terms.
    constraints : iterable
        Constraint terms from the ConstraintSystem.
    find_patterns : dict
        Mapping from find-variable term to ``(pattern, type)`` tuple.
    """

    def __init__(
        self,
        index: Any,
        constraints: Iterable[Any],
        find_patterns: Dict[Any, Tuple[Any, Any]],
    ) -> None:
        self._index = index
        self._find_patterns: Dict[Any, Tuple[Any, Any]] = dict(find_patterns)
        self._constraints: List[Any] = list(constraints)

    def optimize(
        self,
        rules: Any,
        environment: Any,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> List[FindData]:
        """
        Produce an optimised list of ``FindData`` descriptors.

        Steps:
        1. Build ``ItemData`` for every find and constraint.
        2. Register variable use-lists.
        3. Split into connected components.
        4. Order each component greedily.
        5. Compile partial rules via the rule table.
        """
        cancel = cancel or (lambda: False)

        # -- Step 1: build item data -----------------------------------------
        item_dats: Dict[Any, ItemData] = {}
        use_lists: Dict[Any, Set[ItemData]] = {}

        for var, (pattern, type_) in self._find_patterns.items():
            item = ItemData(var, pattern)
            item_dats[var] = item
            self._register_uses(item, use_lists)

        for con in self._constraints:
            item = ItemData(con)
            item_dats[con] = item
            self._register_uses(item, use_lists)

        # -- Step 2: connected components ------------------------------------
        components = self._compute_components(item_dats, use_lists)

        if not components:
            # No items at all: return a single default FindData
            default = self._compile_partial(rules, environment, None, None, set())
            return [default]

        # -- Step 3/4: order each component and compile ----------------------
        outputs: List[FindData] = []
        for comp_id, component in enumerate(components):
            ordering = self._order_component(comp_id, component, use_lists)
            if not ordering:
                continue

            # Compile the ordered component into FindData
            fd = self._compile_component_ordering(rules, environment, ordering)
            outputs.append(fd)

        return outputs if outputs else [FindData()]

    # ------- Use-list registration ------------------------------------------

    @staticmethod
    def _register_uses(
        item: ItemData, use_lists: Dict[Any, Set[ItemData]]
    ) -> None:
        for v in item.variables:
            if v not in use_lists:
                use_lists[v] = set()
            use_lists[v].add(item)

    # ------- Connected components -------------------------------------------

    def _compute_components(
        self,
        item_dats: Dict[Any, ItemData],
        use_lists: Dict[Any, Set[ItemData]],
    ) -> List[Set[ItemData]]:
        """
        Compute connected components via DFS over shared variable use-lists.
        """
        comp_id = -1
        dfs_stack: List[ItemData] = []

        # Assign component IDs via DFS
        for var, users in use_lists.items():
            for d in users:
                if d.component_id == ItemData.NO_COMPONENT_ID:
                    if not dfs_stack:
                        comp_id += 1
                    d.component_id = comp_id
                    dfs_stack.append(d)

            while dfs_stack:
                top = dfs_stack.pop()
                for v in top.variables:
                    for d in use_lists.get(v, []):
                        if d.component_id == ItemData.NO_COMPONENT_ID:
                            d.component_id = comp_id
                            dfs_stack.append(d)

        # Handle isolated items (no shared variables)
        for key, item in item_dats.items():
            if item.component_id == ItemData.NO_COMPONENT_ID:
                comp_id += 1
                item.component_id = comp_id
                break

        if comp_id < 0:
            return []

        # Group by component
        components: List[Set[ItemData]] = [set() for _ in range(comp_id + 1)]
        for key, item in item_dats.items():
            cid = item.component_id
            if cid == ItemData.NO_COMPONENT_ID:
                cid = comp_id
                item.component_id = cid
            components[cid].add(item)

        return components

    # ------- Greedy ordering ------------------------------------------------

    def _order_component(
        self,
        comp_id: int,
        component: Set[ItemData],
        use_lists: Dict[Any, Set[ItemData]],
    ) -> List[Tuple[Optional[ItemData], List[ItemData]]]:
        """
        Greedily order the find variables in a component.

        Returns a list of (find_item_or_None, [constraint_items]) tuples,
        one per ordering step.
        """
        # Separate finds from constraints
        finds: List[ItemData] = [d for d in component if d.kind == ItemKind.Find]
        order_list: List[Tuple[Optional[ItemData], List[ItemData]]] = []

        if not finds:
            # All constraints, no finds
            all_cons = list(component)
            for d in all_cons:
                d.order_id = 0
            order_list.append((None, all_cons))
            return order_list

        # Collect ground-constraint oriented variables
        grnd_orients: Set[Any] = set()
        for d in component:
            d.add_grnd_cnstr_orients(grnd_orients)

        sel_vars: Set[Any] = set()
        next_order = 0

        while finds:
            best_item: Optional[ItemData] = None
            best_orient_count = -1
            best_oriented_items: Set[ItemData] = set()
            best_oriented_vars: Set[Any] = set()

            for f_item in finds:
                o_items, o_vars, _ = self._get_selection_data(
                    comp_id, f_item, sel_vars, grnd_orients, use_lists
                )

                # Count how many remaining finds are partially oriented
                orient_count = 0
                for other in finds:
                    if other is f_item:
                        continue
                    for v in other.variables:
                        if v in o_vars:
                            orient_count += 1

                if orient_count > best_orient_count or (
                    orient_count == best_orient_count
                    and (best_item is None or len(o_items) > len(best_oriented_items))
                ):
                    best_item = f_item
                    best_orient_count = orient_count
                    best_oriented_items = o_items
                    best_oriented_vars = o_vars

            assert best_item is not None
            finds.remove(best_item)

            ordered_cons: List[ItemData] = []
            for d in best_oriented_items:
                if d.kind != ItemKind.Find:
                    d.order_id = next_order
                    ordered_cons.append(d)

            best_item.order_id = next_order
            sel_vars = best_oriented_vars
            order_list.append((best_item, ordered_cons))
            next_order += 1

        return order_list

    # ------- Selection data -------------------------------------------------

    def _get_selection_data(
        self,
        comp_id: int,
        find_item: ItemData,
        selected_vars: Set[Any],
        grnd_orients: Set[Any],
        use_lists: Dict[Any, Set[ItemData]],
    ) -> Tuple[Set[ItemData], Set[Any], Set[Any]]:
        """
        Compute which items and variables would become oriented if
        *find_item* were selected next.
        """
        oriented_items: Set[ItemData] = set()
        find_var = find_item.item

        if find_var in selected_vars:
            return oriented_items, selected_vars, set()

        oriented_vars = set(selected_vars)
        new_oriented: Set[Any] = set()
        var_stack: List[Any] = list(grnd_orients)
        oriented_vars.add(find_var)
        var_stack.append(find_var)

        while var_stack:
            v = var_stack.pop()
            new_oriented.add(v)
            for d in use_lists.get(v, []):
                if d.order_id != ItemData.NO_ORDER_ID:
                    continue
                if d.component_id != comp_id:
                    continue
                if d in oriented_items:
                    continue
                if d.is_triggerable(oriented_vars, var_stack):
                    oriented_items.add(d)

        return oriented_items, oriented_vars, new_oriented

    # ------- Compilation helpers --------------------------------------------

    def _compile_component_ordering(
        self,
        rules: Any,
        environment: Any,
        ordering: List[Tuple[Optional[ItemData], List[ItemData]]],
    ) -> FindData:
        """
        Compile an ordered component into a single ``FindData`` by
        progressively joining partial rules.
        """
        result: Optional[FindData] = None

        for find_item, cons_items in ordering:
            if find_item is not None:
                pat = self._find_patterns.get(find_item.item, (None, None))
                fd = FindData(find_item.item, pat[0], pat[1])
            else:
                fd = FindData()

            constraint_set: set = {c.item for c in cons_items}

            result = self._compile_partial(rules, environment, result, fd, constraint_set)

        return result if result is not None else FindData()

    @staticmethod
    def _compile_partial(
        rules: Any,
        environment: Any,
        f1: Optional[FindData],
        f2: Optional[FindData],
        constraints: set,
    ) -> FindData:
        """
        Ask the rule table to compile a partial rule.
        Falls back to returning f1 or f2 if the rule table does not support
        the operation yet.
        """
        if hasattr(rules, "compile_partial_rule"):
            return rules.compile_partial_rule(
                f1 or FindData(),
                f2 or FindData(),
                constraints,
                environment,
            )
        # Fallback: return whichever FindData is non-default
        if f1 is not None and not f1.is_default:
            return f1
        if f2 is not None and not f2.is_default:
            return f2
        return FindData()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _collect_vars(term: Any, result: Set[Any]) -> None:
    """Recursively collect variable references from a term."""
    if isinstance(term, str):
        if term.startswith("?"):
            result.add(term)
    elif isinstance(term, tuple):
        for sub in term:
            _collect_vars(sub, result)
    elif hasattr(term, "symbol"):
        sym = term.symbol
        if getattr(sym, "is_variable", False):
            result.add(term)
        for arg in getattr(term, "args", []):
            _collect_vars(arg, result)
