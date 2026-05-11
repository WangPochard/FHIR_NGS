"""POST /pdf/parse"""
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.converter.pdf_parser import PdfNgsParser
from app.logger import get_logger

router = APIRouter()
_parser = PdfNgsParser()
logger = get_logger("routers.pdf")


@router.post("/parse", summary="NGS PDF 報告 → 結構化資料")
async def parse_pdf(file: UploadFile = File(..., description="NGS 報告 PDF")):
    logger.info("pdf.parse start | filename=%s size=%s", file.filename, file.size)

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = _parser.parse(tmp_path)
    except Exception as e:
        logger.error("pdf.parse failed | filename=%s error=%s", file.filename, e, exc_info=True)
        raise HTTPException(status_code=422, detail=f"PDF 解析失敗: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    logger.info(
        "pdf.parse done | filename=%s patient=%s variants=%d",
        file.filename, result.patient_id, len(result.variants),
    )
    return JSONResponse(asdict(result))
