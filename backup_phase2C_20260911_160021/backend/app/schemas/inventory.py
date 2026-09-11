from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator


class StockReceiptLineInput(BaseModel):
    ingredient_id: str
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class StockReceiptInput(BaseModel):
    school_id: str
    receipt_date: date
    receipt_no: str = Field(min_length=1, max_length=80)
    source_name: str | None = Field(default=None, max_length=200)
    remarks: str | None = Field(default=None, max_length=1000)
    lines: list[StockReceiptLineInput]

    @model_validator(mode="after")
    def validate_lines(self):
        if not self.lines:
            raise ValueError("At least one stock receipt line is required")
        ingredient_ids = [x.ingredient_id for x in self.lines]
        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValueError("Duplicate ingredient lines are not allowed")
        return self


class StockOpeningInput(BaseModel):
    school_id: str
    opening_date: date
    ingredient_id: str
    quantity: Decimal = Field(gt=0)
    remarks: str | None = Field(default=None, max_length=1000)
