# VitaranIQ — AI/ML & Optimization Design

**Team:** Innovate-x · **Project:** VitaranIQ · **Document:** AI/ML & Optimization Design · **Version:** 1.0 · **Date:** 2026-10-24
**Derived from:** PRD v2.0, SRS v1.0, System Architecture v1.0, Database Schema v1.0. Requirement IDs refer to the SRS.
**Status:** final document of the planned set. Where this design refines the SRS, the refinement is listed in §13.

---

## 1. Purpose and Role of AI

This document fixes how VitaranIQ predicts demand and turns the prediction into a feasible dispatch plan: features, model settings, the integer program, scaling, solver settings, baselines, the experiment that measures the AI contribution, and the tests that prove it works.

### 1.1 Where the AI output changes the decision

The forecast is not decoration. Five parts of the plan depend directly on the model's output:

| # | Decision input | Derived from the ML output | Effect on the plan |
|---|---|---|---|
| 1 | Target stock per store–SKU, `target_q` | Quantile forecast (P70/P80/P90) chosen by critical ratio | How many units each store needs |
| 2 | Sell-through cap for short-life batches | `target_q × min(L,9)/9` | Which batches may go to which store |
| 3 | Expected-wastage coefficient | `target_q` and `P50` over remaining life | Which store gets near-expiry stock |
| 4 | Lost-sales exposure and priority labels | `P50` demand rate, cover days | Who is served first under scarcity, URGENT/HIGH/NORMAL |
| 5 | Heatmap risk and reason-code evidence | Quantiles against on-hand | What the planner sees and why |

The ablation in §9.5 (O-MA vs VitaranIQ) measures this contribution with the optimizer held constant.

### 1.2 Design principles
1. **Predict, then decide, then verify.** ML predicts. A solver decides. An independent checker verifies.
2. **Correct quantities, not point guesses.** The optimizer needs a distribution, so the model predicts quantiles.
3. **Leakage-free by construction.** Every feature and every split is tested for look-ahead.
4. **Everything reproducible.** Seeds, versions and hashes are stored (FR-DAT-01, FR-FCT-07, NFR-REL-02).
5. **Measure honestly.** All KPIs come from the simulator. The design contains no constants that are tuned to hit a target.

---

## 2. End-to-End Computation

```
 history ──► features(t) ──► 4 quantile models ──► sort/clip/ceil ──► ForecastTable
                                                                          │
 margins, costs, w, g ──► critical ratio ──► quantile choice ───────────► Targets (target_q)
                                                                          │
 Snapshot (batches, stock, lanes, trucks) ───────────────────────────────►│
                                                                          ▼
                                            greedy warm start ──► CP-SAT integer program
                                                                          │
                                           FEFO repair ◄── RawPlan (x, y, u, e)
                                                                          │
                                  explain ──► PlanLines ──► plan-checker ──► stored plan
```

**Notation.** *w* warehouse, *s* store, *p* SKU, *b* batch, *t* forecast origin day, *H* = 9 (coverage window in days), `as_of` plan day, `transit[w,s]` lane lead time, `Λ[w,b,s] = expiry[b] − as_of − transit[w,s]` remaining life on arrival.

---

## 3. Data Generation Design (supports FR-DAT-01…05)

| Aspect | Design |
|---|---|
| Random streams | One `SeedSequence(seed)` spawns independent named child streams: `network`, `calendar`, `promo`, `history_noise`, `window_noise[seed]`, `initial_stock`. Changing one component never shifts the random numbers of another. |
| Demand sampling | Gamma–Poisson mixture: `λ ~ Gamma(shape = 1/φ, scale = μ·φ)`, `X ~ Poisson(λ)` with φ = 0.10. This gives mean μ and variance `μ + φμ²` (SRS Appendix B). |
| Mean demand | `μ[d,s,p] = base × size × weekday × season × festival × promo × trend` (SRS Appendix B). Computed as one vectorized NumPy array of shape (730, 25, 12). |
| Calendar | Fixed table in `data/calendar.py`: 12 festival windows per year with approximate fixed month/day (synthetic, not an official calendar): Makar Sankranti, Holi, Gudi Padwa, Eid, Raksha Bandhan, Independence Day, Ganesh Chaturthi, Navratri, Dussehra, Diwali, Christmas, New Year. Public holidays on Jan 26, Aug 15, Oct 2, Dec 25. Covers days 1–740. |
| Store placement | City anchors plus seeded jitter of ±0.15° in latitude and longitude. A placement is rejected and redrawn if any store has fewer than two eligible warehouses. |
| Initial state | Per SRS FR-DAT-04. Remaining-life fractions are drawn uniformly from the stated ranges and rounded to whole days. Batch quantities are split among 2–4 batches with random Dirichlet(1,1,1,1) shares. |
| Window noise | For each backtest seed the days 703–730 are re-sampled from the same μ with a stream seeded by that seed, and stored in `window_demand`. History through day 702 is identical for all seeds. |
| Output check | Generator tests assert: row counts, non-negativity, mean demand per SKU within ±10% of `base × mean size`, weekday ratios within ±5% of the configured multipliers, and an identical dataset hash on a rerun. |

---

## 4. Forecasting Design (FR-FCT-01…09)

### 4.1 Problem framing
The planner needs the distribution of demand **over the coverage window**, not tomorrow's demand. For origin day *t*, the target is

`Y[t,s,p] = Σ_{k=1..9} demand[t+k, s, p]`

One global model per quantile is trained across all 300 series so that stores and SKUs share statistical strength.

### 4.2 Scale normalization
Quantiles are equivariant under multiplication by a positive known function of the features. Each series is therefore normalized by its own recent level:

- `scale[t,s,p] = max(s28 × 9/28, 5)` where `s28` is the sum of daily sales over days `t−27 … t`.
- The model learns the ratio `r = Y / scale`. The forecast is `P_q = r̂_q × scale`.

This lets one tree ensemble handle a milk series selling 100 units a day and a rice series selling 10, without a separate model per series.

### 4.3 Features (21), all computable from data up to day *t* or known in advance

| Group | Feature | Definition |
|---|---|---|
| History | `s1` | Units sold on day *t* |
| | `s7`, `s14`, `s28` | Rolling sums over the last 7, 14, 28 days, each divided by `scale` |
| | `sd7`, `sd28` | Rolling standard deviation of daily sales over 7 and 28 days, divided by `scale/9` |
| | `trend` | `(s7 / 7) ÷ max(s28 / 28, 0.5)` |
| | `wd_factor_sum` | Sum over the 9 target days of the weekday index `wi[dow]`, where `wi` is estimated from the **training segment only** (mean sales by weekday ÷ overall mean) |
| | `promo_last28` | Number of promo days for this store–SKU in the last 28 days |
| Known-future | `n_promo_win` | Promo days of this store–SKU inside days *t+1 … t+9* (from `promo_windows`) |
| | `n_fest_win`, `n_hol_win` | Festival and holiday days inside the target window |
| | `days_to_fest` | Days to the next festival day, capped at 60 |
| Calendar | `dow`, `month` | Day of week and month of the origin day |
| Static | `sku`, `store` | Categorical codes |
| | `category` | Categorical (dairy, bakery, staples, snacks, beverages, personal care) |
| | `size_mult`, `price`, `shelf_life` | Numeric attributes |

**Leakage rules.** (a) A feature at origin *t* may read `sales_daily` rows with `day ≤ t` only. (b) Known-future calendar columns may read days up to *t+9* because they are planned in advance (festival and promo calendars). (c) The weekday index is estimated on training days only. (d) No feature is built from `window_demand`.

### 4.4 Training procedure

| Item | Value |
|---|---|
| Models | Four LightGBM boosters, `objective = quantile`, `alpha ∈ {0.5, 0.7, 0.8, 0.9}` |
| Rows | Train origins 29–620: 592 origins × 300 series = **177,600**. Validation origins 630–663: **10,200**. Test origins 673–721: **14,700** (SRS Appendix C; the first 28 days are warm-up for lags) |
| Hyperparameters | `learning_rate 0.05`, `num_leaves 63`, `min_data_in_leaf 200`, `feature_fraction 0.8`, `bagging_fraction 0.8`, `bagging_freq 1`, `lambda_l2 1.0`, `cat_smooth 20`, `min_data_per_group 100`, `n_estimators 2000` with `early_stopping_rounds 100` on validation pinball loss |
| Determinism | `seed 42`, `deterministic=True`, `force_row_wise=True`, `num_threads 4` |
| Expected run time | Under 1 minute per model on the reference hardware, giving about 3–4 minutes in total (budget: 5 minutes, NFR-PERF-02) |
| Neighbouring-origin overlap | Consecutive origins share 8 of 9 target days. Early stopping uses the separate validation segment, and the 9-day purge keeps targets from crossing segments. |

### 4.5 Post-processing (FR-FCT-06)
1. `pred_q = r̂_q × scale`.
2. Sort the four values per series so `P50 ≤ P70 ≤ P80 ≤ P90`.
3. Clip at 0, then round up to integers.
4. **Calibration (applied only if needed).** On the validation segment compute empirical coverage per quantile. If `|coverage − q| > 0.03`, compute `c_q` = the q-quantile of `Y / max(pred_q, 1)` and multiply that quantile's predictions by `c_q`, clipped to [0.85, 1.20]. The factors are stored in `meta.json`. Test coverage is measured after calibration.

### 4.6 Baseline and evaluation (FR-FCT-04/05)
- **MA9:** `9 × mean(daily sales over the last 7 days)`.
- **Metrics on test origins:** WAPE, bias, coverage per quantile, pinball loss, overall and by SKU and store. Stored in `forecast_metrics`, with every prediction in `forecast_eval`.
- **Targets (PRD §8.2):** WAPE ≤ 20% (floor 25%); ≥ 15% relative improvement over MA9 (floor 5%); P90 coverage 88–92% (floor 85–95%); bias within ±5% (floor ±10%).

**Design-time error analysis.** With negative-binomial noise (φ = 0.10), a 9-day total for a series averaging 40 units a day has a coefficient of variation near 12%, and a slow series averaging 18 units a day near 13%. That implies an **irreducible WAPE of roughly 8–13%**, so a target of 20% leaves room for model error. MA9 cannot anticipate festival, promo or weekday-mix effects inside the window, so it is expected to be clearly worse. These are expectations to be checked at the hour-16 gate, not results.

### 4.7 Cold start (P1, FR-FCT-09)
For a series with fewer than 28 days of history: forecast = category-average daily demand per size unit × store size × 9, with all four quantiles set from category-level empirical ratios. The series is flagged `COLD_START` and shown with a warning.

### 4.8 Artifacts and versioning
`data/models/<model_version>/` holds the four boosters, `meta.json` (dataset hash, seed, feature list, weekday index, calibration factors, library versions) and `metrics.json`. `model_version = lgbm_q_<8 hex of sha256(dataset_hash + feature list + params)>`.

### 4.9 Forecast tests

| Test | Pass condition |
|---|---|
| Leakage: change all sales after day *t* to random values | Features at origin *t* unchanged |
| Target alignment | `Y` equals the sum of days *t+1…t+9* for a hand-computed series |
| Split gap | No training target window overlaps a validation target window |
| Quantile order | No row with `P50 > P70 > …` after post-processing |
| Reproducibility | Same dataset and seed give the same `model_version` and predictions |
| Beats baseline | Test WAPE of the model below WAPE of MA9 (reported, with the gate on hour 16) |

---

## 5. Service-Level Design (FR-SVL-01…04)

**Derivation (newsvendor).** For one SKU in one cycle, ordering too few units costs the underage cost `Cu = margin × g` per unit short (lost margin plus loss of customer goodwill, with `g ∈ {1, 2, 4}`). Ordering too many costs the overage cost `Co = unit_cost × w + holding_cost` per unit left over (`w` = write-off factor 1.0 / 0.3 / 0.1 by shelf life). Expected cost is minimized by stocking to the quantile

`q* = Cu / (Cu + Co)`

This is the critical ratio of BR-02…BR-04. It gives low service levels for perishable low-margin items and high ones for staples.

**Mapping.** `q*` is mapped to the nearest trained quantile in {0.7, 0.8, 0.9} with ties to the higher one and a floor of 0.7 (default, configurable). The floor exists because retail goodwill costs are not fully captured by margin, and it protects the fill-rate KPI. SRS Appendix A lists the resulting quantile for all 12 SKUs (six at P70, five at P80, one at P90), which becomes the unit test.

**Target.** `target_q[s,p] = P_{q(p)}[s,p]` (integer). Because the model is global and the quantile depends only on the SKU, a store's target moves with its own forecast while the service level stays a product-level policy.

**Why the P70 floor is acceptable.** It is a business policy parameter, not a model result. The UI shows the mapping table, and the what-if "service floor" could be exposed as a P2 slider.

---

## 6. Optimization Design (FR-OPT-01…10, FR-SHL-01…04)

### 6.1 Model size and pruning
Candidate shipment variables exist only for `(w,s,p,b)` where the lane is eligible, `Λ[w,b,s] ≥ min_life[p]`, and `stock[w,p,b] > 0`. At the reference scale this is at most 4 × 25 × 12 × ~3 = 3,600 and in practice fewer. Expected size is about 3,000 integer shipment variables, 100 truck variables, 300 `u` and 300 `e` variables, and about 2,000 constraints. This is a small problem for CP-SAT. The expected solve time is 1–5 s, to be confirmed at the hour-24 gate.

### 6.2 Parameters (all integers after scaling)

| Symbol | Meaning | Unit |
|---|---|---|
| `stock[w,p,b]` | Batch quantity | units |
| `vol[p]` | Volume per unit | ml |
| `truck_cap` | 4,000,000 | ml |
| `lane_cost[w,s]` | `round(80,000 + 1,400 × km[w,s])` | paise per truck |
| `fleet[w]` | Trucks per warehouse | trucks |
| `store_cap[s]` | Storage volume | ml |
| `pos0[s,p]` | `onhand + intransit` | units |
| `target[s,p]` | `target_q` | units |
| `Cu[p]` | `margin × g` | paise per unit |
| `Ch[p]` | `round(0.018 × unit_cost)` | paise per unit |
| `Cw[b,s,p]` | Wastage coefficient (§6.5) | paise per unit |

**Objective scale.** All cost coefficients are multiplied by `K = 100`, so the objective is in 0.01 paise. This keeps the FEFO tie-break `ε = 1` (0.01 paise) negligible against every real cost while staying within 64-bit integers. Plan costs reported to users are divided by `K` again.

### 6.3 Decision variables
`x[w,s,p,b] ∈ [0, min(stock, store limit)]`, `y[w,s] ∈ [0, fleet[w]]`, `u[s,p] ∈ [0, target]`, `e[s,p] ≥ 0`. All integers.

### 6.4 Constraints

| # | Constraint | Form |
|---|---|---|
| C1 | Batch stock | `Σ_s x[w,s,p,b] ≤ stock[w,p,b]` |
| C2 | Coverage | `pos0[s,p] + Σ_{w,b} x[w,s,p,b] + u[s,p] ≥ target[s,p]` |
| C3 | Excess | `e[s,p] ≥ pos0[s,p] + Σ x − target[s,p]` |
| C4 | Truck volume | `Σ_{p,b} vol[p]·x[w,s,p,b] ≤ truck_cap · y[w,s]` |
| C5 | Fleet | `Σ_s y[w,s] ≤ fleet[w]` |
| C6 | Store capacity | `Σ_p vol[p]·(pos0[s,p] + Σ x[·,s,p,·]) ≤ store_cap[s]` |
| C7 | Shelf life on arrival | Variables not created when `Λ < min_life[p]` |
| C8 | Short-life sell-through | See below |
| C9 | Lane eligibility | Variables not created for excluded lanes |

**C8, exact form.** The SRS expression `P50·min(L,9)/9 + (target − P50)·min(L,9)/9` simplifies to `target × min(L,9)/9`. The cap matters only for short lives, so it is applied to levels `ℓ < 9`:

For each store *s*, SKU *p* and each distinct short level `ℓ` among its candidate shipments (and its on-hand and in-transit stock):

`Σ_{(w,b): Λ[w,b,s] ≤ ℓ} x[w,s,p,b]  ≤  max(0, ⌊target[s,p] × ℓ / 9⌋ − pos0_life≤ℓ[s,p])`

where `pos0_life≤ℓ` is the on-hand and in-transit stock whose remaining life at arrival is at most `ℓ`. Clipping the right side at 0 prevents infeasibility when existing stock already uses the cap. Batches with `Λ ≥ 9` have no hard cap. Their surplus is discouraged by the excess cost `e·Ch`, which allows a store to take a little more than its target when that fills a truck.

### 6.5 Objective

`minimize K × [ Σ lane_cost[w,s]·y[w,s] + Σ Cu[p]·u[s,p] + Σ Ch[p]·e[s,p] + Σ Cw[b,s,p]·x[w,s,p,b] ] + Σ ε·rank[b]·x[w,s,p,b]`

**Wastage coefficient.** `Cw[b,s,p] = round(unit_cost[p] × w[p] × π)` with

`π = clip(1 − min(P50_9d × min(Λ,9)/9, target) / target, 0, 1)` if `Λ ≤ 18`, otherwise 0.

Intuition: a shipment with short remaining life is wasted in proportion to how much of the stock cannot be sold before expiry. A shipment with a long remaining life can still be sold in later cycles, so it carries no wastage cost beyond holding.

**FEFO tie-break.** `rank[b]` is 0 for the earliest-expiring batch of a warehouse–SKU and increases by one for each later batch. It breaks ties only.

### 6.6 Warm start and solver settings
- **Greedy warm start (hint only).** For each store–SKU with a shortfall `max(0, target − pos0)`, take the eligible batch with the earliest expiry from the cheapest lane (`lane_cost / truck_cap`), respecting C1 and C8. Fill one store at a time in descending order of `Cu × shortfall`. Round trucks up. The solution is passed as `AddHint`, so the solver starts from a good incumbent. An infeasible hint is simply ignored.
- **CP-SAT parameters:** `max_time_in_seconds = 8`, `relative_gap_limit = 0.005`, `num_workers = 4` (interactive) or `1` (`deterministic`), `random_seed = 42`, `log_search_progress = false`.
- **Status mapping:** `OPTIMAL` → OPTIMAL; `FEASIBLE` (time limit hit with a solution) → FEASIBLE; anything else → `FALLBACK_ZERO` (all `x = 0`, `u = target`, which is always valid).
- **Determinism:** with `num_workers = 1`, a fixed seed and sorted variable creation order (by `w, s, p, b` codes), two runs give the same plan. Interactive runs with 4 workers may differ in tie-breaking, and therefore the backtest and tests use the deterministic mode.

### 6.7 Post-solve processing
1. **FEFO repair** (FR-SHL-04): for each warehouse–SKU, while a newer batch ships on a lane and an older batch that is C7-eligible and not C8-blocked for that store has spare stock, move `min(shipped_newer, spare_older)` units from newer to older. Quantity per lane is unchanged, so trucks and costs stay valid.
2. **Truck cost allocation** (FR-REC-04): lane cost is divided among the lane's lines in proportion to loaded volume, with the largest-remainder rule so the paise sum exactly.
3. **Cost decomposition:** transport, lost-sales, holding and wastage terms are recomputed from the final lines (independently of solver values) and stored in `plans`.
4. **Priority and unmet:** `cover_days = pos0 ÷ (P50_9d/9)`. `URGENT` if `cover_days ≤ transit_days`, `HIGH` if `≤ 3`, else `NORMAL`. `plan_unmet` and `margin_at_risk` come from `u`.

### 6.8 Why this model is suitable
- **Integer trucks per lane** capture economies of full loads, a decision that rules and proportional splits ignore.
- **Batch-level variables** let expiry shape the allocation rather than being fixed afterwards.
- **Lost-sales penalty with `g`** automatically ranks stores and SKUs when stock is short.
- **Always feasible** because the zero plan satisfies every constraint.

---

## 7. Plan-Checker Design (FR-CHK-01…05)

The checker is a separate package. Its inputs are plain data: the `Snapshot`, the plan lines, and the plan's `targets` table. It imports nothing from `optimize`, `forecast` or `sim`.

| # | Check | Implementation |
|---|---|---|
| 1 | Non-negative integers | Type and range test on every line |
| 2 | Batch stock | Group by `(w, batch)`; sum ≤ stock |
| 3 | Trucks | Per lane `ceil(loaded_ml / truck_cap) ≤ trucks_on_lane`; per warehouse `Σ trucks ≤ fleet` |
| 4 | Store capacity | `Σ vol × (pos0 + delivered)` per store |
| 5 | Shelf life | `expiry − (as_of + transit) ≥ min_life` |
| 6 | Lane eligibility | Lane exists and `eligible = 1` |
| 7 | FEFO invariant | For each warehouse–SKU and store with a newer batch shipped: every older batch must be exhausted, ineligible on the lane (C7/C9), or **C8-blocked**, meaning one more unit would exceed the short-life cap computed from `targets` |

Independent cost recompute (FR-OPT-04) is a separate test that uses the same pure functions. The mutation tests of FR-CHK-04 corrupt a valid plan once per check and confirm detection.

---

## 8. Explainability Computation (FR-EXP-01…05)

All codes are computed after solving, from the same arrays the solver used:

| Code | Computation |
|---|---|
| `LOW_COVER` | `cover_days < 3`; evidence: `cover_days`, `P50_9d`, chosen quantile value, `onhand`, `intransit` |
| `EXPIRY_FIRST` | The line's batch has the smallest `expiry` among batches with remaining stock at that warehouse for that SKU that are eligible on the lane; evidence: batch id and remaining life on arrival |
| `LOWEST_COST_SOURCE` | `lane_cost / truck_cap` is the minimum among eligible warehouses holding stock of the SKU; evidence lists the alternatives |
| `CAPACITY_LIMITED` | Truck fill ≥ 95% or store volume use ≥ 95% after delivery |
| `SCARCE_PRIORITY` | `Σ_s u[s,p] > 0` for the SKU network-wide and this line delivers ≥ 1 unit |
| `REPLENISH_TO_TARGET` | Default |
| `NEXT_BEST` (P1) | See §10.2 |

Tests recompute every evidence value from the stored snapshot and compare exactly (FR-EXP-03).

---

## 9. Baselines, Simulator and Ablation (FR-SIM-01…09)

### 9.1 Simulator state and daily loop
State: per store–SKU a list of `(expiry_day, qty)` sorted by expiry; per warehouse–SKU a list of batches; in-transit shipments with arrival days. Each day in 703…730: (1) add scheduled inbound (plan days only) and arrivals; (2) serve demand from `window_demand[seed]` FEFO, record unmet; (3) remove expired units at stores and warehouses and record wastage; (4) at the start of days 703, 710, 717, 724 (before step 1) call `policy.plan`, run the checker, and dispatch (arrival = day + transit).

### 9.2 Policies

| Policy | Demand input | Order rule | Notes |
|---|---|---|---|
| **B1** | `m28` = mean daily sales over the last 28 days | `need = max(0, round(9 × m28) − position)` | Nearest eligible warehouse with stock, FEFO, then the next nearest |
| **B2** | `m28` | `need = max(0, round(1.25 × 9 × m28) − position)` | Same sourcing |
| **O-MA** | `ma7` = mean of last 7 days | Same optimizer, `P50_9d = 9 × ma7`, `target = ceil(1.25 × 9 × ma7)` for every SKU | Isolates the effect of quantile forecasts and service levels |
| **VitaranIQ** | Quantile forecasts and critical-ratio targets | Same optimizer | Full system |

**Rules shared by baselines.** They respect hard physical rules so that their plans pass the checker: min-life on arrival (C7), lane eligibility (C9), batch stock (C1), fleet (C5) and store capacity (C6) with orders trimmed to fit. They do **not** use the short-life sell-through cap, quantile targets, margin-based prioritization, or truck-fill optimization. Under scarcity, stock at a warehouse–SKU is shared pro rata to requests (largest-remainder rounding). Trucks per lane are `ceil(volume / truck_cap)`.

### 9.3 KPI computation
Raw sums per run go to `sim_results` and `sim_daily`. KPIs are derived only in the database view `v_sim_kpis` (BR-05). The strongest baseline is the better of B1 and B2 on each KPI, averaged over seeds (BR-06).

### 9.4 Runtime budget
There are 40 tasks (4 policies × 5 seeds × 2 scenarios). The 20 optimizer-based tasks each solve 4 plans with a limit of 8 s, which is at most 640 s of CPU spread over 4 processes, about 160 s. The 20 baseline tasks take seconds.

### 9.5 Ablation and reporting protocol
- **AI contribution:** `(Cost(O-MA) − Cost(VitaranIQ)) ÷ Cost(O-MA)` on `total_cost = transport + lost margin + wastage`.
- **Optimizer contribution:** `(Cost(strongest baseline) − Cost(O-MA)) ÷ Cost(strongest baseline)`.
- Report the mean and the min–max over the 5 seeds, plus the number of seeds in which the sign of the difference is favourable. With 5 seeds no statistical significance is claimed. The UI shows the spread instead.
- A KPI is marked *met*, *below target* or *below floor* using the PRD thresholds. Misses are displayed, not hidden.

---

## 10. What-If and Counterfactual Design

### 10.1 What-if (FR-WIF)
- **Warehouse outage (P0):** set all batches of the chosen warehouse to quantity 0, mark its lanes ineligible, and re-solve the full problem. The delta compares transport paise, unmet units, margin at risk, truck count and the list of stores whose lines changed.
- **Demand spike (P1):** multiply all four quantiles of the selected stores by the factor before service-level mapping, then re-solve.
- **Fuel price (P1):** multiply the per-km part of `lane_cost` by the factor.

### 10.2 Counterfactual `NEXT_BEST` (P1)
For a plan line `(w, s, p)`: forbid warehouse *w* for store–SKU `(s, p)`, fix every other store–SKU's shipment variables to the base plan, free the `y` variables of lanes into store *s*, and re-solve with a 2 s limit. Because only one store–SKU is free, the sub-problem is tiny and solves in well under a second. The delta of the objective is stored as `delta_cost_paise`.

---

## 11. Verification Plan and Gates

| Area | Tests |
|---|---|
| Generator | Determinism hash, moment checks (§3), validation rules V1–V8 |
| Forecast | §4.9 tests; coverage and WAPE report |
| Service level | Fixed SKU table reproduces SRS Appendix A quantiles |
| Optimizer correctness | **Brute-force comparison:** 1 warehouse, 2 stores, 1 SKU, 2 batches, small integer quantities. The CP-SAT optimum must equal the exhaustive optimum. Repeat on 50 random tiny instances. |
| Constraint tests | One crafted instance per constraint C1–C9 where the unconstrained solution would violate it |
| Property test | 20 random seeds on the full network: every plan passes the checker; unmet + delivered satisfy coverage identity |
| Cost integrity | Independent recompute of cost components equals solver objective components within ₹0.01 |
| Determinism | Two deterministic runs give identical lines |
| Simulator accounting | Stock conservation: `initial + inbound + delivered = sold + expired + final` for every store–SKU and warehouse–SKU |
| Baselines | Each baseline plan passes the checker on all seeds |
| Performance | Plan generation ≤ 15 s; training ≤ 5 min; full backtest ≤ 15 min |

**Acceptance gates**

| Hour | Gate | Evidence |
|---|---|---|
| 6 | Data generator complete | Hash test passes, moment checks pass |
| 16 | Model vs baseline | WAPE and coverage report; if the model does not beat MA9, investigate features and the generator before proceeding |
| 24 | End-to-end plan | Forecast → optimizer → checker runs on the full network in ≤ 15 s |
| 30 | Backtest | All four policies run on one seed; accounting tests pass |

---

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Model does not clearly beat MA9 | Weak AI claim | Promo and festival calendars are known-future features; weekday-mix feature; if the gap is small, report it honestly and show the optimizer's own contribution through B1/B2 vs O-MA |
| Quantile miscalibration | Wrong service levels | Validation-based multiplicative calibration (§4.5); coverage shown in the UI |
| Solver slower than expected | Misses 15 s budget | 8 s limit, warm start, pruning, relative gap 0.5%, fallback plan |
| Truck fill below 80% target | KPI miss | Excess allowed for long-life SKUs to fill trucks; parameters in SRS Appendix A; change control if first run shows < 70% |
| P70 floor hides differentiation | Less visible newsvendor effect | Floor is configurable and the mapping table is displayed |
| Synthetic data too easy | Inflated accuracy | State the limitation (SRS §11); noise and promo shocks included; benchmark on a public dataset as a side check |
| Backtest unfair to baselines | Credibility | Same physical rules and checker for all policies; baseline logic documented in §9.2 |
| CP-SAT non-determinism with several workers | Irreproducible figures | Deterministic mode for tests and backtest |

---

## 13. Refinements to SRS and PRD Required by This Design

| # | Item | Change |
|---|---|---|
| 1 | SRS C8 / FR-OPT-02 | Apply the sell-through cap only to short levels `ℓ < 9`, in the exact form of §6.4, with the right side clipped at 0. The expression `P50·L/9 + safety·L/9` equals `target·L/9`. |
| 2 | SRS FR-SHL-02 | The wastage coefficient includes the write-off factor and an 18-day exposure horizon: `Cw = unit_cost × w × π`, with `π` in §6.5. |
| 3 | SRS FR-OPT-04 | Costs are scaled to 0.01 paise (`K = 100`) inside the solver, so that the FEFO tie-break `ε = 1` is negligible. Reported costs remain in paise. |
| 4 | SRS FR-CHK-01 / FR-SHL-03 | The checker also reads the plan's `targets`, and the FEFO invariant allows an older batch to be skipped when it is C8-blocked. |
| 5 | SRS FR-SIM-03 | Baselines obey C1, C5, C6, C7 and C9 but not C8 or quantile logic (§9.2). |
| 6 | PRD F-03 and §6.5 (carried over from the SRS review) | Replace `(1 + criticality)` by the stockout multiplier `g ∈ {1, 2, 4}`; state the P70 minimum service quantile and the {P70, P80, P90} mapping. |

---

## 14. Traceability

| SRS area | Section of this document |
|---|---|
| FR-DAT | §3 |
| FR-FCT | §4 |
| FR-SVL | §5 |
| FR-OPT, FR-SHL | §6 |
| FR-CHK | §7 |
| FR-EXP | §8 |
| FR-SIM | §9 |
| FR-WIF, FR-EXP-04 | §10 |
| NFR-REL, NFR-PERF, NFR-MNT | §6.6, §9.4, §11 |
