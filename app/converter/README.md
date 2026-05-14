# converter — VCF / PDF 解析

將輸入檔案解析為結構化變異資料，不直接產出 FHIR（FHIR 組裝在 `ui/router.py` 的 `_build_bundle()`）。

---

## 支援格式

| 格式 | 解析器 | 備註 |
|------|--------|------|
| `.vcf` | `vcf_to_fhir.py` | 支援 VEP CSQ / SnpEff ANN annotation |
| `.pdf` | `pdf_parser.py` + `llm/service.py` | 規則解析優先，失敗才用 LLM |
| `.txt` | `llm/service.py` | 整份送 LLM |

---

## VCF 解析

`vcf_to_fhir.py` 的 `parse_vcf_records()` 逐行讀 VCF，輸出 `VcfRecord` list。

關鍵轉換：
- `POS` 欄位：VCF 1-based → 存入 DB 前轉 0-based，FHIR Bundle 組裝時再 `-1`
- `INFO/AF`：直接取為 VAF
- `FORMAT/GT`：`0/1` → heterozygous，`1/1` → homozygous
- 參考基因組：從 VCF header `##reference` 或 `##assembly` 自動偵測

---

## PDF 解析

`pdf_parser.py` 的 `PdfNgsParser` 先跑表格模式（`pdfplumber.extract_tables()`），抓不到再 fallback 用 regex 找 HGVS notation。

長文件（多頁 PDF）由 `llm/service.py` 處理，見 `app/llm/README.md`。
