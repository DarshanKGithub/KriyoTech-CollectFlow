import os
from datetime import timedelta
from pathlib import Path
from celery.schedules import crontab
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = [
    "partners",
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "corsheaders", "rest_framework", "rest_framework_simplejwt", "rest_framework_simplejwt.token_blacklist", "django_filters",
    "tenants", "accounts", "vendors", "procurement", "documents", "invoices",
    "matching", "exceptions_app", "approvals", "exports_app", "audit", "notifications", "payments", "inbound_email", "operations", "communications", "phase3", "fleet", "admin_console", "erp", "settlements",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
if os.getenv("DJANGO_TEST_SQLITE") == "1":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "test.sqlite3"}}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": os.getenv("POSTGRES_DB", "kriyopay"),
        "USER": os.getenv("POSTGRES_USER", "kriyopay"), "PASSWORD": os.getenv("POSTGRES_PASSWORD", "kriyopay-local"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"), "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60}}
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
                            {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}]
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "invoice-workflow-maintenance": {"task": "invoices.tasks.maintain_invoice_workflows", "schedule": 60.0},
    "gmail-invoice-intake-poll": {"task": "phase3.tasks.sync_gmail_mailboxes", "schedule": 300.0},
    "daily-operations-digest": {"task": "phase3.tasks.send_daily_operations_digest", "schedule": crontab(hour=8, minute=0)},
    "billing-webhook-recovery": {"task": "admin_console.tasks.maintain_billing_webhooks", "schedule": 60.0},
    "invitation-delivery-recovery": {"task": "admin_console.tasks.maintain_invitation_deliveries", "schedule": 60.0},
    "erp-stalled-job-maintenance": {"task": "erp.tasks.recover_stalled_jobs", "schedule": 60.0},
    "erp-scheduled-imports": {"task": "erp.tasks.schedule_imports", "schedule": 60.0},
    "extraction-queue-maintenance": {
        "task": "invoices.tasks.maintain_extraction_queue",
        "schedule": 60.0,
    },
    "fleet-daily-reminders": {
        "task": "fleet.tasks.send_fleet_reminders",
        "schedule": crontab(minute=0),
    },
    "fleet-eta-risk-monitor": {
        "task": "fleet.tasks.notify_fleet_eta_risks",
        "schedule": 300.0,
    },
    "fleet-exception-monitor": {"task": "fleet.tasks.maintain_fleet_exceptions", "schedule": 300.0},
    "fleet-google-route-monitor": {"task": "fleet.tasks.refresh_fleet_routes", "schedule": 300.0},
    "fleet-customer-notices": {"task": "fleet.tasks.maintain_customer_notices", "schedule": 60.0},
    "fleet-location-history-retention": {"task": "fleet.tasks.prune_fleet_location_history", "schedule": crontab(minute=35, hour=2)},
}
STATIC_URL = "static/"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "media/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": ["partners.authentication.KriyoPayJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend", "rest_framework.filters.OrderingFilter"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination", "PAGE_SIZE": 25}
SIMPLE_JWT = {
    "TOKEN_REFRESH_SERIALIZER": "partners.authentication.KriyoPayTokenRefreshSerializer",
    "TOKEN_BLACKLIST_SERIALIZER": "partners.authentication.KriyoPayTokenBlacklistSerializer",
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "14"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if origin.strip()]
CORS_ALLOW_HEADERS = (*default_headers, "x-workspace")
CORS_ALLOW_HEADERS = (*CORS_ALLOW_HEADERS, "x-branch")
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "fleet_tracking": ({"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "fleet-tracking-tests"}
        if os.getenv("DJANGO_TEST_SQLITE") == "1" else {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("FLEET_CACHE_URL", CELERY_BROKER_URL),
            "KEY_PREFIX": "kriyopay-fleet-tracking",
            "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        }),
}
EXTRACTION_STALE_SECONDS = int(os.getenv("EXTRACTION_STALE_SECONDS", "900"))
INVOICE_AUTO_MATCH_CONFIDENCE_THRESHOLD = float(os.getenv("INVOICE_AUTO_MATCH_CONFIDENCE_THRESHOLD", "0.90"))
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "0") == "1"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "20"))
PLATFORM_SUPPORT_EMAIL = "info@kriyotechlabs.com"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", PLATFORM_SUPPORT_EMAIL)
ZOHO_SMTP_HOST = os.getenv("ZOHO_SMTP_HOST", "").strip()
ZOHO_SMTP_APP_PASSWORD = os.getenv("ZOHO_SMTP_APP_PASSWORD", "").strip()
if ZOHO_SMTP_HOST and ZOHO_SMTP_APP_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = ZOHO_SMTP_HOST
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_USE_SSL = False
    EMAIL_HOST_USER = DEFAULT_FROM_EMAIL = PLATFORM_SUPPORT_EMAIL
    EMAIL_HOST_PASSWORD = ZOHO_SMTP_APP_PASSWORD
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
DOCUMENT_STORAGE = os.getenv("DOCUMENT_STORAGE", "local")
EXTRACTION_PROVIDER = os.getenv("EXTRACTION_PROVIDER", "manual")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
WEBHOOK_FERNET_KEY = os.getenv("WEBHOOK_FERNET_KEY", "")
ERP_CREDENTIALS_KEY = os.getenv("ERP_CREDENTIALS_KEY", "")
ERP_TRUSTED_ORIGINS = [origin.strip().rstrip("/") for origin in os.getenv("ERP_TRUSTED_ORIGINS", "").split(",") if origin.strip()]
GOOGLE_GMAIL_CLIENT_FILE = os.getenv("GOOGLE_GMAIL_CLIENT_FILE", "")
GOOGLE_GMAIL_REDIRECT_URI = os.getenv("GOOGLE_GMAIL_REDIRECT_URI", "http://localhost:3000/integrations/gmail/callback")
GOOGLE_SIGNIN_CLIENT_FILE = os.getenv("GOOGLE_SIGNIN_CLIENT_FILE", "")
GOOGLE_SIGNIN_REDIRECT_URI = os.getenv("GOOGLE_SIGNIN_REDIRECT_URI", "http://localhost:8000/api/v1/auth/oauth/google/callback/")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
RAZORPAY_API_BASE_URL = os.getenv("RAZORPAY_API_BASE_URL", "https://api.razorpay.com/v1")
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"vendor_portal": "60/hour", "gmail_oauth_callback": "60/hour", "google_signin_start": "60/hour", "google_signin_callback": "60/hour", "admin_login": "10/hour", "password_reset": "5/hour"}
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["admin_mfa"] = "30/hour"
