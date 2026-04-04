#!/usr/bin/env python3
"""
Apply arabic_text patches from an OCR preview CSV to the main hadith CSV.

Strategy:
  - For each hadith, compute average Arabic token length (proxy for "joinedness").
    Raw PyMuPDF extraction produces many single-char tokens (avg ~2-3).
    Apple Vision OCR produces whole words (avg ~5-8).
  - Patch the main CSV row when the OCR arabic_text is clearly better:
      * OCR avg_token_len >= 4.0  (properly joined Arabic words)
      * AND OCR avg_token_len >  original avg_token_len  (improvement)
  - Skip rows whose hadith ID is in --skip-ids (default: 235.1-235.7 handled separately).
  - Always write a backup before patching.

Usage:
    ./venv/bin/python man-la-yahduruhu-al-faqih/apply_ocr_patches.py \
        --preview datasets/tahdib-al-ahkam/tahdib-al-ahkam-vol.3_hadiths_ocr_preview.csv \
        --main    datasets/tahdib-al-ahkam/tahdib-al-ahkam-vol.3_hadiths.csv \
        --skip-ids 235.1 235.2 235.3 235.4 235.5 235.6 235.7
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def avg_token_length(arabic_text: str) -> float:
    if not arabic_text.strip():
        return 0.0
    tokens = arabic_text.split()
    arabic_tokens = [t for t in tokens if ARABIC_RE.search(t)]
    if not arabic_tokens:
        return 0.0
    return sum(len(t) for t in arabic_tokens) / len(arabic_tokens)


def run(preview_path: Path, main_path: Path, skip_ids: set[str], dry_run: bool) -> None:
    # Load preview rows keyed by hadith number
    preview: dict[str, str] = {}
    with preview_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            hid = row.get("Hadith Number", "").strip()
            at = row.get("arabic_text", "").strip()
            if hid and at:
                preview[hid] = at

    # Load main rows
    rows: list[dict[str, str]] = []
    with main_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    improved = 0
    skipped_explicit = 0
    skipped_no_improvement = 0

    for row in rows:
        hid = row.get("Hadith Number", "").strip()

        if hid in skip_ids:
            skipped_explicit += 1
            continue

        ocr_text = preview.get(hid, "")
        if not ocr_text:
            continue

        orig_text = row.get("arabic_text", "")
        orig_score = avg_token_length(orig_text)
        ocr_score = avg_token_length(ocr_text)

        # Only patch when OCR Arabic looks like proper joined words AND is better
        if ocr_score >= 4.0 and ocr_score > orig_score:
            if not dry_run:
                row["arabic_text"] = ocr_text
            improved += 1
        else:
            skipped_no_improvement += 1

    print(f"Rows patched   : {improved}")
    print(f"Rows skipped (explicit skip-ids): {skipped_explicit}")
    print(f"Rows skipped (no improvement)  : {skipped_no_improvement}")

    if dry_run:
        print("[dry-run] No changes written.")
        return

    backup = main_path.with_suffix(".pre_ocr_patch.bak")
    shutil.copy2(main_path, backup)
    print(f"Backup → {backup}")

    tmp = main_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(main_path)
    print(f"Written → {main_path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Apply OCR arabic_text patches to main CSV.")
    p.add_argument("--preview", required=True, help="OCR preview CSV from ocr_arabic_preview.py.")
    p.add_argument("--main", required=True, help="Main hadith CSV to patch.")
    p.add_argument(
        "--skip-ids",
        nargs="*",
        default=["235.1", "235.2", "235.3", "235.4", "235.5", "235.6", "235.7"],
        help="Hadith IDs to skip (handled by a separate script).",
    )
    p.add_argument("--dry-run", action="store_true", help="Report without writing.")
    return p


def main() -> int:
    args = build_parser().parse_args()
    run(
        Path(args.preview).expanduser().resolve(),
        Path(args.main).expanduser().resolve(),
        set(args.skip_ids),
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
