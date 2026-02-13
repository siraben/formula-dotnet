"""Core API tests.

Converted from: Src/Tests/CoreTests.cs
"""

import os
from pathlib import Path

from formula.api.nodes import ProgramName, Span
from formula.api.constants import NodeKind


def test_program_name():
    """Verify ProgramName string representation."""
    name = ProgramName("models/graphs.4ml")
    name_str = str(name)
    assert "graphs.4ml" in name_str


def test_program_name_uri():
    """Verify ProgramName with file URI."""
    name = ProgramName("/tmp/test.4ml")
    assert name.uri is not None


def test_span_creation():
    """Verify Span dataclass creation."""
    span = Span(start_line=1, start_col=0, end_line=5, end_col=10)
    assert span.start_line == 1
    assert span.end_col == 10


def test_node_kinds():
    """Verify NodeKind enum values are distinct."""
    kinds = set()
    for kind in NodeKind:
        assert kind.value not in kinds or kind.name == "AnyNodeKind"
        kinds.add(kind.value)


def test_cnst_node():
    """Verify creating a constant node."""
    from formula.api.nodes import Cnst
    from formula.api.constants import CnstKind
    from fractions import Fraction

    node = Cnst(Span(), Fraction(42))
    assert node.node_kind == NodeKind.Cnst
    assert node.raw == Fraction(42)
    assert node.cnst_kind == CnstKind.Numeric


def test_id_node():
    """Verify creating an Id node."""
    from formula.api.nodes import Id

    node = Id(Span(), "myVar")
    assert node.node_kind == NodeKind.Id
    assert node.name == "myVar"


def test_func_term_node():
    """Verify creating a FuncTerm node."""
    from formula.api.nodes import FuncTerm, Id

    func = FuncTerm(Span(), Id(Span(), "Node"))
    func.add_arg(Id(Span(), "x"))
    func.add_arg(Id(Span(), "y"))

    assert func.node_kind == NodeKind.FuncTerm
    assert len(func.args) == 2
    assert func.function.name == "Node"


def test_domain_node():
    """Verify creating a Domain node."""
    from formula.api.nodes import Domain
    from formula.api.constants import ComposeKind

    domain = Domain(Span(), "TestDomain", ComposeKind.Non)
    assert domain.node_kind == NodeKind.Domain
    assert domain.name == "TestDomain"


def test_deep_clone():
    """Verify deep cloning preserves structure."""
    from formula.api.nodes import Id

    orig = Id(Span(), "test")
    clone = orig.deep_clone()
    assert clone.name == orig.name
    assert clone is not orig
