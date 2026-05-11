"""Unit tests for Settings / config."""
from app.config import Settings


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.port == 8000
        assert s.host == "0.0.0.0"
        assert s.log_level == "INFO"
        assert s.hapi_fhir_url == "http://localhost:8080/fhir"

    def test_override_via_env(self, monkeypatch):
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("HAPI_FHIR_URL", "http://hapi.example.com/fhir")
        s = Settings()
        assert s.port == 9000
        assert s.hapi_fhir_url == "http://hapi.example.com/fhir"
