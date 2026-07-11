"""Export extracted records to CSV / Excel via pandas.

List-valued (array) fields are joined with ", " so they render in a flat table.
"""

import io
from typing import Any

import pandas as pd


def _flatten(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat = []
    for r in records:
        flat.append(
            {k: ", ".join(map(str, v)) if isinstance(v, list) else v for k, v in r.items()}
        )
    return flat


def to_csv(records: list[dict[str, Any]]) -> bytes:
    df = pd.DataFrame(_flatten(records))
    return df.to_csv(index=False).encode("utf-8-sig")  # BOM so Excel opens UTF-8 cleanly


def to_xlsx(records: list[dict[str, Any]]) -> bytes:
    df = pd.DataFrame(_flatten(records))
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="records")
    return buffer.getvalue()
