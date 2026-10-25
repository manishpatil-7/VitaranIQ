"""
Baseline Policy B2: Reorder-Up-To with 25% Buffer.
Implements FR-SIM-03.
"""

from typing import Dict, Tuple
from vitaraniq.sim.policies.b1 import PolicyB1


class PolicyB2(PolicyB1):
    name: str = "B2"

    def __init__(self, sales_history_means: Dict[Tuple[str, str], float]):
        super().__init__(sales_history_means=sales_history_means, buffer_factor=1.25)
