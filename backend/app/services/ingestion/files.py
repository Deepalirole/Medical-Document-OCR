import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, UnidentifiedImageError

from app.core.errors import AppError


@dataclass(frozen=True)
class ValidatedFile:
    content: bytes
    original_filename: str
    generated_filename: str
    mime_type: str
    source_type: str
    sha256: str
    page_count: int


class FileValidator:
    MIME_BY_SUFFIX = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    def __init__(self, max_upload_mb: int, max_pdf_pages: int) -> None:
        self.max_bytes = max_upload_mb * 1024 * 1024
        self.max_pdf_pages = max_pdf_pages

    def validate(self, filename: str, claimed_mime: str | None, content: bytes) -> ValidatedFile:
        if not content:
            raise AppError("FILE_EMPTY", "The uploaded file is empty.", 422)
        if len(content) > self.max_bytes:
            raise AppError("FILE_TOO_LARGE", "The file exceeds the configured upload limit.", 413)

        suffix = Path(filename).suffix.lower()
        expected_mime = self.MIME_BY_SUFFIX.get(suffix)
        if not expected_mime:
            raise AppError("FILE_TYPE_UNSUPPORTED", "Upload a PDF, JPG, JPEG, or PNG file.", 415)
        if claimed_mime and claimed_mime.split(";")[0].lower() != expected_mime:
            raise AppError("FILE_MIME_MISMATCH", "The extension and MIME type do not match.", 415)

        source_type = "pdf" if suffix == ".pdf" else "image"
        try:
            if source_type == "pdf":
                document = fitz.open(stream=content, filetype="pdf")
                if document.needs_pass:
                    raise AppError("PDF_ENCRYPTED", "Encrypted PDFs are not supported.", 422)
                page_count = document.page_count
                document.close()
                if page_count < 1:
                    raise AppError("FILE_CORRUPT", "The PDF contains no pages.", 422)
                if page_count > self.max_pdf_pages:
                    raise AppError("PDF_TOO_MANY_PAGES", "The PDF exceeds the page limit.", 422)
            else:
                with Image.open(BytesIO(content)) as image:
                    image.verify()
                page_count = 1
        except AppError:
            raise
        except (fitz.FileDataError, UnidentifiedImageError, OSError, ValueError) as error:
            raise AppError("FILE_CORRUPT", "The uploaded document cannot be read.", 422) from error

        digest = hashlib.sha256(content).hexdigest()
        return ValidatedFile(
            content=content,
            original_filename=Path(filename).name,
            generated_filename=f"{digest[:20]}{suffix}",
            mime_type=expected_mime,
            source_type=source_type,
            sha256=digest,
            page_count=page_count,
        )
