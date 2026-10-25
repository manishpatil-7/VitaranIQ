# VitaranIQ — In-Depth System Memory Map

**Project:** VitaranIQ — Distribution Intelligence & Inventory Optimization Engine  
**Team:** Innovate-x (Lead: Devendra Nimbalkar · Members: Manish Patil, Pranav Yadav, Om Lad)  
**Hackathon:** Triwizathon · Problem Statement 2 (FMCG Regional Allocation & Inventory Optimization)  
**Document Context:** Synthesized from `Vitaran-IQ_PRD.md`, `VitaranIQ_SRS_v1.md`, `VitaranIQ_System_Architecture_v1.md`, `VitaranIQ_Database_Schema_v1.md`, and `VitaranIQ_AIML_Optimization_Design_v1.md`.

---

## 1. High-Level Vision & Problem Topology

### 1.1 Core Problem Statement
FMCG distribution across regional networks suffers from:
- **Spatial Mismatches:** Stockouts in high-velocity stores coexisting with excess holding in low-velocity stores.
- **Perishability & Expiry Wastage:** Non-FEFO picking and sending short-life batches to slow-moving outlets causing write-offs.
- **Logistical Inefficiencies:** Sub-optimal truck fills, ignoring second-source warehouses, and erratic transport expenses.
- **Unprioritized Scarcity:** Pro-rata allocation during stock shortages instead of prioritizing high-margin / critical SKUs.

### 1.2 VitaranIQ Core Value Proposition
A closed-loop, 4-stage pipeline that converts sales history, inventory batches, and network constraints into an executable weekly dispatch plan:
$$\text{History} \xrightarrow{\text{Forecast (LightGBM Quantiles)}} \text{Uncertainty Bounds} \xrightarrow{\text{Service-Level (Newsvendor)}} \text{Store Targets} \xrightarrow{\text{Optimize (CP-SAT)}} \text{Batch Dispatch Plan} \xrightarrow{\text{Independent Checker}} \text{Verified Plan + Explanations}$$

### 1.3 Key Differentiators vs. Typical Solutions
1. **Distributional Forecasts instead of Point Estimates:** 4 Quantiles ($P50, P70, P80, P90$) over cumulative 9-day coverage windows avoid error accumulation from summing daily forecasts.
2. **Newsvendor Critical-Ratio Service Levels:** Differentiates perishable low-margin items ($CR \approx 0.30 \to P70$ floor) from high-margin staples ($CR \approx 0.86 \to P90$).
3. **Batch-Level, Shelf-Life-Aware Integer Programming:** Direct formulation of batch remaining life, arrival eligibility, sell-through caps, and integer truck loads.
4. **Independent Plan-Checker with Deterministic FEFO Repair:** Complete isolation between solver code and validation code.
5. **Ablation-Driven Proof Engine:** 28-day simulator across 4 policies ($\text{B1}, \text{B2}, \text{O-MA}, \text{VitaranIQ}$) across 5 seeds and 2 supply scenarios to isolate the AI contribution ($+5\%$ cost reduction vs O-MA).
6. **Rule-Based Ground-Truth Explainability:** Every line contains mathematically verifiable reason codes with zero LLM hallucination in the decision path.

---

## 2. Network Topology & Reference Parameters

### 2.1 Geographic & Network Spec (Maharashtra Demo Network)
- **4 Warehouses ($W=4$):**
  - $W_1$: Pune $(18.52^\circ\text{N}, 73.86^\circ\text{E})$, Inbound weight $0.35$, Fleet $30$ trucks
  - $W_2$: Mumbai–Bhiwandi $(19.08^\circ\text{N}, 72.88^\circ\text{E})$, Inbound weight $0.30$, Fleet $30$ trucks
  - $W_3$: Nashik $(20.00^\circ\text{N}, 73.79^\circ\text{E})$, Inbound weight $0.20$, Fleet $30$ trucks
  - $W_4$: Kolhapur $(16.71^\circ\text{N}, 74.24^\circ\text{E})$, Inbound weight $0.15$, Fleet $30$ trucks
- **25 Stores ($S=25$):**
  - Anchors: Pune, Mumbai, Thane, Nashik, Kolhapur, Satara, Sangli, Solapur, Ahmednagar, Aurangabad, Ichalkaranji, Karad ($\pm 0.15^\circ$ seeded jitter).
  - Size multipliers: Drawn from 25 configured values ($0.5$ to $2.0$).
  - Storage capacity: $18,000\,\text{L} \times \text{size} = 18,000,000\,\text{ml} \times \text{size}$.
- **Lanes ($100$ total):**
  - $\text{km} = 1.3 \times \text{haversine}(w, s)$.
  - Transit time: $1\text{ day if } \text{km} \le 200$; $2\text{ days if } 200 < \text{km} \le 450$.
  - Ineligible if $\text{km} > 450$ (stored with `eligible=0`). Every store has $\ge 2$ eligible warehouses.
- **Truck Specifications:**
  - Capacity: $4,000\,\text{L} = 4,000,000\,\text{ml}$.
  - Transport cost: $\text{Fixed } ₹800 + ₹14/\text{km}$.
  - In integer paise: $\text{lane\_cost}[w,s] = 80,000 + 1,400 \times \text{km}[w,s]$.
  - Homogeneous fleet, 1 destination store per truck per cycle.

### 2.2 SKU Master Catalog (12 SKUs)

| SKU ID | Name | Category | Cost (₹) | Price (₹) | Margin (₹) | Vol (ml) | Shelf Life (d) | Min Life on Arrival | $w$ | $g$ | Base Demand/d | CR | Quantile Target |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `MILK-1L` | Fresh Milk 1L | Dairy | 52 | 60 | 8 | 1,200 | 5 | 3 | 1.0 | 4 | 120 | 0.38 | P70 (floor) |
| `CURD-400G` | Set Curd 400g | Dairy | 28 | 34 | 6 | 500 | 10 | 5 | 1.0 | 2 | 75 | 0.30 | P70 (floor) |
| `BREAD-400G` | White Bread 400g | Bakery | 30 | 40 | 10 | 2,500 | 4 | 2 | 1.0 | 4 | 90 | 0.57 | P70 (floor) |
| `BISC-250` | Marie Biscuit 250g | Snacks | 22 | 30 | 8 | 800 | 180 | 72 | 0.1 | 2 | 105 | 0.86 | P90 |
| `NOODLE-70` | Instant Noodles 70g| Snacks | 11 | 14 | 3 | 400 | 270 | 108 | 0.1 | 2 | 90 | 0.82 | P80 |
| `RICE-5KG` | Basmati Rice 5kg | Staples | 310 | 360 | 50 | 6,500 | 365 | 120 | 0.1 | 4 | 36 | 0.85 | P80 |
| `ATTA-5KG` | Chakki Atta 5kg | Staples | 240 | 275 | 35 | 6,500 | 120 | 48 | 0.1 | 4 | 42 | 0.83 | P80 |
| `OIL-1L` | Sunflower Oil 1L | Staples | 140 | 160 | 20 | 1,100 | 270 | 108 | 0.1 | 4 | 60 | 0.83 | P80 |
| `TEA-250G` | CTC Tea 250g | Beverages | 110 | 130 | 20 | 900 | 365 | 120 | 0.1 | 2 | 54 | 0.75 | P80 (tie $\to$ high) |
| `SOAP-100G` | Bath Soap 100g | Personal | 28 | 36 | 8 | 200 | 730 | 120 | 0.1 | 1 | 48 | 0.71 | P70 |
| `JUICE-1L` | Mixed Fruit Juice 1L| Beverages | 75 | 95 | 20 | 1,100 | 90 | 36 | 0.3 | 1 | 42 | 0.46 | P70 (floor) |
| `CHIPS-90G`| Potato Chips 90g | Snacks | 16 | 20 | 4 | 1,500 | 120 | 48 | 0.1 | 1 | 84 | 0.68 | P70 |

---

## 3. Mathematical & Algorithmic Formulations

### 3.1 Synthetic Demand Generator
- **Daily Mean Formula:**
  $$\mu[d,s,p] = \text{base}[p] \times \text{size}[s] \times \text{weekday}[\text{dow}(d)] \times \text{season}[p,d] \times \text{festival}[d,p] \times \text{promo}[d,s,p] \times \text{trend}[d]$$
- **Components:**
  - $\text{weekday}$: Mon 0.90, Tue 0.90, Wed 0.95, Thu 1.00, Fri 1.10, Sat 1.25, Sun 1.20
  - $\text{season}[p,d] = 1 + A[p] \cdot \sin(2\pi (\text{doy} - 15) / 365)$; $A = 0.25$ for `JUICE-1L`, $0.05$ for others
  - $\text{festival}[d,p]$: 12 festival periods/year. Multiplier $1.5$ for OIL, ATTA, BISC, CHIPS, TEA, JUICE; $1.2$ for others
  - $\text{promo}[d,s,p]$: 2 quarterly 5-day windows. Multiplier $1.35$ on promo days; $0.85$ on post-3 days
  - $\text{trend}[d] = 1 + 0.10 \times d / 730$
- **Negative-Binomial Noise Sampling (Gamma-Poisson Mixture):**
  $$\lambda \sim \text{Gamma}\left(\text{shape} = \frac{1}{\phi},\, \text{scale} = \mu \cdot \phi\right),\quad X \sim \text{Poisson}(\lambda),\quad \text{with } \phi = 0.10$$
  Yields $\mathbb{E}[X] = \mu$ and $\text{Var}(X) = \mu + 0.10 \mu^2$.

### 3.2 Demand Forecasting Module
- **Target:** $Y[t,s,p] = \sum_{k=1}^9 \text{demand}[t+k, s, p]$ (9-day forward cumulative demand).
- **Scale Normalization:** $\text{scale}[t,s,p] = \max\left(s_{28} \times \frac{9}{28},\, 5\right)$, where $s_{28}$ is sum of sales in days $t-27 \dots t$.
- **Models:** 4 LightGBM Boosters for $\alpha \in \{0.5, 0.7, 0.8, 0.9\}$ trained to predict ratio $r = Y/\text{scale}$.
- **21 Leakage-Free Features:**
  - Rolling history: $s_1$, $s_7/\text{scale}$, $s_{14}/\text{scale}$, $s_{28}/\text{scale}$, rolling std $sd_7$, $sd_{28}$, trend ratio, `wd_factor_sum` (weekday factor sum over target 9 days, fitted only on training set), promo count last 28 days.
  - Known future: Promo days in $t+1 \dots t+9$, festival days in $t+1 \dots t+9$, holiday days, days to next festival (capped at 60).
  - Calendar & Static: `dow`, `month`, categorical SKU, categorical Store, category, `size_mult`, `price`, `shelf_life`.
- **Chronological Split:**
  - Train: origins 29–620 (177,600 series-days)
  - Purge: 621–629 (9-day lookahead gap)
  - Validation: 630–663 (10,200 series-days)
  - Purge: 664–672
  - Test: 673–721 (14,700 series-days)
- **Post-Processing Pipeline:**
  1. Denormalize: $\hat{P}_q = \hat{r}_q \times \text{scale}$.
  2. Monotonic sort: enforce $P50 \le P70 \le P80 \le P90$.
  3. Clip at 0 and round up ($\lceil \cdot \rceil$) to integers.
  4. Validation calibration: If empirical coverage deviates $> 0.03$ on validation set, multiply by factor $c_q \in [0.85, 1.20]$.

### 3.3 Newsvendor Critical-Ratio Service-Level Mapping
- **Underage Cost ($C_u$):** $C_u = \text{margin}[p] \times g[p]$ (lost margin + customer goodwill penalty, $g \in \{1, 2, 4\}$).
- **Overage Cost ($C_o$):** $C_o = \text{unit\_cost}[p] \times w[p] + \text{holding\_cost}[p]$
  - Write-off factor $w$: $1.0$ if $\text{shelf\_life} \le 14$; $0.3$ if $\le 90$; else $0.1$.
  - Holding cost: $0.018 \times \text{unit\_cost}$ ($0.2\%$ per day over 9 days).
- **Critical Ratio:**
  $$\text{CR} = \frac{C_u}{C_u + C_o}$$
- **Discretized Mapping:** $\text{CR}$ mapped to nearest in $\{0.7, 0.8, 0.9\}$ with tie-breaker going to higher quantile and a floor of $0.7$.
- **Stock Target:** $\text{target\_q}[s,p] = P_{q(p)}[s,p]$.

### 3.4 CP-SAT Optimization Formulation
- **Scaling:** Cost parameters scaled by $K = 100$ (internal precision in 0.01 paise).
- **Variables:**
  - $x[w,s,p,b] \in \mathbb{Z}_{\ge 0}$: batch quantity shipped.
  - $y[w,s] \in \{0, \dots, \text{fleet}[w]\}$: integer truck count on lane.
  - $u[s,p] \in [0, \text{target\_q}]$: unmet demand units.
  - $e[s,p] \ge 0$: excess units above target.
- **Objective Function:**
  $$\min \sum_{(w,s)} \text{lane\_cost}[w,s] \cdot y[w,s] + \sum_{(s,p)} C_u[p] \cdot u[s,p] + \sum_{(s,p)} C_h[p] \cdot e[s,p] + \sum_{(w,s,p,b)} C_w[b,s,p] \cdot x[w,s,p,b] + \sum \epsilon \cdot \text{rank}[b] \cdot x[w,s,p,b]$$
  where $\epsilon = 1$ (0.01 paise FEFO tie-break), and:
  $$C_w[b,s,p] = \text{round}\left(\text{unit\_cost}[p] \times w[p] \times \pi\right), \quad \pi = \text{clip}\left(1 - \frac{\min(P50_{9d} \times \min(\Lambda, 9)/9,\, \text{target})}{\text{target}},\, 0,\, 1\right) \text{ if } \Lambda \le 18 \text{ else } 0$$
- **Hard Constraints (C1–C9):**
  1. **Batch Stock (C1):** $\sum_s x[w,s,p,b] \le \text{stock}[w,p,b]$
  2. **Coverage (C2):** $\text{pos0}[s,p] + \sum_{w,b} x[w,s,p,b] + u[s,p] \ge \text{target\_q}[s,p]$
  3. **Excess Definition (C3):** $e[s,p] \ge \text{pos0}[s,p] + \sum x - \text{target\_q}[s,p]$
  4. **Truck Volume (C4):** $\sum_{p,b} \text{vol}[p] \cdot x[w,s,p,b] \le \text{truck\_cap} \cdot y[w,s]$ ($4,000,000\,\text{ml}$)
  5. **Fleet Limit (C5):** $\sum_s y[w,s] \le \text{fleet}[w]$ (30 trucks)
  6. **Store Storage Capacity (C6):** $\sum_p \text{vol}[p] \cdot (\text{pos0}[s,p] + \sum x) \le \text{store\_cap}[s]$
  7. **Shelf Life on Arrival (C7):** $x[w,s,p,b] = 0$ if $\Lambda[w,b,s] < \text{min\_life}[p]$
  8. **Sell-Through Cap (C8):** For each short life level $\ell < 9$:
     $$\sum_{(w,b): \Lambda \le \ell} x[w,s,p,b] \le \max\left(0,\, \left\lfloor \text{target\_q}[s,p] \times \frac{\ell}{9} \right\rfloor - \text{pos0\_life}_{\le \ell}[s,p]\right)$$
  9. **Lane Eligibility (C9):** $x = 0$ if $\text{km} > 450$.
- **Warm-Start Incumbent:** Greedy solver hint ranking stores by $C_u \times \text{shortfall}$ and pulling oldest eligible batches from cheapest lanes.
- **Solver Parameters:** 8s timeout, 0.5% relative gap, deterministic mode (1 worker, fixed seed) for tests and backtest; 4 workers for interactive demo. Guaranteed feasible solution via fallback zero plan ($x=0, u=\text{target\_q}$).

### 3.5 FEFO Invariant & Deterministic Repair
- **FEFO Invariant:** Within $(w, p)$, if a newer batch ships to store $s$, every older batch eligible on $(w,s)$ must be fully exhausted, C7/C9 ineligible, or C8-blocked (hitting short-life sell-through cap).
- **Deterministic Repair:** If violated, iteratively swap units from newer to older eligible batches without altering total quantity per lane.

---

## 4. Complete System Architecture & Module Boundaries

### 4.1 Layered Architecture & Import Governance
```
Layer 4: API Layer         vitaraniq/api/       (FastAPI routes, Pydantic v2 schemas, error handlers)
Layer 3: Orchestration     vitaraniq/services/  (PlanService, ForecastService, BacktestService, WhatIfService, DataService)
Layer 2: Domain Logic      vitaraniq/           (data/, forecast/, service_level/, optimize/, check/, explain/, sim/, reports/)
Layer 1: Infrastructure    vitaraniq/core/, db/ (config, logging, units, ids, jobs runner, SQLite repositories)
```
- **Strict Rule:** `check/` MUST NOT import anything from `optimize/`, `forecast/`, or `sim/`.
- Domain modules are pure logic functions taking dataclasses and returning dataclasses. Only `services/` and `db/` perform database I/O.

### 4.2 Core Frozen Data Contracts
1. `Params`: Loaded from `config/params.yaml` (single source of truth for constants).
2. `Snapshot`: In-memory state holding arrays for warehouses, stores, SKUs, lanes, active batches, store on-hand, and in-transit.
3. `ForecastTable`: 300 rows $\times$ (P50, P70, P80, P90) 9-day demand integers + cold-start flags.
4. `Targets`: Store–SKU targets: `target_q`, `p50_9d`, `chosen_quantile`, `critical_ratio`.
5. `RawPlan`: Solver output: shipment lines $(w, s, p, b, qty)$, trucks on lane, unmet demand, solver metrics.
6. `PlanLine`: User-facing shipment: SKU, from, to, batch, expiry, quantity, trucks, allocated line cost (₹), priority, reason codes.
7. `CheckResult`: `status` (`PASS`/`FAIL`) + list of constraint violations.
8. `SimResult`: Daily and aggregated simulation records: units demanded, sold, unmet, delivered, wastage ₹, transport ₹, truck fill, KPIs.

### 4.3 Concurrency Architecture
- **API Requests:** Async FastAPI running under Uvicorn.
- **Fast Solves (Interactive Plan / What-If):** In-process `ThreadPoolExecutor(2)` sharing in-memory `ModelBundle` and `Snapshot` cache.
- **Long-Running Jobs (Training & 40-Run Backtests):** `ProcessPoolExecutor(4)` spawning isolated worker processes. Job status persisted in `jobs` table with polling every 2s from the frontend.
- **SQLite Database:** WAL mode, `busy_timeout = 5000ms`, short atomic write transactions.

---

## 5. Simulation Engine & Policy Comparison

### 5.1 Simulation Day Loop (Days 703 to 730 = 28 Days)
- **Re-planning Days:** Starts of days 703, 710, 717, 724.
- **Sequential Daily Events:**
  1. Scheduled inbound arrives (normal: 105% mean demand, scarcity: 80% mean demand) + in-transit arrivals added to stock.
  2. Realized demand from `window_demand[seed]` is served FEFO from store stock. Unmet demand is recorded and lost (no backorders).
  3. Expired stock at stores and warehouses is written off at unit cost.
- **Stock Conservation Invariant:**
  $$\text{Initial Stock} + \text{Inbound} + \text{Delivered} = \text{Sold} + \text{Expired} + \text{Final Stock}$$

### 5.2 Four Policies Under Identical Constraints
1. **Policy B1 (Moving Average Proportional):**
   $\text{need} = \max(0, \text{round}(9 \times m_{28}) - \text{position})$. Sourced from nearest eligible warehouse FEFO. Pro-rata allocation under scarcity.
2. **Policy B2 (Reorder-Up-To with Buffer):**
   $\text{need} = \max(0, \text{round}(1.25 \times 9 \times m_{28}) - \text{position})$. Same sourcing rules.
3. **Policy O-MA (Optimizer with Static Demand):**
   Same CP-SAT solver, but driven by 7-day MA: $P50_{9d} = 9 \times \text{MA}_7$, $\text{target\_q} = \lceil 1.25 \times 9 \times \text{MA}_7 \rceil$.
4. **Policy VitaranIQ (Full System):**
   LightGBM quantile forecasts ($P50\dots P90$) + Critical-Ratio service level mapping + CP-SAT solver + FEFO repair.

### 5.3 KPI Definitions (`v_sim_kpis`)
- **Fill Rate:** $\frac{\text{units sold}}{\text{units demanded}}$ (Target $\ge 95\%$, Floor $\ge 90\%$)
- **Stockout Rate:** $\frac{\text{store-days with unmet demand}}{\text{total store-days}}$ (Target $-25\%$ vs baseline, Floor $-10\%$)
- **Wastage (₹):** $\sum \text{expired units} \times \text{unit cost}$ (Target $-25\%$ vs baseline, Floor $-10\%$)
- **Cost per Unit Delivered (₹):** $\frac{\text{transport paise}}{\text{units delivered}}$ (Target $\le \text{baseline}$)
- **Average Truck Fill:** $\frac{\text{loaded volume}}{\text{total truck capacity}}$ (Target $\ge 80\%$, Floor $\ge 70\%$)
- **AI Contribution (Ablation):** $\frac{\text{Total Cost}(O\text{-}MA) - \text{Total Cost}(\text{VitaranIQ})}{\text{Total Cost}(O\text{-}MA)} \ge 5\%$
- **Scarcity Margin-Weighted Fill Rate:** $\frac{\sum \text{margin} \times \text{units sold}}{\sum \text{margin} \times \text{units demanded}} \ge +5\%\text{ points vs } B_1$

---

## 6. Explainability & Validation Engines

### 6.1 Independent Plan-Checker (7 Hard Checks)
1. Non-negative integer quantities on every line.
2. Batch availability: Shipped quantity per batch $\le$ warehouse batch stock.
3. Truck constraints: $\lceil \text{loaded\_ml} / 4,000,000 \rceil \le \text{trucks\_on\_lane}$, and $\sum_s \text{trucks} \le \text{fleet}[w]$.
4. Store capacity: Total volume after delivery $\le \text{store\_cap}[s]$.
5. Shelf life on arrival: $\text{expiry} - (\text{as\_of} + \text{transit}) \ge \text{min\_life}[p]$.
6. Lane eligibility: Distance $\le 450\,\text{km}$ and eligible flag $=1$.
7. FEFO invariant: No newer batch shipped while an eligible, unblocked older batch has remaining stock.

### 6.2 Rule-Based Reason Codes & Evidential Triggers

| Code | Exact Trigger Condition | Numeric Evidence Payload |
|---|---|---|
| `LOW_COVER` | $\text{cover\_days} < 3$ before shipment | `cover_days`, `p50_9d`, `selected_quantile_val`, `onhand`, `intransit` |
| `EXPIRY_FIRST` | Batch is earliest expiring eligible batch with stock | `batch_id`, `expires_in_days_on_arrival` |
| `LOWEST_COST_SOURCE` | Warehouse has minimum $₹/\text{L}$ among eligible sources with stock | `lane_cost_per_litre`, alternative warehouse costs |
| `CAPACITY_LIMITED` | Truck fill $\ge 95\%$ or Store volume fill $\ge 95\%$ | `truck_fill_pct`, `store_use_pct` |
| `SCARCE_PRIORITY` | Network unmet demand $\sum u > 0$ and line delivers $\ge 1$ | `network_unmet_units`, `margin_at_risk_inr` |
| `REPLENISH_TO_TARGET` | Default fallback when target is replenished | `target_q`, `position_before`, `position_after` |
| `NEXT_BEST` (P1) | Counterfactual re-solve with alternative warehouse | `alt_warehouse`, `delta_cost_inr` |

---

## 7. Database Architecture & Schema Catalogue

- **Engine:** SQLite $\ge 3.37$ (Enforcing `STRICT` tables and `WITHOUT ROWID` where applicable).
- **Core Entities (24 Tables + 1 View):**
  - **Master & Input:** `datasets`, `warehouses`, `stores`, `products`, `lanes`, `calendar`, `promo_windows`, `sales_daily` (219k rows), `window_demand` (42k rows), `batches`, `inbound_schedule`, `store_stock`, `in_transit`.
  - **Models & Forecasts:** `models`, `forecast_metrics`, `forecast_eval` (14.7k rows).
  - **Planning & Decisions:** `plans`, `plan_lines`, `plan_line_reasons`, `plan_lanes`, `plan_unmet`, `plan_targets`, `plan_deltas`, `counterfactuals`.
  - **Simulation & Jobs:** `jobs`, `backtest_runs`, `sim_results`, `sim_daily`, `sim_plan_checks`, `v_sim_kpis` (SQL View).
- **Canonical Dataset Hash:** SHA-256 of sorted canonical export ensures 100% deterministic reproducibility.

---

## 8. Frontend User Experience & Visual Workflows

### 8.1 Key Pages & Views
1. **Executive Dashboard:**
   - Real-time KPI Cards (Fill Rate, Stockout Rate, Wastage ₹, Transport ₹, Truck Fill).
   - Interactive Risk Heatmap (25 Stores $\times$ 12 SKUs) highlighting Stockout Risk ($r = \text{clip}(1 - \text{position}/P90_{9d}, 0, 1)$) and Expiry Risk ($x = \text{clip}((\text{expiring}_{7d} - P50_{9d} \times 7/9)/\text{onhand}, 0, 1)$).
2. **Forecast Studio:**
   - Store & SKU selector with interactive Recharts actual vs. $P50$ forecast line and $P70-P90$ quantile uncertainty bands.
   - WAPE, Bias, and Pinball loss diagnostic breakdown.
3. **Dispatch Plan Generator:**
   - One-click *Generate Plan* trigger with live stage timers ($\le 15\text{s}$ budget).
   - Filterable, sortable recommendation table with SKU, source warehouse, destination store, batch, quantity, truck allocation, ₹ cost, priority tags, and reason badges.
   - CSV & FEFO Pick List export.
4. **Explainability Drawer:**
   - Sliding evidence panel displaying exact mathematical calculations and lane cost comparisons behind any chosen shipment line.
5. **Backtest & Proof Engine:**
   - Side-by-side 4-policy comparison matrix (B1, B2, O-MA, VitaranIQ).
   - Day-by-day cumulative loss & wastage tracking charts.
   - Ablation gauge highlighting the pure AI contribution ($+5\%$ cost savings over O-MA).
6. **What-If Scenario Simulator:**
   - Warehouse outage disruption testing (zeroing warehouse stock and re-optimizing in $<20\text{s}$) with delta impact table.
   - P1 Demand Spikes and Fuel Price sensitivity sliders.
7. **Transparent Assumptions & Data Card:**
   - Live rendering of all model parameters, cost constants, and verified mathematical rules.

---

## 9. Verification Gates & Execution Roadmap

| Milestone | Gate Criteria | Verification Method |
|---|---|---|
| **Hour 6** | Seeded Data Generator produces 219,000 rows; SHA-256 hash match; V1–V8 validation passes | `pytest tests/test_generator.py` |
| **Hour 16** | 4 Quantile LightGBM models trained; test WAPE $\le 20\%$; beating MA9 by $\ge 15\%$ | `pytest tests/test_forecast.py` |
| **Hour 24** | End-to-end solve on full network (4 $\times$ 25 $\times$ 12) completes in $\le 15\text{s}$; plan-checker reports 0 violations across 20 seeds | `pytest tests/test_optimizer.py` |
| **Hour 30** | Backtest simulator runs all 4 policies on seed 42; stock conservation holds exactly | `pytest tests/test_simulator.py` |
| **Hour 48** | Full UI, CSV export, warehouse outage what-if, and Dockerized demo ready for presentation | End-to-End Demo Script |

---
*Memory Map generated and indexed for VitaranIQ engine construction.*
