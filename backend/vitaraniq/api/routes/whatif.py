"""
What-If Disruption Scenario Routes.
Conforms to System Architecture §6, SRS FR-WIF-01..05, and AIML Design §7.
"""

from fastapi import APIRouter, HTTPException
from vitaraniq.services.whatif_svc import WhatIfService
from vitaraniq.api.schemas import WhatIfOutageRequest, WhatIfResponse

router = APIRouter(prefix="/whatif", tags=["What-If Scenarios"])


@router.post("", response_model=WhatIfResponse)
def run_whatif_outage(req: WhatIfOutageRequest):
    try:
        res = WhatIfService.run_warehouse_outage(
            base_plan_id=req.base_plan_id,
            outage_warehouse_id=req.outage_warehouse_id,
            workers=req.workers,
        )
        return WhatIfResponse(
            whatif_plan_id=res["whatif_plan_id"],
            base_plan_id=res["base_plan_id"],
            outage_warehouse_id=res["outage_warehouse_id"],
            comparison=res["comparison"],
            displaced_stores=res["displaced_stores"],
            new_routes=res["new_routes"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
