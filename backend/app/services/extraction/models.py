"""Internal models for the extraction pipeline (not API-facing)."""

from typing import Literal

from pydantic import BaseModel, Field

FieldType = Literal["string", "number", "url", "boolean", "array"]
Strategy = Literal["selector", "llm"]


class FieldSpec(BaseModel):
    name: str = Field(description="snake_case key used in the output records")
    description: str = Field(description="What this field contains, for the extractor")
    type: FieldType = "string"


class ExtractionPlan(BaseModel):
    """The planner's structured reading of the user's natural-language request."""

    is_extractable: bool = Field(description="Whether the request can be fulfilled from this page")
    reason: str = Field(default="", description="Why not, when is_extractable is false")
    is_list: bool = Field(
        default=True, description="True if the page holds many records; False for a single record"
    )
    fields: list[FieldSpec] = Field(default_factory=list)
    suggested_strategy: Strategy = Field(
        default="llm",
        description="'selector' for regular repeated markup, 'llm' for irregular content",
    )


class FieldSelector(BaseModel):
    selector: str = Field(description="CSS selector, relative to the record container")
    # Where the value lives: element text, or a named attribute (e.g. href, src)
    attr: str = Field(default="text")
    # True for list-valued fields (e.g. tags): match all elements, return a list
    multiple: bool = Field(default=False)


class SelectorPlan(BaseModel):
    """A declarative extraction plan executed by SelectorExecutor (no code execution)."""

    # CSS selector matching each record container; empty for single-record pages
    record_selector: str = Field(default="")
    fields: dict[str, FieldSelector] = Field(default_factory=dict)
