"""Merge a signature PNG onto a specific page of a PDF at a given position."""
import io

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


def merge_signature_onto_pdf(
    pdf_bytes: bytes,
    sig_png_bytes: bytes,
    page_index: int,
    x_pct: float,
    y_pct: float,
    w_pct: float,
    h_pct: float,
) -> bytes:
    """
    Composite a signature PNG onto a specific page of a PDF.

    Coordinates are percentages of the page dimensions (0-100).
    y_pct is measured from the TOP of the page (matching browser convention).
    Returns the merged PDF as bytes.
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page = reader.pages[page_index]
    media = page.mediabox

    page_w = float(media.width)
    page_h = float(media.height)

    # Convert percentages to PDF points
    x_pts = x_pct / 100.0 * page_w
    w_pts = w_pct / 100.0 * page_w
    h_pts = h_pct / 100.0 * page_h

    # PDF origin is bottom-left; y_pct is top-down, so flip
    y_pts = page_h - (y_pct / 100.0 * page_h) - h_pts

    # Build a single-page overlay PDF with the signature image
    overlay_buf = io.BytesIO()
    c = Canvas(overlay_buf, pagesize=(page_w, page_h))

    sig_image = ImageReader(io.BytesIO(sig_png_bytes))
    c.drawImage(
        sig_image,
        x_pts, y_pts, w_pts, h_pts,
        mask="auto",  # preserve PNG transparency
    )
    c.save()

    # Merge overlay onto the target page
    overlay_reader = PdfReader(overlay_buf)
    page.merge_page(overlay_reader.pages[0])

    # Write the full PDF out
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
