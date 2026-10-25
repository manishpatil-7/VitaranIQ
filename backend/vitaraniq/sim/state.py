"""
Simulation State Tracking and Inventory Ledger.
Maintains batch-level FEFO store inventory, warehouse batches, and in-transit shipments.
Enforces the Stock Conservation Invariant (FR-SIM-08).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import copy

from vitaraniq.db.snapshot import Snapshot


@dataclass
class StoreLedger:
    initial_stock: int = 0
    receipts: int = 0
    sales: int = 0
    wastage: int = 0
    final_stock: int = 0

    @property
    def is_conserved(self) -> bool:
        return (self.initial_stock + self.receipts) == (self.sales + self.wastage + self.final_stock)

    @property
    def imbalance(self) -> int:
        return (self.initial_stock + self.receipts) - (self.sales + self.wastage + self.final_stock)


@dataclass
class WarehouseLedger:
    initial_stock: int = 0
    inbound: int = 0
    dispatched: int = 0
    wastage: int = 0
    final_stock: int = 0

    @property
    def is_conserved(self) -> bool:
        return (self.initial_stock + self.inbound) == (self.dispatched + self.wastage + self.final_stock)

    @property
    def imbalance(self) -> int:
        return (self.initial_stock + self.inbound) - (self.dispatched + self.wastage + self.final_stock)


class SimState:
    def __init__(self, snapshot: Snapshot):
        self.as_of_day = snapshot.as_of_day
        self.snapshot = snapshot

        # 1. Warehouse batches: (w_id, sku_id) -> list of batch dicts
        self.wh_batches: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for b in snapshot.batches:
            if b["qty"] > 0:
                self.wh_batches[(b["warehouse_id"], b["sku_id"])].append({
                    "batch_id": b["batch_id"],
                    "expiry_day": b["expiry_day"],
                    "qty": b["qty"],
                })
        for k in self.wh_batches:
            self.wh_batches[k].sort(key=lambda x: x["expiry_day"])

        # 2. Store stock: (s_id, sku_id) -> list of batch dicts
        self.store_stock: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for (s_id, sku_id), s_info in snapshot.store_onhand.items():
            if s_info["qty"] > 0:
                self.store_stock[(s_id, sku_id)].append({
                    "batch_id": f"INIT-{s_id}-{sku_id}",
                    "expiry_day": s_info["expiry_day"],
                    "qty": s_info["qty"],
                })

        # 3. In-transit queue
        self.in_transit: List[Dict[str, Any]] = []
        for it in snapshot.intransit:
            self.in_transit.append({
                "store_id": it["store_id"],
                "sku_id": it["sku_id"],
                "batch_id": f"INIT-TRANSIT-{it['store_id']}-{it['sku_id']}",
                "expiry_day": it["expiry_day"],
                "arrival_day": it["arrival_day"],
                "qty": it["qty"],
            })

        # 4. Conservation Ledgers
        self.store_ledgers: Dict[Tuple[str, str], StoreLedger] = defaultdict(StoreLedger)
        for (s_id, sku_id), b_list in self.store_stock.items():
            tot = sum(b["qty"] for b in b_list)
            self.store_ledgers[(s_id, sku_id)].initial_stock = tot

        self.wh_ledgers: Dict[Tuple[str, str], WarehouseLedger] = defaultdict(WarehouseLedger)
        for (w_id, sku_id), b_list in self.wh_batches.items():
            tot = sum(b["qty"] for b in b_list)
            self.wh_ledgers[(w_id, sku_id)].initial_stock = tot

    def add_scheduled_inbound(self, inbound_items: List[Dict[str, Any]], day: int):
        """Add weekly inbound factory deliveries to warehouse stock."""
        for item in inbound_items:
            w_id = item["warehouse_id"]
            sku_id = item["sku_id"]
            qty = item["qty"]
            exp = item["expiry_day"]
            b_id = item.get("batch_id", f"INB-{w_id}-{sku_id}-D{day}")

            self.wh_batches[(w_id, sku_id)].append({
                "batch_id": b_id,
                "expiry_day": exp,
                "qty": qty,
            })
            self.wh_batches[(w_id, sku_id)].sort(key=lambda x: x["expiry_day"])
            self.wh_ledgers[(w_id, sku_id)].inbound += qty

    def dispatch_plan_lines(self, lines: List[Dict[str, Any]], day: int, lane_transit: Dict[Tuple[str, str], int]):
        """Deduct dispatched batches from warehouse and push to in_transit queue."""
        for line in lines:
            w_id = line["warehouse_id"]
            s_id = line["store_id"]
            sku_id = line["sku_id"]
            b_id = line["batch_id"]
            b_exp = line["batch_expiry_day"]
            qty = line["qty"]
            if qty <= 0:
                continue

            transit = lane_transit.get((w_id, s_id), 1)
            arr_day = day + transit

            # Deduct from warehouse batch
            found = False
            for b in self.wh_batches[(w_id, sku_id)]:
                if b["batch_id"] == b_id:
                    if b["qty"] < qty:
                        raise ValueError(f"Warehouse {w_id} batch {b_id} stock {b['qty']} < dispatched {qty}")
                    b["qty"] -= qty
                    found = True
                    break

            if not found:
                raise ValueError(f"Warehouse {w_id} batch {b_id} not found in active batches")

            self.wh_ledgers[(w_id, sku_id)].dispatched += qty

            # Add to in_transit
            self.in_transit.append({
                "store_id": s_id,
                "sku_id": sku_id,
                "batch_id": b_id,
                "expiry_day": b_exp,
                "arrival_day": arr_day,
                "qty": qty,
            })

        # Remove 0-qty warehouse batches
        for k in self.wh_batches:
            self.wh_batches[k] = [b for b in self.wh_batches[k] if b["qty"] > 0]

    def process_arrivals(self, day: int) -> int:
        """Step 1: Deliver in-transit shipments arriving today into store stock."""
        arrived = [it for it in self.in_transit if it["arrival_day"] == day]
        self.in_transit = [it for it in self.in_transit if it["arrival_day"] > day]

        tot_units = 0
        for it in arrived:
            s_id = it["store_id"]
            sku_id = it["sku_id"]
            qty = it["qty"]
            self.store_stock[(s_id, sku_id)].append({
                "batch_id": it["batch_id"],
                "expiry_day": it["expiry_day"],
                "qty": qty,
            })
            self.store_stock[(s_id, sku_id)].sort(key=lambda x: x["expiry_day"])
            self.store_ledgers[(s_id, sku_id)].receipts += qty
            tot_units += qty

        return tot_units

    def serve_demand_fefo(self, realized_demand: Dict[Tuple[str, str], int]) -> Tuple[int, int]:
        """
        Step 2: Serve realized daily demand FEFO from store stock.
        Returns: (total_sold_units, total_unmet_units)
        """
        tot_sold = 0
        tot_unmet = 0

        for (s_id, sku_id), dem in realized_demand.items():
            if dem <= 0:
                continue

            rem_dem = dem
            batches = self.store_stock[(s_id, sku_id)]
            for b in batches:
                if rem_dem <= 0:
                    break
                take = min(b["qty"], rem_dem)
                b["qty"] -= take
                rem_dem -= take
                tot_sold += take
                self.store_ledgers[(s_id, sku_id)].sales += take

            unmet = rem_dem
            tot_unmet += unmet

            # Filter out depleted batches
            self.store_stock[(s_id, sku_id)] = [b for b in batches if b["qty"] > 0]

        return tot_sold, tot_unmet

    def write_off_expired(self, day: int) -> Tuple[int, int]:
        """
        Step 3: Remove expired units at stores and warehouses where expiry_day <= day.
        Returns: (store_wastage_units, warehouse_wastage_units)
        """
        st_waste = 0
        wh_waste = 0

        # Store write-offs
        for (s_id, sku_id), batches in self.store_stock.items():
            valid = []
            for b in batches:
                if b["expiry_day"] <= day:
                    st_waste += b["qty"]
                    self.store_ledgers[(s_id, sku_id)].wastage += b["qty"]
                else:
                    valid.append(b)
            self.store_stock[(s_id, sku_id)] = valid

        # Warehouse write-offs
        for (w_id, sku_id), batches in self.wh_batches.items():
            valid = []
            for b in batches:
                if b["expiry_day"] <= day:
                    wh_waste += b["qty"]
                    self.wh_ledgers[(w_id, sku_id)].wastage += b["qty"]
                else:
                    valid.append(b)
            self.wh_batches[(w_id, sku_id)] = valid

        return st_waste, wh_waste

    def finalize_ledgers(self):
        """Record closing stocks for invariant audit."""
        for (s_id, sku_id), batches in self.store_stock.items():
            self.store_ledgers[(s_id, sku_id)].final_stock = sum(b["qty"] for b in batches)

        for (w_id, sku_id), batches in self.wh_batches.items():
            self.wh_ledgers[(w_id, sku_id)].final_stock = sum(b["qty"] for b in batches)

    def check_conservation_invariant(self) -> Tuple[bool, List[str]]:
        """Verify Initial + Inbound/Receipts == Final + Sales/Dispatched + Wastage."""
        self.finalize_ledgers()
        errors = []

        for (s_id, sku_id), l in self.store_ledgers.items():
            if not l.is_conserved:
                errors.append(
                    f"Store({s_id})-SKU({sku_id}) conservation violated: "
                    f"init({l.initial_stock}) + recv({l.receipts}) != "
                    f"sold({l.sales}) + waste({l.wastage}) + fin({l.final_stock}) "
                    f"[diff = {l.imbalance}]"
                )

        for (w_id, sku_id), l in self.wh_ledgers.items():
            if not l.is_conserved:
                errors.append(
                    f"Warehouse({w_id})-SKU({sku_id}) conservation violated: "
                    f"init({l.initial_stock}) + inb({l.inbound}) != "
                    f"disp({l.dispatched}) + waste({l.wastage}) + fin({l.final_stock}) "
                    f"[diff = {l.imbalance}]"
                )

        return len(errors) == 0, errors

    def export_snapshot_for_day(self, day: int) -> Snapshot:
        """Create an updated Snapshot object representing current state on re-planning day."""
        wh_batches_list = []
        for (w_id, sku_id), b_list in self.wh_batches.items():
            for b in b_list:
                if b["qty"] > 0:
                    wh_batches_list.append({
                        "batch_id": b["batch_id"],
                        "warehouse_id": w_id,
                        "sku_id": sku_id,
                        "qty": b["qty"],
                        "expiry_day": b["expiry_day"],
                    })

        store_onhand_dict = {}
        for (s_id, sku_id), b_list in self.store_stock.items():
            tot_q = sum(b["qty"] for b in b_list)
            # Earliest expiry for store on-hand representation
            min_exp = min((b["expiry_day"] for b in b_list), default=999)
            store_onhand_dict[(s_id, sku_id)] = {
                "qty": tot_q,
                "expiry_day": min_exp,
            }

        intransit_list = [copy.deepcopy(it) for it in self.in_transit]

        return Snapshot(
            dataset_id=self.snapshot.dataset_id,
            as_of_day=day,
            warehouses=self.snapshot.warehouses,
            stores=self.snapshot.stores,
            products=self.snapshot.products,
            lanes=self.snapshot.lanes,
            batches=wh_batches_list,
            store_onhand=store_onhand_dict,
            intransit=intransit_list,
            fleet=self.snapshot.fleet,
            store_cap=self.snapshot.store_cap,
        )
