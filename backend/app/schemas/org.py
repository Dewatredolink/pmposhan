from pydantic import BaseModel, ConfigDict

class DistrictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name_en: str
    name_mr: str
    active: bool

class SchoolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    udise_code: str
    name_en: str
    name_mr: str
    village: str | None
    class_1_5_strength: int
    class_6_8_strength: int
    active: bool
