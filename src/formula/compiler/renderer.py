"""
Port of Microsoft.Formula.Compiler.Renderer (Renderer.cs).

The Renderer takes a compiled module AST and "renders" any quotation
nodes back into concrete FORMULA syntax using the configured renderer
plugin (``parse_ActiveRenderer``).

If no renderer is configured, quotation nodes are left unchanged.  If a
renderer produces a string result, that string is re-parsed into an AST
fragment and spliced in place of the original quotation.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from formula.compiler.configuration import (
    Configuration,
    CnstKind,
    Flag,
    NodeKind,
    SeverityKind,
)


# ---------------------------------------------------------------------------
# RenderResult  (accumulator for rendering outcomes)
# ---------------------------------------------------------------------------

class RenderResult:
    """Collects the outcome of a render pass."""

    def __init__(self) -> None:
        self.succeeded: bool = True
        self.module: Any = None
        self._flags: List[Flag] = []

    @property
    def flags(self) -> List[Flag]:
        return list(self._flags)

    def add_flag(self, flag: Flag) -> None:
        self._flags.append(flag)
        if flag.severity == SeverityKind.Error:
            self.succeeded = False

    def add_flags(self, flags) -> None:
        if flags is None:
            return
        for f in flags:
            self.add_flag(f)

    def failed(self) -> None:
        self.succeeded = False


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class Renderer:
    """
    Renders quotation nodes in a module AST back to concrete syntax.

    Parameters
    ----------
    source_module : Any
        The (possibly reduced) module AST.
    result : RenderResult
        Accumulator for the rendering outcome.
    cancel : callable, optional
        Returns True when cancellation is requested.
    """

    def __init__(
        self,
        source_module: Any,
        result: RenderResult,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._source_module = source_module
        self._result = result
        self._cancel = cancel or (lambda: False)
        self._rendered = False

    def render(self) -> bool:
        """
        Execute the rendering pass.  Returns True on success.

        The method walks the AST top-down.  When a ``FuncTerm`` node is
        encountered under a configuration that specifies an active renderer,
        the renderer plugin's ``render()`` method is called.  The returned
        string is parsed back into an AST node and spliced in.
        """
        if self._rendered:
            return self._result.succeeded

        self._rendered = True
        config_stack: List[Configuration] = []

        # Attempt to get the reduced form
        simpl_node = self._get_reduced_or_source()

        result_node = self._walk(simpl_node, config_stack)

        if self._cancel():
            self._result.add_flag(Flag(
                SeverityKind.Error,
                self._source_module,
                "Cancelled rendering.",
                code=70,
            ))

        if self._result.succeeded and result_node is not None:
            self._result.module = result_node

        return self._result.succeeded

    # ===== Private ==========================================================

    def _get_reduced_or_source(self) -> Any:
        """
        If the source module has a reduced form (from quotation elimination),
        return it; otherwise return the source module itself.
        """
        node = getattr(self._source_module, "node", self._source_module)
        compiler_data = getattr(node, "compiler_data", None)
        if compiler_data is not None:
            reduced = getattr(compiler_data, "reduced", None)
            if reduced is not None:
                return reduced
        return self._source_module

    def _walk(self, node: Any, config_stack: List[Configuration]) -> Any:
        """
        Recursive AST walk that renders quotation nodes.

        * Config nodes are skipped (they do not produce output).
        * Nodes that own a configuration push it onto the stack.
        * FuncTerm nodes are candidates for rendering if an active renderer
          is configured.
        * All other nodes are cloned with recursively-walked children.
        """
        nk = getattr(node, "node_kind", None)

        # Skip Config nodes
        if nk == NodeKind.Config:
            return node

        # Push config if this node owns one
        conf = self._try_get_config(node)
        if conf is not None:
            config_stack.append(conf)

        try:
            if nk == NodeKind.FuncTerm:
                rendered = self._try_render_func_term(node, config_stack)
                if rendered is not None:
                    return rendered

            # Recurse into children
            children = list(getattr(node, "children", []))
            if not children:
                return node

            new_children = []
            any_changed = False
            for child in children:
                new_child = self._walk(child, config_stack)
                new_children.append(new_child)
                if new_child is not child:
                    any_changed = True

            if not any_changed:
                return node

            return self._shallow_clone(node, new_children)
        finally:
            if conf is not None:
                config_stack.pop()

    def _try_render_func_term(
        self, node: Any, config_stack: List[Configuration]
    ) -> Optional[Any]:
        """
        If the current configuration has an active renderer, use it to
        render the func-term node.  Returns the replacement node, or
        ``None`` if no rendering was done.
        """
        if not config_stack:
            return None

        conf = config_stack[-1]
        value = conf.try_get_setting(Configuration.PARSE_ACTIVE_RENDER_SETTING)
        if value is None:
            return None

        renderer_name = value.get_string_value()
        parser = conf.try_get_parser_instance(renderer_name)
        if parser is None:
            self._result.add_flag(Flag(
                SeverityKind.Error, node,
                f"Cannot find a parser named '{renderer_name}'.",
                code=71,
            ))
            return None

        try:
            import io
            sw = io.StringWriter() if hasattr(io, "StringWriter") else io.StringIO()
            render_flags: List[Flag] = []

            if hasattr(parser, "render"):
                ok = parser.render(conf, sw, node, render_flags)
            else:
                ok = False
                render_flags.append(Flag(
                    SeverityKind.Error, node,
                    f"Parser '{renderer_name}' does not support rendering.",
                    code=72,
                ))

            self._result.add_flags(render_flags)

            if not ok:
                self._result.add_flag(Flag(
                    SeverityKind.Error, node,
                    "Rendering failed.", code=73,
                ))
                return None

            rendered_str = sw.getvalue()
            return self._parse_data_term(rendered_str, node)

        except Exception as exc:
            self._result.add_flag(Flag(
                SeverityKind.Error, node,
                f"Renderer plugin exception: {exc}", code=74,
            ))
            return None

    def _parse_data_term(self, text: str, blame: Any) -> Any:
        """
        Re-parse a rendered string into an AST node.
        Placeholder: in the full implementation this calls
        ``Factory.Instance.ParseDataTerm()``.
        """
        # Return a synthetic Cnst node wrapping the rendered string
        return _RenderedNode(text, blame)

    @staticmethod
    def _try_get_config(node: Any) -> Optional[Configuration]:
        """If *node* has an attached Configuration, return it."""
        config_node = getattr(node, "config", None)
        if config_node is not None:
            cd = getattr(config_node, "compiler_data", None)
            if isinstance(cd, Configuration):
                return cd
        return None

    @staticmethod
    def _shallow_clone(node: Any, new_children: list) -> Any:
        """
        Return a copy of *node* with replaced children.
        Falls back to returning the node unchanged if cloning is not
        supported.
        """
        if hasattr(node, "shallow_clone"):
            result = node
            for idx, child in enumerate(new_children):
                result = result.shallow_clone(child, idx)
            return result
        # Fallback: return a wrapper
        return _ClonedNode(node, new_children)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _RenderedNode:
    """Stand-in for a node produced by parsing a rendered string."""

    def __init__(self, text: str, blame: Any) -> None:
        self.text = text
        self.blame = blame
        self.node_kind = NodeKind.Cnst
        self.children: list = []

    def __repr__(self):
        return f"RenderedNode({self.text!r})"


class _ClonedNode:
    """Stand-in for a shallow clone of a node with new children."""

    def __init__(self, original: Any, children: list) -> None:
        self._original = original
        self.children = children
        self.node_kind = getattr(original, "node_kind", None)

    def __getattr__(self, name):
        if name.startswith("_") or name in ("children", "node_kind"):
            raise AttributeError(name)
        return getattr(self._original, name)
