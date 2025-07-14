import re
import string
import base64
import gzip

# Normalize Islamic terminology
ISLAMIC_TERMS_MAP = {
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
    "wuzu": "wudu"
}


def compress_text(text: str) -> str:
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


def normalize_text(text: str) -> str:
    # Lowercase
    text = text.lower()

    # Remove punctuation
    text = text.translate(str.maketrans("", "", string.punctuation))

    # Normalize Islamic terms
    words = text.split()
    normalized_words = [ISLAMIC_TERMS_MAP.get(word, word) for word in words]

    return " ".join(normalized_words)
