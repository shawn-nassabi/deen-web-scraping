#!/usr/bin/env python3
"""One-time parser for Man La Yahduruhu Al-Faqih PDF volumes."""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF


DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[1] / "datasets" / "man-la-yahduruhu-al-faqih"
)

CSV_COLUMNS = [
    "Chapter Number",
    "Chapter Title",
    "Hadith Number",
    "arabic_text",
    "english_text",
    "commentary",
    "references",
    "source_pdf",
    "page_start",
    "page_end",
]

CHAPTER_HEADER_RE = re.compile(r"^CHAPTER\s+(\d+)\s*[-–]\s*(.+)$", re.IGNORECASE)
HADITH_START_RE = re.compile(r"^H\.?\s*(\d+)\s*(?:[-–—]\s*)?(.*)$", re.IGNORECASE)
REFERENCES_RE = re.compile(r"^\[REFERENCES\]\s*(.*)$", re.IGNORECASE)
AL_SADUQ_RE = re.compile(r"^\[AL\s+SADUQ\]$", re.IGNORECASE)
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_RE = re.compile(r"[A-Za-z]")


@dataclass
class HadithRecord:
    chapter_number: str
    chapter_title: str
    hadith_number: str
    source_pdf: str
    page_start: int
    page_end: int
    arabic_lines: list[str] = field(default_factory=list)
    english_lines: list[str] = field(default_factory=list)
    commentary_lines: list[str] = field(default_factory=list)
    references_lines: list[str] = field(default_factory=list)


def normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_text_block(lines: Iterable[str], separator: str = "\n") -> str:
    cleaned = [normalize_line(line) for line in lines if normalize_line(line)]
    if not cleaned:
        return ""
    joined = separator.join(cleaned)
    joined = re.sub(r" *\n *", "\n", joined)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def clean_chapter_title(title: str) -> str:
    text = normalize_line(title)
    text = re.sub(r"\.{2,}\s*\d+\s*$", "", text)
    return text.strip()


def contains_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text))


def has_latin(text: str) -> bool:
    return bool(LATIN_RE.search(text))


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    if line in {"﴿", "﴾", "HADITH", "-", "–", "—"}:
        return True
    if re.fullmatch(r"֎\s*HADITH\s+\d+\s*[–-]\s*\d+\s*֍", line, re.IGNORECASE):
        return True
    if re.fullmatch(r"[֎֍]+", line):
        return True
    return False


def finalize_record(record: HadithRecord) -> dict[str, str | int]:
    return {
        "Chapter Number": record.chapter_number,
        "Chapter Title": record.chapter_title,
        "Hadith Number": record.hadith_number,
        "arabic_text": clean_text_block(record.arabic_lines),
        "english_text": clean_text_block(record.english_lines),
        "commentary": clean_text_block(record.commentary_lines),
        "references": clean_text_block(record.references_lines, separator=" "),
        "source_pdf": record.source_pdf,
        "page_start": record.page_start,
        "page_end": record.page_end,
    }


def parse_pdf(pdf_path: Path) -> list[dict[str, str | int]]:
    doc = fitz.open(pdf_path)
    results: list[dict[str, str | int]] = []

    current_chapter_number = ""
    current_chapter_title = ""
    current_hadith: HadithRecord | None = None
    mode = "between"
    pending_arabic_lines: list[str] = []
    content_started = False
    first_page_hadith_prelude = False

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        page_text = doc[page_idx].get_text("text")
        page_has_hadith_marker = any(
            HADITH_START_RE.match(normalize_line(line))
            for line in page_text.splitlines()
            if normalize_line(line)
        )
        if not content_started and not page_has_hadith_marker:
            continue

        for raw_line in page_text.splitlines():
            line = normalize_line(raw_line)
            if not line:
                continue

            chapter_match = CHAPTER_HEADER_RE.match(line)
            if chapter_match:
                current_chapter_number = chapter_match.group(1).strip()
                current_chapter_title = clean_chapter_title(chapter_match.group(2))
                if mode == "references":
                    mode = "between"
                continue

            hadith_match = HADITH_START_RE.match(line)
            if hadith_match:
                content_started = True
                first_page_hadith_prelude = False
                if current_hadith is not None:
                    results.append(finalize_record(current_hadith))

                hadith_number = hadith_match.group(1).strip()
                remainder = normalize_line(hadith_match.group(2))
                current_hadith = HadithRecord(
                    chapter_number=current_chapter_number,
                    chapter_title=current_chapter_title,
                    hadith_number=hadith_number,
                    source_pdf=pdf_path.name,
                    page_start=page_num,
                    page_end=page_num,
                    arabic_lines=pending_arabic_lines.copy(),
                )
                pending_arabic_lines.clear()
                mode = "english"
                if remainder and remainder not in {"-", "–", "—"}:
                    current_hadith.english_lines.append(remainder)
                continue

            if not content_started:
                if line == "HADITH":
                    first_page_hadith_prelude = True
                    pending_arabic_lines.clear()
                    continue
                if first_page_hadith_prelude:
                    if line in {"﴿", "﴾", "-", "–", "—"}:
                        continue
                    if re.fullmatch(r"\d{1,4}", line):
                        continue
                    if contains_arabic(line):
                        pending_arabic_lines.append(line)
                continue

            if is_noise_line(line):
                if mode in {"english", "commentary", "references"}:
                    mode = "between"
                continue

            if re.fullmatch(r"\d{1,4}", line):
                continue

            if AL_SADUQ_RE.match(line):
                if current_hadith is not None:
                    mode = "commentary"
                    current_hadith.page_end = page_num
                continue

            references_match = REFERENCES_RE.match(line)
            if references_match:
                if current_hadith is not None:
                    mode = "references"
                    first_ref_line = normalize_line(references_match.group(1))
                    if first_ref_line:
                        current_hadith.references_lines.append(first_ref_line)
                        current_hadith.page_end = page_num
                continue

            if current_hadith is None:
                if contains_arabic(line):
                    pending_arabic_lines.append(line)
                continue

            if mode == "english":
                if contains_arabic(line) and not has_latin(line):
                    mode = "between"
                    pending_arabic_lines.append(line)
                else:
                    current_hadith.english_lines.append(line)
                    current_hadith.page_end = page_num
                continue

            if mode == "commentary":
                if contains_arabic(line) and not has_latin(line):
                    mode = "between"
                    pending_arabic_lines.append(line)
                else:
                    current_hadith.commentary_lines.append(line)
                    current_hadith.page_end = page_num
                continue

            if mode == "references":
                if contains_arabic(line) and not has_latin(line):
                    mode = "between"
                    pending_arabic_lines.append(line)
                else:
                    current_hadith.references_lines.append(line)
                    current_hadith.page_end = page_num
                continue

            if mode == "between" and contains_arabic(line):
                pending_arabic_lines.append(line)

    if current_hadith is not None:
        results.append(finalize_record(current_hadith))

    doc.close()
    return results


def write_csv(rows: list[dict[str, str | int]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def run(input_paths: list[str], output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    for input_path_str in input_paths:
        input_path = Path(input_path_str).expanduser().resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"Input PDF does not exist: {input_path}")

        rows = parse_pdf(input_path)
        output_csv = output_dir / f"{input_path.stem}_hadiths.csv"
        write_csv(rows, output_csv)

        first_hadith = rows[0]["Hadith Number"] if rows else ""
        last_hadith = rows[-1]["Hadith Number"] if rows else ""
        print(
            f"{input_path.name}: rows={len(rows)}, first_hadith={first_hadith}, "
            f"last_hadith={last_hadith}, output={output_csv}"
        )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse Man La Yahduruhu Al-Faqih PDFs into one-row-per-hadith CSV files."
    )
    parser.add_argument(
        "--input",
        nargs="+",
        required=True,
        help="One or more input PDF paths.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory for CSV files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return run(args.input, Path(args.output_dir).expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
