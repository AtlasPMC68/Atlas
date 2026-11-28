from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LabelStyle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=50)
    size_px: int = Field(ge=6, le=96)
    font_style: Literal["normal", "italic"]
    font_weight: Literal["normal", "bold"] = "normal"
    bold: bool = False
    text_transform: Literal["none", "uppercase"]
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    priority: int = Field(default=30, ge=0, le=100)
    min_zoom: float = Field(default=1.0, ge=0, le=20)
    has_point: bool = False
    point_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    point_stroke_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    point_fill_opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    point_stroke_opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    point_stroke_width: float | None = Field(default=None, ge=0.0, le=20.0)


class LabelStylesRequest(BaseModel):
    styles: list[LabelStyle] = Field(max_length=100)

    def unique_ids(self) -> bool:
        ids = [style.id for style in self.styles]
        return len(ids) == len(set(ids))
