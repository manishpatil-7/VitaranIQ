"""
FastAPI Application Entrypoint.
Conforms to System Architecture §6.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.staticfiles import StaticFiles

from vitaraniq.api.errors import VitaranIQError, vitaraniq_exception_handler
from vitaraniq.api.routes.health import router as health_router
from vitaraniq.api.routes.data import router as data_router
from vitaraniq.api.routes.forecast import router as forecast_router
from vitaraniq.api.routes.plan import router as plan_router
from vitaraniq.api.routes.whatif import router as whatif_router
from vitaraniq.api.routes.backtest import router as backtest_router

app = FastAPI(
    title="VitaranIQ: AI-Powered Distribution Intelligence Engine",
    description="FMCG multi-echelon inventory optimization, quantile forecasting, and FEFO dispatch engine.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware for frontend dashboard integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom exception handlers
app.add_exception_handler(VitaranIQError, vitaraniq_exception_handler)

# Include API v1 Routers
api_v1_prefix = "/api/v1"
app.include_router(health_router, prefix=api_v1_prefix)
app.include_router(data_router, prefix=api_v1_prefix)
app.include_router(forecast_router, prefix=api_v1_prefix)
app.include_router(plan_router, prefix=api_v1_prefix)
app.include_router(whatif_router, prefix=api_v1_prefix)
app.include_router(backtest_router, prefix=api_v1_prefix)


# Mount frontend static assets if built, else return API root info
web_dist = Path(__file__).resolve().parents[3] / "web" / "dist"
if web_dist.exists() and web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="static")
else:
    @app.get("/")
    def root():
        return {
            "engine": "VitaranIQ",
            "description": "FMCG Distribution Intelligence & Inventory Optimization Engine",
            "docs": "/docs",
            "health": "/api/v1/health",
            "version": "1.0.0",
        }
