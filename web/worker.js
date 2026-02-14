/**
 * Web Worker (classic) — initializes Pyodide + Z3, handles parse/solve messages.
 *
 * Loading strategy:
 *  - Pyodide: importScripts (sets global loadPyodide)
 *  - z3-built.js: importScripts (sets global initZ3 — Emscripten WASM loader)
 *  - z3-solver API: dynamic import() via esm.sh (CJS→ESM + transitive deps)
 *  - browser.js init() reads global.initZ3, set by importScripts above
 */

const Z3_CDN = "https://cdn.jsdelivr.net/npm/z3-solver@4.13.4/build/";
const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.5/full/";

let pyodide = null;

function post(type, data) {
  self.postMessage({ type, ...data });
}

function progress(phase) {
  post("progress", { phase });
}

// Emscripten spawns pthread sub-workers via new Worker(z3-built.js), but
// browsers block cross-origin worker scripts. Proxy through blob URLs
// using importScripts, which IS allowed cross-origin.
function patchWorkerForCrossOrigin() {
  const OriginalWorker = self.Worker;
  self.Worker = function (url, opts) {
    if (typeof url === "string" && !url.startsWith("blob:")) {
      try {
        const parsed = new URL(url, self.location.href);
        if (parsed.origin !== self.location.origin) {
          const blob = new Blob(
            [`importScripts(${JSON.stringify(parsed.href)});`],
            { type: "application/javascript" },
          );
          return new OriginalWorker(URL.createObjectURL(blob), opts);
        }
      } catch (_) { /* fall through */ }
    }
    return new OriginalWorker(url, opts);
  };
}

async function loadZ3() {
  // __filename tells Emscripten where to find z3-built.wasm
  self.__filename = Z3_CDN + "z3-built.js";
  patchWorkerForCrossOrigin();
  importScripts(Z3_CDN + "z3-built.js");

  // browser.js reads initZ3 from `global`
  self.global = self;

  const z3Module = await import("https://esm.sh/z3-solver@4.13.4/build/browser");
  const z3 = await z3Module.init();
  self._z3ctx = new z3.Context("main");
}

async function loadPyodideAndFormula() {
  const baseUrl = self.location.href.replace(/\/[^/]*$/, "/");

  // Install ANTLR4 parser runtime
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  await micropip.install("antlr4-python3-runtime==4.13.2");

  // Unpack FORMULA source into virtual filesystem
  const resp = await fetch(baseUrl + "formula-src.tar.gz");
  if (!resp.ok) throw new Error(`Failed to fetch formula-src.tar.gz: ${resp.status}`);
  pyodide.unpackArchive(await resp.arrayBuffer(), "gztar", { extractDir: "/home/pyodide" });
  pyodide.runPython(`
import sys
if "/home/pyodide" not in sys.path:
    sys.path.insert(0, "/home/pyodide")
`);

  // Install z3 shim and formula bridge into VFS
  for (const [file, dest] of [["z3_shim.py", "z3.py"], ["formula_bridge.py", "formula_bridge.py"]]) {
    const text = await (await fetch(baseUrl + file)).text();
    pyodide.FS.writeFile("/home/pyodide/" + dest, text);
  }

  await pyodide.runPythonAsync("import formula_bridge");
}

async function init() {
  try {
    progress("Loading Python runtime...");
    importScripts(PYODIDE_CDN + "pyodide.js");
    pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });
    progress("Python runtime loaded.");

    progress("Loading Z3 solver (this may take a moment)...");
    await loadZ3();
    progress("Z3 solver loaded.");

    progress("Installing FORMULA dependencies...");
    await loadPyodideAndFormula();
    progress("FORMULA ready.");

    post("ready", {});
  } catch (err) {
    post("error", { message: `Initialization failed: ${err.message}\n${err.stack || ""}` });
  }
}

// ── Message handler ──────────────────────────────────────────────

async function handleParse(code) {
  const result = await pyodide.runPythonAsync(
    `from formula_bridge import parse; parse(${JSON.stringify(code)})`,
  );
  return JSON.parse(result);
}

async function handleSolve({ code, model, domain, maxSols }) {
  const result = await pyodide.runPythonAsync(
    `from formula_bridge import solve; solve(${JSON.stringify(code)}, ${JSON.stringify(model)}, ${JSON.stringify(domain)}, ${maxSols || 1})`,
  );
  return JSON.parse(result);
}

async function handleInspect({ code, module, view }) {
  const result = await pyodide.runPythonAsync(
    `from formula_bridge import inspect; inspect(${JSON.stringify(code)}, ${JSON.stringify(module || "")}, ${JSON.stringify(view)})`,
  );
  return JSON.parse(result);
}

const EMPTY_PARSE = { ok: false, modules: {}, errors: [] };
const EMPTY_SOLVE = { ok: false, result: "error", errors: [], output: "" };

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === "parse") {
      post("parseResult", { result: await handleParse(msg.code) });
    } else if (msg.type === "solve") {
      post("solveResult", { result: await handleSolve(msg) });
    } else if (msg.type === "inspect") {
      post("inspectResult", { result: await handleInspect(msg), view: msg.view });
    }
  } catch (err) {
    const error = { severity: "Error", message: err.message, line: 0, col: 0 };
    if (msg.type === "parse") {
      post("parseResult", { result: { ...EMPTY_PARSE, errors: [error] } });
    } else {
      post("solveResult", { result: { ...EMPTY_SOLVE, errors: [error] } });
    }
  }
};

init();
