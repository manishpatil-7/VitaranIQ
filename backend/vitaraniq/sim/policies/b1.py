"""
Baseline Policy B1: 28-day Moving Average with Nearest-Warehouse Sourcing.
Implements FR-SIM-03 and AIML Design §9.2.
"""

from typing import Any, Dict, List, Tuple
from collections import defaultdict
import math

from vitaraniq.db.snapshot import Snapshot
from vitaraniq.optimize.waste import compute_lane_cost_paise


class PolicyB1:
    name: str = "B1"

    def __init__(self, sales_history_means: Dict[Tuple[str, str], float], buffer_factor: float = 1.0):
        """
        sales_history_means: (store_id, sku_id) -> mean daily sales over last 28 days
        buffer_factor: 1.0 for B1, 1.25 for B2
        """
        self.means = sales_history_means
        self.buffer_factor = buffer_factor

    def plan(self, snapshot: Snapshot, day: int) -> List[Dict[str, Any]]:
        as_of = day
        truck_cap_ml = 4000000

        prod_map = {p["sku_id"]: p for p in snapshot.products}
        store_map = {s["store_id"]: s for s in snapshot.stores}
        wh_map = {w["warehouse_id"]: w for w in snapshot.warehouses}

        # 1. Compute requested need per store-SKU
        requests = {}
        for s in snapshot.stores:
            s_id = s["store_id"]
            for p in snapshot.products:
                sku_id = p["sku_id"]
                m28 = self.means.get((s_id, sku_id), p["base_units_per_day"] * s["size_mult"])
                target_need = round(self.buffer_factor * 9.0 * m28)
                pos0 = snapshot.store_onhand.get((s_id, sku_id), {}).get("qty", 0) + sum(
                    it["qty"] for it in snapshot.intransit if it["store_id"] == s_id and it["sku_id"] == sku_id
                )
                need = max(0, target_need - pos0)
                requests[(s_id, sku_id)] = need

        # 2. Track remaining batch stock at warehouses
        rem_stock = {b["batch_id"]: b["qty"] for b in snapshot.batches if b["qty"] > 0}
        wh_sku_batches = defaultdict(list)
        for b in snapshot.batches:
            if b["qty"] > 0:
                wh_sku_batches[(b["warehouse_id"], b["sku_id"])].append(b)
        for k in wh_sku_batches:
            wh_sku_batches[k].sort(key=lambda x: x["expiry_day"])  # FEFO order

        # 3. Sort eligible warehouses by distance for each store
        store_wh_priority = {}
        for s_id in store_map:
            eligible_whs = []
            for w_id in wh_map:
                lane = snapshot.lanes.get((w_id, s_id))
                if lane and lane.get("eligible", 0) == 1:
                    eligible_whs.append((w_id, lane["km"], lane.get("transit_days", 1)))
            eligible_whs.sort(key=lambda x: x[1])  # Nearest first
            store_wh_priority[s_id] = eligible_whs

        # 4. Allocate from nearest warehouse
        shipments = []
        delivered_to_store_vol = defaultdict(int)

        for (s_id, sku_id), needed in requests.items():
            if needed <= 0:
                continue

            p_info = prod_map[sku_id]
            vol_unit = p_info["volume_ml"]
            min_life = p_info["min_life_days"]
            s_cap = store_map[s_id]["storage_cap_ml"]
            rem_needed = needed

            # Nearest eligible warehouses
            for (w_id, km, transit) in store_wh_priority[s_id]:
                if rem_needed <= 0:
                    break

                for b in wh_sku_batches.get((w_id, sku_id), []):
                    b_id = b["batch_id"]
                    avail = rem_stock.get(b_id, 0)
                    if avail <= 0:
                        continue

                    # Check C7 shelf life on arrival
                    if b["expiry_day"] - (as_of + transit) < min_life:
                        continue

                    # Check C6 store capacity
                    cur_vol = sum(
                        snapshot.store_onhand.get((s_id, p["sku_id"]), {}).get("qty", 0) * p["volume_ml"]
                        for p in snapshot.products
                    ) + delivered_to_store_vol[s_id]
                    spare_vol = max(0, s_cap - cur_vol)
                    max_store_units = spare_vol // max(1, vol_unit)
                    if max_store_units <= 0:
                        break

                    alloc = min(rem_needed, avail, max_store_units)
                    if alloc > 0:
                        shipments.append({
                            "warehouse_id": w_id,
                            "store_id": s_id,
                            "sku_id": sku_id,
                            "batch_id": b_id,
                            "batch_expiry_day": b["expiry_day"],
                            "qty": alloc,
                        })
                        rem_stock[b_id] -= alloc
                        delivered_to_store_vol[s_id] += alloc * vol_unit
                        rem_needed -= alloc

        # 5. Truck assignment and lane cost allocation
        lane_vols = defaultdict(int)
        lane_shipments = defaultdict(list)
        for sh in shipments:
            k = (sh["warehouse_id"], sh["store_id"])
            vol = sh["qty"] * prod_map[sh["sku_id"]]["volume_ml"]
            lane_vols[k] += vol
            lane_shipments[k].append(sh)

        formatted_lines = []
        line_no = 1
        for (w_id, s_id), sh_list in lane_shipments.items():
            tot_v = lane_vols[(w_id, s_id)]
            trks = max(1, math.ceil(tot_v / truck_cap_ml))
            lane_info = snapshot.lanes.get((w_id, s_id))
            km = lane_info["km"] if lane_info else 100.0
            lane_cost = trks * compute_lane_cost_paise(km)

            for sh in sh_list:
                line_v = sh["qty"] * prod_map[sh["sku_id"]]["volume_ml"]
                line_cost_paise = int(round((line_v / max(1, tot_v)) * lane_cost))
                formatted_lines.append({
                    "line_no": line_no,
                    "sku_id": sh["sku_id"],
                    "warehouse_id": w_id,
                    "store_id": s_id,
                    "batch_id": sh["batch_id"],
                    "batch_expiry_day": sh["batch_expiry_day"],
                    "qty": sh["qty"],
                    "trucks_on_lane": trks,
                    "line_cost_paise": line_cost_paise,
                    "priority": "NORMAL",
                    "reason_codes": [{"code": "REPLENISH_TO_TARGET", "evidence": {"policy": self.name}}],
                })
                line_no += 1

        return formatted_lines
