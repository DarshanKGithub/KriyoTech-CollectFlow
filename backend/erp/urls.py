from django.urls import path
from .views import Connections, ConnectionDetail, ConnectionTest, SyncRuns, Records, RecordDetail, RecordDownload, RecordSend, RecordReconcile, RecordConflictReview
from .candidates import LocalCandidates

urlpatterns = [
    path("connections", Connections.as_view()),
    path("local-records", LocalCandidates.as_view()),
    path("connections/<uuid:connection_id>", ConnectionDetail.as_view()),
    path("connections/<uuid:connection_id>/test", ConnectionTest.as_view()),
    path("runs", SyncRuns.as_view()),
    path("records", Records.as_view()),
    path("records/<uuid:record_id>", RecordDetail.as_view()),
    path("records/<uuid:record_id>/download", RecordDownload.as_view()),
    path("records/<uuid:record_id>/send", RecordSend.as_view()),
    path("records/<uuid:record_id>/reconcile", RecordReconcile.as_view()),
    path("records/<uuid:record_id>/review-conflict", RecordConflictReview.as_view()),
]
