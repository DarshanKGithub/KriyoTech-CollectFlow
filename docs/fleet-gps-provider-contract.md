# Fleet GPS provider adapter

The generic webhook accepts normalized device events at `POST /api/v1/fleet/gps-provider/events`. It is provider-neutral; vendor certification and protocol-specific polling/webhook conversion remain separate integration work.

## Device setup

Workspace owners and fleet operators create/list mappings at `GET|POST /api/v1/fleet/gps-devices`; they can disable a mapping or move it to another same-workspace vehicle with `PATCH /api/v1/fleet/gps-devices/{id}`. Every change requires a reason. The provider/device pair is globally unique in this deployment. Configure a mapping before sending events.

Create body:

```json
{"provider":"ACME_TRACKER","device_id":"truck-901","vehicle_id":"<fleet vehicle UUID>","reason":"Register tracker for pilot vehicle"}
```

## Signed event

Set `FLEET_GPS_WEBHOOK_SECRET` to at least 32 random bytes and provision the same secret only in the provider's secure callback configuration. Requests use the exact raw JSON bytes as the signed body:

```text
X-Fleet-Timestamp: <Unix seconds>
X-Fleet-Signature: <lowercase hex HMAC-SHA256(secret, timestamp + "." + raw body)>
Content-Type: application/json
```

The timestamp may be at most five minutes from server time. Event IDs are namespaced with provider and device for idempotent replay. A device maps to its one currently active trip by vehicle assignment; missing or ambiguous assignment is rejected.

```json
{
  "provider":"ACME_TRACKER",
  "device_id":"truck-901",
  "event_id":"vendor-event-000091",
  "captured_at":"2026-11-01T12:30:00Z",
  "latitude":19.076,
  "longitude":72.8777,
  "accuracy_m":12,
  "speed_kmh":42.5,
  "heading_degrees":87
}
```

`accuracy_m`, `speed_kmh`, and `heading_degrees` are optional. Accepted timestamps are within the last 24 hours and no more than two minutes ahead. Late samples are retained without moving the latest location backward; only fresh fixes feed live stop/geofence/deviation processing. Signature failures, unknown devices, and bad events are rejected before writes.

## Retention and operations

`fleet.tasks.prune_fleet_location_history` removes expired raw GPS samples and latest-location projections in batches. Celery Beat runs it daily at 02:35 server time. `FLEET_GPS_HISTORY_RETENTION_DAYS` defaults to 90 and accepts 30–3650. The task returns a cutoff, deletion counts, and whether another batch remains. Run repeatedly until `more_pending` is false during a large initial cleanup.

Before pilot activation, configure HTTPS, rotate/provision the webhook secret, confirm provider timestamp/event-ID behavior, replay recorded vendor fixtures, and exercise backup restore plus expiry deletion in staging. The shared-secret generic contract does not replace a provider-specific authorization or certification review.
