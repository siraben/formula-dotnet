/**
 * FORMULA 2.0 Web Playground — main thread UI logic.
 */

// ── Example programs ─────────────────────────────────────────────

const EXAMPLES = {
  "Mapping Example": `domain Mapping
{
  Component ::= new (id: Integer, utilization: Real).
  Processor ::= new (id: Integer).
  Mapping   ::= new (c: Component, p: Processor).

  // The utilization must be > 0
  invalidUtilization :- c is Component, c.utilization <= 0.

  badMapping :- p is Processor,
    s = sum(0.0, { c.utilization |
                   c is Component, Mapping(c, p) }), s > 100.

  conforms no badMapping, no invalidUtilization.
}

partial model pm of Mapping
{
  c1 is Component(0, x).
  c2 is Component(1, y).
  p1 is Processor(0).
  Mapping(c1, p1).
  Mapping(c2, p1).
}`,

  "SEND+MORE=MONEY": `domain Money
{
  Send ::= new (s: Integer, e: Integer, n: Integer, d: Integer).
  More ::= new (m: Integer, o: Integer, r: Integer, e: Integer).
  Money ::= new (m: Integer, o: Integer, n: Integer, e: Integer, y: Integer).

  goodSend :- s is Send, s.s >= 0, s.s <= 9, s.e >= 0, s.e <= 9, s.n >= 0, s.n <= 9, s.d >= 0, s.d <= 9.
  goodMore :- m is More, m.m >= 0, m.m <= 9, m.o >= 0, m.o <= 9, m.r >= 0, m.r <= 9, m.e >= 0, m.e <= 9.
  goodMoney :- m is Money, m.m >= 0, m.m <= 9, m.o >= 0, m.o <= 9, m.n >= 0, m.n <= 9, m.e >= 0, m.e <= 9, m.y >= 0, m.y <= 9.

  goodSolution :- send is Send, more is More, money is Money,
    1000 * send.s + 100 * send.e + 10 * send.n + send.d +
    1000 * more.m + 100 * more.o + 10 * more.r + more.e =
    10000 * money.m + 1000 * money.o + 100 * money.n + 10 * money.e + money.y,
    send.s != send.e, send.s != send.n, send.s != send.d,
    send.e != send.n, send.e != send.d, send.n != send.d,
    more.m != more.o, more.m != more.r, more.m != more.e,
    more.o != more.r, more.o != more.e, more.r != more.e,
    money.m != money.o, money.m != money.n, money.m != money.e, money.m != money.y,
    money.o != money.n, money.o != money.e, money.o != money.y,
    money.n != money.e, money.n != money.y, money.e != money.y,
    send.s != money.y, send.s != more.r, send.d != more.r,
    send.e = more.e, send.n = money.n,
    more.m = money.m, more.o = money.o, more.e = money.e,
    more.m != 0.

  conforms goodSend, goodMore, goodMoney, goodSolution.
}

partial model pm of Money
{
  Send(s, e, n, d).
  More(m, o, r, e).
  Money(m, o, n, e, y).
}`,

  "Hello World": `domain Hello
{
  Greeting ::= new (msg: Integer).
  valid :- g is Greeting, g.msg >= 0, g.msg <= 100.
  conforms valid.
}

partial model pm of Hello
{
  Greeting(x).
}`,
};

// ── DOM elements ─────────────────────────────────────────────────

const editor = document.getElementById("editor");
const output = document.getElementById("output");
const runBtn = document.getElementById("run-btn");
const exampleSelect = document.getElementById("example-select");
const modelSelect = document.getElementById("model-select");
const domainSelect = document.getElementById("domain-select");
const statusEl = document.getElementById("status");

// ── State ────────────────────────────────────────────────────────

let worker = null;
let isReady = false;
let isBusy = false;
let currentModules = {};

// ── Worker setup ─────────────────────────────────────────────────

function initWorker() {
  worker = new Worker("worker.js");
  worker.onmessage = handleWorkerMessage;
  worker.onerror = (e) => {
    setStatus("error", `Worker error: ${e.message}`);
  };
}

function handleWorkerMessage(e) {
  const msg = e.data;

  switch (msg.type) {
    case "progress":
      setStatus("loading", msg.phase);
      break;

    case "ready":
      isReady = true;
      setStatus("ready", "Ready");
      runBtn.disabled = false;
      // Auto-parse current content
      requestParse();
      break;

    case "error":
      setStatus("error", msg.message);
      break;

    case "output":
      appendOutput(msg.text, msg.severity || "info");
      break;

    case "parseResult":
      handleParseResult(msg.result);
      break;

    case "solveResult":
      handleSolveResult(msg.result);
      isBusy = false;
      runBtn.disabled = false;
      runBtn.textContent = "Run";
      break;
  }
}

// ── Status ───────────────────────────────────────────────────────

function setStatus(cls, text) {
  statusEl.className = cls;
  if (cls === "loading") {
    statusEl.innerHTML = `<span class="spinner"></span>${text}`;
  } else {
    statusEl.textContent = text;
  }
}

// ── Output ───────────────────────────────────────────────────────

function clearOutput() {
  output.innerHTML = "";
}

function appendOutput(text, severity) {
  const span = document.createElement("span");
  span.className = `out-${severity}`;
  span.textContent = text;
  output.appendChild(span);

  // Auto-scroll
  const wrap = document.getElementById("output-wrap");
  wrap.scrollTop = wrap.scrollHeight;
}

// ── Parsing ──────────────────────────────────────────────────────

let parseTimer = null;

function requestParse() {
  if (!isReady || !worker) return;
  if (parseTimer) clearTimeout(parseTimer);
  parseTimer = setTimeout(() => {
    worker.postMessage({ type: "parse", code: editor.value });
  }, 500);
}

function handleParseResult(result) {
  currentModules = result.modules || {};
  updateModuleSelectors();

  // Show parse errors in output if any
  if (result.errors && result.errors.length > 0) {
    for (const err of result.errors) {
      const loc = err.line ? ` (line ${err.line})` : "";
      appendOutput(`${err.severity}: ${err.message}${loc}\n`, "error");
    }
  }
}

function updateModuleSelectors() {
  // Populate model and domain selects
  const models = [];
  const domains = [];

  for (const [name, info] of Object.entries(currentModules)) {
    if (info.kind === "model") {
      models.push({ name, ...info });
    } else if (info.kind === "domain") {
      domains.push({ name, ...info });
    }
  }

  // Model selector: prefer partial models
  modelSelect.innerHTML = "";
  // Sort partial models first
  models.sort((a, b) => (b.is_partial ? 1 : 0) - (a.is_partial ? 1 : 0));
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m.name;
    opt.textContent = m.name + (m.is_partial ? " (partial)" : "");
    modelSelect.appendChild(opt);
  }

  // Domain selector
  domainSelect.innerHTML = "";
  for (const d of domains) {
    const opt = document.createElement("option");
    opt.value = d.name;
    opt.textContent = d.name;
    domainSelect.appendChild(opt);
  }

  // Auto-select domain matching model's domain ref
  if (models.length > 0 && models[0].domain) {
    domainSelect.value = models[0].domain;
  }
}

// ── Solving ──────────────────────────────────────────────────────

function runSolve() {
  if (!isReady || isBusy || !worker) return;

  const model = modelSelect.value;
  const domain = domainSelect.value;

  if (!model || !domain) {
    clearOutput();
    appendOutput("Please select a model and domain.\n", "warning");
    return;
  }

  isBusy = true;
  runBtn.disabled = true;
  runBtn.textContent = "Solving...";
  clearOutput();
  appendOutput(`Solving ${model} against ${domain}.conforms...\n\n`, "info");

  worker.postMessage({
    type: "solve",
    code: editor.value,
    model: model,
    domain: domain,
    maxSols: 1,
  });
}

function handleSolveResult(result) {
  if (result.result === "sat") {
    appendOutput("\n--- RESULT: SAT ---\n", "success");
    if (result.solution && Object.keys(result.solution).length > 0) {
      appendOutput("Solution:\n", "success");
      for (const [k, v] of Object.entries(result.solution)) {
        appendOutput(`  ${k} = ${v}\n`, "success");
      }
    }
  } else if (result.result === "unsat") {
    appendOutput("\n--- RESULT: UNSAT ---\n", "warning");
    appendOutput("No solution satisfies all constraints.\n", "warning");
  } else if (result.result === "parse_error") {
    appendOutput("\n--- PARSE ERROR ---\n", "error");
    if (result.errors) {
      for (const err of result.errors) {
        appendOutput(`${err.message}\n`, "error");
      }
    }
  } else {
    appendOutput("\n--- ERROR ---\n", "error");
    if (result.errors) {
      for (const err of result.errors) {
        appendOutput(`${err.message}\n`, "error");
      }
    }
  }

  setStatus("ready", "Ready");
}

// ── Event listeners ──────────────────────────────────────────────

// Examples dropdown
exampleSelect.addEventListener("change", () => {
  const name = exampleSelect.value;
  if (name && EXAMPLES[name]) {
    editor.value = EXAMPLES[name];
    clearOutput();
    requestParse();
  }
});

// Run button
runBtn.addEventListener("click", runSolve);

// Keyboard shortcut: Ctrl/Cmd+Enter to run
editor.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    runSolve();
  }
  // Tab support
  if (e.key === "Tab") {
    e.preventDefault();
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    editor.value = editor.value.substring(0, start) + "  " + editor.value.substring(end);
    editor.selectionStart = editor.selectionEnd = start + 2;
  }
});

// Auto-parse on typing
editor.addEventListener("input", () => {
  requestParse();
});

// Model selector change: auto-select matching domain
modelSelect.addEventListener("change", () => {
  const modelName = modelSelect.value;
  const info = currentModules[modelName];
  if (info && info.domain) {
    domainSelect.value = info.domain;
  }
});

// ── Initialize ───────────────────────────────────────────────────

// Load default example
editor.value = EXAMPLES["Mapping Example"];
setStatus("loading", "Initializing...");
runBtn.disabled = true;
initWorker();
