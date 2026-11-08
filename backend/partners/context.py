"""Explicit schema boundary; public is deliberately absent from reseller search paths."""
import re
from contextlib import contextmanager
from contextvars import ContextVar
from django.db import connection

_schema = ContextVar("partner_schema", default="public")
_partner = ContextVar("partner_brand", default=None)


def current_schema():
    return _schema.get()

def current_partner():
    return _partner.get()


def validate_schema(schema):
    if schema != "public" and not re.fullmatch(r"partner_[0-9a-f]{32}", schema or ""):
        raise ValueError("Invalid reseller schema identifier")
    return schema


def set_search_path(schema):
    validate_schema(schema)
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('search_path', %s, false)", [schema])
    elif schema != "public":
        raise RuntimeError("Reseller isolation requires PostgreSQL")


@contextmanager
def schema_context(schema, partner=None):
    validate_schema(schema)
    previous = current_schema()
    if connection.in_atomic_block and schema != previous:
        raise RuntimeError("Cannot switch reseller inside a database transaction")
    token = _schema.set(schema)
    brand_token = _partner.set(partner)
    from django.contrib.contenttypes.models import ContentType
    try:
        set_search_path(schema)
        ContentType.objects.clear_cache()
        yield
    finally:
        _schema.reset(token)
        _partner.reset(brand_token)
        # A failed transaction/connection must never be returned with another schema.
        try:
            set_search_path(previous)
        except Exception:
            connection.close()
        ContentType.objects.clear_cache()


def cache_key(key, key_prefix, version):
    return f"{key_prefix}:{current_schema()}:{version}:{key}"


class SchemaContentTypeCache(dict):
    """Django keys its process-wide content type cache by database alias only."""
    def __getitem__(self, key):
        return super().__getitem__((current_schema(), key))

    def setdefault(self, key, default=None):
        return super().setdefault((current_schema(), key), default)


class ControlPlaneRouter:
    def allow_migrate(self, db, app_label, **hints):
        if app_label == "partners":
            return current_schema() == "public"
        return None

