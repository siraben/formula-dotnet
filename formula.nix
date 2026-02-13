{ lib, buildPythonApplication, pythonRelaxDepsHook, hatchling, antlr4-python3-runtime, z3-solver, pytestCheckHook, antlr4 }:

buildPythonApplication {
  pname = "formula";
  version = "2.0.0";
  pyproject = true;

  src = ./.;

  nativeBuildInputs = [ antlr4 pythonRelaxDepsHook ];

  pythonRemoveDeps = [ "z3-solver" ];

  build-system = [ hatchling ];

  dependencies = [
    antlr4-python3-runtime
    z3-solver
  ];

  preBuild = ''
    cd src/formula/api/parser
    antlr4 -Dlanguage=Python3 -visitor -no-listener FormulaLexer.g4 FormulaParser.g4
    cd ../../../..
  '';

  nativeCheckInputs = [
    pytestCheckHook
  ];

  meta = with lib; {
    description = "Formal Specifications for Verification and Synthesis";
    homepage = "https://github.com/VUISIS/formula-dotnet";
    license = licenses.mspl;
    maintainers = with maintainers; [ siraben ];
    platforms = platforms.unix;
    mainProgram = "formula";
  };
}
