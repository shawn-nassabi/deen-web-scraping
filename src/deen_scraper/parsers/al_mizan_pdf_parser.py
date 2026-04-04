#!/usr/bin/env python3
"""
Parse Al-Mizan PDF and extract structured data to CSV
Extracts: surah name, chapter number, title, verses, english quran translation, commentary
"""

import re
import csv
from pathlib import Path
import fitz  # PyMuPDF

PDF_PATH = "../datasets/al-mizan/pdfs/al_mizan_03.pdf"
OUTPUT_CSV = "../datasets/al-mizan/al_mizan_03_parsed.csv"


def extract_text_from_pdf(pdf_path):
    """Extract all text from PDF with page numbers, skipping TOC pages and everything before Foreword"""
    doc = fitz.open(pdf_path)
    pages_text = []
    found_foreword = False
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        
        # Skip everything before "Foreword"
        if "foreword" in text.lower():
            found_foreword = True
        
        if not found_foreword:
            continue
        
        # Skip table of contents pages (even after foreword)
        if "table of contents" in text.lower():
            continue
        # Skip pages that are clearly TOC (have "Traditions" and "Footnote" but no actual verse content)
        if "traditions" in text.lower() and "footnote" in text.lower() and "commentary" not in text.lower():
            # Double check - if it has actual verse text, it's not TOC
            if not re.search(r'\(\d+\)', text) and "of the people" not in text.lower():
                continue
        pages_text.append((page_num + 1, text))
    doc.close()
    return pages_text


def parse_chapter_header(line):
    """
    Parse chapter header patterns for both formats:
    Format 1 (vol 1):
    - "Chapter 1"
    - "Suratul FƗtiha: The Chapter of the Opening 1:1-5"
    - "1:6-7"
    - "Suratul Baqarah: The Chapter of The Cow 2:1-5"
    - "Chapter Two"
    - "al Baqarah (The Cow)"
    
    Format 2 (vol 2):
    - "Suratul Baqarah: Verses 94 - 99"
    """
    chapter_num = None
    surah_name = None
    chapter_title = None
    verses = None
    
    # Pattern 1: "Chapter 1" or "Chapter 2"
    match = re.match(r"Chapter\s+(\d+)", line, re.IGNORECASE)
    if match:
        chapter_num = int(match.group(1))
    
    # Pattern 2 (Format 2): "Suratul Baqarah: Verses 94 - 99"
    match = re.match(r"Suratul\s+([^:]+):\s*Verses?\s+(\d+)\s*-\s*(\d+)", line, re.IGNORECASE)
    if match:
        surah_name = match.group(1).strip()
        verse_start = match.group(2).strip()
        verse_end = match.group(3).strip()
        # Try to extract chapter number from context or use a default
        # For now, we'll extract it from the surah name or verse numbers
        verses = f"{verse_start}-{verse_end}"
        # We'll need to determine chapter number from context or verse numbers
    
    # Pattern 3: "Suratul FƗtiha: The Chapter of the Opening 1:1-5" (Format 1)
    if not verses:
        match = re.match(r"Suratul\s+([^:]+):\s*The\s+Chapter\s+of\s+(?:The\s+)?([^0-9]+)\s+(\d+:\d+(?:-\d+)?)", line, re.IGNORECASE)
        if match:
            surah_name = match.group(1).strip()
            chapter_title = match.group(2).strip()
            verses = match.group(3).strip()
            if not chapter_num:
                # Extract chapter number from verses (e.g., "1:1-5" -> chapter 1)
                verse_match = re.match(r"(\d+):", verses)
                if verse_match:
                    chapter_num = int(verse_match.group(1))
    
    # Pattern 4: Just verse reference "1:6-7" or "2:1-5"
    if not verses:
        match = re.match(r"^(\d+:\d+(?:-\d+)?)$", line.strip())
        if match:
            verses = match.group(1)
            verse_match = re.match(r"(\d+):", verses)
            if verse_match:
                chapter_num = int(verse_match.group(1))
    
    # Pattern 5: "Chapter Two" or "Chapter Three"
    if not chapter_num:
        match = re.match(r"Chapter\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|Nineteen|Twenty)", line, re.IGNORECASE)
        if match:
            number_words = {
                "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
                "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
                "nineteen": 19, "twenty": 20
            }
            chapter_num = number_words.get(match.group(1).lower())
    
    # Pattern 6: "al Baqarah (The Cow)" - extract surah name and title
    if not surah_name:
        match = re.match(r"al\s+([^(]+)\s*\(([^)]+)\)", line, re.IGNORECASE)
        if match:
            surah_name = match.group(1).strip()
            chapter_title = match.group(2).strip()
    
    return chapter_num, surah_name, chapter_title, verses


def extract_verse_number(text):
    """Extract verse number from text like '(1)' or '(2)' - can be at end or before punctuation"""
    # Try at end first
    match = re.search(r"\((\d+)\)\s*[\.\)]*\s*$", text.strip())
    if match:
        return int(match.group(1))
    # Try anywhere in the line
    match = re.search(r"\((\d+)\)", text)
    if match:
        return int(match.group(1))
    return None

def contains_arabic(text):
    """Check if text contains Arabic characters"""
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    return bool(arabic_pattern.search(text))


def parse_pdf_content(pdf_path):
    """Parse PDF and extract structured data"""
    pages_text = extract_text_from_pdf(pdf_path)
    
    # Combine all pages
    full_text = "\n".join([text for _, text in pages_text])
    
    # Split by lines
    lines = full_text.split("\n")
    
    records = []
    current_chapter_num = None
    current_surah_name = None
    current_chapter_title = None
    current_verses = None
    current_quran_text = []
    current_commentary = []
    in_commentary = False
    in_quran_text = False
    verse_reference_seen = False  # Track if we've seen a verse reference for current section
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip navigation/header lines
        if any(skip in line.lower() for skip in ["subject index", "search", "announcements", "feedback", "support this site"]):
            i += 1
            continue
        
        # Check for chapter header patterns
        chapter_num, surah_name, chapter_title, verses = parse_chapter_header(line)
        
        # Check if this line contains a verse reference pattern (like "2:6-7" or "1:1-5")
        # This could be standalone or at the start/end of a line
        verse_ref_match = re.search(r"^(\d+:\d+(?:-\d+)?)$", line.strip())
        if not verse_ref_match:
            # Also check if verse reference appears at the end of a line (like "Suratul... 1:1-5")
            verse_ref_match = re.search(r"(\d+:\d+(?:-\d+)?)$", line.strip())
        
        if chapter_num is not None or surah_name or verses or verse_ref_match:
            # Save previous record if we have data
            if current_commentary or current_quran_text:
                if current_chapter_num and (current_quran_text or current_commentary):
                    records.append({
                        "surah_name": current_surah_name or "",
                        "chapter_number": str(current_chapter_num) if current_chapter_num else "",
                        "title": current_chapter_title or "",
                        "verses_covered": current_verses or "",
                        "english_quran_translation": "\n".join(current_quran_text).strip(),
                        "english_commentary": "\n".join(current_commentary).strip()
                    })
            
            # Update current metadata
            if chapter_num is not None:
                current_chapter_num = chapter_num
            if surah_name:
                current_surah_name = surah_name
            if chapter_title:
                current_chapter_title = chapter_title
            if verses:
                current_verses = verses
                # Also extract chapter number from verses if not set
                if current_chapter_num is None:
                    verse_match = re.match(r"(\d+):", verses)
                    if verse_match:
                        current_chapter_num = int(verse_match.group(1))
            
            # If we see a verse reference (like "2:6-7"), start collecting Quran text immediately
            if verse_ref_match:
                current_verses = verse_ref_match.group(1)
                verse_match = re.match(r"(\d+):", current_verses)
                if verse_match:
                    current_chapter_num = int(verse_match.group(1))
                # Start collecting Quran text from next line
                in_quran_text = True
                in_commentary = False
                current_quran_text = []
                current_commentary = []
                verse_reference_seen = True
                # Move to next line - don't add the verse reference line itself to Quran text
                i += 1
                continue
            
            # Handle Format 2: "Suratul X: Verses Y - Z" pattern
            if verses and "-" in verses and ":" not in verses:
                # This is Format 2 (e.g., "94-99")
                # Extract chapter number from surah name - common surahs
                surah_to_chapter = {
                    "baqarah": 2, "baqara": 2, "fatiha": 1, "fƗtiha": 1, "fatihah": 1,
                    "imran": 3, "nisa": 4, "maidah": 5, "an'am": 6, "a'raf": 7,
                    "anfal": 8, "tawbah": 9, "yunus": 10, "hud": 11, "yusuf": 12
                }
                if current_surah_name:
                    surah_lower = current_surah_name.lower().strip()
                    for surah, ch_num in surah_to_chapter.items():
                        if surah in surah_lower:
                            current_chapter_num = ch_num
                            break
                
                # For Format 2, we need to wait for English text (skip Arabic)
                # Set flag to start collecting when we see English with verse numbers
                verse_reference_seen = True
                in_quran_text = False  # Don't start yet - wait for English text
                in_commentary = False
                current_quran_text = []
                current_commentary = []
                # Format the verses as "chapter:start-end" if we have chapter_num
                if current_chapter_num:
                    verse_parts = verses.split("-")
                    if len(verse_parts) == 2:
                        current_verses = f"{current_chapter_num}:{verse_parts[0]}-{verse_parts[1]}"
                i += 1
                continue
            
            # Reset for new section
            current_quran_text = []
            current_commentary = []
            in_commentary = False
            in_quran_text = False
            verse_reference_seen = False
            i += 1
            continue
        
        # Check for "COMMENTARY" or "Commentary" marker (both formats)
        if "commentary" in line.lower() and len(line.split()) <= 3:
            in_commentary = True
            in_quran_text = False
            verse_reference_seen = False
            i += 1
            continue
        
        # If we're in a chapter section, collect text
        if current_chapter_num is not None:
            if not in_commentary:
                # Check if this line is the COMMENTARY marker (only check current line, not look ahead)
                if "commentary" in line.lower() and len(line.split()) <= 3 and (in_quran_text or verse_reference_seen):
                    # We've reached the commentary section
                    in_commentary = True
                    in_quran_text = False
                    verse_reference_seen = False
                    i += 1
                    continue
                
                # For Format 2: Skip Arabic text, start collecting when we see English verse translation
                if verse_reference_seen and not in_quran_text:
                    # Skip Arabic lines, empty lines, and section headers
                    if contains_arabic(line) or not line.strip() or "Verses" in line or "Suratul" in line:
                        i += 1
                        continue
                    # Check if this is English verse translation
                    # Look for quoted text (common in translations) or verse numbers
                    has_quotes = '"' in line or "'" in line
                    has_verse_number = extract_verse_number(line) is not None
                    # Also check if line starts with capital letter and has substantial content (likely start of verse)
                    starts_with_capital = line.strip() and line.strip()[0].isupper() if line.strip() else False
                    is_substantial = len(line.strip()) > 15
                    
                    # Start collecting if it looks like verse translation (quotes, verse numbers, or capital start)
                    looks_like_verse = has_verse_number or (has_quotes and is_substantial) or (starts_with_capital and is_substantial and not contains_arabic(line))
                    
                    if looks_like_verse:
                        # This is English verse translation - start collecting from THIS line (don't skip it)
                        in_quran_text = True
                        current_quran_text.append(line)
                        i += 1
                        continue
                    # If it doesn't look like verse text yet, keep waiting (might be transition text)
                    i += 1
                    continue
                
                # If we're collecting English translation, continue collecting all English text until COMMENTARY
                if in_quran_text:
                    # Collect as English translation (everything until COMMENTARY)
                    # Skip Arabic text and empty lines - we only want English
                    if line and not contains_arabic(line) and line.strip():
                        current_quran_text.append(line)
                elif line and not contains_arabic(line) and (extract_verse_number(line) is not None or re.search(r"\(\d+\)", line)):
                    # This line has verse numbers and is English, start collecting translation
                    # This handles Format 1 where verse text appears directly with verse numbers
                    in_quran_text = True
                    verse_reference_seen = True
                    current_quran_text.append(line)
            elif in_commentary and line:
                stripped = line.strip()
                
                # Filter out page numbers - they appear as standalone numbers
                # Skip if line is just a number (1-999, typical page number range)
                if re.match(r'^\d{1,3}$', stripped):
                    # Check if it's a reasonable page number (not a verse number in context)
                    try:
                        num = int(stripped)
                        if 1 <= num <= 999:  # Reasonable page number range
                            i += 1
                            continue
                    except:
                        pass
                
                # Skip lines that are just whitespace and a number
                if re.match(r'^\s*\d{1,3}\s*$', stripped):
                    i += 1
                    continue
                
                # Remove trailing page numbers (numbers at end of very short lines)
                # But preserve numbers that are part of actual text content
                if len(stripped.split()) <= 2:
                    # If line is very short and ends with a number, might be page number
                    if re.search(r'\s+\d{1,3}\s*$', stripped):
                        # Check if it's likely a page number vs part of text
                        # If the line is mostly just a number, skip it
                        words = stripped.split()
                        if len(words) == 1 and words[0].isdigit():
                            i += 1
                            continue
                        # If it's "word number" and number is reasonable page number, might be page number
                        if len(words) == 2 and words[1].isdigit() and 1 <= int(words[1]) <= 999:
                            # Could be page number, but be conservative - only remove if very short
                            if len(words[0]) < 5:  # Very short word + number = likely page number
                                i += 1
                                continue
                
                if line.strip():  # Only add non-empty lines
                    current_commentary.append(line)
        
        i += 1
    
    # Save last record
    if current_commentary or current_quran_text:
        if current_chapter_num and (current_quran_text or current_commentary):
            records.append({
                "surah_name": current_surah_name or "",
                "chapter_number": str(current_chapter_num) if current_chapter_num else "",
                "title": current_chapter_title or "",
                "verses_covered": current_verses or "",
                "english_quran_translation": "\n".join(current_quran_text).strip(),
                "english_commentary": "\n".join(current_commentary).strip()
            })
    
    return records


def save_to_csv(records, output_path):
    """Save records to CSV file"""
    if not records:
        print("❌ No records to save")
        return
    
    fieldnames = ["surah_name", "chapter_number", "title", "verses_covered", 
                  "english_quran_translation", "english_commentary"]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    
    print(f"✅ Saved {len(records)} records to {output_path}")


if __name__ == "__main__":
    print(f"📖 Parsing PDF: {PDF_PATH}")
    records = parse_pdf_content(PDF_PATH)
    print(f"📊 Extracted {len(records)} records")
    
    # Print first few records for debugging
    for i, record in enumerate(records, start=1):
        print(f"\n--- Record {i} ---")
        print(f"Chapter: {record['chapter_number']}")
        print(f"Surah: {record['surah_name']}")
        print(f"Title: {record['title']}")
        print(f"Verses: {record['verses_covered']}")
        print(f"Quran text length: {len(record['english_quran_translation'])} chars")
        print(f"Commentary length: {len(record['english_commentary'])} chars")
    
    save_to_csv(records, OUTPUT_CSV)

