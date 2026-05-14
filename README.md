# FHIR NGS Converter — 系統架構

將 NGS（次世代定序）基因檢測報告轉換為 HL7 FHIR R4 transaction Bundle，供 HAPI FHIR Server 儲存與查詢。

---

## 為什麼需要這個系統？

NGS 報告由**外部基因檢測機構**出具，格式不統一（PDF 或 VCF），院內 HIS 無法直接收納。
本系統作為中介層，將這些報告標準化成 FHIR 資源，讓院內系統可以查詢與整合。

```
外部基因檢測機構
  ├─ PDF 報告（人類可讀）
  └─ VCF 檔案（機器可讀）
          │
          ▼
  ┌─────────────────────┐
  │   FHIR NGS Converter │
  │                     │
  │  PDF → LLM 解析      │
  │  VCF → 直接解析      │
  │      ↓              │
  │  人工審閱 UI         │
  │      ↓              │
  │  FHIR Bundle 組裝   │
  └─────────────────────┘
          │
          ▼
  HAPI FHIR Server
```

---

## 模組架構

```
app/
├── converter/      VCF / PDF 解析 → 結構化資料
├── llm/            PDF 長文件逐頁 LLM 解析（含快取）
├── ui/             上傳 → 審閱 → 產出 FHIR Bundle 的 Web 流程
└── valueset/       FHIR ValueSet 資料（基因體相關 code system）
```

各模組詳細說明見各目錄的 `README.md`。

---

## 資料流

```
上傳檔案
  │
  ├─ .vcf ──────────────────────────────────────────────────┐
  │   vcf_to_fhir.py 解析每行變異                           │
  │   ↓                                                      │
  │   ConversionJob + VariantDraft 存入 DB                   │
  │                                                          │
  └─ .pdf / .txt ────────────────────────────────────────┐  │
      llm/service.py 逐頁解析（pdfplumber + LLM）        │  │
      ↓                                                   │  │
      ConversionJob + VariantDraft 存入 DB ───────────────┘  │
                                                             │
                                                             ▼
                                                 UI 逐筆審閱 / 補值
                                                             │
                                                             ▼
                                               FHIR transaction Bundle
                                          (MolecularSequence + Observation)
                                                             │
                                                             ▼
                                                   HAPI FHIR Server
```

---

## 輸出的 FHIR 資源

| 資源 | 說明 | LOINC |
|------|------|-------|
| `MolecularSequence` | 染色體座標、REF/ALT、品質分數 | — |
| `Observation` | 基因名、HGVS c./p.、VAF、雜合/純合、臨床意義 | 81252-9 |

LOINC code 對應與 VCF 欄位映射詳見 `skill.md`。

---

## 快速啟動

```bash
pip install -r requirements.txt

# 開發模式
python run.py --reload

# 指定 port
python run.py --port 8080
```

環境變數（`.env`）：

| 變數 | 說明 | 預設 |
|------|------|------|
| `HAPI_FHIR_URL` | HAPI FHIR Server 位址 | `http://localhost:8080/fhir` |
| `LLM_IP` / `LLM_PORT` | Ollama 位址 | `localhost:11434` |
| `LLM_MODEL` | 使用的模型 | `llama3.1:8b` |
| `DB_HOST/NAME/USER/PWD` | PostgreSQL 連線 | — |

---

## 部署（Docker）

```bash
docker compose up -d
```

`docker-compose.yml` 包含：FHIR NGS Converter + HAPI FHIR Server + PostgreSQL。

---

## 專案規則

- VCF `POS` 轉 FHIR 需 `-1`（VCF 1-based → FHIR 0-based coordinateSystem）
- LOINC code 不得自行捏造，一律查 `template/valuesets/` 下的 ValueSet JSON（健保署官方下載）
- Bundle 類型固定為 `transaction`
- 參考基因組版本（GRCh37/38）必須在 `MolecularSequence` 明確標示
