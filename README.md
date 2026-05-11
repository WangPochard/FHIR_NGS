# FHIR NGS Converter

將 NGS（次世代定序）基因檢測報告轉換為 HL7 FHIR R4 transaction Bundle，供 HAPI FHIR Server 儲存與查詢。

---

## 背景：NGS 資料從哪裡來？

NGS 基因檢測**不是門診日常產生的資料**，也不存在 HIS 中。
通常由**外部專業基因檢測機構**（如台灣基因、訊聯、Illumina 認證實驗室等）執行，院內只負責送檢與接收報告。

```
院內醫師開立基因檢測申請
        ↓
病人抽血 / 切片取樣 → 送往外部基因檢測機構
        ↓
外部機構進行 NGS 定序
  Raw reads (FASTQ)
        ↓
  比對參考基因組 (BAM)
        ↓
  變異偵測 (Variant Calling)
        ↓
  輸出結果 ← 院內收到的通常是這兩種格式
  ┌──────────────┬──────────────────────────────┐
  │ PDF / 文字報告 │ 人類可讀，含基因名、HGVS、臨床意義│  ← 最常見
  │ VCF 檔案      │ 機器可讀，逐位點變異資料         │  ← 不一定會附
  └──────────────┴──────────────────────────────┘
        ↓
本專案：解析上述資料 → 轉換為 FHIR R4 資源 → 存入 HAPI FHIR Server
```

> **實務說明：** 多數外部機構給的是 PDF 或結構化文字報告，VCF 需另外申請或不一定提供。
> 因此本專案的輸入格式需視合作機構而定，VCF 是最理想的機器可讀格式，但非唯一來源。

---

## VCF 格式說明

VCF（Variant Call Format）是記錄基因變異的標準文字格式，每一行代表一個變異位點：

```
CHROM  POS       ID          REF  ALT  QUAL  FILTER  INFO
13     32340300  rs80359550  A    AT   980   PASS    DP=120;AF=0.52;CSQ=...
```

| 欄位 | 說明 |
|------|------|
| `CHROM / POS` | 染色體編號與位置 |
| `REF / ALT` | 正常鹼基 / 突變鹼基 |
| `QUAL` | 偵測品質分數（越高越可信） |
| `FILTER` | `PASS` = 通過品質過濾 |
| `INFO/AF` | 變異頻率（0.5 ≈ 雜合，1.0 ≈ 純合）|
| `INFO/CSQ` | VEP 或 SnpEff 的 annotation（基因名、HGVS notation 等）|
| `FORMAT/GT` | 基因型：`0/1` 雜合、`1/1` 純合 |

---

## 目前功能

- 解析 VCF 檔案（支援 VEP CSQ / SnpEff ANN annotation 欄位）
- 自動偵測參考基因組版本（GRCh37 / GRCh38）
- 每個變異產生 `MolecularSequence` + `Observation`（含標準 LOINC code）
- 輸出 FHIR R4 transaction Bundle

## 輸出的 FHIR 資源

| 資源 | 說明 | LOINC |
|------|------|-------|
| `MolecularSequence` | 染色體座標、REF/ALT、品質分數 | — |
| `Observation` | 基因名、HGVS c./p.、VAF、雜合/純合狀態 | 81252-9 |

詳細欄位對應見 `skill.md`。

---

## 快速啟動

```bash
pip install -r requirements.txt

# 開發模式（hot reload）
python run.py --reload

# 指定 port
python run.py --port 8080
```

## API

### `POST /convert/vcf`

上傳 VCF 檔案，回傳 FHIR transaction Bundle（JSON）。

| 欄位 | 類型 | 說明 |
|------|------|------|
| `file` | file | VCF 檔案 |
| `patient_id` | string | Patient resource ID |
| `specimen_id` | string | Specimen resource ID |

```bash
curl -X POST http://localhost:8000/convert/vcf \
  -F "file=@data/input/sample.vcf" \
  -F "patient_id=p-001" \
  -F "specimen_id=sp-001"
```

---

## 專案結構

```
fhir_ngs/
├── run.py                        # 啟動入口
├── skill.md                      # FHIR NGS domain knowledge
├── app/
│   ├── main.py
│   ├── converter/
│   │   └── vcf_to_fhir.py       # VcfToFhirConverter（主邏輯）
│   └── routers/
│       └── converter.py          # POST /convert/vcf
└── data/
    ├── input/                    # 輸入 VCF（含 sample.vcf 測試檔）
    └── output/                   # 轉換後 FHIR JSON
```

## Domain Knowledge

`skill.md` 記錄所有 FHIR Genomics 相關知識：Resource 對應、LOINC code、VCF 欄位映射、外部資料庫清單，以及待確認的資料收集項目。
