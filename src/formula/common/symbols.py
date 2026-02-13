"""
Port of Src/Core/Common/Symbols/SymbolTable.cs, Namespace.cs, Symbol.cs.

The SymbolTable class is the central registry that:
  - Builds namespaces from module declarations
  - Registers all user-defined symbols (constructors, maps, unions, constants)
  - Creates and caches base sort / base constant / base op symbols
  - Resolves qualified and unqualified names
  - Constructs type representations
  - Manages relabeling / renaming of namespaces

Namespace is re-exported from symbol_types for convenience.
"""
from __future__ import annotations

import threading
from fractions import Fraction
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

from formula.common.symbol_types import (
    BaseCnstSymb,
    BaseOpSymb,
    BaseSortKind,
    BaseSortSymb,
    CnstKind,
    ConSymb,
    Groundness,
    MapKind,
    MapSymb,
    Namespace,
    OpKind,
    RelKind,
    ReservedOpKind,
    SizeExpr,
    SizeExprKind,
    Symbol,
    SymbolKind,
    UnnSortSymb,
    UnnSymb,
    UserCnstSymb,
    UserCnstSymbKind,
    UserSortSymb,
    UserSymbol,
    _SORT_KIND_NAMES,
)


# Re-export Namespace so users can ``from formula.common.symbols import Namespace``
__all__ = ["SymbolTable", "Namespace"]


class SymbolTable:
    """
    The central symbol registry for a FORMULA module.

    Maintains:
    - The root ``Namespace`` and its hierarchy
    - Caches for base constants (numeric / string), base sorts, base ops
    - A monotonically increasing symbol-id counter
    - Label registration for constructor field labels
    - Name resolution (qualified and unqualified)
    - Relabeling support
    """

    MANGLE_PREFIX = "~"
    NOT_REL_CNSTR_NAME = "notRelational"
    NOT_FUN_CNSTR_NAME = "notFunctional"
    NOT_INJ_CNSTR_NAME = "notInjective"
    NOT_TOTAL_CNSTR_NAME = "notTotal"
    NOT_INV_TOTAL_CNSTR_NAME = "notInvTotal"
    CONFORMS_NAME = "conforms"
    REQUIRES_NAME = "requires"
    ENSURES_NAME = "ensures"
    SC_VALUE_NAME = MANGLE_PREFIX + "scValue"
    _SUB_PREFIX_NAME = MANGLE_PREFIX + "sub"
    _ARG_PREFIX_NAME = MANGLE_PREFIX + "arg"
    _REL_SUB_NAME = MANGLE_PREFIX + "rel"

    _NAMESPACE_SEP = "."

    def __init__(self, env: Any = None) -> None:
        """
        Create a new empty symbol table.

        Parameters
        ----------
        env : optional
            An environment / parameters object (for source-location printing etc.).
        """
        self._env = env
        self._next_id = 0
        self._id_lock = threading.Lock()

        # The root namespace (empty name)
        self._root = Namespace(symbol_table=self)

        # Base sort symbols (one per BaseSortKind)
        self._base_sorts: Dict[BaseSortKind, BaseSortSymb] = {}

        # Cached base constant symbols
        self._string_cnsts: Dict[str, BaseCnstSymb] = {}
        self._rat_cnsts: Dict[Fraction, BaseCnstSymb] = {}

        # Base op symbols (keyed by their op_kind enum value)
        self._op_symbs: Dict[Any, BaseOpSymb] = {}
        self._rel_symbs: Dict[RelKind, BaseOpSymb] = {}
        self._reserved_symbs: Dict[ReservedOpKind, BaseOpSymb] = {}

        # Union sort symbols created for base sorts
        self._unn_sort_symbs: Dict[BaseSortKind, UnnSortSymb] = {}

        # Label -> list of UserSortSymb that have a field with that label
        self._labels: Dict[str, List[UserSortSymb]] = {}

        # Initialise base sorts
        self._init_base_sorts()

    # -- properties --------------------------------------------------------
    @property
    def env(self) -> Any:
        return self._env

    @property
    def root(self) -> Namespace:
        return self._root

    # -- ID generation -----------------------------------------------------
    def _get_next_id(self) -> int:
        with self._id_lock:
            sid = self._next_id
            self._next_id += 1
            return sid

    # -- base sorts --------------------------------------------------------
    def _init_base_sorts(self) -> None:
        """Create and register the built-in sort symbols."""
        for sk in BaseSortKind:
            sym = BaseSortSymb(sk)
            sym.id = self._get_next_id()
            self._base_sorts[sk] = sym

            # Also create the wrapping UnnSortSymb (auto-gen)
            unn = UnnSortSymb(self._root, sym)
            unn.id = self._get_next_id()
            self._unn_sort_symbs[sk] = unn

    def get_sort_symbol(self, sort_kind: BaseSortKind) -> BaseSortSymb:
        """Return the ``BaseSortSymb`` for the given ``BaseSortKind``."""
        return self._base_sorts[sort_kind]

    def get_sort_unn_symbol(self, sort_kind: BaseSortKind) -> UnnSortSymb:
        """Return the ``UnnSortSymb`` wrapper for the given ``BaseSortKind``."""
        return self._unn_sort_symbs[sort_kind]

    # -- base constant symbols ---------------------------------------------
    def get_cnst_symbol(self, value: Any) -> BaseCnstSymb:
        """
        Return the (cached) ``BaseCnstSymb`` for *value*.

        *value* may be an ``int``, ``float``, ``Fraction``, or ``str``.
        """
        if isinstance(value, str):
            sym = self._string_cnsts.get(value)
            if sym is None:
                sym = BaseCnstSymb(value)
                sym.id = self._get_next_id()
                self._string_cnsts[value] = sym
            return sym
        else:
            r = Fraction(value) if not isinstance(value, Fraction) else value
            sym = self._rat_cnsts.get(r)
            if sym is None:
                sym = BaseCnstSymb(r)
                sym.id = self._get_next_id()
                self._rat_cnsts[r] = sym
            return sym

    # -- base op symbols ---------------------------------------------------
    def register_op_symbol(self, sym: BaseOpSymb) -> None:
        """Register a ``BaseOpSymb`` so it can be looked up by its op_kind."""
        sym.id = self._get_next_id()
        if isinstance(sym.op_kind, ReservedOpKind):
            self._reserved_symbs[sym.op_kind] = sym
        elif isinstance(sym.op_kind, RelKind):
            self._rel_symbs[sym.op_kind] = sym
        elif isinstance(sym.op_kind, OpKind):
            self._op_symbs[sym.op_kind] = sym
        else:
            self._op_symbs[sym.op_kind] = sym

    def get_op_symbol(self, op_kind: Any) -> BaseOpSymb:
        """Look up a ``BaseOpSymb`` by its operator kind enum value."""
        if isinstance(op_kind, ReservedOpKind):
            return self._reserved_symbs[op_kind]
        elif isinstance(op_kind, RelKind):
            return self._rel_symbs[op_kind]
        else:
            return self._op_symbs[op_kind]

    def has_op_symbol(self, op_kind: Any) -> bool:
        if isinstance(op_kind, ReservedOpKind):
            return op_kind in self._reserved_symbs
        elif isinstance(op_kind, RelKind):
            return op_kind in self._rel_symbs
        else:
            return op_kind in self._op_symbs

    # -- user symbol registration ------------------------------------------
    def register_symbol(
        self,
        symbol: UserSymbol,
        namespace: Optional[Namespace] = None,
        size_expr: Optional[SizeExpr] = None,
    ) -> bool:
        """
        Add *symbol* to its namespace (or *namespace* if specified).
        Returns True on success.
        """
        ns = namespace or symbol.namespace
        flags: List[Any] = []
        return ns.try_add_symbol(symbol, self._get_next_id, flags, size_expr)

    # -- label registration ------------------------------------------------
    def register_label(self, label: str, sort_symbol: UserSortSymb) -> None:
        """Record that *sort_symbol* has a field named *label*."""
        lst = self._labels.get(label)
        if lst is None:
            lst = []
            self._labels[label] = lst
        lst.append(sort_symbol)

    def get_label_sorts(self, label: str) -> List[UserSortSymb]:
        """Return the list of sorts that have *label* as a field name."""
        return self._labels.get(label, [])

    # -- name resolution ---------------------------------------------------
    def resolve(
        self,
        qualified_name: str,
        from_namespace: Optional[Namespace] = None,
    ) -> Tuple[Optional[UserSymbol], Optional[UserSymbol]]:
        """
        Resolve a (possibly qualified) name to a user symbol.

        Returns ``(symbol, None)`` on unambiguous success,
        ``(symbol1, symbol2)`` if ambiguous, or ``(None, None)`` if not found.
        """
        if from_namespace is None:
            from_namespace = self._root

        parts = qualified_name.split(self._NAMESPACE_SEP)
        if len(parts) == 1:
            return self._resolve_unqualified(parts[0], from_namespace)
        else:
            return self._resolve_qualified(parts, from_namespace)

    def _resolve_unqualified(
        self,
        name: str,
        ns: Namespace,
    ) -> Tuple[Optional[UserSymbol], Optional[UserSymbol]]:
        """Search up the namespace chain for *name*."""
        found: Optional[UserSymbol] = None
        ambig: Optional[UserSymbol] = None
        crnt: Optional[Namespace] = ns
        while crnt is not None:
            sym = crnt.try_get_symbol(name)
            if sym is not None:
                if found is None:
                    found = sym
                else:
                    ambig = sym
                    return (found, ambig)
            # Also search children (for renaming scenarios)
            for child in crnt.children.values():
                sym = child.try_get_symbol(name)
                if sym is not None:
                    if found is None:
                        found = sym
                    elif found is not sym:
                        ambig = sym
                        return (found, ambig)
            crnt = crnt.parent
        return (found, ambig)

    def _resolve_qualified(
        self,
        parts: List[str],
        ns: Namespace,
    ) -> Tuple[Optional[UserSymbol], Optional[UserSymbol]]:
        """Resolve a dotted qualified name."""
        # Navigate through namespace hierarchy
        crnt: Optional[Namespace] = self._root
        for part in parts[:-1]:
            if crnt is None:
                return (None, None)
            child = crnt.try_get_child(part)
            if child is None:
                # Try symbol that acts as a namespace
                return (None, None)
            crnt = child
        if crnt is None:
            return (None, None)
        sym = crnt.try_get_symbol(parts[-1])
        return (sym, None)

    # -- relabeling --------------------------------------------------------
    def relabel(
        self,
        src_prefix: str,
        dst_prefix: str,
        ns: Namespace,
    ) -> Namespace:
        """
        Starting from namespace *ns*, replace the ancestor named
        *src_prefix* with *dst_prefix*.

        Returns the resulting namespace (or *ns* unchanged if no match).
        """
        suffix = ns.split_suffix(None)
        if suffix is None:
            return ns

        # Find and replace
        new_parts: List[str] = []
        replaced = False
        for part in suffix:
            if not replaced and part == src_prefix:
                new_parts.append(dst_prefix)
                replaced = True
            else:
                new_parts.append(part)

        if not replaced:
            return ns

        # Navigate to the target namespace
        crnt = self._root
        for part in new_parts:
            if not part:
                continue
            child = crnt.try_get_child(part)
            if child is None:
                child = crnt.try_add_namespace(part)
            crnt = child  # type: ignore[assignment]
        return crnt  # type: ignore[return-value]

    # -- namespace construction helpers ------------------------------------
    def make_namespace(self, path: str) -> Namespace:
        """
        Ensure the full dotted namespace *path* exists, creating intermediate
        namespaces as needed. Returns the leaf namespace.
        """
        crnt = self._root
        for part in path.split(self._NAMESPACE_SEP):
            if not part:
                continue
            child = crnt.try_get_child(part)
            if child is None:
                child = crnt.try_add_namespace(part)
            crnt = child  # type: ignore[assignment]
        return crnt  # type: ignore[return-value]

    # -- convenience constructors for user symbols -------------------------
    def make_con_symbol(
        self,
        namespace: Namespace,
        name: str,
        arity: int,
        is_new: bool = True,
        is_sub: bool = False,
        is_autogen: bool = False,
    ) -> ConSymb:
        """Create, register, and return a ``ConSymb``."""
        sym = ConSymb(namespace, name, arity, is_new, is_sub, is_autogen)
        self.register_symbol(sym)
        return sym

    def make_map_symbol(
        self,
        namespace: Namespace,
        name: str,
        dom_arity: int,
        cod_arity: int,
        map_kind: MapKind = MapKind.Fun,
        is_partial: bool = False,
        is_autogen: bool = False,
    ) -> MapSymb:
        """Create, register, and return a ``MapSymb``."""
        sym = MapSymb(
            namespace, name, dom_arity, cod_arity,
            map_kind, is_partial, is_autogen,
        )
        self.register_symbol(sym)
        return sym

    def make_unn_symbol(
        self,
        namespace: Namespace,
        name: str,
        is_autogen: bool = False,
    ) -> UnnSymb:
        """Create, register, and return a ``UnnSymb``."""
        sym = UnnSymb(namespace, name, is_autogen)
        self.register_symbol(sym)
        return sym

    def make_user_cnst_symbol(
        self,
        namespace: Namespace,
        name: str,
        cnst_kind: UserCnstSymbKind,
        is_autogen: bool = False,
    ) -> UserCnstSymb:
        """Create, register, and return a ``UserCnstSymb``."""
        sym = UserCnstSymb(namespace, name, cnst_kind, is_autogen)
        self.register_symbol(sym)
        return sym

    def make_variable(
        self,
        namespace: Namespace,
        name: str,
    ) -> UserCnstSymb:
        """Shortcut: create a variable symbol."""
        return self.make_user_cnst_symbol(
            namespace, name, UserCnstSymbKind.Variable, is_autogen=True,
        )

    # -- mangling helpers --------------------------------------------------
    @staticmethod
    def mangle(name: str) -> str:
        """Return a mangled name that cannot collide with user names."""
        return f"{SymbolTable.MANGLE_PREFIX}{name}"

    @staticmethod
    def sub_prefix_name(index: int) -> str:
        return f"{SymbolTable._SUB_PREFIX_NAME}{index}"

    @staticmethod
    def arg_prefix_name(index: int) -> str:
        return f"{SymbolTable._ARG_PREFIX_NAME}{index}"

    # -- sort name utilities -----------------------------------------------
    @staticmethod
    def try_get_sort_name(sort_kind: BaseSortKind) -> Optional[str]:
        return _SORT_KIND_NAMES.get(sort_kind)

    @staticmethod
    def try_get_sort_kind(name: str) -> Optional[BaseSortKind]:
        for sk, sname in _SORT_KIND_NAMES.items():
            if sname == name:
                return sk
        return None

    # -- iteration ---------------------------------------------------------
    def all_symbols(self) -> Iterable[UserSymbol]:
        """Yield every user symbol in the entire namespace tree."""
        return self._root.descendant_symbols

    def all_base_sorts(self) -> Iterable[BaseSortSymb]:
        return self._base_sorts.values()

    def all_base_cnsts(self) -> Iterable[BaseCnstSymb]:
        yield from self._string_cnsts.values()
        yield from self._rat_cnsts.values()

    # -- debugging ---------------------------------------------------------
    def debug_print(self) -> None:
        """Print the symbol table to stdout for debugging."""
        import sys
        self._debug_print_ns(self._root, sys.stdout, 0)

    def _debug_print_ns(self, ns: Namespace, out: Any, indent: int) -> None:
        prefix = "  " * indent
        for name, sym in ns.symbols.items():
            out.write(f"{prefix}{sym.kind.name}: {sym.printable_name} (id={sym.id}, arity={sym.arity})\n")
        for cname, child in ns.children.items():
            out.write(f"{prefix}namespace {child.full_name}:\n")
            self._debug_print_ns(child, out, indent + 1)

    def __repr__(self) -> str:
        n = sum(1 for _ in self.all_symbols())
        return f"<SymbolTable root='{self._root.full_name}' symbols={n}>"
