import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.api.v1.tasks import _summary as _task_summary
from app.core.config import get_settings
from app.models.orm import ScrapeBatch
from app.models.schemas import (
    BatchDetail,
    BatchListResponse,
    BatchRequest,
    BatchSummary,
    ScrapeStatus,
)
from app.repository import BatchRepository
from app.services import export_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batches"])


def _summary(batch: ScrapeBatch) -> BatchSummary:
    return BatchSummary(
        id=batch.id,
        prompt=batch.prompt,
        status=ScrapeStatus(batch.status),
        total=batch.total,
        completed=batch.completed,
        failed=batch.failed,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )


@router.post("/batch", response_model=BatchSummary, status_code=202)
async def start_batch(request: Request, payload: BatchRequest) -> BatchSummary:
    """Accept a batch and run it in the background; poll GET /batches/{id} for progress."""
    settings = get_settings()
    if len(payload.urls) > settings.batch_max_urls:
        raise HTTPException(
            status_code=422,
            detail=f"At most {settings.batch_max_urls} URLs per batch",
        )

    batch_repo: BatchRepository = request.app.state.batch_repo
    batch_id = uuid.uuid4().hex
    urls = [str(u) for u in payload.urls]
    await batch_repo.create(batch_id, payload.prompt, len(urls))

    runner = request.app.state.batch_runner
    task = asyncio.create_task(
        runner.run(batch_id, urls, payload.prompt, payload.options.model_dump(exclude_none=True))
    )
    # Hold a reference so the task is not garbage-collected mid-flight.
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    batch = await batch_repo.get(batch_id)
    assert batch is not None
    return _summary(batch)


@router.get("/batches", response_model=BatchListResponse)
async def list_batches(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> BatchListResponse:
    repo: BatchRepository = request.app.state.batch_repo
    batches, total = await repo.list_batches(limit=limit, offset=offset)
    return BatchListResponse(
        total=total, limit=limit, offset=offset, items=[_summary(b) for b in batches]
    )


@router.get("/batches/{batch_id}", response_model=BatchDetail)
async def get_batch(request: Request, batch_id: str) -> BatchDetail:
    repo: BatchRepository = request.app.state.batch_repo
    batch = await repo.get(batch_id, with_tasks=True)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return BatchDetail(
        **_summary(batch).model_dump(),
        error_message=batch.error_message,
        shared_plan=batch.shared_plan,
        tasks=[_task_summary(t) for t in batch.tasks],
    )


@router.get("/batches/{batch_id}/export")
async def export_batch(
    request: Request,
    batch_id: str,
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
) -> Response:
    """Every member task's records in one file, each row tagged with its source URL."""
    repo: BatchRepository = request.app.state.batch_repo
    if await repo.get(batch_id) is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    records = await repo.records_for_export(batch_id)
    if not records:
        raise HTTPException(status_code=404, detail="No result records for this batch")

    if format == "csv":
        return Response(
            content=export_service.to_csv(records),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="batch-{batch_id}.csv"'},
        )
    return Response(
        content=export_service.to_xlsx(records),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="batch-{batch_id}.xlsx"'},
    )
