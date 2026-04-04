#!/usr/bin/env python3
"""
Parse Al-Mizan Volume 3 PDF and extract structured data to CSV
This volume has a different format with "Volume 3: Surah X, Verse Y" headers
"""

import re
import csv
from pathlib import Path
import fitz  # PyMuPDF

PDF_PATH = "../datasets/al-mizan/pdfs/al_mizan_03.pdf"
OUTPUT_CSV = "../datasets/al-mizan/al_mizan_03_parsed.csv"


def contains_arabic(text):
    """Check if text contains Arabic characters"""
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    return bool(arabic_pattern.search(text))


def extract_text_from_pdf(pdf_path):
    """Extract all text from PDF, skipping TOC and everything before Foreword"""
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
        
        # Skip table of contents pages
        if "table of contents" in text.lower():
            continue
        
        pages_text.append((page_num + 1, text))
    
    doc.close()
    return pages_text


def parse_volume_header(line):
    """
    Parse volume header pattern: "Volume 3: Surah Baqarah, Verse 186"
    Returns: (surah_name, verse_number, chapter_number)
    """
    # Pattern: "Volume 3: Surah Baqarah, Verse 186" or "Volume 3: Surah Baqarah, Verse (186)"
    match = re.search(r'Volume\s+3:\s*Surah\s+([^,]+),\s*Verse\s*\(?(\d+)\)?', line, re.IGNORECASE)
    if match:
        surah_name = match.group(1).strip()
        verse_number = match.group(2).strip()
        
        # Try to extract chapter number from surah name or context
        # Common surahs
        surah_to_chapter = {
            "baqarah": 2, "baqara": 2, "fatiha": 1, "fƗtiha": 1, "fatihah": 1,
            "imran": 3, "nisa": 4, "maidah": 5, "an'am": 6, "a'raf": 7,
            "anfal": 8, "tawbah": 9, "yunus": 10, "hud": 11, "yusuf": 12,
            "hijr": 15, "hijr": 15, "dukhan": 44, "mumtahinah": 60, "maidah": 5,
            "hashr": 59
        }
        
        chapter_num = None
        surah_lower = surah_name.lower().strip()
        for surah, ch_num in surah_to_chapter.items():
            if surah in surah_lower:
                chapter_num = ch_num
                break
        
        return surah_name, verse_number, chapter_num
    
    return None, None, None


def parse_pdf_content(pdf_path):
    """Parse PDF and extract structured data"""
    pages_text = extract_text_from_pdf(pdf_path)
    
    # Combine all pages
    full_text = "\n".join([text for _, text in pages_text])
    
    # Split by lines
    lines = full_text.split("\n")
    
    records = []
    current_surah_name = None
    current_chapter_num = None
    current_verse = None
    current_verses_range = None
    current_quran_text = []
    current_commentary = []
    in_commentary = False
    in_quran_text = False
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip navigation/header lines
        if any(skip in line.lower() for skip in ["subject index", "search", "announcements", "feedback", "support this site"]):
            i += 1
            continue
        
        # Check for Volume 3 header pattern
        surah_name, verse_number, chapter_num = parse_volume_header(line)
        
        if surah_name and verse_number:
            # Save previous record if we have data
            if current_commentary or current_quran_text:
                if current_chapter_num and current_verse:
                    # Determine verse range
                    if current_verses_range:
                        verses_covered = f"{current_chapter_num}:{current_verses_range}"
                    else:
                        verses_covered = f"{current_chapter_num}:{current_verse}"
                    
                    records.append({
                        "surah_name": current_surah_name or "",
                        "chapter_number": str(current_chapter_num) if current_chapter_num else "",
                        "title": "",  # Volume 3 doesn't seem to have chapter titles in headers
                        "verses_covered": verses_covered,
                        "english_quran_translation": "\n".join(current_quran_text).strip(),
                        "english_commentary": "\n".join(current_commentary).strip()
                    })
            
            # Update current metadata
            current_surah_name = surah_name
            current_chapter_num = chapter_num
            current_verse = verse_number
            current_verses_range = None  # Reset range
            
            # Reset for new section
            current_quran_text = []
            current_commentary = []
            in_commentary = False
            in_quran_text = False
            i += 1
            continue
        
        # Check for "COMMENTARY" marker
        if "commentary" in line.lower() and len(line.split()) <= 3:
            in_commentary = True
            in_quran_text = False
            i += 1
            continue
        
        # If we're in a section, collect text
        if current_chapter_num is not None and current_verse:
            if not in_commentary:
                # Collect verse translation (English text before COMMENTARY)
                # Skip Arabic text and empty lines
                if line and not contains_arabic(line) and line.strip():
                    # Check if this looks like it might be the start of a new section
                    # (another Volume 3 header would be caught above, so this is safe)
                    current_quran_text.append(line)
                    in_quran_text = True
            elif in_commentary:
                # Collect commentary text
                stripped = line.strip()
                
                # Filter out page numbers - standalone numbers
                if re.match(r'^\d{1,3}$', stripped):
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
                
                # Remove trailing page numbers from very short lines
                if len(stripped.split()) <= 2:
                    if re.search(r'\s+\d{1,3}\s*$', stripped):
                        words = stripped.split()
                        if len(words) == 1 and words[0].isdigit():
                            i += 1
                            continue
                        if len(words) == 2 and words[1].isdigit() and 1 <= int(words[1]) <= 999:
                            if len(words[0]) < 5:  # Very short word + number = likely page number
                                i += 1
                                continue
                
                if line.strip():  # Only add non-empty lines
                    current_commentary.append(line)
        
        i += 1
    
    # Save last record
    if current_commentary or current_quran_text:
        if current_chapter_num and current_verse:
            if current_verses_range:
                verses_covered = f"{current_chapter_num}:{current_verses_range}"
            else:
                verses_covered = f"{current_chapter_num}:{current_verse}"
            
            records.append({
                "surah_name": current_surah_name or "",
                "chapter_number": str(current_chapter_num) if current_chapter_num else "",
                "title": "",
                "verses_covered": verses_covered,
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
        print(f"Verses: {record['verses_covered']}")
        print(f"Translation length: {len(record['english_quran_translation'])} chars")
        print(f"Commentary length: {len(record['english_commentary'])} chars")
    
    save_to_csv(records, OUTPUT_CSV)

