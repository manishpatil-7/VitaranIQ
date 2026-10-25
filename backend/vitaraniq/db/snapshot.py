"""
In-memory Snapshot data contract and database loader.
Conforms to System Architecture §4 and Database Schema §6.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import sqlite3
import pandas as pd

from vitaraniq.db.session import get_db_path, get_sqlite_connection


@dataclass
class Snapshot:
    dataset_id: str
    as_of_day: int
    warehouses: List[Dict[str, Any]]
    stores: List[Dict[str, Any]]
    products: List[Dict[str, Any]]
    lanes: Dict[Tuple[str, str], Dict[str, Any]]  # (w_id, s_id) -> {km, transit_days, eligible}
    batches: List[Dict[str, Any]]                # list of batch dicts
    store_onhand: Dict[Tuple[str, str], Dict[str, Any]]  # (s_id, sku_id) -> {qty, expiry_day}
    intransit: List[Dict[str, Any]]              # list of in-transit records
    fleet: Dict[str, int]                        # w_id -> fleet
    store_cap: Dict[str, int]                    # s_id -> storage_cap_ml
    wh_map: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    store_map: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    prod_map: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        self.wh_map = {w["warehouse_id"]: w for w in self.warehouses}
        self.store_map = {s["store_id"]: s for s in self.stores}
        self.prod_map = {p["sku_id"]: p for p in self.products}


def load_snapshot_from_db(dataset_id: str, as_of_day: int = 703, conn: sqlite3.Connection = None) -> Snapshot:
    """Load Snapshot from SQLite database matching Database Schema §6."""
    close_conn = False
    if conn is None:
        conn = get_sqlite_connection()
        close_conn = True

    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Warehouses
        cur.execute("SELECT warehouse_id, name, lat, lon, fleet, inbound_weight FROM warehouses WHERE dataset_id = ?", (dataset_id,))
        warehouses = [dict(r) for r in cur.fetchall()]

        # 2. Stores
        cur.execute("SELECT store_id, name, city, region, lat, lon, size_mult, storage_cap_ml FROM stores WHERE dataset_id = ?", (dataset_id,))
        stores = [dict(r) for r in cur.fetchall()]

        # 3. Products
        cur.execute("""
            SELECT sku_id, name, category, unit_cost_paise, price_paise,
                   (price_paise - unit_cost_paise) AS margin_paise,
                   volume_ml, shelf_life_days, min_life_days, write_off_factor,
                   stockout_mult, base_units_per_day
            FROM products WHERE dataset_id = ?
        """, (dataset_id,))
        products = [dict(r) for r in cur.fetchall()]

        # 4. Lanes
        cur.execute("SELECT warehouse_id, store_id, km, transit_days, eligible FROM lanes WHERE dataset_id = ?", (dataset_id,))
        lanes = {}
        for r in cur.fetchall():
            lanes[(r["warehouse_id"], r["store_id"])] = {
                "km": r["km"],
                "transit_days": r["transit_days"],
                "eligible": r["eligible"],
            }

        # 5. Batches at as_of_day with qty > 0
        cur.execute("""
            SELECT batch_id, warehouse_id, sku_id, qty, expiry_day
            FROM batches
            WHERE dataset_id = ? AND as_of_day = ? AND qty > 0
            ORDER BY expiry_day ASC
        """, (dataset_id, as_of_day))
        batches = [dict(r) for r in cur.fetchall()]

        # 6. Store on-hand
        cur.execute("""
            SELECT store_id, sku_id, qty, expiry_day
            FROM store_stock
            WHERE dataset_id = ? AND as_of_day = ?
        """, (dataset_id, as_of_day))
        store_onhand = {}
        for r in cur.fetchall():
            store_onhand[(r["store_id"], r["sku_id"])] = {
                "qty": r["qty"],
                "expiry_day": r["expiry_day"],
            }

        # 7. In-transit
        cur.execute("""
            SELECT store_id, sku_id, arrival_day, qty, expiry_day
            FROM in_transit
            WHERE dataset_id = ? AND as_of_day = ?
        """, (dataset_id, as_of_day))
        intransit = [dict(r) for r in cur.fetchall()]

        fleet = {w["warehouse_id"]: w["fleet"] for w in warehouses}
        store_cap = {s["store_id"]: s["storage_cap_ml"] for s in stores}

        return Snapshot(
            dataset_id=dataset_id,
            as_of_day=as_of_day,
            warehouses=warehouses,
            stores=stores,
            products=products,
            lanes=lanes,
            batches=batches,
            store_onhand=store_onhand,
            intransit=intransit,
            fleet=fleet,
            store_cap=store_cap,
        )
    finally:
        if close_conn:
            conn.close()
