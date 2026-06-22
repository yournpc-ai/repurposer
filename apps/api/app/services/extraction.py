"""Text extraction from uploaded files."""

from pathlib import Path

import structlog

from app.config import settings

logger = structlog.get_logger()

FilePath = str | Path


def extract_text(file_path: FilePath) -> str | None:
    """Extract text from a file based on its extension.

    Supported formats: .txt, .md, .markdown, .pdf

    Args:
        file_path: Absolute path or path relative to settings.upload_dir.
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = settings.upload_dir / path

    suffix = path.suffix.lower()

    try:
        if suffix in {".txt", ".md", ".markdown"}:
            return _extract_plaintext(path)
        if suffix == ".pdf":
            return _extract_pdf(path)
        logger.warning("unsupported_file_format", path=str(path), suffix=suffix)
        return None
    except Exception as e:
        logger.error("text_extraction_failed", path=str(path), error=str(e))
        return None


def _extract_plaintext(file_path: Path) -> str | None:
    """Extract text from a plain text file."""
    # Try utf-8 first, fallback to common encodings
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]
    for encoding in encodings:
        try:
            with file_path.open("r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return None


def _extract_pdf(file_path: Path) -> str | None:
    """Extract text from a PDF file."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        logger.error("pypdf_not_installed", error=str(e))
        return None

    reader = PdfReader(str(file_path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages) if pages else None
