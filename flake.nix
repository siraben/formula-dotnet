{
  description = "FORMULA 2.0 - Formal Specifications for Verification and Synthesis";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
    flake-compat = {
      url = "github:edolstra/flake-compat";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, utils, ... }:
    utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in {
        packages.default = pkgs.python3Packages.callPackage ./formula.nix {
          inherit (pkgs) antlr4;
        };

        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            (python3.withPackages (p: with p; [
              antlr4-python3-runtime
              z3-solver
              pytest
              pytest-cov
              hatchling
            ]))
            antlr4
          ];
          shellHook = ''
            export PYTHONPATH="$PWD/src:$PYTHONPATH"
          '';
        };
      }
    );
}
