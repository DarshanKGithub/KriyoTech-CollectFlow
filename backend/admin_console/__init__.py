"""Admin console app package.

Keep this module free of Django model and view imports. Django imports app
packages while the app registry is still being populated; ORM-backed exports
here can raise AppRegistryNotReady before startup completes.
"""

__version__ = "1.0.0"
