# Admin Audit Log

Record actor, internal role, action key, target tenant, object type/id, reason, safe metadata, and timestamp for every successful control-plane mutation. Rows are append-only through application APIs; no update/delete endpoint exists. Permission denials should be captured without leaking submitted secrets. Retention and export policy must be set before production launch.
