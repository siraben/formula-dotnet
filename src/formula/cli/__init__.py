"""FORMULA 2.0 CLI layer -- Python port of Src/CommandLine/."""

from .interfaces import (
    ConsoleSink,
    ConsoleChooser,
    DigitChoiceKind,
    IChooser,
    IMessageSink,
    SeverityKind,
)
from .option_parser import Options, OptValueKind, parse_switch_string
from .task_manager import TaskKind, TaskManager
from .command_interface import CommandInterface

__all__ = [
    "CommandInterface",
    "ConsoleSink",
    "ConsoleChooser",
    "DigitChoiceKind",
    "IChooser",
    "IMessageSink",
    "Options",
    "OptValueKind",
    "SeverityKind",
    "TaskKind",
    "TaskManager",
    "parse_switch_string",
]
