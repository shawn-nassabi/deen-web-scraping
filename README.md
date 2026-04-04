# Deen Web Scraping & Indexing Pipeline

> An end-to-end pipeline for scraping, parsing, cleaning, chunking, and vector-indexing Islamic hadith collections — both **Shia** and **Sunni** — into Pinecone vector databases for semantic search.

---

## Quick Start

```bash
# 1. Set up
python -m pip install -e ".[dev]"
cp .env.example .env   # then fill in your API keys

# 2. Create vector indexes (one-time)
python -m deen_scraper.indexing.index_setup

# 3. Clean, chunk, and index (example: al-Faqih)
python -m deen_scraper.cleaners.faqih              # CSV -> JSONL chunks
python -m deen_scraper.indexing.dense_indexer --collection man-la-yahduruhu-al-faqih   # JSONL -> Pinecone dense
python -m deen_scraper.indexing.sparse_indexer --collection man-la-yahduruhu-al-faqih  # JSONL -> Pinecone sparse
```

---

## Architecture Overview

```
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
 │ SCRAPER  │──▶│  PARSER  │──▶│ CLEANER  │──▶│ CHUNKER  │──▶│  INDEXER │
 └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
  Web pages       PDF->CSV       CSV->JSONL    Text         Dense + Sparse
  PDF downloads   OCR fix                                          Pinecone
```

| Stage | What it does | Key modules |
|-------|-------------|-------------|
| **Scrape** | Download PDFs or scrape web pages | `deen_scraper/scrapers/` |
| **Parse** | Convert raw formats to structured CSV | `deen_scraper/parsers/` |
| **OCR** | Enhance Arabic text via Apple Vision OCR | `deen_scraper/ocr/` |
| **Clean** | Normalise, merge fields, chunk text | `deen_scraper/cleaners/` |
| **Index** | Embed + upsert to Pinecone | `deen_scraper/indexing/` |

---

## Directory Structure

```
deen-web-scraping/
│
├── src/deen_scraper/          # ★ ALL production code lives here
│   ├── config.py              # Central config: paths, constants, collection metadata
│   │
│   ├── scrapers/              # Data acquisition (HTTP)
│   │   ├── al_mizan_web.py       # Download Al-Mizan PDFs from al-mizan.org
│   │   ├── al_mizan_svg.py       # Scrape SVG-backed volume routes (almizan.org/vol/N/…)
│   │   └── sunnah_scraper.py     # Scrape sunnah.com for Sunni collections
│   │
│   ├── parsers/               # Raw format -> structured CSV
│   │   ├── pdf_hadith_parser.py  # Unified PDF->CSV parser (Faqih + Tahdhib)
│   │   ├── al_mizan_pdf_parser.py  # Al-Mizan PDF->CSV (vol 1/2 format)
│   │   └── al_mizan_pdf_parser_v3.py  # Al-Mizan PDF->CSV (vol 3 format)
│   │
│   ├── ocr/                   # Apple Vision OCR for Arabic text
│   │   ├── core.py               # Shared OCR utilities (regex, LineBox, Marker, ocr_crop, etc.)
│   │   ├── faqih_ocr.py          # OCR for Man La Yahduruhu al-Faqih volumes
│   │   ├── tahdhib_ocr.py         # OCR for Tahdhib al-Ahkam (preview/compare/patch)
│   │   ├── apply_patches.py      # Apply OCR preview patches to main CSV
│   │   ├── fix_arabic_shift.py   # Fix 1-position shift in Faqih OCR results
│   │   └── handle_subsections.py  # Handle hadith 235 split subsections (Tahdhib vol 3)
│   │
│   ├── cleaners/              # CSV cleaning + chunking -> JSONL
│   │   ├── base.py               # Shared: chunk_paragraphs(), extract_topic_tags(), etc.
│   │   ├── al_kafi.py            # Al-Kafi cleaner
│   │   ├── al_mizan.py           # Al-Mizan PDF->JSONL cleaner
│   │   ├── faqih.py              # Man La Yahduruhu al-Faqih cleaner
│   │   ├── tahdhib.py             # Tahdhib al-Ahkam cleaner
│   │   ├── nahjul_balagha.py     # Nahj al-Balagha cleaner
│   │   ├── sunni.py              # ALL 5 Sunni collections (unified)
│   │   └── clean_commentary.py   # Post-process: strip Arabic from commentary field
│   │
│   ├── chunking/              # Text splitting strategies
│   │   └── splitter.py           # paragraph-aware + RecursiveCharacterTextSplitter
│   │
│   ├── indexing/              # Pinecone vector database operations
│   │   ├── dense_indexer.py      # Unified dense indexer (SentenceTransformer -> Pinecone)
│   │   ├── sparse_indexer.py     # Unified sparse indexer (TF-IDF -> Pinecone)
│   │   └── index_setup.py        # Create dense & sparse Pinecone indexes
│   │
│   └── utils/
│       └── text.py               # compress_text(), normalize_text(), ISLAMIC_TERMS_MAP
│
├── data/                      # ★ ALL data files (git-ignored after initial add)
│   ├── raw/                   # Original source files — do NOT modify
│   │   ├── shia/
│   │   │   ├── alkafi/
│   │   │   ├── nahjul_balagha/
│   │   │   ├── man-la-yahduruhu-al-faqih/{csv,pdfs}/
│   │   │   ├── tahdhib-al-ahkam/{csv,pdfs}/
│   │   │   └── al-mizan/{pdfs,svg_scraped}/
│   │   └── sunni/             # 5 CSVs from sunnah.com
│   ├── processed/             # Cleaned/enhanced CSVs (post-OCR)
│   └── chunks/                # Final JSONL files ready for indexing
│       ├── *.jsonl            # Per-collection chunk files
│       └── sunni/             # Sunni collection chunk files
│
├── docs/                      # Per-collection documentation
│   ├── al-mizan.md
│   ├── man-la-yahduruhu-al-faqih.md
│   └── tahdhib-al-ahkam.md    # Includes known pitfalls & handoff notes
│
├── scripts/                   # One-off convenience wrappers
│   └── run_faqih_ocr_all_volumes.sh
│
├── notebooks/                 # Exploratory Jupyter notebooks (ephemeral)
│
├── tests/
│   ├── __init__.py
│   └── ...
│
├── pyproject.toml             # Project deps, install entry points
├── .env.example               # Template (cp .env.example .env)
├── .gitignore
└── RESTRUCTURE_PLAN.md        # Full restructuring plan & rationale
```

---

## How to Navigate This Project

### "I want to add a new hadith collection"

1. **Raw data**: Place source files (CSVs, PDFs) under `data/raw/shia/<name>/` or `data/raw/sunni/`
2. **Register it** in `src/deen_scraper/config.py` → add to `COLLECTIONS` dict and `COLLECTION_INPUTS`
3. **Create a cleaner**: Copy any existing `cleaners/*.py` as a template (they all follow the same pattern)
4. **Index it**: The unified indexers already support new collections — just pass `--collection <name>`

### "I want to understand how a collection is processed"

1. Check `docs/<collection>.md` for collection-specific notes
2. Read the corresponding module in `src/deen_scraper/cleaners/` for the cleaning/chunking logic
3. All cleaners read from `data/raw/` and write to `data/chunks/`
4. The `config.py` module maps each collection to its author, sect, and indexer prompt template

### "I have a PDF with new hadith format"

1. Read `src/deen_scraper/parsers/pdf_hadith_parser.py` — it already handles two formats (Faqih `H.N` and Tahdhib `HADITH.N`)
2. Add a new marker regex to `src/deen_scraper/ocr/core.py` → `HADITH_MARKER_RES`
3. Pass `--format <new>` to the parser

### "Arabic OCR quality is bad"

1. See `docs/tahdhib-al-ahkam.md` for detailed OCR quality workflows and known pitfalls
2. Run the OCR pipeline: `python -m deen_scraper.ocr.faqih_ocr --pdf <path> --csv <path>`
3. Review the auto-generated `_ocr_preview.csv` and `_ocr_compare.csv` files
4. Apply patches: `python -m deen_scraper.ocr.apply_patches --preview <path> --main <path>`

### "I want to query the vector database"

- Dense index name: `deen-index-v2` (SentenceTransformer `all-mpnet-base-v2`, 768-dim, cosine)
- Sparse index name: `deen-index-v2-sparse` (TF-IDF, dotproduct)
- Hybrid retrieval: weight dense 70% + sparse 30% (see `.env.example`)
- All upserts use namespace `ns1`

---

## Setting Up

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your Pinecone API key
```

---

## Pipeline Stages (Detailed)

### Stage 1: Scrape

Download raw source materials. Run only when new source data is available.

```bash
# Download Al-Mizan PDFs
python -c "from deen_scraper.scrapers.al_mizan_web import scrape_al_mizan_pdfs; scrape_al_mizan_pdfs()"

# Scrape a specific SVG volume route
python -m deen_scraper.scrapers.al_mizan_svg --url https://almizan.org/vol/34/1-237
```

### Stage 2: Parse

Convert raw files into structured CSV. The `pdf_hadith_parser` handles both Faqih and Tahdhib format PDFs.

```bash
# Parse a Faqih or Tahdhib PDF
python -m deen_scraper.parsers.pdf_hadith_parser --input data/raw/shia/man-la-yahduruhu-al-faqih/pdfs/vol.1.pdf --output-dir data/raw/shia/man-la-yahduruhu-al-faqih/csv

# Parse Al-Mizan PDF
python -c "from deen_scraper.parsers.al_mizan_pdf_parser import main; main()"
```

### Stage 3: OCR (Optional but Recommended)

Enhance Arabic text quality. The parser extracts Arabic from PDFs via PyMuPDF text extraction, but OCR via Apple Vision (macOS-only) produces more accurate results with properly connected Arabic characters.

```bash
# Run OCR for Faqih volumes (macOS, Apple Vision)
python -m deen_scraper.ocr.faqih_ocr --pdf <path> --csv <path> --hadith-start 1 --hadith-end 100

# Review compare output
# <csv>_ocr_compare.csv contains original_arabic_text vs ocr_arabic_text per hadith
```

### Stage 4: Clean & Chunk

Convert CSV -> JSONL chunks. Each collection has its own cleaner.

```bash
python -m deen_scraper.cleaners.al_kafi           # Al-Kafi (8 volumes)
python -m deen_scraper.cleaners.nahjul_balagha    # Nahj al-Balagha
python -m deen_scraper.cleaners.faqih              # Man La Yahduruhu al-Faqih (4 volumes)
python -m deen_scraper.cleaners.tahdhib             # Tahdhib al-Ahkam (3 volumes)
python -m deen_scraper.cleaners.al_mizan            # Al-Mizan (from PDFs)
python -m deen_scraper.cleaners.sunni              # All 5 Sunni collections
```

Output: JSONL files in `data/chunks/` — one per collection.

### Stage 5: Index

Upload chunks to Pinecone as dense + sparse vectors.

```bash
# Create indexes (one-time setup)
python -m deen_scraper.indexing.index_setup

# Dense index (SentenceTransformer embeddings)
python -m deen_scraper.indexing.dense_indexer --collection man-la-yahduruhu-al-faqih

# Sparse index (TF-IDF)
python -m deen_scraper.indexing.sparse_indexer --collection man-la-yahduruhu-al-faqih
```

---

## Collections

| Collection | Sect | Volumes | Raw Input | Format | Status |
|-----------|------|---------|-----------|--------|--------|
| Al-Kafi | Shia | 8 | CSV | `data/raw/shia/alkafi/` | ✅ Cleaned & indexed |
| Nahj al-Balagha | Shia | 1 | CSV | `data/raw/shia/nahjul_balagha/` | ✅ Cleaned & indexed |
| Man La Yahduruhu al-Faqih | Shia | 4 | PDF -> CSV -> OCR | `data/raw/shia/man-la-yahduruhu-al-faqih/` | ✅ Cleaned & indexed |
| Tahdhib al-Ahkam | Shia | 3 | PDF -> CSV -> OCR | `data/raw/shia/tahdhib-al-ahkam/` | ✅ Cleaned & indexed |
| Al-Mizan | Shia | Multiple | PDF + Web | `data/raw/shia/al-mizan/` | Partial |
| Sahih al-Bukhari | Sunni | All books | CSV | `data/raw/sunni/` | ✅ |
| Sahih Muslim | Sunni | All books | CSV | `data/raw/sunni/` | ✅ |
| Jami at-Tirmidhi | Sunni | All books | CSV | `data/raw/sunni/` | ✅ |
| Sunan Abi Dawud | Sunni | All books | CSV | `data/raw/sunni/` | ✅ |
| Sunan an-Nasai | Sunni | All books | CSV | `data/raw/sunni/` | ✅ |

---

## Canonical Chunk Schema

Every JSONL chunk follows this unified schema. Downstream services (APIs, frontend) depend on these fields:

```json
{
  "sect": "shia",
  "collection": "man-la-yahduruhu-al-faqih",
  "author": "Shaykh al-Saduq",
  "volume": "1",
  "book_number": "",
  "book_title": "",
  "chapter_number": "1",
  "chapter_title": "WATER; ITS PURITY AND IMPURITY",
  "hadith_no": "1",
  "lang": "en",
  "grade_en": "",
  "grade_ar": "",
  "text_en": "English hadith text...",
  "text_ar": "Arabic hadith text...",
  "commentary": "Scholar's note...",
  "cross_references": "...",
  "source_scholar": "",
  "page_start": "10",
  "page_end": "12",
  "topic_tags": ["water", "purity"],
  "hadith_id": "shia_man-la-yahduruhu-al-faqih_1_1_1",
  "chunk_id": "faqih_1_1_1_0",
  "text_chunk": "Chunked text for embedding..."
}
```

---

## Configuration

All constants and paths live in `src/deen_scraper/config.py`. Environment variables override defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_SIZE` | `350` | Target chunk size in words |
| `CHUNK_OVERLAP` | `50` | Overlap between adjacent chunks |
| `DENSE_INDEX_NAME` | `deen-index-v2` | Pinecone dense index name |
| `SPARSE_INDEX_NAME` | `deen-index-v2-sparse` | Pinecone sparse index name |
| `PINECONE_NAMESPACE` | `ns1` | Namespace for all upserts |
| `DENSE_RESULT_WEIGHT` | `0.7` | Weight for dense search results |
| `SPARSE_RESULT_WEIGHT` | `0.3` | Weight for sparse search results |
| `EMBEDDING_MODEL` | `sentence-transformers/all-mpnet-base-v2` | Model for dense embeddings |

---

## Known Issues & Pitfalls

### Tahdhib al-Ahkam
- **Vol 2 hadith 931/932 anomaly**: The printed PDF has a duplicate 931 and missing 932. The second 931 should be treated as 932 in dataset logic.
- **Vol 3 hadith 235**: A massive composite hadith was split into 235.1–235.7. Only 235.1 should have Arabic text; 235.2–235.7 must remain empty to avoid duplication.
- **See `docs/tahdhib-al-ahkam.md`** for the complete list of known issues, validation checklists, and the recommended workflow for processing new volumes.

### General
- OCR only works on macOS (Apple Vision framework). On other platforms, fall back to PyMuPDF's built-in text extraction.
- Pinecone upserts are not idempotent — running the indexer on the same chunks twice creates duplicate vectors. Always check before re-indexing.
- The `.env` file contains real secrets and must **never** be committed.

---

## Legacy Code

The original `chunksets/` directory and `datasets/` layout are preserved in git history but are **deprecated**. All new development should use the `src/deen_scraper/` package and `data/` directory structure.

The `notebooks/` directory contains historical exploration notebooks that are no longer maintained.

---

## License

MIT
