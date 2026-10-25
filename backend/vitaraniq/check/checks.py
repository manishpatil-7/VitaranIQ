"""
Independent Plan-Checker Module.
Implements FR-CHK-01..05, verifying all physical and business constraints:
1. Non-negative integer quantities
2. Batch availability
3. Truck volume and warehouse fleet capacity
4. Store storage capacity after delivery
5. Shelf life on arrival (min life)
6. Lane eligibility
7. FEFO invariant with C8-block awareness
"""

from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import math

from vitaraniq.check.result import CheckResult, Violation


def check_plan(
    snapshot: Any,  # Snapshot dataclass or compatible object
    lines: List[Dict[str, Any]],  # List of plan lines
    targets: Optional[Any] = None,  # Targets object with .get(s_id, p_id).target_q
    truck_cap_ml: int = 4000000,
) -> CheckResult:
    violations: List[Violation] = []
    as_of = snapshot.as_of_day

    # Pre-build lookup dictionaries from snapshot
    batch_stock_map = {b["batch_id"]: b["qty"] for b in snapshot.batches}
    batch_exp_map = {b["batch_id"]: b["expiry_day"] for b in snapshot.batches}
    batch_wh_map = {b["batch_id"]: b["warehouse_id"] for b in snapshot.batches}
    batch_sku_map = {b["batch_id"]: b["sku_id"] for b in snapshot.batches}

    prod_map = {p["sku_id"]: p for p in snapshot.products}
    store_map = {s["store_id"]: s for s in snapshot.stores}
    wh_map = {w["warehouse_id"]: w for w in snapshot.warehouses}

    # Tracking accumulators
    shipped_per_batch = defaultdict(int)
    volume_per_lane = defaultdict(int)
    trucks_per_lane = defaultdict(int)
    delivered_vol_per_store = defaultdict(int)
    trucks_per_wh = defaultdict(int)

    # Group shipments by (warehouse_id, sku_id, store_id) for FEFO check
    shipments_by_wh_sku_store = defaultdict(list)

    for line in lines:
        qty = line.get("qty", 0)
        sku_id = line["sku_id"]
        w_id = line["warehouse_id"]
        s_id = line["store_id"]
        b_id = line["batch_id"]
        trucks = line.get("trucks_on_lane", 1)

        p_info = prod_map.get(sku_id)
        vol_unit = p_info["volume_ml"] if p_info else 0
        min_life = p_info["min_life_days"] if p_info else 0

        # Check 1: Non-negative integer quantity
        if not isinstance(qty, int) or qty <= 0:
            violations.append(Violation(
                check_id=1,
                check_name="NonNegativeInteger",
                entity=f"Line(SKU={sku_id}, WH={w_id}, Store={s_id})",
                detail=f"Invalid quantity {qty}; must be positive integer",
            ))

        # Check 6: Lane eligibility
        lane_info = snapshot.lanes.get((w_id, s_id))
        if not lane_info or lane_info.get("eligible", 0) != 1:
            violations.append(Violation(
                check_id=6,
                check_name="LaneEligibility",
                entity=f"Lane({w_id}->{s_id})",
                detail="Lane is excluded (> 450 km or missing)",
            ))

        # Check 5: Shelf life on arrival
        transit = lane_info.get("transit_days", 1) if lane_info else 1
        line_exp = line.get("batch_expiry_day")
        wh_exp = batch_exp_map.get(b_id)
        b_exp = min(e for e in [line_exp, wh_exp] if e is not None) if (line_exp is not None or wh_exp is not None) else 0
        rem_life_arr = b_exp - (as_of + transit)
        if rem_life_arr < min_life:
            violations.append(Violation(
                check_id=5,
                check_name="ShelfLifeOnArrival",
                entity=f"Batch({b_id}) to Store({s_id})",
                detail=f"Remaining life {rem_life_arr}d is less than min required {min_life}d",
            ))

        # Accumulate
        shipped_per_batch[b_id] += qty
        vol_line = qty * vol_unit
        volume_per_lane[(w_id, s_id)] += vol_line
        delivered_vol_per_store[s_id] += vol_line
        trucks_per_lane[(w_id, s_id)] = max(trucks_per_lane[(w_id, s_id)], trucks)

        shipments_by_wh_sku_store[(w_id, sku_id, s_id)].append({
            "batch_id": b_id,
            "expiry_day": b_exp,
            "qty": qty,
        })

    # Check 2: Batch availability
    for b_id, shipped_qty in shipped_per_batch.items():
        avail = batch_stock_map.get(b_id, 0)
        if shipped_qty > avail:
            violations.append(Violation(
                check_id=2,
                check_name="BatchAvailability",
                entity=f"Batch({b_id})",
                detail=f"Shipped {shipped_qty} exceeds warehouse stock {avail}",
            ))

    # Check 3: Truck volume and warehouse fleet capacity
    for (w_id, s_id), tot_vol in volume_per_lane.items():
        trks = trucks_per_lane[(w_id, s_id)]
        req_trks = math.ceil(tot_vol / truck_cap_ml)
        if trks < req_trks:
            violations.append(Violation(
                check_id=3,
                check_name="TruckVolumeCapacity",
                entity=f"Lane({w_id}->{s_id})",
                detail=f"Volume {tot_vol} ml requires {req_trks} trucks, allocated {trks}",
            ))
        trucks_per_wh[w_id] += trks

    for w_id, fleet_used in trucks_per_wh.items():
        wh_fleet = snapshot.fleet.get(w_id, 30)
        if fleet_used > wh_fleet:
            violations.append(Violation(
                check_id=3,
                check_name="WarehouseFleetLimit",
                entity=f"Warehouse({w_id})",
                detail=f"Dispatched {fleet_used} trucks, exceeds fleet limit {wh_fleet}",
            ))

    # Check 4: Store capacity after delivery
    for s_id, s_info in store_map.items():
        cap = s_info["storage_cap_ml"]
        # Existing on-hand volume
        onhand_vol = 0
        for (st_id, sku_id), stock_info in snapshot.store_onhand.items():
            if st_id == s_id:
                p_vol = prod_map[sku_id]["volume_ml"]
                onhand_vol += stock_info["qty"] * p_vol

        deliv_vol = delivered_vol_per_store[s_id]
        total_vol = onhand_vol + deliv_vol
        if total_vol > cap:
            violations.append(Violation(
                check_id=4,
                check_name="StoreStorageCapacity",
                entity=f"Store({s_id})",
                detail=f"Total volume {total_vol} ml exceeds store capacity {cap} ml",
            ))

    # Check 7: FEFO invariant
    # For each warehouse-SKU and store with a newer batch shipped:
    # every older batch must be exhausted, C7-ineligible, or C8-blocked
    wh_sku_all_batches = defaultdict(list)
    for b in snapshot.batches:
        wh_sku_all_batches[(b["warehouse_id"], b["sku_id"])].append(b)

    for (w_id, sku_id, s_id), sh_items in shipments_by_wh_sku_store.items():
        all_wh_b = sorted(wh_sku_all_batches[(w_id, sku_id)], key=lambda x: x["expiry_day"])
        lane_info = snapshot.lanes.get((w_id, s_id))
        transit = lane_info.get("transit_days", 1) if lane_info else 1
        min_life = prod_map[sku_id]["min_life_days"]

        for sh in sh_items:
            cur_exp = sh["expiry_day"]
            # Look at older batches in warehouse
            for older_b in all_wh_b:
                if older_b["expiry_day"] >= cur_exp:
                    break  # Not older

                # Check if older batch is C7-ineligible
                rem_life = older_b["expiry_day"] - (as_of + transit)
                if rem_life < min_life:
                    continue  # Ineligible on this lane

                # Check if older batch has unused stock
                older_b_id = older_b["batch_id"]
                older_avail = older_b["qty"] - shipped_per_batch[older_b_id]
                if older_avail > 0:
                    # Check C8 blocking
                    c8_blocked = False
                    if rem_life < 9:
                        if targets is not None:
                            t_obj = None
                            if hasattr(targets, "get"):
                                try:
                                    t_obj = targets.get(s_id, sku_id)
                                except TypeError:
                                    t_obj = targets.get((s_id, sku_id))
                            elif isinstance(targets, dict):
                                t_obj = targets.get((s_id, sku_id))

                            target_q = t_obj.target_q if hasattr(t_obj, "target_q") else (t_obj if isinstance(t_obj, (int, float)) else 0)
                            onhand_short = snapshot.store_onhand.get((s_id, sku_id), {}).get("qty", 0)
                            cap_l = max(0, math.floor(target_q * rem_life / 9.0) - onhand_short)
                            shipped_to_store_short = sum(
                                s_line["qty"] for s_line in lines
                                if s_line["store_id"] == s_id and s_line["sku_id"] == sku_id
                                and (batch_exp_map.get(s_line["batch_id"], s_line.get("batch_expiry_day", 0)) - (as_of + transit)) <= rem_life
                            )
                            if shipped_to_store_short >= cap_l:
                                c8_blocked = True
                        else:
                            # Without targets, a batch with rem_life < 9 is subject to C8 sell-through capping
                            c8_blocked = True

                    if not c8_blocked:
                        violations.append(Violation(
                            check_id=7,
                            check_name="FEFOInvariant",
                            entity=f"Warehouse({w_id})-SKU({sku_id})->Store({s_id})",
                            detail=f"Shipped newer batch {sh['batch_id']} (exp {cur_exp}) while older batch {older_b_id} (exp {older_b['expiry_day']}) has {older_avail} units left",
                        ))

    return CheckResult(
        status="PASS" if len(violations) == 0 else "FAIL",
        violations=violations,
    )
