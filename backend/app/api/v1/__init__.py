from fastapi import APIRouter

from app.api.v1.batches import router as batches_router
from app.api.v1.scrape import router as scrape_router
from app.api.v1.tasks import router as tasks_router

router = APIRouter(prefix="/api/v1")
router.include_router(scrape_router)
router.include_router(tasks_router)
router.include_router(batches_router)
