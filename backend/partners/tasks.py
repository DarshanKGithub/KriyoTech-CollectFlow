"""Prevent queued work from retired reseller schemas running in KriyoPay."""
from celery import Task


class KriyoPayTask(Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        headers = self.request.headers or {}
        if headers.get("partner_schema", "public") != "public" or headers.get("product_instance"):
            raise RuntimeError("Retired reseller task refused; no company data changed")
        return self.run(*args, **kwargs)
