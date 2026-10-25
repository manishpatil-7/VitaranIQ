"""
Authoritative SQLite DDL for VitaranIQ.
Enforces STRICT tables, WAL mode, foreign keys, and integrity constraints
matching VitaranIQ_Database_Schema_v1.md.
"""

SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

-- ───────────── meta ─────────────
CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER PRIMARY KEY,
  description TEXT NOT NULL,
  applied_at  TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS datasets (
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
CREATE UNIQUE INDEX IF NOT EXISTS ux_datasets_active ON datasets(is_active) WHERE is_active = 1;

-- ───────────── master data ─────────────
CREATE TABLE IF NOT EXISTS warehouses (
  dataset_id       TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  warehouse_id     TEXT NOT NULL,
  name             TEXT NOT NULL,
  lat              REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon              REAL NOT NULL CHECK (lon BETWEEN -180 AND 180),
  fleet            INTEGER NOT NULL CHECK (fleet >= 0),
  inbound_weight   REAL NOT NULL CHECK (inbound_weight >= 0 AND inbound_weight <= 1),
  PRIMARY KEY (dataset_id, warehouse_id)
) STRICT;

CREATE TABLE IF NOT EXISTS stores (
  dataset_id      TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  store_id        TEXT NOT NULL,
  name            TEXT NOT NULL,
  city            TEXT NOT NULL,
  region          TEXT NOT NULL,
  lat             REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon             REAL NOT NULL CHECK (lon BETWEEN -180 AND 180),
  size_mult       REAL NOT NULL CHECK (size_mult > 0),
  storage_cap_ml  INTEGER NOT NULL CHECK (storage_cap_ml > 0),
  PRIMARY KEY (dataset_id, store_id)
) STRICT;

CREATE TABLE IF NOT EXISTS products (
  dataset_id         TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  sku_id             TEXT NOT NULL,
  name               TEXT NOT NULL,
  category           TEXT NOT NULL,
  unit_cost_paise    INTEGER NOT NULL CHECK (unit_cost_paise > 0),
  price_paise        INTEGER NOT NULL,
  volume_ml          INTEGER NOT NULL CHECK (volume_ml > 0),
  shelf_life_days    INTEGER NOT NULL CHECK (shelf_life_days > 0),
  min_life_days      INTEGER NOT NULL CHECK (min_life_days >= 0),
  write_off_factor   REAL NOT NULL CHECK (write_off_factor BETWEEN 0 AND 1),
  stockout_mult      INTEGER NOT NULL CHECK (stockout_mult >= 1),
  base_units_per_day REAL NOT NULL CHECK (base_units_per_day > 0),
  margin_paise       INTEGER GENERATED ALWAYS AS (price_paise - unit_cost_paise) VIRTUAL,
  PRIMARY KEY (dataset_id, sku_id),
  CHECK (price_paise > unit_cost_paise),
  CHECK (min_life_days <= shelf_life_days)
) STRICT;

CREATE TABLE IF NOT EXISTS lanes (
  dataset_id    TEXT NOT NULL,
  warehouse_id  TEXT NOT NULL,
  store_id      TEXT NOT NULL,
  km            REAL NOT NULL CHECK (km > 0),
  transit_days  INTEGER NOT NULL CHECK (transit_days IN (1,2)),
  eligible      INTEGER NOT NULL CHECK (eligible IN (0,1)),
  PRIMARY KEY (dataset_id, warehouse_id, store_id),
  FOREIGN KEY (dataset_id, warehouse_id) REFERENCES warehouses(dataset_id, warehouse_id) ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, store_id)     REFERENCES stores(dataset_id, store_id)         ON DELETE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS calendar (
  dataset_id     TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  day            INTEGER NOT NULL CHECK (day BETWEEN 1 AND 740),
  date           TEXT NOT NULL,
  dow            INTEGER NOT NULL CHECK (dow BETWEEN 0 AND 6),
  month          INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
  is_holiday     INTEGER NOT NULL CHECK (is_holiday IN (0,1)),
  is_festival    INTEGER NOT NULL CHECK (is_festival IN (0,1)),
  festival_name  TEXT,
  PRIMARY KEY (dataset_id, day)
) STRICT;

CREATE TABLE IF NOT EXISTS promo_windows (
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
CREATE TABLE IF NOT EXISTS sales_daily (
  dataset_id  TEXT NOT NULL,
  store_id    TEXT NOT NULL,
  sku_id      TEXT NOT NULL,
  day         INTEGER NOT NULL CHECK (day BETWEEN 1 AND 730),
  units       INTEGER NOT NULL CHECK (units >= 0),
  promo_flag  INTEGER NOT NULL DEFAULT 0 CHECK (promo_flag IN (0,1)),
  PRIMARY KEY (dataset_id, store_id, sku_id, day),
  FOREIGN KEY (dataset_id, store_id) REFERENCES stores(dataset_id, store_id)   ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)   REFERENCES products(dataset_id, sku_id)   ON DELETE CASCADE
) STRICT, WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_sales_day ON sales_daily(dataset_id, day);

CREATE TABLE IF NOT EXISTS window_demand (
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
CREATE TABLE IF NOT EXISTS batches (
  dataset_id    TEXT NOT NULL,
  batch_id      TEXT NOT NULL,
  warehouse_id  TEXT NOT NULL,
  sku_id        TEXT NOT NULL,
  as_of_day     INTEGER NOT NULL DEFAULT 703,
  qty           INTEGER NOT NULL CHECK (qty >= 0),
  expiry_day    INTEGER NOT NULL,
  PRIMARY KEY (dataset_id, batch_id),
  CHECK (expiry_day >= as_of_day),
  FOREIGN KEY (dataset_id, warehouse_id) REFERENCES warehouses(dataset_id, warehouse_id) ON DELETE CASCADE,
  FOREIGN KEY (dataset_id, sku_id)       REFERENCES products(dataset_id, sku_id)         ON DELETE CASCADE
) STRICT;
CREATE INDEX IF NOT EXISTS ix_batches_fefo ON batches(dataset_id, warehouse_id, sku_id, expiry_day);

CREATE TABLE IF NOT EXISTS inbound_schedule (
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

CREATE TABLE IF NOT EXISTS store_stock (
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

CREATE TABLE IF NOT EXISTS in_transit (
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

-- ───────────── models and forecasts ─────────────
CREATE TABLE IF NOT EXISTS models (
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
CREATE INDEX IF NOT EXISTS ix_models_dataset ON models(dataset_id, trained_at);

CREATE TABLE IF NOT EXISTS forecast_metrics (
  model_version  TEXT NOT NULL REFERENCES models(model_version) ON DELETE CASCADE,
  scope          TEXT NOT NULL CHECK (scope IN ('overall','sku','store')),
  scope_id       TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS forecast_eval (
  model_version  TEXT NOT NULL REFERENCES models(model_version) ON DELETE CASCADE,
  origin_day     INTEGER NOT NULL CHECK (origin_day BETWEEN 673 AND 721),
  store_id       TEXT NOT NULL,
  sku_id         TEXT NOT NULL,
  p50            INTEGER NOT NULL,
  p70            INTEGER NOT NULL,
  p80            INTEGER NOT NULL,
  p90            INTEGER NOT NULL,
  ma9            INTEGER NOT NULL,
  actual_9d      INTEGER NOT NULL,
  PRIMARY KEY (model_version, origin_day, store_id, sku_id),
  CHECK (p50 <= p70 AND p70 <= p80 AND p80 <= p90)
) STRICT, WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_feval_series ON forecast_eval(model_version, store_id, sku_id, origin_day);

-- ───────────── plans ─────────────
CREATE TABLE IF NOT EXISTS plans (
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
  total_cost_paise      INTEGER NOT NULL,
  transport_paise       INTEGER NOT NULL,
  unmet_units           INTEGER NOT NULL,
  stage_timings_json    TEXT NOT NULL CHECK (json_valid(stage_timings_json)),
  created_at            TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS ix_plans_dataset ON plans(dataset_id, created_at);
CREATE INDEX IF NOT EXISTS ix_plans_base    ON plans(base_plan_id);

CREATE TABLE IF NOT EXISTS plan_lines (
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
CREATE INDEX IF NOT EXISTS ix_pl_store ON plan_lines(plan_id, store_id);
CREATE INDEX IF NOT EXISTS ix_pl_wh    ON plan_lines(plan_id, warehouse_id);
CREATE INDEX IF NOT EXISTS ix_pl_sku   ON plan_lines(plan_id, sku_id);
CREATE INDEX IF NOT EXISTS ix_pl_prio  ON plan_lines(plan_id, priority);

CREATE TABLE IF NOT EXISTS plan_line_reasons (
  plan_id        TEXT NOT NULL,
  line_no        INTEGER NOT NULL,
  code           TEXT NOT NULL CHECK (code IN ('LOW_COVER','EXPIRY_FIRST','LOWEST_COST_SOURCE',
                                               'CAPACITY_LIMITED','SCARCE_PRIORITY',
                                               'REPLENISH_TO_TARGET','NEXT_BEST')),
  evidence_json  TEXT NOT NULL CHECK (json_valid(evidence_json)),
  PRIMARY KEY (plan_id, line_no, code),
  FOREIGN KEY (plan_id, line_no) REFERENCES plan_lines(plan_id, line_no) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_plr_code ON plan_line_reasons(plan_id, code);

CREATE TABLE IF NOT EXISTS plan_lanes (
  plan_id           TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  warehouse_id      TEXT NOT NULL,
  store_id          TEXT NOT NULL,
  trucks            INTEGER NOT NULL CHECK (trucks >= 1),
  loaded_ml         INTEGER NOT NULL CHECK (loaded_ml > 0),
  truck_cost_paise  INTEGER NOT NULL CHECK (truck_cost_paise >= 0),
  PRIMARY KEY (plan_id, warehouse_id, store_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS plan_unmet (
  plan_id              TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  store_id             TEXT NOT NULL,
  sku_id               TEXT NOT NULL,
  units                INTEGER NOT NULL CHECK (units > 0),
  margin_at_risk_paise INTEGER NOT NULL CHECK (margin_at_risk_paise >= 0),
  PRIMARY KEY (plan_id, store_id, sku_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS plan_targets (
  plan_id           TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  store_id          TEXT NOT NULL,
  sku_id            TEXT NOT NULL,
  p50               INTEGER NOT NULL,
  p70               INTEGER NOT NULL,
  p80               INTEGER NOT NULL,
  p90               INTEGER NOT NULL,
  critical_ratio    REAL NOT NULL,
  chosen_quantile   REAL NOT NULL CHECK (chosen_quantile IN (0.7,0.8,0.9)),
  target_q          INTEGER NOT NULL,
  onhand            INTEGER NOT NULL,
  intransit         INTEGER NOT NULL,
  cold_start        INTEGER NOT NULL DEFAULT 0 CHECK (cold_start IN (0,1)),
  PRIMARY KEY (plan_id, store_id, sku_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS plan_deltas (
  plan_id                  TEXT PRIMARY KEY REFERENCES plans(plan_id) ON DELETE CASCADE,
  base_plan_id             TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
  delta_transport_paise    INTEGER NOT NULL,
  delta_unmet_units        INTEGER NOT NULL,
  delta_margin_risk_paise  INTEGER NOT NULL,
  delta_trucks             INTEGER NOT NULL,
  affected_stores_json     TEXT NOT NULL CHECK (json_valid(affected_stores_json))
) STRICT;

CREATE TABLE IF NOT EXISTS counterfactuals (
  plan_id               TEXT NOT NULL,
  line_no               INTEGER NOT NULL,
  alt_warehouse_id      TEXT NOT NULL,
  delta_cost_paise      INTEGER,
  status                TEXT NOT NULL CHECK (status IN ('PENDING','DONE','INFEASIBLE','TIMEOUT')),
  solved_at             TEXT,
  PRIMARY KEY (plan_id, line_no),
  FOREIGN KEY (plan_id, line_no) REFERENCES plan_lines(plan_id, line_no) ON DELETE CASCADE
) STRICT, WITHOUT ROWID;

-- ───────────── backtest and jobs ─────────────
CREATE TABLE IF NOT EXISTS jobs (
  job_id       TEXT PRIMARY KEY,
  type         TEXT NOT NULL CHECK (type IN ('TRAIN','BACKTEST','COUNTERFACTUAL')),
  status       TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
  progress     INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  message      TEXT,
  params_json  TEXT NOT NULL CHECK (json_valid(params_json)),
  result_ref   TEXT,
  created_at   TEXT NOT NULL,
  started_at   TEXT,
  finished_at  TEXT
) STRICT;
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS ix_jobs_type   ON jobs(type, created_at);

CREATE TABLE IF NOT EXISTS backtest_runs (
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

CREATE TABLE IF NOT EXISTS sim_results (
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
  CHECK (units_sold + units_unmet = units_demanded)
) STRICT, WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sim_daily (
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

CREATE TABLE IF NOT EXISTS sim_plan_checks (
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

-- ───────────── KPI view ─────────────
DROP VIEW IF EXISTS v_sim_kpis;
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
"""


def init_db(connection):
    """Execute authoritative schema DDL on an open sqlite3 connection."""
    connection.executescript(SCHEMA_DDL)
    connection.commit()
