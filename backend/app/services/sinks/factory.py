import logging

from app.core.config import Settings
from app.services.sinks.base import ResultSink
from app.services.sinks.null_sink import NullSink

logger = logging.getLogger(__name__)


def build_sink(settings: Settings) -> ResultSink:
    if settings.result_sink_url:
        from app.services.sinks.sql_sink import SqlResultSink

        logger.info("external result sink enabled")
        return SqlResultSink(settings.result_sink_url)
    return NullSink()
