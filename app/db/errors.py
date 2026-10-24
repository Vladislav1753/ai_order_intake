import functools
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.exc import DataError, IntegrityError, InterfaceError, OperationalError

from app.core.errors import (
    AlreadyExistsError,
    InvalidDataError,
    StorageUnavailableError,
)


@contextmanager
def translate_db_errors() -> Iterator[None]:
    """Re-raise database errors as domain errors. Wrap every query and commit with it.

    Programming errors (bad SQL, lazy loading in async code) are not translated: they are
    bugs, not conditions to report.
    """
    try:
        yield
    except IntegrityError as exc:
        if "UNIQUE" in str(exc.orig):
            raise AlreadyExistsError(f"Already saved: {exc.orig}") from exc
        raise InvalidDataError(f"Rejected by the database: {exc.orig}") from exc
    except DataError as exc:
        raise InvalidDataError(f"Rejected by the database: {exc.orig}") from exc
    except (OperationalError, InterfaceError) as exc:
        raise StorageUnavailableError(f"Database unavailable: {exc.orig}") from exc


def translates_db_errors[**P, R](
    method: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """Decorator form of `translate_db_errors` for async repository methods."""

    @functools.wraps(method)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with translate_db_errors():
            return await method(*args, **kwargs)

    return wrapper
