#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
from ocrmac.ocrmac import OCR


ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_RE = re.compile(r"[A-Za-z]")
HADITH_DOT_RE = re.compile(r"^HADITH\.?\s*(\d+)\b", re.IGNORECASE)


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


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_arabic_only(line: str) -> bool:
    return bool(ARABIC_RE.search(line)) and not bool(LATIN_RE.search(line))


def extract_page_lines(page: fitz.Page) -> list[LineBox]:
    lines: list[LineBox] = []
    line_idx = 0
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = normalize("".join(span.get("text", "") for span in spans))
            if not text:
                continue
            x0, y0, x1, y1 = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
            lines.append(LineBox(text=text, bbox=(x0, y0, x1, y1), line_idx=line_idx))
            line_idx += 1
    return lines


def find_markers(doc: fitz.Document) -> list[Marker]:
    markers: list[Marker] = []
    for page_idx in range(len(doc)):
        lines = extract_page_lines(doc[page_idx])
        for line in lines:
            match = HADITH_DOT_RE.match(line.text)
            if match:
                markers.append(
                    Marker(
                        hadith_number=int(match.group(1)),
                        page_idx=page_idx,
                        line_idx=line.line_idx,
                    )
                )
    markers.sort(key=lambda marker: (marker.page_idx, marker.line_idx))
    return markers


def marker_bounds(markers: list[Marker], hadith_number: int) -> tuple[Marker, Marker | None]:
    starts = [marker for marker in markers if marker.hadith_number == hadith_number]
    if not starts:
        raise ValueError(f"Could not find marker for hadith {hadith_number}.")
    start = starts[0]
    later = [marker for marker in markers if (marker.page_idx, marker.line_idx) > (start.page_idx, start.line_idx)]
    end = later[0] if later else None
    return start, end


def parse_base_hadith_number(hadith_id: str) -> int | None:
    value = (hadith_id or "").strip()
    if not value:
        return None
    match = re.match(r"^(\d+)(?:\.\d+)?$", value)
    if not match:
        return None
    return int(match.group(1))


def arabic_boxes_for_hadith(
    doc: fitz.Document, markers: list[Marker], hadith_number: int
) -> list[tuple[int, tuple[float, float, float, float]]]:
    start, end = marker_bounds(markers, hadith_number)
    results: list[tuple[int, tuple[float, float, float, float]]] = []

    for page_idx in range(start.page_idx, (end.page_idx if end else len(doc) - 1) + 1):
        lines = extract_page_lines(doc[page_idx])
        page_line_start = start.line_idx if page_idx == start.page_idx else -1
        page_line_end = end.line_idx if (end is not None and page_idx == end.page_idx) else 10**9

        segment = [line for line in lines if page_line_start < line.line_idx < page_line_end]
        arabic_lines: list[LineBox] = []
        for line in segment:
            if is_arabic_only(line.text):
                arabic_lines.append(line)

        if not arabic_lines:
            continue

        x0 = min(line.bbox[0] for line in arabic_lines)
        y0 = min(line.bbox[1] for line in arabic_lines)
        x1 = max(line.bbox[2] for line in arabic_lines)
        y1 = max(line.bbox[3] for line in arabic_lines)
        margin = 8.0
        rect = (max(0.0, x0 - margin), max(0.0, y0 - margin), x1 + margin, y1 + margin)
        results.append((page_idx, rect))

    return results


def ocr_crop(page: fitz.Page, rect: tuple[float, float, float, float], zoom: float = 3.0) -> str:
    clip = fitz.Rect(*rect)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    ocr_results = OCR(
        image=image,
        framework="vision",
        recognition_level="accurate",
        language_preference=["ar-SA"],
        detail=False,
    ).recognize()
    arabic_lines = [
        normalize(text)
        for text in ocr_results
        if normalize(text) and ARABIC_RE.search(text) and not LATIN_RE.search(text)
    ]
    return "\n".join(arabic_lines).strip()


def postprocess_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        return rows

    source_overflow_markers = [
        re.compile(
            r"\s(?:Muhammad|Ahmad|Ali|Hisham|Zayd|Ja['’]far|Abu)\s+(?:ibn|bin)\s+[^\n]{0,35}?\bsaid:\s*",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:So\s+this\s+is|As\s+for\s+what|The\s+Shaykh|It\s+is\s+to\s+be\s+understood)\b",
            re.IGNORECASE,
        ),
    ]
    source_wrap_namey_re = re.compile(r"(\{a\.s\}|\{s\.a\}|\{saws\}|Imam|Prophet|ibn|bint|al-)", re.IGNORECASE)
    source_wrap_sentence_starts = (
        "The ",
        "And ",
        "If ",
        "As ",
        "This ",
        "It ",
        "Since ",
        "Do ",
        "Even ",
        "But ",
        "Thus ",
        "His ",
        "Among ",
        "What ",
        "Then ",
        "In ",
        "A ",
    )
    english_artifact_line_re = re.compile(r"^[\s\W_]*[HADIThadit]{1,8}[\s\W_]*$")

    # 0) Normalize any literal escaped newlines in text fields.
    for row in rows:
        for field in ("english_text", "commentary"):
            value = row.get(field) or ""
            if "\\n" in value:
                row[field] = value.replace("\\n", "\n")

    # 1) Normalize source/commentary split
    for row in rows:
        source = (row.get("source") or "").strip()
        commentary = (row.get("commentary") or "").strip()

        # Move explicit [SOURCE] line from commentary into source.
        if commentary.startswith("[SOURCE]"):
            lines = [line.strip() for line in commentary.splitlines() if line.strip()]
            if lines:
                source_head = lines[0].replace("[SOURCE]", "", 1).strip()
                source = " ".join(part for part in [source, source_head] if part).strip()
                commentary = "\n".join(lines[1:]).strip()

        # Move wrapped source continuations from commentary head into source.
        if commentary:
            lines = [line.strip() for line in commentary.splitlines() if line.strip()]
            moved: list[str] = []
            while lines:
                first = lines[0]
                if first.startswith(source_wrap_sentence_starts):
                    break
                if first.endswith((".", ":", "?", "!", ").", ".”", "\"")):
                    break
                if len(first) > 220:
                    break
                if not source_wrap_namey_re.search(first):
                    break
                moved.append(lines.pop(0))
            if moved:
                source = " ".join([source, *moved]).strip()
                commentary = "\n".join(lines).strip()

        # Move source overflow narrative text back into commentary.
        if source:
            start: int | None = None
            for marker in source_overflow_markers:
                match = marker.search(source)
                if not match:
                    continue
                idx = match.start()
                if idx <= 0:
                    continue
                if start is None or idx < start:
                    start = idx
            if start is not None:
                head = source[:start].strip()
                tail = source[start:].strip()
                if head and tail:
                    source = head
                    commentary = (tail + ("\n" + commentary if commentary else "")).strip()

        row["source"] = source
        row["commentary"] = commentary

    # 2) Remove Arabic leakage from commentary
    for row in rows:
        commentary = (row.get("commentary") or "").strip()
        if not commentary:
            continue
        kept: list[str] = []
        for line in commentary.splitlines():
            text = line.strip()
            if not text:
                continue
            if ARABIC_RE.search(text):
                continue
            kept.append(text)
        row["commentary"] = "\n".join(kept).strip()

    # 3) Remove tiny HADITH marker fragments from english_text
    for row in rows:
        english = (row.get("english_text") or "").strip()
        if not english:
            continue
        lines = [line.strip() for line in english.splitlines() if line.strip()]
        kept: list[str] = []
        for line in lines:
            if len(line) <= 12 and english_artifact_line_re.match(line):
                continue
            kept.append(line)
        row["english_text"] = "\n".join(kept).strip()

    # 4) Fix wrapped chapter-title spillover from english tail
    by_chapter: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_chapter[row["Chapter Number"]].append(row)

    def is_upper_heading(text: str) -> bool:
        value = text.strip()
        if len(value) < 25:
            return False
        letters = [char for char in value if char.isalpha()]
        if not letters:
            return False
        upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
        return upper_ratio > 0.8

    for chapter_number, chapter_rows in by_chapter.items():
        tails = Counter()
        for row in chapter_rows:
            lines = [line.strip() for line in (row.get("english_text") or "").splitlines() if line.strip()]
            if lines:
                tails[lines[-1]] += 1
        current_title = chapter_rows[0].get("Chapter Title", "")
        if not tails:
            continue

        title_looks_incomplete = bool(
            re.search(r"(?:,\s*$|\b(?:AND|OR|OF|IN|FOR|WITH|SHOULD|WHAT)\s*$)", current_title, re.IGNORECASE)
        )
        default_threshold = max(10, int(len(chapter_rows) * 0.2))
        min_threshold = 2 if title_looks_incomplete else default_threshold

        for tail, count in tails.most_common():
            if count < min_threshold:
                break
            if not is_upper_heading(tail):
                continue
            if tail in current_title:
                continue

            new_title = f"{current_title} {tail}".strip()
            for row in chapter_rows:
                row["Chapter Title"] = new_title
                lines = [line.strip() for line in (row.get("english_text") or "").splitlines() if line.strip()]
                if lines and lines[-1] == tail:
                    lines = lines[:-1]
                    row["english_text"] = "\n".join(lines).strip()
            current_title = new_title

        # Remove chapter-title fragments leaking at both head and tail.
        for row in chapter_rows:
            lines = [line.strip() for line in (row.get("english_text") or "").splitlines() if line.strip()]
            while lines and is_upper_heading(lines[0]) and lines[0] in current_title and lines[0] != current_title:
                lines = lines[1:]
            while lines and is_upper_heading(lines[-1]) and lines[-1] in current_title and lines[-1] != current_title:
                lines = lines[:-1]
            row["english_text"] = "\n".join(lines).strip()

            # Remove chapter-title fragments that leaked into commentary blocks,
            # usually from page header carry-over during extraction.
            commentary_lines = [
                line.strip() for line in (row.get("commentary") or "").splitlines() if line.strip()
            ]
            commentary_lines = [
                line
                for line in commentary_lines
                if not (is_upper_heading(line) and line in current_title and line != current_title)
            ]
            row["commentary"] = "\n".join(commentary_lines).strip()

    return rows


def run(
    pdf_path: Path,
    source_csv: Path,
    preview_csv: Path,
    compare_csv: Path,
    hadith_start: int,
    hadith_end: int,
) -> None:
    with source_csv.open(newline="", encoding="utf-8") as f:
        original_rows = list(csv.DictReader(f))
        fieldnames = list(original_rows[0].keys()) if original_rows else []

    doc = fitz.open(pdf_path)
    markers = find_markers(doc)
    ocr_cache: dict[int, str] = {}

    compare_rows: list[dict[str, str]] = []
    preview_rows: list[dict[str, str]] = []

    for original in original_rows:
        hadith_id = (original.get("Hadith Number") or "").strip()
        base_hadith_number = parse_base_hadith_number(hadith_id)
        if base_hadith_number is None:
            continue

        if not (hadith_start <= base_hadith_number <= hadith_end):
            continue

        if base_hadith_number not in ocr_cache:
            boxes = arabic_boxes_for_hadith(doc, markers, base_hadith_number)
            ocr_parts: list[str] = []
            for page_idx, rect in boxes:
                part = ocr_crop(doc[page_idx], rect)
                if part:
                    ocr_parts.append(part)
            ocr_cache[base_hadith_number] = "\n".join(part for part in ocr_parts if part).strip()
        ocr_arabic = ocr_cache.get(base_hadith_number, "")

        preview_row = dict(original)
        if ocr_arabic:
            preview_row["arabic_text"] = ocr_arabic
        preview_rows.append(preview_row)

        compare_rows.append(
            {
                "Hadith Number": hadith_id,
                "page_start": original["page_start"],
                "page_end": original["page_end"],
                "original_arabic_text": original["arabic_text"],
                "ocr_arabic_text": ocr_arabic,
            }
        )

    preview_rows = postprocess_rows(preview_rows)

    preview_csv.parent.mkdir(parents=True, exist_ok=True)
    compare_csv.parent.mkdir(parents=True, exist_ok=True)

    with preview_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(preview_rows)

    with compare_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Hadith Number",
                "page_start",
                "page_end",
                "original_arabic_text",
                "ocr_arabic_text",
            ],
        )
        writer.writeheader()
        writer.writerows(compare_rows)

    doc.close()

    print(
        f"Wrote OCR preview rows: {len(preview_rows)} -> {preview_csv}\n"
        f"Wrote comparison rows: {len(compare_rows)} -> {compare_csv}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OCR Arabic preview for a hadith subset.")
    parser.add_argument("--pdf", required=True, help="Input PDF path.")
    parser.add_argument("--source-csv", required=True, help="Existing parsed CSV path.")
    parser.add_argument("--preview-csv", required=True, help="Output preview CSV path.")
    parser.add_argument("--compare-csv", required=True, help="Output comparison CSV path.")
    parser.add_argument("--hadith-start", type=int, default=1)
    parser.add_argument("--hadith-end", type=int, default=10)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run(
        pdf_path=Path(args.pdf).expanduser().resolve(),
        source_csv=Path(args.source_csv).expanduser().resolve(),
        preview_csv=Path(args.preview_csv).expanduser().resolve(),
        compare_csv=Path(args.compare_csv).expanduser().resolve(),
        hadith_start=args.hadith_start,
        hadith_end=args.hadith_end,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
