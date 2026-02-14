"""Z3 Python API compatibility shim for Pyodide + z3-solver JS.

This module shadows ``import z3`` when running inside Pyodide.  It wraps the
JavaScript z3-solver (loaded via npm/CDN) to match the subset of the Python z3
API consumed by ``_direct_solver.py``.

The JS z3 Context is expected on ``self._z3ctx`` (set by the Web Worker).
"""

from __future__ import annotations

from pyodide.ffi import run_sync  # type: ignore[import]
from js import _z3ctx as _ctx  # type: ignore[import]

# ── Sort wrappers ─────────────────────────────────────────────────

class SortRef:
    """Wrapper around a JS z3 sort for reliable equality comparison."""

    __slots__ = ("_js", "_name")

    def __init__(self, js_sort):
        self._js = js_sort
        self._name = str(js_sort)

    def __eq__(self, other):
        if isinstance(other, SortRef):
            return self._name == other._name
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, SortRef):
            return self._name != other._name
        return NotImplemented

    def __hash__(self):
        return hash(self._name)

    def __repr__(self):
        return self._name


_int_sort = None
_real_sort = None
_string_sort = None


def _get_sort(obj):
    """Get sort from a JS z3 object, handling both property and method."""
    s = obj.sort
    return s() if callable(s) else s


def _get_int_sort():
    global _int_sort
    if _int_sort is None:
        _int_sort = SortRef(_get_sort(_ctx.Int))
    return _int_sort


def _get_real_sort():
    global _real_sort
    if _real_sort is None:
        _real_sort = SortRef(_get_sort(_ctx.Real))
    return _real_sort


def _get_string_sort():
    global _string_sort
    if _string_sort is None:
        _string_sort = SortRef(_get_sort(_ctx.String))
    return _string_sort


# ── Wrapper classes ───────────────────────────────────────────────

class ExprRef:
    """Base expression wrapper around a JS z3 expression."""

    __slots__ = ("_js",)

    def __init__(self, js_expr):
        self._js = js_expr

    # Comparison operators -> BoolRef
    def __eq__(self, other):
        other = _to_js(other)
        return _wrap(self._js.eq(other))

    def __ne__(self, other):
        other = _to_js(other)
        return _wrap(self._js.neq(other))

    def __lt__(self, other):
        other = _to_js(other)
        return _wrap(self._js.lt(other))

    def __le__(self, other):
        other = _to_js(other)
        return _wrap(self._js.le(other))

    def __gt__(self, other):
        other = _to_js(other)
        return _wrap(self._js.gt(other))

    def __ge__(self, other):
        other = _to_js(other)
        return _wrap(self._js.ge(other))

    def __bool__(self):
        raise TypeError(
            "Coercion of a z3 expression to bool is not supported. "
            "Use If/And/Or instead."
        )

    def __hash__(self):
        return id(self._js)

    def sexpr(self):
        return str(self._js.sexpr())

    def sort(self):
        s = self._js.sort
        return SortRef(s() if callable(s) else s)

    def __repr__(self):
        return str(self._js.sexpr())


class ArithRef(ExprRef):
    """Arithmetic expression (Int or Real)."""

    def __add__(self, other):
        other = _to_js(other)
        return _wrap(self._js.add(other))

    def __radd__(self, other):
        other = _to_js(other)
        return _wrap(_ctx.Int.val(0).add(other).add(self._js)) if isinstance(other, int) else _wrap(self._js.add(other))

    def __sub__(self, other):
        other = _to_js(other)
        return _wrap(self._js.sub(other))

    def __mul__(self, other):
        other = _to_js(other)
        return _wrap(self._js.mul(other))

    def __rmul__(self, other):
        other = _to_js(other)
        return _wrap(self._js.mul(other))

    def __truediv__(self, other):
        other = _to_js(other)
        return _wrap(self._js.div(other))

    def __mod__(self, other):
        other = _to_js(other)
        return _wrap(self._js.mod(other))

    def __neg__(self):
        return _wrap(self._js.neg())

    def __pos__(self):
        return self


class BoolRef(ExprRef):
    """Boolean expression."""
    pass


class ModelRef:
    """Wraps the JS z3 model."""

    __slots__ = ("_js",)

    def __init__(self, js_model):
        self._js = js_model

    def evaluate(self, expr):
        js_expr = _to_js(expr)
        result = self._js.eval(js_expr)
        return _wrap(result)


# ── Sentinel values ───────────────────────────────────────────────

sat = "sat"
unsat = "unsat"
unknown = "unknown"


# ── Sort constructors / checks ────────────────────────────────────

def IntSort():
    return _get_int_sort()


def RealSort():
    return _get_real_sort()


def StringSort():
    return _get_string_sort()


# ── Value constructors ────────────────────────────────────────────

def Int(name):
    return ArithRef(_ctx.Int.const(name))


def Real(name):
    return ArithRef(_ctx.Real.const(name))


def IntVal(n):
    return ArithRef(_ctx.Int.val(int(n)))


def RealVal(v):
    return ArithRef(_ctx.Real.val(float(v)))


def StringVal(s):
    return ExprRef(_ctx.String.val(str(s)))


# ── Logical combinators ──────────────────────────────────────────

def And(*args):
    flat = _flatten_args(args)
    if len(flat) == 0:
        return BoolRef(_ctx.Bool.val(True))
    if len(flat) == 1:
        return _wrap(flat[0])
    return _wrap(_ctx.And(*flat))


def Or(*args):
    flat = _flatten_args(args)
    if len(flat) == 0:
        return BoolRef(_ctx.Bool.val(False))
    if len(flat) == 1:
        return _wrap(flat[0])
    return _wrap(_ctx.Or(*flat))


def Not(a):
    return _wrap(_ctx.Not(_to_js(a)))


def If(cond, t, f):
    return _wrap(_ctx.If(_to_js(cond), _to_js(t), _to_js(f)))


# ── Arithmetic helpers ────────────────────────────────────────────

def ToReal(e):
    return ArithRef(_ctx.ToReal(_to_js(e)))


# ── Solver ────────────────────────────────────────────────────────

class Solver:
    def __init__(self):
        self._js = _ctx.Solver.new()

    def set(self, key, value):
        # JS solver set is limited; best-effort
        try:
            self._js.set(key, value)
        except Exception:
            pass

    def add(self, *constraints):
        for c in constraints:
            self._js.add(_to_js(c))

    def check(self):
        result = run_sync(self._js.check())
        r = str(result)
        if r == "sat":
            return sat
        elif r == "unsat":
            return unsat
        return unknown

    def model(self):
        return ModelRef(self._js.model())


# ── Internal helpers ──────────────────────────────────────────────

def _to_js(val):
    """Convert a Python value to a JS z3 expression."""
    if isinstance(val, ExprRef):
        return val._js
    if isinstance(val, bool):
        return _ctx.Bool.val(val)
    if isinstance(val, int):
        return _ctx.Int.val(val)
    if isinstance(val, float):
        return _ctx.Real.val(val)
    if isinstance(val, str):
        return _ctx.String.val(val)
    # Assume it is already a JS object
    return val


def _flatten_args(args):
    """Flatten a tuple of args that may contain lists into JS exprs."""
    result = []
    for a in args:
        if isinstance(a, (list, tuple)):
            for item in a:
                result.append(_to_js(item))
        else:
            result.append(_to_js(a))
    return result


def _sort_name(js_expr):
    """Get the sort name string of a JS z3 expression."""
    try:
        s = js_expr.sort
        return str(s() if callable(s) else s)
    except Exception:
        return "unknown"


def _wrap(js_expr):
    """Wrap a JS z3 expression in the appropriate Python class."""
    try:
        sn = _sort_name(js_expr)
    except Exception:
        return ExprRef(js_expr)

    if sn == "Bool":
        return BoolRef(js_expr)
    if sn in ("Int", "Real"):
        return ArithRef(js_expr)
    return ExprRef(js_expr)
