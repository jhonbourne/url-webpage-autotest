import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.agents.scraper_agent import ScraperAgent
from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory, init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import request_id_var, setup_logging
from app.repository import TaskRepository
from app.services.dom_service import DOMService
from app.services.extraction import (
    ExtractionPlanner,
    LLMExtractor,
    ResultValidator,
    SelectorExecutor,
    SelectorGenerator,
)
from app.services.fetch_service import FetchService
from app.services.llm import build_chat_model
from app.services.sinks import build_sink


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)

    fetch_service = FetchService(settings)
    app.state.fetch_service = fetch_service

    # Persistence: local application-state store + optional external result sink.
    engine = create_engine(settings.database_url)
    await init_db(engine)
    app.state.db_engine = engine
    app.state.task_repo = TaskRepository(create_session_factory(engine))
    app.state.result_sink = build_sink(settings)

    # Role-based models: general reasoning vs. code-specialized (selector generation).
    general_llm = build_chat_model(settings, role="general")
    code_llm = build_chat_model(settings, role="code")
    app.state.agent = ScraperAgent(
        fetch_service=fetch_service,
        dom_service=DOMService(),
        planner=ExtractionPlanner(general_llm),
        selector_generator=SelectorGenerator(code_llm),
        selector_executor=SelectorExecutor(),
        llm_extractor=LLMExtractor(general_llm),
        validator=ResultValidator(min_field_coverage=settings.min_field_coverage),
        max_retries=settings.max_extraction_retries,
    )

    yield

    await fetch_service.aclose()
    await app.state.result_sink.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan, debug=settings.debug)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(v1_router)

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        request_id_var.set(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
