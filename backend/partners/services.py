"""Compatibility helpers for KriyoPay customer links and existing message callers."""
from urllib.parse import urlencode
from django.conf import settings


def frontend_link(path, params=None):
    return settings.FRONTEND_BASE_URL + path + ("?" + urlencode(params) if params else "")


def branding():
    return {"slug":"", "name":"KriyoTech Labs", "product_name":"KriyoPay", "primary_color":"#16734A", "support_email":"", "is_platform":True}
