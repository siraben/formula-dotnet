"""
Port of Microsoft.Formula.Compiler.FactSet (FactSet.cs).

A FactSet computes and manages the database of ground facts contained in
a (partial) model.  It validates model facts, resolves symbolic constants
(aliases), handles model compositions (imports), compiles the associated
rule table, and provides operations for expanding terms and converting
models to object graphs.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

from formula.compiler.configuration import (
    Configuration,
    CnstKind,
    Flag,
    NodeKind,
    SeverityKind,
    Span,
)
from formula.compiler.constraint_system import SuccessToken
from formula.compiler.module_data import ModuleData


# ---------------------------------------------------------------------------
# AliasData  (inner helper)
# ---------------------------------------------------------------------------

class AliasData:
    """
    Tracks the definition and type of a symbolic constant (alias).
    """

    def __init__(self, symb_cnst: Any, def_node: Any = None) -> None:
        self.smb_cnst: Any = symb_cnst
        self.def_node: Any = def_node
        self.exp_definition: Any = None      # expanded definition term
        self.type: Any = None                # type term

    def try_define(
        self,
        model_fact: Any,
        term: Any,
        aliases: set,
        alias_map: Dict[Any, "AliasData"],
        flags: List[Flag],
    ) -> bool:
        """
        Attempt to define this alias with *term*.  Returns False if the
        alias is already defined (redefinition error).
        """
        if self.exp_definition is not None:
            flags.append(Flag(
                SeverityKind.Error,
                model_fact,
                f"Alias '{getattr(self.smb_cnst, 'name', self.smb_cnst)}' "
                f"is already defined.",
                code=60,
            ))
            return False
        self.exp_definition = term
        return True

    def import_definition(self, exp_def: Any, type_term: Any) -> None:
        self.exp_definition = exp_def
        self.type = type_term


# ---------------------------------------------------------------------------
# FactSet
# ---------------------------------------------------------------------------

class FactSet:
    """
    Validates and stores the facts of a FORMULA model.

    Responsibilities:
    * Parse each ``ModelFact`` node, building ground terms.
    * Resolve and expand symbolic constants (aliases like ``%x``).
    * Import facts from composed sub-models.
    * Compile the associated rule table for derived facts.
    * Provide ``expand()`` for converting AST terms to ``Term`` objects.
    * Provide ``mk_object_graph()`` for producing external representations.

    Parameters
    ----------
    mod_data : ModuleData
        The module data for the model being compiled.
    """

    _CANCEL_CHECK_FREQ: int = 1000

    def __init__(self, mod_data: ModuleData) -> None:
        self._mod_data: ModuleData = mod_data
        self._model: Any = mod_data.reduced          # AST<Model>
        self._index: Any = None                       # TermIndex (created on validate)
        self._rules: Any = None                       # RuleTable

        self._alias_data_map: OrderedDict[Any, AliasData] = OrderedDict()
        self._facts: set = set()                       # Set[Term]
        self._fact_locations: Dict[Any, Any] = {}      # Term -> Node

        # Determine whether to keep fact locations (proof support)
        self._is_keep_fact_locations: bool = False
        self._init_keep_locations()

        # Thread-safety lock for term index (mirrors SpinLock in C#)
        self._term_index_lock = threading.Lock()

    def _init_keep_locations(self) -> None:
        """Check the configuration for proofs_KeepLineNumbers = TRUE."""
        try:
            model_node = getattr(self._model, "node", self._model)
            config = getattr(model_node, "config", None)
            if config is not None:
                conf = getattr(config, "compiler_data", None)
                if isinstance(conf, Configuration):
                    val = conf.try_get_setting(
                        Configuration.PROOFS_KEEP_LINE_NUMBERS_SETTING
                    )
                    if val is not None and val.get_string_value().upper() == "TRUE":
                        self._is_keep_fact_locations = True
        except Exception:
            pass

    # ------- Properties -----------------------------------------------------

    @property
    def source_program(self) -> Any:
        if self._mod_data is not None:
            return getattr(self._mod_data.source, "program", None)
        return None

    @property
    def model(self) -> Any:
        return self._model

    @property
    def index(self) -> Any:
        return self._index

    @property
    def rules(self) -> Any:
        return self._rules

    @property
    def facts(self) -> set:
        return self._facts

    @property
    def is_keep_fact_locations(self) -> bool:
        return self._is_keep_fact_locations

    # ------- Validation (main entry point) ----------------------------------

    def validate(
        self,
        flags: List[Flag],
        cancel: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """
        Validate the model:
        1. Check the domain reference.
        2. Import composed sub-models.
        3. Process each ModelFact, building ground terms.
        4. Resolve alias orientations.
        5. Compile the rule table.

        Returns True on success.
        """
        cancel = cancel or (lambda: False)
        success = SuccessToken()
        model_node = getattr(self._model, "node", self._model)

        # Check for illegal renaming on domain reference
        domain = getattr(model_node, "domain", None)
        if domain is not None:
            rename = getattr(domain, "rename", None)
            if rename:
                flags.append(Flag(
                    SeverityKind.Error, domain,
                    "Renaming operator cannot be used here.", code=61))
                return False

        # Import composed sub-models
        compositions = getattr(model_node, "compositions", [])
        for mr in compositions:
            compiler_data = getattr(mr, "compiler_data", None)
            if not isinstance(compiler_data, dict) and compiler_data is None:
                return False
            # In full implementation, validate containment and import facts
            self._import_composition(mr, success, flags)

        if not success.result:
            return False

        # Process model facts
        model_facts = getattr(model_node, "facts", [])
        check_cancel = 0
        for fact in model_facts:
            check_cancel += 1
            if check_cancel % self._CANCEL_CHECK_FREQ == 0 and cancel():
                return False

            term = self._create_fact(fact, success, flags)
            if term is None:
                continue

            binding = getattr(fact, "binding", None)
            self._facts.add(_term_key(term))

            if self._is_keep_fact_locations:
                match_node = getattr(fact, "match", fact)
                self._fact_locations[_term_key(term)] = match_node

            # Handle alias binding
            if binding is not None:
                alias_name = getattr(binding, "name", None)
                if alias_name:
                    alias_data = self._get_alias_data(alias_name, fact)
                    if not alias_data.try_define(fact, term, set(), self._alias_data_map, flags):
                        success.failed()

        if not success.result or cancel():
            return False

        # Validate alias orientation
        if not self._validate_orientation(flags, cancel):
            success.failed()

        if not success.result or cancel():
            return False

        # Compile the rule table
        self._rules = _RuleTableStub(self._mod_data, self._index)
        if not self._rules.compile(flags, cancel):
            success.failed()

        return success.result and not cancel()

    # ------- Symbolic constant helpers --------------------------------------

    def get_symb_cnst_value(self, symb_cnst: Any) -> Any:
        """
        Return the expanded definition of a symbolic constant.
        Should only be called after successful compilation.
        """
        key = _symb_key(symb_cnst)
        data = self._alias_data_map.get(key)
        return data.exp_definition if data else None

    def get_symb_cnst_type(self, symb_cnst: Any) -> Any:
        """Return the type of a symbolic constant."""
        key = _symb_key(symb_cnst)
        data = self._alias_data_map.get(key)
        if data is not None and data.exp_definition is not None:
            return data.type
        return None

    # ------- Rewriting symbolic constants -----------------------------------

    def convert_symb_cnsts_to_vars(self) -> Tuple[set, Dict[Any, Any]]:
        """
        Rewrite all facts by replacing symbolic constants with variables.
        Returns (rewritten_facts, alias_map).
        """
        rewritten: set = set()
        for f in self._facts:
            rewritten.add(self._rewrite_symb_cnsts(f))

        alias_map: Dict[Any, Any] = {}
        for key, data in self._alias_data_map.items():
            if data.exp_definition is not None:
                alias_map[key] = self._rewrite_symb_cnsts(data.exp_definition)

        return rewritten, alias_map

    # ------- Term expansion -------------------------------------------------

    def expand(self, ast: Any, flags: List[Flag]) -> Any:
        """
        Convert a term AST to a term, expanding symbolic constants.
        Returns None on error.
        Should only be called after successful compilation.
        """
        with self._term_index_lock:
            success = SuccessToken()
            result = self._expand_walk(ast, success, flags)
            return result

    # ------- Fact location --------------------------------------------------

    def try_get_locator(self, term: Any) -> Optional[Any]:
        """
        If ``is_keep_fact_locations`` is True, return the source node
        that produced *term*.
        """
        if not self._is_keep_fact_locations:
            return None
        key = _term_key(term)
        return self._fact_locations.get(key)

    # ------- Object graph ---------------------------------------------------

    def mk_object_graph(
        self,
        result: Any,
        con_map: Dict[str, Callable],
        rat_con: Callable,
        str_con: Callable,
    ) -> None:
        """
        Convert the model to an object graph.
        Should only be called after successful validation.
        """
        term_to_alias: Dict[Any, str] = {}
        for key, data in self._alias_data_map.items():
            if data.exp_definition is not None:
                name = getattr(key, "name", str(key))
                if name.startswith("%"):
                    name = name[1:]
                term_to_alias[_term_key(data.exp_definition)] = name

        for fact_key in self._facts:
            cs_term = self._mk_single_object(
                fact_key, result, term_to_alias, con_map, rat_con, str_con
            )
            if cs_term is not None:
                if hasattr(result, "objects"):
                    result.objects.append(cs_term)

    # ===== Private ==========================================================

    def _create_fact(
        self, fact: Any, success: SuccessToken, flags: List[Flag]
    ) -> Any:
        """
        Convert a ModelFact AST node into a term.
        Simplified walk that handles Cnst, Id, and FuncTerm.
        """
        match = getattr(fact, "match", fact)
        return self._walk_fact(match, success, flags)

    def _walk_fact(
        self, node: Any, success: SuccessToken, flags: List[Flag]
    ) -> Any:
        nk = getattr(node, "node_kind", None)

        if nk == NodeKind.Cnst:
            return getattr(node, "raw", node)

        elif nk == NodeKind.Id:
            name = getattr(node, "name", str(node))
            # Check if it is a symbolic constant (alias reference)
            if name.startswith("%") or name.startswith("_"):
                return name
            return name

        elif nk == NodeKind.FuncTerm:
            func = getattr(node, "function", None)
            args = getattr(node, "args", [])
            func_name = getattr(func, "name", str(func)) if func else "?"

            child_terms = []
            for arg in args:
                ct = self._walk_fact(arg, success, flags)
                if ct is None:
                    success.failed()
                    continue
                child_terms.append(ct)

            if not success.result:
                return None
            return (func_name, tuple(child_terms))

        else:
            # Fallback
            return node

    def _import_composition(
        self, mod_ref: Any, success: SuccessToken, flags: List[Flag]
    ) -> None:
        """Import facts from a composed sub-model."""
        compiler_data = getattr(mod_ref, "compiler_data", None)
        if compiler_data is None:
            return

        # In full implementation: resolve the ModuleData, get its FactSet,
        # check containment, and clone facts with renaming.

    def _validate_orientation(
        self, flags: List[Flag], cancel: Callable[[], bool]
    ) -> bool:
        """
        Validate that aliases are well-oriented (no circular definitions).
        """
        # Build a dependency graph among aliases and check for cycles
        visited: set = set()
        on_stack: set = set()

        for key, data in self._alias_data_map.items():
            if key in visited:
                continue
            if self._has_cycle(key, visited, on_stack, flags):
                return False
        return True

    def _has_cycle(
        self,
        key: Any,
        visited: set,
        on_stack: set,
        flags: List[Flag],
    ) -> bool:
        visited.add(key)
        on_stack.add(key)

        data = self._alias_data_map.get(key)
        if data is not None and data.exp_definition is not None:
            deps = self._extract_alias_deps(data.exp_definition)
            for dep in deps:
                if dep not in visited:
                    if self._has_cycle(dep, visited, on_stack, flags):
                        return True
                elif dep in on_stack:
                    flags.append(Flag(
                        SeverityKind.Error, data.def_node,
                        f"Circular alias definition involving '{key}'",
                        code=62))
                    return True

        on_stack.discard(key)
        return False

    def _extract_alias_deps(self, term: Any) -> List[Any]:
        """Extract alias references from a term."""
        deps: list = []
        if isinstance(term, str) and (term.startswith("%") or term.startswith("_")):
            deps.append(term)
        elif isinstance(term, tuple) and len(term) == 2:
            for arg in term[1]:
                deps.extend(self._extract_alias_deps(arg))
        return deps

    def _get_alias_data(self, name: str, node: Any) -> AliasData:
        key = f"%{name}" if not name.startswith("%") else name
        if key not in self._alias_data_map:
            self._alias_data_map[key] = AliasData(key, node)
        return self._alias_data_map[key]

    def _rewrite_symb_cnsts(self, term: Any) -> Any:
        """Replace symbolic constant references with variable terms."""
        if isinstance(term, str):
            if term.startswith("%"):
                return f"?{term}"
            return term
        if isinstance(term, tuple) and len(term) == 2:
            func_name, args = term
            new_args = tuple(self._rewrite_symb_cnsts(a) for a in args)
            return (func_name, new_args)
        return term

    def _expand_walk(
        self, ast: Any, success: SuccessToken, flags: List[Flag]
    ) -> Any:
        """Walk an AST and expand symbolic constants."""
        nk = getattr(ast, "node_kind", None)
        node = getattr(ast, "node", ast)
        if nk == NodeKind.Id or (isinstance(node, str)):
            name = getattr(node, "name", str(node))
            data = self._alias_data_map.get(name)
            if data is not None and data.exp_definition is not None:
                return data.exp_definition
            return name
        if nk == NodeKind.FuncTerm:
            func = getattr(node, "function", None)
            args = getattr(node, "args", [])
            func_name = getattr(func, "name", str(func)) if func else "?"
            child_terms = []
            for a in args:
                ct = self._expand_walk(a, success, flags)
                if ct is None:
                    success.failed()
                else:
                    child_terms.append(ct)
            if not success.result:
                return None
            return (func_name, tuple(child_terms))
        return node

    def _mk_single_object(
        self,
        term_key: Any,
        result: Any,
        term_to_alias: Dict[Any, str],
        con_map: Dict[str, Callable],
        rat_con: Callable,
        str_con: Callable,
    ) -> Any:
        """Convert a single term into a C#-style object graph element."""
        if isinstance(term_key, (int, float)):
            return rat_con(term_key)
        if isinstance(term_key, str):
            if term_key in con_map:
                return con_map[term_key]([])
            return str_con(term_key)
        if isinstance(term_key, tuple) and len(term_key) == 2:
            func_name, args = term_key
            alias = term_to_alias.get(term_key)
            if alias is not None and hasattr(result, "aliases"):
                existing = result.aliases.get(alias)
                if existing is not None:
                    return existing

            child_objs = []
            for a in args:
                child_objs.append(
                    self._mk_single_object(a, result, term_to_alias, con_map, rat_con, str_con)
                )

            constructor = con_map.get(func_name)
            if constructor is not None:
                obj = constructor(child_objs)
            else:
                obj = (func_name, child_objs)

            if alias is not None and hasattr(result, "aliases"):
                result.aliases[alias] = obj

            return obj
        return term_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _term_key(term: Any) -> Any:
    """Produce a hashable key for a term."""
    if isinstance(term, (str, int, float, tuple)):
        return term
    return id(term)


def _symb_key(symb: Any) -> Any:
    name = getattr(symb, "name", None) or getattr(symb, "full_name", None)
    if name is not None:
        return name
    return symb


class _RuleTableStub:
    """Placeholder RuleTable until the full Common.Rules layer is available."""

    def __init__(self, mod_data: Any, index: Any) -> None:
        self.mod_data = mod_data
        self.index = index

    def compile(self, flags: List[Flag], cancel: Callable[[], bool] = None) -> bool:
        # In full implementation, this builds the rule table from the
        # module's domain/transform rules.
        return True
