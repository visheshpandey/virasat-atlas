"""OCR digitisation of scanned documents."""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.schemas.heritage import OcrOut, TagOut
from app.services import entry_service, ocr_service, tagger

router = APIRouter(tags=["ocr"])


@router.post("/ocr", response_model=OcrOut)
async def ocr(
    file: UploadFile = File(),
    lang: str = Form(default="hin+eng"),
) -> OcrOut:
    """Read the text in a scanned image and tag it.

    To keep the result, send it to POST /entries with kind="ocr".
    Returns 501 when Tesseract (or the language data) is not installed.
    """
    if not ocr_service.valid_lang(lang):
        raise HTTPException(
            status_code=422, detail="lang must look like 'eng', 'hin' or 'hin+eng'"
        )
    if not ocr_service.tesseract_available():
        raise HTTPException(
            status_code=501,
            detail="OCR is not available: Tesseract is not installed on the server. "
            "Install it (with the hin, guj and eng language packs) or set TESSERACT_CMD.",
        )
    data = await entry_service.read_upload(file)
    entry_service.verify_image(data)
    try:
        text = await run_in_threadpool(ocr_service.run_ocr, data, lang)
    except ocr_service.OcrUnavailable as exc:
        raise HTTPException(status_code=501, detail=f"OCR is not available: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    tags = TagOut(**await tagger.tag_text(text)) if text else TagOut()
    return OcrOut(text=text, language=tags.language, tags=tags)
