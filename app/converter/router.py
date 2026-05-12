import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.converter.pdf_parser import PdfNgsParser
from app.converter.vcf_to_fhir import VcfToFhirConverter
from app.logger import get_logger

router = APIRouter()
logger = get_logger("converter")

# region VCF


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
            "entry": [{
                "fullUrl": "urn:uuid:abc123",
                "resource": {"resourceType": "MolecularSequence", "id": "abc123"},
                "request": {"method": "PUT", "url": "MolecularSequence/abc123"},
            }],
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
    responses={
        200: {"description": "轉換成功，回傳 FHIR Bundle"},
        422: {"model": ErrorResponse, "description": "VCF 解析失敗"},
    },
    status_code=status.HTTP_200_OK,
)
async def convert_vcf(
    file: UploadFile = File(..., description="VCF 檔案（`.vcf`）"),
    patient_id: str = Form(..., description="Patient resource ID", examples=["p-001"]),
    specimen_id: str = Form(..., description="Specimen resource ID", examples=["sp-001"]),
):
    logger.info("vcf.convert start | filename=%s patient=%s", file.filename, patient_id)
    with tempfile.NamedTemporaryFile(suffix=".vcf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        bundle = VcfToFhirConverter(patient_id=patient_id, specimen_id=specimen_id).convert(tmp_path)
    except Exception as e:
        logger.error("vcf.convert failed | %s", e, exc_info=True)
        raise HTTPException(status_code=422, detail=f"VCF 轉換失敗: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info("vcf.convert done | entries=%d", len(bundle.get("entry", [])))
    return JSONResponse(bundle)

# endregion

# region PDF


class VariantRowSchema(BaseModel):
    gene: str = Field("", description="基因名稱")
    hgvs_c: str = Field("", description="cDNA 變異")
    hgvs_p: str = Field("", description="蛋白質變異")
    zygosity: str = Field("", description="雜合 / 純合")
    classification: str = Field("", description="臨床意義")
    exon: str = Field("", description="外顯子位置")
    raw: dict = Field(default_factory=dict, description="原始欄位")


class ParsedReportSchema(BaseModel):
    patient_name: str = Field("")
    patient_id: str = Field("")
    report_date: str = Field("")
    panel_name: str = Field("")
    specimen_type: str = Field("")
    conclusion: str = Field("")
    variants: list[VariantRowSchema] = Field(default_factory=list)
    raw_text: str = Field("")


_parser = PdfNgsParser()


@router.post(
    "/pdf",
    summary="NGS PDF 報告 → 結構化資料",
    description=(
        "上傳 NGS 機構出具的 PDF 報告，解析並回傳結構化資料。\n\n"
        "回傳原始解析結果，**不含 FHIR 轉換**。"
    ),
    response_model=ParsedReportSchema,
    status_code=status.HTTP_200_OK,
)
async def parse_pdf(file: UploadFile = File(..., description="NGS 報告 PDF 檔案")):
    logger.info("pdf.parse start | filename=%s", file.filename)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        result = _parser.parse(tmp_path)
    except Exception as e:
        logger.error("pdf.parse failed | %s", e, exc_info=True)
        raise HTTPException(status_code=422, detail=f"PDF 解析失敗: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)
    logger.info("pdf.parse done | patient=%s variants=%d", result.patient_id, len(result.variants))
    return JSONResponse(asdict(result))

# endregion
