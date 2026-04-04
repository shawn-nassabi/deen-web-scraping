"""Shared OCR helpers for Arabic hadith text extraction from PDFs.

This module consolidates the ~15 duplicated functions that appeared across
five files (``ocr_arabic_preview.py``, ``ocr_faqih_arabic.py``,
``fix_faqih_arabic_shift.py``, ``ocr_235_subsections.py``,
``apply_ocr_patches.py``).

Usage pattern for any OCR script:
    markers = find_markers(doc, marker_type="faqih")
    for hid in range(start, end):
        boxes = arabic_boxes_for_hadith(doc, markers, hadith_number=hid)
        for page_idx, rect in boxes:
            ocr_text = ocr_crop(doc[page_idx], rect)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import fitz  # PyMuPDF
from PIL import Image
from ocrmac.ocrmac import OCR

# ---------------------------------------------------------------------------
# Regex constants (shared by every OCR / hadith module)
# ---------------------------------------------------------------------------
ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
LATIN_RE = re.compile(r"[A-Za-z]")

# Marker patterns per collection
HADITH_MARKER_RES: dict[str, re.Pattern[str]] = {
    "faqih":   re.compile(r"^H\.?\s*(\d+)\b", re.IGNORECASE),      # "H.123" or "H 123"
    "tahdhib": re.compile(r"^HADITH\.?\s*(\d+)\b", re.IGNORECASE),  # "HADITH.123" or "HADITH 123"
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LineBox:
    """One line of text extracted from a PDF page with its bounding box."""
    text: str
    bbox: tuple[float, float, float, float]   # (x0, y0, x1, y1)
    page_idx: int = 0
    line_idx: int = 0


@dataclass
class Marker:
    """A hadith-number marker found in the PDF."""
    hadith_number: int
    page_idx: int
    line_idx: int


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Collapse internal whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def is_arabic_only(line: str) -> bool:
    """True when *line* contains Arabic script and zero Latin characters."""
    return bool(ARABIC_RE.search(line)) and not bool(LATIN_RE.search(line))


def avg_token_length(arabic_text: str) -> float:
    """Quality proxy: average character length of Arabic tokens.

    Properly joined Arabic words yield scores of ~5-8; raw PyMuPDF
    extraction often yields ~2-3 because each glyph is a separate token.
    A threshold of 4.0 is used to decide whether to patch with OCR results.
    """
    if not arabic_text.strip():
        return 0.0
    tokens = arabic_text.split()
    arabic_tokens = [t for t in tokens if ARABIC_RE.search(t)]
    if not arabic_tokens:
        return 0.0
    return sum(len(t) for t in arabic_tokens) / len(arabic_tokens)


def extract_page_lines(
    page: fitz.Page,
    page_idx: int = 0,
) -> list[LineBox]:
    """Return a list of LineBox entries for every text line on *page*."""
    lines: list[LineBox] = []
    line_idx = 0
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            text = normalize("".join(
                sp.get("text", "") for sp in ln.get("spans", [])
            ))
            if not text:
                continue
            x0, y0, x1, y1 = ln.get("bbox", (0.0, 0.0, 0.0, 0.0))
            lines.append(LineBox(
                text=text, bbox=(x0, y0, x1, y1),
                page_idx=page_idx, line_idx=line_idx,
            ))
            line_idx += 1
    return lines


def find_markers(
    doc: fitz.Document,
    marker_type: str = "faqih",
) -> list[Marker]:
    """Scan the entire PDF for hadith markers of the given *marker_type*."""
    pattern = HADITH_MARKER_RES[marker_type]
    markers: list[Marker] = []
    for page_idx in range(len(doc)):
        for lb in extract_page_lines(doc[page_idx], page_idx):
            m = pattern.match(lb.text)
            if m:
                markers.append(Marker(
                    hadith_number=int(m.group(1)),
                    page_idx=page_idx,
                    line_idx=lb.line_idx,
                ))
    markers.sort(key=lambda mk: (mk.page_idx, mk.line_idx))
    return markers


def marker_bounds(
    markers: list[Marker],
    hadith_number: int,
) -> tuple[Marker, Marker | None]:
    """Return (start_marker, end_marker_or_None) for the given hadith number."""
    starts = [mk for mk in markers if mk.hadith_number == hadith_number]
    if not starts:
        raise ValueError(f"No marker found for hadith {hadith_number}")
    start = starts[0]
    later = [
        mk for mk in markers
        if (mk.page_idx, mk.line_idx) > (start.page_idx, start.line_idx)
    ]
    return start, (later[0] if later else None)


def arabic_boxes_for_hadith(
    doc: fitz.Document,
    markers: list[Marker],
    hadith_number: int,
    margin: float = 8.0,
) -> list[tuple[int, tuple[float, float, float, float]]]:
    """Return list of (page_idx, rect) covering Arabic text for one hadith."""
    start, end = marker_bounds(markers, hadith_number)
    results: list[tuple[int, tuple[float, float, float, float]]] = []

    for page_idx in range(
        start.page_idx,
        (end.page_idx if end else len(doc) - 1) + 1,
    ):
        page_lines = extract_page_lines(doc[page_idx], page_idx)
        line_start = start.line_idx if page_idx == start.page_idx else -1
        line_end = (
            end.line_idx
            if (end is not None and page_idx == end.page_idx)
            else 10 ** 9
        )
        segment = [lb for lb in page_lines if line_start < lb.line_idx < line_end]
        arabic = [lb for lb in segment if is_arabic_only(lb.text)]
        if not arabic:
            continue

        x0 = min(lb.bbox[0] for lb in arabic) - margin
        y0 = min(lb.bbox[1] for lb in arabic) - margin
        x1 = max(lb.bbox[2] for lb in arabic) + margin
        y1 = max(lb.bbox[3] for lb in arabic) + margin
        results.append((page_idx, (max(0.0, x0), max(0.0, y0), x1, y1)))

    return results


def ocr_crop(
    page: fitz.Page,
    rect: tuple[float, float, float, float],
    zoom: float = 3.0,
) -> str:
    """Run Apple Vision OCR on a rectangular area of a PDF page.

    Returns only Arabic-language lines (no Latin), joined with newlines.
    """
    clip = fitz.Rect(*rect)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False,
    )
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    results = OCR(
        image=image,
        framework="vision",
        recognition_level="accurate",
        language_preference=["ar-SA"],
        detail=False,
    ).recognize()
    arabic_lines = [
        normalize(t)
        for t in results
        if normalize(t) and ARABIC_RE.search(t) and not LATIN_RE.search(t)
    ]
    return "\n".join(arabic_lines).strip()


def parse_base_hadith_number(hadith_id: str) -> int | None:
    """Extract the integer portion from a hadith ID (handles decimal subsections).

    ``"235"`` → 235,  ``"235.3"`` → 235,  ``"H.123"`` → None.
    """
    value = (hadith_id or "").strip()
    if not value:
        return None
    m = re.match(r"^(\d+)(?:\.\d+)?$", value)
    return int(m.group(1)) if m else None
