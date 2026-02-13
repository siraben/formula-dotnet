"""Port of Src/CommandLine/OptionParser.cs.

Provides ``parse_switch_string`` which parses CLI switch strings such as
``-v``, ``--verbose``, ``-f:"hello"`` into an ``Options`` object.
"""

from __future__ import annotations

from enum import IntEnum, auto
from typing import List, Optional, Tuple


# ── Value kinds ───────────────────────────────────────────────────────

class OptValueKind(IntEnum):
    Id = 0
    Integer = 1
    String = 2


# ── Options accumulator ──────────────────────────────────────────────

class Options:
    """Accumulates parsed switches/flags and their values.

    ``option_lists`` is a list of ``(name, values)`` tuples where
    *values* is a list of ``(OptValueKind, object)`` pairs.
    """

    def __init__(self) -> None:
        self._options: List[Tuple[str, List[Tuple[OptValueKind, object]]]] = []
        self._kind: Optional[OptValueKind] = None
        self._token: str = ""

    @property
    def option_lists(self) -> List[Tuple[str, List[Tuple[OptValueKind, object]]]]:
        return self._options

    # -- token helpers (called from the parser) ------------------------

    def start_token(self, kind: Optional[OptValueKind] = None, c: str = "\0") -> None:
        self._kind = kind
        self._token = ""
        if c != "\0":
            self._token += c

    def append_token(self, c: str) -> None:
        self._token += c

    def end_token(self) -> None:
        if self._token == "" and self._kind is None:
            return

        if self._kind is None:
            # This is a flag/switch name
            self._options.append((self._token, []))
        elif self._kind == OptValueKind.Integer:
            assert len(self._options) > 0
            vals = self._options[-1][1]
            vals.append((OptValueKind.Integer, int(self._token)))
        elif self._kind == OptValueKind.Id:
            assert len(self._options) > 0 and self._token != ""
            vals = self._options[-1][1]
            vals.append((OptValueKind.Id, self._token))
        elif self._kind == OptValueKind.String:
            assert len(self._options) > 0
            vals = self._options[-1][1]
            vals.append((OptValueKind.String, self._token))
        else:
            raise NotImplementedError(f"Unknown OptValueKind: {self._kind}")

        self._token = ""
        self._kind = None


# ── Parse states ──────────────────────────────────────────────────────

class _PS(IntEnum):
    SwStart = 0
    SwStartCnt = auto()
    SwName = auto()
    SwNameOrEnd = auto()
    SwEndOrVal = auto()
    FirstVal = auto()
    Next = auto()
    IdVal = auto()
    IntVal = auto()
    StrValStart = auto()
    StrValEnd = auto()
    StrVal = auto()
    EStrVal = auto()
    EStrValEsc = auto()
    Unhandled = auto()


# ── Character classification helpers ──────────────────────────────────

def _is_ws(c: str) -> bool:
    return c == "\0" or c.isspace()


def _is_id_start(c: str) -> bool:
    return c.isalpha() or c == "_"


def _is_id_middle(c: str) -> bool:
    return c.isalnum() or c == "_"


# ── Token action helpers (mirror C# static helpers) ───────────────────

def _start(opt: Options, kind: Optional[OptValueKind], nxt: _PS, c: str = "\0") -> _PS:
    opt.start_token(kind, c)
    return nxt


def _app(opt: Options, nxt: _PS, c: str) -> _PS:
    opt.append_token(c)
    return nxt


def _end(opt: Options, nxt: _PS) -> _PS:
    opt.end_token()
    return nxt


def _se(opt: Options, kind: Optional[OptValueKind], nxt: _PS, c: str = "\0") -> _PS:
    opt.start_token(kind, c)
    opt.end_token()
    return nxt


def _ae(opt: Options, nxt: _PS, c: str) -> _PS:
    opt.append_token(c)
    opt.end_token()
    return nxt


def _app_esc(opt: Options, nxt: _PS, c: str) -> _PS:
    if c in ("n", "N"):
        opt.append_token("\n")
    elif c in ("r", "R"):
        opt.append_token("\r")
    elif c in ("t", "T"):
        opt.append_token("\t")
    else:
        opt.append_token(c)
    return nxt


# ── Parse table ───────────────────────────────────────────────────────
# Each entry is a list of handler functions.  The first handler that does
# NOT return ``_PS.Unhandled`` wins.

_U = _PS.Unhandled

_PARSE_TABLE = {
    _PS.SwStart: [
        lambda c, la, o: (
            _U if c != "-" else
            (_PS.SwStartCnt if la == "-" else
             (_PS.SwName if _is_id_start(la) else _U))
        ),
        lambda c, la, o: _PS.SwName if (c == "/" and _is_id_start(la)) else _U,
        lambda c, la, o: _PS.SwStart if _is_ws(c) else _U,
    ],

    _PS.SwStartCnt: [
        lambda c, la, o: _start(o, None, _PS.SwName),
    ],

    _PS.SwName: [
        lambda c, la, o: (
            _U if not _is_id_start(c) else
            (_start(o, None, _PS.SwNameOrEnd, c) if _is_id_middle(la) else
             _se(o, None, _PS.SwEndOrVal, c))
        ),
    ],

    _PS.SwNameOrEnd: [
        lambda c, la, o: (
            _app(o, _PS.SwNameOrEnd, c) if _is_id_middle(la) else
            _ae(o, _PS.SwEndOrVal, c)
        ),
    ],

    _PS.SwEndOrVal: [
        lambda c, la, o: (
            _U if c != "-" else
            (_PS.SwStartCnt if la == "-" else
             (_PS.SwName if _is_id_start(la) else _U))
        ),
        lambda c, la, o: _PS.SwName if (c == "/" and _is_id_start(la)) else _U,
        lambda c, la, o: _PS.FirstVal if c == ":" else _U,
        lambda c, la, o: _PS.SwEndOrVal if _is_ws(c) else _U,
    ],

    _PS.FirstVal: [
        lambda c, la, o: (
            _U if not _is_id_start(c) else
            (_start(o, OptValueKind.Id, _PS.IdVal, c) if _is_id_middle(la) else
             _se(o, OptValueKind.Id, _PS.Next, c))
        ),
        lambda c, la, o: (
            _U if not c.isdigit() else
            (_start(o, OptValueKind.Integer, _PS.IntVal, c) if la.isdigit() else
             _se(o, OptValueKind.Integer, _PS.Next, c))
        ),
        lambda c, la, o: (
            _start(o, OptValueKind.String, _PS.EStrVal) if c == '"' else _U
        ),
        lambda c, la, o: (
            _start(o, OptValueKind.String, _PS.StrValStart) if (c == "'" and la == '"') else _U
        ),
        lambda c, la, o: _PS.FirstVal if _is_ws(c) else _U,
    ],

    _PS.IdVal: [
        lambda c, la, o: (
            _app(o, _PS.IdVal, c) if _is_id_middle(la) else
            _ae(o, _PS.Next, c)
        ),
    ],

    _PS.IntVal: [
        lambda c, la, o: (
            _app(o, _PS.IntVal, c) if la.isdigit() else
            _ae(o, _PS.Next, c)
        ),
    ],

    _PS.StrValStart: [
        lambda c, la, o: _PS.StrVal,
    ],

    _PS.StrVal: [
        lambda c, la, o: (
            _PS.StrValEnd if (c == '"' and la == "'") else
            _app(o, _PS.StrVal, c)
        ),
    ],

    _PS.StrValEnd: [
        lambda c, la, o: _end(o, _PS.Next),
    ],

    _PS.EStrVal: [
        lambda c, la, o: _PS.EStrValEsc if c == "\\" else _U,
        lambda c, la, o: (
            _end(o, _PS.Next) if c == '"' else
            _app(o, _PS.EStrVal, c)
        ),
    ],

    _PS.EStrValEsc: [
        lambda c, la, o: _app_esc(o, _PS.EStrVal, c),
    ],

    _PS.Next: [
        lambda c, la, o: (
            _U if c != "-" else
            (_PS.SwStartCnt if la == "-" else
             (_PS.SwName if _is_id_start(la) else _U))
        ),
        lambda c, la, o: _PS.SwName if (c == "/" and _is_id_start(la)) else _U,
        lambda c, la, o: _PS.FirstVal if c == "," else _U,
        lambda c, la, o: _PS.Next if _is_ws(c) else _U,
    ],
}


# ── Public API ────────────────────────────────────────────────────────

def parse_switch_string(switch_string: str) -> Tuple[bool, Options, int]:
    """Parse a switch string.

    Returns ``(success, options, err_pos)``.  On success *err_pos* is 0.

    A switch string may contain flags (``-f``, ``--flag``) and switches
    with values (``-s:val1,val2``, ``--switch:"hello"``).
    """
    options = Options()

    # Empty string is a valid (vacuous) input
    if len(switch_string) == 0:
        return True, options, 0

    state = _PS.SwStart
    la: str = switch_string[0]
    last = len(switch_string) - 1

    for i in range(len(switch_string)):
        c = la
        la = switch_string[i + 1] if i < last else "\0"
        actions = _PARSE_TABLE.get(state)
        if actions is None:
            return False, options, i

        for action in actions:
            new_state = action(c, la, options)
            if new_state != _PS.Unhandled:
                state = new_state
                break
        else:
            # All actions returned Unhandled
            return False, options, i

    # Check that we are in a valid final state
    if state in (_PS.FirstVal, _PS.StrValStart, _PS.StrVal,
                 _PS.EStrVal, _PS.EStrValEsc):
        return False, options, len(switch_string)

    options.end_token()
    return True, options, 0
