# Al-Mizan PDF Scraper and Indexer

This module scrapes PDFs from al-mizan.org, extracts text and metadata, and indexes them to a vector database.

## Overview

The Al-Mizan scraper extracts Tafsir (Quranic commentary) from PDFs with the following metadata:
- **Title**: The title of the tafsir work
- **Chapters**: Chapter references (Surah names/numbers)
- **Verses**: Verse references (e.g., "2:255", "2:255-256")
- **Translator**: Name of the translator
- **Volume**: Volume number

The commentary text is chunked and stored in Pinecone vector database.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure you have a `.env` file with your Pinecone credentials:
```
PINECONE_API_KEY=your_api_key
PINECONE_ENVIRONMENT=your_environment
```

## Usage

### Step 1: Scrape PDFs

Run the scraper to download PDFs from al-mizan.org:

```bash
cd al-mizan
python scraper.py
```

The scraper will:
- Search for PDF links on al-mizan.org
- Download PDFs to `../datasets/al-mizan/pdfs/`
- Skip already downloaded files

You can also specify custom URLs:
```python
from scraper import scrape_al_mizan_pdfs
custom_urls = ["https://www.al-mizan.org/specific-page"]
scrape_al_mizan_pdfs(custom_urls)
```

### Step 2: Extract and Clean PDFs

Process the downloaded PDFs to extract text, parse metadata, and chunk commentary:

```bash
cd chunksets
python al_mizan_cleaner.py
```

This will:
- Extract text from all PDFs in `../datasets/al-mizan/pdfs/`
- Parse metadata (title, chapters, verses, translator, volume)
- Chunk the commentary text
- Save chunks to `../datasets/cleaned_data/al_mizan_cleaned_chunks.jsonl`

### Step 3: Index to Vector Database

Index the cleaned chunks to Pinecone:

```bash
cd chunksets
python index_dense.py
```

When prompted, select "y" for Al-Mizan Tafsir indexing.

## File Structure

```
al-mizan/
├── scraper.py          # Downloads PDFs from al-mizan.org
└── README.md          # This file

chunksets/
├── al_mizan_cleaner.py # Extracts text, parses metadata, chunks commentary
└── index_dense.py     # Indexes chunks to Pinecone (updated to support al-mizan)

datasets/
├── al-mizan/
│   └── pdfs/          # Downloaded PDF files
└── cleaned_data/
    └── al_mizan_cleaned_chunks.jsonl  # Processed chunks
```

## Metadata Structure

Each chunk in the vector database contains:

```json
{
  "sect": "shia",
  "collection": "al-mizan",
  "title": "Tafsir Al-Mizan",
  "volume": "1",
  "chapters": "Chapter 2, Al-Baqarah",
  "verses": "2:255, 2:256",
  "verse_reference": "2:255",
  "translator": "Sayed Saeed Akhtar Rizvi",
  "lang": "en",
  "chunk_id": "al_mizan_0",
  "text_chunk": "Commentary text here..."
}
```

## Notes

- The scraper respects rate limits with 1-second delays between requests
- PDFs are skipped if they already exist locally
- The cleaner uses intelligent parsing to extract metadata, but may need adjustment based on PDF structure
- Commentary is chunked using RecursiveCharacterTextSplitter with 350 word chunks and 50 word overlap

