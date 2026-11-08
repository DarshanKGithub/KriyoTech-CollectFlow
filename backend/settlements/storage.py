"""Financial source evidence is served through authorized APIs, never a media URL."""
import os
from pathlib import Path
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class FinancialSourceStorage(FileSystemStorage):
    @property
    def base_location(self):
        media = Path(settings.MEDIA_ROOT)
        from partners.context import current_schema
        root = Path(getattr(settings, "FINANCIAL_SOURCE_ROOT", media.parent / ("private_" + media.name)))
        return str(root if current_schema() == "public" else root / "resellers" / current_schema())

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Financial evidence requires an authorized source-download API.")
