import uuid
import hashlib
from datetime import datetime, timezone


def generate_plan_id() -> str:
    """Generate plan id with 'p_' prefix."""
    return f"p_{uuid.uuid4().hex[:8]}"


def generate_run_id() -> str:
    """Generate backtest run id with 'r_' prefix."""
    return f"r_{uuid.uuid4().hex[:8]}"


def generate_job_id() -> str:
    """Generate background job id with 'j_' prefix."""
    return f"j_{uuid.uuid4().hex[:8]}"


def generate_batch_id(warehouse_id: str, sku_id: str, expiry_day: int, index: int) -> str:
    """Generate deterministic batch ID."""
    return f"B-{warehouse_id}-{sku_id}-D{expiry_day}-{index:02d}"


def compute_sha256(content: str) -> str:
    """Compute standard SHA-256 hex string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()
