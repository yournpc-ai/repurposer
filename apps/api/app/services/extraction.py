"""Text extraction from uploaded files stored as object storage keys."""

import tempfile
from pathlib import Path

import structlog

from app.services.storage import download_to_temp, save

logger = structlog.get_logger()

FileKey = str


async def extract_text(file_key: FileKey) -> str | None:
    """Extract text from a file based on its extension.

    Supported formats: .txt, .md, .markdown, .pdf

    The file is downloaded from object storage to a temporary path, processed,
    and the temp file is removed before returning.
    """
    tmp_path = await download_to_temp(file_key)
    if tmp_path is None:
        logger.warning("extract_text_missing", key=file_key)
        return None

    try:
        suffix = tmp_path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            return _extract_plaintext(tmp_path)
        if suffix == ".pdf":
            return _extract_pdf(tmp_path)
        logger.warning("unsupported_file_format", key=file_key, suffix=suffix)
        return None
    except Exception as e:
        logger.error("text_extraction_failed", key=file_key, error=str(e))
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


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


async def render_pdf_pages(
    file_key: FileKey,
    out_dir: Path,
    *,
    max_pages: int = 20,
    target_width: int = 1080,
) -> list[Path]:
    """Render PDF pages to PNGs in ``out_dir``; return the written page paths.

    Used to turn a slide deck into backing visuals for a "stills" clip. Capped at
    ``max_pages`` (logged when truncated — no silent cap). Empty list on any error
    or if PyMuPDF is unavailable; the caller falls back to text-only slides.

    The source PDF is downloaded from object storage to a temporary path before
    rendering.
    """
    if not file_key.lower().endswith(".pdf"):
        return []

    tmp_path = await download_to_temp(file_key)
    if tmp_path is None:
        logger.warning("render_pdf_pages_missing", key=file_key)
        return []

    try:
        import pymupdf  # PyMuPDF; renders pages without system deps
    except ImportError as e:
        logger.error("pymupdf_not_installed", error=str(e))
        return []

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        with pymupdf.open(str(tmp_path)) as doc:
            total = doc.page_count
            if total > max_pages:
                logger.warning(
                    "pdf_pages_truncated", key=file_key, total=total, kept=max_pages
                )
            for i in range(min(total, max_pages)):
                page = doc.load_page(i)
                zoom = target_width / page.rect.width if page.rect.width else 1.0
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
                dest = out_dir / f"page-{i + 1:03d}.png"
                pixmap.save(str(dest))
                written.append(dest)
        return written
    except Exception as e:
        logger.error("pdf_render_failed", key=file_key, error=str(e))
        return []
    finally:
        tmp_path.unlink(missing_ok=True)


async def render_pdf_pages_and_upload(
    file_key: FileKey,
    output_prefix: str,
    *,
    max_pages: int = 20,
    target_width: int = 1080,
) -> list[str]:
    """Render PDF pages and upload the PNGs to object storage.

    Returns a list of object keys. The caller stores these keys in
    ``asset.slide_pages``.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        page_paths = await render_pdf_pages(
            file_key,
            out_dir,
            max_pages=max_pages,
            target_width=target_width,
        )
        keys: list[str] = []
        for idx, page_path in enumerate(page_paths, start=1):
            key = f"{output_prefix}/page-{idx:03d}.png"
            await save(key, page_path.read_bytes(), content_type="image/png")
            keys.append(key)
        return keys
