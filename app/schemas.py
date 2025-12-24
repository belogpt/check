import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, validator

from app.models import ReceiptStatus, UnitStatus


class ItemBase(BaseModel):
    name: str
    qty_total: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    amount_total: float = Field(..., ge=0)

    @validator("amount_total")
    def validate_amount(cls, value, values):
        qty = values.get("qty_total")
        unit = values.get("unit_price")
        if qty and unit and value == 0:
            return value
        if qty and unit and value < unit * qty * 0.5:
            # allow some OCR noise but avoid clear mistakes
            return round(value, 2)
        return round(value, 2)


class ParsedOcrItem(BaseModel):
    name: str
    price: float
    quantity: int
    total: float
    is_promo: bool = False
    parse_error: bool = False


class ItemSchema(ItemBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class ItemUpdate(BaseModel):
    items: list[ItemBase]


class ItemUnitSchema(BaseModel):
    id: uuid.UUID
    unit_index: int
    amount_total: float
    amount_paid: float
    status: UnitStatus

    class Config:
        orm_mode = True


class ItemWithUnits(BaseModel):
    id: uuid.UUID
    name: str
    qty_total: int
    unit_price: float
    amount_total: float
    units: list[ItemUnitSchema]

    class Config:
        orm_mode = True


class PaymentSchema(BaseModel):
    id: uuid.UUID
    payer_name: str
    amount: float
    unit_id: uuid.UUID
    created_at: datetime

    class Config:
        orm_mode = True


class ReceiptRoomResponse(BaseModel):
    token: str
    status: ReceiptStatus
    items: list[ItemWithUnits]
    payments: list[PaymentSchema]
    created_at: datetime

    class Config:
        orm_mode = True


class PaymentLine(BaseModel):
    item_id: uuid.UUID
    mode: Literal["unit_full", "unit_partial"]
    unit_id: uuid.UUID | None = None
    amount: float | None = None

    @validator("amount")
    def validate_amount(cls, value, values):
        if values.get("mode") == "unit_partial" and (value is None or value <= 0):
            raise ValueError("amount is required for partial payments")
        return value

    @validator("unit_id")
    def validate_unit_id(cls, value, values):
        if values.get("mode") == "unit_partial" and value is None:
            raise ValueError("unit_id is required for partial payments")
        return value


class PaymentRequest(BaseModel):
    payer_name: str
    lines: list[PaymentLine]


class FinalizeResponse(BaseModel):
    room_url: str


class ReceiptUploadResponse(BaseModel):
    receipt_id: uuid.UUID
    items: list[ItemSchema]


class OcrPreviewResponse(BaseModel):
    ocr_text: str
    items: list[ParsedOcrItem]


class HealthResponse(BaseModel):
    status: str


class ReceiptListItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    status: ReceiptStatus

    class Config:
        orm_mode = True
