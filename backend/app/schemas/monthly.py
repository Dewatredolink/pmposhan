from pydantic import BaseModel, Field


class MonthlyGenerateInput(BaseModel):
    school_id: str
    year: int = Field(ge=2000, le=2200)
    month: int = Field(ge=1, le=12)


class MonthlyActionInput(BaseModel):
    remarks: str | None = Field(default=None, max_length=1000)


class OrgAccessInput(BaseModel):
    keycloak_subject: str = Field(min_length=3, max_length=64)
    username: str = Field(min_length=1, max_length=120)
    role: str
    district_id: str | None = None
    block_id: str | None = None
    cluster_id: str | None = None
