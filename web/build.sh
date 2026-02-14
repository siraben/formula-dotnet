#!/usr/bin/env bash
# Bundle src/formula/ into a tar.gz for loading into Pyodide's virtual filesystem.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="$SCRIPT_DIR/formula-src.tar.gz"

echo "Bundling src/formula/ -> $OUT"
tar -czf "$OUT" -C "$REPO_ROOT/src" formula/
echo "Done: $(du -h "$OUT" | cut -f1) compressed"
