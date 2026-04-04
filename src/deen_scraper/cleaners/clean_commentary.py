#!/usr/bin/env python3
"""
Post-processing script to strip Arabic text from the commentary field.

The parser's dot_seen_arabic_quote_end heuristic (now removed) previously caused
Arabic continuation lines from the hadith text to be mis-routed to commentary_lines
whenever a » character appeared mid-Arabic-block.  Some Arabic commentary from editors
(Tusi / Mufid) also lands in commentary via the dot_seen_latin_for_current_hadith flag
when the Arabic original of the commentary precedes its English translation.

This script cleans the existing vol.3 CSV (which has manual 235.x splits and OCR patches
that we want to preserve) by stripping pure-Arabic lines from the commentary field.
It does NOT attempt to move stripped lines to arabic_text to avoid overwriting OCR work.

Usage:
    ./venv/bin/python man-la-yahduruhu-al-faqih/clean_commentary_arabic.py \
        --input  datasets/tahdib-al-ahkam/tahdib-al-ahkam-vol.3_hadiths.csv \
        --output datasets/tahdib-al-ahkam/tahdib-al-ahkam-vol.3_hadiths.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
LATIN_RE = re.compile(r"[A-Za-z]")

CSV_COLUMNS = [
    "Chapter Number",
    "Chapter Title",
    "Hadith Number",
    "arabic_text",
    "english_text",
    "source",
    "commentary",
    "references",
    "source_pdf",
    "page_start",
    "page_end",
]


def is_arabic_only_line(line: str) -> bool:
    """True if the line contains Arabic but no Latin characters."""
    stripped = line.strip()
    return bool(ARABIC_RE.search(stripped)) and not LATIN_RE.search(stripped)


# Decorative hadith banners that leak into english_text:
#   ֎ HADITH 266 ֍   (single-number banner)
#   ֎ HADITH - ֍     (dash-only banner)
# The parser now filters these via is_noise_line; this regex cleans existing CSVs.
_NOISE_BANNER_RE = re.compile(
    r"֎\s*HADITH\s*(?:\d+|[-–—])\s*֍",
    re.IGNORECASE,
)


def strip_noise_banners(text: str) -> str:
    """Remove decorative ֎ HADITH N ֍ / ֎ HADITH - ֍ banners from a text field."""
    if not text:
        return text
    cleaned = _NOISE_BANNER_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def strip_arabic_from_commentary(commentary: str) -> str:
    """
    Remove lines that are purely Arabic (contain Arabic script but no Latin letters).
    Lines that are empty, purely numeric/punctuation, or contain both Arabic and Latin
    are left untouched.
    """
    if not commentary:
        return commentary

    kept: list[str] = []
    for line in commentary.split("\n"):
        if not is_arabic_only_line(line):
            kept.append(line)

    # Collapse runs of blank lines left after removal
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def process_csv(input_path: Path, output_path: Path) -> None:
    rows: list[dict[str, str]] = []
    with input_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))

    commentary_changed = 0
    banner_changed = 0
    for row in rows:
        original_comm = row.get("commentary", "")
        cleaned_comm = strip_arabic_from_commentary(original_comm)
        if cleaned_comm != original_comm:
            row["commentary"] = cleaned_comm
            commentary_changed += 1

        original_eng = row.get("english_text", "")
        cleaned_eng = strip_noise_banners(original_eng)
        if cleaned_eng != original_eng:
            row["english_text"] = cleaned_eng
            banner_changed += 1

    print(
        f"Processed {len(rows)} rows; "
        f"cleaned commentary in {commentary_changed} rows, "
        f"removed noise banners from english_text in {banner_changed} rows."
    )

    # Write atomically: write to a temp file then replace
    tmp_path = output_path.with_suffix(".tmp")
    fieldnames = [c for c in CSV_COLUMNS if c in rows[0]] if rows else CSV_COLUMNS
    with tmp_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(output_path)
    print(f"Wrote {output_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Strip Arabic lines from commentary field.")
    p.add_argument("--input", required=True, help="Input CSV path.")
    p.add_argument(
        "--output",
        required=True,
        help="Output CSV path (can be same as input to edit in-place).",
    )
    p.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Write a .bak backup of the input before overwriting (default: True).",
    )
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}")
        return 1

    if args.backup and input_path == output_path:
        backup = input_path.with_suffix(".bak")
        shutil.copy2(input_path, backup)
        print(f"Backup written to {backup}")

    process_csv(input_path, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
