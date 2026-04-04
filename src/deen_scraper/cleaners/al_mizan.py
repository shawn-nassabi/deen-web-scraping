"""Al-Mizan PDF Cleaner
Extracts text from PDFs, parses metadata (title, chapters, verses, translator, volume),
and chunks the commentary text for vector database storage.

Uses the shared chunking utilities from deen_scraper.chunking.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from deen_scraper.chunking.splitter import split_recursive
from deen_scraper.config import AL_MIZAN_PDF_DIR, CHUNK_FILES

try:
    import fitz  # PyMuPDF
except ImportError:
    raise ImportError("PyMuPDF not installed. Install with: pip install PyMuPDF")

INPUT_DIR = AL_MIZAN_PDF_DIR
OUTPUT_JSONL = CHUNK_FILES.get("al-mizan", Path("data/chunks/al_mizan_cleaned_chunks.jsonl"))


def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF file."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page_num in range(len(doc)):
            page = doc[page_num]
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""


def parse_volume_from_filename(filename):
    """Extract volume number from filename."""
    patterns = [
        r"[vV]olume\s*(\d+)", r"[vV]ol\.?\s*(\d+)",
        r"[vV]\.?\s*(\d+)", r"vol\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
    return ""


def parse_metadata_from_text(text, filename):
    """Parse metadata from PDF text."""
    metadata = {
        "title": "",
        "chapters": [],
        "verses": [],
        "translator": "",
        "volume": parse_volume_from_filename(filename),
    }

    lines = text.split("\n")[:20]
    for line in lines:
        line = line.strip()
        if 10 < len(line) < 200 and not metadata["title"]:
            metadata["title"] = line
            break

    chapter_patterns = [
        r"[Cc]hapter\s+(\d+)",
        r"[Ss]urah\s+([A-Za-z\s]+)",
        r"[Cc]hapter:\s*([A-Za-z\s]+)",
    ]
    for pattern in chapter_patterns:
        matches = re.findall(pattern, text[:5000])
        if matches:
            metadata["chapters"] = list(set(matches))
            break

    verse_patterns = [
        r"(\d+):(\d+)(?:-(\d+))?",
        r"[Vv]erse\s+(\d+)",
        r"[Aa]yah\s+(\d+)",
    ]
    verses = []
    for pattern in verse_patterns:
        matches = re.findall(pattern, text[:10000])
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    if len(match) == 3:
                        verses.append(f"{match[0]}:{match[1]}-{match[2]}")
                    elif len(match) == 2:
                        verses.append(f"{match[0]}:{match[1]}")
                else:
                    verses.append(str(match))
    metadata["verses"] = list(set(verses))[:50]

    translator_patterns = [
        r"[Tt]ranslated\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"[Tt]ranslator[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+[Tt]ranslation",
    ]
    for pattern in translator_patterns:
        match = re.search(pattern, text[:3000])
        if match:
            metadata["translator"] = match.group(1)
            break

    return metadata


def extract_commentary_sections(text):
    """Extract commentary sections from text."""
    sections = []
    verse_commentary_pattern = r"(\d+:\d+(?:-\d+)?)\s+(.+?)(?=\d+:\d+|$)"
    matches = re.finditer(verse_commentary_pattern, text, re.DOTALL)

    for match in matches:
        verse_ref = match.group(1)
        commentary = match.group(2).strip()
        if len(commentary) > 50:
            sections.append({"verse_reference": verse_ref, "commentary": commentary})

    if not sections:
        sections.append({"verse_reference": "", "commentary": text})

    return sections


def build_chunks(pdf_path, metadata, commentary_sections, base_chunk_idx):
    """Build chunk records with metadata."""
    all_chunks = []
    chunk_counter = base_chunk_idx

    for section in commentary_sections:
        commentary_text = section["commentary"]
        verse_ref = section["verse_reference"]

        if len(commentary_text.split()) > 400:
            chunks = split_recursive(commentary_text)
        else:
            chunks = [commentary_text]

        for chunk in chunks:
            chunk_metadata = {
                "sect": "shia",
                "collection": "al-mizan",
                "title": metadata["title"],
                "volume": metadata["volume"],
                "chapters": ", ".join(metadata["chapters"]) if metadata["chapters"] else "",
                "verses": ", ".join(metadata["verses"]) if metadata["verses"] else "",
                "verse_reference": verse_ref,
                "translator": metadata["translator"],
                "lang": "en",
                "chunk_id": f"al_mizan_{chunk_counter}",
                "text_chunk": chunk.strip(),
            }
            all_chunks.append(chunk_metadata)
            chunk_counter += 1

    return all_chunks, chunk_counter


def process_al_mizan_pdfs(input_dir=INPUT_DIR):
    """Main processing pipeline."""
    pdf_dir = Path(input_dir)
    if not pdf_dir.exists():
        print(f"Directory not found: {input_dir}")
        return

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {input_dir}")
        return

    print(f"Processing {len(pdf_files)} PDF file(s)...")

    all_chunks = []
    global_chunk_idx = 0

    for pdf_file in pdf_files:
        print(f"\nProcessing {pdf_file.name}...")

        text = extract_text_from_pdf(pdf_file)
        if not text:
            print(f"  No text extracted from {pdf_file.name}, skipping...")
            continue

        metadata = parse_metadata_from_text(text, pdf_file.name)
        print(f"  Volume: {metadata['volume']}")
        print(f"  Title: {metadata['title'][:50]}..." if len(metadata['title']) > 50 else f"  Title: {metadata['title']}")
        print(f"  Translator: {metadata['translator']}")
        print(f"  Chapters: {len(metadata['chapters'])}")
        print(f"  Verses: {len(metadata['verses'])}")

        commentary_sections = extract_commentary_sections(text)
        print(f"  Commentary sections: {len(commentary_sections)}")

        chunks, new_chunk_idx = build_chunks(
            pdf_file, metadata, commentary_sections, global_chunk_idx
        )
        all_chunks.extend(chunks)
        global_chunk_idx = new_chunk_idx

        print(f"  Generated {len(chunks)} chunks")

    output_path = Path(OUTPUT_JSONL)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"\nDone! {len(all_chunks)} chunks saved to:\n   {OUTPUT_JSONL}")
    return all_chunks


if __name__ == "__main__":
    process_al_mizan_pdfs()
