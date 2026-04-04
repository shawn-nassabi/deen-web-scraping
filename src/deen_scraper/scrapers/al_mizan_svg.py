#!/usr/bin/env python3
"""Scrape Al-Mizan volume routes backed by SVG pages into chapter-content CSVs."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests


APP_URL = "https://almizan.org"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "datasets" / "al-mizan" / "svg_scraped"
SVG_BASE_URL = "https://static.almizan.org"
ROUTE_RE = re.compile(r"/vol/(\d+)/(\d+)-(\d+)$")
MATRIX_RE = re.compile(r"matrix\(\s*([^)]+)\)")
SCRIPT_RE = re.compile(r'<script[^>]+src="([^"]*index-[^"]+\.js)"')

CONTENT_COLUMNS = [
    "chapter_number",
    "chapter_title_en",
    "chapter_title_ar",
    "verse_from",
    "verse_to",
    "volume_number",
    "segment_page_from",
    "segment_page_to",
    "extracted_page_from",
    "extracted_page_to",
    "extracted_page_count",
    "source_route_url",
    "text",
]

PAGE_COLUMNS = [
    "volume_number",
    "page_number",
    "chapter_number",
    "chapter_title_en",
    "chapter_title_ar",
    "verse_from",
    "verse_to",
    "source_route_url",
    "svg_url",
    "text",
]

PUNCTUATION_NO_SPACE_BEFORE = set(".,;:!?)]}”’")


@dataclass(frozen=True)
class Segment:
    chapter_number: int
    chapter_title_en: str
    chapter_title_ar: str
    verse_from: int
    verse_to: int
    volume_number: int
    page_from: int
    page_to: int


@dataclass(frozen=True)
class Glyph:
    x: float
    y: float
    scale: float
    char: str


class AlmizanSvgScraper:
    def __init__(self, session: requests.Session | None = None, request_delay: float = 0.0) -> None:
        self.session = session or requests.Session()
        self.request_delay = request_delay
        self._segments_cache: list[Segment] | None = None

    def _sleep(self) -> None:
        if self.request_delay > 0:
            time.sleep(self.request_delay)

    def _fetch_text(self, url: str) -> str:
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        self._sleep()
        return response.text

    def _extract_array_literal(self, js_text: str, marker: str) -> str:
        marker_index = js_text.find(marker)
        if marker_index < 0:
            raise ValueError(f"Marker not found in JS bundle: {marker}")

        start = js_text.find("[", marker_index)
        if start < 0:
            raise ValueError(f"Array start not found after marker: {marker}")

        depth = 0
        in_string: str | None = None
        escaped = False

        for idx in range(start, len(js_text)):
            ch = js_text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == in_string:
                    in_string = None
                continue

            if ch in {"'", '"', "`"}:
                in_string = ch
                continue

            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return js_text[start : idx + 1]

        raise ValueError(f"Unbalanced array literal for marker: {marker}")

    def _eval_js_arrays(self, x5_literal: str, c5_literal: str) -> dict[str, Any]:
        node_code = (
            f"const x5={x5_literal};\n"
            f"const C5={c5_literal};\n"
            "process.stdout.write(JSON.stringify({x5, C5}));\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(node_code)
            tmp_path = Path(tmp.name)

        try:
            result = subprocess.run(
                ["node", str(tmp_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        return json.loads(result.stdout)

    def _load_segments(self) -> list[Segment]:
        if self._segments_cache is not None:
            return self._segments_cache

        app_html = self._fetch_text(APP_URL)
        script_match = SCRIPT_RE.search(app_html)
        if not script_match:
            raise RuntimeError("Could not find app JS bundle URL in almizan.org HTML")

        script_url = urljoin(APP_URL, script_match.group(1))
        js_text = self._fetch_text(script_url)

        x5_literal = self._extract_array_literal(js_text, "const x5=")
        c5_literal = self._extract_array_literal(js_text, "const C5=")
        parsed = self._eval_js_arrays(x5_literal, c5_literal)

        segments: list[Segment] = []
        for chapter in parsed["C5"]:
            chapter_num = int(chapter["num"])
            chapter_title_en = chapter["title"]["en"]
            chapter_title_ar = chapter["title"].get("ar", "")
            for verse_set in chapter.get("verseSets", []):
                segments.append(
                    Segment(
                        chapter_number=chapter_num,
                        chapter_title_en=chapter_title_en,
                        chapter_title_ar=chapter_title_ar,
                        verse_from=int(verse_set["verseFrom"]),
                        verse_to=int(verse_set["verseTo"]),
                        volume_number=int(verse_set["volume"]),
                        page_from=int(verse_set["pageFrom"]),
                        page_to=int(verse_set["pageTo"]),
                    )
                )

        self._segments_cache = segments
        return segments

    def _parse_route(self, route_url: str) -> tuple[int, int, int]:
        path = urlparse(route_url).path.rstrip("/")
        match = ROUTE_RE.search(path)
        if not match:
            raise ValueError(f"Unsupported route format (expected /vol/<num>/<from>-<to>): {route_url}")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    def _extract_text_from_svg(self, svg_text: str) -> str:
        root = ET.fromstring(svg_text)
        use_nodes = root.findall(".//{http://www.w3.org/2000/svg}use")

        id_to_chars: dict[str, Counter[str]] = defaultdict(Counter)
        xlink_href = "{http://www.w3.org/1999/xlink}href"
        for node in use_nodes:
            glyph_id = node.attrib.get(xlink_href, node.attrib.get("href", ""))
            glyph_id = glyph_id[1:] if glyph_id.startswith("#") else glyph_id
            data_text = node.attrib.get("data-text")
            if glyph_id and data_text:
                id_to_chars[glyph_id][data_text] += 1

        inferred_char: dict[str, str] = {}
        for glyph_id, counter in id_to_chars.items():
            top_char, _ = counter.most_common(1)[0]
            inferred_char[glyph_id] = top_char

        glyphs: list[Glyph] = []
        for node in use_nodes:
            transform = node.attrib.get("transform", "")
            matrix_match = MATRIX_RE.search(transform)
            if not matrix_match:
                continue

            parts = matrix_match.group(1).replace(",", " ").split()
            if len(parts) != 6:
                continue

            try:
                scale = abs(float(parts[0]))
                x = float(parts[4])
                y = float(parts[5])
            except ValueError:
                continue

            glyph_id = node.attrib.get(xlink_href, node.attrib.get("href", ""))
            glyph_id = glyph_id[1:] if glyph_id.startswith("#") else glyph_id
            char = node.attrib.get("data-text")
            if not char:
                char = inferred_char.get(glyph_id, " ")
            glyphs.append(Glyph(x=x, y=y, scale=scale, char=char))

        if not glyphs:
            return ""

        glyphs.sort(key=lambda item: (item.y, item.x))

        lines: list[list[Glyph]] = []
        current: list[Glyph] = []
        current_y: float | None = None
        current_scale = 11.0
        y_tolerance = 0.9

        for glyph in glyphs:
            if current_y is None:
                current = [glyph]
                current_y = glyph.y
                current_scale = glyph.scale
                continue

            if abs(glyph.y - current_y) <= y_tolerance:
                current.append(glyph)
            else:
                lines.append(sorted(current, key=lambda item: item.x))
                current = [glyph]
                current_y = glyph.y
                current_scale = glyph.scale
                y_tolerance = max(0.9, current_scale * 0.08)

        if current:
            lines.append(sorted(current, key=lambda item: item.x))

        line_records: list[tuple[float, float, str]] = []
        for glyph_line in lines:
            if not glyph_line:
                continue

            text_parts: list[str] = []
            prev_x: float | None = None
            prev_scale: float = glyph_line[0].scale

            for glyph in glyph_line:
                ch = glyph.char
                if prev_x is not None:
                    gap = glyph.x - prev_x
                    if gap > max(14.0, prev_scale * 1.6):
                        if (
                            text_parts
                            and text_parts[-1] != " "
                            and ch != " "
                            and ch not in PUNCTUATION_NO_SPACE_BEFORE
                        ):
                            text_parts.append(" ")
                text_parts.append(ch)
                prev_x = glyph.x
                prev_scale = glyph.scale

            line_text = "".join(text_parts)
            line_text = re.sub(r"\s+", " ", line_text).strip()
            line_text = re.sub(r"\s+([,.;:!?])", r"\1", line_text)
            if line_text:
                avg_scale = sum(item.scale for item in glyph_line) / len(glyph_line)
                line_records.append((glyph_line[0].y, avg_scale, line_text))

        if not line_records:
            return ""

        output_lines: list[str] = []
        prev_y: float | None = None
        prev_scale = 11.0
        for y, scale, text in line_records:
            if prev_y is not None:
                gap = y - prev_y
                if gap > max(17.0, prev_scale * 1.9):
                    output_lines.append("")
            output_lines.append(text)
            prev_y = y
            prev_scale = scale

        text = "\n".join(output_lines).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _fetch_page_text(self, volume_number: int, page_number: int) -> tuple[str, str]:
        svg_url = f"{SVG_BASE_URL}/{volume_number}_{page_number}.svg"
        svg_text = self._fetch_text(svg_url)
        return svg_url, self._extract_text_from_svg(svg_text)

    def scrape_route(self, route_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        volume_number, route_from, route_to = self._parse_route(route_url)
        all_segments = self._load_segments()

        relevant_segments = [
            segment
            for segment in all_segments
            if segment.volume_number == volume_number
            and segment.page_to >= route_from
            and segment.page_from <= route_to
        ]
        relevant_segments.sort(key=lambda item: (item.page_from, item.chapter_number, item.verse_from))

        content_rows: list[dict[str, Any]] = []
        page_rows: list[dict[str, Any]] = []

        for segment in relevant_segments:
            page_start = max(segment.page_from, route_from)
            page_end = min(segment.page_to, route_to)
            if page_start > page_end:
                continue

            page_texts: list[str] = []
            for page_number in range(page_start, page_end + 1):
                svg_url, text = self._fetch_page_text(volume_number, page_number)
                page_rows.append(
                    {
                        "volume_number": volume_number,
                        "page_number": page_number,
                        "chapter_number": segment.chapter_number,
                        "chapter_title_en": segment.chapter_title_en,
                        "chapter_title_ar": segment.chapter_title_ar,
                        "verse_from": segment.verse_from,
                        "verse_to": segment.verse_to,
                        "source_route_url": route_url,
                        "svg_url": svg_url,
                        "text": text,
                    }
                )
                page_texts.append(text)

            merged_text = "\n\n".join(part for part in page_texts if part.strip()).strip()
            content_rows.append(
                {
                    "chapter_number": segment.chapter_number,
                    "chapter_title_en": segment.chapter_title_en,
                    "chapter_title_ar": segment.chapter_title_ar,
                    "verse_from": segment.verse_from,
                    "verse_to": segment.verse_to,
                    "volume_number": segment.volume_number,
                    "segment_page_from": segment.page_from,
                    "segment_page_to": segment.page_to,
                    "extracted_page_from": page_start,
                    "extracted_page_to": page_end,
                    "extracted_page_count": (page_end - page_start + 1),
                    "source_route_url": route_url,
                    "text": merged_text,
                }
            )

        return content_rows, page_rows


def route_to_slug(route_url: str) -> str:
    path = urlparse(route_url).path.strip("/")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path)


def write_csv(rows: list[dict[str, Any]], columns: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Al-Mizan SVG-backed volume routes into chapter-content CSV files."
    )
    parser.add_argument(
        "--url",
        nargs="+",
        required=True,
        help="One or more Al-Mizan routes, e.g. https://almizan.org/vol/34/1-237",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for output CSVs (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Optional delay (seconds) between HTTP requests.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    scraper = AlmizanSvgScraper(request_delay=args.delay)

    for route_url in args.url:
        content_rows, page_rows = scraper.scrape_route(route_url)
        slug = route_to_slug(route_url)
        content_path = output_dir / f"{slug}_chapter_contents.csv"
        pages_path = output_dir / f"{slug}_pages.csv"
        write_csv(content_rows, CONTENT_COLUMNS, content_path)
        write_csv(page_rows, PAGE_COLUMNS, pages_path)

        print(
            f"{route_url}: segments={len(content_rows)}, pages={len(page_rows)}, "
            f"content_csv={content_path}, pages_csv={pages_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
