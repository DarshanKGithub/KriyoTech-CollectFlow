"""Maintenance for GPS episodes whose reporting stream has gone stale."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import FleetGeofenceDwellEpisode, FleetRouteDeviationEpisode, FleetStopEpisode

GPS_GAP = timedelta(minutes=2)


@transaction.atomic
def expire_stale_tracking_episodes(now=None, limit=1000):
    now = now or timezone.now()
    cutoff = now - GPS_GAP
    stops = list(FleetStopEpisode.objects.select_for_update(skip_locked=True).filter(
        ended_at__isnull=True, last_sample_at__lt=cutoff).order_by("last_sample_at")[:limit])
    for episode in stops:
        episode.ended_at = episode.last_sample_at
        episode.status = FleetStopEpisode.Status.INTERRUPTED
        episode.save(update_fields=["ended_at", "status"])

    dwell = list(FleetGeofenceDwellEpisode.objects.select_for_update(skip_locked=True).filter(
        ended_at__isnull=True, last_sample_at__lt=cutoff).order_by("last_sample_at")[:limit])
    for episode in dwell:
        episode.ended_at = episode.last_sample_at
        episode.end_reason = FleetGeofenceDwellEpisode.EndReason.GPS_GAP
        episode.save(update_fields=["ended_at", "end_reason"])

    deviations = list(FleetRouteDeviationEpisode.objects.select_for_update(skip_locked=True).filter(
        status__in=[FleetRouteDeviationEpisode.Status.CANDIDATE, FleetRouteDeviationEpisode.Status.ACTIVE],
        last_sample_at__lt=cutoff).order_by("last_sample_at")[:limit])
    for episode in deviations:
        episode.ended_at = episode.last_sample_at
        episode.status = FleetRouteDeviationEpisode.Status.INTERRUPTED
        episode.end_reason = FleetRouteDeviationEpisode.EndReason.GPS_GAP
        episode.save(update_fields=["ended_at", "status", "end_reason"])
    return {"stationary_closed": len(stops), "dwell_closed": len(dwell), "route_deviations_closed": len(deviations)}
