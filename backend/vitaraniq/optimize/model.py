"""
OR-Tools CP-SAT Integer Program Formulation for VitaranIQ.
Implements FR-OPT-01..10, FR-SHL-01..02, and AIML Design §6.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import time
from ortools.sat.python import cp_model

from vitaraniq.core.config import SystemParams, load_params
from vitaraniq.db.snapshot import Snapshot
from vitaraniq.optimize.waste import compute_holding_cost_paise, compute_lane_cost_paise, compute_waste_coeff
from vitaraniq.service_level.newsvendor import Targets


@dataclass
class RawPlan:
    status: str  # "OPTIMAL", "FEASIBLE", "FALLBACK_ZERO"
    gap_pct: float
    solve_time_s: float
    shipments: List[Dict[str, Any]]  # list of {"warehouse_id", "store_id", "sku_id", "batch_id", "qty", "expiry_day"}
    trucks_on_lane: Dict[Tuple[str, str], int]  # (w, s) -> trucks
    unmet_demand: Dict[Tuple[str, str], int]    # (s, p) -> unmet_units
    excess_stock: Dict[Tuple[str, str], int]    # (s, p) -> excess_units
    total_cost_paise: int
    transport_paise: int
    lost_sales_paise: int
    holding_paise: int
    wastage_paise: int


def build_and_solve_cpsat(
    snapshot: Snapshot,
    targets: Targets,
    params: SystemParams = None,
    time_limit_s: float = 8.0,
    deterministic: bool = False,
    workers: int = 4,
    unavailable_warehouses: Optional[List[str]] = None,
) -> RawPlan:
    """Build and solve CP-SAT integer program under constraints C1–C9."""
    if params is None:
        params = load_params()

    t_start = time.perf_counter()
    model = cp_model.CpModel()
    as_of = snapshot.as_of_day
    K = params.optimization.objective_scale_k  # 100

    unavail_wh = set(unavailable_warehouses or [])
    truck_cap_ml = params.network.trucks.capacity_ml

    # Dictionaries for quick lookup
    prod_map = {p["sku_id"]: p for p in snapshot.products}
    store_map = {s["store_id"]: s for s in snapshot.stores}
    wh_map = {w["warehouse_id"]: w for w in snapshot.warehouses}

    # 1. Prune candidate variables (w, s, p, b)
    # Group batches by (w, p) and sort by expiry
    wh_sku_batches = {}
    for b in snapshot.batches:
        if b["warehouse_id"] in unavail_wh or b["qty"] <= 0:
            continue
        key = (b["warehouse_id"], b["sku_id"])
        if key not in wh_sku_batches:
            wh_sku_batches[key] = []
        wh_sku_batches[key].append(b)

    for k in wh_sku_batches:
        wh_sku_batches[k].sort(key=lambda x: x["expiry_day"])

    # Decision variables
    x_vars: Dict[Tuple[str, str, str, str], cp_model.IntVar] = {}
    x_metadata: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    batch_shipments = {b["batch_id"]: [] for b in snapshot.batches}
    lane_shipments = {(w["warehouse_id"], s["store_id"]): [] for w in snapshot.warehouses for s in snapshot.stores}
    store_sku_shipments = {(s["store_id"], p["sku_id"]): [] for s in snapshot.stores for p in snapshot.products}

    # FEFO tie break age ranks
    age_ranks = {}
    for (w_id, sku_id), b_list in wh_sku_batches.items():
        for r_idx, b in enumerate(b_list):
            age_ranks[b["batch_id"]] = r_idx

    for (w_id, sku_id), b_list in wh_sku_batches.items():
        p_info = prod_map[sku_id]
        min_life = p_info["min_life_days"]
        vol = p_info["volume_ml"]

        for s in snapshot.stores:
            s_id = s["store_id"]
            lane_info = snapshot.lanes.get((w_id, s_id))
            if not lane_info or lane_info.get("eligible", 0) != 1:
                continue  # C9: lane ineligible

            transit = lane_info.get("transit_days", 1)

            for b in b_list:
                b_id = b["batch_id"]
                b_exp = b["expiry_day"]
                rem_life = b_exp - (as_of + transit)

                if rem_life < min_life:
                    continue  # C7: shelf life on arrival

                # Variable upper bound
                ub = min(b["qty"], s["storage_cap_ml"] // max(vol, 1))
                var_name = f"x_{w_id}_{s_id}_{sku_id}_{b_id}"
                x_var = model.NewIntVar(0, ub, var_name)
                
                var_key = (w_id, s_id, sku_id, b_id)
                x_vars[var_key] = x_var
                x_metadata[var_key] = {
                    "warehouse_id": w_id,
                    "store_id": s_id,
                    "sku_id": sku_id,
                    "batch_id": b_id,
                    "expiry_day": b_exp,
                    "rem_life": rem_life,
                    "volume_ml": vol,
                }

                batch_shipments[b_id].append(x_var)
                lane_shipments[(w_id, s_id)].append((x_var, vol))
                store_sku_shipments[(s_id, sku_id)].append(x_var)

    # Truck variables y[w, s]
    y_vars: Dict[Tuple[str, str], cp_model.IntVar] = {}
    wh_trucks = {w["warehouse_id"]: [] for w in snapshot.warehouses}

    for w in snapshot.warehouses:
        w_id = w["warehouse_id"]
        fleet = 0 if w_id in unavail_wh else w["fleet"]

        for s in snapshot.stores:
            s_id = s["store_id"]
            y_var = model.NewIntVar(0, fleet, f"y_{w_id}_{s_id}")
            y_vars[(w_id, s_id)] = y_var
            wh_trucks[w_id].append(y_var)

    # Unmet and Excess variables
    u_vars: Dict[Tuple[str, str], cp_model.IntVar] = {}
    e_vars: Dict[Tuple[str, str], cp_model.IntVar] = {}

    for s in snapshot.stores:
        s_id = s["store_id"]
        for p in snapshot.products:
            sku_id = p["sku_id"]
            t_obj = targets.get(s_id, sku_id)
            target_val = t_obj.target_q

            u_var = model.NewIntVar(0, max(0, target_val), f"u_{s_id}_{sku_id}")
            e_var = model.NewIntVar(0, s["storage_cap_ml"] // max(p["volume_ml"], 1), f"e_{s_id}_{sku_id}")

            u_vars[(s_id, sku_id)] = u_var
            e_vars[(s_id, sku_id)] = e_var

    # ──────────────── CONSTRAINTS ────────────────
    # C1: Batch stock constraint
    for b in snapshot.batches:
        b_id = b["batch_id"]
        shipped = batch_shipments.get(b_id, [])
        if shipped:
            model.Add(sum(shipped) <= b["qty"])

    # C2 & C3: Coverage and Excess
    for s in snapshot.stores:
        s_id = s["store_id"]
        for p in snapshot.products:
            sku_id = p["sku_id"]
            t_obj = targets.get(s_id, sku_id)
            target_val = t_obj.target_q
            pos0 = t_obj.onhand + t_obj.intransit

            shipped_vars = store_sku_shipments.get((s_id, sku_id), [])
            sum_x = sum(shipped_vars) if shipped_vars else 0

            # C2: pos0 + sum(x) + u >= target
            model.Add(pos0 + sum_x + u_vars[(s_id, sku_id)] >= target_val)

            # C3: e >= pos0 + sum(x) - target
            model.Add(e_vars[(s_id, sku_id)] >= pos0 + sum_x - target_val)

    # C4: Truck volume
    for (w_id, s_id), vol_pairs in lane_shipments.items():
        if vol_pairs:
            model.Add(
                sum(var * vol for var, vol in vol_pairs) <= truck_cap_ml * y_vars[(w_id, s_id)]
            )
        else:
            model.Add(y_vars[(w_id, s_id)] == 0)

    # C5: Warehouse fleet limit
    for w_id, y_list in wh_trucks.items():
        fleet = 0 if w_id in unavail_wh else wh_map[w_id]["fleet"]
        model.Add(sum(y_list) <= fleet)

    # C6: Store storage capacity
    for s in snapshot.stores:
        s_id = s["store_id"]
        store_cap = s["storage_cap_ml"]
        store_vol_terms = []

        for p in snapshot.products:
            sku_id = p["sku_id"]
            vol = p["volume_ml"]
            t_obj = targets.get(s_id, sku_id)
            pos0 = t_obj.onhand + t_obj.intransit

            store_vol_terms.append(pos0 * vol)
            for x_var in store_sku_shipments.get((s_id, sku_id), []):
                store_vol_terms.append(x_var * vol)

        model.Add(sum(store_vol_terms) <= store_cap)

    # C8: Short-life sell-through cap (for levels ell < 9)
    for s in snapshot.stores:
        s_id = s["store_id"]
        for p in snapshot.products:
            sku_id = p["sku_id"]
            t_obj = targets.get(s_id, sku_id)
            target_val = t_obj.target_q

            # Find distinct remaining-life levels ell < 9
            candidate_rem_lives = set()
            for (w_id, st_id, p_id, b_id), meta in x_metadata.items():
                if st_id == s_id and p_id == sku_id and meta["rem_life"] < 9:
                    candidate_rem_lives.add(meta["rem_life"])

            # On-hand remaining life
            onhand_info = snapshot.store_onhand.get((s_id, sku_id))
            if onhand_info:
                onhand_rem = onhand_info["expiry_day"] - as_of
                if onhand_rem < 9:
                    candidate_rem_lives.add(onhand_rem)

            for ell in sorted(list(candidate_rem_lives)):
                # Units arriving with life <= ell
                short_x_vars = []
                for (w_id, st_id, p_id, b_id), meta in x_metadata.items():
                    if st_id == s_id and p_id == sku_id and meta["rem_life"] <= ell:
                        short_x_vars.append(x_vars[(w_id, st_id, p_id, b_id)])

                onhand_short = 0
                if onhand_info and (onhand_info["expiry_day"] - as_of) <= ell:
                    onhand_short = onhand_info["qty"]

                cap_ell = max(0, math.floor(target_val * ell / 9.0) - onhand_short)
                if short_x_vars:
                    model.Add(sum(short_x_vars) <= cap_ell)

    # ──────────────── OBJECTIVE ────────────────
    # Scaled by K = 100
    obj_terms = []

    # 1. Transport cost
    for (w_id, s_id), y_var in y_vars.items():
        lane_info = snapshot.lanes.get((w_id, s_id))
        km = lane_info["km"] if lane_info else 100.0
        cost_paise = compute_lane_cost_paise(
            km, params.network.trucks.fixed_cost_paise, params.network.trucks.cost_per_km_paise
        )
        obj_terms.append(K * cost_paise * y_var)

    # 2. Lost sales penalty u * margin * g
    for (s_id, sku_id), u_var in u_vars.items():
        p_info = prod_map[sku_id]
        cu_paise = p_info["margin_paise"] * p_info["stockout_mult"]
        obj_terms.append(K * cu_paise * u_var)

    # 3. Holding excess cost e * holding_cost
    for (s_id, sku_id), e_var in e_vars.items():
        p_info = prod_map[sku_id]
        ch_paise = compute_holding_cost_paise(p_info["unit_cost_paise"], params.optimization.holding_cost_rate)
        obj_terms.append(K * ch_paise * e_var)

    # 4. Expected wastage Cw * x + FEFO tie break eps * rank
    for var_key, x_var in x_vars.items():
        w_id, s_id, sku_id, b_id = var_key
        meta = x_metadata[var_key]
        p_info = prod_map[sku_id]
        t_obj = targets.get(s_id, sku_id)

        cw_paise = compute_waste_coeff(
            unit_cost_paise=p_info["unit_cost_paise"],
            write_off_factor=p_info["write_off_factor"],
            rem_life_arrival=meta["rem_life"],
            p50_9d=t_obj.p50_9d,
            target_q=t_obj.target_q,
        )
        rank = age_ranks.get(b_id, 0)
        # FEFO priority: older batch (lower rank) preferred
        obj_terms.append((K * cw_paise + K * 10 * rank) * x_var)

    model.Minimize(sum(obj_terms))

    # ──────────────── WARM START (GREEDY INCUMBENT) ────────────────
    # Greedily allocate shortfalls from oldest eligible batches on cheapest lanes
    try:
        shortfalls = []
        for s in snapshot.stores:
            s_id = s["store_id"]
            for p in snapshot.products:
                sku_id = p["sku_id"]
                t_obj = targets.get(s_id, sku_id)
                sf = max(0, t_obj.target_q - (t_obj.onhand + t_obj.intransit))
                if sf > 0:
                    shortfalls.append((s_id, sku_id, sf, p["margin_paise"] * p["stockout_mult"]))

        # Sort descending by margin penalty
        shortfalls.sort(key=lambda x: x[3], reverse=True)
        rem_batch_stock = {b["batch_id"]: b["qty"] for b in snapshot.batches if b["warehouse_id"] not in unavail_wh}

        for s_id, sku_id, sf, _ in shortfalls:
            needed = sf
            # Candidate batches
            cand = []
            for (w_id, st_id, p_id, b_id), meta in x_metadata.items():
                if st_id == s_id and p_id == sku_id and rem_batch_stock.get(b_id, 0) > 0:
                    cand.append((b_id, (w_id, st_id, p_id, b_id), meta["expiry_day"]))
            cand.sort(key=lambda x: x[2])  # oldest first

            for b_id, vkey, _ in cand:
                avail = rem_batch_stock[b_id]
                alloc = min(needed, avail)
                model.AddHint(x_vars[vkey], alloc)
                rem_batch_stock[b_id] -= alloc
                needed -= alloc
                if needed <= 0:
                    break
    except Exception:
        pass

    # ──────────────── SOLVER EXECUTION ────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.relative_gap_limit = params.optimization.relative_gap_limit
    solver.parameters.random_seed = 42

    if deterministic:
        solver.parameters.num_workers = 1
    else:
        solver.parameters.num_workers = workers

    status_code = solver.Solve(model)
    t_solve = round(time.perf_counter() - t_start, 3)

    if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status_str = "OPTIMAL" if status_code == cp_model.OPTIMAL else "FEASIBLE"
        gap_pct = round(100.0 * (solver.ObjectiveValue() - solver.BestObjectiveBound()) / max(1.0, abs(solver.ObjectiveValue())), 2) if status_code == cp_model.FEASIBLE else 0.0

        shipments = []
        trucks_lane = {}
        unmet = {}
        excess = {}

        for var_key, x_var in x_vars.items():
            qty = int(solver.Value(x_var))
            if qty > 0:
                meta = x_metadata[var_key]
                shipments.append({
                    "warehouse_id": meta["warehouse_id"],
                    "store_id": meta["store_id"],
                    "sku_id": meta["sku_id"],
                    "batch_id": meta["batch_id"],
                    "qty": qty,
                    "expiry_day": meta["expiry_day"],
                })

        for (w_id, s_id), y_var in y_vars.items():
            val = int(solver.Value(y_var))
            trucks_lane[(w_id, s_id)] = val

        tot_transport = 0
        for (w_id, s_id), trks in trucks_lane.items():
            lane_info = snapshot.lanes.get((w_id, s_id))
            km = lane_info["km"] if lane_info else 100.0
            cost_paise = compute_lane_cost_paise(
                km, params.network.trucks.fixed_cost_paise, params.network.trucks.cost_per_km_paise
            )
            tot_transport += trks * cost_paise

        tot_lost_sales = 0
        for (s_id, sku_id), u_var in u_vars.items():
            u_val = int(solver.Value(u_var))
            unmet[(s_id, sku_id)] = u_val
            p_info = prod_map[sku_id]
            tot_lost_sales += u_val * p_info["margin_paise"] * p_info["stockout_mult"]

        tot_holding = 0
        for (s_id, sku_id), e_var in e_vars.items():
            e_val = int(solver.Value(e_var))
            excess[(s_id, sku_id)] = e_val
            p_info = prod_map[sku_id]
            tot_holding += e_val * compute_holding_cost_paise(p_info["unit_cost_paise"])

        tot_wastage = 0
        for sh in shipments:
            s_id = sh["store_id"]
            sku_id = sh["sku_id"]
            t_obj = targets.get(s_id, sku_id)
            p_info = prod_map[sku_id]
            lane_info = snapshot.lanes.get((sh["warehouse_id"], s_id))
            transit = lane_info.get("transit_days", 1) if lane_info else 1
            rem_life = sh["expiry_day"] - (as_of + transit)

            cw = compute_waste_coeff(
                unit_cost_paise=p_info["unit_cost_paise"],
                write_off_factor=p_info["write_off_factor"],
                rem_life_arrival=rem_life,
                p50_9d=t_obj.p50_9d,
                target_q=t_obj.target_q,
            )
            tot_wastage += sh["qty"] * cw

        total_cost = tot_transport + tot_lost_sales + tot_holding + tot_wastage

        return RawPlan(
            status=status_str,
            gap_pct=gap_pct,
            solve_time_s=t_solve,
            shipments=shipments,
            trucks_on_lane=trucks_lane,
            unmet_demand=unmet,
            excess_stock=excess,
            total_cost_paise=total_cost,
            transport_paise=tot_transport,
            lost_sales_paise=tot_lost_sales,
            holding_paise=tot_holding,
            wastage_paise=tot_wastage,
        )

    # Fallback zero plan (FR-OPT-06)
    unmet = {}
    tot_lost_sales = 0
    for s in snapshot.stores:
        s_id = s["store_id"]
        for p in snapshot.products:
            sku_id = p["sku_id"]
            t_obj = targets.get(s_id, sku_id)
            unmet[(s_id, sku_id)] = t_obj.target_q
            tot_lost_sales += t_obj.target_q * p["margin_paise"] * p["stockout_mult"]

    return RawPlan(
        status="FALLBACK_ZERO",
        gap_pct=0.0,
        solve_time_s=t_solve,
        shipments=[],
        trucks_on_lane={},
        unmet_demand=unmet,
        excess_stock={},
        total_cost_paise=tot_lost_sales,
        transport_paise=0,
        lost_sales_paise=tot_lost_sales,
        holding_paise=0,
        wastage_paise=0,
    )
