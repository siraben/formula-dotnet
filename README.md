# FORMULA 2.0 - Formal Specifications for Verification and Synthesis
[![build](https://github.com/VUISIS/formula-dotnet/actions/workflows/build.yml/badge.svg)](https://github.com/VUISIS/formula-dotnet/actions/workflows/build.yml)

## Building and running FORMULA

### With Nix flakes (macOS/Linux)
To build and run the command line interpreter with Nix flakes:

```bash
nix run github:VUISIS/formula-dotnet
```

### With pip

Requires Python 3.11+ and a Java runtime (for ANTLR4 grammar generation).

```bash
pip install -e .
formula
```

### Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Integration tests (solver tests) require `z3-solver` and the test `.4ml` files in `Tst/`:

```bash
pytest tests/ -v -m integration
```

### Jupyter kernel

```bash
pip install -e ".[kernel]"
python -m kernel.install
```

Then open a Jupyter notebook and select the "Formula" kernel.

## CLI usage

You can exit the command line interpreter with the `exit` command. Available commands include:

- `load <file>` - Load a `.4ml` specification file
- `solve <model> <n> <domain>.conforms` - Solve for up to n models
- `query <model> <query>` - Query a model
- `print <module>` - Print a module
- `help` - Show all available commands
