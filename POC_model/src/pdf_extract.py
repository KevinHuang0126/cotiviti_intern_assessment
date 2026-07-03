"""PDF to text extraction using pdfplumber."""

from __future__ import annotations

from pathlib import Path


def extract_pdf_text(pdf_path: str | Path) -> str:
    import pdfplumber

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\f".join(pages)


def extract_coverage_section(text: str, header: str = "Coverage") -> str:
    """Heuristic: grab lines after a coverage header."""
    lines = text.splitlines()
    capturing = False
    section: list[str] = []
    for line in lines:
        if header.lower() in line.lower() and not capturing:
            capturing = True
            section.append(line)
            continue
        if capturing:
            if line.strip().startswith("## ") and section:
                break
            section.append(line)
    return "\n".join(section).strip() if section else text[:4000]
