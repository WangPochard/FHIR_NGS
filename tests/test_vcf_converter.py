"""Unit tests for VcfToFhirConverter."""
import textwrap
from pathlib import Path

import pytest

from app.converter.vcf_to_fhir import VcfToFhirConverter


# ── Fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_VCF = textwrap.dedent("""\
    ##fileformat=VCFv4.2
    ##reference=GRCh38
    ##INFO=<ID=AF,Number=A,Type=Float,Description="AF">
    ##INFO=<ID=DP,Number=1,Type=Integer,Description="DP">
    ##INFO=<ID=CSQ,Number=.,Type=String,Description="VEP">
    ##FORMAT=<ID=GT,Number=1,Type=String,Description="GT">
    #CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE
    13\t32340300\trs80359550\tA\tAT\t980\tPASS\tDP=120;AF=0.52;CSQ=AT|frameshift_variant|HIGH|BRCA2|ENSG00000139618|ENST00000380152|protein_coding|c.5266dup|p.Gln1756ProfsTer25|rs80359550\tGT\t0/1
""")

TWO_VARIANT_VCF = textwrap.dedent("""\
    ##fileformat=VCFv4.2
    ##reference=GRCh37
    #CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE
    17\t43082434\trs28897672\tG\tA\t850\tPASS\tDP=98;AF=0.48\tGT\t0/1
    12\t25245350\trs121913529\tC\tA\t920\tPASS\tDP=135;AF=1.00\tGT\t1/1
""")


@pytest.fixture
def vcf_file(tmp_path: Path):
    def _make(content: str) -> Path:
        p = tmp_path / "test.vcf"
        p.write_text(content)
        return p
    return _make


@pytest.fixture
def converter():
    return VcfToFhirConverter(patient_id="p-001", specimen_id="sp-001")


# ── Bundle structure ───────────────────────────────────────────────────────────

class TestBundleStructure:
    def test_bundle_type(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "transaction"

    def test_entry_count_one_variant(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        # 1 variant → MolecularSequence + Observation = 2 entries
        assert len(bundle["entry"]) == 2

    def test_entry_count_two_variants(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(TWO_VARIANT_VCF))
        assert len(bundle["entry"]) == 4

    def test_entry_has_required_keys(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        for entry in bundle["entry"]:
            assert "fullUrl" in entry
            assert "resource" in entry
            assert "request" in entry
            assert entry["request"]["method"] == "PUT"

    def test_resource_types(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        types = {e["resource"]["resourceType"] for e in bundle["entry"]}
        assert types == {"MolecularSequence", "Observation"}


# ── VCF parsing ────────────────────────────────────────────────────────────────

class TestVcfParsing:
    def test_pos_is_zero_based(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        seq = next(e["resource"] for e in bundle["entry"]
                   if e["resource"]["resourceType"] == "MolecularSequence")
        # VCF POS=32340300 → FHIR 0-based = 32340299
        assert seq["referenceSeq"]["windowStart"] == 32340299

    def test_ref_genome_grch38(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        seq = next(e["resource"] for e in bundle["entry"]
                   if e["resource"]["resourceType"] == "MolecularSequence")
        # GRCh38 LOINC = LA26806-2
        codes = [c["code"] for c in seq["referenceSeq"]["referenceSeqId"]["coding"]]
        assert "LA26806-2" in codes

    def test_ref_genome_grch37(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(TWO_VARIANT_VCF))
        seq = next(e["resource"] for e in bundle["entry"]
                   if e["resource"]["resourceType"] == "MolecularSequence")
        codes = [c["code"] for c in seq["referenceSeq"]["referenceSeqId"]["coding"]]
        assert "LA14029-5" in codes

    def test_patient_reference(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        obs = next(e["resource"] for e in bundle["entry"]
                   if e["resource"]["resourceType"] == "Observation")
        assert obs["subject"]["reference"] == "Patient/p-001"

    def test_specimen_reference(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        obs = next(e["resource"] for e in bundle["entry"]
                   if e["resource"]["resourceType"] == "Observation")
        assert obs["specimen"]["reference"] == "Specimen/sp-001"


# ── Observation components ─────────────────────────────────────────────────────

class TestObservationComponents:
    def _obs(self, bundle):
        return next(e["resource"] for e in bundle["entry"]
                    if e["resource"]["resourceType"] == "Observation")

    def test_has_gene_component(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        obs = self._obs(bundle)
        loinc_codes = [
            c["code"]["coding"][0]["code"]
            for c in obs["component"]
        ]
        assert "48018-6" in loinc_codes  # gene studied

    def test_allelic_state_heterozygous(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        obs = self._obs(bundle)
        allelic = next(
            (c for c in obs["component"]
             if c["code"]["coding"][0]["code"] == "81255-2"), None
        )
        assert allelic is not None
        assert allelic["valueCodeableConcept"]["coding"][0]["code"] == "LA6706-1"

    def test_allelic_state_homozygous(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(TWO_VARIANT_VCF))
        # second variant is 1/1 homozygous
        obs_list = [e["resource"] for e in bundle["entry"]
                    if e["resource"]["resourceType"] == "Observation"]
        hom_obs = obs_list[1]
        allelic = next(
            (c for c in hom_obs["component"]
             if c["code"]["coding"][0]["code"] == "81255-2"), None
        )
        assert allelic is not None
        assert allelic["valueCodeableConcept"]["coding"][0]["code"] == "LA6705-3"

    def test_rs_id_as_identifier(self, converter, vcf_file):
        bundle = converter.convert(vcf_file(MINIMAL_VCF))
        obs = self._obs(bundle)
        assert obs["identifier"][0]["value"] == "rs80359550"


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_vcf(self, converter, vcf_file):
        empty = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        bundle = converter.convert(vcf_file(empty))
        assert bundle["entry"] == []

    def test_missing_qual(self, converter, vcf_file):
        vcf = textwrap.dedent("""\
            ##fileformat=VCFv4.2
            ##reference=GRCh38
            #CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
            1\t1000\t.\tA\tG\t.\tPASS\tDP=50
        """)
        bundle = converter.convert(vcf_file(vcf))
        assert len(bundle["entry"]) == 2
