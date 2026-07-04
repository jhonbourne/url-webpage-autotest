from fastapi import APIRouter

from app.api.v1.scrape import router as scrape_router

router = APIRouter(prefix="/api/v1")
router.include_router(scrape_router)
