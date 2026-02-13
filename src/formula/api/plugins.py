"""Plugin interfaces for the FORMULA 2.0 API.

Ported from Microsoft.Formula.API.Plugins (Src/Core/API/Plugins/*.cs).

Defines the abstract interfaces for quotation parsers and search
strategies that can be registered with the FORMULA environment.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Sequence, TextIO, Tuple

from formula.api.nodes import Node, Span
from formula.api.constants import CnstKind


# ---------------------------------------------------------------------------
# IQuoteParser -- interface for quotation parsers
# ---------------------------------------------------------------------------

class IQuoteParser(ABC):
    """Abstract interface for a quotation parser plugin.

    Ported from Microsoft.Formula.API.Plugins.IQuoteParser.
    """

    @property
    @abstractmethod
    def description(self) -> str:
        """A description of this parser."""
        ...

    @property
    @abstractmethod
    def unquote_prefix(self) -> str:
        """The string to prefix the Id of an unquote."""
        ...

    @property
    @abstractmethod
    def suggested_data_model(self) -> Optional[Any]:
        """The suggested data model for quotes (an AST<Domain>)."""
        ...

    @property
    @abstractmethod
    def suggested_settings(self) -> Sequence[Tuple[str, CnstKind, str]]:
        """Suggested settings for this plugin."""
        ...

    @abstractmethod
    def create_instance(
        self,
        module: Any,
        collection_name: str,
        instance_name: str,
    ) -> "IQuoteParser":
        """Create an instance of this parser attached to *module*."""
        ...

    @abstractmethod
    def parse(
        self,
        config: Any,
        quote_stream: Any,
        positioner: Any,
    ) -> Tuple[bool, Optional[Any], List[Any]]:
        """Attempt to build an AST from a quote stream.

        Returns (success, results_ast, flags).
        """
        ...

    @abstractmethod
    def render(
        self,
        config: Any,
        writer: TextIO,
        ast: Any,
    ) -> Tuple[bool, List[Any]]:
        """Render an AST to a text writer.

        Returns (success, flags).
        """
        ...


# ---------------------------------------------------------------------------
# ISearchStrategy -- interface for search strategies
# ---------------------------------------------------------------------------

class ISearchStrategy(ABC):
    """Abstract interface for a solver search strategy plugin.

    Ported from Microsoft.Formula.API.Plugins.ISearchStrategy.
    """

    @property
    @abstractmethod
    def description(self) -> str:
        """A description of this strategy."""
        ...

    @property
    @abstractmethod
    def suggested_settings(self) -> Sequence[Tuple[str, CnstKind, str]]:
        """Suggested settings for this plugin."""
        ...

    @abstractmethod
    def create_instance(
        self,
        module: Any,
        collection_name: str,
        instance_name: str,
    ) -> "ISearchStrategy":
        """Create an instance of this strategy attached to *module*."""
        ...

    @abstractmethod
    def begin(self, solver: Any) -> Tuple["ISearchStrategy", List[Any]]:
        """Begin enumeration for a specific solving task.

        Returns (strategy_instance, flags).
        """
        ...

    @abstractmethod
    def get_next_cmd(self) -> Optional[Any]:
        """Return the next set of DOFs for search, or ``None`` to stop."""
        ...


# ---------------------------------------------------------------------------
# SourcePositioner -- maps (line, col) in quote stream to source positions
# ---------------------------------------------------------------------------

class SourcePositioner:
    """Maps zero-indexed (line, col) pairs to locations in a source program.

    Ported from Microsoft.Formula.API.Plugins.SourcePositioner.
    A simplified Python version; full implementation requires tracking
    quote runs and escape ids.
    """

    def __init__(self, quote_span: Span):
        self._quote_span = quote_span

    def get_source_position(
        self,
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
    ) -> Span:
        """Map a span in the quote stream to a span in the source."""
        sl = self._quote_span.start_line + start_line
        sc = self._quote_span.start_col + start_col
        el = self._quote_span.start_line + end_line
        ec = self._quote_span.start_col + end_col
        return Span(sl, sc, el, ec, self._quote_span.program)
