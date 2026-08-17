"""Tests for the al-islam.org scraper parsers and cleaner.

The parsers are pure functions over HTML, so these run offline against
fixtures in ``tests/fixtures/al_islam/`` that mirror al-islam.org's markup.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deen_scraper.cleaners.al_islam import (
    MAX_CHUNK_WORDS,
    build_chunks,
    build_topic_tags,
    chunk_chapter,
    extract_arabic_quotes,
)
from deen_scraper.scrapers.al_islam import (
    canonical_url,
    parse_author_page,
    parse_book_page,
    parse_chapter_page,
    slug_from_url,
)

FIXTURES = Path(__file__).parent / "fixtures" / "al_islam"
AUTHOR_URL = "https://al-islam.org/person/murtadha-mutahhari"
BOOK_URL = "https://al-islam.org/spiritual-discourses-murtadha-mutahhari"
CHAPTER_URL = f"{BOOK_URL}/discourse-1-criteria-humanity"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/spiritual-discourses-murtadha-mutahhari", BOOK_URL),
        ("/spiritual-discourses-murtadha-mutahhari/", BOOK_URL),
        (BOOK_URL + "#toc", BOOK_URL),
        ("person/murtadha-mutahhari", AUTHOR_URL),
    ],
)
def test_canonical_url_normalises(raw, expected):
    assert canonical_url(raw) == expected


def test_canonical_url_keeps_pager_query():
    assert canonical_url("/person/murtadha-mutahhari?page=3") == AUTHOR_URL + "?page=3"


def test_slug_from_url_ignores_query():
    assert slug_from_url(AUTHOR_URL + "?page=3") == "murtadha-mutahhari"


# ---------------------------------------------------------------------------
# Author page
# ---------------------------------------------------------------------------

def test_parse_author_page_extracts_books_and_pager():
    page = parse_author_page(fixture("author_page.html"), AUTHOR_URL)

    assert page.author_name == "Murtadha Mutahhari"
    # The heading counts view rows, which over-counts books credited to the
    # scholar in more than one field.
    assert page.advertised_rows == 50
    assert page.next_url == AUTHOR_URL + "?page=1"
    assert [b.slug for b in page.books] == [
        "spiritual-discourses-murtadha-mutahhari",
        "divine-justice-murtadha-mutahhari",
    ]


def test_parse_author_page_ignores_other_views():
    """A book must not be picked up from the sibling Media view."""
    page = parse_author_page(fixture("author_page.html"), AUTHOR_URL)
    assert all("lecture" not in b.slug for b in page.books)


def test_parse_author_page_last_page_has_no_next():
    page = parse_author_page(fixture("author_page_last.html"), AUTHOR_URL + "?page=6")
    assert page.next_url is None
    assert [b.slug for b in page.books] == ["man-and-faith-murtadha-mutahhari"]


# ---------------------------------------------------------------------------
# Book page
# ---------------------------------------------------------------------------

def test_parse_book_page_metadata():
    meta, _ = parse_book_page(fixture("book_page.html"), BOOK_URL)

    assert meta.title == "Spiritual Discourses"
    assert meta.node_id == "39742"
    assert meta.slug == "spiritual-discourses-murtadha-mutahhari"
    assert meta.authors == ["Murtadha Mutahhari"]
    assert meta.translators == ["Dr. Alaedin Pazargadi"]
    assert meta.publishers == ["Islamic Propagation Organization"]
    assert meta.tags == ["Spirituality", "Ethics"]
    assert meta.description.startswith("Criteria for humanity")


def test_parse_book_page_toc_is_ordered_and_excludes_self_link():
    _, chapters = parse_book_page(fixture("book_page.html"), BOOK_URL)

    assert [c.order for c in chapters] == [1, 2, 3, 4]
    assert [c.slug for c in chapters] == [
        "discourse-1-criteria-humanity",
        "discourse-2-school-humanity",
        "discourse-3-spiritual-freedom-1",
        "discourse-3-part-b",
    ]
    assert chapters[0].title == "Discourse 1: The Criteria for Humanity"
    # Nested sub-chapters keep their depth so structure is not lost.
    assert chapters[3].depth == 3
    assert all(c.url != BOOK_URL for c in chapters)


# ---------------------------------------------------------------------------
# Chapter page
# ---------------------------------------------------------------------------

def test_parse_chapter_page_extracts_prose():
    parsed = parse_chapter_page(fixture("chapter_page.html"), CHAPTER_URL)

    assert parsed["heading"] == "Discourse 1: The Criteria for Humanity"
    text = parsed["text"]
    assert text.startswith("I have been asked to discuss")
    # Paragraphs are separated by blank lines so the chunker can split on them.
    assert "\n\n" in text
    # Headings, blockquotes, and list items are all captured.
    assert "The View of the Philosophers" in text
    assert "Man is a rational animal." in text
    assert "Self-sacrifice comes closer." in text
    # Wrapped source lines are joined and space-before-punctuation is fixed.
    assert "an easy matter." in text
    assert "  " not in text


def test_parse_chapter_page_separates_footnotes_from_body():
    """Footnotes are a `ul.footnotes` list inside the body field, so they must
    be lifted out or they read as trailing prose."""
    parsed = parse_chapter_page(fixture("chapter_page.html"), CHAPTER_URL)

    assert "Nahj al-Balagha, Letter 45." in parsed["footnotes"]
    assert "Mathnavi, Book 1." in parsed["footnotes"]
    assert "Nahj al-Balagha" not in parsed["text"]


def test_parse_chapter_page_strips_inline_footnote_markers():
    """The `[1]` anchors must not leave stray digits mid-sentence."""
    parsed = parse_chapter_page(fixture("chapter_page.html"), CHAPTER_URL)

    assert "in his testament." in parsed["text"]
    assert "testament1" not in parsed["text"]


def test_parse_chapter_page_drops_scripts():
    parsed = parse_chapter_page(fixture("chapter_page.html"), CHAPTER_URL)
    assert "getElementsByClassName" not in parsed["text"]


def test_parse_chapter_page_without_body_is_empty_not_an_error():
    parsed = parse_chapter_page("<html><body><article></article></body></html>", CHAPTER_URL)
    assert parsed == {"heading": "", "text": "", "footnotes": ""}


# ---------------------------------------------------------------------------
# Cleaner
# ---------------------------------------------------------------------------

def sample_record(**overrides) -> dict:
    record = {
        "author_slug": "murtadha-mutahhari",
        "author_name": "Murtadha Mutahhari",
        "book_title": "Spiritual Discourses",
        "book_slug": "spiritual-discourses-murtadha-mutahhari",
        "book_url": BOOK_URL,
        "book_translators": ["Dr. Alaedin Pazargadi"],
        "book_publishers": ["Islamic Propagation Organization"],
        "book_tags": ["Spirituality"],
        "chapter_order": 1,
        "chapter_title": "Discourse 1: The Criteria for Humanity",
        "chapter_slug": "discourse-1-criteria-humanity",
        "chapter_url": CHAPTER_URL,
        "text": "\n\n".join(f"Paragraph {i} about the criteria for humanity." for i in range(40)),
        "footnotes": "Nahj al-Balagha, Letter 45.",
    }
    record.update(overrides)
    return record


def test_build_chunks_tags_every_chunk():
    chunks = build_chunks(sample_record(), "al-islam-murtadha-mutahhari", "Murtadha Mutahhari")

    assert chunks, "expected at least one chunk"
    for chunk in chunks:
        assert chunk["sect"] == "shia"
        assert chunk["author"] == "Murtadha Mutahhari"
        assert chunk["book_title"] == "Spiritual Discourses"
        assert chunk["collection"] == "al-islam-murtadha-mutahhari"
        assert chunk["source_url"] == CHAPTER_URL
        assert chunk["text_chunk"]


def test_build_chunks_ids_are_unique_and_ordered():
    chunks = build_chunks(sample_record(), "al-islam-murtadha-mutahhari", "Murtadha Mutahhari")
    ids = [c["chunk_id"] for c in chunks]

    assert len(ids) == len(set(ids))
    assert ids[0].endswith("_0")


def test_build_chunks_metadata_is_pinecone_safe():
    """Pinecone rejects None; every value must be a str, number, or list of str."""
    chunks = build_chunks(sample_record(), "al-islam-murtadha-mutahhari", "Murtadha Mutahhari")

    for key, value in chunks[0].items():
        assert value is not None, f"{key} is None"
        if isinstance(value, list):
            assert all(isinstance(v, str) for v in value), key
        else:
            assert isinstance(value, (str, int, float, bool)), f"{key} is {type(value)}"


def test_build_chunks_skips_stub_chapters():
    assert build_chunks(sample_record(text="Too short."), "c", "A") == []
    assert build_chunks(sample_record(text=""), "c", "A") == []


def test_chunk_chapter_splits_a_single_huge_paragraph():
    """One 2000-word paragraph cannot be split on paragraph breaks, so it must
    be broken down further or the embedder would truncate it."""
    huge = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_chapter(huge)

    assert len(chunks) > 1
    assert all(len(c.split()) <= MAX_CHUNK_WORDS for c in chunks)


def test_chunk_chapter_leaves_normal_paragraphs_alone():
    text = "\n\n".join("A short paragraph of prose." for _ in range(3))
    assert chunk_chapter(text) == [
        "A short paragraph of prose. A short paragraph of prose. A short paragraph of prose."
    ]


def test_extract_arabic_quotes_lifts_inline_arabic():
    text = (
        "Hadrat Ali said: \u0647\u0645 \u0645\u0648\u0636\u0639 \u0633\u0631\u0647 "
        "\u0648 \u0644\u062c\u0623 \u0623\u0645\u0631\u0647, and this means the following."
    )
    quotes = extract_arabic_quotes(text)

    assert quotes.startswith("\u0647\u0645 \u0645\u0648\u0636\u0639")
    assert "means" not in quotes


def test_extract_arabic_quotes_ignores_isolated_words():
    """A single Arabic term inside English prose is not a quotation."""
    assert extract_arabic_quotes("The word \u0632\u0643\u0627\u0629 means charity.") == ""


def test_extract_arabic_quotes_on_english_only_text():
    assert extract_arabic_quotes("Purely English prose with no Arabic at all.") == ""


def test_build_chunks_mirrors_arabic_into_text_ar():
    arabic = "\u0647\u0645 \u0645\u0648\u0636\u0639 \u0633\u0631\u0647 \u0648 \u0644\u062c\u0623"
    record = sample_record(text=f"He said: {arabic}\n\n" + "\n\n".join(
        f"Paragraph {i} of discussion." for i in range(30)
    ))
    chunks = build_chunks(record, "al-islam-murtadha-mutahhari", "Murtadha Mutahhari")

    # Arabic stays readable inline and is mirrored into text_ar.
    assert arabic in chunks[0]["text_chunk"]
    assert arabic in chunks[0]["text_ar"]
    # Chunks with no Arabic get an empty string, never None.
    assert all(isinstance(c["text_ar"], str) for c in chunks)


def test_build_topic_tags_merges_title_tokens_and_book_tags():
    tags = build_topic_tags("The Criteria for Humanity", ["Spirituality", "Ethics"])

    assert "criteria" in tags
    assert "humanity" in tags
    assert "spirituality" in tags
    # Stop words are dropped by the shared helper.
    assert "the" not in tags
    assert len(tags) == len(set(tags))
