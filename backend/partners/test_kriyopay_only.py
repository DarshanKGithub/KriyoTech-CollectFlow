import pytest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient
from .authentication import check_binding
from .services import branding, frontend_link


def test_retired_reseller_tokens_cannot_enter_kriyopay():
    check_binding({})
    check_binding({"partner_schema":"public"})
    for token in ({"partner_schema":"partner_"+"a"*32}, {"product_instance":"retired-product"}):
        with pytest.raises(AuthenticationFailed):
            check_binding(token)


@pytest.mark.django_db
def test_reseller_endpoints_are_retired_and_hints_do_not_select_schema():
    client = APIClient()
    for path in ("/api/v1/platform/partners", "/api/v1/admin/brand", "/api/v1/brand", "/api/v1/resellers/retired-reseller/brand"):
        assert client.get(path).status_code == 404
    assert client.get("/api/v1/health", HTTP_X_PARTNER="retired-reseller").status_code == 200
    assert branding()["product_name"] == "KriyoPay"
    assert "partner=" not in frontend_link("/login")


def test_old_reseller_jobs_are_refused():
    from .tasks import KriyoPayTask
    from config.celery import app
    KriyoPayTask.bind(app)
    task = KriyoPayTask()
    task.push_request(headers={"partner_schema":"partner_"+"b"*32})
    try:
        with pytest.raises(RuntimeError, match="Retired reseller"):
            task()
    finally:
        task.pop_request()
