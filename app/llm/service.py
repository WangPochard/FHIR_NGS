import re
import json
from pathlib import Path
from typing import Any

import pdfplumber
from langchain_community.llms import Ollama

from app.config import get_settings
from app.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

_PARSE_PROMPT = """你是一位 NGS（次世代定序）報告解析專家。
請從以下報告文字中，擷取所有變異資訊與基本資料，並以 JSON 格式回應。

注意：
- 若某欄位報告中未提及，填入 null
- zygosity 請統一輸出英文：heterozygous / homozygous / hemizygous
- classification 請統一輸出英文：pathogenic / likely_pathogenic / uncertain_significance / likely_benign / benign
- consequence 請輸出 SO 術語（如 missense_variant / frameshift_variant / stop_gained 等），若不確定填 null
- hgvs_c / hgvs_p 請盡量保留報告原文格式

報告文字：
{report_text}

請輸出 JSON（僅輸出 JSON，不要加任何說明文字）：
{{
  "patient_name": null,
  "patient_id": null,
  "report_date": null,
  "panel_name": null,
  "specimen_type": null,
  "ref_genome": "GRCh38",
  "conclusion": null,
  "variants": [
    {{
      "gene": null,
      "hgvs_c": null,
      "hgvs_p": null,
      "chrom": null,
      "pos": null,
      "ref": null,
      "alt": null,
      "zygosity": null,
      "consequence": null,
      "classification": null,
      "af": null,
      "dp": null,
      "rs_id": null
    }}
  ]
}}"""


class LLMService:
    def __init__(self, model: str = None, base_url: str = None, temperature: float = 0.1):
        self.model_name = model or settings.llm_model
        self.base_url = base_url or settings.llm_base_url
        self.llm = Ollama(
            model=self.model_name,
            base_url=self.base_url,
            temperature=temperature,
        )
        logger.info(f"LLM 服務初始化: {self.model_name} @ {self.base_url}")

    # ------------------------------------------------------------------
    # 文字萃取
    # ------------------------------------------------------------------
    def _extract_text(self, path: str | Path) -> str:
        path = Path(path)
        if path.suffix.lower() == ".pdf":
            with pdfplumber.open(path) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            text = "\n\n".join(pages)
            logger.info(f"PDF 萃取: {path.name} ({len(pdf.pages)} 頁, {len(text)} 字)")
            return text
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            logger.info(f"TXT 讀取: {path.name} ({len(text)} 字)")
            return text

    # ------------------------------------------------------------------
    # NGS 報告解析（PDF / TXT → 結構化 dict）
    # ------------------------------------------------------------------
    def parse_ngs_report(self, path: str | Path) -> dict[str, Any]:
        """解析 NGS 報告，回傳結構化資料。

        回傳格式：
        {
            "patient_name": str | None,
            "patient_id": str | None,
            "report_date": str | None,
            "panel_name": str | None,
            "specimen_type": str | None,
            "ref_genome": str,
            "conclusion": str | None,
            "variants": [
                {
                    "gene": str | None,
                    "hgvs_c": str | None,
                    "hgvs_p": str | None,
                    "chrom": str | None,
                    "pos": int | None,
                    "ref": str | None,
                    "alt": str | None,
                    "zygosity": str | None,
                    "consequence": str | None,
                    "classification": str | None,
                    "af": float | None,
                    "dp": int | None,
                    "rs_id": str | None
                }
            ]
        }
        """
        report_text = self._extract_text(path)
        prompt = _PARSE_PROMPT.format(report_text=report_text[:6000])

        try:
            response = self.llm.invoke(prompt)
            logger.debug(f"LLM raw response (first 300): {response[:300]}")
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                variant_count = len(data.get("variants", []))
                logger.info(f"NGS 報告解析完成: {Path(path).name}, {variant_count} 個變異")
                return data
        except Exception as e:
            logger.warning(f"NGS 報告解析失敗: {e}")

        logger.warning("NGS 解析 fallback：回傳空結構")
        return {
            "patient_name": None,
            "patient_id": None,
            "report_date": None,
            "panel_name": None,
            "specimen_type": None,
            "ref_genome": "GRCh38",
            "conclusion": None,
            "variants": [],
        }


llm_service = LLMService()
