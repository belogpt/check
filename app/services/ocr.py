from __future__ import annotations

import re
import uuid
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from fastapi import UploadFile

from app.core.config import get_settings
from app.schemas import ItemBase


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


def _parse_line(line: str) -> ItemBase | None:
    clean = re.sub(r"[^\w\d.,\sx×X+-]", "", line).strip()
    if not clean:
        return None
    qty_price_total = re.search(
        r"(.+?)\s+(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)$",
        clean,
        re.IGNORECASE,
    )
    numbers = re.findall(r"(\d+(?:[.,]\d+)?)", clean)
    if qty_price_total:
        name = qty_price_total.group(1).strip()
        qty = float(qty_price_total.group(2).replace(",", "."))
        unit = float(qty_price_total.group(3).replace(",", "."))
        total = float(qty_price_total.group(4).replace(",", "."))
        if qty <= 0:
            return None
        return ItemBase(name=name, qty_total=int(round(qty)), unit_price=round(unit, 2), amount_total=round(total, 2))
    if len(numbers) >= 2:
        total = float(numbers[-1].replace(",", "."))
        unit = float(numbers[-2].replace(",", "."))
        qty = 1
        name = re.sub(r"(\d+(?:[.,]\d+)?)(?!.*\d)", "", clean).strip()
        return ItemBase(name=name, qty_total=qty, unit_price=round(unit, 2), amount_total=round(total, 2))
    return None


def parse_items(text: str) -> list[ItemBase]:
    items: list[ItemBase] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "итого" in line.lower():
            break
        parsed = _parse_line(line)
        if parsed:
            items.append(parsed)
    return items


async def save_upload(file: UploadFile, media_dir: Path) -> Path:
    media_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix or ".png"
    filename = f"{uuid.uuid4()}{suffix}"
    destination = media_dir / filename
    content = await file.read()
    destination.write_bytes(content)
    return destination


async def extract_items(file: UploadFile, media_root: Path) -> tuple[Path, str, list[ItemBase]]:
    saved_path = await save_upload(file, media_root)
    processed = preprocess_image(saved_path)
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd or pytesseract.pytesseract.tesseract_cmd
    text = pytesseract.image_to_string(processed, lang="rus+eng")
    items = parse_items(text)
    return saved_path, text, items
