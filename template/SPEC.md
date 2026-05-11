# 健保署 NGS FHIR 申報規格

來源：Taiwan NGS IG v1.0.1
官方網址：https://build.fhir.org/ig/TWNHIFHIR/ngs/
基礎版本：FHIR R4.0.1 / TW Core IG v0.3.2

---

## 必要 FHIR 資源（一份申報需全部包含）

```
Bundle (transaction)
├── Patient              病人基本資料
├── Specimen             檢體資訊
├── ServiceRequest       申請單（醫師開立）
├── Device               定序設備
├── Observation (1..N)   基因變異結果     ← 主要資料
└── DiagnosticReport     整份基因報告     ← 彙整上述所有
```

---

## DiagnosticReport Profile（TWNGS）

| 欄位 | 必填 | 值 / 規定 |
|------|------|----------|
| `status` | 1..1 | `final` |
| `code.coding.system` | 1..1 | `http://loinc.org` |
| `code.coding.code` | 1..1 | `51969-4`（Genetic analysis report）|
| `basedOn` | 1..* | ServiceRequest reference |
| `effectiveDateTime` | Must-Support | 報告日期 |
| `performer` | 1..1 | Organization reference（檢驗機構）|
| `result` | 1..* | Observation references |
| `extension:condition` | Must-Support | 疾病資訊 extension |

Extension URL：
`https://nhicore.nhi.gov.tw/ngs/StructureDefinition/extension-DiagnosticReport-condition`

---

## Observation Profile（TWNGS）

| 欄位 | 必填 | 值 / 規定 |
|------|------|----------|
| `identifier` | 1..1 | VPN 格式：癌別 + 年份 + 5 碼流水號 |
| `status` | 1..1 | `final` |
| `code.coding.code` | 1..1 | `69548-6`（Genetic variant assessment）|
| `subject` | 1..1 | Patient reference |
| `effectiveDateTime` | 1..1 | 報告日期 |
| `performer` | 1..1 | Organization reference |
| `specimen` | 1..1 | Specimen reference |
| `device` | 1..1 | Device reference（定序設備）|
| `method` | 1..1 | `LA26398-0`（Sequencing）|
| `component` | 3..* | 見下表 |

### Observation.component 必要欄位

| component | LOINC code | 說明 |
|-----------|-----------|------|
| `gene-test-code` | 81247-9 | 基因套組代碼（健保 NGS ValueSet）|
| `gene-list` | 48018-6 | 基因名稱（HGNC nomenclature，格式：`HGNC:BRCA2`）|
| `representative-coding-hgvs` | 48004-6 | HGVS c. notation |

---

## Specimen Profile（TWNGS）

| 欄位 | 必填 | 值 / 規定 |
|------|------|----------|
| `identifier` | 1..1 | 病理編號 |
| `accessionIdentifier` | Must-Support | 檢體條碼 |
| `type` | 1..1 | CodeableConcept（LOINC-健保NGS ValueSet）|
| `subject` | 1..1 | Patient reference |
| `collection.collector` | Must-Support | 採集醫師 |
| `collection.collectedDateTime` | Must-Support | 採集日期 |
| `container.identifier` | Must-Support | 容器編號 |

---

## 與現行程式碼的落差（Gap Analysis）

| 項目 | 現行產出 | 規格要求 | 狀態 |
|------|---------|---------|------|
| Observation code | `81252-9` | `69548-6` | 需修正 |
| Observation identifier | 無 | VPN 格式 1..1 | 缺少 |
| Observation method | 無 | `LA26398-0` (Sequencing) | 缺少 |
| Observation device | 無 | Device reference 1..1 | 缺少 |
| DiagnosticReport | 無 | 必要資源 | 未實作 |
| ServiceRequest | 無 | DiagnosticReport.basedOn 1..* | 未實作 |
| Device resource | 無 | 必要資源 | 未實作 |
| gene-list component | gene name 字串 | `HGNC:GENE_NAME` 格式 | 需修正 |
| Specimen resource | 僅 reference | 完整 Specimen resource | 未實作 |
| extension:condition | 無 | Must-Support | 未實作 |

---

## 健保 NGS 申報流程（參考）

```
醫院 → POST Bundle → 健保署 FHIR Server
         ↑
    本專案產出
```

VPN identifier 格式範例：
- 乳癌(BC) + 2026年 + 流水號00001 → `BC202600001`

---

## 參考連結

- Taiwan NGS IG v1.0.1：https://build.fhir.org/ig/TWNHIFHIR/ngs/
- TW Core IG：https://build.fhir.org/ig/cctwFHIRterm/MOHW_TWCoreIG_Build/
- HGNC 基因命名：https://www.genenames.org/
- HL7 Genomics Reporting IG：http://hl7.org/fhir/uv/genomics-reporting/
