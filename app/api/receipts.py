import logging
import secrets
import uuid
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from pytesseract import TesseractError, TesseractNotFoundError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.websocket_manager import manager
from app.db import get_session
from app.models import ItemUnit, Payment, Receipt, ReceiptItem, ReceiptStatus
from app.schemas import (
    FinalizeResponse,
    ItemSchema,
    ItemUpdate,
    OcrPreviewResponse,
    ParsedOcrItem,
    PaymentRequest,
    ReceiptRoomResponse,
    ReceiptUploadResponse,
)
from app.services.ocr import extract_items
from app.services.payments import PaymentError, process_payment_lines


router = APIRouter(prefix="/api")
settings = get_settings()
logger = logging.getLogger(__name__)


def _validate_upload(file: UploadFile) -> int:
    if not file.content_type or "image" not in file.content_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type")
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    max_bytes = settings.upload_max_mb * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")
    return size


async def _run_ocr(file: UploadFile, media_root: Path) -> tuple[Path, str, list[ParsedOcrItem]]:
    try:
        return await extract_items(file, media_root=media_root)
    except TesseractNotFoundError as exc:
        logger.exception("Tesseract is not installed or not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR недоступен: отсутствует бинарник Tesseract",
        ) from exc
    except TesseractError as exc:
        logger.exception("Tesseract failed to process the image")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR недоступен: отсутствуют языковые данные Tesseract",
        ) from exc
    except ValueError as exc:
        logger.warning("Invalid image data: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось прочитать изображение. Проверьте, что файл является изображением чека.",
        ) from exc
    except Exception as exc:  # pragma: no cover - safety net for unexpected OCR failures
        error_id = uuid.uuid4().hex[:8]
        logger.exception("Failed to process uploaded receipt image (error_id=%s)", error_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось обработать чек (код {error_id})",
        ) from exc


@router.post("/receipts/preview", response_model=OcrPreviewResponse)
async def preview_receipt(file: UploadFile) -> OcrPreviewResponse:
    size = _validate_upload(file)
    logger.info(
        "Previewing receipt upload: filename=%s content_type=%s size_bytes=%s", file.filename, file.content_type, size
    )
    media_root = Path(settings.media_root)
    path, text, parsed_items = await _run_ocr(file, media_root=media_root)
    try:
        return OcrPreviewResponse(ocr_text=text, items=parsed_items)
    finally:
        path.unlink(missing_ok=True)


@router.post("/receipts", response_model=ReceiptUploadResponse)
async def upload_receipt(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> ReceiptUploadResponse:
    size = _validate_upload(file)
    logger.info(
        "Processing receipt upload: filename=%s content_type=%s size_bytes=%s", file.filename, file.content_type, size
    )

    media_root = Path(settings.media_root)
    path, text, parsed_items = await _run_ocr(file, media_root=media_root)
    receipt = Receipt(image_path=str(path), status=ReceiptStatus.draft)
    session.add(receipt)
    await session.flush()
    items: list[ReceiptItem] = []
    for parsed in parsed_items:
        name = parsed.name or "Без названия"
        item = ReceiptItem(
            receipt_id=receipt.id,
            name=name,
            qty_total=parsed.quantity,
            unit_price=parsed.price,
            amount_total=parsed.total,
        )
        session.add(item)
        items.append(item)
    await session.commit()
    logger.info(
        "Receipt %s saved with %d parsed items. First characters of OCR text: %s",
        receipt.id,
        len(items),
        text[:120].replace("\n", "\\n"),
    )
    return ReceiptUploadResponse(receipt_id=receipt.id, items=items)


@router.get("/receipts/{receipt_id}/items", response_model=list[ItemSchema])
async def get_receipt_items(receipt_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[ItemSchema]:
    result = await session.execute(select(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id))
    items = result.scalars().all()
    if not items:
        receipt_exists = await session.get(Receipt, receipt_id)
        if not receipt_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return list(items)


@router.put("/receipts/{receipt_id}/items", response_model=list[ItemSchema])
async def update_receipt_items(
    receipt_id: uuid.UUID, payload: ItemUpdate, session: AsyncSession = Depends(get_session)
) -> list[ItemSchema]:
    receipt = await session.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    if receipt.status != ReceiptStatus.draft:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receipt already finalized")
    item_ids_subquery = select(ReceiptItem.id).where(ReceiptItem.receipt_id == receipt_id)
    await session.execute(delete(ItemUnit).where(ItemUnit.item_id.in_(item_ids_subquery)))
    await session.execute(delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id))
    updated_items: list[ReceiptItem] = []
    for item in payload.items:
        db_item = ReceiptItem(
            receipt_id=receipt_id,
            name=item.name,
            qty_total=item.qty_total,
            unit_price=item.unit_price,
            amount_total=item.amount_total,
        )
        session.add(db_item)
        updated_items.append(db_item)
    await session.commit()
    return updated_items


@router.post("/receipts/{receipt_id}/finalize", response_model=FinalizeResponse)
async def finalize_receipt(
    receipt_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
) -> FinalizeResponse:
    receipt = await session.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    if receipt.status != ReceiptStatus.draft:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receipt already finalized")

    token = secrets.token_urlsafe(16)
    receipt.token = token
    receipt.status = ReceiptStatus.open

    result = await session.execute(select(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id))
    items = result.scalars().all()
    for item in items:
        for idx in range(item.qty_total):
            unit = ItemUnit(
                item_id=item.id,
                unit_index=idx,
                amount_total=item.unit_price,
                amount_paid=Decimal("0.00"),
            )
            session.add(unit)

    await session.commit()
    room_url = str(request.url_for("room_page", token=token))
    return FinalizeResponse(room_url=room_url)


@router.get("/receipts/{token}", response_model=ReceiptRoomResponse)
async def get_room(token: str, session: AsyncSession = Depends(get_session)) -> ReceiptRoomResponse:
    receipt_result = await session.execute(select(Receipt).where(Receipt.token == token))
    receipt = receipt_result.scalar_one_or_none()
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    items_result = await session.execute(select(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id))
    items = items_result.scalars().all()
    for item in items:
        await session.refresh(item, attribute_names=["units"])
    payments_result = await session.execute(
        select(Payment).where(Payment.receipt_id == receipt.id).order_by(Payment.created_at.desc())
    )
    payments = payments_result.scalars().all()
    return ReceiptRoomResponse(
        token=token, status=receipt.status, items=items, payments=payments, created_at=receipt.created_at
    )


@router.post("/receipts/{token}/pay")
async def pay_receipt(
    token: str, payload: PaymentRequest, session: AsyncSession = Depends(get_session)
):
    try:
        await process_payment_lines(
            session,
            token=token,
            payer_name=payload.payer_name,
            lines=[line.dict() for line in payload.lines],
        )
        await session.commit()
        await manager.broadcast(token, {"type": "payment", "payer": payload.payer_name})
    except PaymentError as exc:
        await session.rollback()
        status_code = status.HTTP_409_CONFLICT if "exceed" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc))
    return {"status": "ok"}
