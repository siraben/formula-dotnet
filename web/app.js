/**
 * FORMULA 2.0 Web Playground — main thread UI logic.
 */

// ── Examples ─────────────────────────────────────────────────────

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

// ── DOM ──────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);
const editor = $("editor");
const output = $("output");
const outputWrap = $("output-wrap");
const runBtn = $("run-btn");
const exampleSelect = $("example-select");
const modelSelect = $("model-select");
const domainSelect = $("domain-select");
const statusEl = $("status");

// ── State ────────────────────────────────────────────────────────

let worker = null;
let isReady = false;
let isBusy = false;
let parseTimer = null;
let currentModules = {};

// ── Helpers ──────────────────────────────────────────────────────

function setStatus(cls, text) {
  statusEl.className = cls;
  statusEl.innerHTML = cls === "loading"
    ? `<span class="spinner"></span>${text}`
    : text;
}

function clearOutput() {
  output.innerHTML = "";
}

function appendOutput(text, severity = "info") {
  const span = document.createElement("span");
  span.className = `out-${severity}`;
  span.textContent = text;
  output.appendChild(span);
  outputWrap.scrollTop = outputWrap.scrollHeight;
}

function addOption(select, value, label) {
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = label;
  select.appendChild(opt);
}

function sendParse() {
  if (isReady && worker) {
    worker.postMessage({ type: "parse", code: editor.value });
  }
}

function debouncedParse() {
  if (!isReady || !worker) return;
  clearTimeout(parseTimer);
  parseTimer = setTimeout(sendParse, 500);
}

// ── Module selectors ─────────────────────────────────────────────

function updateModuleSelectors() {
  const models = [];
  const domains = [];
  for (const [name, info] of Object.entries(currentModules)) {
    (info.kind === "model" ? models : domains).push({ name, ...info });
  }

  models.sort((a, b) => (b.is_partial ? 1 : 0) - (a.is_partial ? 1 : 0));

  modelSelect.innerHTML = "";
  for (const m of models) {
    addOption(modelSelect, m.name, m.name + (m.is_partial ? " (partial)" : ""));
  }

  domainSelect.innerHTML = "";
  for (const d of domains) {
    addOption(domainSelect, d.name, d.name);
  }

  if (models.length > 0 && models[0].domain) {
    domainSelect.value = models[0].domain;
  }
}

// ── Worker message handling ──────────────────────────────────────

function handleWorkerMessage(e) {
  const { type, ...data } = e.data;

  switch (type) {
    case "progress":
      setStatus("loading", data.phase);
      break;

    case "ready":
      isReady = true;
      setStatus("ready", "Ready");
      runBtn.disabled = false;
      sendParse();
      break;

    case "error":
      setStatus("error", data.message);
      break;

    case "output":
      appendOutput(data.text, data.severity || "info");
      break;

    case "parseResult":
      currentModules = data.result.modules || {};
      updateModuleSelectors();
      if (data.result.errors?.length) {
        for (const err of data.result.errors) {
          const loc = err.line ? ` (line ${err.line})` : "";
          appendOutput(`${err.severity}: ${err.message}${loc}\n`, "error");
        }
      }
      break;

    case "solveResult":
      renderSolveResult(data.result);
      isBusy = false;
      runBtn.disabled = false;
      runBtn.textContent = "Run";
      setStatus("ready", "Ready");
      break;
  }
}

function renderSolveResult(result) {
  const handlers = {
    sat() {
      appendOutput("\n--- RESULT: SAT ---\n", "success");
      if (result.solution && Object.keys(result.solution).length > 0) {
        appendOutput("Solution:\n", "success");
        for (const [k, v] of Object.entries(result.solution)) {
          appendOutput(`  ${k} = ${v}\n`, "success");
        }
      }
    },
    unsat() {
      appendOutput("\n--- RESULT: UNSAT ---\n", "warning");
      appendOutput("No solution satisfies all constraints.\n", "warning");
    },
  };

  const handler = handlers[result.result];
  if (handler) {
    handler();
  } else {
    const label = result.result === "parse_error" ? "PARSE ERROR" : "ERROR";
    appendOutput(`\n--- ${label} ---\n`, "error");
    for (const err of result.errors || []) {
      appendOutput(`${err.message}\n`, "error");
    }
  }
}

// ── Actions ──────────────────────────────────────────────────────

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

  worker.postMessage({ type: "solve", code: editor.value, model, domain, maxSols: 1 });
}

function loadExample(name) {
  if (!EXAMPLES[name]) return;
  editor.value = EXAMPLES[name];
  clearOutput();
  clearTimeout(parseTimer);
  sendParse();
}

// ── Event listeners ──────────────────────────────────────────────

exampleSelect.addEventListener("change", () => loadExample(exampleSelect.value));
runBtn.addEventListener("click", runSolve);
$("clear-btn").addEventListener("click", clearOutput);
editor.addEventListener("input", debouncedParse);

modelSelect.addEventListener("change", () => {
  const info = currentModules[modelSelect.value];
  if (info?.domain) domainSelect.value = info.domain;
});

editor.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    runSolve();
  }
  if (e.key === "Tab") {
    e.preventDefault();
    const { selectionStart: s, selectionEnd: end } = editor;
    editor.value = editor.value.substring(0, s) + "  " + editor.value.substring(end);
    editor.selectionStart = editor.selectionEnd = s + 2;
  }
});

// ── Init ─────────────────────────────────────────────────────────

editor.value = EXAMPLES["Mapping Example"];
setStatus("loading", "Initializing...");
runBtn.disabled = true;

worker = new Worker("worker.js");
worker.onmessage = handleWorkerMessage;
worker.onerror = (e) => setStatus("error", `Worker error: ${e.message}`);
