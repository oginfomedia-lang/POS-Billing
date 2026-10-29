"""SKU prefixes: three English letters from a Marathi or English name (transliterated, never translated)."""
import pytest

from app.utils.sku_prefix import CATEGORY_FALLBACK, PRODUCT_FALLBACK, sku_prefix, to_latin


@pytest.mark.parametrize("name, latin, prefix", [
    # Marathi
    ("किराणा", "kirana", "KIR"),
    ("साखर", "sakhar", "SAK"),
    ("तांदूळ", "tandul", "TAN"),
    ("पेये", "peye", "PEY"),
    ("दूध", "dudh", "DUD"),
    ("कोका कोला", "koka kola", "KOK"),
    ("केसांचे तेल", "kesanche tel", "KES"),
    ("दुग्धजन्य पदार्थ", "dugdhajany padarth", "DUG"),
    # English, as typed
    ("Grocery", "grocery", "GRO"),
    ("Sugar", "sugar", "SUG"),
    ("Personal Care", "personal care", "PER"),
    ("Hair Oil", "hair oil", "HAI"),
    ("Coca Cola", "coca cola", "COC"),
])
def test_examples(name, latin, prefix):
    assert to_latin(name) == latin
    assert sku_prefix(name, PRODUCT_FALLBACK) == prefix


@pytest.mark.parametrize("name, prefix", [
    ("मसाला", "MAS"),            # inherent a inside a word is kept
    ("गहू", "GAH"),
    ("क्षीर", "KSH"),             # conjuncts
    ("ज्ञानेश्वर", "DNY"),
    ("श्रीखंड", "SHR"),
    ("कृष्णा", "KRU"),            # vowel sign ृ
    ("आंबा", "AMB"),             # anusvara before a labial = m
    ("शेंगदाणे", "SHE"),
    ("ऑईल", "OIL"),              # Marathi ऑ / ॉ / ॲ / ॅ
    ("कॉफी", "KOP"),
    ("मॅगी", "MEG"),
    ("चहा", "CHA"),
    ("छत्री", "CHH"),
])
def test_matras_conjuncts_and_marathi_letters(name, prefix):
    assert sku_prefix(name, PRODUCT_FALLBACK) == prefix


@pytest.mark.parametrize("name, prefix", [
    ("Amul दूध", "AMU"),          # mixed: English first
    ("दूध Amul", "DUD"),          # mixed: Marathi first
    ("साखर 1kg", "SAK"),          # numbers ignored
    ("पोहे (जाड)", "POH"),         # punctuation ignored
    ("Parle-G 100g!", "PAR"),
    ("  Tea  ", "TEA"),
    ("7 Up", "UPX"),             # fewer than three letters: padded with X
    ("७ अप", "APX"),             # Devanagari digits too
    ("Café", "CAF"),             # accents dropped
])
def test_spaces_digits_punctuation_and_short_names(name, prefix):
    assert sku_prefix(name, PRODUCT_FALLBACK) == prefix


@pytest.mark.parametrize("name", ["", None, "   ", "123", "!!!", "--- 42 ---", "日本"])
def test_no_usable_letters_uses_the_fallback(name):
    assert sku_prefix(name, CATEGORY_FALLBACK) == "CAT"
    assert sku_prefix(name, PRODUCT_FALLBACK) == "PRD"


def test_unicode_is_normalised():
    # The same word typed as decomposed characters (e.g. pasted from another app) gives the same prefix.
    import unicodedata
    assert sku_prefix(unicodedata.normalize("NFD", "Café"), PRODUCT_FALLBACK) == "CAF"
    assert sku_prefix(unicodedata.normalize("NFD", "कॉफी"), PRODUCT_FALLBACK) == "KOP"


def test_prefix_is_always_three_upper_case_letters():
    for name in ["किराणा", "a", "Zz", "क", "", "x y z", "Ωmega"]:
        p = sku_prefix(name, PRODUCT_FALLBACK)
        assert len(p) == 3 and p.isalpha() and p.isupper() and p.isascii()
