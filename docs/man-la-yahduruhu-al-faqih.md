# Man La Yahduruhu Al-Faqih PDF Scraper

One-time parser for extracting hadith rows from the `Man La Yahduruhu Al-Faqih` PDF volumes.

## Output Schema

Each CSV row represents one hadith with these columns:

1. `Chapter Number`
2. `Chapter Title`
3. `Hadith Number`
4. `arabic_text`
5. `english_text`
6. `commentary`
7. `references`
8. `source_pdf`
9. `page_start`
10. `page_end`

## Run

From project root:

```bash
venv/bin/python man-la-yahduruhu-al-faqih/pdf_to_hadith_csv.py \
  --input /Users/tamieemjaffary/Downloads/man-la-yahduruhu-al-faqih-vol.1.pdf
```

Optional output directory override:

```bash
venv/bin/python man-la-yahduruhu-al-faqih/pdf_to_hadith_csv.py \
  --input /path/to/vol1.pdf /path/to/vol2.pdf \
  --output-dir /Users/tamieemjaffary/PycharmProjects/deen-web-scraping/datasets/man-la-yahduruhu-al-faqih
```

## Notes

- Front matter is skipped automatically until first hadith marker (`H.<number>`).
- Original hadith numbering is preserved as-is.
- `[AL SADUQ]` content is captured under `commentary`.
- `[REFERENCES]` content is captured under `references`.
