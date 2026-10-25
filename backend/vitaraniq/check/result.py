"""
Plan-Checker Result Data Contract.
Implements FR-CHK-01..03.
"""

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Violation:
    check_id: int
    check_name: str
    entity: str
    detail: str


@dataclass
class CheckResult:
    status: str  # "PASS" or "FAIL"
    violations: List[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "PASS" and len(self.violations) == 0

    def raise_if_failed(self):
        if not self.passed:
            details = "; ".join(f"[{v.check_name}] {v.entity}: {v.detail}" for v in self.violations)
            raise ValueError(f"PLAN_CHECK_FAILED: {details}")
