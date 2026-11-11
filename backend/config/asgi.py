import os
from django.core.asgi import get_asgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from config.mobile_realtime import with_mobile_realtime

application = with_mobile_realtime(get_asgi_application())
