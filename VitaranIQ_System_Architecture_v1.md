# VitaranIQ — System Architecture

**Team:** Innovate-x · **Project:** VitaranIQ · **Document:** System Architecture · **Version:** 1.0 · **Date:** 2026-10-24
**Derived from:** PRD v2.0 and SRS v1.0. SRS IDs (FR-…, NFR-…) are cited so every design choice can be traced to a requirement.
**Next documents:** Database Schema → AI/ML & Optimization Design.

---

## 1. Architecture Goals and Drivers

| Driver | Requirement source | Design consequence |
|---|---|---|
| Plan in ≤ 15 s on a laptop | NFR-PERF-01 | Cached model, in-memory snapshot, solver time limit 8 s, no network hops in the decision path |
| Correctness over speed of build | FR-CHK-01…05, NFR-HON-01 | Independent checker module that cannot import the optimizer; KPIs only from stored simulation records |
| Reproducibility | FR-DAT-01, NFR-REL-02 | Seeded generation, versioned model artifacts, deterministic solver mode |
| Small team, 48 hours | PRD §9 | Modular monolith, one backend language, no message broker, no external services |
| Long jobs without blocking the UI | FR-SIM-08, NFR-PERF-02 | Background job runner with progress polling |
| One-command demo, works offline | NFR-PRT-01, §2.4 | Docker Compose, SQLite, no paid or remote APIs |

**Style:** a **modular monolith**. One Python backend process with strictly layered modules, one SQLite database, one React front end. It is the simplest design that meets the requirements, and module boundaries are drawn so any module could later become a service.

---

## 2. System Context and Containers

```
                     ┌───────────────────────────────────────────────────┐
  Planner /          │                 Docker Compose                    │
  Manager /          │                                                   │
  Evaluator          │  ┌───────────────┐   /api/v1 (JSON)  ┌──────────┐ │
  (browser) ───────► │  │  web (nginx)  │ ────────────────► │   api    │ │
                     │  │  React SPA    │                   │ FastAPI  │ │
                     │  └───────────────┘                   │ + worker │ │
                     │                                      │  pools   │ │
                     │                                      └────┬─────┘ │
                     │                       ┌───────────────────┼─────┐ │
                     │                       ▼                   ▼     │ │
                     │               ┌──────────────┐   ┌────────────┐ │ │
                     │               │ SQLite (WAL) │   │ data/      │ │ │
                     │               │ vitaraniq.db │   │ models/    │ │ │
                     │               └──────────────┘   │ exports/   │ │ │
                     │                                  └────────────┘ │ │
                     └───────────────────────────────────────────────────┘
```

| Container | Technology | Responsibility |
|---|---|---|
| `web` | React + Vite + Tailwind, Recharts, built to static files, served by nginx | UI. Proxies `/api/*` to `api`. No business logic. |
| `api` | Python 3.11, FastAPI, uvicorn (1 process) | REST API, orchestration, in-process worker pools, all domain modules |
| SQLite | SQLite 3, WAL mode | One database file for data, plans, jobs and simulation records |
| Artifact store | Local volume `data/` | Model files, metrics, CSV exports |

There is no cache server, queue server or external API.

---

## 3. Layered Module Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│ L4  API layer          vitaraniq/api/    routers, pydantic schemas,   │
│                                          error mapping, CORS          │
├───────────────────────────────────────────────────────────────────────┤
│ L3  Services           vitaraniq/services/  PlanService, ForecastSvc, │
│     (orchestration)    BacktestService, WhatIfService, DataService    │
├───────────────────────────────────────────────────────────────────────┤
│ L2  Domain modules     data/ forecast/ service_level/ optimize/       │
│     (pure logic)       check/ explain/ sim/ reports/                  │
├───────────────────────────────────────────────────────────────────────┤
│ L1  Infrastructure     core/ (config, logging, units, ids)           │
│                        db/ (SQLAlchemy models, repositories)          │
│                        jobs/ (job runner, registry)                   │
└───────────────────────────────────────────────────────────────────────┘
```

**Dependency rules (enforced by an import-linter test, NFR-MNT-01)**
1. Imports go downward only. L4 → L3 → L2 → L1.
2. Domain modules in L2 never import `api` or `services`.
3. **`check/` imports nothing from `optimize/`, `forecast/` or `sim/`.** It depends only on `core/` and plain data classes (FR-CHK-01).
4. `sim/` may call `optimize/`, `forecast/`, `service_level/` and `check/`, but not the API layer.
5. Domain modules receive data as arguments. Only `services/` and `db/` read or write the database.

### 3.1 Module responsibilities

| Module | Responsibility | SRS | Owner |
|---|---|---|---|
| `api/` | Routes, request/response schemas, error body, request ids | §3.2.2 | Devendra |
| `services/` | One orchestrator per use case; transaction boundaries; caching | all | Devendra |
| `core/` | Settings, parameter file loader, logging, unit scaling (paise, ml), id generation, stage timers | NFR-OBS-01 | Devendra |
| `db/` | SQLAlchemy models, repositories, snapshot loader | §3.5 | Devendra |
| `jobs/` | Job table, process pool, progress reporting | FR-SIM-08 | Devendra |
| `data/` | Generator, demand model, calendar, validators | FR-DAT-01…08 | Pranav |
| `forecast/` | Feature builder, trainer, predictor, metrics, artifact store | FR-FCT-01…09 | Pranav |
| `service_level/` | Critical ratio, quantile mapping, `target_q` | FR-SVL-01…04 | Pranav |
| `optimize/` | Model builder, solver wrapper, scaling, waste coefficients, FEFO repair | FR-OPT, FR-SHL | Om |
| `check/` | Independent plan-checker | FR-CHK-01…05 | Om |
| `explain/` | Reason codes, evidence, counterfactuals | FR-EXP-01…05 | Devendra + Om |
| `sim/` | Day-loop simulator, four policies, KPI computation | FR-SIM-01…09 | Om + Pranav |
| `reports/` | Data card, CSV export, pick lists | FR-DAT-07, FR-REC-03/05 | Devendra |
| `web/` | React app | FR-UI-01…10 | Manish |

---

## 4. Internal Data Contracts

All domain modules exchange these plain, typed structures (Python dataclasses holding NumPy arrays or pandas DataFrames). They are the contract between Pranav's forecasting code and Om's optimizer, so they are frozen early.

| Structure | Contents | Produced by | Consumed by |
|---|---|---|---|
| `Params` | Parsed `config/params.yaml` (Appendix A constants, truck, costs, solver limits) | `core` | all |
| `Snapshot` | `as_of_day`; arrays shaped by index: warehouses W=4, stores S=25, SKUs P=12; `batches` table (batch_id, w, p, qty, expiry_day); `store_onhand` (s, p, qty, expiry_day); `intransit` (s, p, qty); `lanes` (w, s, km, transit_days, eligible); `sku` attributes (volume, shelf life, cost, price, min_life, w, g); `fleet[w]`, `store_cap[s]` | `db` snapshot loader | forecast, optimize, check, explain, sim |
| `ForecastTable` | For each (s, p): `p50, p70, p80, p90` of 9-day demand (integers); `model_version`; `cold_start` flag | `forecast.predict` | service_level, explain |
| `Targets` | For each (s, p): `target_q`, `p50_9d`, `chosen_quantile`, `cr` | `service_level` | optimize, explain |
| `SolveOptions` | `time_limit_s`, `deterministic`, `workers`, `seed`, `forced_sources` (for counterfactuals), `unavailable_warehouses` | service | optimize |
| `RawPlan` | Lines `(w, s, p, batch, qty)`, trucks per lane, unmet per (s, p), solver status, gap, time | `optimize` | `services`, `check` |
| `PlanLine` | `sku, from, to, batch, batch_expiry_day, qty, trucks_on_lane, line_cost_inr, priority, reason_codes[]` | `explain` | `db`, `api`, `reports` |
| `CheckResult` | `status` PASS/FAIL, list of violations `(check_id, entity, detail)` | `check` | `services` |
| `SimResult` | Per day and total: units demanded, sold, unmet, delivered, wastage units and ₹, transport ₹, truck loads; KPI dict | `sim` | `db`, `api` |

**Key function signatures (frozen interfaces)**

```python
# forecast
predict(model: ModelBundle, snapshot_history: SalesHistory, as_of_day: int) -> ForecastTable
# service_level
make_targets(forecast: ForecastTable, params: Params) -> Targets
# optimize
solve(snapshot: Snapshot, targets: Targets, forecast: ForecastTable,
      params: Params, opts: SolveOptions) -> RawPlan
# check  (no imports from optimize)
check_plan(snapshot: Snapshot, lines: list[PlanLine], params: Params) -> CheckResult
# explain
explain(snapshot: Snapshot, forecast: ForecastTable, targets: Targets,
        raw: RawPlan, params: Params) -> list[PlanLine]
# sim
class Policy(Protocol):
    def plan(self, state: SimState, day: int) -> list[PlanLine]: ...
simulate(policy: Policy, dataset_id: str, seed: int, scenario: str) -> SimResult
```

All four policies (B1, B2, O-MA, VitaranIQ) implement `Policy`, so the simulator treats them identically (FR-SIM-05).

---

## 5. Key Runtime Flows

### 5.1 `POST /plan` (synchronous, ≤ 15 s)

```
Client ─► api.router ─► PlanService.generate(request)
  1  load Snapshot from DB (db.snapshot_loader)                          ≤ 1 s
  2  validate Snapshot (data.validators, FR-DAT-06)                        
  3  load ModelBundle from cache (or artifact store); predict            ≤ 2 s
        ─► ForecastTable (300 rows × 4 quantiles)
  4  service_level.make_targets  ─► Targets
  5  optimize.solve  (thread pool, time limit 8 s)                       ≤ 8 s
        ─► RawPlan  (status OPTIMAL | FEASIBLE | FALLBACK_ZERO)
  6  FEFO check + repair (optimize.fefo_repair)
  7  explain.explain  ─► list[PlanLine] with reason codes               ≤ 1 s
  8  check.check_plan  ─► CheckResult       (FAIL ⇒ HTTP 500 PLAN_CHECK_FAILED)
  9  persist plan + lines (db)                                           ≤ 1 s
 10  return PlanResponse; schedule NEXT_BEST counterfactuals (P1, async)
```

Each stage is wrapped in a stage timer. The timings are stored with the plan and logged (NFR-OBS-01, NFR-PERF-01).

### 5.2 `POST /forecast/train` (job, ≤ 5 min)

```
api ─► ForecastService.start_train ─► jobs.submit(TrainJob) ─► 202 {job_id}
process pool worker:
  load sales + calendar from DB
  forecast.features.build(origins per Appendix C)       (no leakage: data ≤ origin day)
  forecast.train(4 quantile models, early stopping on validation)
  forecast.metrics (WAPE, bias, coverage, pinball) on test origins
  write artifacts data/models/<model_version>/  + metrics.json
  register model_version in DB;  update job progress at each step
client polls GET /jobs/{id} every 2 s
```

`model_version = lgbm_q_<first 8 chars of sha256(dataset_hash + feature_list + params)>`.

### 5.3 `POST /backtest` (job, ≤ 15 min)

```
api ─► BacktestService.start ─► jobs.submit(BacktestJob) ─► 202 {job_id}
worker pool (4 processes): one task per (policy, seed, scenario)  → 40 tasks
  task: sim.simulate(policy, seed, scenario)
        day loop 703..730 per SRS FR-SIM-02
        plans on days 703, 710, 717, 724  ─► policy.plan ─► check.check_plan
        optimizer policies run with deterministic=True (1 worker, fixed seed)
  write SimResult + KPIs to DB (backtest_runs)
parent: aggregates mean and min–max, marks KPI target/floor status
```

Time estimate: 20 optimizer-based tasks × 4 solves × ≤ 8 s ≈ 640 s of CPU; across 4 processes ≈ 160 s. Baseline tasks take seconds. This leaves a wide margin under the 15-minute limit.

### 5.4 `POST /whatif` (synchronous, ≤ 20 s)

`WhatIfService` loads the base plan's snapshot, applies the scenario to the in-memory `Snapshot` (P0: zero the chosen warehouse's batches and mark its lanes ineligible; P1: scale forecast quantiles or `truck_per_km`), re-runs steps 3–9 of §5.1 with `scenario` tagged, then computes the delta table against the base plan.

### 5.5 `POST /data/generate` (synchronous, ≤ 60 s)

`DataService` calls `data.generator(seed)`, writes tables in one transaction, computes `dataset_hash`, deletes dependent models, plans and backtests, and clears in-memory caches (FR-DAT-08).

---

## 6. Concurrency, Jobs and Caching

| Concern | Design | Why |
|---|---|---|
| Request handling | FastAPI `async` endpoints; CPU-bound work runs through `run_in_executor` so the event loop stays free | Keeps `/health` and reads responsive during a solve |
| Plan and what-if solves | **Thread pool, 2 workers.** CP-SAT and LightGBM prediction run in native code | Shares the in-memory model and snapshot cache, lowest latency |
| Training and backtests | **Process pool, up to 4 workers** (`ProcessPoolExecutor`, `spawn` start method) | CPU-bound, isolated from the API process; no GIL contention |
| Job tracking | `jobs` table: `job_id, type, status (QUEUED/RUNNING/SUCCEEDED/FAILED), progress 0–100, message, result_ref, created_at, finished_at` | Survives client disconnects (NFR-REL-03). No Redis or Celery needed. |
| Job recovery | On startup, jobs left `RUNNING` are marked `FAILED` with message `interrupted` | Honest state after restart |
| Solver parallelism | Interactive plan: 4 solver workers. Backtest and tests: 1 worker with fixed seed (`deterministic=true`) | Speed for the demo; reproducibility for evidence (FR-OPT-07) |
| Plan limit | One interactive solve at a time per dataset; extra requests queue for ≤ 30 s, then return 429 | Prevents CPU oversubscription during the demo |
| SQLite | WAL mode, `busy_timeout=5000 ms`, short write transactions, each process opens its own connection | Safe multi-process access |
| Caches (in memory) | `ModelBundle` by `model_version`; `Snapshot` by `(dataset_hash, as_of_day)`; `ForecastTable` by `(model_version, as_of_day)` | Meets the 2 s inference and 1 s assembly budgets |
| Cache invalidation | Every key contains `dataset_hash` or `model_version`. Regeneration or retraining changes the key; old entries are dropped. | Prevents stale plans (FR-DAT-08) |

---

## 7. Storage Architecture

| Store | Content | Notes |
|---|---|---|
| `data/vitaraniq.db` (SQLite) | Master data, daily sales, batches, store stock, lanes, calendar, plans, plan lines, jobs, forecast runs, backtest runs | Full table definitions are in the Database Schema document |
| `data/models/<model_version>/` | `q50.txt, q70.txt, q80.txt, q90.txt` (LightGBM boosters), `meta.json` (dataset hash, seed, features, params, timestamps), `metrics.json` | Immutable once written (FR-FCT-07) |
| `data/exports/` | Plan CSVs, pick lists, data card | Regenerable, safe to delete |
| `config/params.yaml` | Appendix A constants, solver limits, service-level floor | **Single source of truth.** The data card and the Assumptions page are generated from this file. |

Docker volume `vitaraniq_data` mounts `data/`, so a container restart keeps the dataset and model.

---

## 8. API Layer Design

- Base path `/api/v1`. Auto-generated OpenAPI at `/docs`. The exported `openapi.json` is committed and frozen by hour 3 so the front end can build against mocks.
- **Schemas:** pydantic models for every request and response. Plan lines, solver and checker status match SRS §3.2.2.
- **Error mapping:** a single exception handler converts domain exceptions to the SRS error body:

| Exception | HTTP | `code` |
|---|---|---|
| `ValidationFailure` | 422 | `VALIDATION_ERROR` (with `fields[]`) |
| `DatasetMissing` | 409 | `DATASET_NOT_FOUND` |
| `ModelMissing` | 409 | `MODEL_NOT_TRAINED` |
| `PlanCheckFailed` | 500 | `PLAN_CHECK_FAILED` (violations listed) |
| `NotFound` | 404 | `NOT_FOUND` |
| `Busy` | 429 | `SOLVER_BUSY` |
| other | 500 | `INTERNAL_ERROR` (no stack trace in the body) |

- **Request id:** every request gets an id that appears in logs and the `X-Request-Id` header.
- **CORS:** only the web origin. The API binds to `127.0.0.1` by default (NFR-SEC-01/02).
- **Long-running endpoints** return `202` with a `job_id`; progress is read from `GET /jobs/{id}`.

---

## 9. Front-End Architecture

| Aspect | Design |
|---|---|
| Stack | React 18, Vite, Tailwind, React Router, Recharts, Leaflet (P1) |
| State | Server state through React Query (caching, polling jobs every 2 s, retry). Local UI state with `useState`. No global store. |
| Data access | One typed API client generated from `openapi.json`. Pages never call `fetch` directly. |
| Pages | `Dashboard`, `Forecast`, `Plan`, `Backtest`, `WhatIf`, `Assumptions` (+ `Map` P1) |
| Shared components | `KpiCard`, `RiskHeatmap`, `ForecastChart`, `PlanTable` (sort, filter, paging), `ExplainPanel`, `JobProgress`, `StatusBadge`, `ErrorBanner`, `EmptyState` |
| Resilience | Every page implements loading, empty and error states (FR-UI-08). Errors display the server `message`. |
| Accessibility | Heatmap cells show numbers in addition to colour (§3.2.1) |
| Dev workflow | `npm run dev` with proxy to `localhost:8000`; mock-service-worker handlers for each endpoint during early build |

Front-end modules never compute KPIs or plan logic. They render what the API returns (NFR-HON-01).

---

## 10. Repository Layout

```
vitaraniq/
├── docker-compose.yml
├── Makefile                      # make up | test | lint | gen | train | backtest
├── README.md
├── config/
│   └── params.yaml               # single source of truth for constants
├── backend/
│   ├── pyproject.toml / requirements.txt   # pinned versions
│   ├── vitaraniq/
│   │   ├── api/        (routers/, schemas/, errors.py, main.py)
│   │   ├── services/   (plan.py, forecast.py, backtest.py, whatif.py, data.py)
│   │   ├── core/       (settings.py, logging.py, units.py, timers.py, ids.py)
│   │   ├── db/         (models.py, repositories.py, snapshot.py, migrations/)
│   │   ├── jobs/       (runner.py, registry.py)
│   │   ├── data/       (generator.py, demand_model.py, calendar.py, validators.py)
│   │   ├── forecast/   (features.py, train.py, predict.py, metrics.py, artifacts.py)
│   │   ├── service_level/ (newsvendor.py)
│   │   ├── optimize/   (model.py, solve.py, scaling.py, waste.py, fefo_repair.py)
│   │   ├── check/      (checks.py, result.py)         # no imports from optimize/
│   │   ├── explain/    (reason_codes.py, counterfactual.py)
│   │   ├── sim/        (engine.py, state.py, kpis.py, policies/{b1,b2,o_ma,vitaraniq}.py)
│   │   └── reports/    (data_card.py, csv_export.py, picklists.py)
│   └── tests/
│       ├── unit/  integration/  e2e/
│       ├── test_import_rules.py      # layering + checker independence
│       └── golden/                   # seed-42 hashes and expected CSV
├── web/
│   ├── package.json / package-lock.json
│   └── src/ (api/, pages/, components/, hooks/, mocks/)
└── docs/
    ├── PRD.md  SRS.md  ARCHITECTURE.md  DB_SCHEMA.md  AIML_DESIGN.md
    └── openapi.json
```

---

## 11. Deployment and Runtime

```yaml
# docker-compose.yml (outline)
services:
  api:
    build: ./backend
    command: uvicorn vitaraniq.api.main:app --host 0.0.0.0 --port 8000
    volumes: [ "vitaraniq_data:/app/data", "./config:/app/config:ro" ]
    environment: [ "DB_PATH=/app/data/vitaraniq.db", "SOLVER_TIME_LIMIT_S=8", "SOLVER_WORKERS=4" ]
    healthcheck: { test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"] }
  web:
    build: ./web          # multi-stage: npm build → nginx
    ports: [ "8080:80" ]  # nginx serves SPA and proxies /api to api:8000
    depends_on: [ api ]
volumes: { vitaraniq_data: {} }
```

| Item | Design |
|---|---|
| First run | `make up` → open `http://localhost:8080` → *Generate data* → *Train model* → *Generate plan*. A `make demo` target performs all three and pre-computes the backtest so the demo starts with cached results. |
| Config | Environment variables override `params.yaml` for deployment-level settings only (paths, solver limits). Business constants stay in `params.yaml`. |
| Pinning | All library versions are pinned. OR-Tools and LightGBM versions are recorded in model `meta.json` for reproducibility. |
| Resources | Reference hardware: 4 cores, 8 GB RAM. Expected peak memory < 2 GB (dataset ≈ 219 k rows; model files < 50 MB). |

---

## 12. Cross-Cutting Concerns

### 12.1 Observability (NFR-OBS-01)
- Structured JSON logs: `ts, level, request_id, module, event, duration_ms`.
- One summary line per plan: stage timings, solver status, gap, line count, checker result.
- `/health` returns: service up, dataset id and hash, active model version, last job status.

### 12.2 Error handling and failure modes

| Failure | Detection | Behaviour |
|---|---|---|
| No solution within time limit | Solver status `UNKNOWN` | Return `FALLBACK_ZERO` plan, flagged in the UI (FR-OPT-06) |
| Solver returns a plan that fails the checker | `check_plan` FAIL | HTTP 500 `PLAN_CHECK_FAILED`; plan is not stored as valid; violations logged (FR-CHK-03) |
| Model not trained | Model registry empty | 409 `MODEL_NOT_TRAINED`; UI shows a *Train model* action |
| Dataset missing or changed | Dataset id mismatch | 409 `DATASET_NOT_FOUND`; caches dropped |
| Invalid snapshot | Validators V1–V8 | 422 with field-level errors (FR-DAT-06) |
| Worker process crashes in a job | Future raises | Job `FAILED` with message; other tasks continue; partial results not shown as final |
| SQLite lock contention | `OperationalError` | Retry with backoff up to the busy timeout; then 500 |
| Container restart during a job | Startup scan | Job marked `FAILED: interrupted` |

### 12.3 Security (NFR-SEC)
Local-only binding by default, schema validation on every request, parameterized SQL through SQLAlchemy, no secrets in the repository, no personal data. Authentication is deliberately absent in P0 and listed as P2.

### 12.4 Testing architecture (NFR-MNT-02)

| Level | Content |
|---|---|
| Unit | Generator determinism (hash), feature leakage test, service-level table (Appendix A), solver constraints, **checker mutation tests (7)**, simulator accounting (stock conservation), reason-code recomputation |
| Integration | Plan end-to-end on seed 42 within 15 s; 20-seed reliability run (NFR-REL-01); deterministic double run equality (NFR-REL-02) |
| Contract | API responses validated against `openapi.json`; front-end mocks use the same schemas |
| Architecture | `test_import_rules.py` enforces layering and checker independence |
| E2E (demo) | Scripted walkthrough: generate → train → plan → export → backtest → outage what-if |

---

## 13. Requirement-to-Component Traceability

| SRS area | Primary components |
|---|---|
| FR-DAT | `data/`, `db/`, `services/data`, `reports/data_card` |
| FR-FCT | `forecast/`, `jobs/`, `services/forecast` |
| FR-SVL | `service_level/` |
| FR-OPT, FR-SHL | `optimize/` |
| FR-CHK | `check/` |
| FR-REC | `explain/`, `reports/csv_export`, `web/PlanTable` |
| FR-EXP | `explain/` |
| FR-SIM | `sim/`, `jobs/`, `services/backtest` |
| FR-WIF | `services/whatif` |
| FR-UI | `web/` |
| NFR-PERF | stage timers in `core/`, caches in `services/` |
| NFR-REL | deterministic mode in `optimize/`, jobs recovery in `jobs/` |
| NFR-SEC | `api/` middleware, local binding in Compose |
| NFR-MNT | import-linter test, `tests/` |
| NFR-PRT | `docker-compose.yml`, `Makefile` |
| NFR-HON | `sim/` records, `web/` rendering only |

---

## 14. Architecture Decision Records

| # | Decision | Alternatives considered | Rationale |
|---|---|---|---|
| ADR-1 | Python/FastAPI for the whole backend | Node + Express with a Python service | One language removes an integration boundary and the most likely failure in a short build. |
| ADR-2 | Modular monolith | Microservices | Fewer moving parts, one deployment, boundaries still enforced by import rules. |
| ADR-3 | OR-Tools CP-SAT | PuLP/CBC, SCIP | Integer variables and time limits with best-feasible results are first-class; free; fast at this size. Costs scaled to integers. |
| ADR-4 | SQLite (WAL) | PostgreSQL, MongoDB | Zero setup, enough for ≈ 220 k rows and low concurrency. Repositories hide the engine so PostgreSQL is a P2 swap. |
| ADR-5 | In-process pools plus a `jobs` table | Celery + Redis | No extra services. Meets job needs (progress, failure state) for two long jobs. |
| ADR-6 | Threads for plans, processes for jobs | All threads; all processes | Plans need shared cache and low latency; jobs need CPU isolation. |
| ADR-7 | Independent checker with no optimizer imports | Check inside the optimizer | A separate code path catches modelling errors that the solver shares with itself. |
| ADR-8 | `params.yaml` as single source of constants | Constants in code and docs | Keeps data card, UI and code consistent. |
| ADR-9 | Reason codes by rules from solver numbers | LLM-generated text | Verifiable, no hallucination, offline. LLM wording stays P2. |
| ADR-10 | React Query + typed client from OpenAPI | Redux, hand-written fetch | Less boilerplate; contract stays in sync. |

---

## 15. Risks to the Architecture

| Risk | Mitigation |
|---|---|
| Solver time on the full network | 8 s limit, fallback plan, develop on a small seed first (gate at hour 24) |
| SQLite write contention during the backtest | Workers return results to the parent, which writes in one batch; WAL mode and busy timeout |
| Process pool start-up cost on Windows (`spawn`) | Pool created once at app start; jobs reuse workers |
| Interface drift between Pranav's and Om's modules | Data contracts in §4 are frozen by hour 3 and covered by integration tests |
| Cache serving stale results after retraining | Version keys on every cache entry (§6) |

---

## 16. Evolution Path (beyond the hackathon)
PostgreSQL for concurrent users · Celery or a managed queue for long jobs · authentication and roles · route-level optimization (VRP) and multi-drop trucks · ERP/WMS connectors · scheduled retraining with drift monitoring (P2 feature).
