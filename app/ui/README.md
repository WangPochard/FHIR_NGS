# ui — 上傳審閱流程

Web UI，讓使用者上傳報告、逐筆審閱變異、下載 FHIR Bundle。

---

## 頁面流程

```
GET  /ui/                          上傳頁（選檔 + 填 patient_id / specimen）
  │
  POST /ui/upload
  │  ├─ .vcf → vcf_to_fhir 解析
  │  └─ .pdf/.txt → llm/service 解析
  │  ↓ 建立 ConversionJob + VariantDraft（存 DB）
  │
  GET  /ui/jobs/{id}/variants/{n}  逐筆審閱（補 DNA change type、臨床意義）
  │  POST 儲存後跳下一筆
  │
  GET  /ui/jobs/{id}/result        預覽 FHIR Bundle JSON
  GET  /ui/jobs/{id}/result/download  下載 JSON 檔
```

---

## 資料模型

| 模型 | 說明 |
|------|------|
| `ConversionJob` | 一次上傳 = 一個 Job，記錄 patient/specimen 資訊 |
| `VariantDraft` | 每個變異一筆，status: `pending` → `done` |

---

## FHIR Bundle 組裝

`_build_bundle()` 在 `router.py`，呼叫 `build_single_variant_resources()` 為每筆 `VariantDraft` 產生：
- `MolecularSequence`（座標、REF/ALT）
- `Observation`（基因名、HGVS、VAF、臨床意義）

最後用 `VcfToFhirConverter._assemble_bundle()` 包成 `transaction` Bundle。
