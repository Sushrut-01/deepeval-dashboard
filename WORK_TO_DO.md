# DeepEval Local Dashboard — Complete Work-To-Do List
# Equivalent to: Confident AI + LangSmith + Langfuse (All Features) + QA Bug Identification
# Port: 5000 | Stack: FastAPI + Single HTML (React via CDN) | Pattern: KCRecruit
# Last updated: 2026-06-01

---

## WHAT THIS IS & WHAT IT REPLACES

This dashboard was designed across a full planning conversation covering:

1. Confident AI (SaaS) → We cannot self-host it. This dashboard is the local replacement.
2. deepeval inspect (built-in TUI) → Terminal-only, one run at a time, no history.
   This dashboard replaces it entirely with a browser UI + all missing features.
3. LangSmith features → Sessions, Threads, Online Evaluators, Automations, Webhooks,
   Playground, Prompt Hub, Custom Dashboards, Feedback, Group-by charts.
4. Langfuse features → Users page, Environments, Versions, Annotation Queues,
   Score Configs, Corrected Outputs, Agent Graph, Latency/Cost/Usage Dashboards,
   Token type breakdown, Prompt labels, LLM-as-Judge traces.
5. QA Bug System → Unique feature not in any SaaS platform. 12 bug categories,
   35 specific bugs, root cause heatmap, CI/CD gate API.

### What deepeval inspect could NOT do (all now YES in this dashboard):
| Was NO in inspect       | Now YES in dashboard                              |
|-------------------------|---------------------------------------------------|
| History across runs     | DEEPEVAL_RESULTS_FOLDER saves every run           |
| Score trends over time  | Metrics & Analytics page — line charts            |
| Score distribution      | Histogram charts per metric                       |
| Compare run A vs B      | Compare Runs page — grouped bar charts            |
| Dataset management      | Datasets page — grouped by test case name         |
| Prompt versioning       | Prompt Hub — versions + labels                    |
| Human annotation        | Annotations page + Annotation Queues              |
| A/B experiments         | Compare Runs + version grouping                   |
| CI/CD results dashboard | /api/bugs/run/{filename}/gate endpoint            |
| Search across all runs  | Spotlight (Ctrl+K) + filter bars on every page    |
| Team collaboration      | Annotation queues with reviewer assignment        |
| Alerts / notifications  | Webhooks + alert banner on Dashboard              |

---

## TECH STACK

| Layer       | Technology                                          |
|-------------|-----------------------------------------------------|
| Backend     | FastAPI (Python), Uvicorn, port 5000                |
| Frontend    | Single `dashboard.html` — React 18 CDN + Babel CDN  |
| Charts      | Chart.js 4 via CDN                                  |
| Storage     | Local JSON files (eval_history/) + annotations.json |
| Theme       | Kforce Blue (#1558CB) — reuse preview.html CSS      |
| No npm      | No webpack, no node_modules, no build step          |

---

## PROJECT STRUCTURE

```
local-dashboard/
├── WORK_TO_DO.md                  ← this file
├── requirements.txt
├── .env.example
├── run.py                         ← entry point (python run.py)
├── backend/
│   ├── main.py                    ← FastAPI app, port 5000, CORS, static mount
│   ├── config.py                  ← env vars, settings
│   ├── routers/
│   │   ├── runs.py                ← /api/runs/*
│   │   ├── metrics.py             ← /api/metrics/*
│   │   ├── traces.py              ← /api/traces/*
│   │   ├── annotations.py         ← /api/annotations/*
│   │   ├── queues.py              ← /api/queues/*
│   │   ├── sessions.py            ← /api/sessions/*
│   │   ├── users.py               ← /api/users/*
│   │   ├── usage.py               ← /api/usage/* (platform utilization stats)
│   │   ├── evaluators.py          ← /api/evaluators/* (online evals)
│   │   ├── automations.py         ← /api/automations/*
│   │   ├── webhooks.py            ← /api/webhooks/*
│   │   ├── prompts.py             ← /api/prompts/*
│   │   ├── datasets.py            ← /api/datasets/*
│   │   ├── bugs.py                ← /api/bugs/* (QA bug detection)
│   │   └── dashboard.py           ← /api/dashboard/*
│   └── services/
│       ├── run_loader.py          ← reads/parses all test_run_*.json (LLM + Conversational)
│       ├── aggregator.py          ← trends, averages, pass rates
│       ├── bug_detector.py        ← pipeline bug classification engine
│       ├── session_builder.py     ← groups traces by threadId/userId into sessions
│       ├── user_tracker.py        ← per-user cost/usage aggregation from userId in traces
│       ├── env_detector.py        ← reads env from hyperparameters/CONFIDENT_TRACE_ENVIRONMENT
│       ├── online_eval_worker.py  ← APScheduler: polls eval_history/ every 30s for new runs,
│       │                             runs bug_detector + enabled online evaluators automatically
│       └── webhook_sender.py      ← fires HTTP POST on rule match with HMAC signature
├── backend/static/
│   └── dashboard.html             ← complete single-file React frontend
└── eval_history/
    ├── test_run_*.json            ← DeepEval output (DEEPEVAL_RESULTS_FOLDER)
    ├── annotations.json           ← human annotations + scores + corrected outputs
    ├── queues.json                ← annotation queue definitions + items
    ├── score_configs.json         ← custom scoring dimension definitions
    ├── evaluators.json            ← online evaluator configs
    ├── automations.json           ← automation rule definitions
    ├── webhooks.json              ← webhook endpoint configs + delivery log
    ├── prompts.json               ← saved prompt versions with labels
    ├── sessions.json              ← thread/session groupings (built from threadId)
    ├── feedback.json              ← thumbs up/down + numeric scores per trace
    └── bug_reports.json           ← generated bug reports per run
```

---

## PHASE 1 — FOUNDATION & CONFIGURATION

### 1.1 requirements.txt
```
fastapi
uvicorn[standard]
python-dotenv
httpx
apscheduler        # online eval background jobs
```

### 1.2 .env.example
```
DEEPEVAL_RESULTS_FOLDER=./eval_history
DASHBOARD_PORT=5000
PASS_RATE_ALERT_THRESHOLD=0.70
ENVIRONMENT=development
APP_VERSION=1.0.0
AUTO_REFRESH_INTERVAL=30
```

### 1.3 main.py tasks
- [ ] FastAPI app on port 5000
- [ ] CORS allow all origins (dev mode)
- [ ] Mount /static → backend/static/
- [ ] Register all routers under /api/
- [ ] Serve dashboard.html on GET /
- [ ] On startup: verify eval_history folder exists, log run count
- [ ] Start APScheduler for online eval background worker
- [ ] Global exception handler (return JSON error, never crash)

### 1.4 run_loader.py service tasks
- [ ] Scan eval_history/ for all test_run_*.json sorted by mtime
- [ ] Parse and validate each file (skip malformed files with warning)
- [ ] Extract from LLMApiTestCase: name, input, actualOutput, expectedOutput,
        context, retrievalContext, toolsCalled, expectedTools, tokenCost,
        completionTime, tags, success, metricsData, runDuration, evaluationCost,
        trace, metadata, comments
- [ ] Extract from ConversationalApiTestCase: name, success, metricsData,
        runDuration, evaluationCost, turns (role/content/order/retrievalContext/toolsCalled),
        scenario, expectedOutcome, userDescription, context, metadata, tags
- [ ] Extract run-level: testPassed, testFailed, runDuration, evaluationCost,
        metricsScores, hyperparameters, identifier, datasetAlias, traceMetricsScores
- [ ] Auto-detect environment: read from hyperparameters.environment OR
        hyperparameters.CONFIDENT_TRACE_ENVIRONMENT OR default to "untagged"
- [ ] Auto-detect version: read from hyperparameters.version OR
        hyperparameters.APP_VERSION OR identifier field
- [ ] Extract userId and threadId from trace fields for session building
- [ ] Cache parsed runs in memory, refresh cache every 30s
- [ ] Detect new run files since last cache refresh (compare file list vs cached list)
- [ ] On new run detected: trigger bug_detector + online_eval_worker notification

### 1.5 aggregator.py service tasks
- [ ] compute_pass_rate(runs) → float per run
- [ ] compute_metric_trends(runs) → per-metric avg score over time
- [ ] compute_cost_breakdown(runs) → per-model, per-tag, per-run
- [ ] compute_latency_percentiles(spans) → P50, P95, P99
- [ ] compute_error_rates(runs) → errored spans / total spans per run
- [ ] compute_user_stats(runs) → per-userId: cost, traces, sessions
- [ ] compute_token_breakdown(runs) → input/output/cached tokens separately
- [ ] compute_version_comparison(runs) → metric scores grouped by app version
- [ ] detect_regression(runs, metric) → flag if score dropped vs prev run

---

## PHASE 2 — BACKEND API ENDPOINTS (ALL)

### 2.A Dashboard
| Method | Endpoint                    | Returns                                                     |
|--------|-----------------------------|-------------------------------------------------------------|
| GET    | /api/dashboard              | totalRuns, overallPassRate, totalCost, avgDuration, lastRunTime, errorRate, tokenTotal |
| GET    | /api/dashboard/prebuilt     | 6 sections: traces, llmCalls, costTokens, tools, runTypes, feedbackScores |
| GET    | /api/dashboard/sparklines   | Last 10 runs: passRate[], cost[], errorRate[], duration[]   |

### 2.B Runs
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/runs                        | Paginated list with filters: ?env=&version=&status=&search= |
| GET    | /api/runs/{filename}             | Full run JSON                                             |
| GET    | /api/runs/{filename}/cases       | Test cases ?status=&metric=&search=&page=&tag=            |
| GET    | /api/runs/{filename}/cases/{name}| Single test case: all fields + metricsData + trace        |
| GET    | /api/runs/{filename}/cases/{name}/trace | Full trace with all span buckets                   |
| GET    | /api/runs/{filename}/summary     | Metric breakdown + hyperparameters + pass rate            |
| DELETE | /api/runs/{filename}             | Delete JSON file from history                             |
| GET    | /api/runs/{filename}/bug-report  | Auto-generated bug report for this run                    |

### 2.C Metrics
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/metrics/trends              | Per-metric avg score per run over time                    |
| GET    | /api/metrics/summary             | All-time avg, best, worst, trend direction per metric     |
| GET    | /api/metrics/distribution/{name} | Score histogram buckets [0-0.2, 0.2-0.4 ... 0.8-1.0]     |
| GET    | /api/metrics/grouped             | ?groupBy=tag|metadata|version|env — split chart series    |

### 2.D Latency
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/latency/percentiles         | P50/P95/P99 per run, per span type                        |
| GET    | /api/latency/trends              | Avg/P95 latency over time per span type                   |
| GET    | /api/latency/breakdown           | Per span type: agent/llm/retriever/tool/base avg duration |

### 2.E Cost & Tokens
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/cost/breakdown              | Per model, per tag, per run, per userId                   |
| GET    | /api/cost/trends                 | Total cost per run over time                              |
| GET    | /api/tokens/breakdown            | Input/output/cached/total tokens per run                  |
| GET    | /api/tokens/per-model            | Token usage grouped by LLM model name                     |

### 2.F Traces
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/traces                      | All traces across all runs, paginated + filterable        |
| GET    | /api/traces/{traceId}            | Full span tree for one trace                              |
| GET    | /api/traces/errors               | Only errored traces across all runs                       |
| GET    | /api/traces/search               | ?q=spanName|model|tag full-text search across spans       |

### 2.G Sessions / Threads
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/sessions                    | All sessions: sessionId, traceCount, duration, cost, userId |
| GET    | /api/sessions/{sessionId}        | All traces in a session, ordered by time                  |
| POST   | /api/sessions                    | Manually group traces into a session                      |

### 2.H Users
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/users                       | All unique userIds: traceCount, cost, sessions, lastSeen  |
| GET    | /api/users/{userId}              | All traces for this user + cost + session list            |
| GET    | /api/users/{userId}/trends       | Per-user cost and usage over time                         |

### 2.I Feedback
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/feedback                    | All feedback entries across all runs                      |
| POST   | /api/feedback                    | Save {runFile, caseName, spanId, type, score, comment}    |
| GET    | /api/feedback/summary            | Aggregate: thumbsUp%, thumbsDown%, avg numeric score      |

### 2.J Annotations
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/annotations                 | All annotations with filter ?run=&label=&queue=           |
| POST   | /api/annotations                 | Save {run, caseName, label, note, correctedOutput, scores}|
| GET    | /api/annotations/export/csv      | Download all annotations as CSV                           |
| GET    | /api/annotations/stats           | Total annotated, % per label, inter-rater agreement       |

### 2.K Annotation Queues
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/queues                      | All queue definitions                                     |
| POST   | /api/queues                      | Create queue {name, description, scoreConfigs[], assignees[]} |
| GET    | /api/queues/{id}                 | Queue detail + items + progress                           |
| POST   | /api/queues/{id}/items           | Add trace/case to queue                                   |
| GET    | /api/queues/{id}/next            | Next unannotated item for reviewer                        |
| POST   | /api/queues/{id}/items/{itemId}  | Submit annotation for item + advance to next              |
| DELETE | /api/queues/{id}                 | Delete queue                                              |

### 2.L Score Configs
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/score-configs               | All score config definitions                              |
| POST   | /api/score-configs               | Create {name, type: numeric|boolean|categorical, range, categories[]} |
| DELETE | /api/score-configs/{id}          | Delete score config                                       |

### 2.M Online Evaluators
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/evaluators                  | All online evaluator configs                              |
| POST   | /api/evaluators                  | Create {name, metric, filter, samplingRate, enabled}      |
| PUT    | /api/evaluators/{id}             | Enable/disable / update config                            |
| GET    | /api/evaluators/{id}/results     | Results of auto-evals run by this evaluator               |
| POST   | /api/evaluators/{id}/run-now     | Manually trigger eval on latest run                       |

### 2.N Automation Rules
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/automations                 | All automation rules                                      |
| POST   | /api/automations                 | Create {name, filter, samplingRate, action: addToQueue|addToDataset|webhook|alert} |
| PUT    | /api/automations/{id}            | Update rule                                               |
| DELETE | /api/automations/{id}            | Delete rule                                               |

### 2.O Webhooks
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/webhooks                    | All webhook endpoints                                     |
| POST   | /api/webhooks                    | Register {name, url, secret, events[]}                    |
| POST   | /api/webhooks/{id}/test          | Fire test payload to webhook URL                          |
| DELETE | /api/webhooks/{id}               | Remove webhook                                            |

### 2.P Datasets
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/datasets                    | Grouped unique test cases: input, expected, run history   |
| GET    | /api/datasets/{name}             | All appearances of this test case across runs with scores |
| GET    | /api/datasets/export             | Download as JSON or CSV                                   |

### 2.Q Prompts
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/prompts                     | All saved prompt versions                                 |
| POST   | /api/prompts                     | Save {alias, version, text, label: draft|staging|production} |
| PUT    | /api/prompts/{alias}/label       | Change label (promote to production without code deploy)  |
| DELETE | /api/prompts/{alias}/{version}   | Delete version                                            |

### 2.R Bug Detection (QA)
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/bugs/run/{filename}         | All bugs found in this run with classification + evidence |
| GET    | /api/bugs/summary                | Bug type counts across all runs                           |
| GET    | /api/bugs/patterns               | Recurring bugs: same test case failing across N runs      |
| GET    | /api/bugs/regressions            | Test cases that passed before but now fail                |
| POST   | /api/bugs/analyze/{filename}     | Force re-analyze a run for bugs                           |

### 2.S Compare
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/compare                     | ?runs=a,b,c — per-metric avg, passRate, cost, duration    |
| GET    | /api/compare/cases               | ?runs=a,b&case=X — same case score across selected runs   |

### 2.T Settings
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/settings                    | Current config: folder, port, env, version, run count     |
| POST   | /api/settings                    | Update folder path, alert threshold, auto-refresh         |

### 2.U Usage / Platform Stats (Langfuse F10)
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/usage/daily                 | Traces/day, spans/day, tokens/day, cost/day (last 30 days)|
| GET    | /api/usage/summary               | Total traces, total spans, total tokens, total cost ever  |
| GET    | /api/usage/by-env                | Usage split by environment (prod/staging/dev)             |
| GET    | /api/usage/by-version            | Usage split by app version tag                            |

### 2.V Metrics Export API (Langfuse F14 — external consumption)
| Method | Endpoint                         | Returns                                                   |
|--------|----------------------------------|-----------------------------------------------------------|
| GET    | /api/v1/metrics-export           | Aggregated metrics JSON for Grafana/billing/rate-limiters |
|        |                                  | ?from=&to=&env=&version=&metric= filters                  |

### 2.W Missing CRUD endpoints (gaps from original list)
| Method | Endpoint                              | Returns                                          |
|--------|---------------------------------------|--------------------------------------------------|
| PUT    | /api/score-configs/{id}               | Update existing score config                     |
| PUT    | /api/annotations/{id}                 | Update existing annotation                       |
| PUT    | /api/webhooks/{id}                    | Update webhook URL/events/secret                 |
| GET    | /api/prompts/{alias}                  | Get all versions for one prompt alias            |
| POST   | /api/datasets/import                  | Upload golden dataset JSON file                  |
| GET    | /api/runs/{filename}/export           | Download this run's full JSON                    |
| GET    | /api/health                           | { status, runCount, cacheAge, port, version }    |

---

## PHASE 3 — FRONTEND PAGES (dashboard.html)

### Page 1 — DASHBOARD
```
Components:
[ ] Environment selector in topbar (All | production | staging | development)
[ ] Version selector in topbar (All | v1.0 | v1.1 | ...)
[ ] Auto-refresh toggle (30s polling)

[ ] Row 1: 6 stat cards
    - Total Runs
    - Overall Pass Rate (colored: green≥80 / amber≥60 / red<60)
    - Total Eval Cost ($)
    - Avg Duration (s)
    - Error Rate (%)
    - Total Tokens

[ ] Prebuilt Sections (each is a collapsible SCard):
    1. Traces — trace count per run (bar chart) + error rate line
    2. LLM Calls — LLM span count per run, avg latency
    3. Cost & Tokens — stacked bar: input/output/cached tokens per run
    4. Tools — top 5 tools by call count + avg duration
    5. Run Types — pie chart of span types (agent/llm/retriever/tool)
    6. Feedback Scores — thumbs up% / avg numeric score per run

[ ] Pass rate sparkline (last 10 runs — line chart)
[ ] Alert banner: if passRate < threshold → red warning bar at top
[ ] Recent Runs table (last 5 rows, click → Run Detail)
```

### Page 2 — TEST RUNS
```
[ ] Filter bar: date range | env | version | pass/fail | metric filter | search
[ ] Runs table columns:
    Timestamp | Env | Version | Passed | Failed | Pass Rate | Cost | Duration | Error Rate | Actions
[ ] Pass rate colored pill
[ ] Error rate badge (red if > 5%)
[ ] Pagination (25 per page)
[ ] Bulk select + delete
[ ] Click row → Run Detail
[ ] Export filtered runs as CSV
```

### Page 3 — RUN DETAIL
```
[ ] Breadcrumb: Dashboard → Test Runs → {run filename}
[ ] Run header: 6 stat cards (passed/failed/passRate/cost/duration/errorRate)
[ ] Hyperparameters panel (collapsible, shows identifier/datasetAlias/custom params)
[ ] Metrics Breakdown bar chart (avg score per metric, color by pass%)
[ ] Test Cases table:
    Name | Tags | Status | per-metric score pills | Latency | Cost | Trace? | Bug? | Actions
[ ] Filter: status (pass/fail/all) | metric | has-trace | has-bug | search
[ ] Bug Report panel (if bugs found: list of detected bugs in this run)
[ ] Click row → Test Case Detail
```

### Page 4 — TEST CASE DETAIL
```
NOTE: DeepEval has TWO test case types. This page handles BOTH:
  - LLMApiTestCase  → standard single-turn (input → output)
  - ConversationalApiTestCase → multi-turn conversation (turns list)

[ ] Breadcrumb: Dashboard → Test Runs → {run} → {case name}
[ ] Pass/Fail banner (green/red full-width)
[ ] Test Case Type badge: "LLM Test Case" or "Conversational Test Case"

--- FOR LLMApiTestCase ---
[ ] 3-column I/O panel:
    [Input] | [Actual Output] | [Expected Output]
    - Diff highlight if expected differs from actual
[ ] Retrieval Context panel:
    - Numbered chunk list (chunk index + char count per chunk)
    - Each chunk text (collapsible if > 300 chars)
    - Total chunks count + total chars
[ ] Tools Called panel:
    - Tool name | args | result | expected tools (side-by-side comparison)
[ ] Token cost + completion time (if present)

--- FOR ConversationalApiTestCase ---
[ ] Scenario + Expected Outcome + User Description panel
[ ] Multi-turn chat view (renders turns as a conversation):
    - USER turn: blue bubble on right
    - ASSISTANT turn: white bubble on left
    - Each turn shows: role | content | retrievalContext (if any) | toolsCalled
    - Turn index + order number
[ ] Per-turn retrieval context (collapsible per turn)

--- COMMON FOR BOTH ---
[ ] Metadata + Tags panel
[ ] Metrics section (each metric as SCard):
    - Metric name + PASS/FAIL pill
    - Score (big number) / Threshold
    - Reason (LLM judge explanation, full text)
    - Eval model used + eval cost
    - Verbose logs (collapsible)
    - LLM-as-Judge trace link (click → opens judge's own trace)
[ ] Trace Viewer (if trace exists — see Page 5)
[ ] Bug Report for this test case (if bugs detected — see Page 22)
[ ] Annotation panel:
    - Score Configs (each config → input/select/toggle by type)
    - Corrected Output textarea
    - Notes textarea
    - Save Annotation button
[ ] Feedback buttons: 👍 👎 + numeric score input
```

### Page 5 — TRACE VIEWER
```
[ ] Span tree left pane (40%):
    - Color-coded by type:
        AGENT     → purple  (#7c3aed)
        LLM       → blue    (#1558CB)
        RETRIEVER → teal    (#0d9488)
        TOOL      → amber   (#d97706)
        BASE      → grey    (#64748b)
    - Each row: type icon | span name | status badge | duration
    - Expand/collapse children
    - ERRORED spans → red background
    - Bug indicator icon next to spans with detected issues

[ ] Span Detail right pane (60%):
    - Header: type · name · status · duration · start/end time
    - For LLM spans: model | provider | input tokens | output tokens | cached tokens | cost
    - For RETRIEVER spans: embedder | top_k | chunk_size
    - For TOOL spans: description | args
    - For AGENT spans: available_tools list | agent_handoffs list
    - Metric badges: PASS/FAIL pills for all metrics on this span
    - Full metric reasons (expandable)
    - Input panel (raw LLM prompt or retrieval query)
    - Output panel (LLM response or retrieved chunks)
    - Retrieval Context (chunks with chunk index + char count)
    - Tools Called payload
    - Expected Output / Expected Tools (if present)
    - Metadata (key-value table)
    - Bug Report for this span (if detected)
    - Raw JSON (collapsible Collapsible)

[ ] Agent Graph View toggle (tree ↔ graph):
    - DAG visualization using SVG
    - Nodes = spans, edges = parent→child arrows
    - Color by type, size by duration
    - Click node → shows detail in right pane

[ ] Span search/filter bar (filter tree by span name)
[ ] Copy span JSON button
[ ] Copy trace JSON button
```

### Page 6 — SESSIONS / THREADS
```
[ ] Sessions table:
    Session ID | User | Trace Count | Duration | Cost | Last Active | Status
[ ] Click row → Session Detail:
    - Timeline of all traces in session (ordered by startTime)
    - Each trace: mini span summary, pass/fail badges
    - Session-level feedback stats
    - Full conversation view (input/output per trace in order)
[ ] Filter by userId | date | has-error
```

### Page 7 — USERS
```
[ ] Users table:
    User ID | Trace Count | Session Count | Total Cost | Total Tokens | Last Seen
[ ] Click → User Detail:
    - Cost/usage trend over time (line chart)
    - All sessions for this user
    - All traces for this user
    - Per-metric pass rate for this user
[ ] Filter by date range
[ ] Export as CSV
```

### Page 8 — METRICS & ANALYTICS
```
[ ] Metric multi-select (which metrics to show)
[ ] Group By selector: None | Tag | Metadata Key | Version | Environment
[ ] Date range picker

[ ] Chart 1: Pass Rate Over Time — line per metric
[ ] Chart 2: Avg Score Over Time — line per metric
[ ] Chart 3: Score Distribution — histogram per metric (0-0.2 ... 0.8-1.0)
[ ] Chart 4: Pass vs Fail stacked bar per run
[ ] Chart 5: Error Rate Over Time — line
[ ] Per-metric summary cards:
    All-time avg | Best score | Worst score | Total passes | Total fails | Trend arrow (↑↓→)
[ ] Regression alerts:
    List of metrics where score dropped vs previous run (with delta %)
```

### Page 9 — LATENCY
```
[ ] Chart 1: P50 / P95 / P99 latency over time (3 lines per chart)
[ ] Chart 2: Avg latency by span type (bar: agent/llm/retriever/tool/base)
[ ] Chart 3: Latency distribution histogram (buckets: <100ms, 100-500ms, 500ms-2s, >2s)
[ ] Slowest spans table:
    Span Name | Type | Run | Duration | Status
[ ] Filter by span type | date | threshold (show only spans > Xms)
```

### Page 10 — COST & TOKENS
```
[ ] Chart 1: Total cost per run (bar chart)
[ ] Chart 2: Cost by model (stacked bar: GPT-4 / Claude / Gemini / etc.)
[ ] Chart 3: Input vs Output vs Cached tokens per run (stacked bar)
[ ] Chart 4: Cost per user (bar chart, top 10 users)
[ ] Chart 5: Cost per tag (bar chart)
[ ] Summary: Most expensive model | Most expensive run | Most expensive user
[ ] Token budget alerts: flag runs where token count > 80% of known model limit
```

### Page 11 — COMPARE RUNS
```
[ ] Multi-select run picker (max 4 runs, checkbox list)
[ ] Side-by-side stat cards (one column per run)
[ ] Grouped bar chart: metric → score per selected run
[ ] Pass rate comparison bar (horizontal progress bars)
[ ] Cost comparison table
[ ] Latency comparison table
[ ] Test case diff section:
    - Select a test case name
    - Show score for that case in each selected run
    - Delta highlighted (green if improved, red if regressed)
[ ] Version comparison: automatically group runs with same version tag
```

### Page 12 — ANNOTATION QUEUES
```
[ ] Queues list: name | item count | reviewed count | progress % | assignees | actions
[ ] Create queue modal:
    - Queue name + description
    - Score Configs multi-select
    - Assign users
    - Filter to populate (env/run/metric)
[ ] Queue Detail:
    - Progress bar (X of Y reviewed)
    - Item list (pending / reviewed / skipped)
    - Add items (from run or filter)
[ ] Reviewer Mode (opens on "Start Reviewing"):
    - Full-screen sequential review
    - Shows: test case input/output + span detail
    - Score inputs per config
    - Corrected Output textarea
    - Notes textarea
    - [Complete + Next] | [Skip] | [Back] buttons
    - Progress indicator (3 of 20)
```

### Page 13 — ANNOTATIONS
```
[ ] Filter: run | queue | label | score range | annotated/unannotated | date
[ ] Table: Test Case | Run | Queue | Label | Scores | Corrected Output | Note | Reviewer | Date
[ ] Inline edit label + note
[ ] Stats bar: total annotated | % correct | % incorrect | % needs_review
[ ] Inter-annotator agreement score (if multiple reviewers annotated same item)
[ ] Export as CSV / JSON button
```

### Page 14 — ONLINE EVALUATORS
```
[ ] Evaluators list: name | metric | filter | sampling rate | enabled toggle | last run | results
[ ] Create evaluator:
    - Name
    - Which deepeval metric to run
    - Filter (which runs/cases to evaluate)
    - Sampling rate (0-100%)
    - Run on: every new run | on schedule | manually
[ ] Evaluator Results table: run | case | metric score | passed | timestamp
[ ] Run Now button (manual trigger)
[ ] Enable/Disable toggle per evaluator
```

### Page 15 — AUTOMATION RULES
```
[ ] Rules list: name | filter | action | sampling rate | trigger count | enabled
[ ] Create rule:
    - Name
    - Filter: env | version | metric | pass/fail | error | tag
    - Sampling rate %
    - Action: Add to Annotation Queue | Add to Dataset | Fire Webhook | Send Alert
[ ] Rule history: last 20 trigger events with timestamp + matched item
[ ] Enable/Disable toggle
```

### Page 16 — WEBHOOKS
```
[ ] Webhook list: name | URL | events | last fired | status (ok/failed)
[ ] Create webhook:
    - Name
    - Target URL
    - Secret (for HMAC signature)
    - Events to subscribe: new_run | eval_failed | bug_detected | annotation_saved | rule_matched
[ ] Test button (fires test payload, shows response)
[ ] Recent deliveries log (timestamp | event | status | response code)
```

### Page 17 — DATASETS
```
[ ] Test case list grouped by name:
    - Input text (truncated)
    - Expected output
    - Appears in N runs
    - Avg score (sparkline across runs)
[ ] Click → Dataset Case Detail:
    - Score per run (table + line chart)
    - All annotations for this case
    - Add to annotation queue button
[ ] Search by input text
[ ] Export as JSON / CSV
[ ] Import golden dataset (upload JSON)
```

### Page 18 — PROMPT HUB
```
[ ] Saved prompts list: alias | current label | versions | last updated
[ ] Create/Edit prompt:
    - Alias name
    - Version string
    - Prompt text (large textarea)
    - Label: draft | staging | production
[ ] Version history table per prompt alias
[ ] Promote to production (changes label, no code needed)
[ ] Compare two versions side-by-side (diff view)
[ ] Link prompt to test runs that used it
```

### Page 19 — PLAYGROUND
```
[ ] Prompt editor (textarea with variable {{placeholder}} highlighting)
[ ] Dataset picker (select from saved datasets)
[ ] Run prompt against: single input OR entire dataset
[ ] Model selector (from configured providers)
[ ] Results table: input | output | metric scores (if evaluators selected)
[ ] Compare: run same prompt against 2 different models side-by-side
[ ] Save result to dataset
[ ] Save prompt to Prompt Hub
```

### Page 20 — CUSTOM DASHBOARDS
```
[ ] Dashboard builder:
    - Add chart widget button
    - Widget types: line chart | bar chart | pie chart | stat card | table
    - For each widget: metric | filter | groupBy | date range
    - Drag-and-drop reorder
    - Resize widgets (1/4 | 1/2 | full width)
[ ] Save dashboard layout (stored in localStorage)
[ ] Multiple dashboard tabs
[ ] Share dashboard (export layout JSON)
```

### Page 23 — USAGE DASHBOARD (Langfuse F10)
```
Tracks platform utilization — how much your eval infrastructure is being used.
Different from Cost page (which tracks $). This tracks volume + activity.

[ ] 4 stat cards:
    Total Traces (all time) | Traces Today | Total Spans | Total Tokens (all time)

[ ] Chart 1: Traces per Day — bar chart (last 30 days)
[ ] Chart 2: Spans per Day — stacked bar by type (agent/llm/retriever/tool/base)
[ ] Chart 3: Token Volume per Day — line chart (input + output combined)
[ ] Chart 4: Runs per Day — bar chart

[ ] By Environment breakdown:
    - Table: environment | runs | traces | tokens | cost
[ ] By Version breakdown:
    - Table: version | runs | traces | avg pass rate | cost

[ ] Activity heatmap (GitHub-style):
    - Grid: last 12 weeks × 7 days
    - Cell color = number of eval runs that day
    - Hover: shows exact count + date
```

### Page 21 — SETTINGS
```
[ ] History folder path (editable, shows run count + disk usage)
[ ] Pass rate alert threshold slider (default 70%)
[ ] Auto-refresh interval (10s / 30s / 60s / off)
[ ] Environment tags (add/remove: production / staging / development)
[ ] App version format (e.g., "v{major}.{minor}.{patch}")
[ ] Score Configs manager (create/edit/delete scoring dimensions)
[ ] Dashboard info: version, port, backend status, cache last refreshed
[ ] Clear cache button
[ ] Export all data as ZIP
```

---

## PHASE 4 — BUG IDENTIFICATION & QA SYSTEM (MOST IMPORTANT)

This is the core QA intelligence layer. Every test run is automatically analyzed
for 12 categories of pipeline bugs. Each bug has: type, severity, evidence, and fix suggestion.

---

### 4.1 BUG DETECTION ENGINE (bug_detector.py)

The engine reads a full TestRun JSON and produces a structured bug report.
It checks every test case and every span inside its trace.

```python
# Bug Report Output Structure:
{
  "run_file": "test_run_20260601.json",
  "total_bugs": 14,
  "critical": 3,
  "warning": 7,
  "info": 4,
  "bugs": [
    {
      "bug_id": "CHUNK-001",
      "type": "CHUNKING",
      "severity": "critical",     # critical | warning | info
      "test_case": "test_rag_1",
      "span_type": "retriever",
      "span_name": "vector_search",
      "title": "Chunk size too small — key information split across boundaries",
      "evidence": {
        "chunk_size": 128,
        "retrieved_chunks": 5,
        "avg_chunk_chars": 312,
        "context_recall_score": 0.31,
        "missing_info_in_chunks": true,
        "actual_output_missing_facts": ["fact_1", "fact_2"]
      },
      "why": "Context Recall is 0.31 (below threshold 0.5). Chunks are only 128 chars, likely splitting sentences mid-way. Key facts in expected_output are absent from retrieved chunks.",
      "fix": "Increase chunk_size to 512-1024. Add 10-20% overlap between chunks. Consider sentence-aware splitting."
    }
  ]
}
```

---

### 4.2 THE 12 BUG CATEGORIES

#### BUG TYPE 1: CHUNKING BUGS
```
Detection Logic:
- Check retriever spans: chunk_size field
- Check context_recall metric score < threshold
- Check if expected_output facts are absent from retrieval_context chunks
- Check avg chunk character count < 200 (too small) or > 4000 (too large)

Specific Bugs Detected:
CHUNK-001: Chunk size too small
  Evidence: chunk_size < 200 AND context_recall < 0.5
  Why: Small chunks split sentences/facts — key info falls between chunk boundaries
  Fix: Increase chunk_size to 512-1024, add sentence-aware splitter

CHUNK-002: Chunk size too large
  Evidence: chunk_size > 3000 AND answer_relevancy < 0.6
  Why: Large chunks include irrelevant text, diluting retrieval precision
  Fix: Reduce chunk_size to 512-1024

CHUNK-003: Missing chunk overlap
  Evidence: retriever span has no overlap config AND context_recall < 0.5
  Why: Without overlap, facts at chunk boundaries are lost
  Fix: Set overlap to 10-15% of chunk_size (e.g., 100 chars for 1000 char chunks)

CHUNK-004: Wrong splitter strategy
  Evidence: chunks end mid-sentence (detected by checking last char of each chunk)
  Why: Character-based splitter ignoring sentence boundaries
  Fix: Use sentence-aware or recursive character splitter
```

#### BUG TYPE 2: RETRIEVAL / EMBEDDING BUGS
```
Detection Logic:
- Check retriever span: top_k, embedder fields
- Check context_recall, context_precision metric scores
- Check if retrieved chunks are semantically unrelated to input

Specific Bugs Detected:
RETRIEVAL-001: Too few chunks retrieved (low top_k)
  Evidence: top_k <= 2 AND context_recall < 0.5
  Why: Not enough chunks to cover the answer — key facts never retrieved
  Fix: Increase top_k to 5-10

RETRIEVAL-002: Too many chunks retrieved (noisy context)
  Evidence: top_k >= 20 AND context_precision < 0.4
  Why: Too much irrelevant context confuses LLM, reduces precision
  Fix: Reduce top_k to 5-8, add reranking step

RETRIEVAL-003: Wrong/missing embedder
  Evidence: embedder field is null OR embedder mismatch between index and query
  Why: Embedding model mismatch means similarity scores are meaningless
  Fix: Ensure same embedding model used for indexing and retrieval

RETRIEVAL-004: Low retrieval relevance
  Evidence: context_precision < 0.3 (retrieved chunks unrelated to query)
  Why: Embedder not capturing domain-specific semantics
  Fix: Fine-tune embedding model or use domain-specific embedder

RETRIEVAL-005: Empty retrieval context
  Evidence: retrieval_context is [] or null
  Why: Vector DB returned no results — query may be out of distribution
  Fix: Check vector DB connectivity, add fallback retrieval
```

#### BUG TYPE 3: LLM GENERATION BUGS
```
Detection Logic:
- Check LLM spans: model, input_token_count, output_token_count, cost
- Check faithfulness, hallucination metric scores
- Compare LLM output vs retrieval_context content

Specific Bugs Detected:
LLM-001: Hallucination — model fabricating facts
  Evidence: faithfulness < 0.5
  Why: Model generating facts not present in retrieval context
  Fix: Add strict grounding instruction to system prompt, lower temperature

LLM-002: Context window overflow
  Evidence: input_token_count > 80% of model's known context limit
  Why: Prompt + context truncated — LLM missing key retrieved information
  Fix: Reduce chunk count, increase chunk compression, use larger context model

LLM-003: Model ignoring retrieval context
  Evidence: faithfulness < 0.4 AND context provided is relevant
  Why: Prompt not instructing model to use context, model using training data instead
  Fix: Add explicit instruction: "Answer ONLY based on the provided context"

LLM-004: Output too short / incomplete answer
  Evidence: output_token_count < 20 AND metric scores low
  Why: Model generating minimal response — max_tokens may be too low
  Fix: Increase max_tokens in model config

LLM-005: Wrong model used
  Evidence: LLM span model field ≠ expected model from hyperparameters
  Why: Fallback model triggered or wrong model configured
  Fix: Verify model configuration, add model assertion in test setup

LLM-006: High latency on LLM span
  Evidence: LLM span duration > P95 latency threshold
  Why: Model overloaded, or prompt too large causing slow TTFT
  Fix: Enable streaming, reduce prompt size, use faster model
```

#### BUG TYPE 4: PROMPT BUGS
```
Detection Logic:
- Check LLM span input (the actual prompt sent to model)
- Check answer_relevancy, instruction_following metric scores
- Detect missing key instructions in prompt

Specific Bugs Detected:
PROMPT-001: Low answer relevancy
  Evidence: answer_relevancy < 0.5
  Why: Prompt instructions too vague — model answering off-topic
  Fix: Add specific task description, format requirements to system prompt

PROMPT-002: Missing grounding instruction
  Evidence: faithfulness < 0.5 AND no "use only provided context" in LLM input
  Why: Prompt allows model to use parametric knowledge, enabling hallucination
  Fix: Add: "Only answer based on the following context. If unsure, say 'I don't know.'"

PROMPT-003: Missing output format instruction
  Evidence: expected_output has structure (JSON/list) but actual_output is plain text
  Why: Prompt not specifying output format
  Fix: Add format instruction: "Respond in JSON with keys: {key1, key2}"

PROMPT-004: System prompt too long
  Evidence: input_token_count > 60% of context and system prompt > 2000 tokens
  Why: Verbose system prompt leaving little room for context/question
  Fix: Compress system prompt, move static instructions to prefix caching
```

#### BUG TYPE 5: TOOL / FUNCTION CALL BUGS
```
Detection Logic:
- Check tool spans: status, input, output, description
- Check tool_correctness metric score
- Compare tools_called vs expected_tools

Specific Bugs Detected:
TOOL-001: Tool call failed (exception)
  Evidence: tool span status = ERRORED
  Why: Tool threw an exception — bad args, API failure, timeout
  Fix: Add error handling in tool, check tool input validation

TOOL-002: Wrong tool called
  Evidence: tools_called ≠ expected_tools
  Why: Agent routing to wrong tool for this input type
  Fix: Improve agent's tool selection prompt, add tool descriptions

TOOL-003: Tool called with wrong arguments
  Evidence: tool span input args don't match tool schema
  Why: LLM hallucinating tool arguments
  Fix: Add strict tool schema validation, use structured output

TOOL-004: Unnecessary tool call
  Evidence: tools_called is non-empty AND expected_tools is empty
  Why: Agent over-triggering tools for simple questions
  Fix: Add guard condition in agent: "only call tools when question requires external data"

TOOL-005: Missing tool call
  Evidence: expected_tools non-empty AND tools_called is empty
  Why: Agent not recognizing when to use tools
  Fix: Improve tool availability description, add few-shot examples of tool use
```

#### BUG TYPE 6: AGENT ROUTING BUGS
```
Detection Logic:
- Check agent spans: available_tools, agent_handoffs, children span count
- Check trace duration vs expected duration
- Detect circular handoffs

Specific Bugs Detected:
AGENT-001: Agent loop detected
  Evidence: same agent span name appears > 3 times in trace
  Why: Agents handing off to each other in a circle — no termination condition
  Fix: Add loop detection, max_iterations guard, explicit termination condition

AGENT-002: Wrong sub-agent selected
  Evidence: agent_handoffs ≠ expected handoff pattern (if known)
  Why: Orchestrator agent routing to wrong specialist
  Fix: Improve routing prompt, add explicit routing examples

AGENT-003: Agent not using available tools
  Evidence: available_tools non-empty AND no tool spans as children
  Why: Agent unaware of tools or prompt doesn't mention them
  Fix: Include tool descriptions in agent's system prompt

AGENT-004: Excessive sub-agent calls
  Evidence: agent handoff count > 5 in single trace
  Why: Over-decomposition of simple task — efficiency bug
  Fix: Consolidate agent responsibilities, use single agent for simple queries
```

#### BUG TYPE 7: REGRESSION BUGS
```
Detection Logic:
- Compare current run vs previous N runs for same test case
- Detect metric score drop > 0.1 between consecutive runs
- Detect previously passing test cases now failing

Specific Bugs Detected:
REGRESSION-001: Metric score dropped significantly
  Evidence: metric score dropped > 0.15 vs average of last 3 runs
  Why: Code/prompt/model change introduced regression
  Fix: Run git diff on prompt files, check model version change, revert last change

REGRESSION-002: Test case flipped from PASS to FAIL
  Evidence: test case passed in last 3 runs, now fails
  Why: Non-determinism OR actual regression from code change
  Fix: Re-run 3 times to check non-determinism; if consistently failing, investigate change

REGRESSION-003: New test cases all failing
  Evidence: test cases present in current run but not in previous runs, all failing
  Why: New test cases cover untested scenarios the model can't handle
  Fix: Review new test cases for validity, improve model coverage for these scenarios
```

#### BUG TYPE 8: LATENCY / PERFORMANCE BUGS
```
Detection Logic:
- Check span durations against P95 baseline
- Check total trace duration
- Identify slowest spans

Specific Bugs Detected:
LATENCY-001: Span duration exceeds P95 threshold
  Evidence: span duration > 2x P95 of same span type
  Why: External API slow, DB slow, or model overloaded
  Fix: Add timeout, caching, or fallback for slow spans

LATENCY-002: Total trace too slow
  Evidence: total trace duration > configured SLA threshold
  Why: Sequential span execution instead of parallel where possible
  Fix: Parallelize independent retriever/tool calls

LATENCY-003: Slow retrieval
  Evidence: retriever span > 3s
  Why: Vector DB cold start, missing index, large dataset
  Fix: Add warm-up, optimize vector DB indexing, add retrieval cache
```

#### BUG TYPE 9: COST ANOMALY BUGS
```
Detection Logic:
- Compare eval cost vs historical average
- Detect unexpectedly expensive LLM calls
- Detect token waste

Specific Bugs Detected:
COST-001: Run cost spike
  Evidence: total cost > 2x average of last 5 runs
  Why: More test cases, larger prompts, or accidental expensive model used
  Fix: Review run size, check model used, add cost budget per run

COST-002: Single LLM call too expensive
  Evidence: single LLM span cost > $0.10
  Why: Prompt too large, or very high-cost model used unnecessarily
  Fix: Use cheaper model for this task, reduce prompt size

COST-003: Token waste — input >> output ratio
  Evidence: input_tokens > 5x output_tokens for simple Q&A task
  Why: System prompt or context far too large for the answer needed
  Fix: Compress system prompt, use RAG to reduce context, enable caching
```

#### BUG TYPE 10: METRIC CONSISTENCY BUGS
```
Detection Logic:
- Check metric scores that contradict each other logically
- Detect impossible score combinations

Specific Bugs Detected:
CONSISTENCY-001: Faithfulness high but Context Recall low (impossible combo)
  Evidence: faithfulness > 0.8 AND context_recall < 0.3
  Why: Evaluator misconfiguration or test case setup error
  Fix: Verify metric configurations, check test case has expected retrieval context

CONSISTENCY-002: Answer Relevancy high but Faithfulness low
  Evidence: answer_relevancy > 0.8 AND faithfulness < 0.3
  Why: Model giving relevant but hallucinated answer — dangerous for production
  Fix: Prioritize faithfulness fix, add grounding instructions

CONSISTENCY-003: All metrics errored
  Evidence: all metricsData have error field set
  Why: Evaluator LLM API failed, or metric config broken
  Fix: Check evaluator API key, verify metric imports, check network
```

#### BUG TYPE 11: DATA QUALITY BUGS
```
Detection Logic:
- Check test case inputs for common issues
- Check expected_output validity

Specific Bugs Detected:
DATA-001: Empty input
  Evidence: input is empty string or null
  Why: Test data generation bug — empty inputs produce meaningless results
  Fix: Add input validation in test setup, filter empty test cases

DATA-002: Missing expected output for hallucination metrics
  Evidence: faithfulness/hallucination metric requires expected_output but it's null
  Why: Test case not configured with expected output
  Fix: Add expected_output to all test cases used with faithfulness metrics

DATA-003: Duplicate test cases
  Evidence: same input appears > 3 times in same run
  Why: Test data deduplication missing
  Fix: Deduplicate test dataset, add unique constraint

DATA-004: Test case name collision
  Evidence: multiple test cases with same name in one run
  Why: Auto-naming conflict
  Fix: Add unique suffix to auto-generated test case names
```

#### BUG TYPE 12: CONFIGURATION BUGS
```
Detection Logic:
- Check metric thresholds against industry norms
- Check hyperparameters for known bad values

Specific Bugs Detected:
CONFIG-001: Metric threshold too lenient
  Evidence: threshold < 0.3 for quality metrics (faithfulness/relevancy)
  Why: Test will pass even with very poor quality — meaningless gate
  Fix: Set thresholds: faithfulness ≥ 0.7, answer_relevancy ≥ 0.7, context_recall ≥ 0.5

CONFIG-002: Metric threshold too strict
  Evidence: threshold > 0.99 for any metric
  Why: Test will never pass — no LLM achieves near-perfect scores
  Fix: Use practical thresholds based on baseline measurements

CONFIG-003: No metrics configured
  Evidence: test case has empty metricsData
  Why: Metrics not attached to test case in test setup
  Fix: Attach at least faithfulness + answer_relevancy to every test case

CONFIG-004: Eval model same as tested model
  Evidence: evaluationModel == model being tested (from hyperparameters)
  Why: Model evaluating itself — severe conflict of interest, unreliable scores
  Fix: Use a different, stronger model as evaluator (e.g., evaluate GPT-4 with Claude)
```

---

### 4.3 BUG DASHBOARD PAGE (Page 22)

```
[ ] Bug Summary stat cards:
    Total Bugs | Critical (red) | Warnings (amber) | Info (blue)

[ ] Bug Type Breakdown bar chart:
    CHUNKING | RETRIEVAL | LLM | PROMPT | TOOL | AGENT | REGRESSION |
    LATENCY | COST | CONSISTENCY | DATA | CONFIG

[ ] Active Bugs table (all open bugs across all runs):
    Bug ID | Type | Severity | Test Case | Run | Title | Fix Available? | Actions

[ ] Bug Detail panel (click row):
    - Full bug description
    - Evidence (all fields with actual values)
    - WHY explanation (human-readable)
    - FIX suggestion (actionable steps)
    - Related spans (click to open Trace Viewer at that span)
    - Mark as Resolved button
    - Add to Annotation Queue button

[ ] Recurring Patterns section:
    - "This bug appeared in 5 of last 7 runs" warning
    - Pattern: CHUNK-001 always triggered when chunk_size < 200

[ ] Regression Alerts section:
    - Test cases that were passing and now fail (with run comparison)
    - Score delta visualization (before → after arrows)

[ ] Root Cause Heatmap:
    - X-axis: span types (retriever/llm/tool/agent)
    - Y-axis: bug categories
    - Cell color = bug frequency
    - Click cell → filtered bug list

[ ] Fix Suggestions Report:
    - Downloadable PDF/JSON of all bugs + fixes
    - Prioritized by severity + frequency

[ ] Resolved Bugs history:
    - Bugs marked resolved with timestamp + resolver
    - Verify fix: compare score before/after resolution run
```

---

### 4.3.1 HOW TO READ THE BUG DASHBOARD — QA GUIDE

When a QA engineer opens the Bug Dashboard after a run, here is the exact workflow:

```
STEP 1: Look at the Root Cause Heatmap first
  - High color in RETRIEVER row + CHUNKING column → chunk size problem
  - High color in LLM row + HALLUCINATION column → faithfulness problem
  - High color in TOOL row + ERRORED column → tool exception problem
  - High color across all columns in REGRESSION row → something changed in code

STEP 2: Filter Active Bugs by CRITICAL severity only
  - Critical = test case is completely broken, not a partial failure
  - Fix ALL critical bugs before investigating warnings

STEP 3: For each Critical bug, click → Bug Detail panel
  - Read the EVIDENCE section first (actual values, not guesses)
  - Read the WHY section (explains root cause in plain English)
  - Read the FIX section (exact steps to resolve)
  - Click "Related spans" → opens Trace Viewer at the exact failing span

STEP 4: In Trace Viewer, verify the bug
  For CHUNK bugs:     Check retriever span → chunk_size field + retrieval_context
  For RETRIEVAL bugs: Check retriever span → top_k + embedder + output chunks
  For LLM bugs:       Check LLM span → input_token_count + faithfulness score + output
  For PROMPT bugs:    Check LLM span → input field (read the actual prompt text)
  For TOOL bugs:      Check tool span → status (ERRORED) + input args + error message
  For AGENT bugs:     Check agent span → agent_handoffs + count of same-name spans
  For REGRESSION:     Open Compare Runs → same test case → score before vs after

STEP 5: Mark bug as Resolved after fix deployed
  - Re-run deepeval → new test_run_*.json auto-appears in dashboard
  - Bug Dashboard shows "Verify fix" → compare score before/after resolution run
  - If bug still present → severity escalates to CRITICAL from WARNING

STEP 6: Export Bug Report for PR review
  - Download as Markdown → paste into GitHub PR description
  - Or download as JSON → CI pipeline reads it for deployment gate
```

### 4.4 QA WORKFLOW INTEGRATION

```
[ ] Auto-analyze every new run on arrival (background worker)
[ ] Bug severity gates:
    - CRITICAL bugs → show red banner on Dashboard
    - Any regression → trigger webhook if configured
    - Bug count > threshold → block CI badge (set via Settings)

[ ] CI/CD Integration:
    GET /api/bugs/run/{filename}/gate
    Returns: { pass: bool, critical_count: int, summary: "..." }
    CI pipeline can call this to gate deployments

[ ] Bug → Annotation Queue automation:
    When a bug is detected, automatically add affected test case to
    "Bug Review" annotation queue for human verification

[ ] Bug Report export:
    - JSON (machine-readable for CI)
    - Markdown (for GitHub PR comments)
    - CSV (for spreadsheet tracking)
```

---

## PHASE 5 — SHARED COMPONENTS (copy from preview.html + new)

| # | Component       | Source          | Notes                                        |
|---|-----------------|-----------------|----------------------------------------------|
| 5.1  | C design tokens   | Copy preview.html | Same Kforce blue (#1558CB)               |
| 5.2  | All base CSS      | Copy preview.html | stat-card, scard, filter-bar, nav-item…  |
| 5.3  | Btn               | Copy preview.html | primary/outline/ghost/success/warn       |
| 5.4  | SCard + SHead     | Copy preview.html | Standard section card                    |
| 5.5  | StatCard          | Copy preview.html | With gradient accent + icon              |
| 5.6  | Avatar            | Copy preview.html | Initials + gradient                      |
| 5.7  | Label + Input     | Copy preview.html | Form elements                            |
| 5.8  | Sidebar           | Adapt preview.html | New nav groups/icons for eval pages     |
| 5.9  | Topbar            | Adapt preview.html | + env selector + version selector       |
| 5.10 | Spotlight         | Adapt preview.html | Search runs + test cases + bugs         |
| 5.11 | MetricPill        | NEW             | PASS (green) / FAIL (red) + score number     |
| 5.12 | ScoreBar          | NEW             | Colored progress bar 0→1                     |
| 5.13 | SpanTree          | NEW             | Recursive React tree for trace viewer        |
| 5.14 | AgentGraph        | NEW             | SVG DAG graph for agent spans                |
| 5.15 | BugCard           | NEW             | Bug type icon + severity + evidence + fix    |
| 5.16 | SeverityBadge     | NEW             | CRITICAL(red)/WARNING(amber)/INFO(blue)      |
| 5.17 | DiffViewer        | NEW             | Side-by-side input/output diff               |
| 5.18 | ChunkViewer       | NEW             | Numbered chunk list with char counts         |
| 5.19 | Toast             | NEW             | Success/error notification popup             |
| 5.20 | ConfirmModal      | NEW             | "Are you sure?" before delete                |
| 5.21 | Pagination        | NEW             | Page buttons with prev/next                  |
| 5.22 | DateRangePicker   | NEW             | Start/end date inputs                        |
| 5.23 | MultiSelect       | NEW             | Checkbox dropdown for run/metric picker      |
| 5.24 | ProgressBar       | NEW             | Horizontal progress (queue completion etc.)  |
| 5.25 | LineChart         | Chart.js CDN    | Time series data                             |
| 5.26 | BarChart          | Chart.js CDN    | Categorical comparison                       |
| 5.27 | HistogramChart    | Chart.js CDN    | Score distribution buckets                   |
| 5.28 | PieChart          | Chart.js CDN    | Span type breakdown                          |
| 5.29 | StackedBarChart   | Chart.js CDN    | Token type / cost breakdown                  |
| 5.30 | SparklineChart    | Chart.js CDN    | Mini line chart in dashboard                 |

---

## PHASE 6 — INFRASTRUCTURE & POLISH

| # | Task                                                                              |
|---|-----------------------------------------------------------------------------------|
| 6.1  | Loading skeleton (grey pulse animation while API fetches)                       |
| 6.2  | Empty state screens (no runs / no traces / no bugs / no annotations)            |
| 6.3  | Error boundary: malformed JSON files skipped with warning toast                 |
| 6.4  | Auto-refresh: poll /api/runs every 30s, show "New run detected" banner          |
| 6.5  | Environment auto-detection: read env from run hyperparameters if present        |
| 6.6  | Version auto-detection: read version from run identifier/hyperparameters        |
| 6.7  | CORS config for dev (allow all origins)                                         |
| 6.8  | Global topbar env + version filter (persists across all pages via React state)  |
| 6.9  | Keyboard shortcuts: Ctrl+K spotlight, Esc close modal, ←/→ navigate runs       |
| 6.10 | one-command startup: python run.py → starts FastAPI on port 5000                |
| 6.11 | /api/health endpoint → { status: ok, runCount, cacheAge }                      |
| 6.12 | Bug detector runs automatically on every new run file detected                  |
| 6.13 | All charts responsive (resize on window resize)                                 |
| 6.14 | Dark/light mode toggle (CSS variable swap)                                      |
| 6.15 | Print/export page as PDF (window.print() + print CSS)                           |

---

## CDN DEPENDENCIES (NO NPM)

```html
<!-- Core (already in preview.html) -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.2/babel.min.js"></script>

<!-- Charts -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

<!-- No other dependencies needed -->
```

---

## BUILD ORDER (RECOMMENDED SEQUENCE)

```
WEEK 1 — BACKEND FOUNDATION
  Day 1-2: Phase 1 (project structure, main.py, run_loader, aggregator)
  Day 3-4: Phase 2.A-2.D (dashboard, runs, metrics, latency endpoints)
  Day 5:   Phase 2.E-2.F (cost, tokens, traces endpoints)
  Test: All endpoints working via FastAPI /docs

WEEK 2 — BACKEND COMPLETE + FRONTEND SHELL
  Day 1-2: Phase 2.G-2.T (sessions, users, feedback, annotations, queues, evaluators, automations, webhooks, datasets, prompts, bugs, compare, settings)
  Day 3:   bug_detector.py (all 12 bug categories)
  Day 4-5: dashboard.html shell (CSS from preview.html, Sidebar, Topbar, routing)

WEEK 3 — CORE PAGES
  Day 1:   Page 1 (Dashboard)
  Day 2:   Page 2 (Test Runs)
  Day 3:   Page 3 (Run Detail)
  Day 4:   Page 4 (Test Case Detail)
  Day 5:   Page 5 (Trace Viewer)

WEEK 4 — ANALYTICS + OBSERVABILITY
  Day 1:   Page 6 (Sessions)
  Day 2:   Page 7 (Users)
  Day 3:   Page 8 (Metrics & Analytics)
  Day 4:   Page 9 (Latency)
  Day 5:   Page 10 (Cost & Tokens)

WEEK 5 — EVALUATION SYSTEM
  Day 1:   Page 11 (Compare Runs)
  Day 2:   Page 12 (Annotation Queues)
  Day 3:   Page 13 (Annotations)
  Day 4:   Page 14 (Online Evaluators)
  Day 5:   Page 15 (Automation Rules)

WEEK 6 — BUG SYSTEM + DATA
  Day 1:   Page 22 (Bug Dashboard)
  Day 2:   Page 16 (Webhooks) + Page 17 (Datasets)
  Day 3:   Page 18 (Prompt Hub) + Page 19 (Playground)
  Day 4:   Page 20 (Custom Dashboards) + Page 21 (Settings)
  Day 5:   Phase 6 (Polish, loading states, empty states, auto-refresh)

WEEK 7 — INTEGRATION TESTING
  Day 1-2: Test all 12 bug categories with real DeepEval runs
  Day 3:   Test annotation queue workflow end-to-end
  Day 4:   Test online evaluator + automation + webhook chain
  Day 5:   Performance testing, UX review, final polish
```

---

## HOW TO GENERATE TEST DATA (DeepEval side)

This dashboard reads JSON files that DeepEval writes. Here is how to produce them:

### Option A — pytest-style (deepeval test run)
```python
# tests/test_my_llm.py
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric, ContextualRecallMetric

def test_rag_answer():
    test_case = LLMTestCase(
        input="What is the capital of France?",
        actual_output=my_llm("What is the capital of France?"),
        expected_output="Paris",
        retrieval_context=["France is a country in Europe. Its capital is Paris."],
    )
    assert_test(test_case, [
        FaithfulnessMetric(threshold=0.7),
        AnswerRelevancyMetric(threshold=0.7),
        ContextualRecallMetric(threshold=0.5),
    ])
```
```bash
# Windows
set DEEPEVAL_RESULTS_FOLDER=./eval_history
deepeval test run tests/

# Linux/Mac
DEEPEVAL_RESULTS_FOLDER=./eval_history deepeval test run tests/
```

### Option B — evaluate() API (no pytest)
```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
import os

os.environ["DEEPEVAL_RESULTS_FOLDER"] = "./eval_history"

test_cases = [
    LLMTestCase(input="...", actual_output="...", retrieval_context=["..."]),
    LLMTestCase(input="...", actual_output="...", retrieval_context=["..."]),
]
evaluate(test_cases, [FaithfulnessMetric(threshold=0.7), AnswerRelevancyMetric(threshold=0.7)])
# → Writes test_run_<timestamp>.json to ./eval_history automatically
```

### Option C — With Tracing (enables Trace Viewer in dashboard)
```python
from deepeval.tracing import observe, update_current_span_test_case

@observe(type="llm", model="gpt-4o")
def call_llm(prompt: str) -> str:
    response = openai_client.chat.completions.create(...)
    return response.choices[0].message.content

@observe(type="retriever", embedder="text-embedding-3-small", top_k=5, chunk_size=512)
def retrieve_chunks(query: str) -> list:
    return vector_db.search(query, top_k=5)

@observe(type="agent")
def my_rag_agent(question: str) -> str:
    chunks = retrieve_chunks(question)
    answer = call_llm(build_prompt(question, chunks))
    update_current_span_test_case(
        input=question,
        actual_output=answer,
        retrieval_context=chunks,
    )
    return answer
```

### Option D — Conversational Test Cases
```python
from deepeval.test_case import ConversationalTestCase, Turn

conv_case = ConversationalTestCase(
    turns=[
        Turn(role="user", content="Hello, who are you?"),
        Turn(role="assistant", content="I am an AI assistant."),
        Turn(role="user", content="What can you help me with?"),
        Turn(role="assistant", content="I can help with questions and tasks."),
    ]
)
evaluate([conv_case], [ConversationalGEvalMetric(...)])
```

### Tagging runs with Environment & Version (for dashboard filters)
```python
# In your test setup or conftest.py
import deepeval

deepeval.log_hyperparameters(
    model="gpt-4o",
    environment="production",    # ← picked up by env_detector.py
    version="v1.2.3",           # ← picked up for version filter
    chunk_size=512,
    top_k=5,
    temperature=0.0,
)
```

---

## HOW TO RUN THE DASHBOARD

```bash
# 1. Clone / create local-dashboard folder
cd local-dashboard

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Set environment variables (.env or shell)
# Windows:
set DEEPEVAL_RESULTS_FOLDER=C:\path\to\eval_history
set DASHBOARD_PORT=5000
# Linux/Mac:
export DEEPEVAL_RESULTS_FOLDER=./eval_history
export DASHBOARD_PORT=5000

# 4. Start the dashboard
python run.py
# → FastAPI starts on http://localhost:5000
# → Open browser → http://localhost:5000
# → API docs → http://localhost:5000/docs

# 5. Run your DeepEval tests in another terminal
DEEPEVAL_RESULTS_FOLDER=./eval_history deepeval test run tests/
# → Dashboard auto-detects new run within 30s
# → Bug detector runs automatically
# → "New run detected" banner appears in dashboard
```

---

## ONLINE EVAL WORKER — HOW IT WORKS (online_eval_worker.py)

```
APScheduler runs every 30 seconds:

1. Compare current eval_history/ file list vs cached file list
2. If new test_run_*.json found:
   a. Load and parse the new run
   b. Run bug_detector.py on it (all 12 categories)
   c. Save bug report to bug_reports.json
   d. For each ENABLED online evaluator config:
      - Apply filter (env/version/metric/tag)
      - Apply sampling rate (random.random() < samplingRate)
      - Run the configured deepeval metric on matching test cases
      - Save results to evaluators/{id}/results.json
   e. For each ENABLED automation rule:
      - Apply filter against new run
      - If matched: execute action (addToQueue / addToDataset / webhook / alert)
   f. For each ENABLED webhook subscribed to "new_run" event:
      - POST payload to webhook URL with HMAC-SHA256 signature
   g. Update in-memory cache
3. Frontend detects new run via /api/runs polling (30s auto-refresh)
4. "New run detected" banner appears — click to navigate to Run Detail
```

---

## SIDEBAR FINAL NAV STRUCTURE (dashboard.html)

```
Logo: DeepEval Dashboard
      AI Evaluation Platform

├── MAIN
│    └── Dashboard              (Page 1)
│
├── EVALUATIONS
│    ├── Test Runs              (Page 2)
│    ├── Run Detail             (Page 3 — hidden, opens on click)
│    └── Test Case Detail       (Page 4 — hidden, opens on click)
│
├── OBSERVABILITY
│    ├── Trace Viewer           (Page 5)
│    ├── Sessions / Threads     (Page 6)
│    └── Users                  (Page 7)
│
├── ANALYSIS
│    ├── Metrics & Analytics    (Page 8)
│    ├── Latency                (Page 9)
│    ├── Cost & Tokens          (Page 10)
│    ├── Usage                  (Page 23) ← NEW
│    └── Compare Runs           (Page 11)
│
├── EVALUATION
│    ├── Annotation Queues      (Page 12)
│    ├── Annotations            (Page 13)
│    └── Online Evaluators      (Page 14)
│
├── AUTOMATION
│    ├── Rules                  (Page 15)
│    └── Webhooks               (Page 16)
│
├── DATA
│    ├── Datasets               (Page 17)
│    └── Prompt Hub             (Page 18)
│
├── TOOLS
│    ├── Playground             (Page 19)
│    ├── Custom Dashboards      (Page 20)
│    └── Bug Dashboard          (Page 22)
│
└── SYSTEM
     └── Settings               (Page 21)

Total: 23 pages (22 visible + 1 hidden detail page)
```

---

## FEATURE COVERAGE SUMMARY

| Platform        | Coverage After Build                              |
|-----------------|---------------------------------------------------|
| Confident AI    | 100% — all features (runs, traces, metrics, datasets, prompts, annotations) |
| LangSmith       | 95% — all except Insights AI Agent (automated PR writer) |
| Langfuse        | 100% — all features including Usage Dashboard + Metrics API |
| QA Bug System   | 100% — 12 categories, 35 bugs, root cause heatmap, CI gate API |

Total pages: 23
Total API endpoints: 70+
Total bug categories: 12
Total specific bug patterns: 35
Shared components: 30 (Phase 5)
Single HTML file: ~10,000-12,000 lines (same pattern as preview.html)
Backend services: 8 (run_loader, aggregator, bug_detector, session_builder,
                     user_tracker, env_detector, online_eval_worker, webhook_sender)

---

## COMPLETE CONVERSATION COVERAGE CHECKLIST

Everything discussed from start of conversation to end:

### Original Questions Answered:
- [x] Can we create an exact copy of Confident AI locally? → YES via this dashboard
- [x] What is the difference between deepeval inspect TUI and Confident AI? → Documented
- [x] How to overcome all the "NO" features of deepeval inspect? → All 12 NOs → YES
- [x] Can we build it like KCRecruit (single HTML + FastAPI)? → YES, same pattern
- [x] Port 5000 → Confirmed throughout
- [x] KCRecruit preview.html CSS reuse → All CSS tokens + components documented

### Platform Features Covered:
- [x] All Confident AI features (test runs, traces, metrics, datasets, prompts, annotations)
- [x] LangSmith: Sessions, Threads, Feedback, Online Evaluators, Automations, Webhooks,
        Playground, Prompt Hub, Custom Dashboards, Group-by charts, Error Rate, Latency P50/P95/P99
- [x] Langfuse: Users page, Environments, Versions, Annotation Queues, Score Configs,
        Corrected Outputs, Agent Graph, Latency Dashboard, Cost Dashboard, Usage Dashboard,
        Token type breakdown (input/output/cached), Prompt labels, LLM-as-Judge traces,
        Metrics API (external export)

### Bug Identification (QA):
- [x] CHUNKING bugs (4 specific bugs)
- [x] RETRIEVAL / EMBEDDING bugs (5 specific bugs)
- [x] LLM GENERATION bugs (6 specific bugs)
- [x] PROMPT bugs (4 specific bugs)
- [x] TOOL / FUNCTION CALL bugs (5 specific bugs)
- [x] AGENT ROUTING bugs (4 specific bugs)
- [x] REGRESSION bugs (3 specific bugs)
- [x] LATENCY / PERFORMANCE bugs (3 specific bugs)
- [x] COST ANOMALY bugs (3 specific bugs)
- [x] METRIC CONSISTENCY bugs (3 specific bugs)
- [x] DATA QUALITY bugs (4 specific bugs)
- [x] CONFIGURATION bugs (4 specific bugs)
- [x] QA workflow guide (how to read heatmap → find bug → fix it)
- [x] CI/CD gate endpoint (/api/bugs/run/{filename}/gate)
- [x] Bug report export (JSON / Markdown / CSV)

### Data Handling:
- [x] LLMApiTestCase (standard test cases) — fully handled
- [x] ConversationalApiTestCase (multi-turn) — chat bubble display
- [x] TraceApi with all span types (base/agent/llm/retriever/tool) — trace viewer
- [x] BaseApiSpan all fields (tokens, cost, embedder, top_k, chunk_size, etc.)
- [x] MetricData all fields (score, threshold, reason, evaluationModel, verboseLogs)

### Infrastructure:
- [x] DEEPEVAL_RESULTS_FOLDER env var for run history
- [x] auto-detect environment from hyperparameters
- [x] auto-detect version from hyperparameters/identifier
- [x] APScheduler background worker (30s polling)
- [x] auto-refresh frontend (30s polling)
- [x] "New run detected" banner
- [x] Single-command startup (python run.py)
- [x] How to generate test data (4 options: pytest, evaluate(), tracing, conversational)
- [x] How to tag runs with environment + version
