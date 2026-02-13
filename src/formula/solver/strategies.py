"""
Port of Src/Core/Solver/Strategies/OATStrategy.cs

The *One-At-a-Time* (OAT) strategy increments each degree-of-freedom (DOF)
independently, solves, then raises all DOFs by one and repeats.

Settings
--------
* **Limit** -- maximum number of DOFs that will be added to any constructor.
* **SolsPerInc** -- maximum number of solutions to enumerate per DOF config.
* **DOFs** -- comma-separated list of type names indicating DOFs.  Only
  new-kind constructors are used.  If not specified, every new-kind
  constructor is a DOF.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from formula.common.terms import UserSymbol
    from formula.solver.solver import ISolver


# ---------------------------------------------------------------------------
# OATStrategy
# ---------------------------------------------------------------------------

class OATStrategy:
    """
    One-at-a-time (OAT) search strategy.

    This is both the *factory* singleton (class-level) and the per-solve
    instance (created by :meth:`begin`).
    """

    LIMIT_SETTING_NAME: str = "Limit"
    SOLS_PER_INC_SETTING_NAME: str = "SolsPerInc"
    DOFS_SETTING_NAME: str = "DOFs"

    _LIST_DELIM: str = ","

    # Singleton factory instance (lazily created)
    _factory_instance: Optional["OATStrategy"] = None

    def __init__(self) -> None:
        self._limit_setting: int = 8
        self._sols_per_inc_setting: int = 1
        self._dofs_setting: Set["UserSymbol"] = set()

        self._solver: Optional["ISolver"] = None
        self._module = None
        self._collection_name: Optional[str] = None
        self._instance_name: Optional[str] = None
        self._table = None  # SymbolTable

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def the_factory_instance(cls) -> "OATStrategy":
        """Return the shared factory singleton."""
        if cls._factory_instance is None:
            cls._factory_instance = cls()
        return cls._factory_instance

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def description(self) -> str:
        return (
            "One-at-a-time (OAT) strategy: Increment each DOF independently, "
            "solve, and then raise all DOFs by one, and repeat."
        )

    @property
    def suggested_settings(self) -> List[Tuple[str, str, str]]:
        """
        Return ``[(setting_name, kind, description), ...]`` for each
        user-configurable knob.
        """
        return [
            (
                self.LIMIT_SETTING_NAME,
                "Numeric",
                "The maximum number of DOFs that will be added to any constructor",
            ),
            (
                self.SOLS_PER_INC_SETTING_NAME,
                "Numeric",
                "The maximum number of solutions to enumerate per DOF configuration",
            ),
            (
                self.DOFS_SETTING_NAME,
                "String",
                (
                    "A comma-separated list of type names indicating DOFs. "
                    "Only new-kind constructors are used. If not specified, "
                    "every new-kind constructor is a DOF."
                ),
            ),
        ]

    @property
    def module(self):
        return self._module

    @property
    def collection_name(self) -> Optional[str]:
        return self._collection_name

    @property
    def instance_name(self) -> Optional[str]:
        return self._instance_name

    @property
    def table(self):
        return self._table

    # ------------------------------------------------------------------
    # ISearchStrategy interface
    # ------------------------------------------------------------------

    def create_instance(
        self,
        module,
        collection_name: str,
        instance_name: str,
    ) -> "OATStrategy":
        """Return a new :class:`OATStrategy` bound to the given module info."""
        inst = OATStrategy()
        inst._module = module
        inst._collection_name = collection_name
        inst._instance_name = instance_name
        return inst

    def begin(
        self,
        solver: "ISolver",
        flags: List,
    ) -> Optional["OATStrategy"]:
        """
        Initialise a new strategy instance for the given *solver*.

        Reads the ``Limit``, ``SolsPerInc`` and ``DOFs`` settings from
        the solver configuration. Populates the DOF set.

        Returns
        -------
        OATStrategy or None
            A new strategy instance, or ``None`` if settings are invalid.
        """
        inst = OATStrategy()
        inst._solver = solver
        inst._module = self._module
        inst._collection_name = self._collection_name
        inst._instance_name = self._instance_name
        inst._table = getattr(solver, "symbol_table", None)

        dofs_string_setting: Optional[str] = None

        # -- Limit --
        limit_val = self._try_get_natural_setting(
            self.LIMIT_SETTING_NAME,
            solver,
            flags,
            default=8,
        )
        if limit_val is None:
            return None
        inst._limit_setting = limit_val

        # -- SolsPerInc --
        sols_val = self._try_get_natural_setting(
            self.SOLS_PER_INC_SETTING_NAME,
            solver,
            flags,
            default=1,
        )
        if sols_val is None:
            return None
        inst._sols_per_inc_setting = sols_val

        # -- DOFs --
        dofs_string_setting = self._try_get_string_setting(
            self.DOFS_SETTING_NAME,
            solver,
            flags,
            default=None,
        )

        success = True
        if dofs_string_setting is not None:
            types = dofs_string_setting.split(self._LIST_DELIM)
            for typename in types:
                if not inst._add_dofs_from_name(typename.strip(), flags):
                    success = False
        else:
            # Every new-kind constructor can be a degree of freedom
            st = getattr(solver, "symbol_table", None)
            if st is not None:
                inst._add_dofs_from_namespace(st.root)

        return inst if success else None

    def get_next_cmd(self) -> Optional[Iterator[Tuple["UserSymbol", int]]]:
        """
        Return the next DOF assignment vector, or ``None`` to terminate.

        .. note:: Not yet fully implemented.
        """
        raise NotImplementedError("OATStrategy.get_next_cmd is not yet implemented")

    # ------------------------------------------------------------------
    # Private helpers -- DOF collection
    # ------------------------------------------------------------------

    def _add_dofs_from_namespace(self, ns) -> None:
        """
        Recursively walk *ns* and add every ``MapSymb`` or new-kind
        ``ConSymb`` to the DOF set.
        """
        for s in getattr(ns, "symbols", []):
            kind = getattr(s, "kind", None)
            if kind == "MapSymb":
                self._dofs_setting.add(s)
            elif kind == "ConSymb" and getattr(s, "is_new", False):
                self._dofs_setting.add(s)

        for child_ns in getattr(ns, "children", []):
            self._add_dofs_from_namespace(child_ns)

    def _add_dofs_from_name(
        self,
        typename: str,
        flags: List,
    ) -> bool:
        """
        Resolve *typename* in the symbol table and add appropriate symbols
        to the DOF set.

        Returns ``True`` on success, ``False`` if the name is ambiguous or
        otherwise invalid.
        """
        if self._table is None:
            return True

        resolved = getattr(self._table, "resolve", lambda _: (None, None))(typename)
        if isinstance(resolved, tuple):
            symb, other = resolved
        else:
            symb = resolved
            other = None

        if symb is None:
            flags.append(
                {
                    "severity": "Error",
                    "message": f"Bad id: '{typename}' is not a valid type.",
                    "code": "BadId",
                }
            )
            return False

        if other is not None:
            flags.append(
                {
                    "severity": "Error",
                    "message": (
                        f"Ambiguous symbol: '{typename}' could be "
                        f"'{getattr(symb, 'full_name', symb)}' or "
                        f"'{getattr(other, 'full_name', other)}'."
                    ),
                    "code": "AmbiguousSymbol",
                }
            )
            return False

        kind = getattr(symb, "kind", None)

        if kind == "MapSymb":
            self._dofs_setting.add(symb)
        elif kind == "UnnSymb":
            # Walk canonical form non-range members
            canon_form = getattr(symb, "canonical_form", None)
            if canon_form is not None:
                for s in getattr(canon_form, "non_range_members", []):
                    sk = getattr(s, "kind", None)
                    if sk == "UserSortSymb":
                        data_sym = getattr(s, "data_symbol", None)
                        dk = getattr(data_sym, "kind", None)
                        if dk == "MapSymb" or (
                            dk == "ConSymb" and getattr(data_sym, "is_new", False)
                        ):
                            self._dofs_setting.add(data_sym)
                        else:
                            flags.append(
                                {
                                    "severity": "Warning",
                                    "message": (
                                        f"Plugin warning ({self._collection_name}, "
                                        f"{self._instance_name}): "
                                        f"The type / value "
                                        f"'{getattr(data_sym, 'full_name', data_sym)}' "
                                        f"is not a legal degree-of-freedom"
                                    ),
                                    "code": "PluginWarning",
                                }
                            )
                    else:
                        flags.append(
                            {
                                "severity": "Warning",
                                "message": (
                                    f"Plugin warning ({self._collection_name}, "
                                    f"{self._instance_name}): "
                                    f"The type / value "
                                    f"'{getattr(s, 'printable_name', s)}' "
                                    f"is not a legal degree-of-freedom"
                                ),
                                "code": "PluginWarning",
                            }
                        )

                range_members = getattr(canon_form, "range_members", None)
                if range_members is not None and len(range_members) > 0:
                    flags.append(
                        {
                            "severity": "Warning",
                            "message": (
                                f"Plugin warning ({self._collection_name}, "
                                f"{self._instance_name}): "
                                f"The type / value 'Integer' is not a legal degree-of-freedom"
                            ),
                            "code": "PluginWarning",
                        }
                    )
        elif kind == "ConSymb" and getattr(symb, "is_new", False):
            self._dofs_setting.add(symb)
        else:
            flags.append(
                {
                    "severity": "Warning",
                    "message": (
                        f"Plugin warning ({self._collection_name}, "
                        f"{self._instance_name}): "
                        f"The type / value "
                        f"'{getattr(symb, 'full_name', symb)}' "
                        f"is not a legal degree-of-freedom"
                    ),
                    "code": "PluginWarning",
                }
            )

        return True

    # ------------------------------------------------------------------
    # Private helpers -- settings
    # ------------------------------------------------------------------

    def _try_get_natural_setting(
        self,
        setting: str,
        solver: "ISolver",
        flags: List,
        default: int,
    ) -> Optional[int]:
        """
        Read a non-negative integer setting from the solver configuration.

        Returns the value on success, *default* if the setting is absent,
        or ``None`` if the value is invalid (an error flag is appended).
        """
        if self._module is None or self._collection_name is None or self._instance_name is None:
            return default

        conf = getattr(solver, "configuration", None)
        if conf is None:
            return default

        getter = getattr(conf, "try_get_setting", None)
        if getter is None:
            return default

        val = getter(f"{self._collection_name}.{self._instance_name}.{setting}")
        if val is None:
            return default

        try:
            n = int(val)
        except (TypeError, ValueError):
            flags.append(
                {
                    "severity": "Error",
                    "message": (
                        f"Bad setting '{setting}': value '{val}' -- "
                        f"Expected a small non-negative integer"
                    ),
                    "code": "BadSetting",
                }
            )
            return None

        if n < 0:
            flags.append(
                {
                    "severity": "Error",
                    "message": (
                        f"Bad setting '{setting}': value '{val}' -- "
                        f"Expected a small non-negative integer"
                    ),
                    "code": "BadSetting",
                }
            )
            return None

        return n

    def _try_get_string_setting(
        self,
        setting: str,
        solver: "ISolver",
        flags: List,
        default: Optional[str],
    ) -> Optional[str]:
        """
        Read a string setting from the solver configuration.

        Returns the value on success, *default* if absent, or ``None``
        if invalid (an error flag is appended).
        """
        if self._module is None or self._collection_name is None or self._instance_name is None:
            return default

        conf = getattr(solver, "configuration", None)
        if conf is None:
            return default

        getter = getattr(conf, "try_get_setting", None)
        if getter is None:
            return default

        val = getter(f"{self._collection_name}.{self._instance_name}.{setting}")
        if val is None:
            return default

        if not isinstance(val, str):
            flags.append(
                {
                    "severity": "Error",
                    "message": (
                        f"Bad setting '{setting}': value '{val}' -- "
                        f"Expected a string value"
                    ),
                    "code": "BadSetting",
                }
            )
            return None

        return val if val.strip() else default
