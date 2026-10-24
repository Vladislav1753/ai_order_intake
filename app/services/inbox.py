"""Reading request files. A file that can't be used is reported, never allowed to stop the run.

Two formats:
- `*.json` in the starter pack's `request.template.json` shape (`id`, `order_ref`, `text`);
- `*.txt` / `*.eml`, a short email: `Request-Id:` and `Order-Ref:` headers (plus optional
  `From:`, `Subject:`), a blank line, then the body. The model sees the subject and body.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.core.config import PROJECT_ROOT
from app.schemas.seed import RequestIn, SeedFile
from app.services.batch import BatchItem

EMAIL_SUFFIXES = {".txt", ".eml"}


@dataclass(frozen=True)
class UnusableInput:
    source_path: str
    raw_text: str
    error: str

    @property
    def external_id(self) -> str:
        """Stable across runs: the file name plus a short hash of its content."""
        digest = hashlib.sha256(self.raw_text.encode()).hexdigest()[:8]
        return f"unusable-{Path(self.source_path).name[:40]}-{digest}"


def load_requests(seed_file: Path, inbox_dir: Path) -> tuple[list[BatchItem], list[UnusableInput]]:
    """The seed requests, then every inbox file in name order."""
    seed = SeedFile.model_validate_json(seed_file.read_text(encoding="utf-8"))
    items: list[BatchItem] = [(r, f"{_display(seed_file)}#{r.id}") for r in seed.requests]
    unusable: list[UnusableInput] = []
    seen = {request.id: (request.text, source) for request, source in items}
    files = sorted(inbox_dir.iterdir()) if inbox_dir.exists() else []
    for path in (p for p in files if p.is_file() and not p.name.startswith(".")):
        source = _display(path)
        raw = path.read_bytes().decode("utf-8", errors="replace")
        try:
            request = read_request_file(path)
        except ValueError as exc:
            unusable.append(UnusableInput(source, raw, str(exc)))
            continue
        earlier = seen.get(request.id)
        if earlier and earlier[0] != request.text:
            error = f"id {request.id} is already used by {earlier[1]} with different text"
            unusable.append(UnusableInput(source, raw, error))
            continue
        if earlier is None:
            seen[request.id] = (request.text, source)
            items.append((request, source))
    return items, unusable


def read_request_file(path: Path) -> RequestIn:
    """Raises `ValueError` with a reviewer-readable reason if the file can't be used."""
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("not UTF-8 text") from exc
    try:
        if path.suffix.lower() == ".json":
            return RequestIn.model_validate_json(raw)
        if path.suffix.lower() in EMAIL_SUFFIXES:
            return _parse_email(raw)
    except ValidationError as exc:
        problems = (f"{'.'.join(map(str, e['loc'])) or 'file'}: {e['msg']}" for e in exc.errors())
        raise ValueError("; ".join(problems)) from exc
    raise ValueError(f"unsupported file type {path.suffix or '(none)'}")


def _parse_email(raw: str) -> RequestIn:
    head, separator, body = raw.replace("\r\n", "\n").partition("\n\n")
    if not separator:
        raise ValueError("no blank line between the headers and the body")
    headers: dict[str, str] = {}
    for line in head.splitlines():
        key, colon, value = line.partition(":")
        if not colon:
            raise ValueError(f"bad header line {line!r}")
        headers[key.strip().lower()] = value.strip()
    missing = [name for name in ("Request-Id", "Order-Ref") if not headers.get(name.lower())]
    if missing:
        raise ValueError(f"missing header {', '.join(missing)}")
    subject = headers.get("subject")
    text = f"Subject: {subject}\n\n{body.strip()}" if subject else body.strip()
    return RequestIn(id=headers["request-id"], order_ref=headers["order-ref"], text=text)


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
