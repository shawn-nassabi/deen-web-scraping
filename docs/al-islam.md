# al-islam.org Scraper and Indexer

Scrapes books from [al-islam.org](https://al-islam.org) (the Ahlul Bayt Digital
Islamic Library Project), organised **by author**: you point the scraper at a
scholar's `/person/<slug>` page and it walks every book that scholar has on the
site, chapter by chapter, into tagged chunks in Pinecone.

Unlike the PDF-based collections in this repo, al-islam.org serves plain HTML
text pages, so **no OCR is involved** — the text is extracted straight from the
page body.

---

## Status

| Author | Author page | Books | Chapters | Chunks | Status |
|--------|-------------|-------|----------|--------|--------|
| Murtadha Mutahhari | `/person/murtadha-mutahhari` | 33 | 414 | 4,480 | ✅ Scraped, cleaned, indexed |

The Mutahhari pilot took 452 requests (~1h20m at the 10-second crawl delay) and
produced 1.14M words of prose.

---

## Page shapes

al-islam.org runs Drupal 7. Three page types matter:

| Page | Node type | What we take from it |
|------|-----------|----------------------|
| `/person/<slug>` | taxonomy term | The list of the scholar's books (paginated Views block) |
| `/<book-slug>` | `fulllengthtext` | Book title, table of contents, author / translator / publisher / tags |
| `/<book-slug>/<chapter-slug>` | `book` | The chapter prose, in `div.field-name-body` |

Key selectors (all pinned in `scrapers/al_islam.py`):

- Books listing: `div.view-taxonomy-term-details-books`
- Table of contents: `#block-ascent-navigation ul.menu.nav li a`, with nesting
  depth in the `li`'s `menu-depth-N` class
- Chapter body: `div.field-name-body`
- Bibliographic fields: `.field-name-field-author`, `-field-translator`,
  `-field-publisher`, `-field-tags`

---

## Usage

### Step 1: Scrape an author

```bash
# List the books that would be scraped, without scraping them
python -m deen_scraper.scrapers.al_islam \
    --author-url https://al-islam.org/person/murtadha-mutahhari --list-only

# Full scrape
python -m deen_scraper.scrapers.al_islam \
    --author-url https://al-islam.org/person/murtadha-mutahhari
```

Writes to `data/raw/shia/al-islam/<author-slug>/`:

- `chapters.jsonl` — one record per chapter, with the book metadata attached
- `books.json` — manifest of the books found and their chapter counts

Useful flags: `--max-books N` (scrape a subset), `--delay` (seconds between
requests, default 10), `--headless`, `--output-dir`.

### Step 2: Clean and chunk

```bash
python -m deen_scraper.cleaners.al_islam --author-slug murtadha-mutahhari
```

Writes `data/chunks/al_islam_<author_slug>_cleaned_chunks.jsonl`.

### Step 3: Index

```bash
python -m deen_scraper.indexing.dense_indexer  --collection al-islam-murtadha-mutahhari
python -m deen_scraper.indexing.sparse_indexer --collection al-islam-murtadha-mutahhari
```

---

## Adding another author

1. Add the slug to `AL_ISLAM_AUTHORS` in `src/deen_scraper/config.py`:

   ```python
   AL_ISLAM_AUTHORS: dict[str, str] = {
       "murtadha-mutahhari": "Murtadha Mutahhari",
       "sayyid-muhammad-husayn-tabatabai": "Allamah Tabatabai",   # new
   }
   ```

   That one line registers the collection name, its raw input directory, its
   chunk file, and its indexer prompt.

2. Run the three steps above with the new slug. No new scraper or cleaner code
   is needed — both are generic across authors.

---

## Fetching: why a browser, and why it is slow

**Cloudflare.** al-islam.org sits behind Cloudflare bot protection, which
answers `requests`/`curl` with a 403 interstitial regardless of headers. Pages
are therefore fetched through a real browser via Playwright, preferring the
system Chrome (`channel="chrome"`). The browser profile is persisted in
`data/raw/shia/al-islam/_browser_profile/` so clearance cookies survive between
runs.

**Crawl delay.** `al-islam.org/robots.txt` asks every crawler for
`Crawl-delay: 10` and does not disallow `/person/` or book pages. The scraper
honours that 10-second spacing by default, which makes a full author scrape
slow: Mutahhari's 33 books are 414 chapter pages, about 80 minutes. Lower it
with `--delay` only if you have permission to.

**Resumability.** Because runs are long, two things make them restartable:

- every fetched page is cached in `data/raw/shia/al-islam/_html_cache/`
- `chapters.jsonl` is appended and flushed per chapter, and a restart skips
  chapters already present

Re-running after an interruption costs no new requests for work already done.
Both directories are git-ignored.

---

## Known issues & pitfalls

### The "N Books" heading is a row count, not a book count

Mutahhari's page says **50 Books** but there are only **33 distinct books**. The
books Views block joins the author taxonomy term against several node fields
(author, translator, editor, …), so a book credited to the scholar more than
once occupies multiple rows: 7 of Mutahhari's books appear 3 times in the
listing, 3 appear twice, and 23 appear once — 50 rows, 33 books.

Consequences:

- Paginating `?page=0..6` yields 50 slots that dedupe to 33 URLs. Duplicate
  links are expected, not a bug.
- **Do not** use the advertised number as a completeness check. `discover_books`
  instead walks the listing a second time and stops when a full pass adds no new
  book.

### `items_per_page` is not exposed

`?items_per_page=100` is ignored, so the 8-per-page pager cannot be avoided.

### Non-book content on author pages

Author pages also list Media, Articles, Questions, and Files in sibling Views
blocks with their own pagers. Book discovery is scoped to the books block only;
widening the selector will pull in lectures and Q&A.

### Sub-chapters

Some books nest chapters (`menu-depth-3` under a `menu-depth-2` parent). These
are scraped as ordinary chapters, with the nesting recorded in `chapter_depth`
so the hierarchy is recoverable.

### Front matter

Short stubs (dedications, one-line translator notes) are dropped by the cleaner
via `MIN_CHAPTER_WORDS`; the scraper still stores them in `chapters.jsonl`.

### Footnotes live *inside* the body field

Footnotes render as `<ul class="footnotes">` at the end of `div.field-name-body`,
with `<a class="see-footnote">` markers inline in the prose. If they are not
lifted out first they read as trailing prose: 310 of Mutahhari's 414 chapters
have them, worth ~44k words of citations that would otherwise pollute the text.

### One paragraph can exceed the chunk size

`chunk_paragraphs` can only break between paragraphs, so a single very long
paragraph comes back as one oversized chunk (the worst case here was 2,383
words). The cleaner re-splits anything over `MAX_CHUNK_WORDS`, because
`all-mpnet-base-v2` silently truncates past roughly 384 tokens and the tail
would never reach the vector.

---

## Chunk schema

Follows the repo's canonical schema, with al-islam.org provenance added. Every
chunk carries `sect`, `author`, and `book_title` as requested.

```json
{
  "sect": "shia",
  "collection": "al-islam-murtadha-mutahhari",
  "author": "Murtadha Mutahhari",
  "book_title": "Spiritual Discourses",
  "chapter_number": "1",
  "chapter_title": "Discourse 1: The Criteria for Humanity",
  "volume": "",
  "book_number": "",
  "hadith_no": "",
  "lang": "en",
  "grade_en": "",
  "grade_ar": "",
  "text_en": "Chunk text ...",
  "text_ar": "Arabic passages quoted inside this chunk, one per line",
  "commentary": "",
  "cross_references": "Footnotes, if the chapter had any",
  "source_scholar": "",
  "page_start": "",
  "page_end": "",
  "topic_tags": ["criteria", "humanity", "spirituality"],
  "hadith_id": "shia_al-islam-murtadha-mutahhari_spiritual-discourses-murtadha-mutahhari_1",
  "chunk_id": "al-islam_spiritual-discourses-murtadha-mutahhari_1_0",
  "source": "al-islam.org",
  "source_url": "https://al-islam.org/spiritual-discourses-murtadha-mutahhari/discourse-1-criteria-humanity",
  "book_slug": "spiritual-discourses-murtadha-mutahhari",
  "book_url": "https://al-islam.org/spiritual-discourses-murtadha-mutahhari",
  "chapter_slug": "discourse-1-criteria-humanity",
  "translator": "Dr. Alaedin Pazargadi",
  "publisher": "Islamic Propagation Organization"
}
```

Notes on field choices:

- `hadith_no` / `grade_*` / `page_*` stay empty: these are books, not graded
  hadith, and web pages have no print pagination. They are kept so the record
  shape matches every other collection.
- `text_en` mirrors `text_chunk` rather than holding the whole chapter, which
  keeps Pinecone metadata small. The full chapter is always recoverable from
  `source_url`.
- These books are English translations that quote Qur'an verses and hadith in
  Arabic inline (about 18% of Mutahhari's paragraphs). Those quotes are **left
  in place** in `text_chunk` so a retrieved passage still reads as written, and
  are **also** copied into `text_ar` so the Arabic is queryable on its own. No
  chunk ends up majority-Arabic, so the English embedding model is unaffected.
- Footnotes go in `cross_references`, the closest existing field.
- `chapter_number` is the chapter's position in the table of contents, since
  al-islam.org chapters are not numbered in a machine-readable way.

---

## Content usage

al-islam.org states that its hosted content is "solely for non-commercial
purposes and with the permission of original copyright holders". Keep that in
mind for anything built on these chunks.

---

## Tests

Parsers are pure functions over HTML, so they are tested offline against
fixtures that mirror al-islam.org's markup:

```bash
python -m pytest tests/test_al_islam.py -q
```

Fixtures live in `tests/fixtures/al_islam/`. If al-islam.org redesigns, these
tests are the fastest way to find which selector broke.
