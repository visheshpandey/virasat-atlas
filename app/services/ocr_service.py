"""OCR digitisation through Tesseract (pytesseract).

The result is returned for review; saving it as a field entry goes through
POST /entries with kind="ocr", so the entry is tagged and indexed like any other.
"""
import io
import os
import re

import pytesseract
from PIL import Image
from pytesseract import TesseractError, TesseractNotFoundError

from app.core.config import settings

# "hin+eng", "guj", "hin_vert+eng": 3-letter codes joined by "+". Keeps arguments out of the CLI.
LANG_PATTERN = re.compile(r"^[a-z]{3}(_[a-z]+)?(\+[a-z]{3}(_[a-z]+)?)*$")
MAX_LANG_LENGTH = 40
OCR_TIMEOUT_SECONDS = 60


class OcrUnavailable(RuntimeError):
    """Tesseract or the requested language data is not installed."""


def _configure() -> None:
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    if settings.TESSDATA_PREFIX:
        os.environ["TESSDATA_PREFIX"] = settings.TESSDATA_PREFIX


def valid_lang(lang: str) -> bool:
    return len(lang) <= MAX_LANG_LENGTH and bool(LANG_PATTERN.match(lang))


def tesseract_available() -> bool:
    """True when the tesseract binary can be executed."""
    _configure()
    try:
        pytesseract.get_tesseract_version()
        return True
    except (TesseractNotFoundError, OSError):
        return False


def run_ocr(data: bytes, lang: str) -> str:
    """Extract text from image bytes. Blocking: call it from a worker thread.

    Raises OcrUnavailable when tesseract or the language data is missing, and
    ValueError when the bytes are not an image.
    """
    _configure()
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:
        raise ValueError("File is not a valid image")
    try:
        return pytesseract.image_to_string(
            image.convert("RGB"), lang=lang, timeout=OCR_TIMEOUT_SECONDS
        ).strip()
    except TesseractNotFoundError as exc:
        raise OcrUnavailable("Tesseract is not installed") from exc
    except TesseractError as exc:
        raise OcrUnavailable(
            f"Tesseract could not load language data for '{lang}'. "
            "Install the matching traineddata files (for example hin, guj, eng)."
        ) from exc
