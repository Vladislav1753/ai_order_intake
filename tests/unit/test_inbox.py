import json
from pathlib import Path

import pytest

from app.services.inbox import load_requests, read_request_file

SEED = {"catalog": [], "requests": [{"id": "R1", "order_ref": "O1", "text": "2 CAB-1"}]}


@pytest.fixture
def seed_file(tmp_path: Path) -> Path:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(SEED), encoding="utf-8")
    return path


def write(directory: Path, name: str, content: str | bytes) -> Path:
    directory.mkdir(exist_ok=True)
    path = directory / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def test_email_file_keeps_subject_and_body(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "r5.txt",
        "From: buyer@example.test\nSubject: Cables\nRequest-Id: R5\nOrder-Ref: O5\n\n"
        "Hi,\nplease send 3 CAB-2.\n",
    )

    request = read_request_file(path)

    assert (request.id, request.order_ref) == ("R5", "O5")
    assert request.text == "Subject: Cables\n\nHi,\nplease send 3 CAB-2."


def test_json_file_uses_the_template_shape(tmp_path: Path) -> None:
    path = write(
        tmp_path, "r6.json", json.dumps({"id": "R6", "order_ref": "O6", "text": "1 HUB-1"})
    )

    assert read_request_file(path).text == "1 HUB-1"


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("bad.json", "{not json", "Invalid JSON"),
        ("no-ref.json", json.dumps({"id": "R7", "text": "x"}), "order_ref"),
        ("no-headers.txt", "Request-Id: R8\n\n", "missing header Order-Ref"),
        ("empty.txt", "Request-Id: R8\nOrder-Ref: O8\n\n   \n", "text"),
        ("one-block.txt", "Request-Id: R8\nOrder-Ref: O8", "no blank line"),
        ("photo.png", b"\x89PNG", "not UTF-8"),
        ("notes.md", "hello", "unsupported file type .md"),
    ],
)
def test_unusable_files_get_a_readable_reason(
    tmp_path: Path, name: str, content: str | bytes, reason: str
) -> None:
    with pytest.raises(ValueError, match=reason):
        read_request_file(write(tmp_path, name, content))


def test_unusable_files_are_reported_and_the_rest_still_load(
    tmp_path: Path, seed_file: Path
) -> None:
    inbox = tmp_path / "inbox"
    write(inbox, "a.json", json.dumps({"id": "R5", "order_ref": "O5", "text": "2 CAB-2"}))
    write(inbox, "b.json", "{broken")
    write(inbox, "c.json", json.dumps({"id": "R1", "order_ref": "O1", "text": "other text"}))

    items, unusable = load_requests(seed_file, inbox)

    assert [request.id for request, _ in items] == ["R1", "R5"]
    assert [(Path(u.source_path).name, "id R1" in u.error) for u in unusable] == [
        ("b.json", False),
        ("c.json", True),
    ]
    assert unusable[0].external_id.startswith("unusable-b.json-")


def test_missing_inbox_means_seed_requests_only(tmp_path: Path, seed_file: Path) -> None:
    items, unusable = load_requests(seed_file, tmp_path / "missing")

    assert [request.id for request, _ in items] == ["R1"]
    assert unusable == []
