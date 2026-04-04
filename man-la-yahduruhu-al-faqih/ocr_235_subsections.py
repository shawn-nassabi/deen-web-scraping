#!/usr/bin/env python3
"""
Custom OCR extractor for hadith 235 subsections in Tahdib al-Ahkam vol.3.

Hadith 235 was manually split into 235.1–235.7, one per SUPPLICATION./HADITH.235
section on pages 162–167 (0-indexed 161–166).  The standard OCR pipeline assigns
the full-hadith Arabic block to every 235.x row; this script instead carves out
each subsection individually and runs Apple Vision OCR on it.

Usage:
    ./venv/bin/python man-la-yahduruhu-al-faqih/ocr_235_subsections.py \
        --pdf  datasets/tahdib-al-ahkam/pdfs/tahdib-al-ahkam-vol.3.pdf \
        --csv  datasets/tahdib-al-ahkam/tahdib-al-ahkam-vol.3_hadiths.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import fitz
from PIL import Image
from ocrmac.ocrmac import OCR

ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_RE = re.compile(r"[A-Za-z]")

# Pages containing hadith 235 (0-indexed)
H235_PAGES = list(range(161, 167))  # pages 162-167


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_arabic_only(line: str) -> bool:
    return bool(ARABIC_RE.search(line)) and not bool(LATIN_RE.search(line))


def is_section_start(text: str) -> bool:
    """True for HADITH.235 or SUPPLICATION. lines."""
    if re.match(r"^HADITH\.?\s*235\b", text, re.IGNORECASE):
        return True
    if text.strip() == "SUPPLICATION.":
        return True
    return False


@dataclass
class LineBox:
    text: str
    bbox: tuple[float, float, float, float]
    page_idx: int
    line_idx: int


def extract_page_lines(page: fitz.Page, page_idx: int) -> list[LineBox]:
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
            lines.append(LineBox(text=text, bbox=(x0, y0, x1, y1), page_idx=page_idx, line_idx=line_idx))
            line_idx += 1
    return lines


def ocr_region(
    doc: fitz.Document,
    page_idx: int,
    rect: tuple[float, float, float, float],
    zoom: float = 3.0,
) -> str:
    clip = fitz.Rect(*rect)
    pix = doc[page_idx].get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
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


def bbox_for_arabic_lines(lines: list[LineBox]) -> tuple[float, float, float, float]:
    margin = 8.0
    x0 = min(ln.bbox[0] for ln in lines) - margin
    y0 = min(ln.bbox[1] for ln in lines) - margin
    x1 = max(ln.bbox[2] for ln in lines) + margin
    y1 = max(ln.bbox[3] for ln in lines) + margin
    return (max(0.0, x0), max(0.0, y0), x1, y1)


@dataclass
class Subsection:
    index: int           # 1-based: 1=235.1, 2=235.2, …
    arabic_lines: list[LineBox] = field(default_factory=list)
    by_page: dict[int, list[LineBox]] = field(default_factory=dict)

    def hadith_id(self) -> str:
        return f"235.{self.index}"


def extract_subsections(doc: fitz.Document) -> list[Subsection]:
    """
    Scan H235_PAGES and split into 7 subsections at each HADITH.235 / SUPPLICATION. marker.
    For each subsection, collect Arabic-only lines that appear BEFORE the first Latin line
    following the marker (i.e., the Arabic prayer text, not the English translation).
    """
    all_lines: list[LineBox] = []
    for page_idx in H235_PAGES:
        all_lines.extend(extract_page_lines(doc[page_idx], page_idx))

    subsections: list[Subsection] = []
    current: Subsection | None = None
    collecting_arabic = False
    sub_index = 0

    for lb in all_lines:
        text = lb.text.strip()

        if is_section_start(text):
            sub_index += 1
            current = Subsection(index=sub_index)
            subsections.append(current)
            collecting_arabic = True  # start collecting after [SOURCE]
            continue

        if current is None:
            continue

        # Skip [SOURCE] header line – but stay in collecting mode
        if text.startswith("[SOURCE]"):
            continue

        # Skip decoration noise
        if text in {"﴿", "﴾", "HADITH", "SUPPLICATION."}:
            continue

        if not collecting_arabic:
            continue

        if is_arabic_only(text):
            current.arabic_lines.append(lb)
            current.by_page.setdefault(lb.page_idx, []).append(lb)
        elif LATIN_RE.search(text):
            # First Latin line marks the end of the Arabic block for this subsection
            collecting_arabic = False

    return subsections


def run(pdf_path: Path, csv_path: Path) -> None:
    doc = fitz.open(pdf_path)
    subsections = extract_subsections(doc)

    print(f"Found {len(subsections)} subsections for hadith 235:")
    for s in subsections:
        print(f"  {s.hadith_id()}: {len(s.arabic_lines)} Arabic lines across pages "
              f"{sorted(s.by_page.keys())}")

    # OCR each subsection per page (Arabic may span multiple pages)
    ocr_results: dict[str, str] = {}
    for s in subsections:
        parts: list[str] = []
        for page_idx in sorted(s.by_page.keys()):
            page_lines = s.by_page[page_idx]
            if not page_lines:
                continue
            rect = bbox_for_arabic_lines(page_lines)
            text = ocr_region(doc, page_idx, rect)
            if text:
                parts.append(text)
            print(f"  {s.hadith_id()} page {page_idx+1}: OCR'd {len(text.splitlines())} lines")
        ocr_results[s.hadith_id()] = "\n".join(parts).strip()

    doc.close()

    # Patch the CSV
    rows: list[dict[str, str]] = []
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    backup = csv_path.with_suffix(".pre235ocr.bak")
    shutil.copy2(csv_path, backup)
    print(f"\nBackup written to {backup}")

    changed = 0
    for row in rows:
        hid = row.get("Hadith Number", "").strip()
        if hid in ocr_results and ocr_results[hid]:
            old = row.get("arabic_text", "")
            row["arabic_text"] = ocr_results[hid]
            changed += 1
            print(f"  Patched {hid}: {len(old)} → {len(ocr_results[hid])} chars")

    tmp = csv_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(csv_path)
    print(f"\nPatched {changed} rows → {csv_path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="OCR Arabic for hadith 235 subsections.")
    p.add_argument("--pdf", required=True)
    p.add_argument("--csv", required=True)
    return p


def main() -> int:
    args = build_parser().parse_args()
    run(Path(args.pdf).expanduser().resolve(), Path(args.csv).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
