#!/usr/bin/env python3
"""Scrape al-islam.org books, discovered from a scholar's ``/person/<slug>`` page.

al-islam.org is a Drupal site, so three page shapes matter:

``/person/<slug>``
    Author page.  Books sit in a paginated Views block
    (``div.view-taxonomy-term-details-books``), eight per page, advanced with
    ``?page=N`` until the "Show More" pager link disappears.

``/<book-slug>``
    Book landing page (node type ``fulllengthtext``).  Carries the table of
    contents (``#block-ascent-navigation``) plus the author / translator /
    publisher / tag fields.

``/<book-slug>/<chapter-slug>``
    Chapter page (node type ``book``).  The prose lives in
    ``div.field-name-body`` as ordinary paragraphs -- no OCR required.

Fetching goes through a real browser (Playwright) because al-islam.org sits
behind Cloudflare, which rejects plain HTTP clients.  Requests are spaced by
the ``Crawl-delay: 10`` that al-islam.org/robots.txt asks for, and every page
is cached on disk, so an interrupted run resumes without re-fetching.

Parsing is kept in pure functions that take HTML strings, so the selectors can
be unit-tested against fixtures without touching the network.

Example
-------
    python -m deen_scraper.scrapers.al_islam \\
        --author-url https://al-islam.org/person/murtadha-mutahhari
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from deen_scraper.config import AL_ISLAM_RAW

BASE_URL = "https://al-islam.org"

# al-islam.org/robots.txt asks every crawler for `Crawl-delay: 10`.
CRAWL_DELAY = 10.0

# Views block that holds a scholar's books on their /person/ page.
BOOKS_VIEW_SELECTOR = "div.view-taxonomy-term-details-books"

# Sidebar block holding a book's table of contents.
TOC_SELECTOR = "#block-ascent-navigation"

BODY_SELECTOR = "div.field-name-body"

# Guard against a pager loop if the markup ever changes.
MAX_AUTHOR_PAGES = 50

# How many times to walk the book listing.  Discovery normally stops after the
# second pass confirms nothing new appeared.  See discover_books.
MAX_DISCOVERY_PASSES = 4

_BLOCK_TAGS = (
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "blockquote", "pre", "dd", "dt", "td", "div",
)

_CHALLENGE_MARKERS = (
    "cf-error-details",
    "Enable JavaScript and cookies to continue",
    "Checking if the site connection is secure",
)
_CHALLENGE_TITLES = ("just a moment", "attention required")


class CloudflareChallenge(RuntimeError):
    """Raised when Cloudflare serves an interstitial instead of the page."""


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BookRef:
    """A book link discovered on an author page."""

    url: str
    slug: str


@dataclass
class AuthorPage:
    """One page of a scholar's book listing."""

    author_name: str
    books: list[BookRef]
    next_url: str | None
    # The count in the "N Books" heading.  This is a *row* count, not a book
    # count -- see discover_books for why the two differ.
    advertised_rows: int | None


@dataclass(frozen=True)
class ChapterRef:
    """A chapter link discovered in a book's table of contents."""

    url: str
    slug: str
    title: str
    depth: int
    order: int


@dataclass
class BookMeta:
    """Bibliographic fields parsed from a book landing page."""

    url: str
    slug: str
    title: str = ""
    node_id: str = ""
    authors: list[str] = field(default_factory=list)
    translators: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def canonical_url(url: str) -> str:
    """Normalise *url* to absolute form with no fragment and no trailing slash."""
    absolute = urljoin(BASE_URL + "/", url)
    parts = urlsplit(absolute)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def slug_from_url(url: str) -> str:
    """Return the last path segment of *url*."""
    return urlparse(canonical_url(url)).path.rstrip("/").rsplit("/", 1)[-1]


def _is_internal_content_link(href: str) -> bool:
    """True for site-internal links that could be a book or chapter page."""
    if not href or href.startswith(("#", "mailto:", "javascript:")):
        return False
    parts = urlsplit(urljoin(BASE_URL + "/", href))
    if parts.netloc and parts.netloc != urlsplit(BASE_URL).netloc:
        return False
    path = parts.path.strip("/")
    if not path:
        return False
    # Taxonomy, utility, and export routes are never book content.
    first = path.split("/", 1)[0]
    return first not in {
        "person", "tags", "taxonomy", "node", "user", "search", "printpdf",
        "printepub", "printmobi", "book", "sites", "system", "comment",
    }


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _clean_inline(text: str) -> str:
    """Collapse whitespace and tidy spacing before punctuation."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


def _leaf_blocks(node) -> list:
    """Return block elements that contain no nested block element.

    Walking only the leaves keeps each paragraph, list item, and heading as one
    unit instead of emitting the same text once per nesting level.
    """
    blocks = []
    for el in node.find_all(_BLOCK_TAGS):
        if el.find(_BLOCK_TAGS) is None:
            blocks.append(el)
    return blocks


def extract_paragraphs(node) -> list[str]:
    """Extract clean paragraph strings from a BeautifulSoup *node*."""
    for junk in node.find_all(["script", "style", "noscript", "iframe"]):
        junk.decompose()

    paragraphs = [_clean_inline(b.get_text(" ")) for b in _leaf_blocks(node)]
    paragraphs = [p for p in paragraphs if p]

    if not paragraphs:
        whole = _clean_inline(node.get_text(" "))
        paragraphs = [whole] if whole else []

    # Drop consecutive duplicates (Drupal sometimes renders a field twice).
    deduped: list[str] = []
    for p in paragraphs:
        if not deduped or deduped[-1] != p:
            deduped.append(p)
    return deduped


# ---------------------------------------------------------------------------
# Parsers (pure functions over HTML -- unit-testable without network)
# ---------------------------------------------------------------------------

def parse_author_page(html: str, page_url: str) -> AuthorPage:
    """Parse one page of an author's book listing.

    ``next_url`` is ``None`` on the last page, which is how the caller knows to
    stop paginating.
    """
    soup = BeautifulSoup(html, "html.parser")

    name_el = soup.select_one("h2.term-details-term-name") or soup.select_one("h1")
    author_name = _clean_inline(name_el.get_text(" ")) if name_el else ""

    view = soup.select_one(BOOKS_VIEW_SELECTOR)
    if view is None:
        return AuthorPage(author_name, [], None, None)

    advertised_rows = None
    heading = view.select_one("h3")
    if heading is not None:
        match = re.search(r"(\d+)\s+Books?", heading.get_text(" "), re.IGNORECASE)
        if match:
            advertised_rows = int(match.group(1))

    content = view.select_one(".view-content") or view
    books: list[BookRef] = []
    seen: set[str] = set()
    for anchor in content.select("a[href]"):
        href = anchor.get("href", "")
        if "?page=" in href or not _is_internal_content_link(href):
            continue
        url = canonical_url(href)
        if url in seen:
            continue
        seen.add(url)
        books.append(BookRef(url=url, slug=slug_from_url(url)))

    next_url = None
    for anchor in view.select("ul.pager a[href], .pager a[href]"):
        href = anchor.get("href", "")
        if "page=" in href:
            next_url = canonical_url(href)
            break

    return AuthorPage(author_name, books, next_url, advertised_rows)


def _field_values(soup, field_name: str) -> list[str]:
    """Return de-duplicated values of a Drupal ``field-name-<field_name>`` field."""
    values: list[str] = []
    for holder in soup.select(f".field-name-{field_name} .field-item"):
        value = _clean_inline(holder.get_text(" "))
        if value and value not in values:
            values.append(value)
    return values


def parse_book_page(html: str, page_url: str) -> tuple[BookMeta, list[ChapterRef]]:
    """Parse a book landing page into its metadata and ordered chapter list."""
    soup = BeautifulSoup(html, "html.parser")
    book_url = canonical_url(page_url)

    title_el = soup.select_one("h1")
    title = _clean_inline(title_el.get_text(" ")) if title_el else ""

    node_id = ""
    shortlink = soup.select_one('link[rel="shortlink"]')
    if shortlink and shortlink.get("href"):
        match = re.search(r"/node/(\d+)", shortlink["href"])
        if match:
            node_id = match.group(1)
    if not node_id:
        body = soup.select_one("body")
        match = re.search(r"page-node-(\d+)", " ".join(body.get("class", []))) if body else None
        if match:
            node_id = match.group(1)

    description = ""
    body_field = soup.select_one(BODY_SELECTOR)
    if body_field is not None:
        paragraphs = extract_paragraphs(body_field)
        description = paragraphs[0] if paragraphs else ""

    meta = BookMeta(
        url=book_url,
        slug=slug_from_url(book_url),
        title=title,
        node_id=node_id,
        authors=_field_values(soup, "field-author"),
        translators=_field_values(soup, "field-translator"),
        publishers=_field_values(soup, "field-publisher"),
        tags=_field_values(soup, "field-tags"),
        description=description,
    )

    chapters: list[ChapterRef] = []
    seen: set[str] = set()
    toc = soup.select_one(TOC_SELECTOR)
    if toc is not None:
        for item in toc.select("li"):
            anchor = item.find("a", href=True)
            if anchor is None:
                continue
            href = anchor["href"]
            if not _is_internal_content_link(href):
                continue
            url = canonical_url(href)
            if url == book_url or url in seen:
                continue
            seen.add(url)
            depth_match = re.search(r"menu-depth-(\d+)", " ".join(item.get("class", [])))
            chapters.append(
                ChapterRef(
                    url=url,
                    slug=slug_from_url(url),
                    title=_clean_inline(anchor.get_text(" ")),
                    depth=int(depth_match.group(1)) if depth_match else 0,
                    order=len(chapters) + 1,
                )
            )

    return meta, chapters


def parse_chapter_page(html: str, page_url: str) -> dict:
    """Parse a chapter page into ``{heading, text, footnotes}``."""
    soup = BeautifulSoup(html, "html.parser")

    article = soup.select_one("article.node-book") or soup.select_one("article") or soup
    body = article.select_one(BODY_SELECTOR)
    if body is None:
        body = soup.select_one(BODY_SELECTOR)

    heading_el = article.select_one("h2")
    heading = _clean_inline(heading_el.get_text(" ")) if heading_el else ""

    if body is None:
        return {"heading": heading, "text": "", "footnotes": ""}

    # Footnotes render as a `ul.footnotes` list at the end of the body field,
    # so pull them out first or they get read as trailing prose.
    footnote_parts: list[str] = []
    for node in body.select(".footnotes"):
        footnote_parts.extend(extract_paragraphs(node))
        node.decompose()

    # Inline `[1]` reference anchors would otherwise leave stray digits in the
    # middle of sentences.
    for marker in body.select("a.see-footnote, sup.see-footnote-ref"):
        marker.decompose()

    return {
        "heading": heading,
        "text": "\n\n".join(extract_paragraphs(body)),
        "footnotes": "\n".join(footnote_parts),
    }


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

class BrowserFetcher:
    """Polite, disk-cached page fetcher backed by a real browser.

    A real browser is required because Cloudflare answers plain HTTP clients
    with a 403 interstitial.  The browser profile is persisted between runs so
    clearance cookies survive, and every response is cached on disk so a run
    interrupted partway through does not re-request pages it already has.
    """

    def __init__(
        self,
        *,
        delay: float = CRAWL_DELAY,
        cache_dir: Path | None = None,
        profile_dir: Path | None = None,
        headless: bool = False,
        timeout_ms: int = 60_000,
    ) -> None:
        self.delay = delay
        self.cache_dir = Path(cache_dir) if cache_dir else AL_ISLAM_RAW / "_html_cache"
        self.profile_dir = Path(profile_dir) if profile_dir else AL_ISLAM_RAW / "_browser_profile"
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._context = None
        self._page = None
        self._last_fetch = 0.0
        self.network_fetches = 0
        self.cache_hits = 0
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- lifecycle ------------------------------------------------------
    def __enter__(self) -> BrowserFetcher:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _ensure_browser(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "playwright is required to fetch al-islam.org.  Install it with:\n"
                "  pip install playwright && python -m playwright install chromium"
            ) from exc

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        launch_kwargs = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.headless,
            "locale": "en-US",
            "viewport": {"width": 1280, "height": 900},
        }
        try:
            # Prefer the user's real Chrome; its fingerprint trips Cloudflare
            # far less often than the bundled build.
            self._context = self._playwright.chromium.launch_persistent_context(
                channel="chrome", **launch_kwargs
            )
        except Exception:
            # No system Chrome (any of several launch errors): fall back to the
            # Playwright-managed build.
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)

        self._context.set_default_timeout(self.timeout_ms)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    def close(self) -> None:
        for closer in (
            getattr(self._context, "close", None),
            getattr(self._playwright, "stop", None),
        ):
            if closer is not None:
                try:
                    closer()
                except Exception:
                    # Teardown is best-effort: a browser that already died must
                    # not mask the scrape's own error on the way out.
                    pass
        self._context = self._page = self._playwright = None

    # -- caching --------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
        return self.cache_dir / f"{slug_from_url(url)[:60]}.{digest}.html"

    def _sleep_for_politeness(self) -> None:
        elapsed = time.monotonic() - self._last_fetch
        remaining = self.delay - elapsed
        if self._last_fetch and remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _looks_like_challenge(title: str, html: str) -> bool:
        if any(marker in title.lower() for marker in _CHALLENGE_TITLES):
            return True
        return any(marker in html for marker in _CHALLENGE_MARKERS)

    def get(self, url: str, *, force: bool = False) -> str:
        """Return the HTML for *url*, from cache when possible."""
        url = canonical_url(url)
        cache_path = self._cache_path(url)
        if cache_path.exists() and not force:
            self.cache_hits += 1
            return cache_path.read_text(encoding="utf-8")

        self._ensure_browser()
        self._sleep_for_politeness()
        self._page.goto(url, wait_until="domcontentloaded")
        self._last_fetch = time.monotonic()
        self.network_fetches += 1

        html = self._page.content()
        if self._looks_like_challenge(self._page.title(), html):
            html = self._wait_out_challenge(url)

        cache_path.write_text(html, encoding="utf-8")
        return html

    def _wait_out_challenge(self, url: str, attempts: int = 12) -> str:
        """Poll while Cloudflare's interstitial resolves itself."""
        for _ in range(attempts):
            time.sleep(5)
            html = self._page.content()
            if not self._looks_like_challenge(self._page.title(), html):
                return html
        raise CloudflareChallenge(
            f"Cloudflare is still challenging {url} after waiting.\n"
            "Re-run with --no-headless and clear the challenge in the browser "
            "window; the profile is saved, so later runs reuse the clearance."
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _walk_author_pages(
    author_url: str,
    fetcher: BrowserFetcher,
    *,
    force: bool,
    max_pages: int,
):
    """Yield each page of an author's book listing, following the pager."""
    next_url: str | None = canonical_url(author_url)
    visited: set[str] = set()
    for _ in range(max_pages):
        if not next_url or next_url in visited:
            return
        visited.add(next_url)
        page = parse_author_page(fetcher.get(next_url, force=force), next_url)
        yield page
        next_url = page.next_url


def discover_books(
    author_url: str,
    fetcher: BrowserFetcher,
    *,
    max_pages: int = MAX_AUTHOR_PAGES,
    max_passes: int = MAX_DISCOVERY_PASSES,
) -> tuple[str, list[BookRef], int | None]:
    """Collect every distinct book link from an author page.

    The "N Books" heading counts view *rows*, not books.  The listing joins the
    author term against several node fields (author, translator, editor, ...),
    so a book credited to the scholar more than once occupies several rows and
    reappears on later ``?page=N`` requests.  Mutahhari's listing advertises 50
    rows that resolve to 33 distinct books: 7 books appear three times, 3 twice,
    and 23 once.

    Because of that, completeness cannot be judged from the advertised number.
    Instead the listing is walked again (bypassing the cache) and discovery
    stops once a full pass adds no new book, which is what confirms the set is
    complete.

    Returns ``(author_name, books, advertised_rows)``.
    """
    author_name = ""
    advertised: int | None = None
    found: dict[str, BookRef] = {}

    for pass_number in range(max_passes):
        before = len(found)
        for page in _walk_author_pages(
            author_url, fetcher, force=pass_number > 0, max_pages=max_pages
        ):
            author_name = author_name or page.author_name
            advertised = advertised or page.advertised_rows
            for book in page.books:
                found.setdefault(book.url, book)

        if pass_number and len(found) == before:
            break  # A full pass added nothing new: the set is complete.
        if pass_number + 1 < max_passes:
            print(f"  pass {pass_number + 1}: {len(found)} distinct book(s), verifying ...")

    if advertised is not None and len(found) < advertised:
        print(
            f"  {len(found)} distinct books from {advertised} listing rows "
            f"({advertised - len(found)} duplicate credits collapsed)."
        )

    return author_name, list(found.values()), advertised


def _load_done_chapter_urls(path: Path) -> set[str]:
    """Return chapter URLs already present in an output JSONL file."""
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["chapter_url"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def scrape_author(
    author_url: str,
    *,
    fetcher: BrowserFetcher,
    output_dir: Path | None = None,
    max_books: int | None = None,
    author_name_override: str = "",
) -> dict:
    """Scrape every book by one author into ``chapters.jsonl``.

    Chapters are appended as they are fetched and chapters already present in
    the output file are skipped, so a long run can be stopped and resumed.
    """
    author_url = canonical_url(author_url)
    author_slug = slug_from_url(author_url)
    out_dir = Path(output_dir) if output_dir else AL_ISLAM_RAW / author_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters_path = out_dir / "chapters.jsonl"
    manifest_path = out_dir / "books.json"

    print(f"Discovering books for {author_url} ...")
    discovered_name, books, _advertised = discover_books(author_url, fetcher)
    author_name = author_name_override or discovered_name or author_slug
    # Sort by slug so a resumed run processes books in the same order.
    books.sort(key=lambda b: b.slug)
    if max_books is not None:
        books = books[:max_books]
    print(f"  {author_name}: {len(books)} book(s) to scrape")

    already_done = _load_done_chapter_urls(chapters_path)
    if already_done:
        print(f"  Resuming: {len(already_done)} chapter(s) already scraped")

    manifest: list[dict] = []
    chapter_count = 0
    empty_chapters: list[str] = []

    with chapters_path.open("a", encoding="utf-8") as sink:
        for position, book in enumerate(books, start=1):
            meta, toc = parse_book_page(fetcher.get(book.url), book.url)
            book_title = meta.title or book.slug
            print(f"  [{position}/{len(books)}] {book_title} -- {len(toc)} chapter(s)")

            manifest.append({**asdict(meta), "chapter_count": len(toc)})
            manifest_path.write_text(
                json.dumps(
                    {"author_slug": author_slug, "author_name": author_name, "books": manifest},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            for chapter in toc:
                if chapter.url in already_done:
                    continue
                parsed = parse_chapter_page(fetcher.get(chapter.url), chapter.url)
                if not parsed["text"]:
                    empty_chapters.append(chapter.url)

                record = {
                    "author_slug": author_slug,
                    "author_name": author_name,
                    "book_title": book_title,
                    "book_slug": meta.slug,
                    "book_url": meta.url,
                    "book_node_id": meta.node_id,
                    "book_translators": meta.translators,
                    "book_publishers": meta.publishers,
                    "book_tags": meta.tags,
                    "chapter_order": chapter.order,
                    "chapter_depth": chapter.depth,
                    "chapter_title": chapter.title or parsed["heading"],
                    "chapter_slug": chapter.slug,
                    "chapter_url": chapter.url,
                    "text": parsed["text"],
                    "footnotes": parsed["footnotes"],
                    "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
                already_done.add(chapter.url)
                chapter_count += 1

    summary = {
        "author_slug": author_slug,
        "author_name": author_name,
        "books": len(books),
        "chapters_written": chapter_count,
        "empty_chapters": empty_chapters,
        "network_fetches": fetcher.network_fetches,
        "cache_hits": fetcher.cache_hits,
        "output": str(chapters_path),
    }
    print(
        f"\nDone: {chapter_count} chapter(s) from {len(books)} book(s)\n"
        f"  {chapters_path}\n"
        f"  network fetches={fetcher.network_fetches}, cache hits={fetcher.cache_hits}"
    )
    if empty_chapters:
        print(f"  Warning: {len(empty_chapters)} chapter(s) had no text")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape al-islam.org books for one author (/person/<slug> page)."
    )
    parser.add_argument(
        "--author-url",
        required=True,
        help="Author page, e.g. https://al-islam.org/person/murtadha-mutahhari",
    )
    parser.add_argument("--output-dir", default=None, help="Defaults to data/raw/shia/al-islam/<slug>/")
    parser.add_argument(
        "--delay",
        type=float,
        default=CRAWL_DELAY,
        help=f"Seconds between network requests (default {CRAWL_DELAY:g}, per robots.txt)",
    )
    parser.add_argument("--max-books", type=int, default=None, help="Only scrape the first N books")
    parser.add_argument("--author-name", default="", help="Override the display name for the author")
    parser.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        default=False,
        help="Run the browser headless (more likely to be challenged by Cloudflare)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Print the discovered book URLs and exit without scraping chapters",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with BrowserFetcher(delay=args.delay, headless=args.headless) as fetcher:
        if args.list_only:
            author_name, books, advertised = discover_books(args.author_url, fetcher)
            print(
                f"{author_name}: {len(books)} distinct book(s)"
                + (f" from {advertised} listing rows" if advertised else "")
            )
            for book in sorted(books, key=lambda b: b.slug):
                print(f"  {book.url}")
            return 0

        scrape_author(
            args.author_url,
            fetcher=fetcher,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            max_books=args.max_books,
            author_name_override=args.author_name,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
