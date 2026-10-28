import io
import json
from types import SimpleNamespace

import pytest
from django.test import override_settings

from vendors.services import GeminiExtractionProvider, ManualExtractionProvider, get_extraction_provider


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.body).encode()


class FakeDocumentFile:
    def open(self, _mode):
        return io.BytesIO(b"%PDF sample invoice")


@pytest.mark.django_db
@override_settings(EXTRACTION_PROVIDER="gemini", GEMINI_API_KEY="unit-test-key", GEMINI_MODEL="gemini-test-model")
def test_gemini_extraction_sends_document_and_returns_review_draft(monkeypatch):
    provider_text = json.dumps({
        "fields": {"supplier_name": "Northwind", "invoice_number": "NW-42", "invoice_total": "118.00", "made_up_field": "ignored"},
        "lines": [{"description": "Consulting", "taxable_value": "100.00", "untrusted": "ignored"}],
        "confidence": {"supplier_name": 0.91, "invoice_total": 0.8, "missing_field": 0.99},
        "warnings": ["Please confirm the supplier details"],
    })
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": provider_text}]}}]})

    monkeypatch.setattr("vendors.services.urllib.request.urlopen", fake_urlopen)
    document = SimpleNamespace(media_type="application/pdf", file=FakeDocumentFile())
    output = GeminiExtractionProvider().extract(document)

    assert captured["url"].endswith("/models/gemini-test-model:generateContent")
    assert captured["headers"]["X-goog-api-key"] == "unit-test-key"
    assert captured["payload"]["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "application/pdf"
    assert output["fields"] == {"supplier_name": "Northwind", "invoice_number": "NW-42", "invoice_total": "118.00"}
    assert output["confidence"] == {"supplier_name": 0.91, "invoice_total": 0.8}
    assert output["lines"] == [{"description": "Consulting", "taxable_value": "100.00"}]
    assert output["warnings"] == ["Please confirm the supplier details"]
    assert get_extraction_provider().__class__ is GeminiExtractionProvider


@pytest.mark.django_db
@override_settings(EXTRACTION_PROVIDER="gemini", GEMINI_API_KEY="", GEMINI_MODEL="gemini-test-model")
def test_gemini_missing_key_fails_with_manual_entry_guidance():
    document = SimpleNamespace(media_type="application/pdf", file=FakeDocumentFile())
    with pytest.raises(RuntimeError, match="enter invoice fields manually"):
        GeminiExtractionProvider().extract(document)


@pytest.mark.django_db
@override_settings(EXTRACTION_PROVIDER="manual")
def test_manual_extraction_provider_stays_available_as_fallback():
    assert isinstance(get_extraction_provider(), ManualExtractionProvider)
    assert get_extraction_provider().extract(None)["warnings"] == ["Manual review required"]
