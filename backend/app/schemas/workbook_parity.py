from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator


class StockLoanInput(BaseModel):
    school_id: str
    loan_date: date
    loan_no: str = Field(min_length=1, max_length=80)
    direction: str
    counterparty_name: str = Field(min_length=1, max_length=250)
    ingredient_id: str
    quantity: Decimal = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_direction(self):
        self.direction = self.direction.upper()
        if self.direction not in {"RECEIVED", "GIVEN"}:
            raise ValueError("direction must be RECEIVED or GIVEN")
        return self


class BmiRecordInput(BaseModel):
    school_id: str
    measurement_date: date
    student_identifier: str | None = Field(default=None, max_length=80)
    student_name: str = Field(min_length=1, max_length=250)
    class_name: str | None = Field(default=None, max_length=40)
    gender: str | None = Field(default=None, max_length=20)
    height_cm: Decimal = Field(gt=0, le=300)
    weight_kg: Decimal = Field(gt=0, le=500)
    remarks: str | None = Field(default=None, max_length=1000)
