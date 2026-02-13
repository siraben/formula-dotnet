"""
Port of Microsoft.Formula.Compiler.Configuration (Configuration.cs).

Manages configuration settings for FORMULA programs and modules.
Handles setting inheritance, plugin registration (parsers, strategies),
module registration, and configuration resolution.
"""

from __future__ import annotations

from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)
from collections import OrderedDict
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Constants  (CnstKind mirrors API.Nodes.CnstKind)
# ---------------------------------------------------------------------------

class CnstKind(Enum):
    Numeric = 0
    String = 1


class NodeKind(Enum):
    """Subset of API NodeKind values used by Configuration."""
    AnyNodeKind = -1
    Program = 0
    Config = 1
    Setting = 2
    ModRef = 3
    Domain = 4
    Transform = 5
    TSystem = 6
    Model = 7
    Param = 8
    Step = 9
    Update = 10
    Rule = 11
    ContractItem = 12
    Quote = 13
    Compr = 14
    FuncTerm = 15
    Id = 16
    Cnst = 17
    Body = 18
    Find = 19
    ModelFact = 20
    QuoteRun = 21


class SeverityKind(Enum):
    Warning = 0
    Error = 1
    Info = 2


class AttributeKind(Enum):
    Name = 0


# ---------------------------------------------------------------------------
# Lightweight stand-in types (thin wrappers until full API/Common layer)
# ---------------------------------------------------------------------------

@dataclass
class Span:
    """Source span (line/col range)."""
    start_line: int = 0
    start_col: int = 0
    end_line: int = 0
    end_col: int = 0


@dataclass
class Flag:
    """Compiler diagnostic message."""
    severity: SeverityKind
    node: Any  # The AST node (or Span) related to the flag
    message: str
    code: int = 0
    program_name: Any = None


@dataclass
class Cnst:
    """Constant node (numeric or string)."""
    cnst_kind: CnstKind
    raw: Any

    def get_string_value(self) -> str:
        assert self.cnst_kind == CnstKind.String
        return str(self.raw)


@dataclass
class Location:
    """Wraps an AST reference used as a keyed location."""
    ast: Any = None
    program: Any = None

    @staticmethod
    def compare(a: "Location", b: "Location") -> int:
        return 0  # placeholder


@dataclass
class PluginSettings:
    """Settings for a registered plugin (parser or strategy)."""
    type_ref: Any = None        # Python class / type object
    constructor: Any = None     # callable
    registration: Any = None    # AST<Setting> that registered this plugin
    settings: Dict[str, Cnst] = field(default_factory=dict)

    def try_get_setting(self, name: str) -> Optional[Cnst]:
        return self.settings.get(name)


@dataclass
class EnvParams:
    """Environment parameters passed into the configuration."""
    pass


# ---------------------------------------------------------------------------
# Setting description tuples (mirrors static arrays in C#)
# ---------------------------------------------------------------------------

@dataclass
class _ColDescr:
    name: str
    type_hint: Any
    description: str


@dataclass
class _SettingDescr:
    name: str
    cnst_kind: CnstKind
    description: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Configuration:
    """
    Manages configuration data attached to a program or module AST node.

    Responsibilities:
    * Store top-level settings (solver costs, flags, etc.)
    * Register and resolve module references by name.
    * Register parser / strategy plugins and their per-plugin settings.
    * Inherit settings from parent configurations and cross-file defaults.
    * Validate settings against known validators.
    """

    # ------- Collection / setting name constants ----------------------------
    PARSERS_COLLECTION_NAME: str = "parsers"
    MODULES_COLLECTION_NAME: str = "modules"
    STRATEGIES_COLLECTION_NAME: str = "strategies"

    DEFAULTS_SETTING: str = "defaults"
    PARSE_ACTIVE_PARSER_SETTING: str = "parse_ActiveParser"
    PARSE_ACTIVE_RENDER_SETTING: str = "parse_ActiveRenderer"
    COMPILER_PRODUCTIVITY_CHECK_SETTING: str = "compiler_ProductivityCheck"
    SOLVER_ACTIVE_STRATEGY_SETTING: str = "solver_ActiveStrategy"
    SOLVER_REAL_COST_SETTING: str = "solver_RealCost"
    SOLVER_INTEGER_COST_SETTING: str = "solver_IntegerCost"
    SOLVER_NATURAL_COST_SETTING: str = "solver_NaturalCost"
    SOLVER_NEG_INTEGER_COST_SETTING: str = "solver_NegIntegerCost"
    SOLVER_POS_INTEGER_COST_SETTING: str = "solver_PosIntegerCost"
    SOLVER_STRING_COST_SETTING: str = "solver_StringCost"
    SOLVER_RECURSION_BOUND_SETTING: str = "solver_RecursionBound"
    PROOFS_KEEP_LINE_NUMBERS_SETTING: str = "proofs_KeepLineNumbers"
    PROOFS_MAX_LOCATIONS_SETTING: str = "proofs_MaxLocations"
    RULE_CLASSES_SETTING: str = "rule_Classes"
    RULE_WATCH_SETTING: str = "rule_Watch"

    # Max int sentinel (Python has arbitrary precision; use 2**31-1 for compat)
    _MAX_INT = 2**31 - 1

    # ------- Static descriptors (built once) --------------------------------

    _collection_descriptions: List[_ColDescr] = []
    _setting_descriptions: List[_SettingDescr] = []
    _top_setting_validators: Dict[str, Callable] = {}
    _initialised: bool = False

    @classmethod
    def _ensure_init(cls) -> None:
        """Lazy one-time static initialisation (mirrors the C# static ctor)."""
        if cls._initialised:
            return
        cls._initialised = True

        M = cls._MAX_INT

        # -- collection descriptions -----------------------------------------
        cls._collection_descriptions = sorted([
            _ColDescr(
                cls.MODULES_COLLECTION_NAME,
                "AST[Node]",
                f"A map from names to modules. Use {cls.MODULES_COLLECTION_NAME}.name = \"name at place.4ml\"."),
            _ColDescr(
                cls.PARSERS_COLLECTION_NAME,
                "IQuoteParser",
                f"A map from names to parsers. Use {cls.PARSERS_COLLECTION_NAME}.name = \"parserClass at implementation.dll\"."),
            _ColDescr(
                cls.STRATEGIES_COLLECTION_NAME,
                "ISearchStrategy",
                f"A map from names to search strategies. Use {cls.STRATEGIES_COLLECTION_NAME}.name = \"strategyClass at implementation.dll\"."),
        ], key=lambda d: d.name)

        # -- setting descriptions --------------------------------------------
        cls._setting_descriptions = sorted([
            _SettingDescr(cls.DEFAULTS_SETTING, CnstKind.String,
                          f"Use {cls.DEFAULTS_SETTING} = \"file.4ml\" to inherit all settings at the file scope of file.4ml."),
            _SettingDescr(cls.PARSE_ACTIVE_PARSER_SETTING, CnstKind.String,
                          f"Use {cls.PARSE_ACTIVE_PARSER_SETTING} = \"name\" to use {cls.PARSERS_COLLECTION_NAME}.name as the active quotation parser."),
            _SettingDescr(cls.PARSE_ACTIVE_RENDER_SETTING, CnstKind.String,
                          f"Use {cls.PARSE_ACTIVE_RENDER_SETTING} = \"name\" to use {cls.PARSERS_COLLECTION_NAME}.name as the active quotation render."),
            _SettingDescr(cls.COMPILER_PRODUCTIVITY_CHECK_SETTING, CnstKind.String,
                          f"Use {cls.COMPILER_PRODUCTIVITY_CHECK_SETTING} = \"F[i, j, ...], ...\" such that F ::= (T_1, ..., T_n)."),
            _SettingDescr(cls.SOLVER_ACTIVE_STRATEGY_SETTING, CnstKind.String,
                          f"Use {cls.SOLVER_ACTIVE_STRATEGY_SETTING} = \"name\" to use {cls.STRATEGIES_COLLECTION_NAME}.name as the active search strategy."),
            _SettingDescr(cls.SOLVER_REAL_COST_SETTING, CnstKind.Numeric,
                          f"Use {cls.SOLVER_REAL_COST_SETTING} = n such that 0 <= n <= {M} to increase the cost of encoding symbolic constants as reals."),
            _SettingDescr(cls.SOLVER_INTEGER_COST_SETTING, CnstKind.Numeric,
                          f"Use {cls.SOLVER_INTEGER_COST_SETTING} = n such that 0 <= n <= {M} to increase the cost of encoding symbolic constants as integers."),
            _SettingDescr(cls.SOLVER_NATURAL_COST_SETTING, CnstKind.Numeric,
                          f"Use {cls.SOLVER_NATURAL_COST_SETTING} = n such that 0 <= n <= {M} to increase the cost of encoding symbolic constants as naturals."),
            _SettingDescr(cls.SOLVER_NEG_INTEGER_COST_SETTING, CnstKind.Numeric,
                          f"Use {cls.SOLVER_NEG_INTEGER_COST_SETTING} = n such that 0 <= n <= {M} to increase the cost of encoding symbolic constants as negative integers."),
            _SettingDescr(cls.SOLVER_POS_INTEGER_COST_SETTING, CnstKind.Numeric,
                          f"Use {cls.SOLVER_POS_INTEGER_COST_SETTING} = n such that 0 <= n <= {M} to increase the cost of encoding symbolic constants as positive integers."),
            _SettingDescr(cls.SOLVER_STRING_COST_SETTING, CnstKind.Numeric,
                          f"Use {cls.SOLVER_STRING_COST_SETTING} = n such that 0 <= n <= {M} to increase the cost of encoding symbolic constants as strings."),
            _SettingDescr(cls.SOLVER_RECURSION_BOUND_SETTING, CnstKind.Numeric,
                          f"Use {cls.SOLVER_RECURSION_BOUND_SETTING} = n for 1 <= n <= {M} to set the maximum recursion depth for symbolic rules."),
            _SettingDescr(cls.PROOFS_KEEP_LINE_NUMBERS_SETTING, CnstKind.String,
                          f"Use {cls.PROOFS_KEEP_LINE_NUMBERS_SETTING} = \"TRUE\" (\"FALSE\") to so proofs can (not) locate line numbers."),
            _SettingDescr(cls.PROOFS_MAX_LOCATIONS_SETTING, CnstKind.Numeric,
                          f"Use {cls.PROOFS_MAX_LOCATIONS_SETTING} = n for 1 <= n <= 256 to set the maximum number of locations computed per proof."),
            _SettingDescr(cls.RULE_CLASSES_SETTING, CnstKind.String,
                          f"Use {cls.RULE_CLASSES_SETTING} = \"class1, ..., classn\" to tag a rule with a set of classes."),
            _SettingDescr(cls.RULE_WATCH_SETTING, CnstKind.String,
                          f"Use {cls.RULE_WATCH_SETTING} = \"TRUE\" (\"FALSE\") to (not) generate an event whenever rules fire."),
        ], key=lambda d: d.name)

        # -- top-level setting validators ------------------------------------
        v = cls._top_setting_validators
        v[cls.PARSE_ACTIVE_PARSER_SETTING] = cls._validate_string_setting
        v[cls.PARSE_ACTIVE_RENDER_SETTING] = cls._validate_string_setting
        v[cls.SOLVER_ACTIVE_STRATEGY_SETTING] = cls._validate_string_setting
        v[cls.COMPILER_PRODUCTIVITY_CHECK_SETTING] = cls._validate_string_setting
        v[cls.RULE_CLASSES_SETTING] = cls._validate_string_setting
        v[cls.RULE_WATCH_SETTING] = cls._validate_bool_setting
        v[cls.PROOFS_KEEP_LINE_NUMBERS_SETTING] = cls._validate_bool_setting
        v[cls.PROOFS_MAX_LOCATIONS_SETTING] = lambda s, f: cls._validate_int_setting(s, 1, 256, f)
        v[cls.SOLVER_REAL_COST_SETTING] = lambda s, f: cls._validate_int_setting(s, 0, M, f)
        v[cls.SOLVER_INTEGER_COST_SETTING] = lambda s, f: cls._validate_int_setting(s, 0, M, f)
        v[cls.SOLVER_NATURAL_COST_SETTING] = lambda s, f: cls._validate_int_setting(s, 0, M, f)
        v[cls.SOLVER_NEG_INTEGER_COST_SETTING] = lambda s, f: cls._validate_int_setting(s, 0, M, f)
        v[cls.SOLVER_POS_INTEGER_COST_SETTING] = lambda s, f: cls._validate_int_setting(s, 0, M, f)
        v[cls.SOLVER_STRING_COST_SETTING] = lambda s, f: cls._validate_int_setting(s, 0, M, f)
        v[cls.SOLVER_RECURSION_BOUND_SETTING] = lambda s, f: cls._validate_int_setting(s, 1, M, f)

    # ------- Static helpers for descriptions --------------------------------

    @classmethod
    def collection_descriptions(cls):
        cls._ensure_init()
        return list(cls._collection_descriptions)

    @classmethod
    def settings_descriptions(cls):
        cls._ensure_init()
        return list(cls._setting_descriptions)

    # ------- Instance -------------------------------------------------------

    def __init__(
        self,
        env_params: EnvParams,
        config_ast: Any,
        config_dep=None,
    ) -> None:
        self.__class__._ensure_init()

        self.env_params = env_params
        self.config_ast = config_ast
        self.attached_ast = config_ast  # simplified: root of owner

        # Inherited configurations (lexical or via "defaults")
        self._inherited_configs: List[Configuration] = []

        # Top-level settings (name -> Cnst)
        self._top_settings: OrderedDict[str, Cnst] = OrderedDict()

        # Module name -> Location
        self._modules: OrderedDict[str, Location] = OrderedDict()

        # Local module name -> set of Locations (for step/update equations)
        self._locals: Dict[str, Set[Location]] = {}

        # Plugin collections
        self._parsers: OrderedDict[str, PluginSettings] = OrderedDict()
        self._strategies: OrderedDict[str, PluginSettings] = OrderedDict()

        # Instantiated plugin instances (populated by create_plugins)
        self._parser_instances: Optional[Dict[str, Any]] = None
        self._strategy_instances: Optional[Dict[str, Any]] = None

        # Dispatch tables
        self._registers: Dict[str, Callable] = {
            self.PARSERS_COLLECTION_NAME: self._register_parser,
            self.STRATEGIES_COLLECTION_NAME: self._register_strategy,
            self.MODULES_COLLECTION_NAME: self._register_module_setting,
        }
        self._setters: Dict[str, Callable] = {
            self.PARSERS_COLLECTION_NAME: self._set_parser,
            self.STRATEGIES_COLLECTION_NAME: self._set_strategy,
            self.MODULES_COLLECTION_NAME: self._set_module,
        }

        self._plugins_map: Dict[str, OrderedDict[str, PluginSettings]] = {
            self.PARSERS_COLLECTION_NAME: self._parsers,
            self.STRATEGIES_COLLECTION_NAME: self._strategies,
        }

    # ------- Properties -----------------------------------------------------

    @property
    def inherited_configurations(self) -> List["Configuration"]:
        return list(self._inherited_configs)

    # ------- Setting look-up ------------------------------------------------

    def try_get_setting(self, setting_name: str) -> Optional[Cnst]:
        """
        Look up a top-level setting by name, searching inherited configs
        if not found locally.
        """
        val = self._top_settings.get(setting_name)
        if val is not None:
            return val
        for conf in self._inherited_configs:
            val = conf.try_get_setting(setting_name)
            if val is not None:
                return val
        return None

    def try_get_plugin_setting(
        self,
        coll_name: str,
        plugin_name: str,
        setting_name: str,
    ) -> Optional[Cnst]:
        """
        Look up a per-plugin setting (e.g. parsers.myParser.someSetting).
        """
        coll = self._plugins_map.get(coll_name)
        if coll is not None:
            ps = coll.get(plugin_name)
            if ps is not None:
                val = ps.try_get_setting(setting_name)
                if val is not None:
                    return val

        for conf in self._inherited_configs:
            val = conf.try_get_plugin_setting(coll_name, plugin_name, setting_name)
            if val is not None:
                return val
        return None

    # ------- Plugin instance look-up ----------------------------------------

    def try_get_parser_instance(self, plugin_name: str) -> Optional[Any]:
        if self._parser_instances is not None:
            inst = self._parser_instances.get(plugin_name)
            if inst is not None:
                return inst
        # Only walk parents if not a top-level program/module config
        for conf in self._inherited_configs:
            inst = conf.try_get_parser_instance(plugin_name)
            if inst is not None:
                return inst
        return None

    def try_get_strategy_instance(self, plugin_name: str) -> Optional[Any]:
        if self._strategy_instances is not None:
            inst = self._strategy_instances.get(plugin_name)
            if inst is not None:
                return inst
        for conf in self._inherited_configs:
            inst = conf.try_get_strategy_instance(plugin_name)
            if inst is not None:
                return inst
        return None

    # ------- Configuration application (the main driver) --------------------

    def apply_configurations(
        self,
        config_ast: Any,
        program_configs: Dict[Any, "Configuration"],
        config_deps: Any,
    ) -> Tuple[bool, List[Flag]]:
        """
        Walk all Setting nodes beneath *config_ast*, dispatch each to the
        appropriate handler (top-set, register, or plugin-set).
        Returns (succeeded, flags).
        """
        flags: List[Flag] = []
        succeeded = True
        settings = self._find_settings(config_ast)
        for setting in settings:
            if not self._set(setting, program_configs, config_deps, flags):
                succeeded = False
        return succeeded, flags

    # ------- Module registration --------------------------------------------

    def register_module(self, loc: Location) -> Tuple[bool, Optional[List[Flag]]]:
        """
        Register a module at *loc*.  The location's AST node must carry a
        ``name`` attribute.
        Returns (succeeded, flags_or_None).
        """
        name = self._get_node_name(loc.ast)
        if name is None:
            return False, [Flag(SeverityKind.Error, loc.ast, "Module has no name", 1)]

        if name in self._modules:
            other = self._modules[name]
            return False, [self._mk_duplicate_module_flag(name, other.ast, loc.ast)]

        if not _is_valid_id(name):
            return False, [
                Flag(SeverityKind.Error, loc.ast, f"Bad identifier '{name}' for module", 2)
            ]

        self._modules[name] = loc
        return True, None

    def register_modules_and_locals(
        self, parent: "Configuration"
    ) -> Tuple[bool, List[Flag]]:
        """
        Import module registrations from a parent (program-level) configuration.
        """
        flags: List[Flag] = []
        succeeded = True
        for name, loc in parent._modules.items():
            node_name = self._get_node_name(loc.ast)
            if node_name != name:
                continue
            ok, reg_flags = self.register_module(loc)
            if not ok:
                succeeded = False
            if reg_flags:
                flags.extend(reg_flags)
        ok2 = self._register_locals(flags)
        return succeeded and ok2, flags

    # ------- Module resolution ----------------------------------------------

    def try_resolve_local_module(self, name: str) -> Optional[Location]:
        """Resolve a module whose definition lives in the same program."""
        loc = self._modules.get(name)
        if loc is not None:
            return loc
        return None

    def try_resolve(
        self,
        mod_ref: Any,
        configurations: Dict[Any, "Configuration"],
        flags: List[Flag],
    ) -> Tuple[bool, Optional[Location], bool]:
        """
        Resolve a ``ModRef`` node.
        Returns (succeeded, location_or_None, is_local).
        """
        ref_location = getattr(mod_ref, "location", None)
        if ref_location is not None:
            ok, loc = self._try_resolve_absolute(mod_ref, configurations, flags)
            return ok, loc, False

        name = getattr(mod_ref, "name", None) or ""
        loc = self._modules.get(name)
        if loc is not None:
            return True, loc, False

        locs = self._locals.get(name)
        if locs:
            return True, next(iter(locs)), True

        for inh in self._inherited_configs:
            ok, loc, is_local = inh.try_resolve(mod_ref, configurations, flags)
            if ok:
                return True, loc, is_local

        return False, None, False

    # ------- Plugin creation ------------------------------------------------

    def create_plugins(self, flags: List[Flag]) -> bool:
        """
        Instantiate all registered parser and strategy plugins visible from
        this configuration.
        """
        self._parser_instances = {}
        self._strategy_instances = {}
        ok1 = self._create_plugin_instances(
            self.PARSERS_COLLECTION_NAME, self._parser_instances, flags
        )
        ok2 = self._create_plugin_instances(
            self.STRATEGIES_COLLECTION_NAME, self._strategy_instances, flags
        )
        return ok1 and ok2

    # ===== Private helpers ==================================================

    def _set(
        self,
        setting: Any,
        program_configs: Dict[Any, "Configuration"],
        config_deps: Any,
        flags: List[Flag],
    ) -> bool:
        """Dispatch a single setting node."""
        key = self._setting_key(setting)
        fragments = key.split(".")
        n = len(fragments)

        if n == 1:
            if fragments[0] == self.DEFAULTS_SETTING:
                return self._inherit(setting, program_configs, config_deps, flags)
            else:
                return self._top_set(setting, flags)
        elif n == 2:
            register = self._registers.get(fragments[0])
            if register is None:
                flags.append(Flag(
                    SeverityKind.Error, setting,
                    f"Unknown collection '{fragments[0]}'", 3))
                return False
            return register(setting, flags, program_configs)
        elif n == 3:
            setter = self._setters.get(fragments[0])
            if setter is None:
                flags.append(Flag(
                    SeverityKind.Error, setting,
                    f"Unknown collection '{fragments[0]}'", 3))
                return False
            return setter(setting, flags)
        else:
            flags.append(Flag(
                SeverityKind.Error, setting,
                "Use collections.plugin = location, or collections.plugin.key = value",
                3))
            return False

    def _top_set(self, setting: Any, flags: List[Flag]) -> bool:
        """Validate and store a top-level setting."""
        name = self._setting_key(setting)
        validator = self._top_setting_validators.get(name)
        if validator is None:
            flags.append(Flag(SeverityKind.Error, setting,
                              f"Invalid setting '{name}'", 4))
            return False

        if not validator(setting, flags):
            return False

        if name in self._top_settings:
            flags.append(Flag(SeverityKind.Error, setting,
                              f"Duplicate setting '{name}'", 5))
            return False

        self._top_settings[name] = self._setting_value(setting)
        return True

    def _inherit(
        self,
        setting: Any,
        program_configs: Dict[Any, "Configuration"],
        config_deps: Any,
        flags: List[Flag],
    ) -> bool:
        """Handle ``defaults = "file.4ml"``."""
        value = self._setting_value(setting)
        if value is None or value.cnst_kind != CnstKind.String:
            flags.append(Flag(SeverityKind.Error, setting,
                              "Expected a filename for 'defaults'", 6))
            return False

        ref_name = value.get_string_value()
        inherited_conf = program_configs.get(ref_name)
        if inherited_conf is None:
            flags.append(Flag(SeverityKind.Error, setting,
                              f"Could not find file '{ref_name}'", 7))
            return False

        self._inherited_configs.insert(0, inherited_conf)
        return True

    def _try_resolve_absolute(
        self,
        mod_ref: Any,
        configurations: Dict[Any, "Configuration"],
        flags: List[Flag],
    ) -> Tuple[bool, Optional[Location]]:
        ref_location = getattr(mod_ref, "location", "")
        name = getattr(mod_ref, "name", "")
        other_config = configurations.get(ref_location)
        if other_config is None:
            flags.append(Flag(
                SeverityKind.Error, mod_ref,
                f"Unable to load file '{ref_location}'", 8))
            return False, None

        loc = other_config._modules.get(name)
        if loc is None:
            flags.append(Flag(
                SeverityKind.Error, mod_ref,
                f"Undefined module '{name}'", 9))
            return False, None

        return True, loc

    # -- plugin registration helpers -----------------------------------------

    def _register_parser(self, setting, flags, program_configs) -> bool:
        ps = self._parsers.setdefault(
            self._setting_key_fragment(setting, 1),
            PluginSettings(),
        )
        if ps.type_ref is not None:
            flags.append(Flag(SeverityKind.Error, setting,
                              "Duplicate parser registration", 10))
            return False
        ps.registration = setting
        # Actual type loading deferred (no .dll reflection in Python)
        return True

    def _register_strategy(self, setting, flags, program_configs) -> bool:
        ps = self._strategies.setdefault(
            self._setting_key_fragment(setting, 1),
            PluginSettings(),
        )
        if ps.type_ref is not None:
            flags.append(Flag(SeverityKind.Error, setting,
                              "Duplicate strategy registration", 10))
            return False
        ps.registration = setting
        return True

    def _register_module_setting(self, setting, flags, program_configs) -> bool:
        """Handle ``modules.name = "ref at file.4ml"``."""
        mod_name = self._setting_key_fragment(setting, 1)
        if not _is_valid_id(mod_name):
            flags.append(Flag(SeverityKind.Error, setting,
                              f"Bad module identifier '{mod_name}'", 2))
            return False
        value = self._setting_value(setting)
        if value is None or value.cnst_kind != CnstKind.String:
            flags.append(Flag(SeverityKind.Error, setting,
                              "Expected a module reference string", 11))
            return False
        # Resolution deferred to BuildModuleDependencies phase
        return True

    def _set_parser(self, setting, flags) -> bool:
        plugin_name = self._setting_key_fragment(setting, 1)
        key_name = self._setting_key_fragment(setting, 2)
        ps = self._parsers.get(plugin_name)
        if ps is None:
            ps = PluginSettings()
            self._parsers[plugin_name] = ps
        ps.settings[key_name] = self._setting_value(setting)
        return True

    def _set_strategy(self, setting, flags) -> bool:
        plugin_name = self._setting_key_fragment(setting, 1)
        key_name = self._setting_key_fragment(setting, 2)
        ps = self._strategies.get(plugin_name)
        if ps is None:
            ps = PluginSettings()
            self._strategies[plugin_name] = ps
        ps.settings[key_name] = self._setting_value(setting)
        return True

    def _set_module(self, setting, flags) -> bool:
        # Per-module settings not typically used; store for future use
        return True

    def _register_locals(self, flags: List[Flag]) -> bool:
        """Register local modules (step/update). Placeholder."""
        return True

    def _create_plugin_instances(
        self,
        coll_name: str,
        instances: Dict[str, Any],
        flags: List[Flag],
    ) -> bool:
        """Instantiate all plugins in the named collection visible from here."""
        coll = self._plugins_map.get(coll_name, {})
        success = True
        for name, ps in coll.items():
            if ps.constructor is not None:
                try:
                    instances[name] = ps.constructor()
                except Exception as exc:
                    flags.append(Flag(
                        SeverityKind.Error, None,
                        f"Failed to create plugin '{name}': {exc}", 12))
                    success = False
            elif ps.type_ref is not None:
                try:
                    instances[name] = ps.type_ref()
                except Exception as exc:
                    flags.append(Flag(
                        SeverityKind.Error, None,
                        f"Failed to create plugin '{name}': {exc}", 12))
                    success = False
        # Inherit from parent configs
        for conf in self._inherited_configs:
            conf._create_plugin_instances(coll_name, instances, flags)
        return success

    # -- validation helpers --------------------------------------------------

    @staticmethod
    def _validate_string_setting(setting: Any, flags: List[Flag]) -> bool:
        value = Configuration._setting_value(setting)
        if value is None or value.cnst_kind != CnstKind.String:
            flags.append(Flag(SeverityKind.Error, setting,
                              "Expected a string value", 13))
            return False
        return True

    @staticmethod
    def _validate_bool_setting(setting: Any, flags: List[Flag]) -> bool:
        value = Configuration._setting_value(setting)
        if value is None or value.cnst_kind != CnstKind.String:
            flags.append(Flag(SeverityKind.Error, setting,
                              "Expected 'TRUE' or 'FALSE'", 14))
            return False
        sv = value.get_string_value().upper()
        if sv not in ("TRUE", "FALSE"):
            flags.append(Flag(SeverityKind.Error, setting,
                              "Expected 'TRUE' or 'FALSE'", 14))
            return False
        return True

    @staticmethod
    def _validate_int_setting(
        setting: Any, lo: int, hi: int, flags: List[Flag]
    ) -> bool:
        value = Configuration._setting_value(setting)
        if value is None or value.cnst_kind != CnstKind.Numeric:
            flags.append(Flag(SeverityKind.Error, setting,
                              f"Expected an integer in [{lo}, {hi}]", 15))
            return False
        try:
            n = int(value.raw)
        except (ValueError, TypeError):
            flags.append(Flag(SeverityKind.Error, setting,
                              f"Expected an integer in [{lo}, {hi}]", 15))
            return False
        if not (lo <= n <= hi):
            flags.append(Flag(SeverityKind.Error, setting,
                              f"Integer {n} out of range [{lo}, {hi}]", 15))
            return False
        return True

    # -- AST extraction helpers (thin adapters) ------------------------------

    @staticmethod
    def _find_settings(config_ast: Any) -> list:
        """
        Extract Setting children from a Config AST node.
        If the config_ast supports iteration (list of settings), use it;
        otherwise return an empty list.
        """
        if hasattr(config_ast, "settings"):
            return list(config_ast.settings)
        if isinstance(config_ast, (list, tuple)):
            return list(config_ast)
        return []

    @staticmethod
    def _setting_key(setting: Any) -> str:
        if isinstance(setting, dict):
            return setting.get("key", "")
        return getattr(setting, "key", "") or ""

    @staticmethod
    def _setting_key_fragment(setting: Any, idx: int) -> str:
        key = Configuration._setting_key(setting)
        parts = key.split(".")
        if idx < len(parts):
            return parts[idx]
        return ""

    @staticmethod
    def _setting_value(setting: Any) -> Optional[Cnst]:
        if isinstance(setting, dict):
            return setting.get("value")
        return getattr(setting, "value", None)

    @staticmethod
    def _get_node_name(node: Any) -> Optional[str]:
        if node is None:
            return None
        if isinstance(node, dict):
            return node.get("name")
        return getattr(node, "name", None)

    @staticmethod
    def _mk_duplicate_module_flag(name, existing_node, new_node) -> Flag:
        return Flag(
            SeverityKind.Error,
            new_node,
            f"Duplicate module registration for '{name}'",
            code=16,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_valid_id(name: str) -> bool:
    """
    Very simple identifier validation (mirrors ASTSchema.IsId for basic names).
    """
    if not name:
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in name)
