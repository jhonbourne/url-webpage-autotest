from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.models.orm import ScrapeTask
from app.models.schemas import TaskDetail, TaskListResponse, TaskSummary
from app.repository import TaskRepository
from app.services import export_service

router = APIRouter(tags=["tasks"])


def _summary(task: ScrapeTask) -> TaskSummary:
    return TaskSummary(
        id=task.id,
        url=task.url,
        prompt=task.prompt,
        status=task.status,
        strategy=task.strategy,
        row_count=task.row_count,
        error_code=task.error_code,
        created_at=task.created_at,
        finished_at=task.finished_at,
    )


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TaskListResponse:
    repo: TaskRepository = request.app.state.task_repo
    tasks, total = await repo.list_tasks(limit=limit, offset=offset)
    return TaskListResponse(
        total=total, limit=limit, offset=offset, items=[_summary(t) for t in tasks]
    )


@router.get("/tasks/{task_id}", response_model=TaskDetail)
async def get_task(request: Request, task_id: str) -> TaskDetail:
    repo: TaskRepository = request.app.state.task_repo
    task = await repo.get_task(task_id, with_result=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = task.result
    return TaskDetail(
        **_summary(task).model_dump(),
        fetch_method=task.fetch_method,
        error_message=task.error_message,
        execution_log=task.execution_log or [],
        fields=result.fields if result else [],
        records=result.records if result else [],
        field_coverage=result.field_coverage if result else {},
        validation=result.validation if result else None,
    )


@router.get("/tasks/{task_id}/export")
async def export_task(
    request: Request,
    task_id: str,
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
) -> Response:
    repo: TaskRepository = request.app.state.task_repo
    result = await repo.get_result(task_id)
    if result is None or not result.records:
        raise HTTPException(status_code=404, detail="No result records for this task")

    if format == "csv":
        return Response(
            content=export_service.to_csv(result.records),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{task_id}.csv"'},
        )
    return Response(
        content=export_service.to_xlsx(result.records),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{task_id}.xlsx"'},
    )
