"""Domain errors: what can go wrong, in the app's own terms.

Lower layers raise these instead of library exceptions (database errors are translated in
`app/db/errors.py`); routers map them to HTTP responses (`app/api/errors.py`). Anything that
is not a `DomainError` is a bug and is left to propagate.
"""


class DomainError(Exception):
    """Base for errors the app expects and reports instead of crashing."""


class NotFoundError(DomainError):
    """The requested record does not exist."""


class AlreadyExistsError(DomainError):
    """A uniqueness rule was broken, e.g. a second draft for one `order_ref`."""


class InvalidDataError(DomainError):
    """A record broke a database rule, e.g. a SKU that is not in the catalog."""


class StorageUnavailableError(DomainError):
    """The database could not be used (locked, missing, disk error). Retrying may work."""
