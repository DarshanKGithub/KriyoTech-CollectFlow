import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry
from django.test import override_settings
from django.utils import timezone
from documents.models import Document
from invoices.models import Invoice, ExtractionResult
from invoices.extraction import recover_stalled_extractions
from invoices.tasks import extract_invoice
from tenants.models import Tenant
from vendors.services import TransientExtractionError


@pytest.fixture
def job(db, monkeypatch):
    # These task recovery tests exercise extraction retries/claims, not plan setup.
    monkeypatch.setattr("admin_console.services.has_feature", lambda tenant, feature: True)
    tenant = Tenant.objects.create(name="Extraction reliability", workspace_key="reliability")
    document = Document.objects.create(tenant=tenant, file="sample.pdf", filename="sample.pdf", media_type="application/pdf", checksum_sha256="a" * 64, size_bytes=100)
    invoice = Invoice.objects.create(tenant=tenant, document=document, status="EXTRACTING")
    extraction = ExtractionResult.objects.create(tenant=tenant, invoice=invoice, status="QUEUED")
    return invoice, extraction


def provider(monkeypatch, effect):
    mocked = Mock(side_effect=effect) if callable(effect) or isinstance(effect, Exception) else Mock(return_value=effect)
    monkeypatch.setattr("invoices.tasks.get_extraction_provider", lambda: SimpleNamespace(extract=mocked))
    return mocked


def test_transient_failure_stays_queued_for_automatic_retry(job, monkeypatch):
    invoice, extraction = job
    provider(monkeypatch, TransientExtractionError("Temporary network error"))
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(extract_invoice, "retry", retry)
    with pytest.raises(Retry): extract_invoice(str(invoice.id), str(extraction.id))
    invoice.refresh_from_db(); extraction.refresh_from_db()
    assert invoice.status == "EXTRACTING"
    assert extraction.status == "QUEUED"
    assert extraction.attempts == 1
    assert retry.call_args.kwargs["countdown"] == 30


def test_retry_budget_ends_in_actionable_failure(job, monkeypatch):
    invoice, extraction = job
    extraction.attempts = 3; extraction.save()
    provider(monkeypatch, TransientExtractionError("Temporary network error"))
    with pytest.raises(TransientExtractionError): extract_invoice(str(invoice.id), str(extraction.id))
    invoice.refresh_from_db(); extraction.refresh_from_db()
    assert invoice.status == "EXTRACTION_FAILED"
    assert extraction.status == "FAILED" and extraction.attempts == 4


def test_duplicate_delivery_does_not_call_provider_twice(job, monkeypatch):
    invoice, extraction = job
    mock = provider(monkeypatch, {"fields": {"invoice_number": "DEMO-1"}})
    extract_invoice(str(invoice.id), str(extraction.id))
    result = extract_invoice(str(invoice.id), str(extraction.id))
    assert result["duplicate_delivery"] is True
    assert mock.call_count == 1


def test_processing_job_is_not_claimed_twice(job, monkeypatch):
    invoice, extraction = job
    extraction.status = "PROCESSING"; extraction.claim_token = uuid.uuid4(); extraction.save()
    mock = provider(monkeypatch, {})
    extract_invoice(str(invoice.id), str(extraction.id))
    mock.assert_not_called()


@override_settings(EXTRACTION_STALE_SECONDS=900)
def test_stalled_job_released_and_late_worker_cannot_overwrite(job, monkeypatch):
    invoice, extraction = job
    def late_response(document):
        ExtractionResult.objects.filter(id=extraction.id).update(updated_at=timezone.now()-timedelta(minutes=20))
        assert recover_stalled_extractions() == 1
        return {"fields": {"invoice_number": "STALE"}}
    provider(monkeypatch, late_response)
    result = extract_invoice(str(invoice.id), str(extraction.id))
    invoice.refresh_from_db(); extraction.refresh_from_db()
    assert result["status"] == "STALE_RESULT_IGNORED"
    assert invoice.invoice_number == "" and invoice.status == "EXTRACTION_FAILED"
    assert extraction.output["error_code"] == "WORKER_STALLED"


def test_old_queued_job_does_not_override_new_extraction(job, monkeypatch):
    invoice, extraction = job
    ExtractionResult.objects.create(tenant=invoice.tenant, invoice=invoice, status="QUEUED")
    mock = provider(monkeypatch, {})
    assert extract_invoice(str(invoice.id), str(extraction.id))["status"] == "IGNORED"
    mock.assert_not_called()


def test_permanent_error_does_not_retry_or_expose_provider_details(job, monkeypatch):
    invoice, extraction = job
    provider(monkeypatch, RuntimeError("private-provider-response"))
    with pytest.raises(RuntimeError): extract_invoice(str(invoice.id), str(extraction.id))
    extraction.refresh_from_db()
    assert extraction.status == "FAILED"
    assert "private-provider-response" not in str(extraction.output)
