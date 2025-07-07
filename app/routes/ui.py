
from fastapi import APIRouter
from . import auth_routes, benchmark_routes, report_routes

router = APIRouter()

router.include_router(auth_routes.router)
router.include_router(benchmark_routes.router)
router.include_router(report_routes.router)
