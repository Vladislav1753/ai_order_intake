from datetime import datetime

import pytest
from sqlalchemy.dialects import sqlite

from app.db.types import UTCDateTime


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="naive"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1), sqlite.dialect())
