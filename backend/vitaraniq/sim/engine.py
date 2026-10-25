"""
28-Day Backtest Simulator Engine.
Implements FR-SIM-01 through FR-SIM-09, conforming to System Architecture §5 and AIML Design §8.
Executes the daily event loop (Arrivals -> Demand FEFO -> Expiry Write-Off) and enforces the Stock Conservation Invariant.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
import sqlite3
import math

from vitaraniq.db.snapshot import Snapshot, load_snapshot_from_db
from vitaraniq.sim.state import SimState
from vitaraniq.sim.policies.base import Policy
from vitaraniq.check.checks import check_plan
from vitaraniq.optimize.waste import compute_lane_cost_paise


class SimEngine:
    def __init__(
        self,
        dataset_id: str,
        seed: int,
        supply_scenario: str,
        policy: Policy,
        conn: sqlite3.Connection,
        truck_cap_ml: int = 4000000,
    ):
        self.dataset_id = dataset_id
        self.seed = seed
        self.supply_scenario = supply_scenario
        self.policy = policy
        self.conn = conn
        self.truck_cap_ml = truck_cap_ml

        # Load master references
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()

        # Products
        cur.execute("""
            SELECT sku_id, unit_cost_paise, price_paise,
                   (price_paise - unit_cost_paise) AS margin_paise, volume_ml
            FROM products WHERE dataset_id = ?
        """, (dataset_id,))
        self.prod_map = {r["sku_id"]: dict(r) for r in cur.fetchall()}

        # Lanes
        cur.execute("SELECT warehouse_id, store_id, km, transit_days, eligible FROM lanes WHERE dataset_id = ?", (dataset_id,))
        self.lanes = {(r["warehouse_id"], r["store_id"]): dict(r) for r in cur.fetchall()}
        self.lane_transit = {(r["warehouse_id"], r["store_id"]): r["transit_days"] for r in self.lanes.values()}

        # Stores
        cur.execute("SELECT store_id FROM stores WHERE dataset_id = ?", (dataset_id,))
        self.store_ids = [r["store_id"] for r in cur.fetchall()]

        # Load window demand for this seed: (day, store_id, sku_id) -> units
        cur.execute("""
            SELECT day, store_id, sku_id, units
            FROM window_demand
            WHERE dataset_id = ? AND seed = ?
        """, (dataset_id, seed))
        self.demand_lookup = {(r["day"], r["store_id"], r["sku_id"]): r["units"] for r in cur.fetchall()}


        # Load scheduled inbound: (day, warehouse_id, sku_id) -> list of {qty, expiry_day}
        cur.execute("""
            SELECT day, warehouse_id, sku_id, qty, expiry_day
            FROM inbound_schedule
            WHERE dataset_id = ? AND supply_scenario = ?
        """, (dataset_id, supply_scenario))
        self.inbound_by_day = defaultdict(list)
        for r in cur.fetchall():
            self.inbound_by_day[r["day"]].append(dict(r))

    def run(self, run_id: str) -> Dict[str, Any]:
        """Execute the 28-day simulation loop (days 703 to 730)."""
        replan_days = {703, 710, 717, 724}

        # Initialize base snapshot at day 703
        init_snapshot = load_snapshot_from_db(self.dataset_id, as_of_day=703, conn=self.conn)
        state = SimState(init_snapshot)

        # Tracking aggregates
        tot_units_demanded = 0
        tot_units_sold = 0
        tot_units_unmet = 0
        tot_units_delivered = 0
        tot_store_days_stockout = 0
        tot_store_days_total = 0

        tot_wastage_units = 0
        tot_wastage_paise = 0
        tot_transport_paise = 0
        tot_trips = 0
        tot_loaded_ml = 0
        tot_truck_capacity_ml = 0

        tot_lost_margin_paise = 0
        tot_margin_demanded_paise = 0
        tot_margin_sold_paise = 0

        daily_records = []
        plan_checks_records = []

        for current_day in range(703, 731):
            day_transport_paise = 0

            # ─── RE-PLANNING DAY EVENT ───
            if current_day in replan_days:
                # 1. Scheduled warehouse inbound arrives at the start of plan day
                inbound_items = self.inbound_by_day.get(current_day, [])
                state.add_scheduled_inbound(inbound_items, current_day)

                # 2. Export updated snapshot for policy
                current_snapshot = state.export_snapshot_for_day(current_day)

                # 3. Call policy to produce plan
                plan_lines = self.policy.plan(current_snapshot, current_day)

                # 4. Plan validation check
                check_res = check_plan(
                    current_snapshot,
                    plan_lines,
                    targets=getattr(self.policy, "last_targets", None),
                    truck_cap_ml=self.truck_cap_ml,
                )
                plan_checks_records.append({
                    "run_id": run_id,
                    "policy": self.policy.name,
                    "seed": self.seed,
                    "supply_scenario": self.supply_scenario,
                    "plan_day": current_day,
                    "checker_status": check_res.status,
                    "n_lines": len(plan_lines),
                })

                # 5. Calculate transport and truck metrics for dispatches
                lane_vols = defaultdict(int)
                for line in plan_lines:
                    v = line["qty"] * self.prod_map[line["sku_id"]]["volume_ml"]
                    lane_vols[(line["warehouse_id"], line["store_id"])] += v
                    tot_loaded_ml += v

                for (w_id, s_id), vol in lane_vols.items():
                    trks = max(1, math.ceil(vol / self.truck_cap_ml))
                    lane = self.lanes.get((w_id, s_id))
                    km = lane["km"] if lane else 100.0
                    cost = trks * compute_lane_cost_paise(km)
                    day_transport_paise += cost
                    tot_transport_paise += cost
                    tot_trips += trks
                    tot_truck_capacity_ml += trks * self.truck_cap_ml

                # 6. Dispatch shipments into in_transit queue
                state.dispatch_plan_lines(plan_lines, current_day, self.lane_transit)

            # ─── DAILY EVENT LOOP (FR-SIM-02) ───
            # Step 1: Inbound arrivals
            arrived_qty = state.process_arrivals(current_day)
            tot_units_delivered += arrived_qty

            # Step 2: Realized demand served FEFO
            day_demand_map = {}
            day_units_demanded = 0
            day_margin_demanded = 0

            for s_id in self.store_ids:
                for sku_id, p_info in self.prod_map.items():
                    d = self.demand_lookup.get((current_day, s_id, sku_id), 0)
                    day_demand_map[(s_id, sku_id)] = d
                    day_units_demanded += d
                    day_margin_demanded += d * p_info["margin_paise"]

            # Track store-level stockout
            store_had_stockout = defaultdict(bool)
            day_units_sold = 0
            day_units_unmet = 0
            day_margin_sold = 0
            day_lost_margin = 0

            for (s_id, sku_id), dem in day_demand_map.items():
                if dem <= 0:
                    continue
                # Serve from store stock FEFO
                batches = state.store_stock[(s_id, sku_id)]
                rem = dem
                for b in batches:
                    if rem <= 0:
                        break
                    take = min(b["qty"], rem)
                    b["qty"] -= take
                    rem -= take
                    day_units_sold += take
                    day_margin_sold += take * self.prod_map[sku_id]["margin_paise"]

                state.store_stock[(s_id, sku_id)] = [b for b in batches if b["qty"] > 0]
                state.store_ledgers[(s_id, sku_id)].sales += (dem - rem)

                if rem > 0:
                    day_units_unmet += rem
                    day_lost_margin += rem * self.prod_map[sku_id]["margin_paise"]
                    store_had_stockout[s_id] = True

            # Step 3: Expiry write-offs
            st_waste, wh_waste = state.write_off_expired(current_day)
            day_wastage_units = st_waste + wh_waste

            # Calculate wastage paise
            # (Assumes average product unit cost across write-offs)
            day_wastage_paise = 0
            for (s_id, sku_id), l in state.store_ledgers.items():
                p_cost = self.prod_map[sku_id]["unit_cost_paise"]
                # Note: wastage tracked accurately in ledgers

            # Aggregate daily counters
            tot_units_demanded += day_units_demanded
            tot_units_sold += day_units_sold
            tot_units_unmet += day_units_unmet
            tot_margin_demanded_paise += day_margin_demanded
            tot_margin_sold_paise += day_margin_sold
            tot_lost_margin_paise += day_lost_margin

            tot_store_days_total += len(self.store_ids)
            tot_store_days_stockout += sum(1 for v in store_had_stockout.values() if v)

            daily_records.append({
                "run_id": run_id,
                "policy": self.policy.name,
                "seed": self.seed,
                "supply_scenario": self.supply_scenario,
                "day": current_day,
                "units_demanded": day_units_demanded,
                "units_sold": day_units_sold,
                "units_unmet": day_units_unmet,
                "wastage_paise": 0,  # Computed from final ledgers
                "transport_paise": day_transport_paise,
            })

        # ─── FINAL AUDIT & STOCK CONSERVATION ───
        state.finalize_ledgers()
        is_conserved, errors = state.check_conservation_invariant()
        if not is_conserved:
            raise RuntimeError(f"Stock conservation violated: {errors[:3]}")

        # Compute total wastage paise from ledgers
        for (s_id, sku_id), l in state.store_ledgers.items():
            tot_wastage_units += l.wastage
            tot_wastage_paise += l.wastage * self.prod_map[sku_id]["unit_cost_paise"]

        for (w_id, sku_id), l in state.wh_ledgers.items():
            tot_wastage_units += l.wastage
            tot_wastage_paise += l.wastage * self.prod_map[sku_id]["unit_cost_paise"]

        # Final result dictionary conforming to sim_results
        result = {
            "run_id": run_id,
            "policy": self.policy.name,
            "seed": self.seed,
            "supply_scenario": self.supply_scenario,
            "units_demanded": tot_units_demanded,
            "units_sold": tot_units_sold,
            "units_unmet": tot_units_unmet,
            "units_delivered": tot_units_delivered,
            "store_days_total": tot_store_days_total,
            "store_days_stockout": tot_store_days_stockout,
            "wastage_units": tot_wastage_units,
            "wastage_paise": tot_wastage_paise,
            "transport_paise": tot_transport_paise,
            "trips": tot_trips,
            "loaded_ml": tot_loaded_ml,
            "truck_capacity_ml_total": max(1, tot_truck_capacity_ml),
            "lost_margin_paise": tot_lost_margin_paise,
            "margin_demanded_paise": tot_margin_demanded_paise,
            "margin_sold_paise": tot_margin_sold_paise,
            "daily_records": daily_records,
            "plan_checks_records": plan_checks_records,
        }

        return result
