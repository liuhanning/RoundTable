"""
Attachment upload, validation, and extraction service.
"""
import json
import shutil
from pathlib import Path
from typing import Dict, Optional

from engine.structures import AttachmentRecord
from utils.file_validator import FileUploadValidationError, validate_upload
from utils.prompt_injection import build_safe_context


INJECTABLE_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
LIST_ONLY_EXTENSIONS = {".xlsx", ".pptx"}


class AttachmentService:
    """Manage uploaded attachments before session creation."""

    def __init__(self, base_dir: str = "data/uploads"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, filename: str, content: bytes) -> AttachmentRecord:
        """Validate and persist a single uploaded file."""
        validation = validate_upload(filename=filename, file_size=len(content), content=content)
        if not validation["valid"]:
            raise FileUploadValidationError(validation["error"])

        extension = Path(filename).suffix.lower()
        attachment_id = validation["file_hash"][:12]
        attachment_dir = self.base_dir / attachment_id
        attachment_dir.mkdir(parents=True, exist_ok=True)

        stored_path = attachment_dir / filename
        stored_path.write_bytes(content)

        extraction_status = "skipped"
        extraction_error = None
        injection_mode = "listed_only"
        extracted_text = None

        if extension in INJECTABLE_EXTENSIONS:
            try:
                extracted_text = self._extract_text(stored_path, extension)
                safe_context = build_safe_context(
                    [{"source": filename, "text": extracted_text, "relevance": 1.0}]
                )
                (attachment_dir / "context.txt").write_text(safe_context, encoding="utf-8")
                injection_mode = "embedded"
                extraction_status = "ready"
            except Exception as exc:
                extraction_status = "failed"
                extraction_error = str(exc)
                raise FileUploadValidationError(f"Attachment extraction failed: {exc}") from exc
        elif extension in LIST_ONLY_EXTENSIONS:
            injection_mode = "listed_only"
            extraction_status = "skipped"

        record = AttachmentRecord(
            attachment_id=attachment_id,
            filename=filename,
            extension=extension,
            size_bytes=len(content),
            stored_path=str(stored_path),
            injection_mode=injection_mode,
            extraction_status=extraction_status,
            extraction_error=extraction_error,
        )
        self._write_metadata(record)
        return record

    def load_attachment(self, attachment_id: str) -> Optional[AttachmentRecord]:
        """Load persisted attachment metadata."""
        metadata_path = self.base_dir / attachment_id / "metadata.json"
        if not metadata_path.exists():
            return None
        with open(metadata_path, "r", encoding="utf-8") as handle:
            return AttachmentRecord.from_dict(json.load(handle))

    def promote_to_session(self, attachment_id: str, session_id: str) -> Optional[AttachmentRecord]:
        """Copy uploaded attachment metadata into a session-owned path."""
        record = self.load_attachment(attachment_id)
        if record is None:
            return None

        source_dir = self.base_dir / attachment_id
        target_dir = Path("data/sessions") / session_id / "attachments" / attachment_id
        target_dir.mkdir(parents=True, exist_ok=True)

        for item in source_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, target_dir / item.name)

        record.stored_path = str(target_dir / record.filename)
        return record

    def _write_metadata(self, record: AttachmentRecord) -> None:
        metadata_path = self.base_dir / record.attachment_id / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as handle:
            json.dump(record.to_dict(), handle, ensure_ascii=False, indent=2)

    def _extract_text(self, path: Path, extension: str) -> str:
        if extension in {".txt", ".md"}:
            return path.read_text(encoding="utf-8")
        if extension == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if extension == ".docx":
            from docx import Document

            document = Document(str(path))
            return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
        raise FileUploadValidationError(f"Unsupported extraction type: {extension}")
