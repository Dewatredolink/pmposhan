from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SchoolProfileUpsert(BaseModel):
    kitchen_type: str = "SCHOOL_KITCHEN"
    cooking_agency: str | None = None
    headmaster_name: str | None = None
    meal_incharge_name: str | None = None
    contact_mobile: str | None = None


class AttendanceInput(BaseModel):
    school_id: str
    meal_date: date
    class_1_5_enrolled: int = Field(ge=0)
    class_1_5_present: int = Field(ge=0)
    class_6_8_enrolled: int = Field(ge=0)
    class_6_8_present: int = Field(ge=0)
    status: str = "DRAFT"

    @model_validator(mode="after")
    def validate_present(self):
        if self.class_1_5_present > self.class_1_5_enrolled:
            raise ValueError("Class 1-5 present count cannot exceed enrolled count")
        if self.class_6_8_present > self.class_6_8_enrolled:
            raise ValueError("Class 6-8 present count cannot exceed enrolled count")
        if self.status not in {"DRAFT", "SUBMITTED"}:
            raise ValueError("Status must be DRAFT or SUBMITTED")
        return self


class MealInput(BaseModel):
    school_id: str
    meal_date: date
    menu_id: str
    meals_class_1_5: int = Field(ge=0)
    meals_class_6_8: int = Field(ge=0)
    tasting_done: bool = False
    hygiene_ok: bool = False
    remarks: str | None = Field(default=None, max_length=1000)
    status: str = "DRAFT"

    @model_validator(mode="after")
    def validate_status(self):
        if self.status not in {"DRAFT", "SUBMITTED"}:
            raise ValueError("Status must be DRAFT or SUBMITTED")
        return self


class VerifyInput(BaseModel):
    school_id: str
    meal_date: date


class UserSchoolAccessCreate(BaseModel):
    keycloak_subject: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=120)
    school_id: str
    role: str
    preferred_language: str = "mr"
