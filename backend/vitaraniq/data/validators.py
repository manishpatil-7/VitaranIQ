"""
Validation module for VitaranIQ data snapshots and tables.
Implements rules V1 through V8 from SRS FR-DAT-06.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ValidationErrorDetail(BaseModel):
    path: str
    issue: str


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[ValidationErrorDetail] = []

    def raise_if_invalid(self):
        if not self.is_valid:
            msg = "; ".join(f"{e.path}: {e.issue}" for e in self.errors)
            raise ValueError(f"VALIDATION_ERROR: {msg}")


def validate_snapshot_data(
    warehouses: List[Dict[str, Any]],
    stores: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    lanes: List[Dict[str, Any]],
    batches: List[Dict[str, Any]],
    store_stock: List[Dict[str, Any]],
    as_of_day: int,
) -> ValidationResult:
    """Validate snapshot collections against rules V1–V8."""
    errors: List[ValidationErrorDetail] = []
    
    wh_ids = {w["warehouse_id"] for w in warehouses}
    store_ids = {s["store_id"] for s in stores}
    sku_ids = set()

    # V4: SKU with non-positive volume, shelf life or cost
    # V5: price <= unit cost
    for p in products:
        sku = p.get("sku_id") or p.get("id")
        sku_ids.add(sku)
        
        vol = p.get("volume_ml", 0)
        shelf = p.get("shelf_life_days", 0)
        cost = p.get("unit_cost_paise", 0)
        price = p.get("price_paise", 0)
        min_life = p.get("min_life_days", 0)

        if vol <= 0:
            errors.append(ValidationErrorDetail(path=f"products[{sku}].volume_ml", issue="must be > 0 (V4)"))
        if shelf <= 0:
            errors.append(ValidationErrorDetail(path=f"products[{sku}].shelf_life_days", issue="must be > 0 (V4)"))
        if cost <= 0:
            errors.append(ValidationErrorDetail(path=f"products[{sku}].unit_cost_paise", issue="must be > 0 (V4)"))
        if price <= cost:
            errors.append(ValidationErrorDetail(path=f"products[{sku}].price_paise", issue="price must be > cost (V5)"))
        if min_life > shelf:
            errors.append(ValidationErrorDetail(path=f"products[{sku}].min_life_days", issue="min_life cannot exceed shelf life"))

    # V3: lane without distance / missing lanes
    lane_pairs = set()
    for l in lanes:
        w_id = l.get("warehouse_id")
        s_id = l.get("store_id")
        km = l.get("km", 0.0)
        if km <= 0:
            errors.append(ValidationErrorDetail(path=f"lanes[{w_id},{s_id}].km", issue="distance must be > 0 (V3)"))
        lane_pairs.add((w_id, s_id))

    for w_id in wh_ids:
        for s_id in store_ids:
            if (w_id, s_id) not in lane_pairs:
                errors.append(ValidationErrorDetail(path=f"lanes[{w_id},{s_id}]", issue="missing lane connection (V3)"))

    # V1, V2, V8 for batches
    for b in batches:
        b_id = b.get("batch_id")
        qty = b.get("qty", 0)
        expiry = b.get("expiry_day", 0)
        w_id = b.get("warehouse_id")
        sku = b.get("sku_id")

        if not isinstance(qty, int) or qty < 0:
            errors.append(ValidationErrorDetail(path=f"batches[{b_id}].qty", issue="must be non-negative integer (V1)"))
        if expiry < as_of_day:
            errors.append(ValidationErrorDetail(path=f"batches[{b_id}].expiry_day", issue=f"expired before as_of_day {as_of_day} (V2)"))
        if w_id not in wh_ids:
            errors.append(ValidationErrorDetail(path=f"batches[{b_id}].warehouse_id", issue=f"referenced unknown warehouse {w_id} (V8)"))
        if sku not in sku_ids:
            errors.append(ValidationErrorDetail(path=f"batches[{b_id}].sku_id", issue=f"referenced unknown sku {sku} (V8)"))

    # V1, V2 for store_stock
    for ss in store_stock:
        s_id = ss.get("store_id")
        sku = ss.get("sku_id")
        qty = ss.get("qty", 0)
        expiry = ss.get("expiry_day", 0)

        if not isinstance(qty, int) or qty < 0:
            errors.append(ValidationErrorDetail(path=f"store_stock[{s_id},{sku}].qty", issue="must be non-negative integer (V1)"))
        if expiry < as_of_day:
            errors.append(ValidationErrorDetail(path=f"store_stock[{s_id},{sku}].expiry_day", issue=f"expired before as_of_day {as_of_day} (V2)"))

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)
