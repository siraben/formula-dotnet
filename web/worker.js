/**
 * Web Worker (classic): initializes Pyodide + Z3, handles parse/solve messages.
 *
 * Loading strategy:
 *  - Pyodide: importScripts (classic worker, sets global loadPyodide)
 *  - z3-built.js: importScripts (sets global initZ3, Emscripten WASM loader)
 *  - z3-solver high-level API: dynamic import() via esm.sh
 *    (esm.sh converts CJS→ESM and bundles transitive deps like async-mutex)
 *  - browser.js init() reads global.initZ3, which we set via importScripts
 */

let pyodide = null;

function post(type, data) {
  self.postMessage({ type, ...data });
}

async function init() {
  try {
    // Step 1: Load Pyodide
    post("progress", { phase: "Loading Python runtime (Pyodide)..." });
    importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js");
    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.5/full/",
    });
    post("progress", { phase: "Python runtime loaded." });

    // Step 2: Load z3-solver WASM
    // z3-built.js defines global `var initZ3` (Emscripten WASM module loader)
    // Set __filename so Emscripten can locate z3-built.wasm relative to the CDN,
    // not relative to the worker page URL (which would 404).
    post("progress", { phase: "Loading Z3 solver (this may take a moment)..." });
    const Z3_CDN = "https://cdn.jsdelivr.net/npm/z3-solver@4.13.4/build/";
    self.__filename = Z3_CDN + "z3-built.js";

    // Monkey-patch Worker so Emscripten's pthread sub-workers can load
    // cross-origin z3-built.js. Browsers block cross-origin worker scripts,
    // but importScripts (inside a worker) IS allowed cross-origin.
    const OriginalWorker = self.Worker;
    self.Worker = function (url, opts) {
      if (typeof url === "string" && !url.startsWith("blob:")) {
        try {
          const parsed = new URL(url, self.location.href);
          if (parsed.origin !== self.location.origin) {
            const blob = new Blob(
              [`importScripts(${JSON.stringify(parsed.href)});`],
              { type: "application/javascript" }
            );
            return new OriginalWorker(URL.createObjectURL(blob), opts);
          }
        } catch (e) { /* fall through */ }
      }
      return new OriginalWorker(url, opts);
    };

    importScripts(Z3_CDN + "z3-built.js");

    // Make initZ3 accessible as global.initZ3 (browser.js reads from `global`)
    self.global = self;

    // Load z3-solver high-level API via esm.sh (handles CJS→ESM + deps)
    const z3Module = await import(
      "https://esm.sh/z3-solver@4.13.4/build/browser"
    );
    const z3 = await z3Module.init();
    const z3ctx = new z3.Context("main");
    self._z3ctx = z3ctx;
    post("progress", { phase: "Z3 solver loaded." });

    // Step 3: Install antlr4
    post("progress", { phase: "Installing ANTLR4 parser..." });
    await pyodide.loadPackage("micropip");
    const micropip = pyodide.pyimport("micropip");
    await micropip.install("antlr4-python3-runtime==4.13.2");
    post("progress", { phase: "ANTLR4 installed." });

    // Step 4: Unpack FORMULA source
    post("progress", { phase: "Loading FORMULA source..." });
    const baseUrl = self.location.href.replace(/\/[^/]*$/, "/");
    const resp = await fetch(baseUrl + "formula-src.tar.gz");
    if (!resp.ok) throw new Error(`Failed to fetch formula-src.tar.gz: ${resp.status}`);
    const buf = await resp.arrayBuffer();
    pyodide.unpackArchive(buf, "gztar", { extractDir: "/home/pyodide" });

    pyodide.runPython(`
import sys
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
`);
    post("progress", { phase: "FORMULA source loaded." });

    // Step 5: Write z3 shim
    post("progress", { phase: "Setting up Z3 bridge..." });
    const z3ShimResp = await fetch(baseUrl + "z3_shim.py");
    const z3ShimText = await z3ShimResp.text();
    pyodide.FS.writeFile("/home/pyodide/z3.py", z3ShimText);
    post("progress", { phase: "Z3 bridge ready." });

    // Step 6: Write formula_bridge
    post("progress", { phase: "Setting up FORMULA bridge..." });
    const bridgeResp = await fetch(baseUrl + "formula_bridge.py");
    const bridgeText = await bridgeResp.text();
    pyodide.FS.writeFile("/home/pyodide/formula_bridge.py", bridgeText);

    // Pre-import the bridge
    await pyodide.runPythonAsync("import formula_bridge");
    post("progress", { phase: "FORMULA bridge ready." });

    // Step 7: Ready!
    post("ready", {});
  } catch (err) {
    post("error", { message: `Initialization failed: ${err.message}\n${err.stack || ""}` });
  }
}

// Message handler
self.onmessage = async function (e) {
  const msg = e.data;

  if (msg.type === "parse") {
    try {
      const result = await pyodide.runPythonAsync(`
from formula_bridge import parse
parse(${JSON.stringify(msg.code)})
`);
      post("parseResult", { result: JSON.parse(result) });
    } catch (err) {
      post("parseResult", {
        result: { ok: false, modules: {}, errors: [{ severity: "Error", message: err.message, line: 0, col: 0 }] },
      });
    }
  } else if (msg.type === "solve") {
    try {
      const result = await pyodide.runPythonAsync(`
from formula_bridge import solve
solve(${JSON.stringify(msg.code)}, ${JSON.stringify(msg.model)}, ${JSON.stringify(msg.domain)}, ${msg.maxSols || 1})
`);
      post("solveResult", { result: JSON.parse(result) });
    } catch (err) {
      post("solveResult", {
        result: { ok: false, result: "error", errors: [{ severity: "Error", message: err.message, line: 0, col: 0 }], output: "" },
      });
    }
  }
};

// Start initialization
init();
