import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app.core.errors import AlreadyExistsError, InvalidDataError, StorageUnavailableError
from app.db.errors import translate_db_errors


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            IntegrityError("INSERT", {}, sqlite3.IntegrityError("UNIQUE constraint failed: x.y")),
            AlreadyExistsError,
        ),
        (
            IntegrityError("INSERT", {}, sqlite3.IntegrityError("FOREIGN KEY constraint failed")),
            InvalidDataError,
        ),
        (
            OperationalError("SELECT", {}, sqlite3.OperationalError("database is locked")),
            StorageUnavailableError,
        ),
    ],
)
def test_database_errors_become_domain_errors(error: Exception, expected: type[Exception]) -> None:
    with pytest.raises(expected) as caught, translate_db_errors():
        raise error

    assert caught.value.__cause__ is error


def test_programming_errors_are_not_hidden() -> None:
    error = ProgrammingError("SELECT", {}, sqlite3.ProgrammingError("no such column"))

    with pytest.raises(ProgrammingError), translate_db_errors():
        raise error
