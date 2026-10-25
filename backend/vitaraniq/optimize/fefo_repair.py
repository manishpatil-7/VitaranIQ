"""
Deterministic FEFO Repair Module.
Implements FR-SHL-03, FR-SHL-04, and AIML Design §6.7.
Swaps shipment quantities from newer to older eligible batches without changing
lane totals or violating C7 (shelf life on arrival) or C8 (sell-through cap).
"""

from typing import Any, Dict, List, Tuple
from collections import defaultdict
import math

from vitaraniq.service_level.newsvendor import Targets


def apply_fefo_repair(
    raw_shipments: List[Dict],
    batches_stock: Dict[str, int],  # batch_id -> initial stock
    all_batches: List[Dict],       # all warehouse batches: [{"batch_id", "warehouse_id", "sku_id", "qty", "expiry_day"}]
    lanes_transit: Dict[Tuple[str, str], int],
    sku_min_life: Dict[str, int],
    as_of_day: int,
    targets: Targets = None,
    store_onhand: Dict[Tuple[str, str], int] = None,
) -> List[Dict]:
    """
    Ensure FEFO invariant within every (warehouse, sku):
    If a newer batch ships to store s, an older eligible batch cannot have remaining stock
    unless it is C8-blocked.
    Swaps units deterministically to older batches.
    """
    if store_onhand is None:
        store_onhand = {}

    # Map all batches by (warehouse_id, sku_id)
    wh_sku_all = defaultdict(list)
    for b in all_batches:
        wh_sku_all[(b["warehouse_id"], b["sku_id"])].append(b)
    for k in wh_sku_all:
        wh_sku_all[k].sort(key=lambda x: x["expiry_day"])

    # Track remaining stock per batch
    rem_stock = dict(batches_stock)
    for sh in raw_shipments:
        b_id = sh["batch_id"]
        rem_stock[b_id] = rem_stock.get(b_id, 0) - sh["qty"]

    # Work with copies of shipments
    shipments = [dict(sh) for sh in raw_shipments if sh["qty"] > 0]

    # For each warehouse and SKU, iteratively repair
    for (w_id, sku_id), all_b_list in wh_sku_all.items():
        min_life = sku_min_life.get(sku_id, 0)

        # Look at shipments for this (w_id, sku_id)
        lane_sh = [sh for sh in shipments if sh["warehouse_id"] == w_id and sh["sku_id"] == sku_id]
        if not lane_sh:
            continue

        # Sort shipments by expiry descending (newest first to donate)
        for sh in sorted(lane_sh, key=lambda x: x["expiry_day"], reverse=True):
            s_id = sh["store_id"]
            transit = lanes_transit.get((w_id, s_id), 1)
            cur_exp = sh["expiry_day"]
            cur_b_id = sh["batch_id"]

            if sh["qty"] <= 0:
                continue

            # Look for older eligible batches with spare stock
            for older_b in all_b_list:
                if older_b["expiry_day"] >= cur_exp:
                    break  # Not older

                older_b_id = older_b["batch_id"]
                older_exp = older_b["expiry_day"]

                # C7: min life on arrival
                rem_life_arr = older_exp - (as_of_day + transit)
                if rem_life_arr < min_life:
                    continue

                # C8: sell-through cap
                c8_blocked = False
                if targets is not None and rem_life_arr < 9:
                    t_obj = targets.get(s_id, sku_id)
                    onhand_short = store_onhand.get((s_id, sku_id), 0)
                    cap_ell = max(0, math.floor(t_obj.target_q * rem_life_arr / 9.0) - onhand_short)
                    # Count already shipped on this store for life <= rem_life_arr
                    already_shipped = sum(
                        s_item["qty"] for s_item in shipments
                        if s_item["store_id"] == s_id and s_item["sku_id"] == sku_id and (s_item["expiry_day"] - (as_of_day + transit)) <= rem_life_arr
                    )
                    if already_shipped >= cap_ell:
                        c8_blocked = True

                if c8_blocked:
                    continue

                spare = rem_stock.get(older_b_id, 0)
                if spare > 0:
                    swap_qty = min(sh["qty"], spare)
                    sh["qty"] -= swap_qty
                    rem_stock[cur_b_id] += swap_qty
                    rem_stock[older_b_id] -= swap_qty

                    # Check if older batch already has a shipment on this lane
                    found = False
                    for existing in shipments:
                        if (existing["warehouse_id"] == w_id and existing["store_id"] == s_id and
                            existing["sku_id"] == sku_id and existing["batch_id"] == older_b_id):
                            existing["qty"] += swap_qty
                            found = True
                            break

                    if not found:
                        shipments.append({
                            "warehouse_id": w_id,
                            "store_id": s_id,
                            "sku_id": sku_id,
                            "batch_id": older_b_id,
                            "qty": swap_qty,
                            "expiry_day": older_exp,
                        })

                    if sh["qty"] <= 0:
                        break

    return [sh for sh in shipments if sh["qty"] > 0]
