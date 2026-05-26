# api/__init__.py

from api.routers.cars import router as cars_router
from api.routers.costs import router as costs_router
from api.routers.reports import router as reports_router
from api.routers.predictions import router as predictions_router

__all__ = ["cars_router", "costs_router", "reports_router", "predictions_router"]