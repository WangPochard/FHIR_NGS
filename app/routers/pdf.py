"""POST /pdf/parse"""
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.converter.pdf_parser import PdfNgsParser
from app.logger import get_logger

router = APIRouter()
_parser = PdfNgsParser()
logger = get_logger("routers.pdf")


class VariantRowSchema(BaseModel):
    gene: str = Field("", description="基因名稱，例如 BRCA1")
    hgvs_c: str = Field("", description="cDNA 變異，例如 c.5266dupC")
    hgvs_p: str = Field("", description="蛋白質變異，例如 p.Gln1756fs")
    zygosity: str = Field("", description="雜合（Heterozygous）/ 純合（Homozygous）")
    classification: str = Field("", description="臨床意義，例如 Pathogenic / VUS / Benign")
    exon: str = Field("", description="外顯子位置，例如 exon 11")
    raw: dict = Field(default_factory=dict, description="原始欄位（備用）")


class ParsedReportSchema(BaseModel):
    patient_name: str = Field("", description="病人姓名")
    patient_id: str = Field("", description="病歷號")
    report_date: str = Field("", description="報告日期（YYYY-MM-DD）")
    panel_name: str = Field("", description="檢測套組名稱")
    specimen_type: str = Field("", description="檢體類型")
    conclusion: str = Field("", description="報告結論摘要（最多 500 字）")
    variants: list[VariantRowSchema] = Field(default_factory=list, description="抽取到的變異清單")
    raw_text: str = Field("", description="PDF 全文（備用，供 LLM 或人工 review）")


class ErrorResponse(BaseModel):
    detail: str = Field(description="錯誤訊息")


@router.post(
    "/parse",
    summary="NGS PDF 報告 → 結構化資料",
    description=(
        "上傳 NGS 機構出具的 PDF 報告，解析並回傳結構化資料。\n\n"
        "**解析策略（依序）：**\n"
        "1. **表格模式**：偵測 PDF 內的表格，依欄位 header 關鍵字映射至標準欄位\n"
        "2. **文字模式（備援）**：當 PDF 無表格時，用 regex 從純文字抓 HGVS notation\n\n"
        "回傳原始解析結果，**不含 FHIR 轉換**。"
    ),
    response_model=ParsedReportSchema,
    response_description="結構化 NGS 報告資料",
    responses={
        200: {"description": "解析成功"},
        422: {"model": ErrorResponse, "description": "PDF 解析失敗"},
    },
    status_code=status.HTTP_200_OK,
)
async def parse_pdf(file: UploadFile = File(..., description="NGS 報告 PDF 檔案")):
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
