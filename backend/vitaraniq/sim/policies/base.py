"""
Base Policy Protocol for VitaranIQ Backtest Simulator.
Implements FR-SIM-05 (all 4 policies implement the exact same plan() interface).
"""

from typing import Any, Dict, List, Protocol
from vitaraniq.db.snapshot import Snapshot


class Policy(Protocol):
    name: str

    def plan(self, snapshot: Snapshot, day: int) -> List[Dict[str, Any]]:
        """
        Produce a list of verified plan lines:
        [{"sku_id", "warehouse_id", "store_id", "batch_id", "batch_expiry_day", "qty", "trucks_on_lane", "line_cost_paise"}]
        """
        ...
