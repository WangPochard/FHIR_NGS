"""
NGS PDF Report Parser

從基因檢測機構的 PDF 報告中抽取結構化資料。
回傳原始解析結果，不做 FHIR 轉換。

支援兩種抽取策略：
  - 表格模式：報告有標準表格（大多數機構）
  - 文字模式：無表格，從純文字中以 regex 抓欄位
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from app.logger import get_logger

logger = get_logger("converter.pdf")


# ─── Data models ─────────────────────────────────────────────────────────────

@dataclass
class VariantRow:
    """One variant extracted from the report."""
    gene: str = ""
    hgvs_c: str = ""
    hgvs_p: str = ""
    zygosity: str = ""          # 雜合/純合
    classification: str = ""    # Pathogenic / VUS / Benign …
    exon: str = ""
    raw: dict[str, str] = field(default_factory=dict)  # 原始欄位，備用


@dataclass
class ParsedReport:
    """Full extracted content of one NGS PDF report."""
    patient_name: str = ""
    patient_id: str = ""
    report_date: str = ""
    panel_name: str = ""
    specimen_type: str = ""
    conclusion: str = ""
    variants: list[VariantRow] = field(default_factory=list)
    raw_text: str = ""          # 全文備用，給後續 LLM 或人工 review


# ─── Parser class ─────────────────────────────────────────────────────────────

class PdfNgsParser:
    """
    Parse an NGS lab PDF report and return a ParsedReport.

    Usage:
        parser = PdfNgsParser()
        result = parser.parse("report.pdf")
    """

    # 常見的欄位 header 關鍵字（不同機構用詞不同，統一 lower 比對）
    VARIANT_HEADERS = {
        "gene":           ["gene", "基因"],
        "hgvs_c":         ["hgvs_c", "c.", "coding", "cdna", "核苷酸變異"],
        "hgvs_p":         ["hgvs_p", "p.", "protein", "amino", "蛋白質變異"],
        "zygosity":       ["zygosity", "genotype", "基因型", "雜合", "pure"],
        "classification": ["classification", "significance", "pathogenicity",
                           "臨床意義", "致病性", "判讀"],
        "exon":           ["exon", "外顯子"],
    }

    def parse(self, pdf_path: str | Path) -> ParsedReport:
        pdf_path = Path(pdf_path)
        logger.info("pdf.parse start | file=%s", pdf_path.name)
        report = ParsedReport()

        with pdfplumber.open(pdf_path) as pdf:
            full_text_parts: list[str] = []
            logger.debug("pdf.parse | pages=%d", len(pdf.pages))

            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                full_text_parts.append(page_text)

                tables = page.extract_tables()
                for table in tables:
                    rows = self._parse_table(table)
                    report.variants.extend(rows)
                    logger.debug("pdf.parse | page=%d table_rows=%d", i + 1, len(rows))

            report.raw_text = "\n".join(full_text_parts)

        self._extract_metadata(report)

        if not report.variants:
            logger.debug("pdf.parse | no table variants, fallback to regex")
            report.variants = self._extract_variants_from_text(report.raw_text)

        logger.info("pdf.parse done | patient=%s variants=%d", report.patient_id, len(report.variants))
        return report

    # ── Table parsing ─────────────────────────────────────────────────────────

    def _parse_table(self, table: list[list[str | None]]) -> list[VariantRow]:
        """Map table rows to VariantRow using header keyword matching."""
        if not table or len(table) < 2:
            return []

        # 找 header row（第一行或前幾行中含關鍵字最多的那行）
        header_row_idx, col_map = self._detect_header(table)
        if not col_map:
            return []

        rows: list[VariantRow] = []
        for raw_row in table[header_row_idx + 1:]:
            if not raw_row or all(c is None or str(c).strip() == "" for c in raw_row):
                continue
            row = self._map_row(raw_row, col_map)
            if row.gene or row.hgvs_c:   # 至少要有基因或 HGVS 才算有效
                rows.append(row)
        return rows

    def _detect_header(self, table: list[list]) -> tuple[int, dict[str, int]]:
        best_idx, best_score, best_map = 0, 0, {}
        for i, row in enumerate(table[:5]):   # 只看前 5 行
            col_map: dict[str, int] = {}
            score = 0
            for j, cell in enumerate(row):
                if cell is None:
                    continue
                cell_lower = str(cell).lower().strip()
                for field_name, keywords in self.VARIANT_HEADERS.items():
                    if any(kw in cell_lower for kw in keywords):
                        col_map[field_name] = j
                        score += 1
                        break
            if score > best_score:
                best_idx, best_score, best_map = i, score, col_map
        return best_idx, best_map

    def _map_row(self, raw_row: list, col_map: dict[str, int]) -> VariantRow:
        def get(field: str) -> str:
            idx = col_map.get(field)
            if idx is None or idx >= len(raw_row):
                return ""
            return str(raw_row[idx] or "").strip()

        raw = {k: get(k) for k in col_map}
        return VariantRow(
            gene=get("gene"),
            hgvs_c=get("hgvs_c"),
            hgvs_p=get("hgvs_p"),
            zygosity=get("zygosity"),
            classification=get("classification"),
            exon=get("exon"),
            raw=raw,
        )

    # ── Metadata extraction ───────────────────────────────────────────────────

    def _extract_metadata(self, report: ParsedReport) -> None:
        text = report.raw_text

        patterns: dict[str, list[str]] = {
            "patient_name":  [r"(?:姓名|病人|Patient\s*Name)[：:]\s*(\S+)"],
            "patient_id":    [r"(?:病歷號|ID|MRN)[：:]\s*(\S+)"],
            "report_date":   [r"(?:報告日期|Report\s*Date)[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})"],
            "panel_name":    [r"(?:檢測套組|Panel|Test\s*Name)[：:]\s*(.+)"],
            "specimen_type": [r"(?:檢體|Specimen)[：:]\s*(.+)"],
        }

        for field_name, pats in patterns.items():
            for pat in pats:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    setattr(report, field_name, m.group(1).strip())
                    break

        # 結論段落（取最後出現的「結論 / Conclusion」後面的文字）
        m = re.search(
            r"(?:結論|Conclusion|Summary)[：:\s]+(.+?)(?:\n\n|\Z)",
            text, re.IGNORECASE | re.DOTALL
        )
        if m:
            report.conclusion = m.group(1).strip()[:500]  # 最多 500 字

    # ── Fallback: regex variant extraction ───────────────────────────────────

    def _extract_variants_from_text(self, text: str) -> list[VariantRow]:
        """
        Fallback: 當 PDF 沒有表格時，用 regex 從純文字抓 HGVS notation。
        抓取格式：c.XXXXX 或 p.XXXXX
        """
        rows: list[VariantRow] = []
        # 找 c. notation
        for m in re.finditer(
            r"([\w\-]+)\s+(?:gene\s+)?(c\.\S+)(?:\s*[,;]\s*(p\.\S+))?",
            text, re.IGNORECASE
        ):
            rows.append(VariantRow(
                gene=m.group(1),
                hgvs_c=m.group(2),
                hgvs_p=m.group(3) or "",
            ))
        return rows
