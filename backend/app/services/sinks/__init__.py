"""Pluggable result sinks.

The app always persists results to its own local database (see TaskRepository).
A ResultSink is an OPTIONAL extra destination for the *result records* only —
e.g. the data team's analysis database — configured via settings.result_sink_url.
Application state (tasks, logs) never leaves the local store.
"""

from app.services.sinks.base import ResultSink
from app.services.sinks.factory import build_sink
from app.services.sinks.null_sink import NullSink

__all__ = ["NullSink", "ResultSink", "build_sink"]
