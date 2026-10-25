"""
Explainability & Priority Assignment Engine.
Implements FR-REC-04, FR-EXP-01..03, and AIML Design §8.
Computes ground-truth reason codes and proportional lane cost allocation.
"""

from typing import Any, Dict, List, Tuple
from collections import defaultdict
import math

from vitaraniq.db.snapshot import Snapshot
from vitaraniq.optimize.model import RawPlan
from vitaraniq.optimize.waste import compute_lane_cost_paise
from vitaraniq.service_level.newsvendor import Targets


def explain_and_format_plan_lines(
    snapshot: Snapshot,
    targets: Targets,
    raw_plan: RawPlan,
    as_of_day: int = 703,
    truck_cap_ml: int = 4000000,
) -> List[Dict[str, Any]]:
    """
    Format plan lines with reason codes, priority, and allocated truck costs.
    100% of lines receive >= 1 verified reason code with numeric evidence.
    """
    prod_map = {p["sku_id"]: p for p in snapshot.products}
    store_map = {s["store_id"]: s for s in snapshot.stores}

    # Group shipments by lane to allocate truck costs proportionally
    lane_lines = defaultdict(list)
    lane_volume = defaultdict(int)

    # Compute network-wide unmet demand per SKU
    network_unmet_per_sku = defaultdict(int)
    for (s_id, sku_id), unmet_units in raw_plan.unmet_demand.items():
        network_unmet_per_sku[sku_id] += unmet_units

    # Group warehouse stock by (warehouse_id, sku_id)
    wh_sku_batches = defaultdict(list)
    for b in snapshot.batches:
        if b["qty"] > 0:
            wh_sku_batches[(b["warehouse_id"], b["sku_id"])].append(b)
    for k in wh_sku_batches:
        wh_sku_batches[k].sort(key=lambda x: x["expiry_day"])

    # First pass: collect lines and volumes
    for sh in raw_plan.shipments:
        w_id = sh["warehouse_id"]
        s_id = sh["store_id"]
        sku_id = sh["sku_id"]
        vol_ml = sh["qty"] * prod_map[sku_id]["volume_ml"]
        
        lane_key = (w_id, s_id)
        lane_lines[lane_key].append(sh)
        lane_volume[lane_key] += vol_ml

    # Compute store post-delivery volume usage
    store_delivered_vol = defaultdict(int)
    for (w_id, s_id), vol in lane_volume.items():
        store_delivered_vol[s_id] += vol

    store_vol_use_pct = {}
    for s_id, s_info in store_map.items():
        cap = s_info["storage_cap_ml"]
        onhand_vol = sum(
            snapshot.store_onhand.get((s_id, p["sku_id"]), {}).get("qty", 0) * p["volume_ml"]
            for p in snapshot.products
        )
        tot_v = onhand_vol + store_delivered_vol[s_id]
        store_vol_use_pct[s_id] = round(100.0 * tot_v / max(1, cap), 1)

    formatted_lines = []
    line_no = 1

    for (w_id, s_id), sh_list in lane_lines.items():
        lane_info = snapshot.lanes.get((w_id, s_id))
        km = lane_info["km"] if lane_info else 100.0
        transit = lane_info.get("transit_days", 1) if lane_info else 1
        num_trucks = raw_plan.trucks_on_lane.get((w_id, s_id), 1)

        # Lane truck cost in paise
        lane_truck_cost_paise = num_trucks * compute_lane_cost_paise(km)
        tot_lane_vol = lane_volume[(w_id, s_id)]
        truck_fill_pct = round(100.0 * tot_lane_vol / max(1, num_trucks * truck_cap_ml), 1)

        # Allocate lane truck cost using largest-remainder rule
        raw_shares = [
            (sh["qty"] * prod_map[sh["sku_id"]]["volume_ml"] * lane_truck_cost_paise) / max(1, tot_lane_vol)
            for sh in sh_list
        ]
        int_shares = [int(math.floor(s)) for s in raw_shares]
        rem_paise = lane_truck_cost_paise - sum(int_shares)
        remainders = [(i, raw_shares[i] - int_shares[i]) for i in range(len(raw_shares))]
        remainders.sort(key=lambda x: x[1], reverse=True)
        for i in range(rem_paise):
            int_shares[remainders[i][0]] += 1

        for idx, sh in enumerate(sh_list):
            sku_id = sh["sku_id"]
            qty = sh["qty"]
            b_id = sh["batch_id"]
            b_exp = sh["expiry_day"]
            p_info = prod_map[sku_id]
            t_obj = targets.get(s_id, sku_id)

            pos_before = t_obj.onhand + t_obj.intransit
            pos_after = pos_before + qty
            p50_daily = max(0.1, t_obj.p50_9d / 9.0)
            cover_days = round(pos_before / p50_daily, 1)

            # Assign priority (FR-OPT-08)
            if cover_days <= transit:
                priority = "URGENT"
            elif cover_days <= 3.0:
                priority = "HIGH"
            else:
                priority = "NORMAL"

            # Compute Reason Codes (FR-EXP-01)
            reason_codes = []

            # 1. LOW_COVER
            if cover_days < 3.0:
                reason_codes.append({
                    "code": "LOW_COVER",
                    "evidence": {
                        "cover_days": cover_days,
                        "p50_9d": t_obj.p50_9d,
                        "selected_quantile_val": t_obj.target_q,
                        "onhand": t_obj.onhand,
                        "intransit": t_obj.intransit,
                    }
                })

            # 2. EXPIRY_FIRST
            wh_batches = wh_sku_batches.get((w_id, sku_id), [])
            # Earliest eligible batch
            earliest_eligible_b = None
            for cand_b in wh_batches:
                r_arr = cand_b["expiry_day"] - (as_of_day + transit)
                if r_arr >= p_info["min_life_days"]:
                    earliest_eligible_b = cand_b
                    break

            if earliest_eligible_b and earliest_eligible_b["batch_id"] == b_id:
                rem_life_arr = b_exp - (as_of_day + transit)
                reason_codes.append({
                    "code": "EXPIRY_FIRST",
                    "evidence": {
                        "batch_id": b_id,
                        "expires_in_days_on_arrival": rem_life_arr,
                    }
                })

            # 3. LOWEST_COST_SOURCE
            # Compare lane cost per litre across eligible warehouses with stock
            cur_lane_cost_per_l = round(compute_lane_cost_paise(km) / (truck_cap_ml / 1000.0) / 100.0, 2)
            alt_costs = []
            is_lowest = True
            for other_w in snapshot.warehouses:
                other_w_id = other_w["warehouse_id"]
                if other_w_id == w_id:
                    continue
                other_lane = snapshot.lanes.get((other_w_id, s_id))
                if other_lane and other_lane.get("eligible", 0) == 1:
                    has_stock = any(b["qty"] > 0 for b in wh_sku_batches.get((other_w_id, sku_id), []))
                    if has_stock:
                        other_cost_l = round(compute_lane_cost_paise(other_lane["km"]) / (truck_cap_ml / 1000.0) / 100.0, 2)
                        alt_costs.append({"warehouse": other_w_id, "cost_per_litre_inr": other_cost_l})
                        if other_cost_l < cur_lane_cost_per_l:
                            is_lowest = False

            if is_lowest and len(alt_costs) > 0:
                reason_codes.append({
                    "code": "LOWEST_COST_SOURCE",
                    "evidence": {
                        "lane_cost_per_litre": cur_lane_cost_per_l,
                        "alternatives": alt_costs,
                    }
                })

            # 4. CAPACITY_LIMITED
            store_pct = store_vol_use_pct.get(s_id, 0.0)
            if truck_fill_pct >= 95.0 or store_pct >= 95.0:
                reason_codes.append({
                    "code": "CAPACITY_LIMITED",
                    "evidence": {
                        "truck_fill_pct": truck_fill_pct,
                        "store_use_pct": store_pct,
                    }
                })

            # 5. SCARCE_PRIORITY
            net_unmet = network_unmet_per_sku.get(sku_id, 0)
            if net_unmet > 0 and qty > 0:
                margin_risk_inr = round((net_unmet * p_info["margin_paise"]) / 100.0, 2)
                reason_codes.append({
                    "code": "SCARCE_PRIORITY",
                    "evidence": {
                        "network_unmet_units": net_unmet,
                        "margin_at_risk_inr": margin_risk_inr,
                    }
                })

            # 6. REPLENISH_TO_TARGET fallback
            if len(reason_codes) == 0:
                reason_codes.append({
                    "code": "REPLENISH_TO_TARGET",
                    "evidence": {
                        "target_q": t_obj.target_q,
                        "position_before": pos_before,
                        "position_after": pos_after,
                    }
                })

            formatted_lines.append({
                "line_no": line_no,
                "sku_id": sku_id,
                "warehouse_id": w_id,
                "store_id": s_id,
                "batch_id": b_id,
                "batch_expiry_day": b_exp,
                "qty": qty,
                "trucks_on_lane": num_trucks,
                "line_cost_paise": int_shares[idx],
                "line_cost_inr": round(int_shares[idx] / 100.0, 2),
                "priority": priority,
                "reason_codes": reason_codes,
            })
            line_no += 1

    return formatted_lines
