"""
Deterministic Synthetic Data Generator for VitaranIQ.
Implements FR-DAT-01 through FR-DAT-05, SRS Appendix A, B, C, and DB Schema §9.
Generates all master data, sales history (219k rows), batches, lanes, calendar, and backtest windows.
"""

import math
import hashlib
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

from vitaraniq.core.config import SystemParams, load_params
from vitaraniq.core.ids import generate_batch_id, compute_sha256, utc_now_iso
from vitaraniq.data.calendar import generate_calendar_days
from vitaraniq.data.validators import validate_snapshot_data


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in kilometers."""
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class SyntheticDataGenerator:
    def __init__(self, seed: int = 42, params: SystemParams = None):
        self.seed = seed
        self.params = params or load_params()
        
        # Spawn independent child random streams
        seq = np.random.SeedSequence(seed)
        child_seqs = seq.spawn(7)
        self.rng_net = np.random.default_rng(child_seqs[0])
        self.rng_cal = np.random.default_rng(child_seqs[1])
        self.rng_promo = np.random.default_rng(child_seqs[2])
        self.rng_hist = np.random.default_rng(child_seqs[3])
        self.rng_init = np.random.default_rng(child_seqs[4])
        self.rng_inbound = np.random.default_rng(child_seqs[5])
        self.child_seq_window = child_seqs[6]

    def generate(self) -> Dict[str, Any]:
        """Generate complete dataset ready for database insertion."""
        dataset_id = f"ds_seed{self.seed}"
        
        # 1. Master: Warehouses
        warehouses = []
        for w in self.params.network.warehouses:
            warehouses.append({
                "dataset_id": dataset_id,
                "warehouse_id": w.id,
                "name": w.name,
                "lat": float(w.lat),
                "lon": float(w.lon),
                "fleet": int(w.fleet),
                "inbound_weight": float(w.inbound_weight),
            })

        # 2. Master: Stores (with rejection sampling for >= 2 eligible warehouses)
        stores, lanes = self._generate_stores_and_lanes(dataset_id, warehouses)

        # 3. Master: Products
        products = []
        for p in self.params.products:
            products.append({
                "dataset_id": dataset_id,
                "sku_id": p.id,
                "name": p.name,
                "category": p.category,
                "unit_cost_paise": int(p.unit_cost_paise),
                "price_paise": int(p.price_paise),
                "volume_ml": int(p.volume_ml),
                "shelf_life_days": int(p.shelf_life_days),
                "min_life_days": int(p.min_life_days),
                "write_off_factor": float(p.write_off_factor),
                "stockout_mult": int(p.stockout_mult),
                "base_units_per_day": float(p.base_units_per_day),
            })

        # 4. Calendar (days 1 to 740)
        calendar = generate_calendar_days(740)
        for c in calendar:
            c["dataset_id"] = dataset_id

        # 5. Promo Windows
        promo_windows = self._generate_promo_windows(dataset_id, stores, products)

        # 6. Sales Daily (days 1 to 730)
        sales_daily, mean_demand_matrix = self._generate_sales_daily(
            dataset_id, stores, products, calendar, promo_windows
        )

        # 7. Initial Batches & Store Stock for Day 703
        batches = self._generate_initial_batches(dataset_id, warehouses, products, mean_demand_matrix)
        store_stock = self._generate_initial_store_stock(dataset_id, stores, products, mean_demand_matrix)
        in_transit = []  # No in-transit on day 703 per FR-DAT-04

        # 8. Scheduled Warehouse Inbound
        inbound_schedule = self._generate_inbound_schedule(dataset_id, warehouses, products, mean_demand_matrix)

        # 9. Window Demand for Held-out Simulation Seeds {11, 12, 13, 14, 15}
        window_demand = self._generate_window_demand(dataset_id, stores, products, mean_demand_matrix)

        # Validate generated snapshot data
        val_result = validate_snapshot_data(
            warehouses=warehouses,
            stores=stores,
            products=products,
            lanes=lanes,
            batches=batches,
            store_stock=store_stock,
            as_of_day=703,
        )
        val_result.raise_if_invalid()

        # Compute canonical dataset hash
        dataset_hash = self._compute_dataset_hash(
            warehouses=warehouses,
            stores=stores,
            products=products,
            lanes=lanes,
            calendar=calendar,
            promo_windows=promo_windows,
            sales_daily=sales_daily,
            batches=batches,
            inbound_schedule=inbound_schedule,
            store_stock=store_stock,
        )

        params_hash = compute_sha256(self.params.model_dump_json())

        dataset_header = {
            "dataset_id": dataset_id,
            "seed": self.seed,
            "dataset_hash": dataset_hash,
            "params_hash": params_hash,
            "created_at": utc_now_iso(),
            "is_active": 1,
            "n_warehouses": len(warehouses),
            "n_stores": len(stores),
            "n_skus": len(products),
            "n_sales_rows": len(sales_daily),
        }

        return {
            "dataset": dataset_header,
            "warehouses": warehouses,
            "stores": stores,
            "products": products,
            "lanes": lanes,
            "calendar": calendar,
            "promo_windows": promo_windows,
            "sales_daily": sales_daily,
            "window_demand": window_demand,
            "batches": batches,
            "inbound_schedule": inbound_schedule,
            "store_stock": store_stock,
            "in_transit": in_transit,
        }

    def _generate_stores_and_lanes(
        self, dataset_id: str, warehouses: List[Dict]
    ) -> Tuple[List[Dict], List[Dict]]:
        anchor_cities = self.params.network.stores.anchor_cities
        sizes = list(self.params.network.stores.size_multipliers)
        self.rng_net.shuffle(sizes)

        while True:
            stores = []
            lanes = []
            all_valid = True

            for idx in range(25):
                s_id = f"S{idx + 1:02d}"
                anchor = anchor_cities[idx % len(anchor_cities)]
                
                # Seeded jitter +/- 0.15 deg
                jitter_lat = self.rng_net.uniform(-0.15, 0.15)
                jitter_lon = self.rng_net.uniform(-0.15, 0.15)
                s_lat = round(anchor.lat + jitter_lat, 4)
                s_lon = round(anchor.lon + jitter_lon, 4)
                size_mult = sizes[idx]
                storage_cap_ml = int(self.params.network.stores.base_storage_cap_ml * size_mult)

                store_record = {
                    "dataset_id": dataset_id,
                    "store_id": s_id,
                    "name": f"{anchor.name} Store #{idx + 1}",
                    "city": anchor.name,
                    "region": anchor.region,
                    "lat": s_lat,
                    "lon": s_lon,
                    "size_mult": size_mult,
                    "storage_cap_ml": storage_cap_ml,
                }
                stores.append(store_record)

                # Compute lanes to all warehouses
                eligible_wh_count = 0
                for w in warehouses:
                    h_dist = haversine_distance(w["lat"], w["lon"], s_lat, s_lon)
                    road_km = round(h_dist * self.params.network.lanes.distance_multiplier, 1)
                    eligible = 1 if road_km <= self.params.network.lanes.max_eligible_km else 0
                    transit_days = 1 if road_km <= self.params.network.lanes.transit_1_day_km_max else 2

                    if eligible:
                        eligible_wh_count += 1

                    lanes.append({
                        "dataset_id": dataset_id,
                        "warehouse_id": w["warehouse_id"],
                        "store_id": s_id,
                        "km": road_km,
                        "transit_days": transit_days,
                        "eligible": eligible,
                    })

                if eligible_wh_count < 2:
                    all_valid = False
                    break

            if all_valid:
                return stores, lanes

    def _generate_promo_windows(
        self, dataset_id: str, stores: List[Dict], products: List[Dict]
    ) -> List[Dict]:
        """Generate two 5-day promo windows per quarter for each store-SKU."""
        records = []
        # Quarters over 740 days: 8 quarters (each ~90 days)
        quarters = [
            (1, 90), (91, 180), (181, 270), (271, 360),
            (361, 450), (451, 540), (541, 630), (631, 720)
        ]

        for s in stores:
            for p in products:
                s_id = s["store_id"]
                sku_id = p["sku_id"]
                for q_start, q_end in quarters:
                    # Pick two non-overlapping start days within quarter
                    valid_starts = list(range(q_start, q_end - 6))
                    starts = sorted(self.rng_promo.choice(valid_starts, size=2, replace=False))
                    for st in starts:
                        records.append({
                            "dataset_id": dataset_id,
                            "store_id": s_id,
                            "sku_id": sku_id,
                            "start_day": int(st),
                            "end_day": int(st + 4),
                        })
        return records

    def _generate_sales_daily(
        self,
        dataset_id: str,
        stores: List[Dict],
        products: List[Dict],
        calendar: List[Dict],
        promo_windows: List[Dict],
    ) -> Tuple[List[Dict], np.ndarray]:
        """Generate daily sales following Negative-Binomial Gamma-Poisson mixture."""
        n_days = 730
        n_stores = len(stores)
        n_products = len(products)

        # Lookup maps
        store_sizes = np.array([s["size_mult"] for s in stores], dtype=np.float64)  # (25,)
        base_units = np.array([p["base_units_per_day"] for p in products], dtype=np.float64)  # (12,)
        
        # Build promo lookup matrix of flags (740, 25, 12)
        promo_flag = np.zeros((741, n_stores, n_products), dtype=np.int8)
        post_promo_flag = np.zeros((741, n_stores, n_products), dtype=np.int8)

        s_map = {s["store_id"]: idx for idx, s in enumerate(stores)}
        p_map = {p["sku_id"]: idx for idx, p in enumerate(products)}

        for pw in promo_windows:
            s_idx = s_map[pw["store_id"]]
            p_idx = p_map[pw["sku_id"]]
            st = pw["start_day"]
            en = pw["end_day"]
            if en <= 740:
                promo_flag[st:en + 1, s_idx, p_idx] = 1
                post_st = en + 1
                post_en = min(en + 3, 740)
                post_promo_flag[post_st:post_en + 1, s_idx, p_idx] = 1

        # Precompute daily factors
        cal_by_day = {c["day"]: c for c in calendar}
        weekday_mults = self.params.demand_model.weekday_multipliers
        
        # 3D mean demand array: (days, stores, products)
        mu = np.zeros((n_days + 1, n_stores, n_products), dtype=np.float64)
        
        for d in range(1, n_days + 1):
            c = cal_by_day[d]
            dow = c["dow"]
            w_mult = weekday_mults[dow]
            
            # Trend factor: 1 + 0.10 * d / 730
            trend_mult = 1.0 + 0.10 * (d / 730.0)

            # Seasonality per SKU
            # season = 1 + A * sin(2*pi*(doy - 15)/365)
            # doy approximation from day: (d - 1) % 365 + 1
            doy = ((d - 1) % 365) + 1
            sin_val = math.sin(2.0 * math.pi * (doy - 15) / 365.0)

            for p_idx, p in enumerate(products):
                sku = p["sku_id"]
                A = 0.25 if sku == "JUICE-1L" else 0.05
                season_mult = 1.0 + A * sin_val

                # Festival multiplier
                fest_mult = 1.0
                if c["is_festival"]:
                    if sku in ["OIL-1L", "ATTA-5KG", "BISC-250", "CHIPS-90G", "TEA-250G", "JUICE-1L"]:
                        fest_mult = 1.50
                    else:
                        fest_mult = 1.20

                # Base for all stores on day d and sku p
                for s_idx in range(n_stores):
                    pr_mult = 1.0
                    if promo_flag[d, s_idx, p_idx]:
                        pr_mult = 1.35
                    elif post_promo_flag[d, s_idx, p_idx]:
                        pr_mult = 0.85

                    mean_val = (base_units[p_idx] *
                                store_sizes[s_idx] *
                                w_mult *
                                season_mult *
                                fest_mult *
                                pr_mult *
                                trend_mult)
                    mu[d, s_idx, p_idx] = mean_val

        # Sample Negative-Binomial demand using Gamma-Poisson mixture
        # lambda ~ Gamma(shape=1/phi, scale=mu*phi)
        # X ~ Poisson(lambda)
        phi = self.params.demand_model.phi
        shape = 1.0 / phi
        scale = mu * phi
        lam = self.rng_hist.gamma(shape=shape, scale=scale)
        demand = self.rng_hist.poisson(lam)

        # Build records
        sales_records = []
        for d in range(1, n_days + 1):
            for s_idx, s in enumerate(stores):
                s_id = s["store_id"]
                for p_idx, p in enumerate(products):
                    sku_id = p["sku_id"]
                    units = int(demand[d, s_idx, p_idx])
                    sales_records.append({
                        "dataset_id": dataset_id,
                        "store_id": s_id,
                        "sku_id": sku_id,
                        "day": d,
                        "units": units,
                        "promo_flag": int(promo_flag[d, s_idx, p_idx]),
                    })

        return sales_records, mu

    def _generate_window_demand(
        self,
        dataset_id: str,
        stores: List[Dict],
        products: List[Dict],
        mean_demand_matrix: np.ndarray,
    ) -> List[Dict]:
        """Generate seed-specific realization for days 703 to 730."""
        records = []
        seeds = self.params.simulation.seeds
        phi = self.params.demand_model.phi
        shape = 1.0 / phi

        # Generate a child sequence for each seed
        for sim_seed in seeds:
            rng_sim = np.random.default_rng(sim_seed)
            for d in range(703, 731):
                mu_day = mean_demand_matrix[d]  # (25, 12)
                scale = mu_day * phi
                lam = rng_sim.gamma(shape=shape, scale=scale)
                realized = rng_sim.poisson(lam)

                for s_idx, s in enumerate(stores):
                    s_id = s["store_id"]
                    for p_idx, p in enumerate(products):
                        sku_id = p["sku_id"]
                        records.append({
                            "dataset_id": dataset_id,
                            "seed": sim_seed,
                            "store_id": s_id,
                            "sku_id": sku_id,
                            "day": d,
                            "units": int(realized[s_idx, p_idx]),
                        })
        return records

    def _generate_initial_batches(
        self,
        dataset_id: str,
        warehouses: List[Dict],
        products: List[Dict],
        mean_demand_matrix: np.ndarray,
    ) -> List[Dict]:
        """Generate warehouse batches for day 703 per FR-DAT-04."""
        as_of_day = 703
        batches = []

        # Mean 9-day network demand per SKU: sum over 9 days across all 25 stores
        mean_9d_network = np.sum(mean_demand_matrix[703:712], axis=(0, 1))  # (12,)

        for p_idx, p in enumerate(products):
            sku_id = p["sku_id"]
            shelf_life = p["shelf_life_days"]
            total_wh_stock = int(round(1.5 * mean_9d_network[p_idx]))

            for w in warehouses:
                w_id = w["warehouse_id"]
                w_stock = int(round(total_wh_stock * w["inbound_weight"]))
                
                # Split into 2 to 4 batches
                n_batches = self.rng_init.integers(2, 5)
                shares = self.rng_init.dirichlet([1.0] * n_batches)
                batch_qtys = [int(round(w_stock * sh)) for sh in shares]
                # Fix rounding discrepancy on last batch
                diff = w_stock - sum(batch_qtys)
                batch_qtys[-1] += diff

                for b_idx, b_qty in enumerate(batch_qtys):
                    if b_qty <= 0:
                        b_qty = 1
                    # Remaining life fraction between 30% and 100%
                    frac = self.rng_init.uniform(0.30, 1.00)
                    rem_days = max(1, int(round(frac * shelf_life)))
                    expiry_day = as_of_day + rem_days
                    b_id = generate_batch_id(w_id, sku_id, expiry_day, b_idx + 1)

                    batches.append({
                        "dataset_id": dataset_id,
                        "batch_id": b_id,
                        "warehouse_id": w_id,
                        "sku_id": sku_id,
                        "as_of_day": as_of_day,
                        "qty": b_qty,
                        "expiry_day": expiry_day,
                    })

        return batches

    def _generate_initial_store_stock(
        self,
        dataset_id: str,
        stores: List[Dict],
        products: List[Dict],
        mean_demand_matrix: np.ndarray,
    ) -> List[Dict]:
        """Generate store on-hand stock for day 703 per FR-DAT-04."""
        as_of_day = 703
        records = []

        # Store on-hand = 3 days of mean demand
        mean_3d = np.sum(mean_demand_matrix[703:706], axis=0)  # (25, 12)

        for s_idx, s in enumerate(stores):
            s_id = s["store_id"]
            for p_idx, p in enumerate(products):
                sku_id = p["sku_id"]
                shelf_life = p["shelf_life_days"]
                onhand_qty = int(round(mean_3d[s_idx, p_idx]))
                if onhand_qty <= 0:
                    onhand_qty = 5

                # Remaining life between 40% and 100%
                frac = self.rng_init.uniform(0.40, 1.00)
                rem_days = max(1, int(round(frac * shelf_life)))
                expiry_day = as_of_day + rem_days

                records.append({
                    "dataset_id": dataset_id,
                    "as_of_day": as_of_day,
                    "store_id": s_id,
                    "sku_id": sku_id,
                    "qty": onhand_qty,
                    "expiry_day": expiry_day,
                })

        return records

    def _generate_inbound_schedule(
        self,
        dataset_id: str,
        warehouses: List[Dict],
        products: List[Dict],
        mean_demand_matrix: np.ndarray,
    ) -> List[Dict]:
        """Generate scheduled warehouse inbound arrivals for days 703, 710, 717, 724."""
        records = []
        plan_days = [703, 710, 717, 724]
        scenarios = [("normal", 1.05), ("scarcity", 0.80)]

        for p_day in plan_days:
            # 7-day mean network demand
            mean_7d_network = np.sum(mean_demand_matrix[p_day:p_day + 7], axis=(0, 1))  # (12,)

            for sc_name, sc_factor in scenarios:
                for p_idx, p in enumerate(products):
                    sku_id = p["sku_id"]
                    shelf_life = p["shelf_life_days"]
                    total_inbound = int(round(sc_factor * mean_7d_network[p_idx]))

                    # Expiry date calculation per Appendix C
                    if shelf_life <= 14:
                        expiry_day = p_day + shelf_life - 1
                    else:
                        expiry_day = p_day + int(round(0.90 * shelf_life))

                    for w in warehouses:
                        w_id = w["warehouse_id"]
                        w_inbound = int(round(total_inbound * w["inbound_weight"]))
                        if w_inbound <= 0:
                            w_inbound = 1

                        records.append({
                            "dataset_id": dataset_id,
                            "supply_scenario": sc_name,
                            "day": p_day,
                            "warehouse_id": w_id,
                            "sku_id": sku_id,
                            "qty": w_inbound,
                            "expiry_day": expiry_day,
                        })

        return records

    def _compute_dataset_hash(self, **tables: List[Dict]) -> str:
        """Compute canonical SHA-256 hash per Database Schema §9."""
        hasher = hashlib.sha256()
        
        table_order = [
            "warehouses", "stores", "products", "lanes", "calendar",
            "promo_windows", "sales_daily", "batches", "inbound_schedule", "store_stock"
        ]

        for tname in table_order:
            rows = tables[tname]
            hasher.update(f"{tname}:{len(rows)}\n".encode("utf-8"))
            if not rows:
                continue

            df = pd.DataFrame(rows)
            # Exclude dataset_id from canonical hash
            if "dataset_id" in df.columns:
                df = df.drop(columns=["dataset_id"])

            # Sort deterministically
            sort_cols = [c for c in df.columns if c not in ["name", "festival_name"]]
            df = df.sort_values(by=sort_cols).reset_index(drop=True)

            csv_text = df.to_csv(index=False, float_format="%.6f", lineterminator="\n")
            hasher.update(csv_text.encode("utf-8"))

        return hasher.hexdigest()
