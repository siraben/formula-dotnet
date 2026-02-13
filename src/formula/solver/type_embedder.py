"""
Port of Src/Core/Solver/TypeEmbedding/TypeEmbedder.cs

Manages the creation and lookup of type embeddings that map FORMULA types
to Z3 sorts and back.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import z3

from formula.solver.type_embeddings import (
    ConstructorEmbedding,
    EnumEmbedding,
    ITypeEmbedding,
    IntegerEmbedding,
    IntRangeEmbedding,
    NaturalEmbedding,
    NegIntegerEmbedding,
    PosIntegerEmbedding,
    RealEmbedding,
    SingletonEmbedding,
    StringEmbedding,
    TypeEmbeddingKind,
    UnionEmbedding,
)

if TYPE_CHECKING:
    from formula.common.terms import (
        AppFreeCanUnn,
        BaseSortKind,
        Symbol,
        Term,
        TermIndex,
    )


class TypeEmbedder:
    """
    Orchestrates the creation and retrieval of type embeddings.

    The embedder maps FORMULA type terms to Z3 sorts through a collection of
    ``ITypeEmbedding`` instances.  It also caches type intersections and union
    factorisations so that repeated queries are fast.
    """

    def __init__(
        self,
        index: "TermIndex",
        context: z3.Context,
        base_sort_costs: Dict[str, int],
    ):
        self.index: "TermIndex" = index
        self.context: z3.Context = context

        # lookup tables
        self._sort_to_embedding: Dict[z3.SortRef, ITypeEmbedding] = {}
        self._type_to_embedding: Dict["Term", ITypeEmbedding] = {}

        # Caches for intersections
        self._intr_cache: Dict[Tuple["Term", "Term"], Tuple[Optional["Term"], Optional["AppFreeCanUnn"]]] = {}

        # Factorisation cache:  type -> (int_factors, cnst_factors)
        self._type_to_factors: Dict["Term", Tuple[List[ITypeEmbedding], List[ITypeEmbedding]]] = {}

        # Atom / range -> cost -> list of embeddings
        self._type_atoms_to_embeddings: Dict["Term", Dict[int, List[ITypeEmbedding]]] = {}
        self._type_rngs_to_embeddings: Dict["Term", Dict[int, List[ITypeEmbedding]]] = {}

        # term -> AppFreeCanUnn
        self._term_to_unn: Dict["Term", "AppFreeCanUnn"] = {}

        # ----- Build base-sort embeddings -----
        self._register(RealEmbedding(self, base_sort_costs.get("Real", 10)))
        self._register(IntegerEmbedding(self, base_sort_costs.get("Integer", 11)))
        self._register(NaturalEmbedding(self, base_sort_costs.get("Natural", 12)))
        self._register(PosIntegerEmbedding(self, base_sort_costs.get("PosInteger", 13)))
        self._register(NegIntegerEmbedding(self, base_sort_costs.get("NegInteger", 13)))
        self._register(StringEmbedding(self, base_sort_costs.get("String", 10)))

        # ----- Build finite enumerations, constructor / union types -----
        sort_to_index: Dict["Term", Tuple[int, "Symbol"]] = {}
        self._mk_enum_types(index.symbol_table.root, sort_to_index)
        self._mk_con_unn_types(sort_to_index)
        self._set_default_values()
        self._register_embedding_atoms()

    # ==================================================================
    # Public API
    # ==================================================================

    def get_embedding(self, type_term: "Term") -> ITypeEmbedding:
        """Look up the embedding registered for *type_term*."""
        return self._type_to_embedding[type_term]

    def get_embedding_by_sort(self, sort: z3.SortRef) -> ITypeEmbedding:
        """Look up the embedding registered for Z3 *sort*."""
        return self._sort_to_embedding[sort]

    def get_embedding_by_base_sort(self, sort_kind: str) -> ITypeEmbedding:
        idx = self.index
        type_term = idx.mk_apply(idx.symbol_table.get_sort_symbol(sort_kind), [])
        return self._type_to_embedding[type_term]

    def get_union(self, t: "Term") -> "AppFreeCanUnn":
        if t not in self._term_to_unn:
            from formula.common.terms import AppFreeCanUnn
            unn = AppFreeCanUnn(t)
            self._term_to_unn[t] = unn
        return self._term_to_unn[t]

    def get_intersection(
        self,
        t1: "Term",
        t2: "Term",
    ) -> Tuple[Optional["Term"], Optional["AppFreeCanUnn"]]:
        """
        Return ``(intr_term, app_free_can_unn)`` for the intersection of *t1*
        and *t2*.  Returns ``(None, None)`` if the intersection is empty.
        """
        key = (t1, t2) if id(t1) <= id(t2) else (t2, t1)
        if key in self._intr_cache:
            return self._intr_cache[key]

        intr = self.index.mk_intersection(t1, t2)
        if intr is None:
            result: Tuple[Optional["Term"], Optional["AppFreeCanUnn"]] = (None, None)
        else:
            from formula.common.terms import AppFreeCanUnn
            result = (intr, AppFreeCanUnn(intr))
        self._intr_cache[key] = result
        return result

    def get_factorizations(
        self,
        type_term: "Term",
    ) -> Tuple[List[ITypeEmbedding], List[ITypeEmbedding]]:
        return self._type_to_factors[type_term]

    def mk_ground(self, t: "Term", embedding: ITypeEmbedding) -> z3.ExprRef:
        """
        Encode the ground FORMULA term *t* as a Z3 expression using
        *embedding*.
        """
        if embedding.kind == TypeEmbeddingKind.Union:
            # For unions, wrap the inner encoding in the appropriate box
            inner_emb = embedding.get_unboxed_embedding(t.symbol)
            inner_enc = self.mk_ground(t, inner_emb)
            return embedding.mk_ground(None, [inner_enc])
        elif t.symbol.is_data_constructor:
            child_encs = []
            con_emb = embedding
            for i, arg in enumerate(t.args):
                arg_sort = con_emb.z3_constructor.accessor(i).range()
                arg_emb = self.get_embedding_by_sort(arg_sort)
                child_encs.append(self.mk_ground(arg, arg_emb))
            return con_emb.mk_ground(t.symbol, child_encs)
        else:
            return embedding.mk_ground(t.symbol, [])

    def mk_equality(self, left: z3.ExprRef, right: z3.ExprRef) -> z3.BoolRef:
        """Return a constraint that is true iff *left* == *right* (type-aware)."""
        left_te = self.get_embedding_by_sort(left.sort())
        right_te = self.get_embedding_by_sort(right.sort())
        test = left_te.mk_test(left, right_te.type_term)
        coerced = right_te.mk_coercion(left)
        return z3.And(test, coerced == right)

    def choose_representation(self, type_term: "Term") -> ITypeEmbedding:
        """
        Choose an embedding that can hold all values inhabiting *type_term*.
        Prefers types with fewer atoms (lower encoding cost).
        """
        # Direct lookup first
        if type_term in self._type_to_embedding:
            return self._type_to_embedding[type_term]

        # Widened type lookup
        unn = self.get_union(type_term)
        wtype = unn.mk_type_term(self.index)
        if wtype in self._type_to_embedding:
            return self._type_to_embedding[wtype]

        # Search for the cheapest embedding whose type is a super-type
        best_emb: Optional[ITypeEmbedding] = None
        best_cost = float("inf")
        for emb in self._sort_to_embedding.values():
            if self.index.is_subtype_widened(wtype, emb.type_term):
                if emb.encoding_cost < best_cost:
                    best_cost = emb.encoding_cost
                    best_emb = emb

        if best_emb is not None:
            return best_emb

        # Fallback: return the first embedding whose type matches
        for emb in self._sort_to_embedding.values():
            return emb

        raise RuntimeError("No suitable embedding found")

    def get_some_constant(self, unn: "AppFreeCanUnn") -> "Term":
        """Return some constant from the union."""
        idx = self.index
        if unn.range_members:
            first_rng = next(iter(unn.range_members.items()))
            return idx.mk_cnst_rational(first_rng[0], 1)
        for s in unn.non_range_members:
            if s.kind in ("BaseCnstSymb", "UserCnstSymb"):
                return idx.mk_apply(s, [])
            if s.kind == "BaseSortSymb":
                sk = s.sort_kind
                if sk in ("Real", "Integer", "Natural"):
                    return idx.zero_value
                elif sk == "PosInteger":
                    return idx.one_value
                elif sk == "NegInteger":
                    return idx.mk_cnst_rational(-1, 1)
                elif sk == "String":
                    return idx.empty_string_value
        raise NotImplementedError("Cannot find a constant in the union")

    # ==================================================================
    # Debug
    # ==================================================================

    def debug_print_embeddings(self) -> None:
        for emb in self._type_to_embedding.values():
            emb.debug_print()

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _register(self, embedding: ITypeEmbedding) -> ITypeEmbedding:
        self._sort_to_embedding[embedding.representation] = embedding
        self._type_to_embedding[embedding.type_term] = embedding
        return embedding

    def _register_embedding_atoms(self) -> None:
        """
        For every atom and range inside each embedding's type, register the
        embedding under the appropriate cost bucket.
        """
        for emb in list(self._sort_to_embedding.values()):
            for t in self._enumerate_type_atoms(emb.type_term):
                target = self._type_atoms_to_embeddings
                if target is None:
                    continue
                if t not in target:
                    target[t] = {}
                cost = emb.encoding_cost
                if cost not in target[t]:
                    target[t][cost] = []
                target[t][cost].append(emb)

    @staticmethod
    def _enumerate_type_atoms(type_term: "Term"):
        """Yield leaf symbols from a type term."""
        if type_term.symbol.arity == 0:
            yield type_term
        for child in type_term.args:
            yield from TypeEmbedder._enumerate_type_atoms(child)

    def _mk_enum_types(
        self,
        ns: "Namespace",
        sort_to_index: Dict["Term", Tuple[int, "Symbol"]],
    ) -> None:
        """Walk the namespace tree and register constructor / map symbols."""
        idx = self.index
        for s in ns.symbols:
            if s.kind in ("ConSymb", "MapSymb"):
                sort_sym = s.sort_symbol
                type_term = idx.mk_apply(sort_sym, [])
                if type_term not in sort_to_index:
                    sort_to_index[type_term] = (len(sort_to_index), s)
                # Register canonical argument types
                for i in range(s.arity):
                    arg_type = idx.get_canonical_term(s, i)
                    if arg_type not in sort_to_index and arg_type not in self._type_to_embedding:
                        sort_to_index[arg_type] = (len(sort_to_index), s)
        for child_ns in ns.children:
            self._mk_enum_types(child_ns, sort_to_index)

    def _mk_con_unn_types(
        self,
        sort_to_index: Dict["Term", Tuple[int, "Symbol"]],
    ) -> None:
        """
        Build mutually recursive Z3 datatypes for all constructor and union
        embeddings.
        """
        if not sort_to_index:
            return

        idx = self.index
        id_to_embedding: Dict[int, ITypeEmbedding] = {}
        for type_term, (uid, sym) in sort_to_index.items():
            if type_term.symbol.kind == "UserSortSymb":
                emb = ConstructorEmbedding(self, sym, sort_to_index)
                id_to_embedding[uid] = emb
            else:
                emb = UnionEmbedding(self, type_term, sort_to_index)
                id_to_embedding[uid] = emb

        # Build Z3 datatypes
        sort_names = [""] * len(id_to_embedding)
        for uid, emb in id_to_embedding.items():
            if emb.kind == TypeEmbeddingKind.Constructor:
                sort_names[uid] = emb.constructor.full_name
            else:
                sort_names[uid] = emb.name

        # For the simple case, create independent datatypes
        for uid, emb in id_to_embedding.items():
            if emb.kind == TypeEmbeddingKind.Constructor:
                ce = emb
                arity = ce.constructor.arity
                dt = z3.Datatype(sort_names[uid], ctx=self.context)
                field_names = [f"Get_{ce.constructor.full_name}_{i}" for i in range(arity)]
                field_sorts = []
                for i in range(arity):
                    arg_type = idx.get_canonical_term(ce.constructor, i)
                    if arg_type in self._type_to_embedding:
                        field_sorts.append(self._type_to_embedding[arg_type].representation)
                    else:
                        # Self-reference or forward reference: use IntSort as placeholder
                        field_sorts.append(z3.IntSort(ctx=self.context))
                args = [(field_names[i], field_sorts[i]) for i in range(arity)]
                dt.declare(ce.constructor.full_name, *args)
                sort = dt.create()
                ce.set_representation(sort)
                ce.set_z3_constructor(sort.constructor(0))
                self._register(ce)
            else:
                ue = emb
                # Union with a single boxing constructor per component
                dt = z3.Datatype(sort_names[uid], ctx=self.context)
                # Add a default boxing constructor
                dt.declare(f"Box_{ue.name}_default", ("Unbox_default", z3.IntSort(ctx=self.context)))
                sort = dt.create()
                ue.set_representation(sort)
                ue.add_boxer(z3.IntSort(ctx=self.context), sort.constructor(0))
                self._register(ue)

    def _set_default_values(self) -> None:
        """Set default member values for constructor and union embeddings."""
        idx = self.index
        for emb in list(self._type_to_embedding.values()):
            if emb.kind == TypeEmbeddingKind.Constructor and emb.default_member is None:
                ce = emb
                args = []
                for i in range(ce.constructor.arity):
                    arg_type = idx.get_canonical_term(ce.constructor, i)
                    if arg_type in self._type_to_embedding:
                        arg_emb = self._type_to_embedding[arg_type]
                        args.append(arg_emb.default_member[0])
                    else:
                        args.append(idx.zero_value)
                term = idx.mk_apply(ce.constructor, args)
                enc = self.mk_ground(term, ce)
                ce.set_default_member(term, enc)
            elif emb.kind == TypeEmbeddingKind.Union and emb.default_member is None:
                ue = emb
                # Pick some constant
                try:
                    unn = self.get_union(ue.type_term)
                    const = self.get_some_constant(unn)
                    enc = self.mk_ground(const, ue)
                    ue.set_default_member(const, enc)
                except Exception:
                    # Fallback
                    pass
