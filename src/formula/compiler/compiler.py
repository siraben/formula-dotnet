"""
Port of Microsoft.Formula.Compiler.Compiler (Compiler.cs).

The Compiler is the main orchestrator of the FORMULA compilation pipeline.
It drives the following sequential stages:

1. **RegisterModules** -- Generate a ``Configuration`` for every newly-loaded
   program and register all top-level modules in each program's config.

2. **ApplyConfiguration** -- Walk every ``Config`` node and dispatch its
   ``Setting`` children (defaults, plugin registrations, per-plugin
   settings).  Build a dependency graph of configurations and check for
   cycles.

3. **BuildModuleDependencies** -- Resolve every ``ModRef`` node, create
   plugin instances, and build a module dependency graph.  Topologically
   sort the graph and check for cycles.

4. **EliminateQuotations** -- For each module, use configured parser
   plugins to replace ``Quote`` nodes with concrete AST fragments.
   The output is stored as a "reduced" form in a ``ModuleData``.

5. **BuildModules** -- Traverse modules in dependency order and for each:
   a. Build a ``SymbolTable``.
   b. Depending on module kind, build a ``FactSet`` (model), ``RuleTable``
      (domain/transform), or ``CoreTSystem`` (TSystem).
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
)

from formula.compiler.configuration import (
    Configuration,
    CnstKind,
    EnvParams,
    Flag,
    Location,
    NodeKind,
    SeverityKind,
)
from formula.compiler.module_data import ModuleData, PhaseKind
from formula.compiler.fact_set import FactSet
from formula.compiler.loader import InstallKind, InstallResult


# ---------------------------------------------------------------------------
# Lightweight dependency-collection helper
# ---------------------------------------------------------------------------

class DependencyCollection:
    """
    A directed graph used to track configuration and module dependencies.
    Supports topological sorting and SCC detection.
    """

    def __init__(self) -> None:
        self._edges: Dict[Any, List[Tuple[Any, Any]]] = {}  # src -> [(dst, label)]
        self._nodes: set = set()

    def add(self, src: Any, dst: Any = None, label: Any = None) -> None:
        self._nodes.add(src)
        if dst is not None:
            self._nodes.add(dst)
            self._edges.setdefault(src, []).append((dst, label))

    def get_topological_sort(
        self, cancel: Optional[Callable[[], bool]] = None
    ) -> Tuple[List[Any], int]:
        """
        Return (sorted_nodes, n_sccs) where sorted_nodes are in dependency
        order.  SCCs with more than one member indicate cycles.
        """
        cancel = cancel or (lambda: False)

        # Kahn's algorithm
        in_degree: Dict[Any, int] = {n: 0 for n in self._nodes}
        for src, dests in self._edges.items():
            for dst, _ in dests:
                in_degree[dst] = in_degree.get(dst, 0) + 1

        queue = [n for n in self._nodes if in_degree.get(n, 0) == 0]
        result: list = []
        while queue:
            if cancel():
                break
            node = queue.pop(0)
            result.append(_DepNode(node))
            for dst, _ in self._edges.get(node, []):
                in_degree[dst] -= 1
                if in_degree[dst] == 0:
                    queue.append(dst)

        # Nodes not in result form cycles
        cycle_nodes = self._nodes - {r.resource for r in result}
        n_sccs = 1 if cycle_nodes else 0

        return result, n_sccs

    def get_sccs(
        self, cancel: Optional[Callable[[], bool]] = None
    ) -> List[Any]:
        """Return strongly connected components (Tarjan's)."""
        cancel = cancel or (lambda: False)

        index_counter = [0]
        stack: list = []
        lowlink: dict = {}
        index: dict = {}
        on_stack: set = set()
        sccs: list = []

        def strongconnect(v):
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w, _ in self._edges.get(v, []):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                component = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    component.append(w)
                    if w == v:
                        break
                sccs.append(component)

        for v in self._nodes:
            if cancel():
                break
            if v not in index:
                strongconnect(v)

        return sccs


class _DepNode:
    """Wrapper returned by topological sort."""

    NORMAL = "normal"

    def __init__(self, resource: Any, kind: str = "normal") -> None:
        self.resource = resource
        self.kind = kind


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class Compiler:
    """
    Main compilation orchestrator for FORMULA 2.0.

    Parameters
    ----------
    env : Any
        The compiler environment (``Env``) carrying global parameters,
        the program cache, and factory methods.
    result : InstallResult
        Accumulator for touched programs and diagnostic flags.
    cancel : callable, optional
        Returns True when cancellation is requested.
    """

    def __init__(
        self,
        env: Any,
        result: InstallResult,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.env = env
        self.result = result
        self._cancel = cancel or (lambda: False)

    # ===== Static helpers ===================================================

    @staticmethod
    def try_get_reduced_form(module: Any) -> Tuple[bool, Any]:
        """
        If *module* has been processed by the compiler, return its reduced
        form (quotation-free AST).
        """
        node = getattr(module, "node", module)
        mod_data = getattr(node, "compiler_data", None)
        if isinstance(mod_data, ModuleData):
            return True, mod_data.reduced
        return False, None

    @staticmethod
    def try_get_symbol_table(module: Any) -> Tuple[bool, Any]:
        """
        If *module* has been processed past the TypesDefined phase,
        return its SymbolTable.
        """
        node = getattr(module, "node", module)
        mod_data = getattr(node, "compiler_data", None)
        if isinstance(mod_data, ModuleData) and mod_data.symbol_table is not None:
            return True, mod_data.symbol_table
        return False, None

    @staticmethod
    def try_get_type_environment(node: Any) -> Tuple[bool, Any]:
        """Return the TypeEnvironment attached to *node*, if any."""
        te = getattr(node, "compiler_data", None)
        # Check if it looks like a TypeEnvironment (duck typing)
        if te is not None and hasattr(te, "set_type"):
            return True, te
        return False, None

    @staticmethod
    def try_get_target(mod_ref: Any) -> Tuple[bool, Any]:
        """Return the resolved target AST for a ``ModRef`` node."""
        cd = getattr(mod_ref, "compiler_data", None)
        if isinstance(cd, Location):
            return True, cd.ast
        return False, None

    # ===== Main entry point =================================================

    def compile(self, is_query_container: bool = False) -> bool:
        """
        Run the full compilation pipeline.

        Stages executed in order:
        1. RegisterModules
        2. ApplyConfiguration
        3. BuildModuleDependencies
        4. EliminateQuotations
        5. BuildModules
        """
        # Stage 1: RegisterModules
        program_configs = self._register_modules()
        if program_configs is None:
            self.result.succeeded = False

        # Stage 2: ApplyConfiguration
        if self.result.succeeded:
            if not self._apply_configuration(program_configs):
                self.result.succeeded = False

        # Stage 3: BuildModuleDependencies
        new_mod_deps: Optional[DependencyCollection] = None
        if self.result.succeeded:
            ok, new_mod_deps = self._build_module_dependencies(program_configs)
            if not ok:
                self.result.succeeded = False

        # Stage 4: EliminateQuotations
        if self.result.succeeded:
            if not self._eliminate_quotations(is_query_container):
                self.result.succeeded = False

        # Stage 5: BuildModules
        if self.result.succeeded and new_mod_deps is not None:
            if not self._build_modules(new_mod_deps):
                self.result.succeeded = False

        return self.result.succeeded

    # ===== Static quotation elimination (usable outside the pipeline) =======

    @staticmethod
    def eliminate_quotations_static(
        config: Configuration,
        ast: Any,
        flags: List[Flag],
    ) -> Any:
        """
        Eliminate quotations from *ast* using parser plugins from *config*.
        Returns the simplified node, or None on error.
        """
        config_stack: List[Configuration] = [config]
        success = _SuccessToken()

        simplified = _elim_quote_walk(ast, config_stack, success, flags)
        return simplified if success.result else None

    # ===== Private pipeline stages ==========================================

    # ------- Stage 1: RegisterModules ---------------------------------------

    def _register_modules(self) -> Optional[Dict[Any, Configuration]]:
        """
        For every newly-loaded program, create a Configuration and register
        all its top-level modules.
        """
        succeeded = True
        program_configs: Dict[Any, Configuration] = {}

        for tp in self.result.touched:
            prog = tp.program
            if tp.status == InstallKind.Cached:
                # Re-use existing config
                existing_conf = self._get_program_config(prog)
                if existing_conf is not None:
                    program_configs[self._prog_key(prog)] = existing_conf
                continue

            # Create a new configuration for this program
            env_params = getattr(self.env, "parameters", EnvParams())
            config_ast = self._find_config(prog)
            settings = Configuration(env_params, config_ast)

            # Attach to program node
            self._set_config_compiler_data(prog, settings)
            program_configs[self._prog_key(prog)] = settings

            # Register all modules declared in this program
            modules = self._find_modules(prog)
            for mod_node, mod_path in modules:
                loc = Location(ast=mod_node, program=prog)
                ok, reg_flags = settings.register_module(loc)
                if not ok:
                    succeeded = False
                if reg_flags:
                    self.result.add_flags(prog, reg_flags)

        return program_configs if succeeded else program_configs

    # ------- Stage 2: ApplyConfiguration ------------------------------------

    def _apply_configuration(
        self, program_configs: Dict[Any, Configuration]
    ) -> bool:
        """
        Walk every Config node in every newly-loaded program and apply
        its settings.  Check for cyclic configuration dependencies.
        """
        succeeded = True
        config_deps = DependencyCollection()

        for tp in self.result.touched:
            if tp.status == InstallKind.Cached:
                continue

            prog = tp.program
            prog_conf = program_configs.get(self._prog_key(prog))

            configs = self._find_all_configs(prog)
            for conf_node, conf_owner in configs:
                conf = self._get_or_create_config(
                    conf_node, prog_conf, config_deps
                )

                # If the owner is a module, register parent's modules
                if self._is_module(conf_owner):
                    ok, reg_flags = conf.register_modules_and_locals(prog_conf)
                    if not ok:
                        succeeded = False
                    self.result.add_flags(prog, reg_flags)

                # Apply settings
                ok, app_flags = conf.apply_configurations(
                    conf_node, program_configs, config_deps
                )
                if not ok:
                    succeeded = False
                self.result.add_flags(prog, app_flags)

        # Check for cyclic config dependencies
        sccs = config_deps.get_sccs(self._cancel)
        cycle_num = 0
        for scc in sccs:
            if len(scc) > 1:
                cycle_num += 1
                succeeded = False
                for dep in scc:
                    self.result.add_flag(
                        dep,
                        Flag(
                            SeverityKind.Error, dep,
                            f"Configuration dependency cycle #{cycle_num}.",
                            code=80,
                        ),
                    )

        return succeeded

    # ------- Stage 3: BuildModuleDependencies -------------------------------

    def _build_module_dependencies(
        self, program_configs: Dict[Any, Configuration]
    ) -> Tuple[bool, DependencyCollection]:
        """
        Resolve all ModRef nodes, create plugin instances, and build a
        module dependency graph.  Return (succeeded, dep_collection).
        """
        mod_deps = DependencyCollection()
        succeeded = True

        for tp in self.result.touched:
            if tp.status == InstallKind.Cached:
                continue

            prog = tp.program
            modules = self._find_modules(prog)

            for mod_node, mod_path in modules:
                # Create plugins for this module's config
                conf = self._get_module_config(mod_node)
                flags: List[Flag] = []
                if conf is not None:
                    if not conf.create_plugins(flags):
                        succeeded = False

                mod_loc = Location(ast=mod_node, program=prog)
                mod_deps.add(mod_loc)

                # Resolve all ModRef children
                mod_refs = self._find_mod_refs(mod_node)
                for ref_node in mod_refs:
                    ref_name = getattr(ref_node, "name", "")
                    if conf is not None:
                        ok, loc, is_local = conf.try_resolve(
                            ref_node, program_configs, flags
                        )
                        if not ok:
                            succeeded = False
                            if not any(f for f in flags if f.node is ref_node):
                                flags.append(Flag(
                                    SeverityKind.Error, ref_node,
                                    f"Undefined module '{ref_name}'.",
                                    code=81,
                                ))
                            continue

                        # Tag the ModRef with the resolved location
                        ref_node.compiler_data = loc

                        if not is_local:
                            mod_deps.add(loc, mod_loc, ref_node)

                self.result.add_flags(prog, flags)

        # Topological sort and check for cycles
        sorted_deps, n_cycles = mod_deps.get_topological_sort(self._cancel)
        if n_cycles > 0:
            succeeded = False
            # Flag all nodes not present in the topo sort
            sorted_set = {d.resource for d in sorted_deps}
            for node in mod_deps._nodes:
                if node not in sorted_set:
                    self.result.add_flag(
                        getattr(node, "program", node),
                        Flag(
                            SeverityKind.Error, node,
                            "Module dependency cycle detected.",
                            code=82,
                        ),
                    )

        return succeeded, mod_deps

    # ------- Stage 4: EliminateQuotations -----------------------------------

    def _eliminate_quotations(self, is_query_container: bool) -> bool:
        """
        For each module in every newly-loaded program, eliminate
        quotation nodes using configured parser plugins.
        """
        succeeded = True
        for tp in self.result.touched:
            if tp.status == InstallKind.Cached:
                continue

            prog = tp.program
            flags: List[Flag] = []
            modules = self._find_modules(prog)

            for mod_node, mod_path in modules:
                if not self._eliminate_module_quotations(
                    is_query_container, mod_node, flags
                ):
                    succeeded = False

            self.result.add_flags(prog, flags)

        return succeeded

    def _eliminate_module_quotations(
        self,
        is_query_container: bool,
        module: Any,
        flags: List[Flag],
    ) -> bool:
        """
        Eliminate quotations in a single module.  On success, set the
        module's ``compiler_data`` to a new ``ModuleData`` carrying the
        reduced (quotation-free) form.
        """
        config_stack: List[Configuration] = []
        success = _SuccessToken()

        simplified = _elim_quote_walk(module, config_stack, success, flags)

        if self._cancel():
            return False

        if success.result and simplified is not None:
            loc = Location(ast=module)
            mod_data = ModuleData(self.env, loc, simplified, is_query_container)
            module.compiler_data = mod_data
            if simplified is not module:
                simplified.compiler_data = mod_data

        return success.result

    # ------- Stage 5: BuildModules ------------------------------------------

    def _build_modules(self, mod_deps: DependencyCollection) -> bool:
        """
        Walk modules in dependency order.  For each, build a SymbolTable,
        then depending on module kind build a FactSet or RuleTable.
        """
        sorted_deps, _ = mod_deps.get_topological_sort(self._cancel)
        flags: List[Flag] = []
        result = True

        for dep in sorted_deps:
            if dep.kind != _DepNode.NORMAL:
                continue

            node = dep.resource
            if isinstance(node, Location):
                node = node.ast

            nk = getattr(node, "node_kind", None)
            if nk not in (
                NodeKind.Domain,
                NodeKind.Transform,
                NodeKind.TSystem,
                NodeKind.Model,
            ):
                continue

            mod_data = getattr(node, "compiler_data", None)
            if not isinstance(mod_data, ModuleData):
                continue

            # Skip already-compiled modules
            if mod_data.phase != PhaseKind.Reduced:
                continue

            # -- Build SymbolTable -------------------------------------------
            flags.clear()
            symb_table = self._build_symbol_table(mod_data, flags)
            prog = getattr(mod_data.source, "program", node)
            self.result.add_flags(prog, list(flags))

            if self._cancel():
                return False

            if symb_table is None or not getattr(symb_table, "is_valid", True):
                result = False
                continue

            mod_data.passed_phase(PhaseKind.TypesDefined, symb_table)
            flags.clear()

            # -- Build final output (kind-dependent) -------------------------
            if nk == NodeKind.Model:
                fact_set = FactSet(mod_data)
                if fact_set.validate(flags, self._cancel):
                    mod_data.passed_phase(PhaseKind.Compiled, fact_set)
                else:
                    result = False

            elif nk == NodeKind.TSystem:
                # CoreTSystem compilation (placeholder)
                tsys = _CoreTSystemStub(mod_data)
                if tsys.compile(flags, self._cancel):
                    mod_data.passed_phase(PhaseKind.Compiled, tsys)
                else:
                    result = False

            else:
                # Domain / Transform => build RuleTable
                rule_table = self._build_rule_table(mod_data, flags)
                if rule_table is not None:
                    mod_data.passed_phase(PhaseKind.Compiled, rule_table)
                else:
                    result = False

            self.result.add_flags(prog, list(flags))

            if self._cancel():
                return False

        return result

    # ===== AST traversal / extraction helpers ===============================

    @staticmethod
    def _prog_key(prog: Any) -> Any:
        """Hashable key for a program."""
        name = getattr(prog, "name", None)
        if name is not None:
            return name
        node = getattr(prog, "node", prog)
        name = getattr(node, "name", None)
        return name if name is not None else id(prog)

    @staticmethod
    def _find_config(prog: Any) -> Any:
        """Find the top-level Config node of a program."""
        node = getattr(prog, "node", prog)
        config = getattr(node, "config", None)
        return config

    @staticmethod
    def _find_all_configs(prog: Any) -> List[Tuple[Any, Any]]:
        """
        Find all Config nodes in a program.
        Returns [(config_node, owner_node), ...].
        """
        results: list = []
        _walk_for_kind(
            getattr(prog, "node", prog),
            NodeKind.Config,
            results,
            with_parent=True,
        )
        return results

    @staticmethod
    def _find_modules(prog: Any) -> List[Tuple[Any, Any]]:
        """
        Return [(module_node, path), ...] for all top-level modules in *prog*.
        """
        results: list = []
        node = getattr(prog, "node", prog)
        for child in getattr(node, "children", []):
            nk = getattr(child, "node_kind", None)
            if nk in (
                NodeKind.Domain,
                NodeKind.Transform,
                NodeKind.TSystem,
                NodeKind.Model,
            ):
                results.append((child, None))
        return results

    @staticmethod
    def _find_mod_refs(module: Any) -> List[Any]:
        """Find all ModRef nodes beneath *module*."""
        results: list = []
        _walk_for_node_kind(module, NodeKind.ModRef, results)
        return results

    @staticmethod
    def _is_module(node: Any) -> bool:
        nk = getattr(node, "node_kind", None)
        return nk in (
            NodeKind.Domain,
            NodeKind.Transform,
            NodeKind.TSystem,
            NodeKind.Model,
        )

    @staticmethod
    def _get_program_config(prog: Any) -> Optional[Configuration]:
        node = getattr(prog, "node", prog)
        config = getattr(node, "config", None)
        if config is not None:
            cd = getattr(config, "compiler_data", None)
            if isinstance(cd, Configuration):
                return cd
        return None

    @staticmethod
    def _set_config_compiler_data(prog: Any, config: Configuration) -> None:
        node = getattr(prog, "node", prog)
        conf_node = getattr(node, "config", None)
        if conf_node is not None:
            conf_node.compiler_data = config

    @staticmethod
    def _get_or_create_config(
        conf_node: Any,
        parent_conf: Optional[Configuration],
        config_deps: DependencyCollection,
    ) -> Configuration:
        cd = getattr(conf_node, "compiler_data", None)
        if isinstance(cd, Configuration):
            return cd
        env_params = EnvParams()
        conf = Configuration(env_params, conf_node, config_deps)
        conf_node.compiler_data = conf
        return conf

    @staticmethod
    def _get_module_config(mod_node: Any) -> Optional[Configuration]:
        if mod_node is None:
            return None
        config = getattr(mod_node, "config", None)
        if config is not None:
            cd = getattr(config, "compiler_data", None)
            if isinstance(cd, Configuration):
                return cd
        return None

    @staticmethod
    def _build_symbol_table(mod_data: ModuleData, flags: List[Flag]) -> Any:
        """
        Build a SymbolTable for the module from its type declarations.
        """
        from formula.common.symbols import SymbolTable
        from formula.common.op_library import register_ops
        from formula.common.symbol_types import MapKind as SymMapKind

        try:
            symbol_table = SymbolTable(mod_data.env)
            register_ops(symbol_table)

            # Get the AST to walk
            module_ast = mod_data.reduced
            if module_ast is None:
                module_ast = getattr(mod_data.source, "ast", None)
            if module_ast is None:
                return symbol_table

            mod_name = getattr(module_ast, "name", "")
            root_ns = symbol_table.make_namespace(mod_name) if mod_name else symbol_table.root

            # Walk type declarations
            type_decls = getattr(module_ast, "type_decls", [])
            for td in type_decls:
                nk = getattr(td, "node_kind", None)

                if nk == NodeKind.ConDecl:
                    name = td.name
                    fields = td.fields
                    arity = len(fields)
                    is_new = getattr(td, "is_new", False)
                    is_sub = getattr(td, "is_sub", False)
                    con_sym = symbol_table.make_con_symbol(
                        root_ns, name, arity, is_new=is_new, is_sub=is_sub
                    )
                    # Register field labels
                    for f in fields:
                        label = getattr(f, "name", None)
                        if label and label != "_":
                            symbol_table.register_label(label, con_sym)

                elif nk == NodeKind.MapDecl:
                    name = td.name
                    dom_fields = td.dom
                    cod_fields = td.cod
                    dom_arity = len(dom_fields)
                    cod_arity = len(cod_fields)
                    is_partial = getattr(td, "is_partial", False)
                    # Convert API MapKind to symbol_types MapKind
                    api_mk = getattr(td, "map_kind", None)
                    mk_name = api_mk.name if api_mk is not None else "Fun"
                    sym_mk = SymMapKind[mk_name] if hasattr(SymMapKind, mk_name) else SymMapKind.Fun
                    map_sym = symbol_table.make_map_symbol(
                        root_ns, name, dom_arity, cod_arity,
                        map_kind=sym_mk, is_partial=is_partial
                    )
                    for f in dom_fields:
                        label = getattr(f, "name", None)
                        if label and label != "_":
                            symbol_table.register_label(label, map_sym)
                    for f in cod_fields:
                        label = getattr(f, "name", None)
                        if label and label != "_":
                            symbol_table.register_label(label, map_sym)

                elif nk == NodeKind.UnnDecl:
                    name = td.name
                    symbol_table.make_unn_symbol(root_ns, name)

            return symbol_table
        except Exception as exc:
            flags.append(Flag(
                SeverityKind.Error, None,
                f"Failed to build symbol table: {exc}",
                code=70,
            ))
            return _SymbolTableStub(mod_data)

    @staticmethod
    def _build_rule_table(mod_data: ModuleData, flags: List[Flag]) -> Any:
        """
        Build a RuleTable for a domain or transform module.
        """
        from formula.common.rules import RuleTable
        from formula.common.terms import TermIndex

        try:
            symbol_table = mod_data.symbol_table
            if symbol_table is None or isinstance(symbol_table, _SymbolTableStub):
                # Fall back to stub if no real symbol table
                stub = _RuleTableStub(mod_data)
                stub.compile(flags)
                return stub

            index = TermIndex(symbol_table)
            rule_table = RuleTable(index)
            rule_table.stratify()
            return rule_table
        except Exception as exc:
            flags.append(Flag(
                SeverityKind.Error, None,
                f"Failed to build rule table: {exc}",
                code=71,
            ))
            return None


# ---------------------------------------------------------------------------
# Quotation elimination (shared between instance and static methods)
# ---------------------------------------------------------------------------

class _SuccessToken:
    def __init__(self):
        self._ok = True

    def failed(self):
        self._ok = False

    @property
    def result(self):
        return self._ok


def _elim_quote_walk(
    node: Any,
    config_stack: List[Configuration],
    success: _SuccessToken,
    flags: List[Flag],
    cancel: Optional[Callable[[], bool]] = None,
) -> Any:
    """
    Recursively walk the AST, replacing Quote nodes with the AST fragment
    produced by the configured parser plugin.
    """
    cancel = cancel or (lambda: False)
    nk = getattr(node, "node_kind", None)

    # Skip Config nodes
    if nk == NodeKind.Config:
        return node

    # Push configuration if this node owns one
    conf = _try_get_config(node)
    if conf is not None:
        config_stack.append(conf)

    try:
        if nk == NodeKind.Quote:
            return _elim_quote(node, config_stack, success, flags, cancel)

        # Recurse into children
        children = list(getattr(node, "children", []))
        if not children:
            return node

        new_children = []
        any_changed = False
        for child in children:
            new_child = _elim_quote_walk(child, config_stack, success, flags, cancel)
            new_children.append(new_child)
            if new_child is not child:
                any_changed = True

        if not any_changed:
            return node

        return _shallow_clone(node, new_children)
    finally:
        if conf is not None and config_stack and config_stack[-1] is conf:
            config_stack.pop()


def _elim_quote(
    node: Any,
    config_stack: List[Configuration],
    success: _SuccessToken,
    flags: List[Flag],
    cancel: Callable[[], bool],
) -> Any:
    """
    Eliminate a single Quote node using the configured parser plugin.
    """
    if not config_stack:
        flags.append(Flag(
            SeverityKind.Error, node,
            "No active parser configured.", code=90,
        ))
        success.failed()
        return node

    conf = config_stack[-1]
    value = conf.try_get_setting(Configuration.PARSE_ACTIVE_PARSER_SETTING)
    if value is None:
        flags.append(Flag(
            SeverityKind.Error, node,
            "No active parser configured.", code=90,
        ))
        success.failed()
        return node

    parser_name = value.get_string_value()
    parser = conf.try_get_parser_instance(parser_name)
    if parser is None:
        flags.append(Flag(
            SeverityKind.Error, node,
            f"Cannot find parser '{parser_name}'.", code=91,
        ))
        success.failed()
        return node

    # Invoke the parser plugin
    try:
        unquote_prefix = getattr(parser, "unquote_prefix", "")
        result_ast = None
        parse_flags: List[Flag] = []

        if hasattr(parser, "parse"):
            ok = parser.parse(conf, node, result_ast, parse_flags)
            if ok and result_ast is not None:
                # Check that the result contains no nested Quote nodes
                if _contains_quote(result_ast):
                    flags.append(Flag(
                        SeverityKind.Error, node,
                        "Parser did not eliminate quotations.", code=92,
                    ))
                    success.failed()
                    return node
                return result_ast
            elif not ok:
                flags.append(Flag(
                    SeverityKind.Error, node,
                    "Quotation parse failed.", code=93,
                ))
                flags.extend(parse_flags)
                success.failed()
                return node
        else:
            flags.append(Flag(
                SeverityKind.Error, node,
                f"Parser '{parser_name}' does not support parsing.", code=94,
            ))
            success.failed()
            return node

    except Exception as exc:
        flags.append(Flag(
            SeverityKind.Error, node,
            f"Parser plugin exception: {exc}", code=95,
        ))
        success.failed()
        return node

    return node


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_get_config(node: Any) -> Optional[Configuration]:
    config = getattr(node, "config", None)
    if config is not None:
        cd = getattr(config, "compiler_data", None)
        if isinstance(cd, Configuration):
            return cd
    return None


def _contains_quote(node: Any) -> bool:
    """Check whether an AST contains any Quote nodes."""
    nk = getattr(node, "node_kind", None)
    if nk == NodeKind.Quote:
        return True
    for child in getattr(node, "children", []):
        if _contains_quote(child):
            return True
    return False


def _shallow_clone(node: Any, new_children: list) -> Any:
    """Shallow-clone a node with new children."""
    if hasattr(node, "shallow_clone"):
        result = node
        for idx, child in enumerate(new_children):
            result = result.shallow_clone(child, idx)
        return result
    # Fallback wrapper
    return _ClonedNode(node, new_children)


class _ClonedNode:
    def __init__(self, original: Any, children: list):
        self._original = original
        self.children = children
        self.node_kind = getattr(original, "node_kind", None)
        self.compiler_data = getattr(original, "compiler_data", None)

    def __getattr__(self, name):
        if name.startswith("_") or name in ("children", "node_kind", "compiler_data"):
            raise AttributeError(name)
        return getattr(self._original, name)


def _walk_for_kind(
    node: Any, kind: NodeKind, results: list, with_parent: bool = False
) -> None:
    nk = getattr(node, "node_kind", None)
    if nk == kind:
        if with_parent:
            results.append((node, None))
        else:
            results.append(node)
    for child in getattr(node, "children", []):
        if with_parent:
            _walk_for_kind_with_parent(child, kind, results, node)
        else:
            _walk_for_kind(child, kind, results, with_parent=False)


def _walk_for_kind_with_parent(
    node: Any, kind: NodeKind, results: list, parent: Any
) -> None:
    nk = getattr(node, "node_kind", None)
    if nk == kind:
        results.append((node, parent))
    for child in getattr(node, "children", []):
        _walk_for_kind_with_parent(child, kind, results, node)


def _walk_for_node_kind(node: Any, kind: NodeKind, results: list) -> None:
    nk = getattr(node, "node_kind", None)
    if nk == kind:
        results.append(node)
    for child in getattr(node, "children", []):
        _walk_for_node_kind(child, kind, results)


# ---------------------------------------------------------------------------
# Stubs for layers not yet ported
# ---------------------------------------------------------------------------

class _SymbolTableStub:
    """Placeholder SymbolTable."""

    def __init__(self, mod_data: ModuleData) -> None:
        self.mod_data = mod_data
        self.is_valid = True

    def compile(self, flags: List[Flag], cancel=None) -> bool:
        return True


class _RuleTableStub:
    """Placeholder RuleTable."""

    def __init__(self, mod_data: ModuleData) -> None:
        self.mod_data = mod_data

    def compile(self, flags: List[Flag], cancel=None) -> bool:
        return True

    def productivity_check(self, setting: Any, flags: List[Flag]) -> None:
        pass


class _CoreTSystemStub:
    """Placeholder CoreTSystem."""

    def __init__(self, mod_data: ModuleData) -> None:
        self.mod_data = mod_data

    def compile(self, flags: List[Flag], cancel=None) -> bool:
        return True
