# VitaranIQ — Database Schema

**Team:** Innovate-x · **Project:** VitaranIQ · **Document:** Database Schema · **Version:** 1.0 · **Date:** 2026-10-24
**Derived from:** SRS v1.0 (§3.5, FR-DAT, FR-OPT-10, FR-SIM-07) and System Architecture v1.0 (§7).
**Engine:** SQLite ≥ 3.37 (needed for `STRICT` tables; checked at start-up), WAL mode, accessed through SQLAlchemy.
**Next document:** AI/ML & Optimization Design.

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Money | Integer **paise** (₹1 = 100). Column suffix `_paise`. |
| Volume | Integer **millilitres**. Column suffix `_ml`. |
| Quantities | Integer units. Never negative. |
| Time | Day index `day` (day 1 = 2024-11-01) as INTEGER. ISO date text only in `calendar`. Timestamps are UTC ISO-8601 text. |
| Identifiers | Readable text codes: `W1…W4`, `S01…S25`, SKU codes such as `BISC-250`. Plan, run and job ids are text with a prefix (`p_`, `r_`, `j_`). |
| Multi-dataset scoping | Every dataset-scoped table carries `dataset_id`. Deleting a dataset removes everything that depends on it (`ON DELETE CASCADE`). SRS FR-DAT-08 allows one active dataset. |
| Enumerations | Stored as TEXT with `CHECK … IN (…)` (§4). |
| JSON | Stored as TEXT with `CHECK (json_valid(col))`. Used only for evidence, parameters and timings, never for data the optimizer reads. |
| Strictness | All tables are `STRICT`. Allowed types: `INTEGER`, `REAL`, `TEXT`. |
| Connection settings | `PRAGMA foreign_keys=ON; journal_mode=WAL; synchronous=NORMAL; busy_timeout=5000;` applied on every connection, including worker processes. |

---

## 2. Entity-Relationship Overview

```
                               datasets
                                  │ 1
      ┌──────────────┬────────────┼──────────────┬─────────────┬──────────────┐
      ▼ n            ▼ n          ▼ n            ▼ n           ▼ n            ▼ n
  warehouses       stores      products       calendar      models        backtest_runs
      │  │           │  │         │  │                        │ │               │ n
      │  └────┬──────┘  │         │  │                        │ └─ forecast_    ▼
      │       ▼ n       │         │  │                        │    metrics   sim_results ─ sim_daily
      │     lanes       │         │  │                        │    forecast_  sim_plan_checks
      │                 │         │  │                        │    eval
      │      promo_windows ◄──────┤  │                        │
      │                 │         │  │                        ▼ n
      │   sales_daily ◄─┴─────────┘  │                     plans ──┬─ plan_lines ── plan_line_reasons
      │   window_demand              │                         │   ├─ plan_lanes
      ├─ batches ◄───────────────────┤                         │   ├─ plan_unmet
      ├─ inbound_schedule ◄──────────┤                         │   ├─ plan_targets
      │                              │                         │   ├─ counterfactuals (P1)
      │   store_stock / in_transit ◄─┘ (stores × products)     │   └─ plan_deltas (what-if)
                                                               ▼
                                                             jobs (independent)
```

Three groups:
1. **Master and generated data:** `datasets, warehouses, stores, products, lanes, calendar, promo_windows, sales_daily, window_demand, batches, inbound_schedule, store_stock, in_transit`.
2. **Models and forecasts:** `models, forecast_metrics, forecast_eval`.
3. **Decisions and evidence:** `plans` (+ children), `backtest_runs` (+ children), `jobs`.

---

## 3. Table Catalogue

| Table | Purpose | Primary key | Approx. rows (reference scale) | SRS |
|---|---|---|---|---|
| `schema_version` | Applied migrations | `version` | 1–10 | — |
| `datasets` | Dataset header, seed, hash, active flag | `dataset_id` | 1 | FR-DAT-01, 08 |
| `warehouses` | 4 warehouses | `(dataset_id, warehouse_id)` | 4 | FR-DAT-02 |
| `stores` | 25 stores with size, capacity, region | `(dataset_id, store_id)` | 25 | FR-DAT-02 |
| `products` | 12 SKUs with cost, price, volume, shelf life, service-level constants | `(dataset_id, sku_id)` | 12 | FR-DAT-02, BR-01…04 |
| `lanes` | Warehouse–store distance and lead time | `(dataset_id, warehouse_id, store_id)` | 100 | FR-DAT-05 |
| `calendar` | Day-level holiday and festival flags, days 1–740 | `(dataset_id, day)` | 740 | FR-DAT-02 |
| `promo_windows` | Known-future promotion windows per store–SKU | `(dataset_id, store_id, sku_id, start_day)` | ≈ 4,800 | App. B |
| `sales_daily` | History: daily units per store–SKU, days 1–730 | `(dataset_id, store_id, sku_id, day)` | 219,000 | FR-DAT-02, 03 |
| `window_demand` | Per-seed demand for backtest days 703–730 | `(dataset_id, seed, store_id, sku_id, day)` | 42,000 (5 seeds) | FR-SIM-06 |
| `batches` | Warehouse stock by batch at the snapshot day | `(dataset_id, batch_id)` | ≈ 150 | FR-DAT-04 |
| `inbound_schedule` | Scheduled warehouse inbound per supply scenario | `(dataset_id, supply_scenario, day, warehouse_id, sku_id)` | 384 | App. C |
| `store_stock` | Store on-hand at the snapshot day | `(dataset_id, as_of_day, store_id, sku_id)` | 300 | FR-DAT-04 |
| `in_transit` | Stock shipped but not yet arrived | `(dataset_id, as_of_day, store_id, sku_id, arrival_day)` | 0 initially | FR-OPT-01 |
| `models` | Trained model versions | `model_version` | few | FR-FCT-07 |
| `forecast_metrics` | WAPE, bias, coverage, pinball by scope | `(model_version, scope, scope_id)` | ≈ 40 per model | FR-FCT-05 |
| `forecast_eval` | Forecast vs actual 9-day sums per test origin | `(model_version, origin_day, store_id, sku_id)` | 14,700 per model | FR-FCT-08 |
| `plans` | Plan header: status, timings, scenario | `plan_id` | tens | FR-OPT-10 |
| `plan_lines` | Shipment lines | `(plan_id, line_no)` | ≤ 1,000 per plan | FR-REC-01 |
| `plan_line_reasons` | Reason codes and evidence per line | `(plan_id, line_no, code)` | ≤ 3,000 per plan | FR-EXP-01 |
| `plan_lanes` | Trucks, loaded volume and cost per lane | `(plan_id, warehouse_id, store_id)` | ≤ 100 per plan | FR-REC-04 |
| `plan_unmet` | Unmet demand against target | `(plan_id, store_id, sku_id)` | ≤ 300 per plan | FR-OPT-09 |
| `plan_targets` | Forecast, service level and target per store–SKU | `(plan_id, store_id, sku_id)` | 300 per plan | FR-EXP-03 |
| `plan_deltas` | What-if difference versus base plan | `plan_id` | few | FR-WIF-01 |
| `counterfactuals` | `NEXT_BEST` results (P1) | `(plan_id, line_no)` | ≤ 20 per plan | FR-EXP-04 |
| `backtest_runs` | Backtest header | `run_id` | few | FR-SIM-07 |
| `sim_results` | Raw KPI sums per policy, seed, scenario | `(run_id, policy, seed, supply_scenario)` | 40 per run | FR-SIM-07 |
| `sim_daily` | Day-by-day series for charts | `(run_id, policy, seed, supply_scenario, day)` | 1,120 per run | FR-UI-05 |
| `sim_plan_checks` | Checker result for every simulated plan | `(run_id, policy, seed, supply_scenario, plan_day)` | 160 per run | FR-SIM-05 |
| `jobs` | Background jobs | `job_id` | tens | NFR-REL-03 |

Total size at the reference scale: about 20–40 MB. Largest tables: `sales_daily` and its index, then `window_demand` and `forecast_eval`.

---

## 4. Enumerations

| Column(s) | Allowed values |
|---|---|
| `supply_scenario` | `normal`, `scarcity` |
| `priority` | `URGENT`, `HIGH`, `NORMAL` |
| `solver_status` | `OPTIMAL`, `FEASIBLE`, `FALLBACK_ZERO` |
| `checker_status` | `PASS`, `FAIL` |
| `scenario_type` | `NONE`, `WAREHOUSE_OUTAGE`, `DEMAND_SPIKE`, `FUEL_PRICE` |
| `reason code` | `LOW_COVER`, `EXPIRY_FIRST`, `LOWEST_COST_SOURCE`, `CAPACITY_LIMITED`, `SCARCE_PRIORITY`, `REPLENISH_TO_TARGET`, `NEXT_BEST` |
| `policy` | `B1`, `B2`, `O_MA`, `VITARANIQ` |
| `chosen_quantile` | `0.7`, `0.8`, `0.9` (stored as REAL) |
| `job type` | `TRAIN`, `BACKTEST`, `COUNTERFACTUAL` |
| `job status` | `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED` |
| `metrics scope` | `overall`, `sku`, `store` |

---

## 5. DDL (authoritative)

Create tables in the order shown (parents first). The Alembic baseline `0001_initial` must equal this script.

```sql
PRAGMA foreign_keys = ON;

-- ───────────── meta ─────────────
CREATE TABLE schema_version (
  version     INTEGER PRIMARY KEY,
  description TEXT NOT NULL,
  applied_at  TEXT NOT NULL
) STRICT;

CREATE TABLE datasets (
  dataset_id    TEXT PRIMARY KEY,
  seed          INTEGER NOT NULL,
  dataset_hash  TEXT NOT NULL,
  params_hash   TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  n_warehouses  INTEGER NOT NULL,
  n_stores      INTEGER NOT NULL,
  n_skus        INTEGER NOT NULL,
  n_sales_rows  INTEGER NOT NULL
) STRICT;
CREATE UNIQUE INDEX ux_datasets_active ON datasets(is_active) WHERE is_active = 1;

-- ───────────── master data ─────────────
CREATE TABLE warehouses (
  dataset_id       TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  warehouse_id     TEXT NOT NULL,
  name             TEXT NOT NULL,
  lat              REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon              REAL NOT NULL CHECK (lon BETWEEN -180 AND 180),
  fleet            INTEGER NOT NULL CHECK (fleet >= 0),
  inbound_weight   REAL NOT NULL CHECK (inbound_weight >= 0 AND inbound_weight <= 1),
  PRIMARY KEY (dataset_id, warehouse_id)
) STRICT;

CREATE TABLE stores (
  dataset_id      TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  store_id        TEXT NOT NULL,
  name            TEXT NOT NULL,
  city            TEXT NOT NULL,
  region          TEXT NOT NULL,                    -- used by the regional demand-spike what-if (P1)
  lat             REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon             REAL NOT NULL CHECK (lon BETWEEN -180 AND 180),
  size_mult       REAL NOT NULL CHECK (size_mult > 0),
  storage_cap_ml  INTEGER NOT NULL CHECK (storage_cap_ml > 0),
  PRIMARY KEY (dataset_id, store_id)
) STRICT;

CREATE TABLE products (
  dataset_id         TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  sku_id             TEXT NOT NULL,
  name               TEXT NOT NULL,
  category           TEXT NOT NULL,
  unit_cost_paise    INTEGER NOT NULL CHECK (unit_cost_paise > 0),
  price_paise        INTEGER NOT NULL,
  volume_ml          INTEGER NOT NULL CHECK (volume_ml > 0),
  shelf_life_days    INTEGER NOT NULL CHECK (shelf_life_days > 0),
  min_life_days      INTEGER NOT NULL CHECK (min_life_days >= 0),
  write_off_factor   REAL NOT NULL CHECK (write_off_factor BETWEEN 0 AND 1),   -- w, BR-02
  stockout_mult      INTEGER NOT NULL CHECK (stockout_mult >= 1),              -- g
  base_units_per_day REAL NOT NULL CHECK (base_units_per_day > 0),
  margin_paise       INTEGER GENERATED ALWAYS AS (price_paise - unit_cost_paise) VIRTUAL,
  PRIMARY KEY (dataset_id, sku_id),
  CHECK (price_paise > unit_cost_paise),                                       -- validation V5
  CHECK (min_life_days <= shelf_life_days)
) STRICT;

CREATE TABLE lanes (
  dataset_id    TEXT NOT NULL,
  warehouse_id  TEXT NOT NULL,
  store_id      TEXT NOT NULL,
  km            REAL NOT NULL CHECK (km > 0),                                  -- validation V3
  transit_days  INTEGER NOT NULL CHECK (transit_days IN (1,2)),
  eligible      INTEGER NOT NULL CHECK (eligible IN (0,1)),                    -- 0 when km > 450
  PRIMARY KEY (dataset_id, warehouse_id, store_id),
  FOREIGN KEY (dataset_id, warehouse_id) REFERENCES warehouses(dataset_id, warehouse_id) ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, store_id)     REFERENCES stores(dataset_id, store_id)         ON DELETE CASCADE
) STRICT;
```

Note on `lanes`: lanes above 450 km are stored with `eligible = 0` and `transit_days = 2`, so the table always has 100 rows. Only `eligible = 1` lanes are used by the optimizer, the baselines and the checker (FR-DAT-05, C9).

```sql
CREATE TABLE calendar (
  dataset_id     TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  day            INTEGER NOT NULL CHECK (day BETWEEN 1 AND 740),
  date           TEXT NOT NULL,
  dow            INTEGER NOT NULL CHECK (dow BETWEEN 0 AND 6),                 -- Monday = 0
  month          INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  is_holiday     INTEGER NOT NULL CHECK (is_holiday IN (0,1)),
  is_festival    INTEGER NOT NULL CHECK (is_festival IN (0,1)),
  festival_name  TEXT,
  PRIMARY KEY (dataset_id, day)
) STRICT;

CREATE TABLE promo_windows (
  dataset_id  TEXT NOT NULL,
  store_id    TEXT NOT NULL,
  sku_id      TEXT NOT NULL,
  start_day   INTEGER NOT NULL,
  end_day     INTEGER NOT NULL,
  PRIMARY KEY (dataset_id, store_id, sku_id, start_day),
  CHECK (start_day BETWEEN 1 AND 740 AND end_day BETWEEN start_day AND 740),
  FOREIGN KEY (dataset_id, store_id) REFERENCES stores(dataset_id, store_id)   ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)   REFERENCES products(dataset_id, sku_id)   ON DELETE CASCADE
) STRICT;

-- ───────────── history and per-seed demand ─────────────
CREATE TABLE sales_daily (
  dataset_id  TEXT NOT NULL,
  store_id    TEXT NOT NULL,
  sku_id      TEXT NOT NULL,
  day         INTEGER NOT NULL CHECK (day BETWEEN 1 AND 730),
  units       INTEGER NOT NULL CHECK (units >= 0),                             -- validation V6
  promo_flag  INTEGER NOT NULL DEFAULT 0 CHECK (promo_flag IN (0,1)),
  PRIMARY KEY (dataset_id, store_id, sku_id, day),                             -- V7 (no duplicates)
  FOREIGN KEY (dataset_id, store_id) REFERENCES stores(dataset_id, store_id)   ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)   REFERENCES products(dataset_id, sku_id)   ON DELETE CASCADE
) STRICT, WITHOUT ROWID;
CREATE INDEX ix_sales_day ON sales_daily(dataset_id, day);

CREATE TABLE window_demand (
  dataset_id  TEXT NOT NULL,
  seed        INTEGER NOT NULL,
  store_id    TEXT NOT NULL,
  sku_id      TEXT NOT NULL,
  day         INTEGER NOT NULL CHECK (day BETWEEN 703 AND 730),
  units       INTEGER NOT NULL CHECK (units >= 0),
  PRIMARY KEY (dataset_id, seed, store_id, sku_id, day),
  FOREIGN KEY (dataset_id, store_id) REFERENCES stores(dataset_id, store_id)   ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)   REFERENCES products(dataset_id, sku_id)   ON DELETE CASCADE
) STRICT, WITHOUT ROWID;

-- ───────────── stock state ─────────────
CREATE TABLE batches (
  dataset_id    TEXT NOT NULL,
  batch_id      TEXT NOT NULL,
  warehouse_id  TEXT NOT NULL,
  sku_id        TEXT NOT NULL,
  as_of_day     INTEGER NOT NULL DEFAULT 703,
  qty           INTEGER NOT NULL CHECK (qty >= 0),                              -- V1
  expiry_day    INTEGER NOT NULL,
  PRIMARY KEY (dataset_id, batch_id),
  CHECK (expiry_day >= as_of_day),                                              -- V2
  FOREIGN KEY (dataset_id, warehouse_id) REFERENCES warehouses(dataset_id, warehouse_id) ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)       REFERENCES products(dataset_id, sku_id)         ON DELETE CASCADE  -- V8
) STRICT;
CREATE INDEX ix_batches_fefo ON batches(dataset_id, warehouse_id, sku_id, expiry_day);

CREATE TABLE inbound_schedule (
  dataset_id       TEXT NOT NULL,
  supply_scenario  TEXT NOT NULL CHECK (supply_scenario IN ('normal','scarcity')),
  day              INTEGER NOT NULL CHECK (day IN (703,710,717,724)),
  warehouse_id     TEXT NOT NULL,
  sku_id           TEXT NOT NULL,
  qty              INTEGER NOT NULL CHECK (qty >= 0),
  expiry_day       INTEGER NOT NULL,
  PRIMARY KEY (dataset_id, supply_scenario, day, warehouse_id, sku_id),
  CHECK (expiry_day >= day),
  FOREIGN KEY (dataset_id, warehouse_id) REFERENCES warehouses(dataset_id, warehouse_id) ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)       REFERENCES products(dataset_id, sku_id)         ON DELETE CASCADE
) STRICT;

CREATE TABLE store_stock (
  dataset_id  TEXT NOT NULL,
  as_of_day   INTEGER NOT NULL,
  store_id    TEXT NOT NULL,
  sku_id      TEXT NOT NULL,
  qty         INTEGER NOT NULL CHECK (qty >= 0),
  expiry_day  INTEGER NOT NULL,
  PRIMARY KEY (dataset_id, as_of_day, store_id, sku_id),
  CHECK (expiry_day >= as_of_day),
  FOREIGN KEY (dataset_id, store_id) REFERENCES stores(dataset_id, store_id)   ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)   REFERENCES products(dataset_id, sku_id)   ON DELETE CASCADE
) STRICT;

CREATE TABLE in_transit (
  dataset_id   TEXT NOT NULL,
  as_of_day    INTEGER NOT NULL,
  store_id     TEXT NOT NULL,
  sku_id       TEXT NOT NULL,
  arrival_day  INTEGER NOT NULL,
  qty          INTEGER NOT NULL CHECK (qty >= 0),
  expiry_day   INTEGER NOT NULL,
  PRIMARY KEY (dataset_id, as_of_day, store_id, sku_id, arrival_day),
  CHECK (arrival_day > as_of_day AND expiry_day >= arrival_day),
  FOREIGN KEY (dataset_id, store_id) REFERENCES stores(dataset_id, store_id)   ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)   REFERENCES products(dataset_id, sku_id)   ON DELETE CASCADE
) STRICT;
```

```sql
-- ───────────── models and forecasts ─────────────
CREATE TABLE models (
  model_version      TEXT PRIMARY KEY,
  dataset_id         TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  trained_at         TEXT NOT NULL,
  seed               INTEGER NOT NULL,
  feature_list_json  TEXT NOT NULL CHECK (json_valid(feature_list_json)),
  params_json        TEXT NOT NULL CHECK (json_valid(params_json)),
  lib_versions_json  TEXT NOT NULL CHECK (json_valid(lib_versions_json)),
  artifact_path      TEXT NOT NULL,
  status             TEXT NOT NULL CHECK (status IN ('READY','FAILED'))
) STRICT;
CREATE INDEX ix_models_dataset ON models(dataset_id, trained_at);

CREATE TABLE forecast_metrics (
  model_version  TEXT NOT NULL REFERENCES models(model_version) ON DELETE CASCADE,
  scope          TEXT NOT NULL CHECK (scope IN ('overall','sku','store')),
  scope_id       TEXT NOT NULL,                       -- 'ALL', a sku_id or a store_id
  n_windows      INTEGER NOT NULL,
  wape_model     REAL NOT NULL,
  wape_ma9       REAL NOT NULL,
  bias           REAL NOT NULL,
  cov_p50        REAL NOT NULL,
  cov_p70        REAL NOT NULL,
  cov_p80        REAL NOT NULL,
  cov_p90        REAL NOT NULL,
  pinball_loss   REAL NOT NULL,
  PRIMARY KEY (model_version, scope, scope_id)
) STRICT;

CREATE TABLE forecast_eval (
  model_version  TEXT NOT NULL REFERENCES models(model_version) ON DELETE CASCADE,
  origin_day     INTEGER NOT NULL CHECK (origin_day BETWEEN 673 AND 721),     -- test origins, App. C
  store_id       TEXT NOT NULL,
  sku_id         TEXT NOT NULL,
  p50 INTEGER NOT NULL, p70 INTEGER NOT NULL, p80 INTEGER NOT NULL, p90 INTEGER NOT NULL,
  ma9            INTEGER NOT NULL,
  actual_9d      INTEGER NOT NULL,
  PRIMARY KEY (model_version, origin_day, store_id, sku_id),
  CHECK (p50 <= p70 AND p70 <= p80 AND p80 <= p90)                            -- FR-FCT-06
) STRICT, WITHOUT ROWID;
CREATE INDEX ix_feval_series ON forecast_eval(model_version, store_id, sku_id, origin_day);
```

```sql
-- ───────────── plans ─────────────
CREATE TABLE plans (
  plan_id               TEXT PRIMARY KEY,
  dataset_id            TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  model_version         TEXT NOT NULL REFERENCES models(model_version) ON DELETE RESTRICT,
  as_of_day             INTEGER NOT NULL,
  supply_scenario       TEXT NOT NULL DEFAULT 'normal' CHECK (supply_scenario IN ('normal','scarcity')),
  scenario_type         TEXT NOT NULL DEFAULT 'NONE'
                        CHECK (scenario_type IN ('NONE','WAREHOUSE_OUTAGE','DEMAND_SPIKE','FUEL_PRICE')),
  scenario_params_json  TEXT CHECK (scenario_params_json IS NULL OR json_valid(scenario_params_json)),
  base_plan_id          TEXT REFERENCES plans(plan_id) ON DELETE SET NULL,
  solver_status         TEXT NOT NULL CHECK (solver_status IN ('OPTIMAL','FEASIBLE','FALLBACK_ZERO')),
  gap_pct               REAL,
  solve_time_s          REAL NOT NULL,
  solver_workers        INTEGER NOT NULL,
  deterministic         INTEGER NOT NULL CHECK (deterministic IN (0,1)),
  checker_status        TEXT NOT NULL CHECK (checker_status IN ('PASS','FAIL')),
  n_lines               INTEGER NOT NULL,
  total_cost_paise      INTEGER NOT NULL,             -- transport + lost-sales + holding + wastage terms
  transport_paise       INTEGER NOT NULL,
  unmet_units           INTEGER NOT NULL,
  stage_timings_json    TEXT NOT NULL CHECK (json_valid(stage_timings_json)),
  created_at            TEXT NOT NULL
) STRICT;
CREATE INDEX ix_plans_dataset ON plans(dataset_id, created_at);
CREATE INDEX ix_plans_base    ON plans(base_plan_id);

CREATE TABLE plan_lines (
  plan_id           TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  line_no           INTEGER NOT NULL,
  sku_id            TEXT NOT NULL,
  warehouse_id      TEXT NOT NULL,
  store_id          TEXT NOT NULL,
  batch_id          TEXT NOT NULL,
  batch_expiry_day  INTEGER NOT NULL,
  qty               INTEGER NOT NULL CHECK (qty > 0),
  trucks_on_lane    INTEGER NOT NULL CHECK (trucks_on_lane >= 1),
  line_cost_paise   INTEGER NOT NULL CHECK (line_cost_paise >= 0),
  priority          TEXT NOT NULL CHECK (priority IN ('URGENT','HIGH','NORMAL')),
  PRIMARY KEY (plan_id, line_no)
) STRICT, WITHOUT ROWID;
CREATE INDEX ix_pl_store ON plan_lines(plan_id, store_id);
CREATE INDEX ix_pl_wh    ON plan_lines(plan_id, warehouse_id);
CREATE INDEX ix_pl_sku   ON plan_lines(plan_id, sku_id);
CREATE INDEX ix_pl_prio  ON plan_lines(plan_id, priority);

CREATE TABLE plan_line_reasons (
  plan_id        TEXT NOT NULL,
  line_no        INTEGER NOT NULL,
  code           TEXT NOT NULL CHECK (code IN ('LOW_COVER','EXPIRY_FIRST','LOWEST_COST_SOURCE',
                                               'CAPACITY_LIMITED','SCARCE_PRIORITY',
                                               'REPLENISH_TO_TARGET','NEXT_BEST')),
  evidence_json  TEXT NOT NULL CHECK (json_valid(evidence_json)),
  PRIMARY KEY (plan_id, line_no, code),
  FOREIGN KEY (plan_id, line_no) REFERENCES plan_lines(plan_id, line_no) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;
CREATE INDEX ix_plr_code ON plan_line_reasons(plan_id, code);

CREATE TABLE plan_lanes (
  plan_id           TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  warehouse_id      TEXT NOT NULL,
  store_id          TEXT NOT NULL,
  trucks            INTEGER NOT NULL CHECK (trucks >= 1),
  loaded_ml         INTEGER NOT NULL CHECK (loaded_ml > 0),
  truck_cost_paise  INTEGER NOT NULL CHECK (truck_cost_paise >= 0),
  PRIMARY KEY (plan_id, warehouse_id, store_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE plan_unmet (
  plan_id             TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  store_id            TEXT NOT NULL,
  sku_id              TEXT NOT NULL,
  units               INTEGER NOT NULL CHECK (units > 0),
  margin_at_risk_paise INTEGER NOT NULL CHECK (margin_at_risk_paise >= 0),
  PRIMARY KEY (plan_id, store_id, sku_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE plan_targets (
  plan_id           TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  store_id          TEXT NOT NULL,
  sku_id            TEXT NOT NULL,
  p50 INTEGER NOT NULL, p70 INTEGER NOT NULL, p80 INTEGER NOT NULL, p90 INTEGER NOT NULL,
  critical_ratio    REAL NOT NULL,
  chosen_quantile   REAL NOT NULL CHECK (chosen_quantile IN (0.7,0.8,0.9)),
  target_q          INTEGER NOT NULL,
  onhand            INTEGER NOT NULL,
  intransit         INTEGER NOT NULL,
  cold_start        INTEGER NOT NULL DEFAULT 0 CHECK (cold_start IN (0,1)),
  PRIMARY KEY (plan_id, store_id, sku_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE plan_deltas (
  plan_id                  TEXT PRIMARY KEY REFERENCES plans(plan_id) ON DELETE CASCADE,
  base_plan_id             TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  delta_transport_paise    INTEGER NOT NULL,
  delta_unmet_units        INTEGER NOT NULL,
  delta_margin_risk_paise  INTEGER NOT NULL,
  delta_trucks             INTEGER NOT NULL,
  affected_stores_json     TEXT NOT NULL CHECK (json_valid(affected_stores_json))
) STRICT;

CREATE TABLE counterfactuals (                       -- P1
  plan_id               TEXT NOT NULL,
  line_no               INTEGER NOT NULL,
  alt_warehouse_id      TEXT NOT NULL,
  delta_cost_paise      INTEGER,
  status                TEXT NOT NULL CHECK (status IN ('PENDING','DONE','INFEASIBLE','TIMEOUT')),
  solved_at             TEXT,
  PRIMARY KEY (plan_id, line_no),
  FOREIGN KEY (plan_id, line_no) REFERENCES plan_lines(plan_id, line_no) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;
```

```sql
-- ───────────── backtest ─────────────
CREATE TABLE jobs (
  job_id       TEXT PRIMARY KEY,
  type         TEXT NOT NULL CHECK (type IN ('TRAIN','BACKTEST','COUNTERFACTUAL')),
  status       TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
  progress     INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  message      TEXT,
  params_json  TEXT NOT NULL CHECK (json_valid(params_json)),
  result_ref   TEXT,                                  -- model_version or run_id
  created_at   TEXT NOT NULL,
  started_at   TEXT,
  finished_at  TEXT
) STRICT;
CREATE INDEX ix_jobs_status ON jobs(status);
CREATE INDEX ix_jobs_type   ON jobs(type, created_at);

CREATE TABLE backtest_runs (
  run_id           TEXT PRIMARY KEY,
  dataset_id       TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  model_version    TEXT NOT NULL REFERENCES models(model_version) ON DELETE RESTRICT,
  job_id           TEXT REFERENCES jobs(job_id) ON DELETE SET NULL,
  status           TEXT NOT NULL CHECK (status IN ('RUNNING','COMPLETE','FAILED')),
  seeds_json       TEXT NOT NULL CHECK (json_valid(seeds_json)),
  scenarios_json   TEXT NOT NULL CHECK (json_valid(scenarios_json)),
  policies_json    TEXT NOT NULL CHECK (json_valid(policies_json)),
  created_at       TEXT NOT NULL,
  finished_at      TEXT
) STRICT;

CREATE TABLE sim_results (
  run_id                  TEXT NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
  policy                  TEXT NOT NULL CHECK (policy IN ('B1','B2','O_MA','VITARANIQ')),
  seed                    INTEGER NOT NULL,
  supply_scenario         TEXT NOT NULL CHECK (supply_scenario IN ('normal','scarcity')),
  units_demanded          INTEGER NOT NULL,
  units_sold              INTEGER NOT NULL,
  units_unmet             INTEGER NOT NULL,
  units_delivered         INTEGER NOT NULL,
  store_days_total        INTEGER NOT NULL,
  store_days_stockout     INTEGER NOT NULL,
  wastage_units           INTEGER NOT NULL,
  wastage_paise           INTEGER NOT NULL,
  transport_paise         INTEGER NOT NULL,
  trips                   INTEGER NOT NULL,
  loaded_ml               INTEGER NOT NULL,
  truck_capacity_ml_total INTEGER NOT NULL,
  lost_margin_paise       INTEGER NOT NULL,
  margin_demanded_paise   INTEGER NOT NULL,
  margin_sold_paise       INTEGER NOT NULL,
  PRIMARY KEY (run_id, policy, seed, supply_scenario),
  CHECK (units_sold + units_unmet = units_demanded)                           -- conservation check
) STRICT, WITHOUT ROWID;

CREATE TABLE sim_daily (
  run_id           TEXT NOT NULL,
  policy           TEXT NOT NULL,
  seed             INTEGER NOT NULL,
  supply_scenario  TEXT NOT NULL,
  day              INTEGER NOT NULL CHECK (day BETWEEN 703 AND 730),
  units_demanded   INTEGER NOT NULL,
  units_sold       INTEGER NOT NULL,
  units_unmet      INTEGER NOT NULL,
  wastage_paise    INTEGER NOT NULL,
  transport_paise  INTEGER NOT NULL,
  PRIMARY KEY (run_id, policy, seed, supply_scenario, day),
  FOREIGN KEY (run_id, policy, seed, supply_scenario)
    REFERENCES sim_results(run_id, policy, seed, supply_scenario) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;

CREATE TABLE sim_plan_checks (
  run_id           TEXT NOT NULL,
  policy           TEXT NOT NULL,
  seed             INTEGER NOT NULL,
  supply_scenario  TEXT NOT NULL,
  plan_day         INTEGER NOT NULL CHECK (plan_day IN (703,710,717,724)),
  checker_status   TEXT NOT NULL CHECK (checker_status IN ('PASS','FAIL')),
  n_lines          INTEGER NOT NULL,
  PRIMARY KEY (run_id, policy, seed, supply_scenario, plan_day),
  FOREIGN KEY (run_id, policy, seed, supply_scenario)
    REFERENCES sim_results(run_id, policy, seed, supply_scenario) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;

-- ───────────── KPI view (the only place KPIs are computed from raw sums) ─────────────
CREATE VIEW v_sim_kpis AS
SELECT run_id, policy, seed, supply_scenario,
       1.0 * units_sold          / NULLIF(units_demanded, 0)        AS fill_rate,
       1.0 * store_days_stockout / NULLIF(store_days_total, 0)      AS stockout_rate,
       wastage_paise,
       transport_paise,
       1.0 * transport_paise     / NULLIF(units_delivered, 0)       AS cost_per_unit_delivered_paise,
       1.0 * loaded_ml           / NULLIF(truck_capacity_ml_total,0) AS truck_fill,
       transport_paise + lost_margin_paise + wastage_paise          AS total_cost_paise,
       1.0 * margin_sold_paise   / NULLIF(margin_demanded_paise, 0) AS margin_weighted_fill_rate
FROM sim_results;
```

---

## 6. Snapshot Loader Mapping

The `db.snapshot_loader` builds the `Snapshot` structure (Architecture §4) from these tables:

| `Snapshot` field | Source |
|---|---|
| `warehouses[w]`: fleet, inbound weight | `warehouses` |
| `stores[s]`: storage capacity, size, region | `stores` |
| `sku[p]`: volume, shelf life, cost, price, margin, `min_life`, `w`, `g` | `products` |
| `lanes[w,s]`: km, transit, eligible | `lanes` |
| `batches` (w, p, qty, expiry) | `batches` where `as_of_day = :as_of` |
| `store_onhand` (s, p, qty, expiry) | `store_stock` where `as_of_day = :as_of` |
| `intransit` (s, p, qty, arrival) | `in_transit` where `as_of_day = :as_of` |
| Sales history for features | `sales_daily` (days ≤ origin) |
| Known-future covariates | `calendar`, `promo_windows` |
| Backtest-window demand | `window_demand` (per seed) |
| Scheduled inbound | `inbound_schedule` (per supply scenario) |

---

## 7. Query Patterns and Indexes

| Use | Query shape | Index used |
|---|---|---|
| Feature building, one series | `WHERE dataset_id=? AND store_id=? AND sku_id=? AND day BETWEEN …` | `sales_daily` primary key |
| Daily totals for the simulator | `WHERE dataset_id=? AND day=?` | `ix_sales_day` |
| FEFO batch order | `WHERE dataset_id=? AND warehouse_id=? AND sku_id=? ORDER BY expiry_day` | `ix_batches_fefo` |
| Forecast chart | `WHERE model_version=? AND store_id=? AND sku_id=? ORDER BY origin_day` | `ix_feval_series` |
| Plan table with filters | `WHERE plan_id=? AND store_id=?` (or warehouse, SKU, priority) | `ix_pl_*` |
| Filter by reason code | `JOIN plan_line_reasons … WHERE plan_id=? AND code=?` | `ix_plr_code` |
| Latest plans list | `WHERE dataset_id=? ORDER BY created_at DESC LIMIT 20` | `ix_plans_dataset` |
| Backtest page | `SELECT * FROM v_sim_kpis WHERE run_id=?` | `sim_results` primary key |
| Running jobs at start-up | `WHERE status='RUNNING'` | `ix_jobs_status` |

---

## 8. Integrity and Validation Mapping

| SRS rule | Enforced by |
|---|---|
| V1 negative or non-integer quantity | `STRICT` INTEGER type + `CHECK (qty >= 0)` |
| V2 expiry earlier than as-of day | `CHECK (expiry_day >= as_of_day)` on stock tables |
| V3 lane without distance | `km` is `NOT NULL`, and the validator checks that a lane exists for every warehouse–store pair |
| V4 SKU with non-positive volume, shelf life or cost | `CHECK` on `products` |
| V5 price ≤ cost | `CHECK (price_paise > unit_cost_paise)` |
| V6 negative sales | `CHECK (units >= 0)` |
| V7 duplicate `(day, store, sku)` | Primary key of `sales_daily` |
| V8 batch with missing warehouse or SKU | Foreign keys on `batches` |
| Unit conservation in simulation | `CHECK (units_sold + units_unmet = units_demanded)` |
| FR-FCT-06 ordering of quantiles | `CHECK (p50 <= p70 AND …)` on `forecast_eval`; the same rule is tested for `plan_targets` |
| FR-DAT-08 one active dataset | Partial unique index `ux_datasets_active` |

Rules the database cannot express (FEFO invariant, truck capacity, store capacity, lead-time eligibility, plan cost recompute) are enforced by the plan-checker (FR-CHK-02) and tested, not by constraints.

`plan_lines`, `plan_unmet` and `plan_targets` reference master data by code only, because the dataset is determined by the parent `plans` row. Service tests check that every code exists in the plan's dataset.

---

## 9. Dataset Hash and Reproducibility

`dataset_hash` (FR-DAT-01) is the SHA-256 of a canonical export:

1. Tables in this fixed order: `warehouses, stores, products, lanes, calendar, promo_windows, sales_daily, batches, inbound_schedule, store_stock`.
2. Rows sorted by primary key. Columns in DDL order. `dataset_id` excluded.
3. UTF-8, `\n` line endings, comma separator, header row per table, REAL values formatted with 6 decimals, NULL as an empty field.
4. Table name and row count written before each table.

`params_hash` is the SHA-256 of `config/params.yaml`. A `model_version` is derived from `dataset_hash + feature list + params_json`, so retraining on identical inputs gives the same version string (Architecture §5.2).

---

## 10. Lifecycle, Migrations and Maintenance

| Topic | Rule |
|---|---|
| Regeneration (FR-DAT-08) | In one transaction: delete the previous `datasets` row (cascades to everything dependent), insert the new dataset and its tables. After commit, the service deletes model artifact folders of removed `models` rows and clears caches. |
| Models in use | `plans.model_version` and `backtest_runs.model_version` use `ON DELETE RESTRICT`, so a model cannot be removed while records reference it. Dataset deletion removes plans and runs first through its own cascade. |
| Migrations | Alembic. `0001_initial` equals §5. Later changes are numbered migrations recorded in `schema_version`. A change to this schema also requires updating SRS §3.5 and this document. |
| Start-up checks | SQLite version ≥ 3.37; `PRAGMA integrity_check` on demand; mark `RUNNING` jobs as `FAILED: interrupted`. |
| Backup | Copy `data/vitaraniq.db` (and `-wal`) while the API is stopped, or use `VACUUM INTO`. The dataset is regenerable from its seed, so the database is not a system of record. |
| Housekeeping | Plans older than the latest 200 may be deleted by a maintenance command. Child rows cascade. |
| Privacy | All data is synthetic. There are no personal fields. |

---

## 11. Sizing and Performance Notes

- **Reference scale:** ≈ 270,000 rows in total, 20–40 MB including indexes.
- **Bulk loading:** use `executemany` inside one transaction for `sales_daily` (219,000 rows). Target ≤ 10 s, well inside the 60 s limit of FR-DAT-01.
- **Snapshot load** (NFR-PERF-01 budget ≤ 1 s): about 750 small rows plus lane and SKU tables, then cached by `(dataset_hash, as_of_day)`.
- **Sales history for training:** read once with a single query into a pandas DataFrame, sorted by the primary key order to keep reads sequential.
- **Writes during backtests:** worker processes return `SimResult` objects, and the parent writes `sim_results`, `sim_daily` and `sim_plan_checks` in one transaction (Architecture §15).
- **Scale path:** the same DDL ports to PostgreSQL by dropping `STRICT` and `WITHOUT ROWID`, replacing the generated column and partial index syntax where needed, and using `JSONB` in place of `TEXT`.

---

## 12. Traceability

| Requirement | Tables |
|---|---|
| FR-DAT-01…08 | `datasets`, `warehouses`, `stores`, `products`, `lanes`, `calendar`, `promo_windows`, `sales_daily`, `batches`, `store_stock`, `inbound_schedule` |
| FR-FCT-01…08 | `models`, `forecast_metrics`, `forecast_eval`, `sales_daily`, `calendar`, `promo_windows` |
| FR-SVL-01…04 | `products` (constants), `plan_targets` |
| FR-OPT-01…10 | `plans`, `plan_lines`, `plan_lanes`, `plan_unmet`, `plan_targets` |
| FR-SHL-01…04 | `batches`, `products` |
| FR-CHK-01…05 | `plans.checker_status`, `sim_plan_checks` |
| FR-REC-01…05 | `plan_lines`, `plan_lanes`, `plan_line_reasons` |
| FR-EXP-01…05 | `plan_line_reasons`, `counterfactuals` |
| FR-SIM-01…09 | `backtest_runs`, `sim_results`, `sim_daily`, `sim_plan_checks`, `window_demand`, `inbound_schedule`, `v_sim_kpis` |
| FR-WIF-01…04 | `plans` (scenario columns), `plan_deltas` |
| NFR-REL-03 | `jobs` |
| NFR-HON-01 | `sim_results` + `v_sim_kpis` (no stored KPI constants) |
