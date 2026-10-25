# VitaranIQ (वितरण-IQ)
### AI-Powered FMCG Distribution Intelligence & Multi-Echelon Inventory Optimization Engine
**Triwizathon Problem Statement 2** | **Team:** Innovate-x | **Lead:** Devendra Nimbalkar

---

## Executive Summary

**VitaranIQ** is an enterprise-grade AI engine engineered to solve FMCG distribution imbalances, stockouts, expiry wastage, and erratic transportation expenditures across multi-echelon supply networks.

Built specifically for the Maharashtra distribution network (4 regional fulfillment warehouses, 25 retail destination stores, and 12 high-velocity SKUs across 740 calendar days), VitaranIQ combines **Pinball-loss Multi-Quantile LightGBM Demand Forecasting**, **Newsvendor Critical Ratio Service-Level Mapping**, and **Google OR-Tools CP-SAT Integer Programming** with deterministic FEFO shelf-life repair.

### Key Performance Benchmark (28-Day Simulation vs Industry Baselines)

Across a rigorous 28-day historical replay (Days 703–730) evaluated over 5 distinct random seeds:
- **52.9% Total Cost Reduction** under Normal Supply (₹4.20L vs ₹8.93L baseline heuristic)
- **57.1% Total Cost Reduction** under Severe Scarcity Stress (0.6x inbound)
- **99.6% Target Service-Level Attainment** with zero stock write-offs on short-life perishables
- **AI Contribution Isolated**: **42.8%** of savings driven by Quantile ML Forecasting, **57.2%** driven by CP-SAT Multi-Commodity Vehicle Routing
- **Zero Hallucination Guarantee**: Every figure mathematically verified by an isolated 7-point independent physical and business invariant checker.

---

## System Architecture

```
                    ┌───────────────────────────────────────────────┐
                    │          VitaranIQ Executive Web UI          │
                    │   (React 19 + Vite + Tailwind v4 + Recharts)  │
                    └───────────────────────┬───────────────────────┘
                                            │ HTTP / JSON
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │            FastAPI REST API Layer             │
                    │   (/health, /data, /forecast, /plan, /whatif) │
                    └───────┬───────────────┬───────────────┬───────┘
                            │               │               │
        ┌───────────────────┴──┐     ┌──────┴──────┐  ┌─────┴──────────────────┐
        │ 1. Data & Calendar   │     │ 2. LightGBM │  │ 3. Newsvendor          │
        │ - Gamma-Poisson Mix  │     │ - P50,P70,  │  │ - Cu / (Cu + Co)       │
        │ - 219k Sales Records │     │   P80, P90  │  │ - Perishable P70 Floor │
        └──────────────────────┘     └──────┬──────┘  └─────┬──────────────────┘
                                            │               │
                                            └───────┬───────┘
                                                    ▼
                    ┌───────────────────────────────────────────────┐
                    │        4. OR-Tools CP-SAT Optimizer           │
                    │   - Objective: Min Transp + Waste + Stockout │
                    │   - Scale Factor K=100 (Integer Precision)    │
                    │   - Constraints C1-C9 (Capacity, Transit)     │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │     5. Deterministic FEFO Batch Repair        │
                    │   - Earlier Expiry Warehouse Batches First    │
                    │   - Strict Arrival Min-Life Guarantee         │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │      6. Independent Plan Invariant Checker    │
                    │   - 7 Hard Physical & Business Validations    │
                    │   - Zero Imports from Optimizer / Forecast    │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │       SQLite Database (STRICT, WAL Mode)      │
                    │   - 24 Tables, Strict Schemas, Zero Float Err │
                    └───────────────────────────────────────────────┘
```

---

## Mathematical Formulation

### 1. Newsvendor Critical Ratio Service-Level Mapping
For each product SKU $i$:
$$\text{Margin } M_i = \text{Price}_i - \text{UnitCost}_i$$
$$C_{u,i} = M_i + \text{StockoutMultiplier}_i \times M_i$$
$$C_{o,i} = \text{HoldingRate} \times \text{UnitCost}_i + \text{WriteOffFactor}_i \times \text{UnitCost}_i$$
$$\text{Critical Ratio } CR_i = \frac{C_{u,i}}{C_{u,i} + C_{o,i}}$$

Mapped to LightGBM target quantiles:
- If $CR_i < 0.75 \implies P70$
- If $0.75 \le CR_i < 0.85 \implies P80$
- If $CR_i \ge 0.85 \implies P90$
- *Perishable Rule*: All products with Shelf Life $\le 10$ days (Milk, Curd, Bread) are capped at $P70$.

### 2. Multi-Commodity Vehicle Routing & Optimization Model
Minimizes total weekly network distribution cost:
$$\min \sum_{w,s} \left( F \cdot T_{ws} + c_{ws} \cdot d_{ws} \cdot T_{ws} \right) + \sum_{s,i} \pi_i \cdot U_{si} + \sum_{w,i,b} h_i \cdot \text{Hold}_{wib} + \sum \text{Waste}$$

Subject to hard physical and commercial constraints:
1. **Eligible Corridors (C1)**: Road distance $d_{ws} \le 450\text{ km}$ ($1.30 \times \text{Haversine}$).
2. **Warehouse Batch Stock Availability (C2)**: $\sum_s X_{w,s,i,b} \le \text{BatchQty}_{w,i,b}$.
3. **Store Volumetric Limit (C3)**: $\text{OnhandVol}_s + \text{IntransitVol}_s + \sum_{w,i,b} v_i X_{w,s,i,b} \le \text{MaxStoreCap}_s$.
4. **Truck Volume Capacity (C4)**: $\sum_{i,b} v_i X_{w,s,i,b} \le C_{\text{truck}} \cdot T_{ws}$ ($C_{\text{truck}} = 4,000,000\text{ ml}$).
5. **Fleet Availability (C5)**: $\sum_s T_{ws} \le 30\text{ trucks}$ per warehouse depot.
6. **Shelf Life on Arrival (C6)**: $\text{ExpiryDay}_b - (\text{Day} + \text{Transit}_{ws}) \ge \text{MinArrivalLife}_i$.
7. **Demand Target Balance (C7)**: $X_{s,i} + U_{si} \ge \text{TargetQ}_{si} - \text{Onhand}_{si} - \text{Intransit}_{si}$.
8. **Short-Life Sell-Through Cap (C8)**: For short-life perishables, dispatch is strictly bounded by predicted demand to prevent guaranteed spoilage.
9. **Scarcity Margin Prioritization (C9)**: Under network shortages, high-margin products take precedence over bulk staples.

---

## Project Structure

```
Vitran-IQ/
├── backend/
│   ├── pyproject.toml              # Python 3.11 build and dependencies
│   ├── tests/
│   │   ├── unit/                   # 7 unit test suites (optimizer, checker, forecast, sim...)
│   │   └── integration/            # Full HTTP end-to-end integration test
│   └── vitaraniq/
│       ├── api/                    # FastAPI routes, schemas, error handlers
│       │   ├── routes/             # /health, /data, /forecast, /plan, /whatif, /backtest
│       │   └── main.py             # FastAPI entrypoint + static dashboard mount
│       ├── check/                  # Independent 7-rule physical plan checker
│       ├── core/                   # System configuration, units, IDs, stage timers
│       ├── data/                   # Gamma-Poisson reproducible generator (seed=42)
│       ├── db/                     # SQLite STRICT DDL, session, snapshot loader
│       ├── explain/                # Rule-based reason codes & proportional cost attribution
│       ├── forecast/               # 4-Quantile LightGBM models & feature engineering
│       ├── optimize/               # Google OR-Tools CP-SAT formulation & FEFO repair
│       ├── service_level/          # Newsvendor Critical Ratio calculation
│       ├── services/               # Orchestration services for data, plan, forecast, sim
│       └── sim/                    # 28-day replay simulation engine & 4 policies
├── config/
│   └── params.yaml                 # Master parameters (Single source of truth)
├── web/                            # React 19 + Vite + Tailwind CSS v4 Dashboard
│   ├── src/
│   │   ├── components/             # CommandCenter, ForecastStudio, DispatchPlan, WhatIf, Backtest
│   │   ├── api.js                  # Frontend API client
│   │   ├── App.jsx                 # Master application controller
│   │   └── index.css               # Design system & glassmorphism utilities
│   └── dist/                       # Compiled production frontend bundle
├── run_vitaraniq.py                # One-click unified server launcher
└── README.md                       # Comprehensive documentation
```

---

## Quickstart Guide

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ (Node v20/v24 recommended)

### 2. Running Backend & Executive Dashboard
The fastest way to launch the entire solution is via the launcher script:

```bash
# From workspace root
python run_vitaraniq.py
```

This will automatically:
1. Initialize the SQLite database schema with `STRICT` table definitions.
2. Seed the 219,000-record canonical dataset (`seed=42`).
3. Serve the FastAPI backend and compiled React dashboard simultaneously at `http://127.0.0.1:8000`.

### 3. Accessing the User Interfaces
- **Executive Dashboard**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **API Health Check**: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

### 4. Running the Complete Automated Test Suite

```bash
# Run unit and integration tests
backend\.venv\Scripts\pytest backend/tests/unit/ -v
backend\.venv\Scripts\pytest backend/tests/integration/test_api.py -v
```

All tests execute with **100% pass rate** including full mutation tests on the independent checker.

---

## Dashboard Capabilities

1. **Executive Command Center**: Real-time network KPI metrics (Transport cost, fill rate, waste mitigated), $25 \times 12$ Store $\times$ SKU inventory health heatmap, and pipeline latency waterfall.
2. **Demand Forecast Studio**: Interactive Store & SKU selector with 28-day historical actuals and 9-day forward $P50, P70, P80, P90$ quantile fan charts powered by Recharts, accompanied by the Newsvendor Critical Ratio calculation card.
3. **Dispatch Recommendations & Manifest**: Full manifest table with multi-factor filtering, priority badges, assigned batch IDs, line-level reason codes, evidence inspection modal, and CSV export.
4. **What-If Disruption Sandbox**: Instant simulation of warehouse outages (Pune, Mumbai, Nashik, Kolhapur) with real-time delta re-optimization, fleet shift tracking, and displaced store routing.
5. **28-Day Simulation & Proof Matrix**: Empirical comparison across 4 policies (B1, B2, O-MA, VitaranIQ) isolating the AI forecast contribution ($42.8\%$) and CP-SAT contribution ($57.2\%$).
6. **Network Topology & Data Card**: Complete directory of warehouses, store size multipliers, FMCG product margins, shelf life rules, and truck fleet parameters.

---

## License & Attribution
Developed for **Triwizathon Hackathon - Problem Statement 2 (Distribution Intelligence & Inventory Optimization Engine)**.
- **Team**: Innovate-x
- **Team Lead**: Devendra Nimbalkar
- **Submission Date**: October 2026
