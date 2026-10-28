from django.conf import settings
from django.db import connection
from django.db.models import Count
from rest_framework.response import Response
from rest_framework.views import APIView
from .permissions import IsAdminStaff


class ExtractionHealth(APIView):
    permission_classes = [IsAdminStaff]

    def get(self, request):
        import redis
        from invoices.models import ExtractionResult
        database = broker = worker = False
        counts = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                database = cursor.fetchone()[0] == 1
            counts = dict(ExtractionResult.objects.values("status").annotate(total=Count("id")).values_list("status", "total"))
        except Exception:
            pass
        try:
            client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=3, socket_timeout=3)
            broker = bool(client.ping())
            worker = bool(client.exists("kriyopay:extraction-worker-heartbeat"))
        except Exception:
            pass
        return Response({"database": database, "redis": broker, "recent_worker_heartbeat": worker,
                         "extraction_counts": counts, "stale_after_seconds": settings.EXTRACTION_STALE_SECONDS,
                         "healthy": database and broker and worker})
