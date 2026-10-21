"""Sound-alike search key, so English letters find Marathi names (and loose spellings find either).

    search_key("मधुर साखर") == "mdhurskhr"     search_key("madhur sakhar") == "mdhurskhr"
    search_key("तांदूळ")     == "tndul"         search_key("Tandool") == search_key("tandul") == "tndul"

Devanagari is spelt out in Roman letters, then both scripts get the same loosening: no "a" at all (the
inherent a can't be written reliably), long and short vowels alike, ट/त ड/द ण/न ळ/ल श/ष written the same,
w = v, ph = f, z = j, ं as m before प फ ब भ म (आंबा = amba) and n elsewhere (कांदा = kanda), doubled letters
once, spaces and punctuation gone.
Products keep this in products.search_key; the search box's text gets the same treatment.
"""
from __future__ import annotations

import re

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}
_VOWELS = {
    # letters and vowel signs: long = short, ॲ/ऑ like e/o
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ru", "ए": "e", "ऐ": "ai", "ओ": "o",
    "औ": "au", "ॲ": "e", "ऑ": "o",
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ru", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ॅ": "e", "ॉ": "o",
    "ँ": "n", "ः": "h",
}
_LABIALS = {"प", "फ", "ब", "भ", "म"}
_SILENT = {"्", "़"}  # halant (joins consonants), nukta
_DIGITS = {chr(0x0966 + d): str(d) for d in range(10)}  # ० - ९

MIN_QUERY_KEY = 2  # shorter keys ("a", "s") would match almost everything


def devanagari_to_roman(text: str) -> str:
    """Spells Devanagari in Roman letters, roughly as people type it (inherent a left out)."""
    text = text.replace("ज्ञ", "dny").replace("क्ष", "ksh")
    out = []
    for i, ch in enumerate(text):
        if ch == "ं":  # anusvara: sounds m before p / b, n elsewhere
            out.append("m" if text[i + 1:i + 2] in _LABIALS else "n")
        elif ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _DIGITS:
            out.append(_DIGITS[ch])
        elif ch not in _SILENT:
            out.append(ch)
    return "".join(out)


def search_key(text: str | None) -> str:
    """The sound-alike key of a name or of what was typed in the search box ("" for nothing useful)."""
    if not text:
        return ""
    s = devanagari_to_roman(text).lower()
    for old, new in (("ph", "f"), ("ksh", "x"), ("chh", "ch"), ("w", "v"), ("z", "j"), ("q", "k"),
                     ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u")):
        s = s.replace(old, new)
    s = s.replace("a", "")
    s = re.sub(r"[^a-z0-9]", "", s)
    return re.sub(r"(.)\1+", r"\1", s)  # dabba = डबा, chikku = चिकू
