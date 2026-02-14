"""Python-side entry point for the FORMULA web playground.

Provides ``parse()`` and ``solve()`` functions called from the Web Worker
via ``pyodide.runPythonAsync()``.
"""

from __future__ import annotations

import json
import sys
import traceback
from io import StringIO

from formula.api.parser.parser import Parser
from formula.api.nodes import ProgramName, NodeKind
from formula.cli.interfaces import IMessageSink, SeverityKind


# ── WebSink ───────────────────────────────────────────────────────

class WebSink(IMessageSink):
    """Message sink that posts messages to the main thread via JS postMessage."""

    def __init__(self):
        self._buf = StringIO()
        self._printed_error = False
        try:
            from js import postMessage as _pm  # type: ignore[import]
            self._post = _pm
        except ImportError:
            self._post = None

    @property
    def writer(self):
        return self._buf

    def reset_printed_error(self):
        self._printed_error = False

    def write_message(self, msg, severity=None):
        if severity == SeverityKind.Error:
            self._printed_error = True
        self._buf.write(msg)
        self._send(msg, severity)

    def write_message_line(self, msg, severity=None):
        if severity == SeverityKind.Error:
            self._printed_error = True
        self._buf.write(msg + "\n")
        self._send(msg + "\n", severity)

    def _send(self, text, severity=None):
        if self._post is not None:
            from pyodide.ffi import to_js  # type: ignore[import]
            from js import Object  # type: ignore[import]
            sev = "info"
            if severity == SeverityKind.Warning:
                sev = "warning"
            elif severity == SeverityKind.Error:
                sev = "error"
            self._post(to_js(
                {"type": "output", "text": text, "severity": sev},
                dict_converter=Object.fromEntries,
            ))


# ── Helpers ───────────────────────────────────────────────────────

def _parse_code(code):
    """Parse FORMULA source text, return (program, modules_dict, errors_list)."""
    parser = Parser()
    name = ProgramName()
    ok, result = parser.parse_text(name, code)

    errors = []
    for flag in result.flags:
        errors.append({
            "severity": flag.severity.name if hasattr(flag.severity, "name") else str(flag.severity),
            "message": str(flag.message) if hasattr(flag, "message") else str(flag),
            "line": getattr(flag.span, "start_line", 0) if hasattr(flag, "span") else 0,
            "col": getattr(flag.span, "start_col", 0) if hasattr(flag, "span") else 0,
        })

    modules = {}
    prog = result.program
    for child in prog.children:
        nk = getattr(child, "node_kind", None)
        nm = getattr(child, "name", None)
        if nk in (NodeKind.Domain, NodeKind.Model) and nm:
            kind = "domain" if nk == NodeKind.Domain else "model"
            is_partial = getattr(child, "is_partial", False)
            domain_ref = None
            if kind == "model":
                dr = getattr(child, "domain", None)
                if dr is not None:
                    domain_ref = getattr(dr, "name", str(dr))
            modules[nm] = {
                "kind": kind,
                "is_partial": is_partial,
                "domain": domain_ref,
            }

    return prog, modules, errors, ok


# ── Public API ────────────────────────────────────────────────────

def parse(code):
    """Parse FORMULA source and return JSON with modules and errors."""
    try:
        _prog, modules, errors, ok = _parse_code(code)
        return json.dumps({"ok": ok, "modules": modules, "errors": errors})
    except Exception as exc:
        return json.dumps({
            "ok": False,
            "modules": {},
            "errors": [{"severity": "Error", "message": str(exc), "line": 0, "col": 0}],
        })


def solve(code, model_name, domain_name, max_sols=1):
    """Parse code and run the direct solver. Returns JSON result."""
    sink = WebSink()

    try:
        prog, modules, errors, ok = _parse_code(code)

        if not ok:
            return json.dumps({
                "ok": False,
                "result": "parse_error",
                "errors": errors,
                "output": "",
            })

        # Find the domain and model nodes
        domain_node = None
        model_node = None
        for child in prog.children:
            nm = getattr(child, "name", None)
            if nm == domain_name:
                domain_node = child
            if nm == model_name:
                model_node = child

        if domain_node is None:
            return json.dumps({
                "ok": False,
                "result": "error",
                "errors": [{"severity": "Error", "message": f"Domain '{domain_name}' not found", "line": 0, "col": 0}],
                "output": "",
            })
        if model_node is None:
            return json.dumps({
                "ok": False,
                "result": "error",
                "errors": [{"severity": "Error", "message": f"Model '{model_name}' not found", "line": 0, "col": 0}],
                "output": "",
            })

        from formula.cli._direct_solver import direct_solve
        result = direct_solve(domain_node, model_node, max_sols, sink)

        if isinstance(result, tuple):
            success, solution = result
        else:
            success = result
            solution = None

        return json.dumps({
            "ok": success,
            "result": "sat" if success else "unsat",
            "solution": solution or {},
            "output": sink._buf.getvalue(),
        })

    except Exception as exc:
        tb = traceback.format_exc()
        return json.dumps({
            "ok": False,
            "result": "error",
            "errors": [{"severity": "Error", "message": f"{exc}\n{tb}", "line": 0, "col": 0}],
            "output": sink._buf.getvalue(),
        })
