from typing import Any


class NullSink:
    """Default sink: results stay in the local store only."""

    async def write(self, task_id: str, url: str, records: list[dict[str, Any]]) -> None:
        return None

    async def aclose(self) -> None:
        return None
