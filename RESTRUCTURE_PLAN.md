# Deen Web Scraping — Project Restructure Plan

> **Branch:** `restructure`
> **Date:** 2026-04-04
> **Status:** Not yet executed — this is the plan of record.

---

## 1. Current-State Diagnosis

### 1.1 High-Level Summary

The project is a **hadith-collection scraping, parsing, cleaning, chunking, and vector-indexing pipeline**.
It serves both **Shia** and **Sunni** collections, processes **PDFs** and **web pages**, cleans raw extractions, chunks text, and upserts dense + sparse vectors to **Pinecone**.

### 1.2 Collections in Scope

| # | Collection | Sect | Source | Format | Volumes |
|---|-----------|------|--------|--------|---------|
| 1 | **Al-Kafi** | Shia | Pre-downloaded CSVs | CSV -> JSONL -> Pinecone | 8 (Vol 1-8 CSVs) |
| 2 | **Nahj al-Balagha** | Shia | Pre-downloaded CSV | CSV -> JSONL -> Pinecone | 1 |
| 3 | **Man La Yahduruhu al-Faqih** | Shia | PDF (4 vols) | PDF -> CSV -> JSONL -> Pinecone | 4 (vol 1-4 CSVs) |
| 4 | **Tahdhib al-Ahkam** | Shia | PDF (3 vols) | PDF -> CSV -> JSONL -> Pinecone | 3 (vol 1-3 CSVs) |
| 5 | **Al-Mizan** (Tafsir) | Shia | Website + PDF | Web scraper + PDF parser -> JSONL -> Pinecone | multiple PDFs + SVG routes |
| 6 | **Sahih al-Bukhari** | Sunni | sunnah.com | Web scraper -> CSV -> Pinecone | all books |
| 7 | **Sahih Muslim** | Sunni | sunnah.com | Web scraper -> CSV -> Pinecone | all books |
| 8 | **Jami at-Tirmidhi** | Sunni | sunnah.com | Web scraper -> CSV -> Pinecone | all books |
| 9 | **Sunan Abi Dawud** | Sunni | sunnah.com | Web scraper -> CSV -> Pinecone | all books |
| 10 | **Sunan an-Nasai** | Sunni | sunnah.com | Web scraper -> CSV -> Pinecone | all books |

### 1.3 Current Directory Layout

```text
deen-web-scraping/
├── .env                          # Secrets (DO NOT COMMIT)
├── .claude/settings.local.json   # Claude Code permission allowlist
├── CLAUDE_HANDOFF_TAHDHIB_AL_AHKAM.md  # Very detailed handoff doc
├── README.md                     # Minimal — 12 lines
├── al-mizan/                     # Al-Mizan scraper & PDF parsers
│   ├── scraper.py                # Download PDFs from al-mizan.org
│   ├── parse_pdf_to_csv.py       # Parse PDF vol 1/2 format -> CSV
│   ├── parse_pdf_to_csv_vol3.py  # Parse PDF vol 3 format -> CSV
│   ├── scrape_volume_svg.py      # Scrape SVG-backed volume routes
│   └── README.md
├── man-la-yahduruhu-al-faqih/    # Faqih + Tahdhib PDF/OCR pipeline
│   ├── pdf_to_hadith_csv.py      # Core PDF->CSV parser (used for both Faqih & Tahdhib)
│   ├── ocr_arabic_preview.py     # OCR Arabic + preview/compare CSVs (Tahdhib variant)
│   ├── ocr_faqih_arabic.py       # OCR Arabic for Faqih volumes (auto-patch)
│   ├── fix_faqih_arabic_shift.py # Fix 1-position shift bug in Faqih OCR
│   ├── clean_commentary_arabic.py # Strip Arabic lines from commentary field
│   ├── apply_ocr_patches.py      # Apply OCR preview patches to main CSV
│   ├── ocr_235_subsections.py    # Handle hadith 235 split subsections
│   └── README.md
├── chunksets/                    # Cleaners, chunkers, and indexers
│   ├── text_prepocesser.py       # Normalize Islamic terms, compress/decompress
│   ├── al_kafi_cleaner.py        # Al-Kafi CSV -> JSONL chunks
│   ├── al_mizan_cleaner.py       # Al-Mizan PDF -> JSONL chunks
│   ├── faqih_cleaner.py          # Faqih CSV -> JSONL chunks
│   ├── tahdib_cleaner.py         # Tahdhib CSV -> JSONL chunks
│   ├── nahjul_balaghah_cleaner.py # Nahj al-Balagha CSV -> JSONL chunks
│   ├── sunni_book_cleaner.py     # Sunni CSVs -> chunk records
│   ├── create_dense_index.py     # Create dense Pinecone index
│   ├── create_sparse_index.py    # Create sparse Pinecone index
│   ├── index_dense.py            # Dense indexer (all collections)
│   ├── index_sparse.py           # Sparse indexer (all collections)
│   ├── index_faqih_dense.py      # Dense indexer (Faqih only)
│   ├── index_faqih_sparse.py     # Sparse indexer (Faqih only)
│   ├── index_tahdib_dense.py     # Dense indexer (Tahdhib only)
│   └── index_tahdib_sparse.py    # Sparse indexer (Tahdhib only)
├── datasets/                     # Raw + cleaned data files
│   ├── alkafi/                   # 8 volume CSVs
│   ├── nahjal_balagha/           # 1 CSV
│   ├── man-la-yahduruhu-al-faqih/ # 4 volume CSVs (+ pdfs subfolder)
│   ├── tahdib-al-ahkam/          # 3 volume CSVs (+ pdfs subfolder)
│   ├── al-mizan/                 # 3 parsed CSVs + svg_scraped/ + pdfs/
│   ├── cleaned_data/             # Output JSONL files
│   └── [5 Sunni collection CSVs] # Loose in datasets root
├── notebooks/                    # Exploratory / legacy
│   ├── scraping.ipynb            # Empty notebook (metadata only)
│   ├── legacy_indexing_script.ipynb  # Historical Pinecone setup
│   └── sunnah-scraper.py         # sunnah.com scraper (used to generate Sunni CSVs)
└── venv/                         # Virtual environment (should be .gitignore'd)
```

### 1.4 Problems Identified

#### A. Duplication & Near-Duplication (Highest Priority)

| Duplicated Code | Files Affected | Issue |
|------------------|---------------|-------|
| `chunk_paragraphs()` — **identical implementation** in 4 files | `al_kafi_cleaner.py`, `faqih_cleaner.py`, `tahdib_cleaner.py`, `nahjul_balaghah_cleaner.py` | Same 21-line function copy-pasted 4x |
| `extract_topic_tags()` — **identical implementation** in 2 files | `faqih_cleaner.py`, `tahdib_cleaner.py` | Copy-pasted |
| Dense indexer logic — **almost identical** across 3 files | `index_dense.py`, `index_faqih_dense.py`, `index_tahdib_dense.py` | Same embedding model, same batching, same metadata compression — only differs in config + text prompt |
| Sparse indexer logic — **almost identical** across 3 files | `index_sparse.py`, `index_faqih_sparse.py`, `index_tahdib_sparse.py` | Same TF-IDF vectorizer, same batching, same metadata — only differs in config |
| OCR pipeline helpers — **duplicated across 5 files** | `ocr_arabic_preview.py`, `ocr_faqih_arabic.py`, `fix_faqih_arabic_shift.py`, `ocr_235_subsections.py`, `apply_ocr_patches.py` | Same `ARABIC_RE`, `LATIN_RE`, `normalize()`, `is_arabic_only()`, `extract_page_lines()`, `avg_token_length()`, `ocr_crop()` |
| Sunni indexing calls — **duplicated in 2 files** | `index_dense.py`, `index_sparse.py` | Both hard-code the same 5 `process_sunni_csv()` calls |
| PDF metadata extraction — **two nearly identical parsers** | `parse_pdf_to_csv.py` vs `parse_pdf_to_csv_vol3.py` | Same structure; `vol3` handles "Volume 3: Surah X, Verse Y" format |

#### B. Architecture & Structural Issues

| Issue | Details |
|-------|---------|
| **No `__init__.py`** in `chunksets/` — imports rely on `sys.path` hacks | `index_faqih_dense.py` and friends use `sys.path.insert(0, ...)` to import from sibling modules |
| **No `requirements.txt` or `pyproject.toml`** | Dependencies are implicit; `venv/` is committed-adjacent |
| **No `.gitignore`** | `venv/`, `.DS_Store`, `.idea/`, `__pycache__/`, `.env`, and large dataset CSVs risk being committed |
| **Hardcoded absolute paths** scattered throughout scripts | e.g. `/Users/tamieemjaffary/Downloads/...`, `/Users/tamieemjaffary/PycharmProjects/...` |
| **Inconsistent schema** across collections | Al-Kafi/Nahj use `hadees_english`/`hadees_arabic`; Faqih/Tahdhib use `english_text`/`arabic_text`; indexers re-map on the fly |
| **Secrets in `.env`** | API keys, database credentials, Redis URLs, and passwords are in the repo root |
| **Monolithic indexers** mix loading, cleaning, chunking, embedding, and uploading | `index_dense.py` is 114 lines doing all five steps; should be decomposable |
| **Collection-specific indexers are copy-paste variations** | `index_faqih_dense.py` (86 lines) and `index_tahdib_dense.py` (94 lines) are ~90% identical |
| **`datasets/` mixes raw inputs and processed outputs** | Raw CSVs, PDFs, and cleaned JSONL all live together under `datasets/` |
| **No CLI entry-point pattern** — every script has its own `if __name__ == "__main__":` with different argparse styles | Makes scripting/automation harder |
| **Legacy `notebooks/` contains dead/exploratory code** | `scraping.ipynb` is essentially empty; `legacy_indexing_script.ipynb` has hardcoded API keys in plaintext |

#### C. Naming & Consistency

| Issue | Examples |
|-------|----------|
| Inconsistent naming convention | `nahjul_balaghah_cleaner.py` (snake_case) vs `al_mizan_cleaner.py` (snake_case) vs naming of directories (`man-la-yahduruhu-al-faqih` with hyphens) |
| Typos | `text_prepocesser.py` should be `text_preprocessor.py` |
| Hardcoded `CHUNK_SIZE = 350 / CHUNK_OVERLAP = 50` duplicated across 6+ files | Should be a single configuration |
| Collections have inconsistent `sect` and `collection` field values | Some use `al-kafi`, others `alkafi`; mixing hyphens and no-hyphens |

---

## 2. Target Architecture

### 2.1 Proposed Directory Structure

```text
deen-web-scraping/
├── .env.example                    # Template with placeholder values (NO real secrets)
├── .gitignore
├── pyproject.toml                  # Dependencies, project metadata, scripts entrypoints
├── README.md                       # Comprehensive project docs
│
├── src/                            # All production code
│   └── deen_scraper/
│       ├── __init__.py
│       ├── config.py               # Central config: paths, chunk params, index names
│       │
│       ├── scrapers/               # Data acquisition (web + PDF download)
│       │   ├── __init__.py
│       │   ├── al_mizan_web.py     # Download PDFs from al-mizan.org
│       │   ├── al_mizan_svg.py     # Scrape SVG-backed volume routes
│       │   └── sunnah_scraper.py   # Scrape sunnah.com for Sunni collections
│       │
│       ├── parsers/                # Raw -> structured CSV conversion
│       │   ├── __init__.py
│       │   ├── pdf_hadith_parser.py    # Unified PDF -> hadith CSV parser (Faqih + Tahdhib)
│       │   ├── al_mizan_pdf_parser.py  # PDF -> CSV for Al-Mizan tafsir
│       │   └── al_mizan_pdf_parser_v3.py # Variant for Vol 3 format
│       │
│       ├── ocr/                    # OCR-based Arabic text enhancement
│       │   ├── __init__.py
│       │   ├── core.py             # Shared: ARABIC_RE, normalize(), extract_page_lines(), ocr_crop(), etc.
│       │   ├── faqih_ocr.py        # OCR for Man La Yahduruhu al-Faqih volumes
│       │   ├── tahdhib_ocr.py      # OCR for Tahdhib al-Ahkam (preview/compare/patch)
│       │   ├── apply_patches.py    # Apply OCR preview patches to any CSV
│       │   ├── fix_arabic_shift.py # Fix 1-position shift in Faqih OCR results
│       │   └── handle_subsections.py # Custom handler for hadith 235 split subsections
│       │
│       ├── cleaners/               # CSV -> cleaned/normalized CSV
│       │   ├── __init__.py
│       │   ├── base.py             # Shared: chunk_paragraphs(), extract_topic_tags(), etc.
│       │   ├── al_kafi.py          # Al-Kafi cleaner
│       │   ├── al_mizan.py         # Al-Mizan cleaner (PDF text extraction -> JSONL)
│       │   ├── faqih.py            # Faqih cleaner
│       │   ├── tahdhib.py          # Tahdhib cleaner
│       │   ├── nahjul_balagha.py   # Nahj al-Balagha cleaner
│       │   ├── sunni.py            # Sunni collection cleaner (all 5 collections)
│       │   └── clean_commentary.py # Post-process script: strip Arabic from commentary
│       │
│       ├── chunking/               # Text splitting -> JSONL
│       │   ├── __init__.py
│       │   └── splitter.py         # Unified chunking: paragraph-aware + RecursiveCharacterTextSplitter fallback
│       │
│       ├── indexing/               # Vector database operations
│       │   ├── __init__.py
│       │   ├── dense_indexer.py    # Unified dense indexer (SentenceTransformer -> Pinecone)
│       │   ├── sparse_indexer.py   # Unified sparse indexer (TF-IDF -> Pinecone)
│       │   └── index_setup.py      # Create dense & sparse Pinecone indexes
│       │
│       └── utils/
│           ├── __init__.py
│           └── text.py             # compress_text(), decompress_text(), normalize_text(), ISLAMIC_TERMS_MAP
│
├── data/                           # All data files (raw inputs + processed outputs)
│   ├── raw/                        # Original, untouched source files
│   │   ├── shia/
│   │   │   ├── alkafi/             # 8 volume CSVs
│   │   │   ├── nahjul_balagha/     # 1 CSV
│   │   │   ├── man-la-yahduruhu-al-faqih/
│   │   │   │   ├── pdfs/           # Original PDFs
│   │   │   │   └── csv/            # Parsed CSVs (one per volume)
│   │   │   ├── tahdhib-al-ahkam/
│   │   │   │   ├── pdfs/           # Original PDFs
│   │   │   │   └── csv/            # Parsed CSVs (one per volume)
│   │   │   └── al-mizan/
│   │   │       ├── pdfs/           # Downloaded PDFs
│   │   │       └── svg_scraped/    # SVG-scraped CSVs
│   │   └── sunni/                  # 5 raw CSVs from sunnah.com scraping
│   │
│   ├── processed/                  # Cleaned/enhanced CSVs (post-OCR, post-cleaning)
│   │   └── [per-collection subdirs]
│   │
│   └── chunks/                     # Final JSONL chunk files ready for indexing
│       ├── alkafi_cleaned_chunks.jsonl
│       ├── nahjul_balagha_cleaned_chunks.jsonl
│       ├── faqih_cleaned_chunks.jsonl
│       ├── tahdhib_al_ahkam_cleaned_chunks.jsonl
│       ├── al_mizan_cleaned_chunks.jsonl
│       └── sunni/
│           ├── sahih_bukhari_chunks.jsonl
│           ├── sahih_muslim_chunks.jsonl
│           ├── tirmidhi_chunks.jsonl
│           ├── ab_dawud_chunks.jsonl
│           └── an_nasai_chunks.jsonl
│
├── notebooks/                      # Exploratory/research notebooks (ephemeral)
│   └── .gitkeep
│
├── scripts/                        # One-off convenience / CLI entry points
│   ├── scrape_sunnah.py            # Wrapper to sunnah scraper
│   ├── scrape_al_mizan.py          # Wrapper to al-mizan scraper
│   ├── parse_pdf.py                # CLI: PDF -> CSV
│   ├── ocr_pass.py                 # CLI: OCR Arabic enhancement
│   ├── clean_collection.py         # CLI: CSV -> cleaned JSONL
│   └── index_collection.py         # CLI: JSONL -> Pinecone
│
├── docs/                           # Documentation
│   ├── al-mizan.md
│   ├── al-kafi.md
│   ├── nahjul-balagha.md
│   ├── man-la-yahduruhu-al-faqih.md
│   ├── tahdhib-al-ahkam.md
│   └── sunni-collections.md
│
└── tests/                          # Test suite
    ├── __init__.py
    ├── test_parsers.py
    ├── test_cleaners.py
    ├── test_chunking.py
    └── test_ocr_helpers.py
```

---

## 3. Detailed Refactoring Plan

### Phase 1: Foundation & Safety (Do First)

#### 1.1 Create `.gitignore`
```
venv/
__pycache__/
*.pyc
.env
*.egg-info/
.pytest_cache/
.idea/
.DS_Store
*.bak
*.tmp
.pre_*.bak
```

#### 1.2 Create `pyproject.toml`
Define all dependencies explicitly:
```toml
[project]
name = "deen-scraper"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "requests",
    "beautifulsoup4",
    "pandas",
    "PyMuPDF",
    "Pillow",
    "ocrmac",
    "pinecone",
    "sentence-transformers",
    "scikit-learn",
    "langchain",
    "python-dotenv",
    "tqdm",
]

[project.scripts]
deen-scrape = "deen_scraper.cli:main"
```

#### 1.3 Create `.env.example`
Template with placeholder values. Document every variable that scripts expect.
**Move the real `.env` to a credentials manager and never commit it.**

#### 1.4 Move `.env` out of version tracking
```bash
git rm --cached .env
```

### Phase 2: Extract Shared Utilities (Eliminate Duplication)

#### 2.1 `src/deen_scraper/utils/text.py` (formerly `text_prepocesser.py`)
- Move `ISLAMIC_TERMS_MAP`, `compress_text()`, `normalize_text()` from `chunksets/text_prepocesser.py`
- Fix typo: rename to `text.py`
- Add `decompress_text()` function that exists but is imported but never defined in the original

#### 2.2 `src/deen_scraper/cleaners/base.py` — **Shared cleaning functions**
Merge the **4 duplicated `chunk_paragraphs()`** and **2 duplicated `extract_topic_tags()`** into shared utilities:
```python
# Shared across ALL cleaners:
CHUNK_SIZE = 350          # single source of truth
CHUNK_OVERLAP = 50        # single source of truth
```

Functions to consolidate:
- `chunk_paragraphs(text, chunk_size, overlap)` — from 4 files
- `extract_topic_tags(chapter_title)` — from 2 files
- `split_book(book)` — from al_kafi & nahjul_balagha
- `split_chapter(chapter)` — from al_kafi & nahjul_balagha
- `extract_numeric(text)` — from al_kafi & nahjul_balagha
- `clean_text(text)` — from al_kafi & nahjul_balagha
- `safe_int(x)` — from al_kafi & nahjul_balagha
- `contains_arabic(text)` — from multiple parsers

#### 2.3 `src/deen_scraper/ocr/core.py` — **Shared OCR utilities**
Merge the **5 files worth of duplicated OCR helpers**:
```python
# Shared regex constants
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_RE = re.compile(r"[A-Za-z]")
HADITH_MARKER_RES = {
    "faqih": re.compile(r"^H\.?\s*(\d+)\b", re.IGNORECASE),
    "tahdhib": re.compile(r"^HADITH\.?\s*(\d+)\b", re.IGNORECASE),
}

# Shared dataclasses
@dataclass class LineBox: ...
@dataclass class Marker: ...

# Shared functions
def normalize(text): ...
def is_arabic_only(line): ...
def avg_token_length(arabic_text): ...
def extract_page_lines(page): ...
def find_markers(doc, marker_type): ...
def marker_bounds(markers, hadith_number): ...
def arabic_boxes_for_hadith(doc, markers, hadith_number): ...
def ocr_crop(page, rect, zoom=3.0): ...
def parse_base_hadith_number(hadith_id): ...
def postprocess_rows(rows): ...
```

#### 2.4 `src/deen_scraper/config.py` — **Central configuration**
Single source for:
- `CHUNK_SIZE`, `CHUNK_OVERLAP`
- `DENSE_INDEX_NAME`, `SPARSE_INDEX_NAME`
- `PINECONE_NAMESPACE`, `BATCH_SIZE`
- `EMBEDDING_MODEL`
- `COLLECTIONS` registry (name, sect, author, input/output paths)

### Phase 3: Consolidate Duplicate Modules

#### 3.1 Unified Dense Indexer
**Replace 3 files** (`index_dense.py`, `index_faqih_dense.py`, `index_tahdib_dense.py`) with **one parameterized `src/deen_scraper/indexing/dense_indexer.py`**:

```python
def run_dense_indexer(records, index_name="deen-index-v2",
                       model_name="sentence-transformers/all-mpnet-base-v2",
                       context_template=None, batch_size=50, namespace="ns1"):
    """
    Generic dense indexer. The context_template allows per-collection customization
    of the embedding prefix without duplicating code.
    """
```

Each collection gets a thin **configuration entry** rather than a separate file.

#### 3.2 Unified Sparse Indexer
**Replace 3 files** (`index_sparse.py`, `index_faqih_sparse.py`, `index_tahdib_sparse.py`) with **one parameterized `src/deen_scraper/indexing/sparse_indexer.py`**.

Same pattern — the TF-IDF + Pinecone logic is identical across collections.

#### 3.3 Unified PDF Hadith Parser
**`src/deen_scraper/parsers/pdf_hadith_parser.py`** — The current `pdf_to_hadith_csv.py` already handles both Faqih and Tahdhib format. Keep it as the unified parser. Make it configurable via a `--format faqih|tahdhib` flag to handle the different marker styles (H.N vs HADITH.N).

#### 3.4 Unified Al-Mizan PDF Parsers
**Merge `parse_pdf_to_csv.py` and `parse_pdf_to_csv_vol3.py`** into a single `src/deen_scraper/parsers/al_mizan_pdf_parser.py` with a format detection or `--variant v1|v3` flag. The two scripts share ~80% of their code base.

#### 3.5 Unified Sunni Processing
**Replace the duplicated Sunni scraping calls** in both `index_dense.py` and `index_sparse.py` with a single `src/deen_scraper/cleaners/sunni.py` that processes all 5 collections via a loop over a configuration list.

### Phase 4: Cleaner Reorganization (6 -> 7 specialized files)

| Current File | Becomes | Changes |
|-------------|---------|---------|
| `chunksets/al_kafi_cleaner.py` | `src/deen_scraper/cleaners/al_kafi.py` | Remove `chunk_paragraphs` (import from `base`); use shared config |
| `chunksets/al_mizan_cleaner.py` | `src/deen_scraper/cleaners/al_mizan.py` | Remove duplications; use shared config |
| `chunksets/faqih_cleaner.py` | `src/deen_scraper/cleaners/faqih.py` | Remove `chunk_paragraphs`, `extract_topic_tags`; import from `base` |
| `chunksets/tahdib_cleaner.py` | `src/deen_scraper/cleaners/tahdhib.py` | Remove `chunk_paragraphs`, `extract_topic_tags`; import from `base` |
| `chunksets/nahjul_balaghah_cleaner.py` | `src/deen_scraper/cleaners/nahjul_balagha.py` | Remove `chunk_paragraphs`; use shared config |
| `chunksets/sunni_book_cleaner.py` | `src/deen_scraper/cleaners/sunni.py` | Refactor to accept collection list; add CLI |
| `chunksets/text_prepocesser.py` | `src/deen_scraper/utils/text.py` | Rename file; keep functions |

### Phase 5: Data Directory Reorganization

#### 5.1 Move from flat `datasets/` to structured `data/raw/` -> `data/processed/` -> `data/chunks/`

```
datasets/
  alkafi/*.csv                   ->  data/raw/shia/alkafi/
  nahjal_balagha/*.csv           ->  data/raw/shia/nahjul_balagha/
  man-la-yahduruhu-al-faqih/*.csv  ->  data/raw/shia/man-la-yahduruhu-al-faqih/csv/
  man-la-yahduruhu-al-faqih/pdfs/*  ->  data/raw/shia/man-la-yahduruhu-al-faqih/pdfs/
  tahdib-al-ahkam/*.csv          ->  data/raw/shia/tahdhib-al-ahkam/csv/
  tahdib-al-ahkam/pdfs/*         ->  data/raw/shia/tahdhib-al-ahkam/pdfs/
  al-mizan/*.csv                 ->  data/raw/shia/al-mizan/
  al-mizan/pdfs/*                ->  data/raw/shia/al-mizan/pdfs/
  al-mizan/svg_scraped/*         ->  data/raw/shia/al-mizan/svg_scraped/
  cleaned_data/*.jsonl           ->  data/chunks/
  [Sunni CSVs loose in root]     ->  data/raw/sunni/
```

**Important note:** The existing cleaned JSONL files and PDFs should be preserved — they represent work-product. Moving is a `git mv` operation to preserve history.

#### 5.2 Update ALL path references
Every script that uses `../datasets/`, `os.path.dirname(os.path.abspath(__file__))`, or hardcoded absolute paths must use `config.py` paths instead.

```python
# Before (in faqih_cleaner.py):
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
INPUT_DIR = os.path.join(REPO_ROOT, "datasets", "man-la-yahduruhu-al-faqih")

# After:
from deen_scraper.config import DATA_DIR
INPUT_DIR = DATA_DIR / "raw" / "shia" / "man-la-yahduruhu-al-faqih" / "csv"
```

### Phase 6: Index Setup Consolidation

**Replace 2 files** (`create_dense_index.py`, `create_sparse_index.py`) with **one `src/deen_scraper/indexing/index_setup.py`** that creates both indexes from a single configuration.

### Phase 7: CLI Entry Points

Create command-line wrappers in `scripts/` so users do not need to know which exact module to invoke:

```bash
# Scrape
python -m deen_scraper scrape sunnah --book bukhari
python -m deen_scraper scrape al-mizan --all

# Parse
python -m deen_scraper parse-pdf --format faqih --input data/raw/shia/.../vol1.pdf --output data/raw/shia/.../csv/

# OCR
python -m deen_scraper ocr --collection faqih --volume 1 --range 1-1573 --dry-run

# Clean and Chunk
python -m deen_scraper clean faqih --all-volumes

# Index
python -m deen_scraper index --collection faqih --type dense
python -m deen_scraper index --collection faqih --type sparse
python -m deen_scraper index --collection all --type both
```

### Phase 8: Documentation

#### 8.1 Update Root `README.md`
Replace the current 12-line README with comprehensive documentation:
- Project overview and architecture
- Setup instructions (`pip install -e .`)
- Quick start for each collection
- Data flow diagram (scrape -> parse -> clean -> chunk -> index)

#### 8.2 Per-Collection Docs in `docs/`
Move and enhance the existing `al-mizan/README.md` and `man-la-yahduruhu-al-faqih/README.md` into `docs/`.

The **very detailed** `CLAUDE_HANDOFF_TAHDHIB_AL_AHKAM.md` should be merged into `docs/tahdhib-al-ahkam.md` as a "Known Issues & Pitfalls" section, since it contains invaluable tribal knowledge about PDF parsing anomalies.

#### 8.3 Schema Documentation
Document the **canonical chunk schema** (all fields in the JSONL output) so downstream consumers (the frontend, APIs) know what to expect.

### Phase 9: Notebooks Cleanup

- **Delete** `scraping.ipynb` (empty, useless)
- **Delete** `legacy_indexing_script.ipynb` (contains hardcoded API keys, superseded by proper indexers)
- **Move** `sunnah-scraper.py` to `src/deen_scraper/scrapers/sunnah_scraper.py` (it is production code, not a notebook artifact)
- Keep `notebooks/` directory empty with `.gitkeep` for future exploratory work

### Phase 10: Testing

Add basic tests to ensure no regressions:

```python
# tests/test_cleaners.py
- Test chunk_paragraphs() produces expected output
- Test extract_topic_tags() handles edge cases
- Test each cleaner produces valid JSONL records

# tests/test_parsers.py
- Test pdf_hadith_parser() handles Faqih H.N format
- Test pdf_hadith_parser() handles Tahdhib HADITH.N format

# tests/test_ocr_helpers.py
- Test avg_token_length() scoring
- Test ARABIC_RE regex behavior
- Test normalize() function
```

---

## 4. File Change Matrix

### Files to DELETE
| File | Reason |
|------|--------|
| `chunksets/create_dense_index.py` | Merged into `index_setup.py` |
| `chunksets/create_sparse_index.py` | Merged into `index_setup.py` |
| `chunksets/index_dense.py` | Replaced by parameterized `dense_indexer.py` |
| `chunksets/index_sparse.py` | Replaced by parameterized `sparse_indexer.py` |
| `chunksets/index_faqih_dense.py` | Replaced by parameterized `dense_indexer.py` |
| `chunksets/index_faqih_sparse.py` | Replaced by parameterized `sparse_indexer.py` |
| `chunksets/index_tahdib_dense.py` | Replaced by parameterized `dense_indexer.py` |
| `chunksets/index_tahdib_sparse.py` | Replaced by parameterized `sparse_indexer.py` |
| `al-mizan/parse_pdf_to_csv.py` | Merged with vol3 variant |
| `al-mizan/parse_pdf_to_csv_vol3.py` | Merged into unified parser |
| `notebooks/scraping.ipynb` | Empty/dead |
| `notebooks/legacy_indexing_script.ipynb` | Superseded + contains API keys |

### Files to MOVE & RENAME
| Current Path | New Path | Notes |
|-------------|----------|-------|
| `chunksets/text_prepocesser.py` | `src/deen_scraper/utils/text.py` | Fix typo |
| `chunksets/al_kafi_cleaner.py` | `src/deen_scraper/cleaners/al_kafi.py` | Remove duplicated code |
| `chunksets/al_mizan_cleaner.py` | `src/deen_scraper/cleaners/al_mizan.py` | Remove duplicated code |
| `chunksets/faqih_cleaner.py` | `src/deen_scraper/cleaners/faqih.py` | Remove duplicated code |
| `chunksets/tahdib_cleaner.py` | `src/deen_scraper/cleaners/tahdhib.py` | Remove duplicated code |
| `chunksets/nahjul_balaghah_cleaner.py` | `src/deen_scraper/cleaners/nahjul_balagha.py` | Remove duplicated code |
| `chunksets/sunni_book_cleaner.py` | `src/deen_scraper/cleaners/sunni.py` | Make configurable |
| `al-mizan/scraper.py` | `src/deen_scraper/scrapers/al_mizan_web.py` | |
| `al-mizan/scrape_volume_svg.py` | `src/deen_scraper/scrapers/al_mizan_svg.py` | |
| `man-la-yahduruhu-al-faqih/pdf_to_hadith_csv.py` | `src/deen_scraper/parsers/pdf_hadith_parser.py` | |
| `man-la-yahduruhu-al-faqih/ocr_arabic_preview.py` | `src/deen_scraper/ocr/tahdhib_ocr.py` | |
| `man-la-yahduruhu-al-faqih/ocr_faqih_arabic.py` | `src/deen_scraper/ocr/faqih_ocr.py` | |
| `man-la-yahduruhu-al-faqih/fix_faqih_arabic_shift.py` | `src/deen_scraper/ocr/fix_arabic_shift.py` | |
| `man-la-yahduruhu-al-faqih/clean_commentary_arabic.py` | `src/deen_scraper/cleaners/clean_commentary.py` | |
| `man-la-yahduruhu-al-faqih/apply_ocr_patches.py` | `src/deen_scraper/ocr/apply_patches.py` | |
| `man-la-yahduruhu-al-faqih/ocr_235_subsections.py` | `src/deen_scraper/ocr/handle_subsections.py` | |
| `notebooks/sunnah-scraper.py` | `src/deen_scraper/scrapers/sunnah_scraper.py` | Move from notebooks |
| `al-mizan/README.md` | `docs/al-mizan.md` | |
| `man-la-yahduruhu-al-faqih/README.md` | `docs/man-la-yahduruhu-al-faqih.md` | |
| `CLAUDE_HANDOFF_TAHDHIB_AL_AHKAM.md` | `docs/tahdhib-al-ahkam.md` (merge content) | Preserve tribal knowledge |
| All `datasets/` files | Reorganized under `data/` | Per the new structure |

### Files to CREATE
| Path | Purpose |
|------|---------|
| `src/__init__.py` | Package root |
| `src/deen_scraper/__init__.py` | Package init |
| `src/deen_scraper/config.py` | Central configuration |
| `src/deen_scraper/scrapers/__init__.py` | Package init |
| `src/deen_scraper/parsers/__init__.py` | Package init |
| `src/deen_scraper/ocr/__init__.py` | Package init |
| `src/deen_scraper/ocr/core.py` | **Shared OCR utilities (biggest code dedup win)** |
| `src/deen_scraper/cleaners/__init__.py` | Package init |
| `src/deen_scraper/cleaners/base.py` | **Shared cleaning utilities (second biggest dedup win)** |
| `src/deen_scraper/chunking/__init__.py` | Package init |
| `src/deen_scraper/chunking/splitter.py` | Unified chunking logic |
| `src/deen_scraper/indexing/__init__.py` | Package init |
| `src/deen_scraper/indexing/dense_indexer.py` | **Unified dense indexer** |
| `src/deen_scraper/indexing/sparse_indexer.py` | **Unified sparse indexer** |
| `src/deen_scraper/indexing/index_setup.py` | Pinecone index creation |
| `src/deen_scraper/utils/__init__.py` | Package init |
| `pyproject.toml` | Project dependencies and metadata |
| `.gitignore` | Standard Python ignores |
| `.env.example` | Environment variable template |
| `data/.gitkeep` | Preserve empty directory in git |
| `notebooks/.gitkeep` | Preserve empty directory |
| `docs/al-kafi.md` | Collection documentation |
| `docs/nahjul-balagha.md` | Collection documentation |
| `docs/sunni-collections.md` | Collection documentation |
| `tests/__init__.py` | Test package init |
| `tests/test_cleaners.py` | Cleaner unit tests |
| `tests/test_parsers.py` | Parser unit tests |
| `tests/test_ocr_helpers.py` | OCR helper tests |
| `RESTRUCTURE_PLAN.md` | This document (record of the plan) |

---

## 5. Unified Chunk Schema (Canonical)

All collections should produce JSONL records with this unified schema:

```json
{
  "sect": "shia|sunni",
  "collection": "al-kafi|nahjul-balagha|man-la-yahduruhu-al-faqih|tahdhib-al-ahkam|al-mizan|sahih-bukhari|sahih-muslim|tirmidhi|abu-dawood|an-nasai",
  "author": "Shaykh al-Kulayni|...",
  "volume": "1",
  "book_number": "1",
  "book_title": "The Book of Intelligence",
  "chapter_number": "1",
  "chapter_title": "The Virtue of Intellect",
  "hadith_no": "1",
  "lang": "en",
  "grade_en": "Sahih",
  "grade_ar": "",
  "text_en": "English hadith text here...",
  "text_ar": "Arabic hadith text here...",
  "commentary": "Additional commentary/notes...",
  "cross_references": "Reference info...",
  "source_scholar": "Source attribution...",
  "page_start": "10",
  "page_end": "12",
  "topic_tags": ["intellect", "virtue"],
  "hadith_id": "shia_al-kafi_1_1_1",
  "chunk_id": "alkafi_0",
  "text_chunk": "Chunked text for embedding..."
}
```

---

## 6. Execution Order & Risk Mitigation

| Step | Action | Risk | Mitigation |
|------|--------|------|------------|
| 1 | Create `.gitignore`, commit | Low | Safe first step |
| 2 | Create `pyproject.toml`, verify `pip install -e .` works | Low | Test in venv first |
| 3 | Create `config.py` with all paths/constants | Medium | All new paths must be verified |
| 4 | Extract `utils/text.py` and `cleaners/base.py` | Medium | Run all cleaners against existing data, verify JSONL output matches |
| 5 | Extract `ocr/core.py` | High | OCR is the most fragile pipeline component; test with existing compare/preview CSVs |
| 6 | Create unified dense + sparse indexers | High | Test upsert with small batch first |
| 7 | Move parsers | Medium | Verify CSV output byte-for-byte identical |
| 8 | Reorganize `data/` directory | High | Use `git mv` to preserve history; verify all path references |
| 9 | Create CLI entry points | Low | Wrappers, not new logic |
| 10 | Delete old files + cleanup notebooks | Low | Verify everything works before deleting |
| 11 | Update documentation | Low | Ongoing |
| 12 | Add tests | Medium | Test against known-good output files |

---

## 7. Key Decisions & Rationale

### Why `src/deen_scraper/` instead of `src/` flat?
Following the `src-layout` convention with a properly named package makes imports clean (`from deen_scraper.cleaners.base import chunk_paragraphs`) and avoids naming collisions.

### Why not remove Pinecone dependency?
The Pinecone indexers are core functionality. Moving to a different vector DB is a separate concern — this restructure is about **organization and deduplication**, not technology replacement.

### Why not unify the two chunk approaches (paragraph-based vs langchain-based)?
The paragraph-based approach (`chunk_paragraphs`) is used for hadith collections where preserving paragraph boundaries matters. The langchain `RecursiveCharacterTextSplitter` is used for long-form commentary (Al-Mizan). These serve different purposes — keep both but make them accessible via a single `splitter.py` with a strategy pattern.

### What about backwards compatibility?
The JSONL schema should remain **additive** — new fields can be added, existing fields should not be removed or renamed, so downstream consumers (the Deen frontend) do not break.

---

## 8. Estimated Impact

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Python files in project (excl venv) | 22 | 28 (+16 new, -12 deleted = net +6 but much more organized) | Cleaner organization |
| Lines of duplicated code | ~600+ lines across 12+ files | ~0 (single source) | **-600 lines of duplication** |
| Indexer files | 8 separate files | 2 parameterized modules | **-6 files** |
| `chunk_paragraphs` copies | 4 copies | 1 shared | **-3 copies** |
| OCR helper function copies | 5 files with ~15 shared functions each | 1 shared module | **-60 duplicated functions** |
| Config constants scattered | 6+ files | 1 file | Centralized |
| Hardcoded absolute paths | 10+ occurrences | 0 (all use `config.py`) | No more path bugs |
| Schema consistency | 3 different informal schemas | 1 canonical schema | Interoperable |
| `sys.path` hack usage | 2 files | 0 | Proper package imports |
| Scripts with no `if __name__` guard | 4 files | 0 | All properly guarded |
ENDDOFFILE