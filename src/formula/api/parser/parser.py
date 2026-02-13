"""Parser wrapper for the FORMULA 2.0 language.

Ported from Microsoft.Formula.API.Parser (Src/Core/API/Parser/Parser.cs).

Provides a high-level ``Parser`` class that combines ANTLR lexing/parsing
with the :class:`FormulaVisitor` to produce an AST.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from formula.api.constants import SeverityKind, BAD_FILE, BAD_SYNTAX, OP_CANCELLED
from formula.api.nodes import Program, ProgramName, Span
from formula.api.parser.FormulaLexer import FormulaLexer
from formula.api.parser.FormulaParser import FormulaParser
from formula.api.parser.visitor import FormulaVisitor, ParseResult, Flag


# ---------------------------------------------------------------------------
# Custom ANTLR error listener that feeds into ParseResult flags
# ---------------------------------------------------------------------------

class _FormulaErrorListener(ErrorListener):
    """Collects ANTLR syntax errors as Flag objects on a ParseResult."""

    def __init__(self, parse_result: ParseResult):
        super().__init__()
        self._parse_result = parse_result

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        span = Span(line, column, line, column, self._parse_result.name)
        flag = Flag(
            SeverityKind.Error,
            span,
            BAD_SYNTAX.format(msg),
            BAD_SYNTAX.code,
            self._parse_result.name,
        )
        self._parse_result.add_flag(flag)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    """High-level parser for FORMULA programs.

    Usage::

        p = Parser()
        ok, result = p.parse_text(ProgramName(), "domain D { ... }")
        ok, result = p.parse_file(ProgramName("foo.4ml"))
    """

    def __init__(self):
        self._visitor = FormulaVisitor()

    # -----------------------------------------------------------------------
    # parse_text
    # -----------------------------------------------------------------------

    def parse_text(
        self,
        name: ProgramName,
        program_text: str,
    ) -> Tuple[bool, ParseResult]:
        """Parse FORMULA source text and return (success, ParseResult).

        Args:
            name: The program name to assign to the AST.
            program_text: The FORMULA source code as a string.

        Returns:
            A tuple ``(ok, parse_result)`` where *ok* is ``True`` if no
            errors occurred and *parse_result* holds the AST and flags.
        """
        program = Program(name)
        parse_result = self._visitor.init_parse_result(program)

        try:
            input_stream = InputStream(program_text)
            result = self._run_parser(input_stream, parse_result)
        except Exception as exc:
            flag = Flag(
                SeverityKind.Error,
                Span(),
                BAD_FILE.format(str(exc)),
                BAD_FILE.code,
                parse_result.name,
            )
            parse_result.add_flag(flag)
            return False, parse_result

        return result, parse_result

    # -----------------------------------------------------------------------
    # parse_file
    # -----------------------------------------------------------------------

    def parse_file(
        self,
        name: ProgramName,
        referrer: Optional[str] = None,
        location: Optional[Span] = None,
    ) -> Tuple[bool, ParseResult]:
        """Parse a FORMULA file and return (success, ParseResult).

        Args:
            name: A file-based ProgramName.
            referrer: Optional name of a referring module (for error messages).
            location: Optional source span of the reference (for error messages).

        Returns:
            A tuple ``(ok, parse_result)`` where *ok* is ``True`` if no
            errors occurred.
        """
        if location is None:
            location = Span()

        program = Program(name)
        parse_result = self._visitor.init_parse_result(program)

        try:
            abs_path = name.abs_path
            if abs_path is None or not os.path.isfile(abs_path):
                if referrer is None:
                    msg = BAD_FILE.format(
                        f"The file {name} does not exist"
                    )
                else:
                    msg = BAD_FILE.format(
                        f"The file {name} referred to in {referrer} "
                        f"({location.start_line}, {location.start_col}) does not exist"
                    )
                flag = Flag(
                    SeverityKind.Error,
                    Span(),
                    msg,
                    BAD_FILE.code,
                    parse_result.name,
                )
                parse_result.add_flag(flag)
                return False, parse_result

            with open(abs_path, "r", encoding="utf-8") as f:
                text = f.read()

            input_stream = InputStream(text)
            result = self._run_parser(input_stream, parse_result)

        except Exception as exc:
            if referrer is None:
                msg = BAD_FILE.format(str(exc))
            else:
                msg = BAD_FILE.format(
                    f"{exc} referred to in {referrer} "
                    f"({location.start_line}, {location.start_col})"
                )
            flag = Flag(
                SeverityKind.Error,
                Span(),
                msg,
                BAD_FILE.code,
                parse_result.name,
            )
            parse_result.add_flag(flag)
            return False, parse_result

        return result, parse_result

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _run_parser(
        self,
        input_stream: InputStream,
        parse_result: ParseResult,
    ) -> bool:
        """Run the ANTLR lexer/parser and visitor on an InputStream.

        Returns True if no errors were encountered.
        """
        lexer = FormulaLexer(input_stream)
        lexer.removeErrorListeners()
        lexer.addErrorListener(_FormulaErrorListener(parse_result))

        token_stream = CommonTokenStream(lexer)

        parser = FormulaParser(token_stream)
        parser.removeErrorListeners()
        parser.addErrorListener(_FormulaErrorListener(parse_result))

        tree = parser.program()

        # If there were syntax errors during lexing/parsing, still visit
        # to get a partial AST, but report failure.
        self._visitor.visitProgram(tree)

        return parse_result.succeeded
