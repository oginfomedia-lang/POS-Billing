"""SKU prefixes: the first three letters of a category or product name, in English letters, for any script.

    sku_prefix("किराणा") == "KIR"     sku_prefix("साखर") == "SAK"     sku_prefix("तांदूळ") == "TAN"
    sku_prefix("Grocery") == "GRO"    sku_prefix("कोका कोला") == "KOK"  sku_prefix("Hair Oil") == "HAI"

Marathi is transliterated (spelt in Roman letters), never translated: साखर is SAKHAR, not SUGAR. The heavy
lifting (vowel signs, conjuncts such as क्ष / ज्ञ / द्ध, the inherent "a") is done by indic_transliteration;
before and after it, a few Marathi habits are applied that its Sanskrit-oriented IAST output lacks:
ऑ/ॲ, ं as n (m before प फ ब भ म), no "a" after a word's last consonant, श/ष as sh, च as ch, ज्ञ as dny.
"""
from __future__ import annotations

import re
import unicodedata

from indic_transliteration import sanscript

PREFIX_LEN = 3
CATEGORY_FALLBACK = "CAT"
PRODUCT_FALLBACK = "PRD"

_CONSONANT = re.compile(r"[क-हक़-य़ॹ-ॿ]")
_LABIALS = set("पफबभम")
_HALANT = "्"
_NUKTA = "़"
# A consonant's own marks: vowel signs, halant, nukta, anusvara, candrabindu, visarga.
_MARKS = re.compile(r"[ऀ-ःऺ-ॏॕ-ॗॢॣ]")
# Marathi letters the library leaves as they are, rewritten as the nearest ones it knows.
_MARATHI = str.maketrans({"ऑ": "ओ", "ॉ": "ो", "ॲ": "ए", "ॅ": "े"})


def _prepare(text: str) -> str:
    """Devanagari as Marathi is spoken, before transliteration: ं / ँ become a half न or म, and a word's last
    bare consonant gets a halant (साखर is sakhar, not sakhara)."""
    text = unicodedata.normalize("NFC", text).translate(_MARATHI)
    out = []
    for i, ch in enumerate(text):
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch in "ंँ":
            out.append(("म" if nxt in _LABIALS else "न") + _HALANT)
            continue
        out.append(ch)
        if _CONSONANT.match(ch) and not _MARKS.match(nxt) and nxt != _NUKTA:
            # The word ends here (space, punctuation, Latin, end): no inherent "a".
            if not _CONSONANT.match(nxt):
                out.append(_HALANT)
    return "".join(out)


_DEVANAGARI_RUN = re.compile(r"[ऀ-ॿ]+")


def _devanagari_to_latin(run: str) -> str:
    s = sanscript.transliterate(_prepare(run), sanscript.DEVANAGARI, sanscript.IAST)
    s = s.replace("jñ", "dny").replace("ch", "chh")  # IAST ch = छ
    s = re.sub(r"c(?!hh)", "ch", s)                   # IAST c = च
    for old, new in (("ś", "sh"), ("ṣ", "sh"), ("ṛ", "ru"), ("ṝ", "ru")):
        s = s.replace(old, new)
    return s


def to_latin(text: str | None) -> str:
    """The name in plain English letters (lower case): Marathi parts transliterated, English parts kept as typed."""
    if not text:
        return ""
    s = _DEVANAGARI_RUN.sub(lambda m: _devanagari_to_latin(m.group()), unicodedata.normalize("NFC", text))
    # Strip the remaining accents (ā → a, ṇ → n, ḷ → l, é → e ...).
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return s.lower()


def sku_prefix(name: str | None, fallback: str) -> str:
    """First PREFIX_LEN English letters of the name, upper case; short names are padded with X; a name with no
    usable letters at all (only digits, symbols, or an unknown script) gets the fallback."""
    letters = re.sub(r"[^a-z]", "", to_latin(name))
    if not letters:
        return fallback
    return letters[:PREFIX_LEN].upper().ljust(PREFIX_LEN, "X")
