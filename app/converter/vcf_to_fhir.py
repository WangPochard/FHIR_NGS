"""
VCF → FHIR R4 Converter

FHIR resource mapping 參見 skill.md § 2
VCF 欄位對應參見 skill.md § 3
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from app.logger import get_logger

logger = get_logger("converter.vcf")


# ─── Data model ──────────────────────────────────────────────────────────────

@dataclass
class VcfRecord:
    """One parsed VCF variant row."""
    chrom: str
    pos_0based: int          # VCF POS - 1（0-based for FHIR coordinateSystem）
    ref: str
    alt: str
    qual: float | None
    filter_status: str
    rs_id: str
    ref_genome: str
    # From INFO/ANN or CSQ
    gene: str = ""
    hgvs_c: str = ""
    hgvs_p: str = ""
    consequence: str = ""
    # Numeric INFO fields
    af: float | None = None  # allele frequency
    dp: int | None = None    # read depth
    # FORMAT
    gt: str = ""             # genotype (0/1, 1/1 …)


# ─── LOINC / coding constants (ref: skill.md § 2.5, 2.6, 4) ─────────────────

_LOINC = "http://loinc.org"

LOINC = {
    "discrete_variant":  "81252-9",
    "vaf":               "81258-6",
    "allelic_state":     "81255-2",
    "gene_studied":      "48018-6",
    "dna_change":        "48004-6",
    "aa_change":         "48005-3",
    "clinical_sig":      "53037-8",
}

ALLELIC_STATE = {
    ("0/1", "0|1"): ("LA6706-1", "Heterozygous"),
    ("1/1", "1|1"): ("LA6705-3", "Homozygous"),
}

CLINVAR_SIG = {
    "pathogenic":       ("LA6668-3",  "Pathogenic"),
    "likely_pathogenic":("LA26332-9", "Likely pathogenic"),
    "vus":              ("LA26333-7", "Uncertain significance"),
    "likely_benign":    ("LA26334-5", "Likely benign"),
    "benign":           ("LA6675-8",  "Benign"),
}

REF_GENOME_LOINC = {
    "GRCh37": "LA14029-5",
    "GRCh38": "LA26806-2",
}


# ─── Converter class ──────────────────────────────────────────────────────────

class VcfToFhirConverter:
    """
    Parses a VCF file and converts each variant to FHIR resources.

    Usage:
        converter = VcfToFhirConverter(patient_id="p-001", specimen_id="sp-001")
        bundle = converter.convert("sample.vcf")
    """

    def __init__(self, patient_id: str, specimen_id: str):
        self.patient_ref = f"Patient/{patient_id}"
        self.specimen_ref = f"Specimen/{specimen_id}"

    # ── Public ────────────────────────────────────────────────────────────────

    def convert(self, vcf_path: str | Path) -> dict[str, Any]:
        """Parse VCF and return a FHIR transaction Bundle."""
        logger.debug("vcf.convert start | path=%s patient=%s", vcf_path, self.patient_ref)
        resources: list[dict] = []
        for record in self._parse_vcf(vcf_path):
            seq = self._build_molecular_sequence(record)
            obs = self._build_variant_observation(record, seq_id=seq["id"])
            resources.extend([seq, obs])
        variant_count = len(resources) // 2
        logger.info("vcf.convert done | variants=%d resources=%d", variant_count, len(resources))
        return self._assemble_bundle(resources)

    # ── VCF parsing ───────────────────────────────────────────────────────────

    def _parse_vcf(self, path: str | Path) -> Iterator[VcfRecord]:
        path = Path(path)
        header_lines: list[str] = []
        ref_genome = "GRCh38"

        with path.open() as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if line.startswith("##"):
                    header_lines.append(line)
                    continue
                if line.startswith("#CHROM"):
                    ref_genome = self._detect_ref_genome(header_lines)
                    continue

                cols = line.split("\t")
                if len(cols) < 8:
                    continue

                chrom, pos, rs_id, ref, alt_col, qual_str, filter_col, info_str = cols[:8]

                try:
                    qual = float(qual_str)
                except ValueError:
                    qual = None

                info = self._parse_info(info_str)
                ann = self._extract_annotation(info)
                gt = self._extract_gt(cols)

                yield VcfRecord(
                    chrom=chrom.lstrip("chr"),
                    pos_0based=int(pos) - 1,
                    ref=ref,
                    alt=alt_col.split(",")[0],   # first ALT only
                    qual=qual,
                    filter_status=filter_col,
                    rs_id=rs_id if rs_id != "." else "",
                    ref_genome=ref_genome,
                    gene=ann.get("gene", ""),
                    hgvs_c=ann.get("hgvs_c", ""),
                    hgvs_p=ann.get("hgvs_p", ""),
                    consequence=ann.get("consequence", ""),
                    af=float(info["AF"]) if "AF" in info else None,
                    dp=int(info["DP"]) if "DP" in info else None,
                    gt=gt,
                )

    @staticmethod
    def _detect_ref_genome(header_lines: list[str]) -> str:
        for line in header_lines:
            if line.startswith("##reference="):
                val = line.split("=", 1)[1].lower()
                if "38" in val or "hg38" in val:
                    return "GRCh38"
                if "37" in val or "hg19" in val:
                    return "GRCh37"
        return "GRCh38"

    @staticmethod
    def _parse_info(info_str: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for part in info_str.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = v
            else:
                result[part] = "true"
        return result

    @staticmethod
    def _extract_annotation(info: dict[str, str]) -> dict[str, str]:
        """Extract gene/HGVS from VEP CSQ or SnpEff ANN (first transcript)."""
        raw = info.get("CSQ") or info.get("ANN") or ""
        if not raw:
            return {}
        fields = raw.split(",")[0].split("|")
        result: dict[str, str] = {}
        if len(fields) > 3:
            result["consequence"] = fields[1]
            result["gene"] = fields[3]
        if len(fields) > 9:
            result["hgvs_c"] = fields[9]
        if len(fields) > 10:
            result["hgvs_p"] = fields[10]
        return result

    @staticmethod
    def _extract_gt(cols: list[str]) -> str:
        if len(cols) < 10:
            return ""
        fmt_keys = cols[8].split(":")
        fmt_vals = cols[9].split(":")
        return dict(zip(fmt_keys, fmt_vals)).get("GT", "")

    # ── FHIR builders ─────────────────────────────────────────────────────────

    def _build_molecular_sequence(self, r: VcfRecord) -> dict[str, Any]:
        ref_loinc = REF_GENOME_LOINC.get(r.ref_genome, REF_GENOME_LOINC["GRCh38"])
        resource: dict[str, Any] = {
            "resourceType": "MolecularSequence",
            "id": self._uid(),
            "type": "DNA",
            "coordinateSystem": 0,
            "patient": {"reference": self.patient_ref},
            "referenceSeq": {
                "referenceSeqId": {
                    "coding": [{"system": _LOINC, "code": ref_loinc}]
                },
                "chromosome": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0955",
                        "code": r.chrom,
                    }]
                },
                "windowStart": r.pos_0based,
                "windowEnd": r.pos_0based + len(r.ref),
            },
            "variant": [{
                "start": r.pos_0based,
                "end": r.pos_0based + len(r.ref),
                "observedAllele": r.alt,
                "referenceAllele": r.ref,
            }],
        }
        if r.qual is not None:
            resource["quality"] = [{"type": "unknown", "score": {"value": r.qual}}]
        return resource

    def _build_variant_observation(self, r: VcfRecord, seq_id: str) -> dict[str, Any]:
        components = self._build_components(r)
        obs: dict[str, Any] = {
            "resourceType": "Observation",
            "id": self._uid(),
            "status": "final",
            "category": [{"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory",
            }]}],
            "code": self._loinc(LOINC["discrete_variant"], "Discrete genetic variant"),
            "subject": {"reference": self.patient_ref},
            "specimen": {"reference": self.specimen_ref},
            "derivedFrom": [{"reference": f"MolecularSequence/{seq_id}"}],
            "component": components,
        }
        if r.rs_id:
            obs["identifier"] = [
                {"system": "http://www.ncbi.nlm.nih.gov/snp", "value": r.rs_id}
            ]
        return obs

    def _build_components(self, r: VcfRecord) -> list[dict]:
        components: list[dict] = []

        if r.gene:
            components.append({
                "code": self._loinc(LOINC["gene_studied"], "Gene studied [ID]"),
                "valueCodeableConcept": {
                    "coding": [{"system": "http://www.genenames.org", "code": r.gene}],
                    "text": r.gene,
                },
            })
        if r.hgvs_c:
            components.append({
                "code": self._loinc(LOINC["dna_change"], "DNA change (c.HGVS)"),
                "valueCodeableConcept": {"text": r.hgvs_c},
            })
        if r.hgvs_p:
            components.append({
                "code": self._loinc(LOINC["aa_change"], "Amino acid change (pHGVS)"),
                "valueCodeableConcept": {"text": r.hgvs_p},
            })
        if r.af is not None:
            components.append({
                "code": self._loinc(LOINC["vaf"], "Allelic frequency by NGS"),
                "valueQuantity": {"value": r.af, "unit": "%"},
            })

        # Allelic state
        for gt_set, (code, display) in ALLELIC_STATE.items():
            if r.gt in gt_set:
                components.append({
                    "code": self._loinc(LOINC["allelic_state"], "Allelic state"),
                    "valueCodeableConcept": {
                        "coding": [{"system": _LOINC, "code": code, "display": display}]
                    },
                })
                break

        return components

    # ── Bundle ────────────────────────────────────────────────────────────────

    @staticmethod
    def _assemble_bundle(resources: list[dict]) -> dict[str, Any]:
        def entry(r: dict) -> dict:
            rt, rid = r["resourceType"], r["id"]
            return {
                "fullUrl": f"urn:uuid:{rid}",
                "resource": r,
                "request": {"method": "PUT", "url": f"{rt}/{rid}"},
            }
        return {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [entry(r) for r in resources],
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _uid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _loinc(code: str, display: str) -> dict:
        return {"coding": [{"system": _LOINC, "code": code, "display": display}]}


# ─── Module-level helpers for UI router ──────────────────────────────────────

def parse_vcf_records(path: str | Path) -> list[VcfRecord]:
    """Parse a VCF file and return all variant records."""
    converter = VcfToFhirConverter(patient_id="tmp", specimen_id="tmp")
    return list(converter._parse_vcf(path))


def build_single_variant_resources(
    record: VcfRecord,
    patient_id: str,
    specimen_id: str,
    dna_change_type_code: str | None = None,
    dna_change_type_display: str | None = None,
    clinical_sig_key: str | None = None,
) -> list[dict]:
    """Build MolecularSequence + Observation(s) for one variant."""
    converter = VcfToFhirConverter(patient_id=patient_id, specimen_id=specimen_id)
    seq = converter._build_molecular_sequence(record)
    obs = converter._build_variant_observation(record, seq_id=seq["id"])

    if dna_change_type_code:
        obs["component"].append({
            "code": converter._loinc("48019-4", "DNA sequence variant type"),
            "valueCodeableConcept": {
                "coding": [{
                    "system": _LOINC,
                    "code": dna_change_type_code,
                    "display": dna_change_type_display or "",
                }]
            },
        })

    resources: list[dict] = [seq, obs]

    if clinical_sig_key and clinical_sig_key in CLINVAR_SIG:
        code, display = CLINVAR_SIG[clinical_sig_key]
        resources.append({
            "resourceType": "Observation",
            "id": VcfToFhirConverter._uid(),
            "status": "final",
            "code": converter._loinc(LOINC["clinical_sig"], "Genetic variation clinical significance"),
            "subject": {"reference": f"Patient/{patient_id}"},
            "derivedFrom": [{"reference": f"MolecularSequence/{seq['id']}"}],
            "valueCodeableConcept": {
                "coding": [{"system": _LOINC, "code": code, "display": display}]
            },
        })

    return resources
