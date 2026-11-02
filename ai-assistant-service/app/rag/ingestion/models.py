from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class ElementType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"


class Element(BaseModel):
    type: ElementType
    text: str
    page_start: int = Field(ge=1, description="1-based starting page number")
    page_end: int = Field(ge=1, description="1-based ending page number")
    heading_path: list[str] = Field(
        default_factory=list,
        description="Hierarchical heading breadcrumb path for this element (e.g. ['Section 1', 'Sub-heading'])"
    )

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Element text cannot be empty or whitespace only.")
        return stripped

    @model_validator(mode="after")
    def validate_page_range(self) -> "Element":
        if self.page_end < self.page_start:
            raise ValueError(
                f"page_end ({self.page_end}) cannot be less than page_start ({self.page_start})."
            )
        return self


class QualityReport(BaseModel):
    page_count: int = Field(ge=0, description="Total page count")
    empty_pages: list[int] = Field(
        default_factory=list,
        description="List of 1-based page numbers that contain no text"
    )
    suspect_char_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Ratio of corrupt or control characters to total text length"
    )
    status: Literal["ok", "quarantine"] = Field(
        default="ok",
        description="Document health status ('ok' or 'quarantine')"
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Reasons for quarantine or quality warnings"
    )


class ParsedDocument(BaseModel):
    source_file: str = Field(description="Source file name or path")
    elements: list[Element] = Field(
        default_factory=list,
        description="Ordered list of parsed structural elements"
    )
    quality: QualityReport = Field(description="Document quality assessment report")
    parser_name: str = Field(description="Parser engine name (e.g. pymupdf4llm)")
    parser_version: str = Field(description="Version of the parser engine")
