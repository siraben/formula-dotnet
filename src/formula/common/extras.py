"""
Port of Src/Core/Common/Extras/*.cs (5 files).

Utility functions and helpers:
  - BitMethods          : bit manipulation (population count, leading zeros, MSB)
  - CompiledNodeMethods : extract compiler metadata from AST nodes
  - EnumerableMethods   : utility functions over iterables / sequences
  - MessageHelpers      : error message formatting and code location strings
  - Z3Utilities         : Z3 solver helper functions (stubs; Z3 optional)
"""
from __future__ import annotations

import io
import math
from fractions import Fraction
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

T = TypeVar("T")
S = TypeVar("S")


# ===================================================================
# BitMethods
# ===================================================================

class BitMethods:
    """
    Bit manipulation utilities.

    Ported from BitMethods.cs.
    """

    CHUNKSIZE = 32  # 8 * sizeof(uint)
    MASKTWO  = 0x55555555
    MASKNIB  = 0x33333333
    MASKBYT  = 0x0F0F0F0F
    MASKPOP  = 0x0000003F

    @staticmethod
    def population_count(x: int) -> int:
        """
        Return the number of 1-bits in the 32-bit representation of *x*.

        Also known as Hamming weight / pop-count.
        """
        x = x & 0xFFFFFFFF
        x -= (x >> 1) & BitMethods.MASKTWO
        x = ((x >> 2) & BitMethods.MASKNIB) + (x & BitMethods.MASKNIB)
        x = ((x >> 4) + x) & BitMethods.MASKBYT
        x += x >> 8
        x += x >> 16
        return x & BitMethods.MASKPOP

    @staticmethod
    def leading_zero_count(x: int) -> int:
        """
        Return the number of leading zeros in the 32-bit representation of *x*.
        """
        x = x & 0xFFFFFFFF
        x |= x >> 1
        x |= x >> 2
        x |= x >> 4
        x |= x >> 8
        x |= x >> 16
        return BitMethods.CHUNKSIZE - BitMethods.population_count(x)

    @staticmethod
    def most_significant_one(x: int) -> int:
        """
        Return the index (0-based) of the most significant 1-bit.

        *x* must be non-zero.
        """
        assert x != 0
        x = x & 0xFFFFFFFF
        x |= x >> 1
        x |= x >> 2
        x |= x >> 4
        x |= x >> 8
        x |= x >> 16
        return BitMethods.population_count(x) - 1

    @staticmethod
    def most_significant_one_big(b: int) -> int:
        """
        For a positive integer *b*, return the largest n where 2^n <= b.
        """
        assert b > 0
        return b.bit_length() - 1


# ===================================================================
# CompiledNodeMethods
# ===================================================================

class CompiledNodeMethods:
    """
    Extension methods for AST nodes that have been compiled and tagged
    with compiler metadata.

    In the Python port, these are static helper functions.
    """

    # Mapping from node kind to the attribute name holding the Config child
    _CONFIG_ATTRS = {
        "Domain": "config",
        "Model": "config",
        "Transform": "config",
        "TSystem": "config",
        "Machine": "config",
        "ModelFact": "config",
        "Rule": "config",
        "ConDecl": "config",
        "MapDecl": "config",
        "UnnDecl": "config",
        "Update": "config",
        "Step": "config",
        "Program": "config",
    }

    @staticmethod
    def get_module_configuration(node: Any) -> Any:
        """
        Retrieve the compiled ``Configuration`` from a module node.

        The node must have ``is_module == True``.
        """
        if node is None:
            return None
        node_kind = getattr(node, "node_kind", None) or type(node).__name__
        attr = CompiledNodeMethods._CONFIG_ATTRS.get(node_kind)
        if attr is None:
            return None
        conf_node = getattr(node, attr, None)
        if conf_node is None:
            return None
        return getattr(conf_node, "compiler_data", None)

    @staticmethod
    def try_get_configuration(node: Any) -> Optional[Any]:
        """
        Try to get a ``Configuration`` from a node that may or may not
        have one.  Returns None if no configuration is available.
        """
        if node is None:
            return None
        node_kind = getattr(node, "node_kind", None) or type(node).__name__
        attr = CompiledNodeMethods._CONFIG_ATTRS.get(node_kind)
        if attr is None:
            return None
        conf_node = getattr(node, attr, None)
        if conf_node is None:
            return None
        return getattr(conf_node, "compiler_data", None)


# ===================================================================
# EnumerableMethods
# ===================================================================

class EnumerableMethods:
    """
    Utility functions for iterables and sequences.

    Most of these mirror Linq-style helpers from the C# codebase.
    """

    @staticmethod
    def none() -> Iterable:
        """Return an empty iterable."""
        return iter(())

    @staticmethod
    def get_enumerable_1(t1: T) -> Iterable[T]:
        """Return a single-element iterable."""
        yield t1

    @staticmethod
    def get_enumerable_2(t1: T, t2: T) -> Iterable[T]:
        yield t1
        yield t2

    @staticmethod
    def get_enumerable_3(t1: T, t2: T, t3: T) -> Iterable[T]:
        yield t1
        yield t2
        yield t3

    @staticmethod
    def get_enumerable_4(t1: T, t2: T, t3: T, t4: T) -> Iterable[T]:
        yield t1
        yield t2
        yield t3
        yield t4

    @staticmethod
    def get_enumerable_array(arr: Optional[Sequence[T]]) -> Iterable[T]:
        """Iterate over an array / sequence (or nothing if None)."""
        if arr is None:
            return iter(())
        return iter(arr)

    @staticmethod
    def to_array(iterable: Optional[Iterable[T]], length: int) -> List[T]:
        """Materialize an iterable into a list of known *length*."""
        if iterable is None:
            assert length == 0
            return []
        result = list(iterable)
        assert len(result) == length
        return result

    @staticmethod
    def is_empty(iterable: Optional[Iterable]) -> bool:
        """Return True if the iterable is None or has no elements."""
        if iterable is None:
            return True
        try:
            it = iter(iterable)
            next(it)
            return False
        except StopIteration:
            return True

    @staticmethod
    def is_several(iterable: Optional[Iterable]) -> bool:
        """Return True if the iterable has at least two elements."""
        if iterable is None:
            return False
        it = iter(iterable)
        try:
            next(it)
            next(it)
            return True
        except StopIteration:
            return False

    @staticmethod
    def is_one(iterable: Optional[Iterable]) -> bool:
        """Return True if the iterable has exactly one element."""
        if iterable is None:
            return False
        it = iter(iterable)
        try:
            next(it)
        except StopIteration:
            return False
        try:
            next(it)
            return False
        except StopIteration:
            return True

    @staticmethod
    def truncate(iterable: Iterable[T], trunc_amount: int) -> Iterable[T]:
        """
        Yield all but the last *trunc_amount* elements.
        """
        buf: List[T] = list(iterable)
        stop = len(buf) - trunc_amount
        for i in range(max(0, stop)):
            yield buf[i]

    @staticmethod
    def append(iterable: Iterable[T], last: T) -> Iterable[T]:
        """Yield all elements of *iterable* followed by *last*."""
        yield from iterable
        yield last

    @staticmethod
    def or_values(values: Optional[Iterable[bool]]) -> bool:
        """Return True if any value is True."""
        if values is None:
            return False
        return any(values)

    @staticmethod
    def and_values(values: Optional[Iterable[bool]]) -> bool:
        """Return True if all values are True."""
        if values is None:
            return True
        return all(values)

    @staticmethod
    def reverse_array(arr: Optional[List[T]], ending_index: Optional[int] = None) -> None:
        """In-place reverse of a list (optionally up to *ending_index*)."""
        if arr is None or len(arr) < 2:
            return
        if ending_index is None:
            arr.reverse()
        else:
            # Reverse arr[0..ending_index] in place
            lo = 0
            hi = ending_index
            while lo < hi:
                arr[lo], arr[hi] = arr[hi], arr[lo]
                lo += 1
                hi -= 1

    @staticmethod
    def to_string(
        elements: Optional[Iterable[T]],
        sep: str,
        to_str: Optional[Callable[[T], str]] = None,
    ) -> str:
        """Join elements with *sep*, using *to_str* for conversion."""
        if elements is None:
            return ""
        if to_str is None:
            return sep.join(str(e) for e in elements)
        return sep.join(to_str(e) for e in elements)

    @staticmethod
    def lex_compare(
        arr1: Sequence[T],
        arr2: Sequence[T],
        compare: Callable[[T, T], int],
    ) -> int:
        """Lexicographic comparison of two sequences."""
        n = min(len(arr1), len(arr2))
        for i in range(n):
            cmp = compare(arr1[i], arr2[i])
            if cmp != 0:
                return cmp
        return len(arr1) - len(arr2)


# ===================================================================
# MessageHelpers
# ===================================================================

class MessageHelpers:
    """
    Helpers for constructing error / warning messages with source locations.
    """

    @staticmethod
    def mk_dup_err_msg(
        item: str,
        off_def1: Any,
        off_def2: Any,
        env_params: Any = None,
    ) -> str:
        """
        Build a "duplicate definition" error message.
        """
        loc1 = MessageHelpers.get_code_location_string(off_def1, env_params)
        loc2 = MessageHelpers.get_code_location_string(off_def2, env_params)
        return f"Duplicate definition of {item} at {loc1} and {loc2}"

    @staticmethod
    def get_code_location_string(
        obj: Any,
        env_params: Any = None,
        prog_name: Any = None,
    ) -> str:
        """
        Extract a human-readable source location string from *obj*.

        *obj* can be a ``Location``, a ``Node`` (with a ``.span``), or
        an ``AST<Node>`` wrapper.
        """
        if obj is None:
            if prog_name:
                return f"{prog_name} (?,?)"
            return "(?,?)"

        # Try Location
        if hasattr(obj, "get_file_location_string"):
            return obj.get_file_location_string(env_params)

        # Try Node with span
        span = None
        if hasattr(obj, "span"):
            span = obj.span
        elif hasattr(obj, "node") and hasattr(obj.node, "span"):
            span = obj.node.span

        if span is not None:
            start_line = getattr(span, "start_line", "?")
            start_col = getattr(span, "start_col", "?")
            if prog_name:
                return f"{prog_name}({start_line}, {start_col})"
            return f"({start_line}, {start_col})"

        # Try tuple of (ProgramName, Node)
        if isinstance(obj, tuple) and len(obj) == 2:
            return MessageHelpers.get_code_location_string(
                obj[1], env_params, obj[0]
            )

        if prog_name:
            return f"{prog_name} (?,?)"
        return "(?,?)"

    @staticmethod
    def debug_get_small_term_string(t: Any) -> str:
        """Produce a compact string representation of a term."""
        if t is None:
            return ""
        sw = io.StringIO()
        from formula.common.terms import TermIndex
        TermIndex.debug_print_small_term(t, sw)
        return sw.getvalue()

    @staticmethod
    def debug_get_small_terms_string(terms: Optional[Iterable]) -> str:
        """Produce a compact string of multiple terms."""
        if terms is None:
            return ""
        parts = []
        from formula.common.terms import TermIndex
        for t in terms:
            sw = io.StringIO()
            TermIndex.debug_print_small_term(t, sw)
            parts.append(sw.getvalue())
        return ",   ".join(parts)


# ===================================================================
# Z3Utilities  (stubs -- Z3 is optional)
# ===================================================================

class Z3Utilities:
    """
    Helper functions for the Z3 SMT solver.

    These are stubs.  When ``z3-solver`` is available, they delegate to
    the z3 Python API.  Otherwise they raise ``ImportError``.
    """

    _z3_available: Optional[bool] = None

    @classmethod
    def _ensure_z3(cls) -> Any:
        """Import z3 or raise ImportError."""
        if cls._z3_available is None:
            try:
                import z3
                cls._z3_available = True
                return z3
            except ImportError:
                cls._z3_available = False
        if not cls._z3_available:
            raise ImportError(
                "Z3 is required for this operation. "
                "Install it with: pip install z3-solver"
            )
        import z3
        return z3

    @staticmethod
    def ite(cond: Any, context: Any, if_true: Any, if_false: Any) -> Any:
        """``context.MkITE(cond, if_true, if_false)``"""
        z3 = Z3Utilities._ensure_z3()
        return z3.If(cond, if_true, if_false)

    @staticmethod
    def implies(expr1: Any, context: Any, expr2: Any) -> Any:
        z3 = Z3Utilities._ensure_z3()
        return z3.Implies(expr1, expr2)

    @staticmethod
    def iff(expr1: Any, context: Any, expr2: Any) -> Any:
        z3 = Z3Utilities._ensure_z3()
        return expr1 == expr2

    @staticmethod
    def z3_not(expr1: Any, context: Any = None) -> Any:
        z3 = Z3Utilities._ensure_z3()
        return z3.Not(expr1)

    @staticmethod
    def neg(expr1: Any, context: Any = None) -> Any:
        z3 = Z3Utilities._ensure_z3()
        return -expr1

    @staticmethod
    def is_even(expr1: Any, context: Any = None) -> Any:
        z3 = Z3Utilities._ensure_z3()
        return expr1 % 2 == 0

    @staticmethod
    def z3_or(expr1: Any, context: Any, expr2: Any) -> Any:
        z3 = Z3Utilities._ensure_z3()
        if expr1 is None:
            return expr2
        if expr2 is None:
            return expr1
        return z3.Or(expr1, expr2)

    @staticmethod
    def z3_and(expr1: Any, context: Any, expr2: Any) -> Any:
        z3 = Z3Utilities._ensure_z3()
        if expr1 is None:
            return expr2
        if expr2 is None:
            return expr1
        return z3.And(expr1, expr2)

    @staticmethod
    def ge(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 >= expr2

    @staticmethod
    def gt(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 > expr2

    @staticmethod
    def le(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 <= expr2

    @staticmethod
    def lt(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 < expr2

    @staticmethod
    def mod(expr1: Any, context: Any, expr2: Any) -> Any:
        z3 = Z3Utilities._ensure_z3()
        return expr1 % expr2

    @staticmethod
    def add(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 + expr2

    @staticmethod
    def sub(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 - expr2

    @staticmethod
    def mul(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 * expr2

    @staticmethod
    def div(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 / expr2

    @staticmethod
    def eq(expr1: Any, context: Any, expr2: Any) -> Any:
        return expr1 == expr2

    @staticmethod
    def neq(expr1: Any, context: Any, expr2: Any) -> Any:
        z3 = Z3Utilities._ensure_z3()
        return z3.Not(expr1 == expr2)

    @staticmethod
    def bv2int(bv_expr: Any, context: Any = None) -> Any:
        """Convert a bit-vector expression to an integer expression."""
        z3 = Z3Utilities._ensure_z3()
        return z3.BV2Int(bv_expr)

    @staticmethod
    def int2bv(int_expr: Any, context: Any = None, size: int = 32) -> Any:
        """Convert an integer expression to a bit-vector of the given *size*."""
        z3 = Z3Utilities._ensure_z3()
        return z3.Int2BV(int_expr, size)

    @staticmethod
    def fit_bv(bv_expr: Any, context: Any, size: int) -> Any:
        """
        Fit a bit-vector expression into a bit-vector of the given *size*,
        either by truncation or zero-extension.
        """
        z3 = Z3Utilities._ensure_z3()
        current_size = bv_expr.size()
        if current_size == size:
            return bv_expr
        elif current_size < size:
            return z3.ZeroExt(size - current_size, bv_expr)
        else:
            return z3.Extract(size - 1, 0, bv_expr)

    @staticmethod
    def compute(
        expr: Any,
        unfold: Callable,
        fold: Callable,
        token: Any = None,
    ) -> Any:
        """
        AST computation over Z3 expressions (unfold / fold pattern).

        Mirrors the ``Term.Compute`` pattern for Z3 expression trees.
        """
        if expr is None:
            return None

        class State:
            def __init__(self, parent, t, unfolding):
                self.parent = parent
                self.t = t
                self.it = iter(unfolding) if unfolding is not None else None
                self.children = []

            def get_next(self):
                if self.it is not None:
                    try:
                        return next(self.it), True
                    except StopIteration:
                        self.it = None
                return None, False

        stack = [State(None, expr, unfold(expr, token))]
        if token is not None and hasattr(token, "result") and not token.result:
            return None

        while stack:
            top = stack[-1]
            child, has_next = top.get_next()
            if has_next:
                stack.append(State(top, child, unfold(child, token)))
                if token is not None and hasattr(token, "result") and not token.result:
                    return None
            else:
                if top.parent is None:
                    return fold(top.t, top.children, token)
                top.parent.children.append(fold(top.t, top.children, token))
                stack.pop()
                if token is not None and hasattr(token, "result") and not token.result:
                    return None

        raise RuntimeError("Impossible: empty stack in Z3Utilities.compute")


# ===================================================================
# IntIntervals  (utility class used by terms / type system)
# ===================================================================

class IntIntervals:
    """
    A set of non-overlapping integer intervals stored in canonical form.

    Each interval is a ``(start, end)`` pair (inclusive on both ends).
    """

    def __init__(self) -> None:
        self._starts: Dict[int, int] = {}  # start -> end

    @property
    def canonical_form(self) -> List[Tuple[int, int]]:
        """Return sorted, non-overlapping intervals."""
        return sorted(self._starts.items())

    @property
    def count(self) -> int:
        return len(self._starts)

    def clear(self) -> None:
        self._starts.clear()

    def add(self, lo: int, hi: int) -> None:
        """Add the interval [lo, hi] and merge with any overlapping ones."""
        new_lo = lo
        new_hi = hi
        to_remove: List[int] = []
        for s, e in sorted(self._starts.items()):
            if s <= hi + 1 and e >= lo - 1:
                new_lo = min(new_lo, s)
                new_hi = max(new_hi, e)
                to_remove.append(s)
        for s in to_remove:
            del self._starts[s]
        self._starts[new_lo] = new_hi

    def contains(self, value: int) -> bool:
        """Return True if *value* is in any interval."""
        for s, e in self._starts.items():
            if s <= value <= e:
                return True
        return False

    def get_size(self) -> int:
        """Count the total number of integers in all intervals."""
        return sum(e - s + 1 for s, e in self._starts.items())

    def clone(self) -> IntIntervals:
        result = IntIntervals()
        result._starts = dict(self._starts)
        return result

    @staticmethod
    def mk_intersection(i1: IntIntervals, i2: IntIntervals) -> IntIntervals:
        """Return a new IntIntervals containing the intersection."""
        result = IntIntervals()
        if i1.count == 0 or i2.count == 0:
            return result
        intervals1 = sorted(i1._starts.items())
        intervals2 = sorted(i2._starts.items())
        idx1, idx2 = 0, 0
        while idx1 < len(intervals1) and idx2 < len(intervals2):
            s1, e1 = intervals1[idx1]
            s2, e2 = intervals2[idx2]
            lo = max(s1, s2)
            hi = min(e1, e2)
            if lo <= hi:
                result.add(lo, hi)
            if e1 < e2:
                idx1 += 1
            else:
                idx2 += 1
        return result

    def __repr__(self) -> str:
        parts = [f"{s}..{e}" for s, e in sorted(self._starts.items())]
        return f"IntIntervals({', '.join(parts)})"
