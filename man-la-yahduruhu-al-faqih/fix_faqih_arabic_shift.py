#!/usr/bin/env python3
"""
Fix the one-position shift in arabic_text for Man La Yahduruhu Al-Faqih volumes.

Background
----------
In these PDFs the Arabic text appears BEFORE the H.N English marker:

    3216 -
    [Arabic text for H.3216]
    H.3216 - English translation…
    ﴿ HADITH ﴾
    3217 -
    [Arabic text for H.3217]
    H.3217 - English translation…

The original OCR script (`ocr_faqih_arabic.py`) captured the Arabic that lies
BETWEEN H.N and H.(N+1) and assigned it to H.N.  But that Arabic belongs to
H.(N+1).  Only the Arabic before the very first H.N marker belongs to H.1 of
the volume.

Fixes applied by this script
-----------------------------
1. OCR the Arabic text on the same page as the first H.N marker but with a
   line position BEFORE that marker — this is the Arabic for the first hadith.
2. Shift every row's arabic_text DOWN by one position in the CSV
   (row[i].arabic_text ← row[i-1].arabic_text; row[0] ← newly OCR'd text).
3. Strip leading Arabic-edition hadith-number prefixes, e.g.:
     "3216 -", "2-", "٣٢١٦ -" at the start of arabic_text lines.

Usage
-----
./venv/bin/python man-la-yahduruhu-al-faqih/fix_faqih_arabic_shift.py \\
    --pdf datasets/man-la-yahduruhu-al-faqih/pdfs/man-la-yahduruhu-al-faqih-vol.1.pdf \\
    --csv datasets/man-la-yahduruhu-al-faqih/man-la-yahduruhu-al-faqih-vol.1_hadiths.csv

# Dry-run (prints what would change, writes nothing)
./venv/bin/python man-la-yahduruhu-al-faqih/fix_faqih_arabic_shift.py \\
    --pdf ... --csv ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image
from ocrmac.ocrmac import OCR


ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_RE  = re.compile(r"[A-Za-z]")
HADITH_H  = re.compile(r"^H\.?\s*(\d+)\b", re.IGNORECASE)

# Matches leading "3216 -", "2-", "٣٢١٦ -" etc. at the START of the text
# (Western digits or Arabic-Indic digits, optional space, dash/em-dash)
_NUM_PREFIX_RE = re.compile(
    r"^[\d\u0660-\u0669]+\s*[\-–—\u2010-\u2015]\s*",
)


@dataclass
class LineBox:
    text: str
    bbox: tuple[float, float, float, float]
    line_idx: int


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_arabic_only(line: str) -> bool:
    return bool(ARABIC_RE.search(line)) and not bool(LATIN_RE.search(line))


def extract_page_lines(page: fitz.Page) -> list[LineBox]:
    lines: list[LineBox] = []
    idx = 0
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            text = normalize("".join(sp.get("text", "") for sp in ln.get("spans", [])))
            if not text:
                continue
            x0, y0, x1, y1 = ln.get("bbox", (0.0, 0.0, 0.0, 0.0))
            lines.append(LineBox(text=text, bbox=(x0, y0, x1, y1), line_idx=idx))
            idx += 1
    return lines


def find_first_marker(doc: fitz.Document) -> tuple[int, int] | None:
    """Return (page_idx, line_idx) of the very first H.N marker in the document."""
    for page_idx in range(len(doc)):
        for lb in extract_page_lines(doc[page_idx]):
            if HADITH_H.match(lb.text):
                return page_idx, lb.line_idx
    return None


def ocr_arabic_before_first_marker(doc: fitz.Document, zoom: float = 3.0) -> str:
    """
    OCR the Arabic lines that appear BEFORE the first H.N marker.

    Strategy:
    - Start from the first-marker page and look for Arabic lines before the marker line.
    - If none found on that page (the first hadith's Arabic may span prior pages, e.g. a
      long chapter-opening hadith), walk backwards page by page collecting Arabic-only
      pages until we hit a page that contains Latin text (front-matter / prelude boundary).
    - OCR each Arabic region per page and concatenate.
    """
    pos = find_first_marker(doc)
    if pos is None:
        return ""
    first_page_idx, first_line_idx = pos

    # Collect per-page (page_idx, list[LineBox]) of Arabic-only lines before the marker
    per_page: list[tuple[int, list[LineBox]]] = []

    # Lines before the marker on the same page
    same_page_lines = extract_page_lines(doc[first_page_idx])
    arabic_same = [
        lb for lb in same_page_lines
        if lb.line_idx < first_line_idx and is_arabic_only(lb.text)
    ]
    if arabic_same:
        per_page.append((first_page_idx, arabic_same))

    # If the first marker page had no Arabic before it, scan backwards page by page
    # collecting Arabic-only lines.  Pages may still contain Latin chapter headers/footers
    # which we ignore — we only care about Arabic-only lines.
    # Stop when a page yields zero Arabic-only lines (true front-matter or image-only page).
    # Look back at most 15 pages to avoid runaway collection.
    if not arabic_same:
        for page_idx in range(first_page_idx - 1, max(-1, first_page_idx - 16), -1):
            page_lines = extract_page_lines(doc[page_idx])
            arabic_lines = [lb for lb in page_lines if is_arabic_only(lb.text)]
            if not arabic_lines:
                # No Arabic at all on this page → we've reached front matter, stop
                break
            per_page.insert(0, (page_idx, arabic_lines))

    if not per_page:
        return ""

    # OCR each page region and concatenate
    parts: list[str] = []
    margin = 8.0
    for page_idx, arabic_lines in per_page:
        x0 = min(lb.bbox[0] for lb in arabic_lines) - margin
        y0 = min(lb.bbox[1] for lb in arabic_lines) - margin
        x1 = max(lb.bbox[2] for lb in arabic_lines) + margin
        y1 = max(lb.bbox[3] for lb in arabic_lines) + margin
        rect = fitz.Rect(max(0.0, x0), max(0.0, y0), x1, y1)

        pix = doc[page_idx].get_pixmap(
            matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False
        )
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        results = OCR(
            image=image,
            framework="vision",
            recognition_level="accurate",
            language_preference=["ar-SA"],
            detail=False,
        ).recognize()
        page_arabic = [
            normalize(t)
            for t in results
            if normalize(t) and ARABIC_RE.search(t) and not LATIN_RE.search(t)
        ]
        if page_arabic:
            parts.append("\n".join(page_arabic))

    return "\n".join(parts).strip()


def strip_number_prefix(text: str) -> str:
    """
    Remove leading hadith-number prefix lines from the arabic_text.

    Some OCR results start with lines like:
        "3216 -"  or  "2-"  or  "٢ -"
    These are Arabic-edition hadith numbers that leaked into the OCR crop.
    Strip any such leading line from the text.
    """
    if not text:
        return text
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        # A pure-number-prefix line: only digits (Western or Arabic-Indic),
        # optional whitespace, and an optional dash — nothing else.
        if re.fullmatch(r"[\d\u0660-\u0669\s\-–—]+", stripped):
            continue
        # Strip a leading prefix from the start of the line itself
        cleaned.append(_NUM_PREFIX_RE.sub("", stripped).strip())
    # Remove empty lines that result from stripping
    cleaned = [ln for ln in cleaned if ln]
    return "\n".join(cleaned).strip()


def avg_token_length(arabic_text: str) -> float:
    if not arabic_text.strip():
        return 0.0
    tokens = arabic_text.split()
    arabic_tokens = [t for t in tokens if ARABIC_RE.search(t)]
    if not arabic_tokens:
        return 0.0
    return sum(len(t) for t in arabic_tokens) / len(arabic_tokens)


def run(pdf_path: Path, csv_path: Path, dry_run: bool) -> None:
    # --- Load CSV ---
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    print(f"Loaded {len(rows)} rows from {csv_path.name}")

    # --- OCR first-hadith Arabic ---
    print("OCR-ing Arabic before first H.N marker (first hadith)…")
    doc = fitz.open(pdf_path)
    first_arabic = ocr_arabic_before_first_marker(doc)
    doc.close()

    first_arabic_clean = strip_number_prefix(first_arabic)
    score = avg_token_length(first_arabic_clean)
    print(f"  First hadith Arabic: {len(first_arabic_clean)} chars, avg_tok={score:.1f}")
    print(f"  Preview: {first_arabic_clean[:120]!r}")

    if dry_run:
        print("[dry-run] Would shift arabic_text column down by 1 and prepend first-hadith Arabic.")
        print("[dry-run] No files written.")
        return

    # --- Build shifted arabic_text values ---
    # new[0]   = first_arabic_clean
    # new[i]   = strip_number_prefix(rows[i-1]["arabic_text"])  for i >= 1
    # rows[-1] discards its current arabic_text (Arabic after last marker = not a hadith)
    new_arabic: list[str] = [first_arabic_clean]
    for row in rows[:-1]:
        new_arabic.append(strip_number_prefix(row.get("arabic_text", "")))

    # Also strip prefixes from the last row's value (came from second-to-last position)
    # Already handled above; just ensure last row gets a clean value
    if len(rows) > 0:
        # new_arabic has len == len(rows)
        pass

    # Apply
    changed = 0
    for row, new_ar in zip(rows, new_arabic):
        old = row.get("arabic_text", "")
        if old != new_ar:
            row["arabic_text"] = new_ar
            changed += 1

    print(f"  Rows updated: {changed}/{len(rows)}")

    # --- Write ---
    backup = csv_path.with_suffix(".pre_shift_fix.bak")
    shutil.copy2(csv_path, backup)
    print(f"Backup  → {backup}")

    tmp = csv_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(csv_path)
    print(f"Written → {csv_path}")

    # --- Final stats ---
    scores = [avg_token_length(r.get("arabic_text", "")) for r in rows]
    good  = sum(1 for s in scores if s >= 3.5)
    empty = sum(1 for s in scores if s == 0)
    avg   = sum(scores) / len(scores) if scores else 0
    print(
        f"\n--- Post-fix stats ---\n"
        f"  Total rows : {len(rows)}\n"
        f"  Good (≥3.5): {good} ({100*good//len(rows)}%)\n"
        f"  Empty      : {empty}\n"
        f"  Avg tok len: {avg:.1f}"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fix arabic_text one-position shift in Faqih CSVs.")
    p.add_argument("--pdf", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    run(
        Path(args.pdf).expanduser().resolve(),
        Path(args.csv).expanduser().resolve(),
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
