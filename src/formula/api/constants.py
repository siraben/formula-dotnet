"""
Constants and enumerations for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.Constants (Src/Core/API/Base/Constants.cs).
"""

from enum import IntEnum, auto


class ContractKind(IntEnum):
    ConformsProp = 0
    EnsuresProp = auto()
    RequiresProp = auto()
    RequiresSome = auto()
    RequiresAtLeast = auto()
    RequiresAtMost = auto()


class ComposeKind(IntEnum):
    Non = 0
    Includes = auto()
    Extends = auto()


class RelKind(IntEnum):
    No = 0
    Eq = auto()
    Neq = auto()
    Le = auto()
    Lt = auto()
    Ge = auto()
    Gt = auto()
    Typ = auto()


class SeverityKind(IntEnum):
    Info = 0
    Warning = 1
    Error = 2


class MapKind(IntEnum):
    Fun = 0
    Inj = auto()
    Bij = auto()
    Sur = auto()


class InstallKind(IntEnum):
    Compiled = 0
    Failed = auto()
    Cached = auto()
    Uninstalled = auto()


class CnstKind(IntEnum):
    Numeric = 0
    String = auto()


class NodeKind(IntEnum):
    Cnst = 0
    Id = auto()
    Range = auto()
    QuoteRun = auto()
    CardPair = auto()
    Quote = auto()
    FuncTerm = auto()
    Find = auto()
    ModelFact = auto()
    Compr = auto()
    RelConstr = auto()
    Body = auto()
    Rule = auto()
    ContractItem = auto()
    Setting = auto()
    Config = auto()
    Field = auto()
    Enum = auto()
    Union = auto()
    ConDecl = auto()
    MapDecl = auto()
    UnnDecl = auto()
    Step = auto()
    ModRef = auto()
    ModApply = auto()
    Param = auto()
    Domain = auto()
    Transform = auto()
    TSystem = auto()
    Model = auto()
    Machine = auto()
    Property = auto()
    Update = auto()
    Program = auto()
    Folder = auto()
    AnyNodeKind = auto()


class OpKind(IntEnum):
    Add = 0
    And = auto()
    AndAll = auto()
    Count = auto()
    Div = auto()
    GCD = auto()
    GCDAll = auto()
    Impl = auto()
    IsSubstring = auto()
    LCM = auto()
    LCMAll = auto()
    LstLength = auto()
    LstReverse = auto()
    LstFind = auto()
    LstFindAll = auto()
    LstFindAllNot = auto()
    LstGetAt = auto()
    Max = auto()
    MaxAll = auto()
    Min = auto()
    MinAll = auto()
    Mod = auto()
    Mul = auto()
    Neg = auto()
    Not = auto()
    Or = auto()
    OrAll = auto()
    Prod = auto()
    Qtnt = auto()
    RflIsMember = auto()
    RflIsSubtype = auto()
    RflGetArgType = auto()
    RflGetArity = auto()
    Sign = auto()
    StrAfter = auto()
    StrBefore = auto()
    StrFind = auto()
    StrGetAt = auto()
    StrJoin = auto()
    StrReplace = auto()
    StrLength = auto()
    StrLower = auto()
    StrReverse = auto()
    StrUpper = auto()
    SymAnd = auto()
    SymAndAll = auto()
    SymCount = auto()
    SymMax = auto()
    Sub = auto()
    Sum = auto()
    ToNatural = auto()
    ToOrdinal = auto()
    ToList = auto()
    ToString = auto()
    ToSymbol = auto()


class ReservedOpKind(IntEnum):
    """Reserved operations introduced by the compiler.

    The user cannot access these operations directly, though they may
    be introduced by the compiler and appear in compiler-generated data.
    """
    Range = 0       # Range(x, y): constructs a type for the interval [x, y]
    TypeUnn = auto()    # TypeUnn(x, y): union of types x and y
    Relabel = auto()    # Relabel(p, p', x): relabels prefixes of constructor applications
    Select = auto()     # Select(x, y): returns argument named y from data term x
    Find = auto()       # Find(t, p, tp): represents a find operation
    Conj = auto()       # Conj(x, y): conjunction of two body constraints
    ConjR = auto()      # ConjR(x, y): conjunction of two disjoint partial rules / projections
    Disj = auto()       # Disj(x, y): disjunction of two partial rules / projections
    Proj = auto()       # Proj(rule, vars): projection of a partial rule / projection
    PRule = auto()      # PRule(f1, f2, body): partial rule with finds
    CRule = auto()      # CRule(h, compr, rule): rule computing part of a comprehension
    Rule = auto()       # Rule(h, rule): complete rule as a term
    Compr = auto()      # Compr(heads, reads, disj): a comprehension


class AttributeKind(IntEnum):
    Cardinality = 0
    CnstKind = auto()
    Raw = auto()
    Name = auto()
    IsNew = auto()
    IsSub = auto()
    ContractKind = auto()
    ComposeKind = auto()
    IsAny = auto()
    Op = auto()
    MapKind = auto()
    IsPartial = auto()
    Rename = auto()
    Location = auto()
    Text = auto()
    Lower = auto()
    Upper = auto()


class ChildContextKind(IntEnum):
    Operator = 0
    Args = auto()
    Initials = auto()
    Nexts = auto()
    Dom = auto()
    Cod = auto()
    Includes = auto()
    Domain = auto()
    Binding = auto()
    Match = auto()
    Inputs = auto()
    Outputs = auto()
    AnyChildContext = auto()


class NodePredicateKind(IntEnum):
    Atom = 0
    false_ = auto()
    Star = auto()
    Or = auto()


class BuilderResultKind(IntEnum):
    Success = 0
    Fail_Closed = auto()
    Fail_BadArgs = auto()


class EnvParamKind(IntEnum):
    """Environment parameter kinds.

    Msgs_SuppressPaths: If true, messages will not include path names,
        only file names (default: true).
    Printer_ReferencePrintKind: Determines how to print references in an AST
        (default: ReferencePrintKind.Verbatim).
    """
    Msgs_SuppressPaths = 0
    Printer_ReferencePrintKind = auto()


class ReferencePrintKind(IntEnum):
    """Controls how module references are printed.

    Verbatim: Print the location string exactly as it appeared in the AST.
    Relative: If resolved and printing to a file, print relative to the
        output file. Otherwise behave like Absolute.
    Absolute: If resolved, print the full URI. Otherwise behave like Verbatim.
    """
    Verbatim = 0
    Relative = auto()
    Absolute = auto()


# ---------------------------------------------------------------------------
# MessageString: lightweight struct for formatted error / warning messages
# ---------------------------------------------------------------------------

class MessageString:
    """A message template with a numeric code, analogous to the C# struct."""

    __slots__ = ("message", "code")

    def __init__(self, message: str, code: int):
        self.message = message
        self.code = code

    def format(self, *args) -> str:
        if self.message is None:
            return ""
        try:
            return self.message.format(*args)
        except (IndexError, KeyError):
            return self.message

    def __repr__(self) -> str:
        return f"MessageString({self.message!r}, {self.code})"


# ---------------------------------------------------------------------------
# Pre-defined message constants (mirrors Constants class in C#)
# ---------------------------------------------------------------------------

OP_CANCELLED = MessageString("{0}. The operation was cancelled", 0)
OP_FAILED = MessageString("The {0} operation failed", 1)
BAD_FILE = MessageString("File access error - {0}", 2)
BAD_SYNTAX = MessageString("Syntax error - {0}", 3)
BAD_ID = MessageString("{0} is not a legal {1} identifier", 4)
BAD_SETTING = MessageString("Cannot set {0} to \"{1}\" - {2}", 5)
BAD_NUMERIC = MessageString("{0} is not a legal numerical constant", 6)
BAD_DEP_CYCLE = MessageString("Cyclic dependency error - {0} cycle {1}", 7)
DUPLICATE_DEFS = MessageString(
    "The {0} has multiple definitions. See {1} and {2}", 8
)
UNDEFINED_SYMBOL = MessageString("The {0} {1} is undefined.", 9)
PLUGIN_EXCEPTION = MessageString("Plugin {0}.{1} threw an exception. {2}", 10)
QUOTATION_ERROR = MessageString("Could not parse or render. {0}", 11)
ALREADY_INSTALLED_ERROR = MessageString(
    "A program called {0} is already installed in this environment. "
    "You must uninstall it first.",
    12,
)
AMBIGUOUS_SYMBOL = MessageString(
    "The {0} {1} is ambiguous. See {2} and {3}", 13
)
BAD_TYPE_DECL = MessageString("The type {0} is badly defined; {1}", 13)
BAD_COMPOSITION = MessageString("Cannot compose {0}; {1}", 14)
BAD_TRANSFORM = MessageString(
    "The transform {0} is badly defined; {1}", 15
)
BAD_TRANS_MODEL_ARG_TYPE = MessageString(
    "Argument {0} of {1} is badly typed; got {2} but expected {3}.", 16
)
BAD_TRANS_OUTPUT_TYPE = MessageString(
    "Output {0} is badly typed; got {1} but expected {2}.", 16
)
BAD_TRANS_VALUE_ARG_TYPE = MessageString(
    "Argument {0} of {1} is badly typed.", 16
)
BAD_ARG_TYPE = MessageString(
    "Argument {0} of function {1} is badly typed.", 16
)
BAD_ARG_TYPES = MessageString(
    "The arguments of function {0} are badly typed.", 16
)
BAD_CONSTRAINT = MessageString("This constraint is unsatisfiable.", 17)
UNSAFE_ARG_TYPE = MessageString(
    "Argument {0} of function {1} is unsafe. "
    "Some values of type {2} are not allowed here.",
    18,
)
UNCOERCIBLE_ARG_TYPE = MessageString(
    "Argument {0} of function {1} is badly typed. "
    "Cannot coerce values of type {2}.",
    19,
)
AMBIGUOUS_COERCIBLE_ARG = MessageString(
    "Argument {0} of function {1} has an ambiguous coercion; "
    'possibly "{2}" -> "{3}".',
    20,
)
FIND_HIDES_ERROR = MessageString(
    "Variable {0} in parent scope is hidden by find.", 21
)
UNORIENTED_ERROR = MessageString("Variable {0} cannot be oriented.", 22)
TRANS_UNORIENTED_ERROR = MessageString(
    "Model variable {0} cannot be oriented.", 22
)
MODEL_GROUNDING_ERROR = MessageString(
    "Symbolic constant {0} does not stand for a ground term.", 23
)
LABEL_CLASH_ERROR = MessageString(
    "The label name {0} clashes with a module name of the same name.", 24
)
STRATIFICATION_ERROR = MessageString(
    "A set comprehension depends on itself. {0}", 25
)
ARG_NEWNESS_ERROR = MessageString(
    "The new-kind constructor {0} cannot accept derived values of type {1} "
    "in argument {2}.",
    26,
)
SUB_ARG_NEWNESS_ERROR = MessageString(
    "The derived-kind sub constructor {0} cannot accept derived values of "
    "type {1} in argument {2}.",
    26,
)
RELATIONAL_ERROR = MessageString(
    "The constructor {0} cannot have relational constraints on itself; "
    "see argument {1}.",
    27,
)
TOTALITY_ERROR = MessageString(
    "The function {0} requires totality on an argument supported by an "
    "infinite number of values; see argument {1}.",
    28,
)
TRANS_NEWNESS_ERROR = MessageString(
    "Transforms cannot define new-kind constructors.", 29
)
DUPLICATE_FIND_ERROR = MessageString(
    "The find variable {0} is defined twice.", 30
)
MODEL_NEWNESS_ERROR = MessageString(
    "Models cannot contain derived-kind constants / constructors.", 31
)
ENUMERATION_ERROR = MessageString(
    "An enumeration cannot contain a symbolic constant", 32
)
MODEL_CYCLIC_DEF_ERROR = MessageString(
    "Symbolic constant {0} is defined using itself.", 33
)
MODEL_CMP_ERROR = MessageString(
    "Cannot include model {0}. It is not a model of a compatible domain.", 34
)
DERIVES_ERROR = MessageString("Rule derives {0}; {1}.", 35)
OBJECT_GRAPH_EXCEPTION = MessageString(
    "An exception occurred while creating an object graph. {0}", 36
)
CARD_CONTRACT_WARNING = MessageString(
    "Cardinality contract ignores the constant / type {0}", 37
)
CARD_NEWNESS_ERROR = MessageString(
    "Cardinality requirements cannot be placed on the derived-kind "
    "constant / constructor {0}.",
    38,
)
PLUGIN_WARNING = MessageString(
    "Plugin {0}.{1} reported a warning. {2}", 39
)
NOT_IMPLEMENTED = MessageString("Feature not implemented: {0}", 40)
SUB_RULE_UNSAT = MessageString(
    "The sub constructor {0} is unsatisfiable.", 41
)
SUB_RULE_UNTRIG = MessageString(
    "The sub constructor {0} will never be triggered in this context.", 42
)
UNINSTALL_ERROR = MessageString(
    "The file {0} could not be uninstalled because it was not installed.", 43
)
DATA_CNST_LIKE_VAR_WARNING = MessageString(
    "The variable {0} is named as if it were a data constant. "
    "All-caps should be reserved for data constants.",
    44,
)
DATA_CNST_LIKE_SYMB_WARNING = MessageString(
    "The symbolic constant {0} is named as if it were a data constant. "
    "All-caps should be reserved for data constants.",
    44,
)
PRODUCTIVITY_ERROR = MessageString(
    "Program never produces values of the form {0}", 45
)
PRODUCTIVITY_PARTIAL_ERROR = MessageString(
    "Program produces only some values of the form {0}. "
    "Listing {1} cases...",
    46,
)
PRODUCTIVITY_CASE_WARNING = MessageString(
    "Case {0}: {1}[{2} : {3}]", 47
)
PRODUCTIVITY_WARNING = MessageString(
    "Rule may construct any value accepted by constructor {0} at indices {1}",
    48,
)
NO_BINDING_TYPE_ERROR = MessageString(
    "Rule contains a variable(s) {0} with no binding type. "
    "Types are not implicitly generated for variables. Example: x is Type.",
    49,
)


# ---------------------------------------------------------------------------
# ASTSchema (singleton) – simplified representation of AST schema constants
# ---------------------------------------------------------------------------

class ASTSchema:
    """Singleton providing standard names and op-kind resolution.

    Ported from Microsoft.Formula.API.ASTQueries.ASTSchema.
    """

    _instance = None

    @classmethod
    def get_instance(cls) -> "ASTSchema":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # Standard constant / type names
    const_name_true: str = "TRUE"
    const_name_false: str = "FALSE"
    dont_care_name: str = "_"
    type_name_constant: str = "Constant"
    type_name_data: str = "Data"

    # Operator name -> OpKind mapping
    _OP_NAME_MAP = {op.name.lower(): op for op in OpKind}

    @classmethod
    def try_get_op_kind(cls, name: str):
        """Return (True, OpKind) if *name* is a built-in operator, else (False, None)."""
        lower = name.lower()
        op = cls._OP_NAME_MAP.get(lower)
        if op is not None:
            return True, op
        return False, None
