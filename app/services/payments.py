import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ItemUnit, Payment, Receipt, ReceiptStatus, UnitStatus


class PaymentError(Exception):
    pass


async def _lock_receipt(session: AsyncSession, token: str) -> Receipt:
    result = await session.execute(select(Receipt).where(Receipt.token == token).with_for_update())
    receipt = result.scalar_one_or_none()
    if not receipt:
        raise PaymentError("Receipt not found")
    if receipt.status != ReceiptStatus.open:
        raise PaymentError("Receipt is not open for payments")
    return receipt


async def pay_full_unit(session: AsyncSession, item_id: uuid.UUID, receipt_id: uuid.UUID) -> tuple[ItemUnit, float]:
    unit_stmt = (
        select(ItemUnit)
        .join(ItemUnit.item)
        .where(
            ItemUnit.item_id == item_id,
            ItemUnit.amount_paid < ItemUnit.amount_total,
            ItemUnit.item.has(receipt_id=receipt_id),
        )
        .with_for_update(skip_locked=True)
        .order_by(ItemUnit.unit_index)
    )
    result = await session.execute(unit_stmt)
    unit = result.scalars().first()
    if not unit:
        raise PaymentError("No unpaid units available")
    remaining = Decimal(unit.amount_total) - Decimal(unit.amount_paid)
    unit.amount_paid = Decimal(unit.amount_paid) + remaining
    unit.status = UnitStatus.paid
    return unit, float(remaining)


async def pay_partial_unit(session: AsyncSession, unit_id: uuid.UUID, amount: float, receipt_id: uuid.UUID) -> tuple[ItemUnit, float]:
    unit_stmt = select(ItemUnit).where(ItemUnit.id == unit_id, ItemUnit.item.has(receipt_id=receipt_id)).with_for_update()
    result = await session.execute(unit_stmt)
    unit = result.scalar_one_or_none()
    if not unit:
        raise PaymentError("Unit not found")
    remaining = Decimal(unit.amount_total) - Decimal(unit.amount_paid)
    amount_decimal = Decimal(str(amount))
    if amount_decimal <= 0:
        raise PaymentError("Amount must be positive")
    if amount_decimal > remaining:
        raise PaymentError("Payment exceeds remaining balance")
    unit.amount_paid = Decimal(unit.amount_paid) + amount_decimal
    if unit.amount_paid == unit.amount_total:
        unit.status = UnitStatus.paid
    else:
        unit.status = UnitStatus.partial
    return unit, float(amount_decimal)


async def finalize_receipt_if_paid(session: AsyncSession, receipt: Receipt) -> None:
    await session.refresh(receipt, attribute_names=["items"])
    for item in receipt.items:
        await session.refresh(item, attribute_names=["units"])
    all_paid = all(unit.status == UnitStatus.paid for item in receipt.items for unit in item.units)
    if all_paid and receipt.items:
        receipt.status = ReceiptStatus.paid


async def record_payment(
    session: AsyncSession, receipt: Receipt, unit: ItemUnit, amount: float, payer_name: str
) -> Payment:
    payment = Payment(
        receipt_id=receipt.id,
        item_id=unit.item_id,
        unit_id=unit.id,
        payer_name=payer_name,
        amount=Decimal(str(amount)),
    )
    session.add(payment)
    return payment


async def process_payment_lines(
    session: AsyncSession, token: str, payer_name: str, lines: list[dict]
) -> list[Payment]:
    receipt = await _lock_receipt(session, token)
    payments: list[Payment] = []
    for line in lines:
        mode = line["mode"]
        item_id = line["item_id"]
        if mode == "unit_full":
            unit, amount = await pay_full_unit(session, item_id=item_id, receipt_id=receipt.id)
            payment = await record_payment(session, receipt, unit, amount, payer_name)
        else:
            unit_id = line["unit_id"]
            amount = line["amount"]
            unit, amount = await pay_partial_unit(session, unit_id=unit_id, amount=amount, receipt_id=receipt.id)
            payment = await record_payment(session, receipt, unit, amount, payer_name)
        payments.append(payment)
    await session.flush()
    await finalize_receipt_if_paid(session, receipt)
    return payments
