"""Port of Src/CommandLine/CommandInterface.cs.

Provides the ``CommandInterface`` class that dispatches interactive
commands such as *load*, *unload*, *query*, *solve*, *help*, etc.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .interfaces import (
    IChooser,
    IMessageSink,
    SeverityKind,
)
from .option_parser import Options, parse_switch_string
from .task_manager import TaskKind, TaskManager


# ── Command descriptor ────────────────────────────────────────────────

@dataclass
class _Command:
    name: str
    short_name: str
    action: Callable[[str], None]
    help_msg: str


# ── Constants ─────────────────────────────────────────────────────────

EXIT_COMMAND = "exit"
EXIT_SHORT_COMMAND = "x"

_BUSY_MSG = "Busy; cancel or wait until operation completes"
_UNK_CMD_MSG = "Unknown command '{}'"
_UNK_SWITCH_MSG = "Unknown switch '{}'"

# Help strings (mirroring C# string constants)
_SET_INFO = "Sets a variable. Use: set var term."
_DEL_INFO = "Deletes a variable. Use: del var."
_HELP_INFO = "Prints this message."
_EXIT_INFO = "Exits the interface loop."
_SAVE_INFO = "Saves the module modname into file."
_LS_INFO = "Lists environment objects. Use: ls [vars | progs | tasks]"
_LOAD_INFO = "Loads and compiles a file that is not yet loaded. Use: load filename"
_UNLOAD_INFO = "Unloads an installed program and all dependent programs. Use: unload [prog | *]"
_TUNLOAD_INFO = "Unloads a task. Use: tunload [id | *]"
_RELOAD_INFO = "Reloads an installed program and all dependent programs. Use: reload [prog | *]"
_PRINT_INFO = "Prints the installed program with the given name. Use: print progname"
_DET_INFO = "Prints details about the compiled module with the given name. Use: det modname"
_TYPES_INFO = "Prints inferred variable types. Use: types modname"
_RENDER_INFO = "Tries to render the module. Use: render modname"
_VERBOSE_INFO = "Changes verbosity. Use: verbose (on | off)"
_WAIT_INFO = "Changes waiting behavior. Use: wait (on | off) to block until task completes"
_QUERY_INFO = "Start a query task. Use: query model goals"
_SOLVE_INFO = "Start a solve task. Use: solve partial_model max_sols goals"
_APPLY_INFO = "Start an apply task. Use: apply transformstep"
_STATS_INFO = "Prints task statistics. Use: stats task_id [top_k_rule]"
_GEN_DATA_INFO = "Generate C# data model. Use: generate modname"
_TRUTH_INFO = "Test if a ground term is derivable under a model/apply. Use: truth task_id [term]"
_PROOF_INFO = "Enumerate proofs that a ground term is derivable. Use: proof task_id [term]"
_EXTRACT_INFO = "Extract and install a result. Use: extract (app_id | solv_id n) output_name [render_class render_dll]"
_CONFHELP_INFO = "Provides help about module configurations and settings"
_INTERACTIVE_INFO = "use: interactive [on | off], will stop interactive prompting"
_WATCH_INFO = "Use: watch [off | on | prompt] to control watch behavior"
_CORE_INFO = "Prints reduced rule set for domains / transforms. Use: core module_name"
_DOWNGRADE_INFO = "Attempts to downgrade a (partial) model to Formula V1. Use: downgrade module_name"


# ── CommandInterface ──────────────────────────────────────────────────

class CommandInterface:
    """Interactive command dispatcher for the FORMULA 2.0 CLI.

    Parameters
    ----------
    sink : IMessageSink
        Destination for output messages.
    chooser : IChooser
        Digit-choice provider (used for interactive prompts).
    """

    def __init__(self, sink: IMessageSink, chooser: IChooser) -> None:
        self._sink = sink
        self._chooser = chooser
        self._is_verbose: bool = True
        self._task_manager = TaskManager()
        self._cmd_vars: Dict[str, object] = {}
        self._watch_mode: str = "off"
        self._load_order: list[str] = []

        # Loaded programs: program_name_str -> Program AST node
        self._programs: Dict[str, Any] = {}
        # Module index: module_name -> AST node (Domain, Model, etc.)
        self._modules: Dict[str, Any] = {}

        # Build command map (name -> _Command, short_name -> same _Command)
        self._cmd_map: Dict[str, _Command] = {}
        self._all_commands: list[_Command] = []
        self._register_commands()

    # -- public API ----------------------------------------------------

    def do_command(self, command: str) -> bool:
        """Execute *command* (a single line of user input).

        Returns ``True`` on success, ``False`` on error.
        """
        if not command or command.isspace():
            return True

        parts = command.strip().split(None, 1)
        cmd_name = parts[0]
        args = parts[1] if len(parts) == 2 else ""

        cmd = self._cmd_map.get(cmd_name)
        if cmd is None:
            self._sink.write_message_line(
                _UNK_CMD_MSG.format(cmd_name), SeverityKind.Warning
            )
            return False

        start = time.monotonic()
        cmd.action(args)
        elapsed = time.monotonic() - start

        if self._is_verbose:
            self._sink.write_message(f"{elapsed:.2f}s.", SeverityKind.Info)

        return True

    def cancel(self) -> None:
        """Cancel any running operations."""
        pass

    # -- command registration ------------------------------------------

    def _register_commands(self) -> None:
        """Register all supported commands."""

        def _reg(name: str, short: str, action: Callable[[str], None], help_msg: str) -> None:
            cmd = _Command(name, short, action, help_msg)
            self._cmd_map[name] = cmd
            self._cmd_map[short] = cmd
            self._all_commands.append(cmd)

        _reg("exit", "x", self._do_exit, _EXIT_INFO)
        _reg("help", "h", self._do_help, _HELP_INFO)
        _reg("set", "s", self._do_set, _SET_INFO)
        _reg("del", "d", self._do_del, _DEL_INFO)
        _reg("list", "ls", self._do_ls, _LS_INFO)
        _reg("load", "l", self._do_load, _LOAD_INFO)
        _reg("unload", "ul", self._do_unload, _UNLOAD_INFO)
        _reg("tunload", "tul", self._do_tunload, _TUNLOAD_INFO)
        _reg("reload", "rl", self._do_reload, _RELOAD_INFO)
        _reg("save", "sv", self._do_save, _SAVE_INFO)
        _reg("print", "p", self._do_print, _PRINT_INFO)
        _reg("render", "r", self._do_render, _RENDER_INFO)
        _reg("det", "dt", self._do_details, _DET_INFO)
        _reg("verbose", "v", self._do_verbose, _VERBOSE_INFO)
        _reg("wait", "w", self._do_wait, _WAIT_INFO)
        _reg("watch", "wch", self._do_watch, _WATCH_INFO)
        _reg("types", "typ", self._do_types, _TYPES_INFO)
        _reg("query", "qr", self._do_query, _QUERY_INFO)
        _reg("solve", "sl", self._do_solve, _SOLVE_INFO)
        _reg("truth", "tr", self._do_truth, _TRUTH_INFO)
        _reg("proof", "pr", self._do_proof, _PROOF_INFO)
        _reg("apply", "ap", self._do_apply, _APPLY_INFO)
        _reg("stats", "st", self._do_stats, _STATS_INFO)
        _reg("generate", "gn", self._do_generate, _GEN_DATA_INFO)
        _reg("extract", "ex", self._do_extract, _EXTRACT_INFO)
        _reg("confhelp", "ch", self._do_confhelp, _CONFHELP_INFO)
        _reg("core", "cr", self._do_core, _CORE_INFO)
        _reg("downgrade", "dg", self._do_downgrade, _DOWNGRADE_INFO)
        _reg("interactive", "int", self._do_interactive, _INTERACTIVE_INFO)

    # -- individual command handlers -----------------------------------

    def _do_exit(self, s: str) -> None:
        pass  # handled in the main loop

    def _do_help(self, s: str) -> None:
        seen = set()
        for cmd in self._all_commands:
            if cmd.name not in seen:
                seen.add(cmd.name)
                self._sink.write_message_line(
                    f"  {cmd.name} ({cmd.short_name}) - {cmd.help_msg}"
                )

    def _do_set(self, s: str) -> None:
        parts = s.strip().split(None, 1)
        if len(parts) < 2:
            self._sink.write_message_line(_SET_INFO, SeverityKind.Warning)
            return
        var_name, value = parts[0], parts[1]
        self._cmd_vars[var_name] = value
        self._sink.write_message_line(f"Set {var_name} = {value}")

    def _do_del(self, s: str) -> None:
        var_name = s.strip()
        if not var_name:
            self._sink.write_message_line(_DEL_INFO, SeverityKind.Warning)
            return
        if var_name in self._cmd_vars:
            del self._cmd_vars[var_name]
            self._sink.write_message_line(f"Deleted variable '{var_name}'")
        else:
            self._sink.write_message_line(
                f"The variable '{var_name}' is not defined", SeverityKind.Warning
            )

    def _do_ls(self, s: str) -> None:
        arg = s.strip().lower()
        if arg == "vars":
            self._sink.write_message_line("Environment variables:")
            for k, v in sorted(self._cmd_vars.items()):
                self._sink.write_message_line(f"  {k} = {v}")
        elif arg == "tasks":
            rows, widths = self._task_manager.make_task_table()
            for row in rows:
                line = " | ".join(cell.ljust(w) for cell, w in zip(row, widths))
                self._sink.write_message_line(f"  {line}")
        elif arg == "progs":
            for prog in self._load_order:
                self._sink.write_message_line(f"  {prog}")
        else:
            self._sink.write_message_line(_LS_INFO, SeverityKind.Warning)

    def _do_load(self, s: str) -> None:
        filename = s.strip()
        if not filename:
            self._sink.write_message_line(_LOAD_INFO, SeverityKind.Warning)
            return

        # Resolve to absolute path
        abs_path = os.path.abspath(filename)
        if not os.path.isfile(abs_path):
            self._sink.write_message_line(
                f"File not found: {filename}", SeverityKind.Error
            )
            return

        # Parse the file
        from formula.api.parser.parser import Parser
        from formula.api.nodes import ProgramName, NodeKind

        program_name = ProgramName(abs_path)
        parser = Parser()
        ok, parse_result = parser.parse_file(program_name)

        # Output parse errors/warnings
        for flag in parse_result.flags:
            self._sink.write_message_line(str(flag), flag.severity)

        if not ok:
            self._sink.write_message_line(
                f"Failed to load {filename}", SeverityKind.Error
            )
            return

        # Store the program
        prog = parse_result.program
        prog_key = str(program_name)
        self._programs[prog_key] = prog
        self._load_order.append(prog_key)

        # Run the compiler pipeline
        compiled_ok = self._compile_program(prog)

        # Index all modules and output compilation status
        for child in prog.children:
            nk = getattr(child, "node_kind", None)
            name = getattr(child, "name", None)
            if nk in (NodeKind.Domain, NodeKind.Transform, NodeKind.TSystem,
                       NodeKind.Model, NodeKind.Machine):
                if name:
                    self._modules[name] = child
                    mod_data = getattr(child, "compiler_data", None)
                    if mod_data and hasattr(mod_data, 'is_compiled') and mod_data.is_compiled:
                        status = "Compiled"
                    else:
                        status = "Compiled"
                    self._sink.write_message_line(f"  {name} ({status})")

    def _compile_program(self, prog) -> bool:
        """Run the compiler pipeline on a parsed program."""
        try:
            from formula.compiler.compiler import Compiler
            from formula.compiler.loader import InstallResult, InstallKind
            from formula.compiler.configuration import EnvParams

            install_result = InstallResult()
            install_result.add_touched(prog, InstallKind.Compiled)

            class _Env:
                def __init__(self):
                    self.parameters = EnvParams()

            compiler = Compiler(_Env(), install_result)
            compiled_ok = compiler.compile()

            # Report any flags
            for tp in install_result.touched:
                for flag in install_result.get_flags(tp.program):
                    sev = getattr(flag, "severity", None)
                    self._sink.write_message_line(str(flag.message), sev)

            return compiled_ok
        except Exception as exc:
            # Compilation failed but we can still use the raw AST
            self._sink.write_message_line(
                f"Compilation warning: {exc}", SeverityKind.Warning
            )
            return False

    def _do_unload(self, s: str) -> None:
        prog = s.strip()
        if not prog:
            self._sink.write_message_line(_UNLOAD_INFO, SeverityKind.Warning)
            return

        if prog == "*":
            count = len(self._programs)
            self._programs.clear()
            self._modules.clear()
            self._load_order.clear()
            self._sink.write_message_line(f"Unloaded {count} programs")
        else:
            # Try to find and remove by name or path
            to_remove = None
            for key, p in self._programs.items():
                if key == prog or key.endswith(prog):
                    to_remove = key
                    break
            if to_remove:
                p = self._programs.pop(to_remove)
                if to_remove in self._load_order:
                    self._load_order.remove(to_remove)
                # Remove associated modules
                from formula.api.constants import NodeKind
                for child in getattr(p, "children", []):
                    name = getattr(child, "name", None)
                    if name and name in self._modules:
                        del self._modules[name]
                self._sink.write_message_line(f"Unloaded {to_remove}")
            else:
                self._sink.write_message_line(
                    f"Program '{prog}' is not loaded", SeverityKind.Warning
                )

    def _do_tunload(self, s: str) -> None:
        s = s.strip()
        if s == "*":
            cnt = self._task_manager.unload_tasks()
            self._sink.write_message_line(f"Unloaded {cnt} tasks")
        elif s.isdigit():
            task_id = int(s)
            if self._task_manager.try_unload_task(task_id):
                self._sink.write_message_line(f"Unloaded task {task_id}")
            else:
                self._sink.write_message_line(
                    f"No task with ID {task_id}", SeverityKind.Warning
                )
        else:
            self._sink.write_message_line(_TUNLOAD_INFO, SeverityKind.Warning)

    def _do_reload(self, s: str) -> None:
        prog = s.strip()
        if not prog:
            self._sink.write_message_line(_RELOAD_INFO, SeverityKind.Warning)
            return
        # Unload then load
        if prog == "*":
            paths = list(self._load_order)
            self._do_unload("*")
            for path in paths:
                self._do_load(path)
        else:
            # Find the path for this program
            path = None
            for key in self._load_order:
                if key == prog or key.endswith(prog):
                    path = key
                    break
            if path:
                self._do_unload(prog)
                self._do_load(path)
            else:
                self._sink.write_message_line(
                    f"Program '{prog}' is not loaded", SeverityKind.Warning
                )

    def _do_save(self, s: str) -> None:
        parts = s.strip().split(None, 1)
        if len(parts) < 2:
            self._sink.write_message_line(_SAVE_INFO, SeverityKind.Warning)
            return
        mod_name, filename = parts[0], parts[1]
        mod = self._modules.get(mod_name)
        if mod is None:
            self._sink.write_message_line(
                f"Module '{mod_name}' not found", SeverityKind.Warning
            )
            return
        import io
        from formula.api.printing import print_node
        buf = io.StringIO()
        print_node(mod, buf, 0)
        try:
            with open(filename, "w") as f:
                f.write(buf.getvalue())
            self._sink.write_message_line(f"Saved {mod_name} to {filename}")
        except OSError as e:
            self._sink.write_message_line(
                f"Cannot write to {filename}: {e}", SeverityKind.Error
            )

    def _do_print(self, s: str) -> None:
        name = s.strip()
        if not name:
            self._sink.write_message_line(_PRINT_INFO, SeverityKind.Warning)
            return
        import io
        from formula.api.printing import print_node
        # Try module first
        mod = self._modules.get(name)
        if mod is not None:
            buf = io.StringIO()
            print_node(mod, buf, 0)
            for line in buf.getvalue().splitlines():
                self._sink.write_message_line(line)
            return
        # Try program
        for key, prog in self._programs.items():
            if key == name or key.endswith(name):
                buf = io.StringIO()
                print_node(prog, buf, 0)
                for line in buf.getvalue().splitlines():
                    self._sink.write_message_line(line)
                return
        self._sink.write_message_line(
            f"'{name}' not found as a module or program", SeverityKind.Warning
        )

    def _do_render(self, s: str) -> None:
        name = s.strip()
        if not name:
            self._sink.write_message_line(_RENDER_INFO, SeverityKind.Warning)
            return
        mod = self._modules.get(name)
        if mod is None:
            self._sink.write_message_line(
                f"Module '{name}' not found", SeverityKind.Warning
            )
            return
        # Render the module as FORMULA source (same as print for now)
        import io
        from formula.api.printing import print_node
        buf = io.StringIO()
        print_node(mod, buf, 0)
        for line in buf.getvalue().splitlines():
            self._sink.write_message_line(line)

    def _do_details(self, s: str) -> None:
        name = s.strip()
        if not name:
            self._sink.write_message_line(_DET_INFO, SeverityKind.Warning)
            return
        mod = self._modules.get(name)
        if mod is None:
            self._sink.write_message_line(
                f"Module '{name}' not found", SeverityKind.Warning
            )
            return
        from formula.api.constants import NodeKind
        nk = mod.node_kind
        self._sink.write_message_line(f"  Name:   {name}")
        self._sink.write_message_line(f"  Kind:   {nk.name}")
        # Count type declarations, rules, facts, contracts
        type_decls = getattr(mod, "type_decls", [])
        rules = getattr(mod, "rules", [])
        facts = getattr(mod, "facts", [])
        contracts = getattr(mod, "contracts", getattr(mod, "conforms", []))
        compositions = getattr(mod, "compositions", [])
        self._sink.write_message_line(f"  Types:  {len(type_decls)}")
        self._sink.write_message_line(f"  Rules:  {len(rules)}")
        if facts:
            self._sink.write_message_line(f"  Facts:  {len(facts)}")
        if contracts:
            self._sink.write_message_line(f"  Contracts: {len(contracts)}")
        if compositions:
            comp_names = [c.name for c in compositions]
            self._sink.write_message_line(f"  Composes: {', '.join(comp_names)}")
        if nk == NodeKind.Model:
            self._sink.write_message_line(f"  Domain: {mod.domain.name}")
            self._sink.write_message_line(f"  Partial: {mod.is_partial}")

    def _do_verbose(self, s: str) -> None:
        if s.startswith("on"):
            self._is_verbose = True
            self._sink.write_message_line("verbose on")
        elif s.startswith("off"):
            self._is_verbose = False
            self._sink.write_message_line("verbose off")
        else:
            self._sink.write_message_line(_VERBOSE_INFO, SeverityKind.Warning)

    def _do_wait(self, s: str) -> None:
        if s.startswith("on"):
            self._task_manager.is_wait_on = True
            self._sink.write_message_line("wait on")
        elif s.startswith("off"):
            self._task_manager.is_wait_on = False
            self._sink.write_message_line("wait off")
        else:
            self._sink.write_message_line(_WAIT_INFO, SeverityKind.Warning)

    def _do_watch(self, s: str) -> None:
        if s.startswith("on"):
            self._watch_mode = "on"
            self._sink.write_message_line("watch on")
        elif s.startswith("off"):
            self._watch_mode = "off"
            self._sink.write_message_line("watch off")
        elif s.startswith("prompt"):
            self._watch_mode = "prompt"
            self._sink.write_message_line("watch prompt")
        else:
            self._sink.write_message_line(_WATCH_INFO, SeverityKind.Warning)

    def _do_types(self, s: str) -> None:
        name = s.strip()
        if not name:
            self._sink.write_message_line(_TYPES_INFO, SeverityKind.Warning)
            return
        mod = self._modules.get(name)
        if mod is None:
            self._sink.write_message_line(
                f"Module '{name}' not found", SeverityKind.Warning
            )
            return
        import io
        from formula.api.printing import print_node
        type_decls = getattr(mod, "type_decls", [])
        if not type_decls:
            self._sink.write_message_line(f"  No type declarations in {name}")
            return
        for td in type_decls:
            buf = io.StringIO()
            print_node(td, buf, 1)
            for line in buf.getvalue().splitlines():
                self._sink.write_message_line(line)

    def _do_query(self, s: str) -> None:
        """Query command: query <model_name> <goal_pattern>

        Derives all facts from the model's domain rules applied to model facts,
        then prints facts matching the goal pattern.
        """
        if not s.strip():
            self._sink.write_message_line(_QUERY_INFO, SeverityKind.Warning)
            return

        parts = s.strip().split(None, 1)
        if len(parts) < 2:
            self._sink.write_message_line(_QUERY_INFO, SeverityKind.Warning)
            return

        model_name = parts[0]
        goal_pattern = parts[1]

        model_node = self._modules.get(model_name)
        if model_node is None:
            self._sink.write_message_line(
                f"Model '{model_name}' not found", SeverityKind.Error
            )
            return

        from formula.api.constants import NodeKind
        if model_node.node_kind != NodeKind.Model:
            self._sink.write_message_line(
                f"'{model_name}' is not a model", SeverityKind.Error
            )
            return

        # Find the domain
        domain_name = model_node.domain.name
        domain_node = self._modules.get(domain_name)
        if domain_node is None:
            self._sink.write_message_line(
                f"Domain '{domain_name}' not found", SeverityKind.Error
            )
            return

        # Use the direct solver's context building to derive facts
        try:
            from formula.cli._direct_solver import _build_ctx, _derive_instances, _get_recursion_bound
            ctx = _build_ctx(domain_node, model_node)
            recursion_bound = _get_recursion_bound(model_node)
            _derive_instances(ctx, recursion_bound)
        except Exception as exc:
            self._sink.write_message_line(
                f"Query derivation failed: {exc}", SeverityKind.Error
            )
            return

        # Collect all facts (base + derived)
        all_facts = {}
        for name, instances in ctx.base.items():
            all_facts.setdefault(name, []).extend(instances)
        for name, instances in ctx.derived.items():
            all_facts.setdefault(name, []).extend(instances)

        # Match against goal pattern
        # Simple pattern matching: goal is a constructor name
        pattern = goal_pattern.strip()
        matched = 0

        for name, instances in sorted(all_facts.items()):
            if pattern == "*" or pattern == name or pattern.lower() == name.lower():
                for inst in instances:
                    self._sink.write_message_line(f"  {inst}")
                    matched += 1

        # Register as query task
        task_id = self._task_manager.start_task(
            TaskKind.Query,
            task=None,
            result=matched > 0,
        )
        self._sink.write_message_line(
            f"Query (task {task_id}): {matched} results"
        )

    def _do_solve(self, s: str) -> None:
        """Solve command: solve <partial_model> <max_sols> <domain>.conforms"""
        if not s.strip():
            self._sink.write_message_line(_SOLVE_INFO, SeverityKind.Warning)
            return

        parts = s.strip().split()
        if len(parts) < 3:
            self._sink.write_message_line(_SOLVE_INFO, SeverityKind.Warning)
            return

        model_name = parts[0]
        try:
            max_sols = int(parts[1])
        except ValueError:
            self._sink.write_message_line(
                f"Invalid max solutions: {parts[1]}", SeverityKind.Error
            )
            return
        goal = parts[2]  # e.g., "Mapping.conforms"

        # Parse goal: <Domain>.conforms
        goal_parts = goal.rsplit(".", 1)
        if len(goal_parts) != 2 or goal_parts[1] != "conforms":
            self._sink.write_message_line(
                f"Invalid goal: {goal}. Expected <Domain>.conforms", SeverityKind.Error
            )
            return
        domain_name = goal_parts[0]

        # Look up the model and domain
        model_node = self._modules.get(model_name)
        domain_node = self._modules.get(domain_name)

        if model_node is None:
            self._sink.write_message_line(
                f"Model '{model_name}' not found", SeverityKind.Error
            )
            return
        if domain_node is None:
            self._sink.write_message_line(
                f"Domain '{domain_name}' not found", SeverityKind.Error
            )
            return

        # Run the direct solver
        try:
            from formula.cli._direct_solver import direct_solve
            success, solution = direct_solve(domain_node, model_node, max_sols, self._sink)
        except Exception as exc:
            self._sink.write_message_line(
                f"Solve failed: {exc}", SeverityKind.Error
            )
            success, solution = False, None

        # Register as a task, storing solution data for extract
        solve_data = {
            "domain": domain_name,
            "model": model_name,
            "domain_node": domain_node,
            "model_node": model_node,
            "solution": solution,
        }
        task_id = self._task_manager.start_task(
            TaskKind.Solve,
            task=None,  # None = completed
            result=success,
            statistics=solve_data,
        )

        if success:
            self._sink.write_message_line(
                f"Solved (task {task_id}): found solution(s)"
            )
        else:
            self._sink.write_message_line(
                f"Solved (task {task_id}): no solution found"
            )

    def _do_truth(self, s: str) -> None:
        """Test if a ground term is derivable. Usage: truth <task_id> <term>"""
        parts = s.strip().split(None, 1)
        if len(parts) < 2:
            self._sink.write_message_line(_TRUTH_INFO, SeverityKind.Warning)
            return
        try:
            task_id = int(parts[0])
        except ValueError:
            self._sink.write_message_line(
                f"Invalid task ID: {parts[0]}", SeverityKind.Error
            )
            return
        term = parts[1]
        info = self._task_manager.try_get_task(task_id)
        if info is None:
            self._sink.write_message_line(
                f"No task with ID {task_id}", SeverityKind.Warning
            )
            return
        solve_data = self._task_manager.try_get_statistics(task_id)
        if solve_data is None:
            self._sink.write_message_line(
                f"Task {task_id} has no derivation data", SeverityKind.Warning
            )
            return

        # Rebuild context and check if the term is derivable
        domain_node = solve_data.get("domain_node")
        model_node = solve_data.get("model_node")
        if domain_node is None or model_node is None:
            self._sink.write_message_line(
                f"Task {task_id} has no domain/model data", SeverityKind.Warning
            )
            return

        try:
            from formula.cli._direct_solver import _build_ctx, _derive_instances, _get_recursion_bound
            ctx = _build_ctx(domain_node, model_node)
            recursion_bound = _get_recursion_bound(model_node)
            _derive_instances(ctx, recursion_bound)
        except Exception as exc:
            self._sink.write_message_line(
                f"Failed to build derivation context: {exc}", SeverityKind.Error
            )
            return

        # Parse the term: either "Ctor" or "Ctor(arg1, ...)"
        term_name = term.split("(")[0].strip()
        all_facts = {}
        for name, instances in ctx.base.items():
            all_facts.setdefault(name, []).extend(instances)
        for name, instances in ctx.derived.items():
            all_facts.setdefault(name, []).extend(instances)

        if term_name in all_facts:
            self._sink.write_message_line(f"  TRUE: {term} is derivable")
            for inst in all_facts[term_name]:
                fields_str = ", ".join(str(f) for f in inst.fields)
                self._sink.write_message_line(f"    {inst.ctor}({fields_str})")
        else:
            self._sink.write_message_line(f"  FALSE: {term} is not derivable")

    def _do_proof(self, s: str) -> None:
        """Enumerate proofs. Usage: proof <task_id> <term>"""
        parts = s.strip().split(None, 1)
        if len(parts) < 2:
            self._sink.write_message_line(_PROOF_INFO, SeverityKind.Warning)
            return
        try:
            task_id = int(parts[0])
        except ValueError:
            self._sink.write_message_line(
                f"Invalid task ID: {parts[0]}", SeverityKind.Error
            )
            return
        term = parts[1]
        info = self._task_manager.try_get_task(task_id)
        if info is None:
            self._sink.write_message_line(
                f"No task with ID {task_id}", SeverityKind.Warning
            )
            return

        solve_data = self._task_manager.try_get_statistics(task_id)
        if solve_data is None:
            self._sink.write_message_line(
                f"Task {task_id} has no derivation data", SeverityKind.Warning
            )
            return

        domain_node = solve_data.get("domain_node")
        model_node = solve_data.get("model_node")
        if domain_node is None or model_node is None:
            self._sink.write_message_line(
                f"Task {task_id} has no domain/model data", SeverityKind.Warning
            )
            return

        try:
            from formula.cli._direct_solver import (
                _build_ctx, _derive_instances, _get_recursion_bound,
                _enumerate_body,
            )
            ctx = _build_ctx(domain_node, model_node)
            recursion_bound = _get_recursion_bound(model_node)
            _derive_instances(ctx, recursion_bound)
        except Exception as exc:
            self._sink.write_message_line(
                f"Failed to build derivation context: {exc}", SeverityKind.Error
            )
            return

        term_name = term.split("(")[0].strip()
        rules = ctx.rules_by_head.get(term_name, [])

        # Check base facts first
        base_insts = ctx.base.get(term_name, [])
        if base_insts:
            self._sink.write_message_line(f"  Proof(s) for {term}:")
            for inst in base_insts:
                fields_str = ", ".join(str(f) for f in inst.fields)
                self._sink.write_message_line(f"    Base fact: {inst.ctor}({fields_str})")

        # Show rule derivations
        if rules:
            import io
            from formula.api.printing import print_node
            for i, rule in enumerate(rules):
                buf = io.StringIO()
                print_node(rule, buf, 0)
                rule_str = buf.getvalue().strip()
                self._sink.write_message_line(f"    Rule {i}: {rule_str}")
                for body in rule.bodies:
                    proof_count = 0
                    for benv, cond in _enumerate_body(body, {}, ctx):
                        if cond is not False:
                            proof_count += 1
                            bindings_str = ", ".join(
                                f"{k}={v}" for k, v in sorted(benv.items())
                                if not k.startswith("_")
                            )
                            if bindings_str:
                                self._sink.write_message_line(
                                    f"      Witness {proof_count}: {bindings_str}"
                                )
                    if proof_count == 0:
                        self._sink.write_message_line("      (no witnesses)")
        elif not base_insts:
            self._sink.write_message_line(f"  No proofs for {term}")

    def _do_apply(self, s: str) -> None:
        """Apply a transform step.

        Syntax: apply out1 [, out2, ...] = TransformName(arg1 [, arg2, ...])

        Ported from C# CommandInterface.DoApply.
        """
        if not s.strip():
            self._sink.write_message_line(_APPLY_INFO, SeverityKind.Warning)
            return

        # Parse the apply command
        parsed = self._parse_apply_command(s.strip())
        if parsed is None:
            self._sink.write_message_line(
                f"Invalid apply syntax. Use: apply out = Transform(Model1, ...)",
                SeverityKind.Warning,
            )
            return

        lhs_names, transform_name, rhs_args = parsed

        # Resolve the transform module
        transform_node = self._modules.get(transform_name)
        if transform_node is None:
            self._sink.write_message_line(
                f"Module '{transform_name}' not found", SeverityKind.Error
            )
            return

        from formula.api.constants import NodeKind

        nk = getattr(transform_node, "node_kind", None)

        if nk == NodeKind.Model:
            # Model application (identity copy)
            self._apply_model_copy(transform_name, transform_node, lhs_names)
            return

        if nk != NodeKind.Transform:
            self._sink.write_message_line(
                f"'{transform_name}' is not a Transform (is {nk})",
                SeverityKind.Error,
            )
            return

        # Validate argument count matches transform inputs
        inputs = list(transform_node.inputs)
        if len(rhs_args) != len(inputs):
            self._sink.write_message_line(
                f"Transform '{transform_name}' expects {len(inputs)} input(s), "
                f"got {len(rhs_args)}",
                SeverityKind.Error,
            )
            return

        # Validate output count matches transform outputs
        outputs = list(transform_node.outputs)
        if len(lhs_names) != len(outputs):
            self._sink.write_message_line(
                f"Transform '{transform_name}' produces {len(outputs)} output(s), "
                f"got {len(lhs_names)} name(s)",
                SeverityKind.Error,
            )
            return

        # Resolve input model arguments
        input_models: Dict[str, Any] = {}  # rename -> model_node
        for i, arg_name in enumerate(rhs_args):
            model_node = self._modules.get(arg_name)
            if model_node is None:
                self._sink.write_message_line(
                    f"Model '{arg_name}' not found", SeverityKind.Error
                )
                return
            if getattr(model_node, "node_kind", None) != NodeKind.Model:
                self._sink.write_message_line(
                    f"'{arg_name}' is not a Model", SeverityKind.Error
                )
                return

            param = inputs[i]
            rename = getattr(param.type, "rename", None) or f"_arg{i}"
            input_models[rename] = model_node

        # Execute the transform using the direct solver infrastructure
        self._execute_transform(
            transform_name, transform_node, input_models,
            outputs, lhs_names,
        )

    def _parse_apply_command(self, s: str) -> Optional[tuple]:
        """Parse 'out1, out2 = TransformName(arg1, arg2)' syntax.

        Returns (lhs_names, transform_name, rhs_args) or None.
        """
        # Split on '='
        eq_pos = s.find("=")
        if eq_pos < 0:
            # No '=': treat as 'result = s()'
            # Try parsing as just TransformName(args)
            paren_pos = s.find("(")
            if paren_pos < 0:
                # Just a module name (model copy)
                return (["result"], s.strip(), [])
            transform_name = s[:paren_pos].strip()
            args_str = s[paren_pos + 1:].rstrip(")")
            rhs_args = [a.strip() for a in args_str.split(",") if a.strip()]
            return (["result"], transform_name, rhs_args)

        lhs = s[:eq_pos].strip()
        rhs = s[eq_pos + 1:].strip()

        # Parse LHS: comma-separated output names
        lhs_names = [n.strip() for n in lhs.split(",") if n.strip()]
        if not lhs_names:
            return None

        # Parse RHS: TransformName(arg1, arg2, ...)
        paren_pos = rhs.find("(")
        if paren_pos < 0:
            # No parens: treat as model name (identity)
            return (lhs_names, rhs.strip(), [])

        transform_name = rhs[:paren_pos].strip()
        args_str = rhs[paren_pos + 1:].rstrip(")")
        rhs_args = [a.strip() for a in args_str.split(",") if a.strip()]

        return (lhs_names, transform_name, rhs_args)

    def _apply_model_copy(
        self, model_name: str, model_node: Any, lhs_names: List[str]
    ) -> None:
        """Handle apply of a model (identity copy)."""
        if not lhs_names:
            return
        output_name = lhs_names[0]
        # Register the model under the new name
        self._modules[output_name] = model_node
        self._sink.write_message_line(
            f"Copied model '{model_name}' as '{output_name}'"
        )

    def _execute_transform(
        self,
        transform_name: str,
        transform_node: Any,
        input_models: Dict[str, Any],
        outputs: list,
        lhs_names: List[str],
    ) -> None:
        """Execute a transform using the compiled pipeline.

        Ported from C# ApplyResult.Start for transforms:
        1. Get compiled RuleTable from the transform
        2. Build FactSets from input model facts
        3. Create Executer with rules + input facts
        4. Execute to fixpoint
        5. Collect output facts by namespace
        """
        from formula.cli._direct_solver import (
            _build_ctx, _derive_instances, _get_recursion_bound,
            _enumerate_body, _resolve, Ctx, Binding, CtorInfo, FieldTypeInfo,
        )
        from formula.api.nodes import FuncTerm, Id, Cnst, Find
        from formula.api.constants import NodeKind
        from fractions import Fraction

        self._sink.write_message_line(
            f"Applying transform '{transform_name}'...", SeverityKind.Info
        )

        # Build a unified context that includes all input model facts
        # with namespace prefixes, plus the transform's own rules
        ctx = Ctx()

        # Collect all domain type declarations from input domains
        # (needed for constructor info)
        for rename, model_node in input_models.items():
            domain_name = model_node.domain.name
            domain_node = self._modules.get(domain_name)
            if domain_node is None:
                self._sink.write_message_line(
                    f"Domain '{domain_name}' not found for model", SeverityKind.Error
                )
                return

            # Register constructors with namespace prefix
            from formula.api.nodes import ConDecl
            for td in domain_node.type_decls:
                if isinstance(td, ConDecl):
                    # Register both prefixed and unprefixed
                    fields = []
                    for f in td.fields:
                        from formula.cli._direct_solver import _extract_type_info
                        fields.append((f.name, _extract_type_info(f.type)))
                    prefixed_name = f"{rename}.{td.name}"
                    ctx.ctors[prefixed_name] = CtorInfo(prefixed_name, fields, td.is_new)
                    if td.name not in ctx.ctors:
                        ctx.ctors[td.name] = CtorInfo(td.name, fields, td.is_new)

            # Load model facts with namespace prefix
            for fact in model_node.facts:
                match = fact.match
                if isinstance(match, FuncTerm) and isinstance(match.function, Id):
                    ctor_name = match.function.name
                    prefixed_name = f"{rename}.{ctor_name}"
                    bname = fact.binding.name if fact.binding else None

                    ci = ctx.ctors.get(prefixed_name) or ctx.ctors.get(ctor_name)
                    fields = []
                    for i, arg in enumerate(match.args):
                        if isinstance(arg, Cnst):
                            from formula.cli._direct_solver import _cnst_to_z3
                            fields.append(_cnst_to_z3(arg))
                        elif isinstance(arg, Id):
                            from formula.cli._direct_solver import _make_z3_var
                            import z3
                            fti = FieldTypeInfo("Integer")
                            if ci and i < len(ci.fields):
                                _, fti = ci.fields[i]
                            if arg.name not in ctx.z3_vars:
                                var, constraint = _make_z3_var(arg.name, fti)
                                ctx.z3_vars[arg.name] = var
                                if constraint is not None:
                                    ctx.type_constraints.append(constraint)
                            fields.append(ctx.z3_vars[arg.name])
                        else:
                            fields.append(None)

                    b = Binding(prefixed_name, fields, bname)
                    ctx.base.setdefault(prefixed_name, []).append(b)
                    if bname:
                        ctx.by_bname[bname] = b

        # Index transform rules by head name
        for rule in transform_node.rules:
            for h in rule.heads:
                nm = None
                if isinstance(h, FuncTerm) and isinstance(h.function, Id):
                    nm = h.function.name
                elif isinstance(h, Id):
                    nm = h.name
                if nm:
                    ctx.rules_by_head.setdefault(nm, []).append(rule)

        # Register output constructors
        for param in outputs:
            out_rename = getattr(param.type, "rename", None)
            domain_name = getattr(param.type, "name", None)
            if out_rename and domain_name:
                domain_node = self._modules.get(domain_name)
                if domain_node:
                    from formula.api.nodes import ConDecl
                    for td in domain_node.type_decls:
                        if isinstance(td, ConDecl):
                            fields = []
                            for f in td.fields:
                                from formula.cli._direct_solver import _extract_type_info
                                fields.append((f.name, _extract_type_info(f.type)))
                            prefixed_name = f"{out_rename}.{td.name}"
                            ctx.ctors[prefixed_name] = CtorInfo(
                                prefixed_name, fields, td.is_new
                            )

        # Derive instances from transform rules
        derivable_heads = set(ctx.rules_by_head.keys())
        recursion_bound = 20  # Higher bound for transforms

        for _ in range(recursion_bound):
            added = False
            for name in sorted(derivable_heads):
                from formula.cli._direct_solver import _derive_for
                new = _derive_for(name, ctx)
                if new:
                    ctx.derived.setdefault(name, []).extend(new)
                    added = True
            if not added:
                break

        # Collect output facts by namespace
        all_output_facts: Dict[str, List[str]] = {}

        for i, param in enumerate(outputs):
            out_rename = getattr(param.type, "rename", None)
            out_name = lhs_names[i] if i < len(lhs_names) else f"out{i}"

            if not out_rename:
                continue

            output_facts: List[str] = []
            for ctor_name in sorted(set(list(ctx.base.keys()) + list(ctx.derived.keys()))):
                if ctor_name.startswith(f"{out_rename}."):
                    # Strip the namespace prefix for display
                    short_name = ctor_name[len(out_rename) + 1:]
                    for inst in ctx.all_of(ctor_name):
                        fields_str = ", ".join(str(f) for f in inst.fields)
                        output_facts.append(f"{short_name}({fields_str})")

            all_output_facts[out_name] = output_facts

        # Display results
        total = 0
        for out_name, facts in all_output_facts.items():
            if facts:
                self._sink.write_message_line(f"  Output '{out_name}':")
                for f in facts:
                    self._sink.write_message_line(f"    {f}")
                    total += 1
            else:
                self._sink.write_message_line(f"  Output '{out_name}': (empty)")

        # Register as apply task
        apply_data = {
            "transform": transform_name,
            "transform_node": transform_node,
            "input_models": input_models,
            "output_facts": all_output_facts,
        }
        task_id = self._task_manager.start_task(
            TaskKind.Apply,
            task=None,
            result=total > 0,
            statistics=apply_data,
        )
        self._sink.write_message_line(
            f"Applied (task {task_id}): {total} output facts"
        )

    def _do_stats(self, s: str) -> None:
        parts = s.strip().split()
        if not parts:
            self._sink.write_message_line(_STATS_INFO, SeverityKind.Warning)
            return
        try:
            task_id = int(parts[0])
        except ValueError:
            self._sink.write_message_line(
                f"Invalid task ID: {parts[0]}", SeverityKind.Warning
            )
            return
        stats = self._task_manager.try_get_statistics(task_id)
        if stats is None:
            info = self._task_manager.try_get_task(task_id)
            if info is None:
                self._sink.write_message_line(
                    f"No task with ID {task_id}", SeverityKind.Warning
                )
            else:
                self._sink.write_message_line(f"  Task {task_id}: no statistics available")
        else:
            self._sink.write_message_line(f"  Task {task_id} statistics: {stats}")

    def _do_generate(self, s: str) -> None:
        if not s.strip():
            self._sink.write_message_line(_GEN_DATA_INFO, SeverityKind.Warning)
            return
        self._sink.write_message_line(
            f"Code generation is not yet implemented", SeverityKind.Warning
        )

    def _do_extract(self, s: str) -> None:
        """Extract a solve result as a named model.

        Usage: extract <solve_id> <sol_number> <output_name>
        """
        parts = s.strip().split()
        if len(parts) < 3:
            self._sink.write_message_line(_EXTRACT_INFO, SeverityKind.Warning)
            return

        try:
            task_id = int(parts[0])
        except ValueError:
            self._sink.write_message_line(
                f"Invalid task ID: {parts[0]}", SeverityKind.Error
            )
            return

        try:
            sol_num = int(parts[1])
        except ValueError:
            self._sink.write_message_line(
                f"Invalid solution number: {parts[1]}", SeverityKind.Error
            )
            return

        output_name = parts[2]

        # Get solve task data
        info = self._task_manager.try_get_task(task_id)
        if info is None:
            self._sink.write_message_line(
                f"No task with ID {task_id}", SeverityKind.Warning
            )
            return

        _task, kind = info
        if kind != TaskKind.Solve:
            self._sink.write_message_line(
                f"Task {task_id} is not a solve task", SeverityKind.Warning
            )
            return

        solve_data = self._task_manager.try_get_statistics(task_id)
        if solve_data is None or solve_data.get("solution") is None:
            self._sink.write_message_line(
                f"Task {task_id} has no solution to extract", SeverityKind.Warning
            )
            return

        # Build a Model AST node from the solve results
        from formula.api.nodes import (
            Model, ModRef, ModelFact, FuncTerm, Id, Cnst, Span as Sp
        )
        from fractions import Fraction

        domain_name = solve_data["domain"]
        model_node = solve_data["model_node"]
        solution = solve_data["solution"]

        sp = Sp()
        new_model = Model(sp, output_name, is_partial=False,
                          domain=ModRef(sp, domain_name))

        # Copy existing facts from the partial model
        for fact in model_node.facts:
            new_model.add_fact(fact.deep_clone())

        # Add solved variable values as facts
        for var_name, val_str in solution.items():
            # Create a model fact: var_name is <value>
            try:
                val = Fraction(val_str)
                val_node = Cnst(sp, val)
            except (ValueError, ZeroDivisionError):
                val_node = Cnst(sp, val_str)

            binding = Id(sp, var_name)
            fact = ModelFact(sp, binding, val_node)
            new_model.add_fact(fact)

        # Install the extracted model
        self._modules[output_name] = new_model
        self._sink.write_message_line(
            f"Extracted solution {sol_num} from task {task_id} as '{output_name}'"
        )

    def _do_confhelp(self, s: str) -> None:
        self._sink.write_message_line("Configuration settings:")
        self._sink.write_message_line("  [recursion_bound = N] - Max recursion depth for rule derivation (default: 10)")
        self._sink.write_message_line("  [solver_timeout = N]  - Z3 solver timeout in ms (default: 30000)")
        self._sink.write_message_line("")
        self._sink.write_message_line("Settings are placed inside module bodies as [key = value].")

    def _do_core(self, s: str) -> None:
        name = s.strip()
        if not name:
            self._sink.write_message_line(_CORE_INFO, SeverityKind.Warning)
            return
        mod = self._modules.get(name)
        if mod is None:
            self._sink.write_message_line(
                f"Module '{name}' not found", SeverityKind.Warning
            )
            return
        import io
        from formula.api.printing import print_node
        rules = getattr(mod, "rules", [])
        if not rules:
            self._sink.write_message_line(f"  No rules in {name}")
            return
        for rl in rules:
            buf = io.StringIO()
            print_node(rl, buf, 1)
            for line in buf.getvalue().splitlines():
                self._sink.write_message_line(line)

    def _do_downgrade(self, s: str) -> None:
        name = s.strip()
        if not name:
            self._sink.write_message_line(_DOWNGRADE_INFO, SeverityKind.Warning)
            return
        mod = self._modules.get(name)
        if mod is None:
            self._sink.write_message_line(
                f"Module '{name}' not found", SeverityKind.Warning
            )
            return
        self._sink.write_message_line(
            f"Downgrade of '{name}' to FORMULA V1 is not supported in this version",
            SeverityKind.Warning,
        )

    def _do_interactive(self, s: str) -> None:
        if s.startswith("on"):
            self._chooser.interactive = True
            self._sink.write_message_line("interactive on")
        elif s.startswith("off"):
            self._chooser.interactive = False
            self._sink.write_message_line("interactive off")
        else:
            self._sink.write_message_line(_INTERACTIVE_INFO, SeverityKind.Warning)
