from django.contrib import admin
from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_GET
from urllib.parse import urlencode
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView
from accounts.auth import UnifiedLoginSerializer
from settlements.urls import platform_patterns
from accounts.password_reset import PasswordResetConfirm, PasswordResetRequest


class UnifiedLoginView(TokenObtainPairView):
    serializer_class = UnifiedLoginSerializer


def service_identity(request):
    return JsonResponse({"service": "kriyopay", "api_version": "v1", "status": "ok"})

@require_GET
def legacy_invitation_page(request):
    """Forward previously emailed backend links to the frontend acceptance page."""
    query = urlencode({"token": request.GET.get("token", "")})
    response = HttpResponseRedirect(f"{settings.FRONTEND_BASE_URL}/invite/accept?{query}")
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


urlpatterns = [
    path("invite/accept", legacy_invitation_page, name="legacy_invitation_page"),
    path("invite/accept/", legacy_invitation_page),
    path("api/v1/health", service_identity, name="service_identity"),
    path("admin/", admin.site.urls),
    path("api/v1/auth/login", UnifiedLoginView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/password-reset/request", PasswordResetRequest.as_view(), name="password_reset_request"),
    path("api/v1/auth/password-reset/confirm", PasswordResetConfirm.as_view(), name="password_reset_confirm"),
    path("api/v1/auth/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/logout", TokenBlacklistView.as_view(), name="token_blacklist"),
    path("api/v1/admin/", include("admin_console.urls")),
    path("api/v1/admin/settlements/", include(platform_patterns)),
    path("api/v1/settlements/", include("settlements.urls")),
    path("api/v1/erp/", include("erp.urls")),
    path("api/v1/", include("invoices.urls")),
    path("api/v1/fleet/", include("fleet.urls")),
]
