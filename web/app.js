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

  "Four Queens": `domain FourQueens
{
    Queens ::= new (q1: Integer, q2: Integer, q3: Integer, q4: Integer).

    // Columns must be in range [1, 4]
    validCols :- q is Queens,
        q.q1 >= 1, q.q1 <= 4,
        q.q2 >= 1, q.q2 <= 4,
        q.q3 >= 1, q.q3 <= 4,
        q.q4 >= 1, q.q4 <= 4.

    // No two queens in the same column
    distinctCols :- q is Queens,
        q.q1 != q.q2, q.q1 != q.q3, q.q1 != q.q4,
        q.q2 != q.q3, q.q2 != q.q4,
        q.q3 != q.q4.

    // No two queens on the same diagonal
    noDiagonals :- q is Queens,
        q.q1 - q.q2 != 1, q.q2 - q.q1 != 1,
        q.q1 - q.q3 != 2, q.q3 - q.q1 != 2,
        q.q1 - q.q4 != 3, q.q4 - q.q1 != 3,
        q.q2 - q.q3 != 1, q.q3 - q.q2 != 1,
        q.q2 - q.q4 != 2, q.q4 - q.q2 != 2,
        q.q3 - q.q4 != 1, q.q4 - q.q3 != 1.

    conforms validCols, distinctCols, noDiagonals.
}

partial model pm of FourQueens
{
    Queens(a, b, c, d).
}`,

  "Graph Coloring": `domain GraphColoring
{
    Coloring ::= new (v0: Integer, v1: Integer, v2: Integer, v3: Integer).

    // Every vertex gets a color in {1, 2, 3}
    validRange :- c is Coloring,
        c.v0 >= 1, c.v0 <= 3,
        c.v1 >= 1, c.v1 <= 3,
        c.v2 >= 1, c.v2 <= 3,
        c.v3 >= 1, c.v3 <= 3.

    // K4: every pair of vertices is adjacent
    noConflict :- c is Coloring,
        c.v0 != c.v1,
        c.v0 != c.v2,
        c.v0 != c.v3,
        c.v1 != c.v2,
        c.v1 != c.v3,
        c.v2 != c.v3.

    conforms validRange, noConflict.
}

// K4 needs 4 colors, so 3-coloring is UNSAT
partial model pm3 of GraphColoring
{
    Coloring(a, b, c, d).
}`,

  "Magic Square": `domain MagicSquare
{
    Grid ::= new (c00: Integer, c01: Integer, c02: Integer,
                  c10: Integer, c11: Integer, c12: Integer,
                  c20: Integer, c21: Integer, c22: Integer).

    // Each cell contains a value in [1, 9]
    validRange :- g is Grid,
        g.c00 >= 1, g.c00 <= 9,
        g.c01 >= 1, g.c01 <= 9,
        g.c02 >= 1, g.c02 <= 9,
        g.c10 >= 1, g.c10 <= 9,
        g.c11 >= 1, g.c11 <= 9,
        g.c12 >= 1, g.c12 <= 9,
        g.c20 >= 1, g.c20 <= 9,
        g.c21 >= 1, g.c21 <= 9,
        g.c22 >= 1, g.c22 <= 9.

    // All nine values are distinct
    allDistinct :- g is Grid,
        g.c00 != g.c01, g.c00 != g.c02, g.c00 != g.c10,
        g.c00 != g.c11, g.c00 != g.c12, g.c00 != g.c20,
        g.c00 != g.c21, g.c00 != g.c22,
        g.c01 != g.c02, g.c01 != g.c10, g.c01 != g.c11,
        g.c01 != g.c12, g.c01 != g.c20, g.c01 != g.c21,
        g.c01 != g.c22,
        g.c02 != g.c10, g.c02 != g.c11, g.c02 != g.c12,
        g.c02 != g.c20, g.c02 != g.c21, g.c02 != g.c22,
        g.c10 != g.c11, g.c10 != g.c12, g.c10 != g.c20,
        g.c10 != g.c21, g.c10 != g.c22,
        g.c11 != g.c12, g.c11 != g.c20, g.c11 != g.c21,
        g.c11 != g.c22,
        g.c12 != g.c20, g.c12 != g.c21, g.c12 != g.c22,
        g.c20 != g.c21, g.c20 != g.c22,
        g.c21 != g.c22.

    // Every row sums to 15
    rowSums :- g is Grid,
        g.c00 + g.c01 + g.c02 = 15,
        g.c10 + g.c11 + g.c12 = 15,
        g.c20 + g.c21 + g.c22 = 15.

    // Every column sums to 15
    colSums :- g is Grid,
        g.c00 + g.c10 + g.c20 = 15,
        g.c01 + g.c11 + g.c21 = 15,
        g.c02 + g.c12 + g.c22 = 15.

    // Both diagonals sum to 15
    diagSums :- g is Grid,
        g.c00 + g.c11 + g.c22 = 15,
        g.c02 + g.c11 + g.c20 = 15.

    conforms validRange, allDistinct, rowSums, colSums, diagSums.
}

partial model pm of MagicSquare
{
    Grid(a, b, c, d, e, f, g, h, i).
}`,

  "Pythagorean Triple": `domain PythagoreanTriple
{
    Triple ::= new (a: Integer, b: Integer, c: Integer).

    // All sides are positive
    positive :- t is Triple, t.a >= 1, t.b >= 1, t.c >= 1.

    // a^2 + b^2 = c^2
    pythagorean :- t is Triple, t.a * t.a + t.b * t.b = t.c * t.c.

    // Canonical order: a <= b < c
    ordered :- t is Triple, t.a <= t.b, t.b < t.c.

    // Keep solutions small
    bounded :- t is Triple, t.c <= 50.

    conforms positive, pythagorean, ordered, bounded.
}

partial model pm of PythagoreanTriple
{
    Triple(a, b, c).
}`,

  "Task Scheduling": `domain TaskScheduling
{
    Schedule ::= new (s0: Integer, s1: Integer, s2: Integer,
                      s3: Integer, s4: Integer).

    // All start times are non-negative
    validStarts :- s is Schedule,
        s.s0 >= 0, s.s1 >= 0, s.s2 >= 0, s.s3 >= 0, s.s4 >= 0.

    // Precedence: T0->T1, T0->T2, T1->T3, T2->T4
    precedences :- s is Schedule,
        s.s0 + 3 <= s.s1,
        s.s0 + 3 <= s.s2,
        s.s1 + 2 <= s.s3,
        s.s2 + 4 <= s.s4.

    // Non-overlap: sequential ordering T0,T1,T2,T3,T4
    noOverlap :- s is Schedule,
        s.s0 + 3 <= s.s1,
        s.s1 + 2 <= s.s2,
        s.s2 + 4 <= s.s3,
        s.s3 + 2 <= s.s4.

    // Makespan: all tasks finish by time 20
    bounded :- s is Schedule,
        s.s0 + 3 <= 20,
        s.s1 + 2 <= 20,
        s.s2 + 4 <= 20,
        s.s3 + 2 <= 20,
        s.s4 + 3 <= 20.

    conforms validStarts, precedences, noOverlap, bounded.
}

partial model pm of TaskScheduling
{
    Schedule(a, b, c, d, e).
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

let activeTab = "output";
const tabContent = { output: "", ast: "", types: "", details: "", rules: "" };

// ── Helpers ──────────────────────────────────────────────────────

function setStatus(cls, text) {
  statusEl.className = cls;
  statusEl.innerHTML = cls === "loading"
    ? `<span class="spinner"></span>${text}`
    : text;
}

function clearOutput() {
  output.innerHTML = "";
  tabContent.output = "";
}

function appendOutput(text, severity = "info") {
  const span = document.createElement("span");
  span.className = `out-${severity}`;
  span.textContent = text;
  output.appendChild(span);
  outputWrap.scrollTop = outputWrap.scrollHeight;
  tabContent.output = output.innerHTML;
}

function showTabContent(tab) {
  if (tab === "output") {
    output.innerHTML = tabContent.output;
  } else {
    output.textContent = tabContent[tab] || "";
  }
  outputWrap.scrollTop = 0;
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

function getInspectModule() {
  // Prefer the selected domain, fall back to first domain found
  const domain = domainSelect.value;
  if (domain) return domain;
  for (const [name, info] of Object.entries(currentModules)) {
    if (info.kind === "domain") return name;
  }
  return "";
}

function sendInspectAll() {
  if (!isReady || !worker) return;
  const mod = getInspectModule();
  const code = editor.value;
  worker.postMessage({ type: "inspectAll", code, module: mod });
}

// ── Tab switching ────────────────────────────────────────────────

function initTabs() {
  const tabs = document.querySelectorAll(".tab");
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      activeTab = btn.dataset.tab;
      showTabContent(activeTab);
    });
  });
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
      if (activeTab === "output") {
        appendOutput(data.text, data.severity || "info");
      } else {
        // Buffer output even when not on the output tab
        const span = document.createElement("span");
        span.className = `out-${data.severity || "info"}`;
        span.textContent = data.text;
        tabContent.output += span.outerHTML;
      }
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
      // Request inspection data after parse
      sendInspectAll();
      break;

    case "inspectAllResult": {
      const result = data.result || {};
      for (const view of ["ast", "types", "details", "rules"]) {
        tabContent[view] = result[view] || "";
      }
      if (activeTab !== "output") {
        showTabContent(activeTab);
      }
      break;
    }

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

  // Switch to output tab when running
  activeTab = "output";
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === "output");
  });

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
  // Clear inspect tabs
  for (const key of ["ast", "types", "details", "rules"]) {
    tabContent[key] = "";
  }
  if (activeTab !== "output") showTabContent(activeTab);
  clearTimeout(parseTimer);
  sendParse();
}

// ── Event listeners ──────────────────────────────────────────────

exampleSelect.addEventListener("change", () => loadExample(exampleSelect.value));
runBtn.addEventListener("click", runSolve);
$("clear-btn").addEventListener("click", () => {
  clearOutput();
  if (activeTab === "output") showTabContent("output");
});
editor.addEventListener("input", debouncedParse);

modelSelect.addEventListener("change", () => {
  const info = currentModules[modelSelect.value];
  if (info?.domain) domainSelect.value = info.domain;
});

domainSelect.addEventListener("change", () => {
  sendInspectAll();
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

initTabs();
editor.value = EXAMPLES["Mapping Example"];
setStatus("loading", "Initializing...");
runBtn.disabled = true;

worker = new Worker("worker.js");
worker.onmessage = handleWorkerMessage;
worker.onerror = (e) => setStatus("error", `Worker error: ${e.message}`);
