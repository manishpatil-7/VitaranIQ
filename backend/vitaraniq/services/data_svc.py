"""
Data Service for VitaranIQ.
Orchestrates generation, atomic database persistence, and snapshot loading.
Conforms to FR-DAT-01..08.
"""

from typing import Any, Dict, Optional
import sqlite3
import json

from vitaraniq.core.config import load_params
from vitaraniq.data.generator import SyntheticDataGenerator
from vitaraniq.db.schema import init_db
from vitaraniq.db.session import get_db_path, get_sqlite_connection
from vitaraniq.db.snapshot import Snapshot, load_snapshot_from_db


import time


class DataService:
    @staticmethod
    def generate_and_save(seed: int = 42, db_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate synthetic dataset and insert into SQLite in a single transaction."""
        t_start = time.perf_counter()
        params = load_params()
        generator = SyntheticDataGenerator(seed=seed, params=params)
        data = generator.generate()

        conn = get_sqlite_connection(db_path)

        try:
            init_db(conn)
            cur = conn.cursor()

            # Atomic transaction
            cur.execute("BEGIN TRANSACTION;")

            # FR-DAT-08: Deactivate / delete existing active datasets (cascades)
            cur.execute("DELETE FROM datasets WHERE is_active = 1;")

            # 1. Dataset Header
            ds = data["dataset"]
            cur.execute("""
                INSERT INTO datasets (
                    dataset_id, seed, dataset_hash, params_hash, created_at,
                    is_active, n_warehouses, n_stores, n_skus, n_sales_rows
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ds["dataset_id"], ds["seed"], ds["dataset_hash"], ds["params_hash"],
                ds["created_at"], ds["is_active"], ds["n_warehouses"], ds["n_stores"],
                ds["n_skus"], ds["n_sales_rows"]
            ))

            # 2. Warehouses
            cur.executemany("""
                INSERT INTO warehouses (dataset_id, warehouse_id, name, lat, lon, fleet, inbound_weight)
                VALUES (:dataset_id, :warehouse_id, :name, :lat, :lon, :fleet, :inbound_weight)
            """, data["warehouses"])

            # 3. Stores
            cur.executemany("""
                INSERT INTO stores (dataset_id, store_id, name, city, region, lat, lon, size_mult, storage_cap_ml)
                VALUES (:dataset_id, :store_id, :name, :city, :region, :lat, :lon, :size_mult, :storage_cap_ml)
            """, data["stores"])

            # 4. Products
            cur.executemany("""
                INSERT INTO products (
                    dataset_id, sku_id, name, category, unit_cost_paise, price_paise,
                    volume_ml, shelf_life_days, min_life_days, write_off_factor,
                    stockout_mult, base_units_per_day
                ) VALUES (
                    :dataset_id, :sku_id, :name, :category, :unit_cost_paise, :price_paise,
                    :volume_ml, :shelf_life_days, :min_life_days, :write_off_factor,
                    :stockout_mult, :base_units_per_day
                )
            """, data["products"])

            # 5. Lanes
            cur.executemany("""
                INSERT INTO lanes (dataset_id, warehouse_id, store_id, km, transit_days, eligible)
                VALUES (:dataset_id, :warehouse_id, :store_id, :km, :transit_days, :eligible)
            """, data["lanes"])

            # 6. Calendar
            cur.executemany("""
                INSERT INTO calendar (dataset_id, day, date, dow, month, is_holiday, is_festival, festival_name)
                VALUES (:dataset_id, :day, :date, :dow, :month, :is_holiday, :is_festival, :festival_name)
            """, data["calendar"])

            # 7. Promo Windows
            cur.executemany("""
                INSERT INTO promo_windows (dataset_id, store_id, sku_id, start_day, end_day)
                VALUES (:dataset_id, :store_id, :sku_id, :start_day, :end_day)
            """, data["promo_windows"])

            # 8. Sales Daily (219,000 rows via executemany)
            cur.executemany("""
                INSERT INTO sales_daily (dataset_id, store_id, sku_id, day, units, promo_flag)
                VALUES (:dataset_id, :store_id, :sku_id, :day, :units, :promo_flag)
            """, data["sales_daily"])

            # 9. Window Demand (42,000 rows)
            cur.executemany("""
                INSERT INTO window_demand (dataset_id, seed, store_id, sku_id, day, units)
                VALUES (:dataset_id, :seed, :store_id, :sku_id, :day, :units)
            """, data["window_demand"])

            # 10. Batches
            cur.executemany("""
                INSERT INTO batches (dataset_id, batch_id, warehouse_id, sku_id, as_of_day, qty, expiry_day)
                VALUES (:dataset_id, :batch_id, :warehouse_id, :sku_id, :as_of_day, :qty, :expiry_day)
            """, data["batches"])

            # 11. Inbound Schedule
            cur.executemany("""
                INSERT INTO inbound_schedule (dataset_id, supply_scenario, day, warehouse_id, sku_id, qty, expiry_day)
                VALUES (:dataset_id, :supply_scenario, :day, :warehouse_id, :sku_id, :qty, :expiry_day)
            """, data["inbound_schedule"])

            # 12. Store Stock
            cur.executemany("""
                INSERT INTO store_stock (dataset_id, as_of_day, store_id, sku_id, qty, expiry_day)
                VALUES (:dataset_id, :as_of_day, :store_id, :sku_id, :qty, :expiry_day)
            """, data["store_stock"])

            conn.commit()
            t_end = time.perf_counter()
            return {
                "dataset_id": ds["dataset_id"],
                "seed": ds["seed"],
                "sha256_hash": ds["dataset_hash"],
                "dataset_hash": ds["dataset_hash"],
                "params_hash": ds["params_hash"],
                "created_at": ds["created_at"],
                "is_active": ds["is_active"],
                "row_counts": {
                    "warehouses": ds["n_warehouses"],
                    "stores": ds["n_stores"],
                    "products": ds["n_skus"],
                    "sales_daily": ds["n_sales_rows"],
                },
                "elapsed_seconds": round(t_end - t_start, 2),
                **ds,
            }
        except Exception as e:

            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def get_active_dataset(conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
        close_conn = False
        if conn is None:
            conn = get_sqlite_connection()
            close_conn = True
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM datasets WHERE is_active = 1 LIMIT 1;")
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            if close_conn:
                conn.close()
