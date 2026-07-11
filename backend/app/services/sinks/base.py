from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ResultSink(Protocol):
    """A destination for extracted result records beyond the local store."""

    async def write(self, task_id: str, url: str, records: list[dict[str, Any]]) -> None: ...

    async def aclose(self) -> None: ...
