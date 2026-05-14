import re
import json
import hashlib
from pathlib import Path
from typing import Any

import pdfplumber
from langchain_community.llms import Ollama

from app.config import get_settings
from app.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

# 快取根目錄：data/cache/pdf_pages/
_CACHE_ROOT = Path(__file__).parents[2] / "data" / "cache" / "pdf_pages"

# 前頁尾段帶入下一頁的字元數（跨頁上下文銜接）
_OVERLAP_CHARS = 300

# ── Prompts ───────────────────────────────────────────────────────────────────

# 第 0 頁：抓 metadata + variants
_PROMPT_FIRST_PAGE = """你是一位 NGS（次世代定序）報告解析專家。
請從以下報告文字中，擷取患者基本資料與所有變異資訊，並以 JSON 格式回應。

注意：
- 若某欄位報告中未提及，填入 null
- zygosity 請統一輸出英文：heterozygous / homozygous / hemizygous
- classification 請統一輸出英文：pathogenic / likely_pathogenic / uncertain_significance / likely_benign / benign
- consequence 請輸出 SO 術語（如 missense_variant / frameshift_variant / stop_gained 等），若不確定填 null
- hgvs_c / hgvs_p 請盡量保留報告原文格式

報告文字：
{page_text}

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

# 後續頁：只抓 variants（不重複問 metadata）
_PROMPT_OTHER_PAGE = """你是一位 NGS（次世代定序）報告解析專家。
請從以下報告文字中，擷取所有基因變異資訊，並以 JSON 格式回應。
若此頁沒有變異資料，回傳 {{"variants": []}}。

注意：
- 若某欄位未提及，填入 null
- zygosity：heterozygous / homozygous / hemizygous
- classification：pathogenic / likely_pathogenic / uncertain_significance / likely_benign / benign
- consequence：SO 術語（missense_variant / frameshift_variant / stop_gained …），不確定填 null
- hgvs_c / hgvs_p 保留原文格式

報告文字：
{page_text}

請輸出 JSON（僅輸出 JSON）：
{{
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pdf_hash(pdf_path: Path) -> str:
    """SHA-256 前 12 碼，作為快取 key。"""
    h = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return h[:12]


def _parse_json(raw: str) -> dict | None:
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def _empty_result() -> dict[str, Any]:
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


def _merge_pages(pages: list[dict]) -> dict[str, Any]:
    """
    合併所有頁面結果：
    - metadata 取第一個非 null 值
    - variants 全部累加
    """
    result = _empty_result()
    meta_fields = ["patient_name", "patient_id", "report_date",
                   "panel_name", "specimen_type", "ref_genome", "conclusion"]

    for page in pages:
        for f in meta_fields:
            if result[f] is None and page.get(f):
                result[f] = page[f]
        result["variants"].extend(page.get("variants") or [])

    return result


# ── Service ───────────────────────────────────────────────────────────────────

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
    # 逐頁解析 PDF（含快取，可斷點續跑）
    # ------------------------------------------------------------------
    def parse_ngs_report(self, path: str | Path) -> dict[str, Any]:
        """
        逐頁解析 NGS PDF 報告，回傳合併後的結構化資料。

        快取策略：
          data/cache/pdf_pages/{hash}_p{n:04d}.txt   — pdfplumber 頁面原文
          data/cache/pdf_pages/{hash}_p{n:04d}.json  — LLM 解析結果
        重跑時已完成的頁面直接讀快取，從斷點繼續。

        TXT 檔案：整份送 LLM（無分頁問題）。
        """
        path = Path(path)

        if path.suffix.lower() != ".pdf":
            return self._parse_txt(path)

        _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        pdf_key = _pdf_hash(path)
        logger.info(f"PDF 解析開始: {path.name} | key={pdf_key}")

        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            logger.info(f"總頁數: {total}")
            page_results: list[dict] = []
            prev_tail = ""  # 前一頁尾段，用於跨頁銜接

            for i, page in enumerate(pdf.pages):
                txt_cache = _CACHE_ROOT / f"{pdf_key}_p{i:04d}.txt"
                json_cache = _CACHE_ROOT / f"{pdf_key}_p{i:04d}.json"

                # ── Step 1: 取頁面文字（優先讀快取）────────────────
                if txt_cache.exists():
                    page_text = txt_cache.read_text(encoding="utf-8")
                    logger.debug(f"[p{i}] txt cache hit")
                else:
                    page_text = page.extract_text() or ""
                    txt_cache.write_text(page_text, encoding="utf-8")
                    logger.debug(f"[p{i}] txt extracted ({len(page_text)} chars)")

                # ── Step 2: LLM 解析（優先讀快取）──────────────────
                if json_cache.exists():
                    page_data = json.loads(json_cache.read_text(encoding="utf-8"))
                    logger.info(f"[p{i}/{total-1}] json cache hit | variants={len(page_data.get('variants', []))}")
                else:
                    # 拼入前頁尾段，讓跨頁變異描述保持連貫
                    llm_input = (prev_tail + "\n" + page_text).strip() if prev_tail else page_text
                    page_data = self._llm_parse_page(llm_input, is_first=(i == 0))
                    json_cache.write_text(
                        json.dumps(page_data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    logger.info(f"[p{i}/{total-1}] LLM done | variants={len(page_data.get('variants', []))}")

                prev_tail = page_text[-_OVERLAP_CHARS:]  # 取原始頁面尾段（不含前頁 overlap）
                page_results.append(page_data)

        result = _merge_pages(page_results)
        logger.info(f"PDF 解析完成: {path.name} | 總變異={len(result['variants'])}")
        return result

    # ------------------------------------------------------------------
    # 單頁 LLM 解析
    # ------------------------------------------------------------------
    def _llm_parse_page(self, page_text: str, is_first: bool) -> dict[str, Any]:
        if not page_text.strip():
            return {"variants": []}

        template = _PROMPT_FIRST_PAGE if is_first else _PROMPT_OTHER_PAGE
        prompt = template.format(page_text=page_text)

        try:
            response = self.llm.invoke(prompt)
            data = _parse_json(response)
            if data:
                return data
            logger.warning("LLM 回應無法解析為 JSON")
        except Exception as e:
            logger.warning(f"LLM 呼叫失敗: {e}")

        return {"variants": []}

    # ------------------------------------------------------------------
    # TXT 檔案（整份送，保持原行為）
    # ------------------------------------------------------------------
    def _parse_txt(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8", errors="replace")
        logger.info(f"TXT 讀取: {path.name} ({len(text)} 字)")

        prompt = _PROMPT_FIRST_PAGE.format(page_text=text[:8000])
        try:
            response = self.llm.invoke(prompt)
            data = _parse_json(response)
            if data:
                logger.info(f"TXT 解析完成: {path.name} | variants={len(data.get('variants', []))}")
                return data
        except Exception as e:
            logger.warning(f"TXT 解析失敗: {e}")

        logger.warning("TXT 解析 fallback：回傳空結構")
        return _empty_result()


llm_service = LLMService()
