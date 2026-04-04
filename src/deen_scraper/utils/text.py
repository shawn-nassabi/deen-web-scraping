"""Text utilities: Islamic term normalization, compression, and preprocessing."""

from __future__ import annotations

import base64
import gzip
import re
import string


# ---------------------------------------------------------------------------
# Islamic terminology normalization
# ---------------------------------------------------------------------------
ISLAMIC_TERMS_MAP: dict[str, str] = {
    "salat": "salah",
    "salaah": "salah",
    "salaat": "salah",
    "zakaat": "zakat",
    "zakah": "zakat",
    "dhikr": "zikr",
    "dhikrullah": "zikr",
    "sawm": "fasting",
    "ramadhan": "ramadan",
    "hadeeth": "hadith",
    "sahabah": "companion",
    "sahabi": "companion",
    "sahaba": "companion",
    "koran": "quran",
    "hussein": "hussain",
    "hossein": "hussain",
    "mohamad": "muhammad",
    "muhamad": "muhammad",
    "mohamed": "muhammad",
    "wudhu": "wudu",
    "wuzu": "wudu",
}


# ---------------------------------------------------------------------------
# Arabic detection
# ---------------------------------------------------------------------------
ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
LATIN_RE = re.compile(r"[A-Za-z]")


def contains_arabic(text: str) -> bool:
    """Return True if *text* contains any Arabic script characters."""
    return bool(ARABIC_RE.search(text))


def contains_latin(text: str) -> bool:
    """Return True if *text* contains any Latin script characters."""
    return bool(LATIN_RE.search(text))


def is_arabic_only(text: str) -> bool:
    """Return True if *text* has Arabic but no Latin characters."""
    return contains_arabic(text) and not contains_latin(text)


# ---------------------------------------------------------------------------
# Compression helpers  (for storing text_ar/text_en in Pinecone metadata)
# ---------------------------------------------------------------------------

def compress_text(text: str) -> str:
    """Gzip-compress and base64-encode *text*."""
    if not text:
        return ""
    compressed = gzip.compress(text.encode("utf-8"))
    return base64.b64encode(compressed).decode("utf-8")


def decompress_text(compressed_text: str) -> str:
    """Decode and decompress base64-encoded gzip text."""
    if not compressed_text:
        return ""
    compressed_bytes = base64.b64decode(compressed_text.encode("utf-8"))
    return gzip.decompress(compressed_bytes).decode("utf-8")


# ---------------------------------------------------------------------------
# Normalisation for sparse (TF-IDF) vectorisation
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, and normalise common Islamic terms.

    Designed for use before TfidfVectorizer so that variant spellings map
    to the same token.
    """
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    words = text.split()
    normalized_words = [ISLAMIC_TERMS_MAP.get(word, word) for word in words]
    return " ".join(normalized_words)
