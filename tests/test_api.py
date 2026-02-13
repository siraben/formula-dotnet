"""API tests – lexer and parser validation.

Converted from: Src/Tests/APITests.cs
"""

from antlr4 import CommonTokenStream, InputStream

from antlr4 import Token

from formula.api.parser.FormulaLexer import FormulaLexer
from formula.api.parser.FormulaParser import FormulaParser


def test_lexer():
    """Verify that 'partial model {}' produces exactly 5 tokens."""
    input_stream = InputStream("partial model {}")
    lexer = FormulaLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    token_stream.fill()
    tokens = token_stream.tokens

    assert len(tokens) == 5
    assert tokens[0].type == FormulaLexer.PARTIAL
    assert tokens[1].type == FormulaLexer.MODEL
    assert tokens[2].type == FormulaLexer.LCBRACE
    assert tokens[3].type == FormulaLexer.RCBRACE
    assert tokens[4].type == Token.EOF


def test_parser():
    """Verify that the parser can handle 'model' and 'domain' tokens."""
    input_stream = InputStream("domain Foo {}")
    lexer = FormulaLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = FormulaParser(token_stream)
    pt = parser.program()

    text = pt.getText()
    assert "domain" in text or "Foo" in text


def test_parse_simple_domain():
    """Parse a simple domain and verify the AST."""
    from formula.api.parser.parser import Parser
    from formula.api.nodes import ProgramName

    p = Parser()
    ok, pr = p.parse_text(ProgramName(), "domain D { A ::= new (x: Integer). }")
    assert ok
    assert pr.succeeded
    assert pr.program is not None
    assert len(pr.program.modules) > 0


def test_parse_model():
    """Parse a model with facts."""
    from formula.api.parser.parser import Parser
    from formula.api.nodes import ProgramName

    p = Parser()
    text = """
    domain Graph {
        Node ::= new (name: String).
        Edge ::= new (src: Node, dst: Node).
    }
    model g of Graph {
        n1 is Node("a").
        n2 is Node("b").
        Edge(n1, n2).
    }
    """
    ok, pr = p.parse_text(ProgramName(), text)
    assert ok
    assert pr.succeeded


def test_parse_send_more_money():
    """Parse the SendMoreMoney.4ml test file."""
    import os
    from formula.api.parser.parser import Parser
    from formula.api.nodes import ProgramName
    from tests.conftest import symbolic_path

    path = symbolic_path("SendMoreMoney.4ml")
    if not os.path.isfile(path):
        import pytest
        pytest.skip("SendMoreMoney.4ml not found")

    name = ProgramName(path)
    p = Parser()
    ok, pr = p.parse_file(name)
    assert ok, f"Parse failed: {[str(f) for f in pr.flags]}"
    assert pr.succeeded
