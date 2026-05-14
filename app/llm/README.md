# llm — PDF 長文件逐頁解析

用 Ollama 本地 LLM 將 NGS PDF 報告（或 TXT）解析為結構化 JSON。
核心設計：**逐頁處理 + 兩層快取**，中途出錯可從斷點繼續，不用重來。

---

## 快取策略

```
data/cache/pdf_pages/
  {sha256[:12]}_p0000.txt    ← pdfplumber 抽出的頁面原文
  {sha256[:12]}_p0000.json   ← LLM 解析結果
  {sha256[:12]}_p0001.txt
  {sha256[:12]}_p0001.json
  ...
```

- **cache key**：PDF 檔案 SHA-256 前 12 碼（同一份 PDF 永遠命中同一組快取）
- `.txt`：pdfplumber 抽文字，速度快，但仍快取以防 PDF 檔遺失
- `.json`：LLM 呼叫結果，最貴，也最容易中途掛掉

重跑時，已存在的 `.json` 直接讀取，跳過 LLM 呼叫；已存在的 `.txt` 跳過 pdfplumber。

---

## 頁面解析流程

```
PDF 每一頁
  │
  ├─ 取頁面文字（txt 快取 or pdfplumber）
  │
  └─ LLM 解析（json 快取 or Ollama）
       ├─ 第 0 頁：問 metadata（姓名/日期/panel）+ variants
       └─ 後續頁：只問 variants（減少幻覺，prompt 更短）

全部頁面完成後 → _merge_pages()
  ├─ metadata：第一個非 null 值優先
  └─ variants：全部累加
```

---

## 回傳格式

```json
{
  "patient_name": "王小明",
  "patient_id": "A123456",
  "report_date": "2024-03-15",
  "panel_name": "腫瘤基因套組 56 基因",
  "specimen_type": "血液",
  "ref_genome": "GRCh38",
  "conclusion": "偵測到 BRCA2 致病性變異",
  "variants": [
    {
      "gene": "BRCA2",
      "hgvs_c": "c.5946delT",
      "hgvs_p": "p.Ser1982ArgfsTer22",
      "chrom": "13",
      "pos": 32340300,
      "ref": "AT",
      "alt": "A",
      "zygosity": "heterozygous",
      "consequence": "frameshift_variant",
      "classification": "pathogenic",
      "af": 0.48,
      "dp": 120,
      "rs_id": "rs80359550"
    }
  ]
}
```

---

## TXT 檔案

整份送 LLM（無分頁問題），截斷上限 8000 字。無快取（TXT 通常較小）。

---

## 設定

`app/config.py` 相關欄位：

| 變數 | 說明 | 預設 |
|------|------|------|
| `LLM_IP` | Ollama 主機 | `localhost` |
| `LLM_PORT` | Ollama port | `11434` |
| `LLM_MODEL` | 模型名稱 | `llama3.1:8b` |

模型需支援 JSON output；建議 context window ≥ 8K。
