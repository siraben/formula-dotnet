"""
FORMULA 2.0 Compiler layer.

Pipeline stages (in order):
    1. RegisterModules
    2. ApplyConfiguration
    3. BuildModuleDependencies
    4. EliminateQuotations
    5. BuildModules
"""

from formula.compiler.compiler import Compiler
from formula.compiler.configuration import Configuration
from formula.compiler.loader import Loader, InstallResult, ProgramName
from formula.compiler.module_data import ModuleData, PhaseKind
from formula.compiler.constraint_system import (
    ConstraintSystem,
    FreshVarKind,
    FindData,
    ComprehensionData,
    LiftedBool,
)
from formula.compiler.action import Action, ActionSet
from formula.compiler.fact_set import FactSet
from formula.compiler.optimizer import Optimizer
from formula.compiler.renderer import Renderer, RenderResult
from formula.compiler.linters import RuleLinter

__all__ = [
    "Compiler",
    "Configuration",
    "Loader",
    "InstallResult",
    "ProgramName",
    "ModuleData",
    "PhaseKind",
    "ConstraintSystem",
    "FreshVarKind",
    "FindData",
    "ComprehensionData",
    "LiftedBool",
    "Action",
    "ActionSet",
    "FactSet",
    "Optimizer",
    "Renderer",
    "RenderResult",
    "RuleLinter",
]
