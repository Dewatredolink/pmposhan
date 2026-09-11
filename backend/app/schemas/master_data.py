from datetime import date
from pydantic import BaseModel, Field, model_validator


class DistrictMasterInput(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name_en: str = Field(min_length=1, max_length=200)
    name_mr: str = Field(min_length=1, max_length=200)
    active: bool = True


class BlockMasterInput(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    district_id: str
    name_en: str = Field(min_length=1, max_length=200)
    name_mr: str = Field(min_length=1, max_length=200)
    active: bool = True


class ClusterMasterInput(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    block_id: str
    name_en: str = Field(min_length=1, max_length=200)
    name_mr: str = Field(min_length=1, max_length=200)
    active: bool = True


class SchoolMasterInput(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    udise_code: str = Field(min_length=1, max_length=30)
    cluster_id: str
    name_en: str = Field(min_length=1, max_length=250)
    name_mr: str = Field(min_length=1, max_length=250)
    village: str | None = Field(default=None, max_length=200)
    class_1_5_strength: int = Field(default=0, ge=0)
    class_6_8_strength: int = Field(default=0, ge=0)
    active: bool = True


class IngredientMasterInput(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name_en: str = Field(min_length=1, max_length=200)
    name_mr: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    base_unit: str = Field(min_length=1, max_length=20)
    reorder_level: float = Field(default=0, ge=0)
    safety_stock: float = Field(default=0, ge=0)
    track_inventory: bool = True
    active: bool = True


class MenuMasterInput(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name_en: str = Field(min_length=1, max_length=200)
    name_mr: str = Field(min_length=1, max_length=200)
    week_pattern: str = Field(default="CUSTOM", min_length=1, max_length=10)
    day_of_week: int = Field(default=1, ge=1, le=6)
    active: bool = True


class RecipeStandardLine(BaseModel):
    ingredient_id: str
    qty_class_1_5: float = Field(default=0, ge=0)
    qty_class_6_8: float = Field(default=0, ge=0)
    unit: str = Field(min_length=1, max_length=20)


class RecipeStandardInput(BaseModel):
    effective_from: date
    items: list[RecipeStandardLine]


class CustomReportInput(BaseModel):
    report_type: str
    language: str = "en"
    columns: list[str] = []
    district_id: str | None = None
    block_id: str | None = None
    cluster_id: str | None = None
    school_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    year: int | None = None
    month: int | None = None
    max_preview_rows: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def validate_period(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be after date_to")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError("month must be 1-12")
        if self.language not in {"en", "mr"}:
            raise ValueError("language must be en or mr")
        return self
