"""POST /convert/vcf"""
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.converter.vcf_to_fhir import VcfToFhirConverter
from app.logger import get_logger

router = APIRouter()
logger = get_logger("routers.converter")


class BundleResponse(BaseModel):
    """FHIR R4 transaction Bundle（簡化 schema 供 Swagger 展示）"""
    resourceType: str = Field("Bundle", examples=["Bundle"])
    type: str = Field("transaction", examples=["transaction"])
    entry: list[dict[str, Any]] = Field(
        description="每個元素包含 fullUrl、resource（MolecularSequence 或 Observation）、request"
    )

    model_config = {"json_schema_extra": {
        "example": {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {
                    "fullUrl": "urn:uuid:abc123",
                    "resource": {"resourceType": "MolecularSequence", "id": "abc123"},
                    "request": {"method": "PUT", "url": "MolecularSequence/abc123"},
                }
            ],
        }
    }}


class ErrorResponse(BaseModel):
    detail: str = Field(description="錯誤訊息")


@router.post(
    "/vcf",
    summary="VCF → FHIR transaction Bundle",
    description=(
        "上傳一個 VCF 檔案，回傳 FHIR R4 `transaction` Bundle。\n\n"
        "**每個變異位點產生：**\n"
        "- `MolecularSequence`：染色體座標、REF/ALT allele、品質分數\n"
        "- `Observation`（LOINC `81252-9`）：基因名稱、HGVS c./p.、VAF、雜合/純合狀態\n\n"
        "自動偵測 VCF header 中的參考基因組版本（GRCh37 / GRCh38）。\n"
        "支援 VEP `CSQ` 及 SnpEff `ANN` annotation 欄位。"
    ),
    response_description="FHIR R4 transaction Bundle（JSON）",
    responses={
        200: {"description": "轉換成功，回傳 FHIR Bundle"},
        422: {"model": ErrorResponse, "description": "VCF 解析失敗"},
    },
    status_code=status.HTTP_200_OK,
)
async def convert_vcf(
    file: UploadFile = File(..., description="VCF 檔案（`.vcf`）"),
    patient_id: str = Form(..., description="Patient resource ID，例如 `p-001`", examples=["p-001"]),
    specimen_id: str = Form(..., description="Specimen resource ID，例如 `sp-001`", examples=["sp-001"]),
):
    logger.info("vcf.convert start | filename=%s patient=%s specimen=%s",
                file.filename, patient_id, specimen_id)

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".vcf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        conv = VcfToFhirConverter(patient_id=patient_id, specimen_id=specimen_id)
        bundle = conv.convert(tmp_path)
    except Exception as e:
        logger.error("vcf.convert failed | filename=%s error=%s", file.filename, e, exc_info=True)
        raise HTTPException(status_code=422, detail=f"VCF 轉換失敗: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    entry_count = len(bundle.get("entry", []))
    logger.info("vcf.convert done | filename=%s patient=%s entries=%d",
                file.filename, patient_id, entry_count)
    return JSONResponse(bundle)
