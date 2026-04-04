#!/usr/bin/env python3
"""
OCR Arabic text for Man La Yahduruhu Al-Faqih volumes.

This script handles the H.N marker format used in these PDFs (vs the HADITH.N
format used in Tahdib al-Ahkam).  It:
  1. Scans the PDF for H.N hadith markers.
  2. For each hadith in the requested range, crops the Arabic bounding box and
     runs Apple Vision OCR.
  3. Writes a preview CSV (full rows with OCR arabic_text) and a compare CSV.
  4. Applies OCR patches to the main CSV wherever OCR quality is better than the
     original (avg Arabic token length >= 4.0 and strictly better than original).

Usage:
    ./venv/bin/python man-la-yahduruhu-al-faqih/ocr_faqih_arabic.py \\
        --pdf  datasets/man-la-yahduruhu-al-faqih/pdfs/man-la-yahduruhu-al-faqih-vol.1.pdf \\
        --csv  datasets/man-la-yahduruhu-al-faqih/man-la-yahduruhu-al-faqih-vol.1_hadiths.csv \\
        --hadith-start 1 --hadith-end 1573

    # Dry-run (no writes to main CSV):
    ./venv/bin/python man-la-yahduruhu-al-faqih/ocr_faqih_arabic.py \\
        --pdf ... --csv ... --hadith-start 1 --hadith-end 10 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
from ocrmac.ocrmac import OCR


ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_RE = re.compile(r"[A-Za-z]")

# Man La Yahduruhu Al-Faqih uses "H.N" or "H N" markers
HADITH_H_RE = re.compile(r"^H\.?\s*(\d+)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LineBox:
    text: str
    bbox: tuple[float, float, float, float]
    line_idx: int


@dataclass
class Marker:
    hadith_number: int
    page_idx: int
    line_idx: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_arabic_only(line: str) -> bool:
    return bool(ARABIC_RE.search(line)) and not bool(LATIN_RE.search(line))


def avg_token_length(arabic_text: str) -> float:
    if not arabic_text.strip():
        return 0.0
    tokens = arabic_text.split()
    arabic_tokens = [t for t in tokens if ARABIC_RE.search(t)]
    if not arabic_tokens:
        return 0.0
    return sum(len(t) for t in arabic_tokens) / len(arabic_tokens)


def extract_page_lines(page: fitz.Page) -> list[LineBox]:
    lines: list[LineBox] = []
    line_idx = 0
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            text = normalize("".join(sp.get("text", "") for sp in ln.get("spans", [])))
            if not text:
                continue
            x0, y0, x1, y1 = ln.get("bbox", (0.0, 0.0, 0.0, 0.0))
            lines.append(LineBox(text=text, bbox=(x0, y0, x1, y1), line_idx=line_idx))
            line_idx += 1
    return lines


def find_markers(doc: fitz.Document) -> list[Marker]:
    markers: list[Marker] = []
    for page_idx in range(len(doc)):
        for lb in extract_page_lines(doc[page_idx]):
            m = HADITH_H_RE.match(lb.text)
            if m:
                markers.append(
                    Marker(
                        hadith_number=int(m.group(1)),
                        page_idx=page_idx,
                        line_idx=lb.line_idx,
                    )
                )
    markers.sort(key=lambda mk: (mk.page_idx, mk.line_idx))
    return markers


def marker_bounds(
    markers: list[Marker], hadith_number: int
) -> tuple[Marker, Marker | None]:
    starts = [mk for mk in markers if mk.hadith_number == hadith_number]
    if not starts:
        raise ValueError(f"No marker found for hadith {hadith_number}")
    start = starts[0]
    later = [
        mk
        for mk in markers
        if (mk.page_idx, mk.line_idx) > (start.page_idx, start.line_idx)
    ]
    return start, (later[0] if later else None)


def arabic_boxes_for_hadith(
    doc: fitz.Document,
    markers: list[Marker],
    hadith_number: int,
) -> list[tuple[int, tuple[float, float, float, float]]]:
    """Return (page_idx, rect) pairs covering Arabic text for this hadith."""
    start, end = marker_bounds(markers, hadith_number)
    results: list[tuple[int, tuple[float, float, float, float]]] = []

    page_range = range(
        start.page_idx,
        (end.page_idx if end else len(doc) - 1) + 1,
    )
    for page_idx in page_range:
        page_lines = extract_page_lines(doc[page_idx])
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

        margin = 8.0
        x0 = min(lb.bbox[0] for lb in arabic) - margin
        y0 = min(lb.bbox[1] for lb in arabic) - margin
        x1 = max(lb.bbox[2] for lb in arabic) + margin
        y1 = max(lb.bbox[3] for lb in arabic) + margin
        results.append((page_idx, (max(0.0, x0), max(0.0, y0), x1, y1)))

    return results


def ocr_crop(page: fitz.Page, rect: tuple[float, float, float, float], zoom: float = 3.0) -> str:
    clip = fitz.Rect(*rect)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
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
    value = (hadith_id or "").strip()
    if not value:
        return None
    m = re.match(r"^(\d+)(?:\.\d+)?$", value)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(
    pdf_path: Path,
    csv_path: Path,
    hadith_start: int,
    hadith_end: int,
    dry_run: bool,
) -> None:
    # --- Load existing CSV ---
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    print(f"Loaded {len(rows)} rows from {csv_path.name}")

    # --- Find markers ---
    print("Scanning PDF for H.N markers…")
    doc = fitz.open(pdf_path)
    markers = find_markers(doc)
    print(f"Found {len(markers)} markers (hadith {markers[0].hadith_number}–{markers[-1].hadith_number})")

    # --- OCR pass ---
    ocr_cache: dict[int, str] = {}
    preview_rows: list[dict[str, str]] = []
    compare_rows: list[dict[str, str]] = []

    target_rows = [
        row for row in rows
        if (n := parse_base_hadith_number(row.get("Hadith Number", ""))) is not None
        and hadith_start <= n <= hadith_end
    ]
    print(f"OCR target: {len(target_rows)} rows in range {hadith_start}–{hadith_end}")

    for i, row in enumerate(target_rows, 1):
        hid = row.get("Hadith Number", "").strip()
        base = parse_base_hadith_number(hid)
        if base is None:
            continue

        if base not in ocr_cache:
            try:
                boxes = arabic_boxes_for_hadith(doc, markers, base)
            except ValueError as exc:
                print(f"  WARN {hid}: {exc}")
                ocr_cache[base] = ""
            else:
                parts = [ocr_crop(doc[pi], rect) for pi, rect in boxes]
                ocr_cache[base] = "\n".join(p for p in parts if p).strip()

        ocr_text = ocr_cache.get(base, "")
        preview_row = dict(row)
        if ocr_text:
            preview_row["arabic_text"] = ocr_text
        preview_rows.append(preview_row)

        compare_rows.append({
            "Hadith Number": hid,
            "page_start": row.get("page_start", ""),
            "page_end": row.get("page_end", ""),
            "original_arabic_text": row.get("arabic_text", ""),
            "ocr_arabic_text": ocr_text,
        })

        if i % 50 == 0:
            print(f"  … {i}/{len(target_rows)} done")

    doc.close()

    # --- Write preview & compare CSVs ---
    stem = csv_path.stem  # e.g. man-la-yahduruhu-al-faqih-vol.1_hadiths
    preview_path = csv_path.parent / f"{stem}_ocr_preview.csv"
    compare_path = csv_path.parent / f"{stem}_ocr_compare.csv"

    with preview_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(preview_rows)

    with compare_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["Hadith Number", "page_start", "page_end",
                        "original_arabic_text", "ocr_arabic_text"],
        )
        writer.writeheader()
        writer.writerows(compare_rows)

    print(f"Preview → {preview_path}")
    print(f"Compare → {compare_path}")

    # --- Apply patches to main CSV ---
    if dry_run:
        _report_patch_stats(rows, compare_rows, dry_run=True)
        return

    backup = csv_path.with_suffix(".pre_ocr_patch.bak")
    shutil.copy2(csv_path, backup)
    print(f"Backup  → {backup}")

    # Build lookup from compare_rows for OCR text
    ocr_by_hid: dict[str, str] = {r["Hadith Number"]: r["ocr_arabic_text"] for r in compare_rows}

    patched = 0
    skipped_no_improvement = 0
    for row in rows:
        hid = row.get("Hadith Number", "").strip()
        if hid not in ocr_by_hid:
            continue
        ocr_text = ocr_by_hid[hid]
        if not ocr_text:
            continue
        orig_text = row.get("arabic_text", "")
        orig_score = avg_token_length(orig_text)
        ocr_score = avg_token_length(ocr_text)
        if ocr_score >= 4.0 and ocr_score > orig_score:
            row["arabic_text"] = ocr_text
            patched += 1
        else:
            skipped_no_improvement += 1

    tmp = csv_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(csv_path)
    print(f"Patched → {csv_path}")

    _report_patch_stats(rows, compare_rows, dry_run=False, patched=patched,
                        skipped=skipped_no_improvement)


def _report_patch_stats(
    rows: list[dict[str, str]],
    compare_rows: list[dict[str, str]],
    dry_run: bool,
    patched: int = 0,
    skipped: int = 0,
) -> None:
    total = len(rows)
    good = sum(1 for r in rows if avg_token_length(r.get("arabic_text", "")) >= 4.0)
    frag = sum(1 for r in rows if 0 < avg_token_length(r.get("arabic_text", "")) < 3.5)
    empty = sum(1 for r in rows if avg_token_length(r.get("arabic_text", "")) == 0)
    print(
        f"\n--- {'DRY-RUN ' if dry_run else ''}Results ---\n"
        f"  Total rows      : {total}\n"
        f"  Good (>=4.0)    : {good} ({100*good//total if total else 0}%)\n"
        f"  Fragmented (<3.5): {frag}\n"
        f"  Empty           : {empty}"
    )
    if not dry_run:
        print(f"  Patched         : {patched}\n  Skipped (no improve): {skipped}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="OCR Arabic text for Man La Yahduruhu Al-Faqih volumes."
    )
    p.add_argument("--pdf", required=True, help="PDF path.")
    p.add_argument("--csv", required=True, help="Main hadith CSV path.")
    p.add_argument("--hadith-start", type=int, default=1, help="First hadith number to process.")
    p.add_argument("--hadith-end", type=int, default=9999999, help="Last hadith number to process.")
    p.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    return p


def main() -> int:
    args = build_parser().parse_args()
    run(
        pdf_path=Path(args.pdf).expanduser().resolve(),
        csv_path=Path(args.csv).expanduser().resolve(),
        hadith_start=args.hadith_start,
        hadith_end=args.hadith_end,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
