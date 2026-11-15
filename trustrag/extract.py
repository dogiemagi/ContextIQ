"""Turn an uploaded file into markdown-ish text the chunker understands.

PDFs get one "## Page N" heading per page, so every citation can say *which page* an answer came from.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

MAX_BYTES = 15 * 1024 * 1024
SUPPORTED = {".pdf", ".txt", ".md", ".markdown"}


class ExtractError(ValueError):
    pass


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)  # de-hyphenate words broken across lines
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_text(filename: str, data: bytes) -> tuple[str, int]:
    """Return (markdown_text, page_count). Raises ExtractError with a user-friendly message."""
    if len(data) > MAX_BYTES:
        raise ExtractError("File is too large (limit 15 MB).")
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise ExtractError("Unsupported file type. Please upload a PDF, TXT or MD file.")
    title = Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "Document"

    if ext == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ExtractError("This PDF is password-protected.")
            pages = [_clean(p.extract_text() or "") for p in reader.pages]
        except ExtractError:
            raise
        except ImportError:
            raise ExtractError("PDF support is not installed (pip install pypdf).") from None
        except Exception:
            raise ExtractError("Could not read this PDF. It may be corrupted.") from None
        if not any(pages):
            raise ExtractError("No readable text found - this looks like a scanned PDF (images only).")
        body = "\n\n".join(f"## Page {i}\n\n{t}" for i, t in enumerate(pages, 1) if t)
        return f"# {title}\n\n{body}", len(pages)

    text = _clean(data.decode("utf-8", errors="ignore"))
    if len(text) < 10:
        raise ExtractError("This file has no readable text.")
    if ext in {".md", ".markdown"} and text.lstrip().startswith("#"):
        return text, 1
    return f"# {title}\n\n{text}", 1
