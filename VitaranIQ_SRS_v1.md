# VitaranIQ — Software Requirements Specification (SRS)

**Team:** Innovate-x · **Project:** VitaranIQ · **Triwizathon Problem Statement 2: Distribution Intelligence & Inventory Optimization Engine**
**Document:** SRS · **Version:** 1.0 · **Date:** 2026-10-24 · **Status:** Baseline for review
**Document set:** PRD v2.0 (why and what) → **SRS (exact requirements, this document)** → System Architecture → Database Schema → AI/ML & Optimization Design

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-24 | First baseline, derived from PRD v2.0 |

---

## 1. Introduction

### 1.1 Purpose
This SRS defines the exact, testable requirements for VitaranIQ. It is the reference for the architecture, database, AI/ML design, implementation and testing documents. The PRD explains the product intent. Where this SRS adds precision (formulas, constants, parameters), the SRS governs, and the PRD is updated to match (see Appendix D).

### 1.2 Scope
VitaranIQ is a web application that, for a synthetic FMCG network, (1) forecasts demand per store and SKU, (2) computes a feasible, cost-minimizing weekly dispatch plan from warehouse batches to stores, (3) validates and explains every plan line, and (4) proves the improvement against baseline policies with a reproducible simulation.

**In scope:** seeded data generation, forecasting, service-level selection, optimization, shelf-life/FEFO logic, plan validation, explanations, backtesting, what-if scenarios, dashboard and CSV export.
**Out of scope:** ERP/WMS integration, vehicle routing, procurement and purchase orders, multi-echelon planning from plants, real-time telemetry, mobile app, user accounts (P2 only).

### 1.3 Definitions

| Term | Definition |
|---|---|
| Store | Retail outlet or sub-distributor depot that receives stock. One row in `stores`. |
| SKU | Stock-keeping unit (a product variant). |
| Batch | A quantity of one SKU at one warehouse sharing one expiry date. |
| Position | `on-hand + in-transit + planned shipments` for a store–SKU. |
| Coverage window | 9 days: 7-day review period + 2-day maximum lead time. |
| Quantile forecast `Pq` | The q-th quantile of cumulative demand over the coverage window. |
| FEFO | First-expired, first-out. |
| WAPE | `Σ|actual − forecast| ÷ Σ actual`. |
| Pinball loss | Quantile-regression loss used to train and score quantile models. |
| CP-SAT | OR-Tools constraint-programming solver, used here as an integer program solver. |
| Plan | Set of shipment lines (warehouse, batch, store, SKU, quantity, trucks) for one planning cycle. |
| Plan-checker | Module that re-validates a plan using only its lines and the input snapshot. |
| Policy | A rule that produces a plan. B1, B2, O-MA and VitaranIQ are the four policies in §3.1.9. |
| Day index | Day 1 = 2024-11-01. Day 730 = 2026-10-31. |

### 1.4 References
- VitaranIQ PRD v2.0 (`VitaranIQ_PRD_v2.md`).
- Triwizathon Problem Statement 2 and Round 1 evaluation framework.
- IEEE 29148 (requirements engineering): structure used as a guide.

### 1.5 Conventions
- **shall** = mandatory. **should** = recommended. **may** = optional.
- **Priority:** P0 (MVP), P1 (after P0 is stable), P2 (optional). Requirements without a tag are P0.
- **IDs:** `FR-<AREA>-nn` functional, `NFR-<AREA>-nn` non-functional, `BR-nn` business rule.
- **Verification (V):** **T** automated test, **D** demonstration, **I** inspection, **A** measured analysis/experiment.
- Money is in Indian rupees (₹). The optimizer works in integer paise. Volume is in millilitres (ml). Dates are day indices unless stated.

---

## 2. Overall Description

### 2.1 Product perspective
VitaranIQ is a standalone, self-contained web application. It does not connect to external systems. All data is synthetic and generated inside the product.

```
 Browser (React SPA) ⇄ REST/JSON ⇄ FastAPI service ⇄ SQLite
                                      ├─ Data generator
                                      ├─ Forecast module (LightGBM)
                                      ├─ Service-level mapper
                                      ├─ Optimizer (OR-Tools CP-SAT)
                                      ├─ Plan-checker + Explainer
                                      └─ Backtest simulator
```

### 2.2 Product functions (summary)
1. Generate a reproducible dataset from a seed.
2. Train and cache quantile demand models and report accuracy.
3. Choose a service-level quantile per SKU by critical ratio.
4. Optimize a dispatch plan under physical and shelf-life constraints.
5. Verify the plan independently and attach reason codes.
6. Replay a 28-day backtest of four policies over 5 seeds and 2 supply scenarios.
7. Re-plan under a disruption (P0: warehouse outage).
8. Present everything in a dashboard and export a CSV.

### 2.3 User classes

| Class | Typical tasks | Access in P0 |
|---|---|---|
| Planner | Generate plan, review lines, export CSV, open explanations | Full |
| Regional manager | Read backtest and KPI pages | Full (read-oriented) |
| Warehouse manager | Read per-warehouse plan lines (P1 pick list) | Full |
| Evaluator | Read assumptions and backtest results | Full |
| Developer/admin (team) | Generate data, train model, run backtest | Full |

P0 has no login. All classes share one interface (see NFR-SEC-01).

### 2.4 Operating environment
- **Server:** Python 3.11, FastAPI, SQLite 3, LightGBM, OR-Tools, pandas, scikit-learn. Linux, macOS or Windows through Docker Compose.
- **Client:** current Chrome or Edge (latest two versions), viewport ≥ 1280 × 720.
- **Reference hardware** for all performance requirements: 4 CPU cores, 8 GB RAM, no GPU.
- **Network:** none required at run time. The demo shall work offline.

### 2.5 Design and implementation constraints
- Open-source and free libraries only. No paid API in any decision path.
- Optimization shall use OR-Tools CP-SAT with integer variables.
- Forecasting shall use LightGBM with the quantile objective.
- SQLite is the P0 database (PostgreSQL is P2).
- The entire stack shall start with `docker compose up`.

### 2.6 Assumptions and dependencies
- Synthetic data follows Appendix B. Real data is not available.
- History is uncensored: recorded sales equal true demand.
- Warehouses receive scheduled weekly inbound that is identical under every policy (Appendix C).
- Lost sales are not backordered.
- Road distance = 1.3 × great-circle distance.

---

## 3. Specific Requirements

### 3.1 Functional requirements

#### 3.1.1 Data generation and validation (DAT)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-DAT-01 | The system shall generate a complete dataset from an integer seed (default 42). Two runs with the same seed shall produce identical canonical CSV exports (equal SHA-256). | P0 | F-01 | T |
| FR-DAT-02 | The dataset shall contain 4 warehouses, 25 stores and 12 SKUs (Appendix A); 730 days of daily sales for every store–SKU (219,000 rows); and a calendar (holiday, festival, promo flags) for days 1–740. | P0 | F-01 | T |
| FR-DAT-03 | Daily demand shall follow the model in Appendix B. Historical sales shall equal true demand. | P0 | F-01 | T |
| FR-DAT-04 | The generator shall create the initial state for day 703: per warehouse–SKU 2–4 batches with remaining life uniformly between 30% and 100% of shelf life, total warehouse stock per SKU = 1.5 × network 9-day mean demand split by weights 0.35 / 0.30 / 0.20 / 0.15 (W1–W4); per store–SKU on-hand = 3 days of mean demand with remaining life uniformly between 40% and 100% of shelf life; no in-transit stock. | P0 | F-01 | T |
| FR-DAT-05 | The generator shall create lanes for every warehouse–store pair with `km = 1.3 × haversine`. `transit_days = 1` if km ≤ 200, `2` if 200 < km ≤ 450. Lanes with km > 450 shall be excluded. Every store shall have at least two eligible warehouses. | P0 | F-01 | T |
| FR-DAT-06 | The system shall validate inputs before every plan, forecast or backtest run and reject invalid data with field-level errors for: (V1) negative or non-integer quantity; (V2) expiry date earlier than the as-of day; (V3) lane without distance; (V4) SKU with non-positive volume, shelf life or unit cost; (V5) price ≤ unit cost; (V6) negative sales; (V7) duplicate `(day, store, sku)` key; (V8) batch referencing a missing warehouse or SKU. | P0 | NFR-03 | T |
| FR-DAT-07 | The system shall export a data card (Markdown) listing every constant of Appendix A, B and C with the seed and dataset hash. | P0 | F-11 | I |
| FR-DAT-08 | The system shall hold exactly one active dataset. Regeneration shall replace it and invalidate the cached model, plans and backtests that depend on it. | P0 | — | T |

#### 3.1.2 Demand forecasting (FCT)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-FCT-01 | The system shall train four LightGBM models with the quantile objective for α ∈ {0.5, 0.7, 0.8, 0.9}. The target for store *s*, SKU *p* at forecast origin *t* is `Y = Σ demand(t+1 … t+9)`. | P0 | F-02 | T |
| FR-FCT-02 | Features at origin *t* shall use data up to day *t* only: lags of daily sales (1, 7, 14, 28 days); rolling mean and standard deviation (7, 14, 28 days); mean of the same weekday over the last 4 weeks; day of week, day of month, month; days to next festival; **known-future** counts of promo days and holiday/festival days inside the 9-day target window; categorical SKU and store ids; store size, unit price, shelf life. | P0 | F-02 | I/T |
| FR-FCT-03 | Training, validation and test origins shall follow Appendix C, including a 9-day purge between segments. Early stopping shall use validation pinball loss. | P0 | F-02 | I/T |
| FR-FCT-04 | The system shall compute a baseline forecast `MA9 = 9 × mean(daily sales over the last 7 days)` for every origin. | P0 | F-02 | T |
| FR-FCT-05 | The system shall report, overall and by SKU and by store: WAPE (VitaranIQ and MA9), bias `Σ(forecast − actual) ÷ Σ actual`, empirical coverage of P50/P70/P80/P90, and mean pinball loss. | P0 | F-02 | T |
| FR-FCT-06 | After prediction the system shall enforce `P50 ≤ P70 ≤ P80 ≤ P90` (sort per series), clip negatives to 0 and round quantile forecasts up to integers. | P0 | F-02 | T |
| FR-FCT-07 | The trained model shall be stored as a versioned artifact with dataset hash, seed, training timestamp, feature list and metrics. Inference for 300 series × 4 quantiles shall complete in ≤ 2 s. | P0 | NFR-02 | T |
| FR-FCT-08 | The system shall expose actual vs forecast (P50 and P90 band) for any store–SKU and date range. | P0 | F-10 | D |
| FR-FCT-09 | For a store–SKU with fewer than 28 days of history, the system shall use the category-average demand per size unit × store size as forecast, and flag the series as `COLD_START`. | P1 | §11 | T |

#### 3.1.3 Service-level selection (SVL)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-SVL-01 | For each SKU the system shall compute the critical ratio `CR = (margin × g) ÷ (margin × g + overage_cost)` where `margin = price − unit_cost`, `g` is the stockout cost multiplier (Appendix A), and `overage_cost = unit_cost × w + holding_cost` (BR-02, BR-03). | P0 | F-03 | T |
| FR-SVL-02 | The system shall map CR to the nearest quantile in {0.7, 0.8, 0.9}. Ties go to the higher quantile. The minimum service quantile is 0.7 (configurable, default 0.7). | P0 | F-03 | T |
| FR-SVL-03 | `target_q[s,p]` shall equal the selected quantile forecast of 9-day demand for the store–SKU. | P0 | F-03 | T |
| FR-SVL-04 | The UI shall show the SKU → CR → quantile mapping table. | P0 | F-03 | D |

#### 3.1.4 Optimization (OPT)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-OPT-01 | The system shall build and solve one CP-SAT integer program per plan request with decision variables `x[w,s,p,b]` (shipped units), `y[w,s]` (trucks), `u[s,p]` (unmet demand against target) and `e[s,p]` (excess over target), all non-negative integers. | P0 | F-04 | I/T |
| FR-OPT-02 | The model shall enforce hard constraints C1–C9 (table below). | P0 | F-04/F-05 | T |
| FR-OPT-03 | The objective shall minimize total ₹: truck cost + lost-sales penalty `u × margin × g` + excess holding `e × holding_cost` + expected-wastage `x × waste_coeff` + FEFO tie-break `x × ε × age_rank` (ε = 1 paise). | P0 | F-04 | I/T |
| FR-OPT-04 | All monetary coefficients shall be scaled to integer paise and all volumes to integer ml before solving. A test shall recompute plan cost independently and match the solver objective components within ₹0.01. | P0 | F-04 | T |
| FR-OPT-05 | The default solver time limit shall be 8 s (request-configurable, max 30 s). The result shall report status (`OPTIMAL`, `FEASIBLE`, `FALLBACK_ZERO`), optimality gap % and solve time. | P0 | F-04 | T |
| FR-OPT-06 | If no solution is found within the limit, the system shall return the zero-shipment plan with `u = target_q`, status `FALLBACK_ZERO`. | P0 | F-04 | T |
| FR-OPT-07 | The request flag `deterministic=true` shall run the solver with one worker and a fixed seed. It shall be used by tests and the backtest. Default requests may use 4 workers. | P0 | NFR-01 | T |
| FR-OPT-08 | Each plan line shall carry a priority: `URGENT` if `cover_days ≤ transit_days`, `HIGH` if `cover_days ≤ 3`, else `NORMAL`. `cover_days = position_before ÷ (P50_9d ÷ 9)`. | P0 | F-06 | T |
| FR-OPT-09 | The plan response shall list unmet demand per store–SKU where `u > 0`, with units and margin at risk. | P0 | F-04 | T |
| FR-OPT-10 | The system shall persist every generated plan with scenario, model version, solver status and timing. | P0 | — | T |

**Constraints (FR-OPT-02)**

| # | Constraint | Statement |
|---|---|---|
| C1 | Warehouse stock | `Σ_s x[w,s,p,b] ≤ stock[w,p,b]` for every batch |
| C2 | Coverage | `position[s,p] + u[s,p] ≥ target_q[s,p]` |
| C3 | Excess | `e[s,p] ≥ position[s,p] − target_q[s,p]` |
| C4 | Truck volume | `Σ_{p,b} vol[p]·x[w,s,p,b] ≤ truck_cap·y[w,s]` |
| C5 | Fleet | `Σ_s y[w,s] ≤ fleet[w]` |
| C6 | Store capacity | `Σ_p vol[p]·position[s,p] ≤ store_cap[s]` |
| C7 | Shelf life on arrival | `x[w,s,p,b] = 0` if `expiry[b] − (as_of + transit[w,s]) < min_life[p]` |
| C8 | Sell-through cap | For each store–SKU and each remaining-life level *L* among its batches: units with remaining life ≤ *L* ≤ `P50_9d × min(L,9)/9 + (target_q − P50_9d) × min(L,9)/9` |
| C9 | Lane eligibility | `x[w,s,p,b] = 0` if the lane is excluded (FR-DAT-05) |

`position[s,p] = onhand[s,p] + intransit[s,p] + Σ_{w,b} x[w,s,p,b]`. The zero-shipment plan satisfies every constraint, so a feasible incumbent always exists.

#### 3.1.5 Shelf life and FEFO (SHL)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-SHL-01 | `min_life[p]` shall follow BR-01. A batch shall ship only if constraint C7 holds. | P0 | F-05 | T |
| FR-SHL-02 | `waste_coeff[b,s,p] = unit_cost[p] × share_unsold`, a constant computed before solving, where `share_unsold = clip((target_q[s,p] − D50(L)) ÷ target_q[s,p], 0, 1)`, *L* is the batch's remaining life on arrival and `D50(L) = P50_9d × min(L,9)/9`. | P0 | F-04 | T |
| FR-SHL-03 | FEFO invariant: within a warehouse and SKU, if a newer batch ships on a lane, every older batch eligible on that lane shall be fully shipped or exhausted. | P0 | F-05 | T |
| FR-SHL-04 | If the solver output violates FR-SHL-03, a deterministic repair shall swap quantities from newer to older eligible batches (total quantity per warehouse–store–SKU unchanged) and re-run the plan-checker. | P0 | F-06 | T |

#### 3.1.6 Plan-checker (CHK)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-CHK-01 | The plan-checker shall be a separate module that reads only plan lines and the input snapshot. It shall not import solver variables. | P0 | F-06 | I |
| FR-CHK-02 | It shall verify: (1) non-negative integer quantities; (2) per-batch shipped ≤ available; (3) truck volume ≤ capacity and trucks per warehouse ≤ fleet; (4) store capacity after delivery; (5) remaining life on arrival ≥ `min_life`; (6) lane eligibility; (7) FEFO invariant. | P0 | F-06 | T |
| FR-CHK-03 | It shall run on every plan, including baseline-policy plans, what-if plans and P1 overrides. A failing plan shall be rejected with HTTP 500 `PLAN_CHECK_FAILED` and a list of violations. It shall never be displayed as valid. | P0 | F-06 | T |
| FR-CHK-04 | Unit tests shall corrupt a valid plan once for each check (1)–(7) and confirm detection. | P0 | F-06 | T |
| FR-CHK-05 | Checker plus explainer latency shall be ≤ 1 s for a plan of up to 1,000 lines. | P0 | NFR-02 | T |

#### 3.1.7 Recommendations and export (REC)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-REC-01 | The plan table shall show: SKU, from warehouse, to store, batch id, batch expiry, quantity, trucks on lane, line cost (₹), priority, reason codes. | P0 | F-07 | D |
| FR-REC-02 | The table shall support sort on any column, filter by SKU, warehouse, store, priority and reason code, and pagination of 50 rows. | P0 | F-07 | D |
| FR-REC-03 | `GET /plan/{id}/export?format=csv` shall return UTF-8 CSV with a header row and columns: `plan_id, as_of_day, sku, from_warehouse, to_store, batch_id, batch_expiry_day, qty, trucks_on_lane, line_cost_inr, priority, reason_codes` (codes joined with `|`). | P0 | F-07 | T |
| FR-REC-04 | `line_cost_inr` shall be the lane truck cost allocated to the line in proportion to its volume share of the lane's loaded volume. Allocated costs of a lane shall sum to the lane's truck cost. | P0 | F-07 | T |
| FR-REC-05 | The system shall produce one FEFO pick list per warehouse (CSV). | P1 | F-17 | D |

#### 3.1.8 Explainability (EXP)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-EXP-01 | Each plan line shall carry one or more reason codes from the table below, with evidence numbers copied from solver and forecast data. | P0 | F-08 | T |
| FR-EXP-02 | Every line shall have ≥ 1 code. If no other trigger applies, `REPLENISH_TO_TARGET` shall be assigned. | P0 | F-08 | T |
| FR-EXP-03 | A test shall recompute the evidence of every line from the stored snapshot and match the displayed values exactly. | P0 | F-08 | T |
| FR-EXP-04 | The system shall compute `NEXT_BEST` for the top 20 lines by line value: re-solve with the next-best source warehouse forced, limit 2 s per re-solve, run asynchronously after the plan is returned. | P1 | F-16 | T |
| FR-EXP-05 | An LLM may rephrase codes into one sentence using computed numbers only. It shall not alter quantities or decisions. A template shall be the fallback. | P2 | F-19 | I |

| Code | Trigger | Evidence fields |
|---|---|---|
| `LOW_COVER` | `cover_days < 3` before shipment | `cover_days, p50_9d, selected_quantile_value, onhand, intransit` |
| `EXPIRY_FIRST` | Line's batch is the earliest-expiring eligible batch with stock at the source | `batch_id, expires_in_days_on_arrival` |
| `LOWEST_COST_SOURCE` | Source has the lowest `lane_cost_per_litre` among eligible warehouses with stock of the SKU | `lane_cost_per_litre, alternatives[]` |
| `CAPACITY_LIMITED` | Truck fill ≥ 95% or store volume use ≥ 95% after delivery | `truck_fill_pct, store_use_pct` |
| `SCARCE_PRIORITY` | `Σ_s u[s,p] > 0` for the SKU and this line delivers ≥ 1 unit | `network_unmet_units, margin_at_risk_inr` |
| `REPLENISH_TO_TARGET` | Default when no other trigger applies | `target_q, position_before, position_after` |
| `NEXT_BEST` (P1) | Counterfactual computed | `alt_warehouse, delta_cost_inr` |

`lane_cost_per_litre = (truck_fixed + truck_per_km × km) ÷ (truck_cap in litres)`.

#### 3.1.9 Backtest simulation (SIM)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-SIM-01 | The simulator shall replay days 703–730 (28 days) with plans generated at the start of days 703, 710, 717 and 724, using only information up to the previous day. The forecast model shall not be retrained inside the window. | P0 | F-09 | T |
| FR-SIM-02 | Daily order of events: (1) scheduled inbound and shipment arrivals are added to stock; (2) realized demand is served from store stock FEFO, unmet demand is lost; (3) expired units are removed at stores and warehouses and counted as wastage. | P0 | F-09 | T |
| FR-SIM-03 | **B1:** order quantity = `max(0, 9 × mean(daily sales of last 28 days) − position)`, filled from the nearest eligible warehouse with stock, then the next nearest. **B2:** order quantity = `max(0, S − position)` with `S = 1.25 × 9 × mean(daily sales of last 28 days)`, same sourcing. Both use FEFO and `ceil(volume ÷ truck_cap)` trucks per lane. | P0 | F-09 | T |
| FR-SIM-04 | **O-MA:** the same optimizer, constraints and objective as VitaranIQ, with `P50_9d = 9 × MA7` (mean daily sales of last 7 days) and `target_q = ceil(1.25 × 9 × MA7)` for every SKU. **VitaranIQ:** quantile forecasts and critical-ratio targets (§3.1.2, §3.1.3). | P0 | F-09 | T |
| FR-SIM-05 | All four policies shall use identical demand, trucks, costs, capacities and the plan-checker. | P0 | F-09 | T |
| FR-SIM-06 | The simulator shall run 5 demand seeds {11, 12, 13, 14, 15} and 2 supply scenarios: **normal** (inbound = 105% of mean network demand) and **scarcity** (80%). Days up to 702 are fixed by dataset seed 42; days 703–730 are sampled per seed. | P0 | F-09 | T |
| FR-SIM-07 | The KPIs shall be computed with the formulas of BR-05 and stored with policy, seed, scenario, model version and timestamp. No KPI shall be hardcoded or edited. | P0 | NFR-04 | I/T |
| FR-SIM-08 | The backtest shall run as a background job. A full run (4 policies × 5 seeds × 2 scenarios) shall finish in ≤ 15 min on reference hardware. A quick mode (1 seed, normal scenario) shall finish in ≤ 2 min. Results shall be cached for the demo. | P0 | F-09 | A |
| FR-SIM-09 | The UI shall show mean and min–max over seeds per policy and KPI, with targets and floors from §8 of the PRD, and mark each as met, below target, or below floor. | P0 | F-10 | D |

#### 3.1.10 What-if scenarios (WIF)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-WIF-01 | The user shall be able to select one warehouse as unavailable. The system shall set its stock to zero, re-plan and return a delta table versus the base plan: transport ₹, unmet units, margin at risk, affected stores, change in truck count. | P0 | F-12 | D/T |
| FR-WIF-02 | Result time shall be ≤ 20 s. | P0 | F-12 | A |
| FR-WIF-03 | Regional demand spike: multiply all forecast quantiles of the selected stores by a user factor between 1.1 and 2.0. | P1 | F-13 | T |
| FR-WIF-04 | Fuel-price change: multiply `truck_per_km` by a user factor between 0.8 and 1.5. | P1 | F-13 | T |

#### 3.1.11 User interface (UI)

| ID | Requirement | Pri | PRD | V |
|---|---|---|---|---|
| FR-UI-01 | **Dashboard:** KPI cards (fill rate, stockout rate, wastage ₹, transport ₹, truck fill) from the latest backtest; heatmap of store × SKU with stockout risk `r = clip(1 − position ÷ P90_9d, 0, 1)` (green < 0.3, amber 0.3–0.6, red > 0.6) and expiry risk `x = clip((units expiring within 7 days − P50_9d × 7/9) ÷ onhand, 0, 1)`. | P0 | F-10 | D |
| FR-UI-02 | **Forecast page:** store and SKU selectors, actual vs P50 line with P90 band, WAPE and coverage for the selection. | P0 | F-10 | D |
| FR-UI-03 | **Plan page:** *Generate Plan* button, status badge (solver status, gap, time, checker PASS), plan table (FR-REC-01/02), CSV export. | P0 | F-07 | D |
| FR-UI-04 | **Explain panel:** opens from a line and shows reason codes, evidence, forecast vs stock chart and lane cost. | P0 | F-08 | D |
| FR-UI-05 | **Backtest page:** policy × KPI table, day-by-day charts of cumulative lost units and wastage ₹, scenario and seed selectors. | P0 | F-09 | D |
| FR-UI-06 | **What-if page:** warehouse outage control (FR-WIF-01) and delta table. | P0 | F-12 | D |
| FR-UI-07 | **Assumptions page:** renders the data card and assumptions/limitations (PRD §11). | P0 | F-11 | D |
| FR-UI-08 | Every page shall have loading, empty and error states. API errors shall display the server's `message`. | P0 | — | D |
| FR-UI-09 | Map view of warehouse → store flows; click opens the plan line. | P1 | F-14 | D |
| FR-UI-10 | Planner override editor (edit quantity or force source) with re-validation by the plan-checker. | P1 | F-15 | D |

#### 3.1.12 Documentation (DOC)

| ID | Requirement | Pri | V |
|---|---|---|---|
| FR-DOC-01 | The repository shall contain a README with one-command start, seed usage, test commands, and a description of all four policies. | P0 | I |
| FR-DOC-02 | The Assumptions page and README shall state data sources, limitations and the definition of every KPI. | P0 | I |

---

### 3.2 External interface requirements

#### 3.2.1 User interface
React + Vite + Tailwind single-page app, Recharts for charts, Leaflet for P1 map. Desktop-first (≥ 1280 px wide), usable at 1024 px. Colour is never the only carrier of meaning (risk cells also show a number).

#### 3.2.2 REST API
Base path `/api/v1`. JSON request and response bodies. Standard error body:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Store S07 has no lane to W3",
             "fields": [ { "path": "lanes[W3,S07].km", "issue": "missing" } ] } }
```

| Method | Path | Purpose | Pri | p95 latency |
|---|---|---|---|---|
| GET | `/health` | Service, dataset and model status | P0 | 100 ms |
| POST | `/data/generate` | Body `{seed}`; creates dataset, returns counts and hash | P0 | 60 s |
| GET | `/data/summary` | Entity counts, dataset hash, seed | P0 | 300 ms |
| POST | `/forecast/train` | Starts training job, returns `job_id` | P0 | job ≤ 5 min |
| GET | `/jobs/{job_id}` | Job status, progress, result reference | P0 | 300 ms |
| GET | `/forecast/accuracy` | Query `group_by=overall|sku|store` | P0 | 300 ms |
| GET | `/forecast/series` | Query `store_id, sku, from_day, to_day` | P0 | 300 ms |
| GET | `/service-levels` | SKU → CR → quantile table | P0 | 300 ms |
| POST | `/plan` | Body `{as_of_day=703, scenario?, solver_time_limit_s?, deterministic?}`; returns plan | P0 | 15 s |
| GET | `/plan/{id}` | Plan header, solver and checker status, KPIs | P0 | 300 ms |
| GET | `/plan/{id}/lines` | Lines with reasons, paging and filters | P0 | 300 ms |
| GET | `/plan/{id}/export` | Query `format=csv` | P0 | 1 s |
| POST | `/backtest` | Body `{seeds, scenarios, policies}`; returns `job_id` | P0 | job ≤ 15 min |
| GET | `/backtest/{run_id}` | KPIs by policy, seed, scenario | P0 | 500 ms |
| POST | `/whatif` | Body `{base_plan_id, scenario:{type, params}}`; returns plan and delta | P0 (outage), P1 (others) | 20 s |
| GET | `/meta/assumptions` | Data card and assumptions | P0 | 300 ms |
| POST | `/plan/{id}/override` | Manual edit with re-check | P1 | 2 s |
| GET | `/plan/{id}/counterfactual` | `NEXT_BEST` results | P1 | 300 ms |
| GET | `/plan/{id}/picklists` | Per-warehouse CSV | P1 | 1 s |

**Status codes:** 200/201 success; 202 job accepted; 400 malformed request; 404 unknown id; 409 `MODEL_NOT_TRAINED` or `DATASET_NOT_FOUND`; 422 `VALIDATION_ERROR`; 500 `PLAN_CHECK_FAILED` or internal error.

**Plan response (abridged)**
```json
{ "plan_id": "p_0001", "as_of_day": 703, "model_version": "lgbm_q_<hash>",
  "solver": { "status": "OPTIMAL", "gap_pct": 0.0, "time_s": 5.2, "workers": 4 },
  "checker": { "status": "PASS", "violations": 0 },
  "lines": [ { "sku": "BISC-250", "from": "W1", "to": "S14", "batch": "B-221", "qty": 120,
               "trucks_on_lane": 1, "line_cost_inr": 3720, "priority": "URGENT",
               "reason_codes": [ { "code": "LOW_COVER", "evidence": { "cover_days": 1.8 } } ] } ],
  "unmet": [ { "store": "S07", "sku": "MILK-1L", "units": 35, "margin_at_risk_inr": 280 } ] }
```

#### 3.2.3 Software interfaces
SQLite through SQLAlchemy (parameterized queries only); OR-Tools CP-SAT Python API; LightGBM Python API; pandas and scikit-learn for data handling and metrics. Library versions shall be pinned in `requirements.txt` and `package-lock.json`.

#### 3.2.4 Data interfaces
CSV export format in FR-REC-03. Dataset export (CSV per table) for the dataset hash test in FR-DAT-01.

---

### 3.3 Non-functional requirements

| ID | Requirement | V |
|---|---|---|
| NFR-PERF-01 | End-to-end `POST /plan` (4 × 25 × 12) shall complete in ≤ 15 s: input assembly ≤ 1 s, forecast inference ≤ 2 s, solve ≤ 8 s, checker and explainer ≤ 1 s, serialization and persistence ≤ 2 s. Each stage time shall be logged. | A |
| NFR-PERF-02 | Model training (4 quantile models, 219,000 series-days) shall complete in ≤ 5 min. | A |
| NFR-PERF-03 | Dashboard and read-only pages shall load in ≤ 2 s on demo data. | A |
| NFR-PERF-04 | What-if re-optimization shall complete in ≤ 20 s. | A |
| NFR-REL-01 | `POST /plan` shall return a valid, checker-approved plan for 20 consecutive random seeds with no unhandled exception. | T |
| NFR-REL-02 | Given identical dataset, model version, request and `deterministic=true`, two plan runs shall return identical lines. | T |
| NFR-REL-03 | Background jobs shall survive a client disconnect and report failures with a message. | T |
| NFR-USE-01 | From the dashboard, a planner shall reach an exported plan in ≤ 4 clicks. | D |
| NFR-USE-02 | All error messages shall name the failing field or condition and, where possible, the corrective action. | I |
| NFR-SEC-01 | P0 has no authentication and the app shall bind to localhost by default. It shall contain no personal data and no secrets in the repository. A login is P2. | I |
| NFR-SEC-02 | All request bodies shall be validated by schema. SQL shall be parameterized. CORS shall allow only the front-end origin. | T/I |
| NFR-MNT-01 | Modules shall be separated as in §2.1. The checker shall not import the optimizer package. | I |
| NFR-MNT-02 | Line coverage of the checker, simulator accounting and service-level modules shall be ≥ 80%. | T |
| NFR-PRT-01 | `docker compose up` shall start the full system on Windows, macOS and Linux. | D |
| NFR-OBS-01 | The service shall log one structured line per plan with stage timings, solver status and gap. | I |
| NFR-HON-01 | No KPI shown in the UI shall be a constant. Each shall link to a stored simulation record. | I |

---

### 3.4 Business rules and formulas

| ID | Rule |
|---|---|
| BR-01 | `min_life[p]` (days remaining on arrival): if `shelf_life ≤ 14`: `max(2, ceil(0.5 × shelf_life))`; otherwise `min(ceil(0.4 × shelf_life), 120)`. |
| BR-02 | Write-off factor `w[p]`: 1.0 if `shelf_life ≤ 14`; 0.3 if `≤ 90`; otherwise 0.1. |
| BR-03 | `holding_cost[p] = 0.018 × unit_cost[p]` (0.2% per day over 9 days). `overage_cost[p] = unit_cost[p] × w[p] + holding_cost[p]`. |
| BR-04 | `lost-sales penalty per unit = margin[p] × g[p]`. |
| BR-05 | **KPIs (per policy, seed and scenario, over days 703–730):** fill rate = units sold ÷ units demanded; stockout rate = store–SKU–days with unmet demand > 0 ÷ all store–SKU–days; wastage ₹ = expired units × unit cost (stores + warehouses); transport ₹ = Σ trips × (`truck_fixed + truck_per_km × km`); cost per unit delivered = transport ₹ ÷ units delivered to stores; truck fill = loaded volume ÷ (trucks × `truck_cap`); total cost = transport ₹ + unmet units × margin + wastage ₹; margin-weighted fill rate = Σ margin × units sold ÷ Σ margin × units demanded. |
| BR-06 | **Comparison:** the *strongest baseline* for a KPI is the better of B1 and B2 on that KPI (mean over seeds). Relative improvement = `(baseline − VitaranIQ) ÷ baseline` for cost-type KPIs. |
| BR-07 | Trucks serve one lane (one warehouse → one store). A truck is used only for shipments on its lane. The same truck cost formula is used for all policies. |

### 3.5 Data requirements
The logical entities are `warehouses, stores, products, batches, store_stock, sales_daily, calendar, lanes, plans, plan_lines, forecast_runs, backtest_runs`. Their exact schema is defined in the Database Schema document. Integrity rules: primary keys unique; all foreign keys valid; quantities non-negative integers; `expiry_day ≥ as_of_day` for stock batches; one active dataset. Data volume at the reference scale: ≈ 219,000 sales rows, ≈ 1,200 lane–SKU eligibility combinations computed at run time (4 × 25 × 12), ≤ 1,000 plan lines per plan.

---

## 4. Verification and Traceability

### 4.1 Verification approach

| Area | Method | Evidence |
|---|---|---|
| Data generation, validation | Unit tests, hash comparison | `tests/test_generator.py`, hash test |
| Forecasting | Holdout evaluation | Accuracy report with WAPE, bias, coverage |
| Service level | Unit tests on a fixed SKU table | Expected quantile per SKU (Appendix A) |
| Optimizer | Constraint tests plus independent cost recompute | Test report, checker output |
| Plan-checker | Mutation tests (one per check) | 7 passing tests |
| Simulator | Accounting tests (stock conservation, cost formulas) | Test report |
| Explanations | Recompute-and-compare tests | 100% match |
| UI | Scripted demo walkthrough | Demo script run |
| Performance | Timed runs on reference hardware | Timing log |

### 4.2 PRD → SRS traceability

| PRD item | SRS requirements |
|---|---|
| F-01 Data generator | FR-DAT-01 to 05, 07, 08 |
| F-02 Forecast | FR-FCT-01 to 08 |
| F-03 Service level | FR-SVL-01 to 04 |
| F-04 Optimizer | FR-OPT-01 to 10, FR-SHL-02 |
| F-05 Shelf life, FEFO | FR-SHL-01, 03, 04 |
| F-06 Plan-checker | FR-CHK-01 to 05 |
| F-07 Recommendation table | FR-REC-01 to 04, FR-UI-03 |
| F-08 Explainability | FR-EXP-01 to 03, FR-UI-04 |
| F-09 Backtest | FR-SIM-01 to 09, FR-UI-05 |
| F-10 Dashboard | FR-UI-01, 02, FR-FCT-08 |
| F-11 Assumptions page | FR-DAT-07, FR-UI-07, FR-DOC-01, 02 |
| F-12 Outage what-if | FR-WIF-01, 02, FR-UI-06 |
| F-13 More what-ifs | FR-WIF-03, 04 |
| F-14 Map | FR-UI-09 |
| F-15 Overrides | FR-UI-10 |
| F-16 Counterfactual | FR-EXP-04 |
| F-17 Pick lists | FR-REC-05 |
| F-19 LLM rewording | FR-EXP-05 |
| NFR-01…05 | NFR-REL-02, NFR-PERF-01, FR-DAT-06, NFR-HON-01, NFR-MNT-02 |

---

## Appendix A — Reference Parameter Set

**Network**

| Item | Value |
|---|---|
| Warehouses | W1 Pune (18.52, 73.86), W2 Mumbai–Bhiwandi (19.08, 72.88), W3 Nashik (20.00, 73.79), W4 Kolhapur (16.71, 74.24) |
| Stores | 25, placed with seeded jitter around: Pune, Mumbai, Thane, Nashik, Kolhapur, Satara, Sangli, Solapur, Ahmednagar, Aurangabad, Ichalkaranji, Karad |
| Store size multiplier | Drawn from `[0.5, 0.6, 0.6, 0.7, 0.8, 0.8, 0.9, 0.9, 1.0, 1.0, 1.0, 1.1, 1.1, 1.2, 1.2, 1.2, 1.3, 1.4, 1.5, 1.5, 1.6, 1.7, 1.8, 2.0, 1.0]`, shuffled by seed |
| Store capacity | `18,000 L × size` (18,000,000 ml × size) |
| Truck | Capacity 4,000 L (4,000,000 ml); fixed ₹800 per trip; ₹14 per km; fleet 30 per warehouse; one dispatch day per cycle |
| Lanes | `km = 1.3 × haversine`; 1 day if ≤ 200 km, 2 days if ≤ 450 km, excluded above 450 km |
| Holding / overage constants | BR-02, BR-03 |

**SKUs** (placeholder values chosen to be realistic; unit in ml)

| SKU | Cost ₹ | Price ₹ | Margin ₹ | Vol ml | Shelf days | min_life | w | g | Base units/day (size 1.0) | CR | Quantile |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MILK-1L | 52 | 60 | 8 | 1,200 | 5 | 3 | 1.0 | 4 | 120 | 0.38 | P70 (floor) |
| CURD-400G | 28 | 34 | 6 | 500 | 10 | 5 | 1.0 | 2 | 75 | 0.30 | P70 (floor) |
| BREAD-400G | 30 | 40 | 10 | 2,500 | 4 | 2 | 1.0 | 4 | 90 | 0.57 | P70 (floor) |
| BISC-250 | 22 | 30 | 8 | 800 | 180 | 72 | 0.1 | 2 | 105 | 0.86 | P90 |
| NOODLE-70 | 11 | 14 | 3 | 400 | 270 | 108 | 0.1 | 2 | 90 | 0.82 | P80 |
| RICE-5KG | 310 | 360 | 50 | 6,500 | 365 | 120 | 0.1 | 4 | 36 | 0.85 | P80 |
| ATTA-5KG | 240 | 275 | 35 | 6,500 | 120 | 48 | 0.1 | 4 | 42 | 0.83 | P80 |
| OIL-1L | 140 | 160 | 20 | 1,100 | 270 | 108 | 0.1 | 4 | 60 | 0.83 | P80 |
| TEA-250G | 110 | 130 | 20 | 900 | 365 | 120 | 0.1 | 2 | 54 | 0.75 | P80 (tie → higher) |
| SOAP-100G | 28 | 36 | 8 | 200 | 730 | 120 | 0.1 | 1 | 48 | 0.71 | P70 |
| JUICE-1L | 75 | 95 | 20 | 1,100 | 90 | 36 | 0.3 | 1 | 42 | 0.46 | P70 (floor) |
| CHIPS-90G | 16 | 20 | 4 | 1,500 | 120 | 48 | 0.1 | 1 | 84 | 0.68 | P70 |

CR is computed with BR-02 to BR-04. The CR and quantile columns are the expected output for the unit test in FR-SVL-01/02.

## Appendix B — Demand Model

For day *d* (day index), store *s*, SKU *p*:

```
μ[d,s,p] = base[p] × size[s] × weekday[dow(d)] × season[p,d] × festival[d,p] × promo[d,s,p] × trend[d]
demand[d,s,p] ~ NegativeBinomial(mean = μ, variance = μ + 0.10·μ²)
```

| Component | Definition |
|---|---|
| weekday | Mon 0.90, Tue 0.90, Wed 0.95, Thu 1.00, Fri 1.10, Sat 1.25, Sun 1.20 |
| season | `1 + A[p] × sin(2π (doy − 15) / 365)`; `A = 0.25` for JUICE-1L, `0.05` for all others |
| festival | Fixed calendar of 12 festival windows per year (3–5 days each). Multiplier 1.5 for OIL, ATTA, BISC, CHIPS, TEA, JUICE; 1.2 for all other SKUs |
| promo | Each store–SKU has two 5-day promo windows per quarter, chosen by seed. Multiplier 1.35 on promo days and 0.85 on the 3 days after |
| trend | `1 + 0.10 × d / 730` |

Promo and festival calendars are known in advance for days 1–740 and are available to the forecaster as covariates.

## Appendix C — Data Splits and Backtest Schedule

| Segment | Days | Notes |
|---|---|---|
| Train origins | 1–620 | Target windows end by day 629 |
| Purge | 621–629 | No origins |
| Validation origins | 630–663 | Early stopping on pinball loss; targets end by day 672 |
| Purge | 664–672 | No origins |
| Test origins | 673–721 | Reported WAPE, bias, coverage (dataset seed 42) |
| Backtest window | 703–730 | Plans at days 703, 710, 717, 724; 5 seeds; days ≥ 703 sampled per seed |

Scheduled warehouse inbound arrives at the start of days 703, 710, 717 and 724 before planning. Inbound quantity per SKU = scenario factor (1.05 normal, 0.80 scarcity) × mean weekly network demand, split by warehouse weights 0.35 / 0.30 / 0.20 / 0.15. Remaining life at receipt: `shelf_life − 1` day if `shelf_life ≤ 14`, otherwise `0.9 × shelf_life`.

## Appendix D — Requirement Risks and Change Control

| Risk | Effect | Handling |
|---|---|---|
| Single-store trucks (BR-07) may give truck fill below the PRD target of 80% | KPI miss | Parameters in Appendix A were chosen so a store's weekly order is about 2–4 truckloads. If the first end-to-end run shows < 70%, adjust store scale or KPI through change control before the build review. |
| Newsvendor quantiles all hit the P70 floor for perishables | Less visible differentiation | Intentional: protects fill rate. Floor value is configurable (FR-SVL-02). |
| CP-SAT run time on the full network | NFR-PERF-01 | 8 s limit and fallback (FR-OPT-05/06) |

**PRD updates needed to match this SRS:** (1) F-03 and §6.5: replace `(1 + criticality)` by `g[p] ∈ {1, 2, 4}`; (2) F-03: state the P70 minimum service quantile and the {P70, P80, P90} mapping instead of "CR below 0.5 uses P50"; (3) §8.1: keep truck-fill target under review (above).

**Change control:** any requirement change is recorded in the version table, applied to the affected downstream documents (architecture, schema, AI/ML design), and reflected in the traceability table.
