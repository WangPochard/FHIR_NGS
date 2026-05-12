"""Integration tests for FastAPI endpoints (no external HAPI needed)."""
import textwrap

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SAMPLE_VCF = textwrap.dedent("""\
    ##fileformat=VCFv4.2
    ##reference=GRCh38
    ##INFO=<ID=AF,Number=A,Type=Float,Description="AF">
    ##INFO=<ID=DP,Number=1,Type=Integer,Description="DP">
    ##FORMAT=<ID=GT,Number=1,Type=String,Description="GT">
    #CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE
    17\t43082434\trs28897672\tG\tA\t850\tPASS\tDP=98;AF=0.48\tGT\t0/1
""").encode()


class TestHealth:
    def test_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "version" in resp.json()


class TestConvertVcf:
    def test_success(self):
        resp = client.post(
            "/convert/vcf",
            data={"patient_id": "p-001", "specimen_id": "sp-001"},
            files={"file": ("test.vcf", SAMPLE_VCF, "text/plain")},
        )
        assert resp.status_code == 200
        bundle = resp.json()
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "transaction"
        assert len(bundle["entry"]) == 2

    def test_missing_patient_id(self):
        resp = client.post(
            "/convert/vcf",
            data={"specimen_id": "sp-001"},
            files={"file": ("test.vcf", SAMPLE_VCF, "text/plain")},
        )
        assert resp.status_code == 422

    def test_invalid_vcf(self):
        resp = client.post(
            "/convert/vcf",
            data={"patient_id": "p-001", "specimen_id": "sp-001"},
            files={"file": ("bad.vcf", b"not a vcf file at all!!!", "text/plain")},
        )
        # Should return 200 with empty bundle (no valid variant lines)
        assert resp.status_code in (200, 422)


class TestOpenApi:
    def test_openapi_schema_exists(self):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "FHIR NGS Converter"

    def test_tags_in_schema(self):
        resp = client.get("/openapi.json")
        schema = resp.json()
        tag_names = [t["name"] for t in schema.get("tags", [])]
        assert "converter" in tag_names
