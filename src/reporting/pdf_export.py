"""PDF report generation via xhtml2pdf."""

from __future__ import annotations
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.db import Database
from src.reporting.html_export import export_findings_html, export_removals_html

logger = logging.getLogger(__name__)


def _html_to_pdf(html_path: str, pdf_path: str) -> str:
    """Convert an HTML file to PDF using xhtml2pdf."""
    from xhtml2pdf import pisa

    html_content = Path(html_path).read_text(encoding="utf-8")
    with open(pdf_path, "wb") as f:
        result = pisa.CreatePDF(io.StringIO(html_content), dest=f)
    if result.err:
        logger.error("PDF conversion had %d errors", result.err)
    return pdf_path


def export_findings_pdf(db: Database, profile: Optional[str] = None,
                        output: Optional[str] = None) -> str:
    """Export findings to a PDF report file."""
    findings = db.get_findings(profile=profile)

    # Generate HTML first
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = str(DATA_DIR / "scans" / f"findings_{ts}_tmp.html")
    export_findings_html(findings, html_path, profile_name=profile or "")

    # Convert to PDF
    if output:
        pdf_path = output
    else:
        pdf_path = str(DATA_DIR / "scans" / f"findings_{ts}.pdf")
    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)

    _html_to_pdf(html_path, pdf_path)

    # Cleanup temp HTML
    try:
        Path(html_path).unlink()
    except OSError:
        pass

    logger.info("PDF export complete: %s (%d findings)", pdf_path, len(findings))
    return pdf_path


def export_removals_pdf(db: Database, profile: Optional[str] = None,
                        output: Optional[str] = None) -> str:
    """Export removals to a PDF report file."""
    removals = db.get_removals(profile=profile)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = str(DATA_DIR / "scans" / f"removals_{ts}_tmp.html")
    export_removals_html(removals, html_path, profile_name=profile or "")

    if output:
        pdf_path = output
    else:
        pdf_path = str(DATA_DIR / "scans" / f"removals_{ts}.pdf")
    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)

    _html_to_pdf(html_path, pdf_path)

    try:
        Path(html_path).unlink()
    except OSError:
        pass

    logger.info("PDF export complete: %s (%d removals)", pdf_path, len(removals))
    return pdf_path
