"""POST /convert/vcf"""
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.converter.vcf_to_fhir import VcfToFhirConverter
from app.logger import get_logger

router = APIRouter()
logger = get_logger("routers.converter")


@router.post("/vcf", summary="VCF → FHIR transaction Bundle")
async def convert_vcf(
    file: UploadFile = File(..., description="VCF 檔案"),
    patient_id: str = Form(..., description="Patient resource ID"),
    specimen_id: str = Form(..., description="Specimen resource ID"),
):
    logger.info("vcf.convert start | filename=%s patient=%s specimen=%s",
                file.filename, patient_id, specimen_id)

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".vcf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        converter = VcfToFhirConverter(patient_id=patient_id, specimen_id=specimen_id)
        bundle = converter.convert(tmp_path)
    except Exception as e:
        logger.error("vcf.convert failed | filename=%s error=%s", file.filename, e, exc_info=True)
        raise HTTPException(status_code=422, detail=f"VCF 轉換失敗: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    entry_count = len(bundle.get("entry", []))
    logger.info("vcf.convert done | filename=%s patient=%s entries=%d",
                file.filename, patient_id, entry_count)
    return JSONResponse(bundle)
