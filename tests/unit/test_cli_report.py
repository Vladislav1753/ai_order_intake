"""The `process` summary line: new drafts are counted by their status after the whole run."""

import pytest

from app.cli import print_report
from app.core.enums import DraftStatus, RequestStatus
from app.services.intake import IntakeResult


def test_a_draft_changed_later_in_the_run_is_counted_by_its_final_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_report(
        [
            IntakeResult("R5", "O5", RequestStatus.DRAFTED, DraftStatus.READY_FOR_REVIEW),
            IntakeResult("R13", "O5", RequestStatus.CONFLICT, DraftStatus.NEEDS_REVIEW),
        ]
    )

    assert (
        "2 requests: 1 new drafts (1 needs_review), 0 duplicate, 1 conflict, 0 failed, "
        "0 already processed"
    ) in capsys.readouterr().out
