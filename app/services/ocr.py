from __future__ import annotations

import re
import uuid
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from fastapi import UploadFile

from app.core.config import get_settings
from app.schemas import ParsedOcrItem


settings = get_settings()


def _deskew(image: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(image > 0))
    if coords.size == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"OpenCV failed to read image at {path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    deskewed = _deskew(thresh)
    return deskewed


SERVICE_KEYWORDS = {"итог", "наличные", "безналичные", "инн", "фн", "фп", "кассир", "дата", "qr"}


def _normalize_numeric_chars(text: str) -> str:
    return (
        text.replace("O", "0")
        .replace("o", "0")
        .replace(",", ".")
        .replace("l", "1")
        .replace("I", "1")
    )


def _strip_position_prefix(text: str) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", text)


def _extract_numbers(line: str) -> list[str]:
    cleaned = _normalize_numeric_chars(_strip_position_prefix(line))
    return re.findall(r"\d+(?:\.\d+)?", cleaned)


def _is_service_line(line: str) -> bool:
    lowered = line.lower()
    return any(keyword in lowered for keyword in SERVICE_KEYWORDS)


def _is_numeric_line(line: str) -> bool:
    numbers = _extract_numbers(line)
    decimal_count = sum(1 for n in numbers if "." in n)
    return len(numbers) >= 3 and decimal_count >= 2


def _parse_numeric_line(line: str) -> tuple[float, int, float, bool]:
    numbers = _extract_numbers(line)
    price = float(numbers[0])
    qty_raw = float(numbers[1])
    total = float(numbers[2])
    quantity = int(round(qty_raw))
    parse_error = quantity <= 0 or abs(qty_raw - quantity) > 0.01
    if abs(price * quantity - total) > 0.01:
        parse_error = True
    return price, quantity, total, parse_error


def parse_items(text: str) -> list[ParsedOcrItem]:
    items: list[ParsedOcrItem] = []
    lines = [ln.strip() for ln in text.splitlines()]
    classified: list[tuple[str, str]] = []
    for line in lines:
        if not line:
            classified.append((line, "service"))
        elif _is_service_line(line):
            classified.append((line, "service"))
        elif _is_numeric_line(line):
            classified.append((line, "numeric"))
        else:
            classified.append((line, "text"))

    for idx, (line, kind) in enumerate(classified):
        if kind != "numeric":
            continue
        name_parts: list[str] = []
        prev_idx = idx - 1
        while prev_idx >= 0 and classified[prev_idx][1] == "text":
            name_parts.insert(0, classified[prev_idx][0])
            prev_idx -= 1
        name = " ".join(name_parts).strip()
        name = _strip_position_prefix(name) or "Без названия"
        price, quantity, total, parse_error = _parse_numeric_line(line)
        items.append(
            ParsedOcrItem(
                name=name,
                price=round(price, 2),
                quantity=quantity,
                total=round(total, 2),
                is_promo=False,
                parse_error=parse_error,
            )
        )
    return items


async def save_upload(file: UploadFile, media_dir: Path) -> Path:
    media_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix or ".png"
    filename = f"{uuid.uuid4()}{suffix}"
    destination = media_dir / filename
    content = await file.read()
    destination.write_bytes(content)
    return destination


async def extract_items(file: UploadFile, media_root: Path) -> tuple[Path, str, list[ParsedOcrItem]]:
    saved_path = await save_upload(file, media_root)
    processed = preprocess_image(saved_path)
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd or pytesseract.pytesseract.tesseract_cmd
    text = pytesseract.image_to_string(processed, lang="rus+eng")
    items = parse_items(text)
    return saved_path, text, items
