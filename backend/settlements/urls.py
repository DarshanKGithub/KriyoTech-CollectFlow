from django.urls import path
from . import views

urlpatterns = [
    path("accounts", views.Accounts.as_view()),
    path("accounts/<uuid:account_id>", views.AccountState.as_view()),
    path("imports", views.Imports.as_view()),
    path("imports/<uuid:batch_id>", views.ImportDetail.as_view()),
    path("imports/<uuid:batch_id>/source", views.ImportSource.as_view()),
    path("records", views.Records.as_view()), path("template", views.Template.as_view()),
    path("provenance", views.Provenance.as_view()),
]
platform_patterns = [
    path("accounts", views.PlatformAccounts.as_view()),
    path("accounts/<uuid:account_id>", views.PlatformAccountState.as_view()),
    path("imports", views.PlatformImports.as_view()),
    path("imports/<uuid:batch_id>", views.PlatformImportDetail.as_view()),
    path("imports/<uuid:batch_id>/source", views.PlatformImportSource.as_view()),
    path("records", views.PlatformRecords.as_view()), path("template", views.PlatformTemplate.as_view()),
]
