"""
Al-Mizan PDF Cleaner
Extracts text from PDFs, parses metadata (title, chapters, verses, translator, volume),
and chunks the commentary text for vector database storage.
"""

import re
import json
from pathlib import Path
import pandas as pd
from langchain.text_splitter import RecursiveCharacterTextSplitter

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF not installed. Install with: pip install PyMuPDF")
    raise

INPUT_DIR = "../datasets/al-mizan/pdfs"
OUTPUT_JSONL = "../datasets/cleaned_data/al_mizan_cleaned_chunks.jsonl"
CHUNK_SIZE = 350
CHUNK_OVERLAP = 50

# Text splitter for chunking commentary
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ".", " "]
)


def extract_text_from_pdf(pdf_path):
    """Extract all text from a PDF file"""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page_num in range(len(doc)):
            page = doc[page_num]
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        print(f"❌ Error extracting text from {pdf_path}: {e}")
        return ""


def parse_volume_from_filename(filename):
    """Extract volume number from filename"""
    # Common patterns: "volume1.pdf", "vol1.pdf", "v1.pdf", "Volume_1.pdf"
    patterns = [
        r"[vV]olume\s*(\d+)",
        r"[vV]ol\.?\s*(\d+)",
        r"[vV]\.?\s*(\d+)",
        r"vol\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
    return ""


def parse_metadata_from_text(text, filename):
    """
    Parse metadata from PDF text
    Looks for patterns like:
    - Title
    - Chapter references (e.g., "Chapter 2", "Surah Al-Baqarah")
    - Verse references (e.g., "2:255", "verse 255", "ayah 255")
    - Translator name
    - Volume number
    """
    metadata = {
        "title": "",
        "chapters": [],
        "verses": [],
        "translator": "",
        "volume": parse_volume_from_filename(filename),
    }
    
    # Extract title (usually in first few lines or from PDF metadata)
    lines = text.split("\n")[:20]  # Check first 20 lines
    for line in lines:
        line = line.strip()
        if len(line) > 10 and len(line) < 200:
            # Likely a title if it's a reasonable length
            if not metadata["title"]:
                metadata["title"] = line
            break
    
    # Extract chapter references
    # Patterns: "Chapter 2", "Surah Al-Baqarah", "Chapter: Al-Baqarah"
    chapter_patterns = [
        r"[Cc]hapter\s+(\d+)",
        r"[Ss]urah\s+([A-Za-z\s]+)",
        r"[Cc]hapter:\s*([A-Za-z\s]+)",
    ]
    for pattern in chapter_patterns:
        matches = re.findall(pattern, text[:5000])  # Check first 5000 chars
        if matches:
            metadata["chapters"] = list(set(matches))  # Remove duplicates
            break
    
    # Extract verse references
    # Patterns: "2:255", "verse 255", "ayah 255", "2:255-256"
    verse_patterns = [
        r"(\d+):(\d+)(?:-(\d+))?",  # Quranic format: 2:255 or 2:255-256
        r"[Vv]erse\s+(\d+)",
        r"[Aa]yah\s+(\d+)",
    ]
    verses = []
    for pattern in verse_patterns:
        matches = re.findall(pattern, text[:10000])  # Check first 10000 chars
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    if len(match) == 3:  # Range like 2:255-256
                        verses.append(f"{match[0]}:{match[1]}-{match[2]}")
                    elif len(match) == 2:  # Single verse like 2:255
                        verses.append(f"{match[0]}:{match[1]}")
                else:
                    verses.append(str(match))
    metadata["verses"] = list(set(verses))[:50]  # Limit to 50 unique verses
    
    # Extract translator
    # Common patterns: "Translated by", "Translator:", "by [Name]"
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
    """
    Extract commentary sections from text
    Tries to identify and separate commentary from verse text
    """
    # Common patterns: commentary often follows verse references
    # Split by verse references and treat following text as commentary
    sections = []
    
    # Pattern: verse reference followed by commentary
    verse_commentary_pattern = r"(\d+:\d+(?:-\d+)?)\s+(.+?)(?=\d+:\d+|$)"
    matches = re.finditer(verse_commentary_pattern, text, re.DOTALL)
    
    for match in matches:
        verse_ref = match.group(1)
        commentary = match.group(2).strip()
        if len(commentary) > 50:  # Only include substantial commentary
            sections.append({
                "verse_reference": verse_ref,
                "commentary": commentary
            })
    
    # If no structured sections found, return full text as commentary
    if not sections:
        sections.append({
            "verse_reference": "",
            "commentary": text
        })
    
    return sections


def build_chunks(pdf_path, metadata, commentary_sections, base_chunk_idx):
    """Build chunk records with metadata"""
    all_chunks = []
    chunk_counter = base_chunk_idx
    
    for section in commentary_sections:
        commentary_text = section["commentary"]
        verse_ref = section["verse_reference"]
        
        # Chunk the commentary
        if len(commentary_text.split()) > 400:
            chunks = text_splitter.split_text(commentary_text)
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
                "text_chunk": chunk.strip()
            }
            all_chunks.append(chunk_metadata)
            chunk_counter += 1
    
    return all_chunks, chunk_counter


def process_al_mizan_pdfs(input_dir=INPUT_DIR):
    """Main processing pipeline"""
    pdf_dir = Path(input_dir)
    if not pdf_dir.exists():
        print(f"❌ Directory not found: {input_dir}")
        return
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ No PDF files found in {input_dir}")
        return
    
    print(f"📚 Processing {len(pdf_files)} PDF file(s)...")
    
    all_chunks = []
    global_chunk_idx = 0
    
    for pdf_file in sorted(pdf_files):
        print(f"\n📖 Processing {pdf_file.name}...")
        
        # Extract text
        text = extract_text_from_pdf(pdf_file)
        if not text:
            print(f"⚠️  No text extracted from {pdf_file.name}, skipping...")
            continue
        
        # Parse metadata
        metadata = parse_metadata_from_text(text, pdf_file.name)
        print(f"   Volume: {metadata['volume']}")
        print(f"   Title: {metadata['title'][:50]}..." if len(metadata['title']) > 50 else f"   Title: {metadata['title']}")
        print(f"   Translator: {metadata['translator']}")
        print(f"   Chapters: {len(metadata['chapters'])}")
        print(f"   Verses: {len(metadata['verses'])}")
        
        # Extract commentary sections
        commentary_sections = extract_commentary_sections(text)
        print(f"   Commentary sections: {len(commentary_sections)}")
        
        # Build chunks
        chunks, new_chunk_idx = build_chunks(
            pdf_file, metadata, commentary_sections, global_chunk_idx
        )
        all_chunks.extend(chunks)
        global_chunk_idx = new_chunk_idx
        
        print(f"   ✅ Generated {len(chunks)} chunks")
    
    # Save to JSONL
    output_path = Path(OUTPUT_JSONL)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    
    print(f"\n✅ Done! {len(all_chunks)} chunks saved to:")
    print(f"   {OUTPUT_JSONL}")
    
    return all_chunks


if __name__ == "__main__":
    process_al_mizan_pdfs()

