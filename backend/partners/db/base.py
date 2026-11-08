from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLDatabaseWrapper
from partners.context import current_schema, validate_schema


class DatabaseWrapper(PostgreSQLDatabaseWrapper):
    def get_connection_params(self):
        params = super().get_connection_params()
        schema = validate_schema(current_schema())
        # Reconnects and persistent connections retain the request/job's boundary.
        params["options"] = f"{params.get('options', '')} -c search_path={schema}".strip()
        return params

