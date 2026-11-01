import pytest

from subtitle_engine.arabic import has_arabic, romanize, romanize_text


@pytest.mark.parametrize("arabic, latin", [
    # exact tokens Whisper produced on the Rozaimi videos
    ("لَا", "la"),
    ("تَقُونُوا", "taqunu"),            # waw after damma = long u; trailing alif silent
    ("إِمَّعًا", "imma'an"),             # shadda doubles; tanwin fath + alif -> an
    ("وَطِنُوا", "watinu"),
    ("أَنفُسَكُمْ", "anfusakum"),          # bare nun -> n; sukun -> nothing
    # common religious phrases
    ("وَطِّنُوا", "wattinu"),
    ("إِمَّعَةً", "imma'atan"),           # ta marbuta with tanwin -> tan
    ("رَحْمَة", "rahmah"),               # bare ta marbuta -> h (Malay style)
    ("بِسْمِ", "bismi"),
    ("الْحَمْدُ", "al-hamdu"),           # moon letter: al-
    ("الرَّحْمَٰنِ", "ar-rahmani"),       # sun letter assimilates; dagger alif -> a
    ("ٱلرَّحِيمِ", "ar-rahimi"),          # alif wasla; ya after kasra = long i
    ("اللَّهِ", "Allah"),
    ("عَلَى", "'ala"),                   # ain -> '; alif maqsura -> a
    ("الْإِثْمِ", "al-ismi"),              # tha -> s (Malay simplified)
    ("مُؤْمِن", "mu'min"),               # hamza on waw mid-word -> '
    ("قُرْآن", "qur'an"),                # alif madda mid-word -> 'a
    ("يَوْم", "yawm"),                   # waw with sukun stays consonant
])
def test_romanize_words(arabic, latin):
    assert romanize(arabic) == latin


def test_romanize_text_keeps_latin_and_spacing():
    assert romanize_text("Nabi s.a.w. kata, لَا تَقُونُوا إِمَّعًا") == "Nabi s.a.w. kata, la taqunu imma'an"
    assert romanize_text(" وَطِنُوا") == " watinu"  # Whisper words keep their leading space
    assert romanize_text("Dalam hadis") == "Dalam hadis"


def test_arabic_punctuation_is_converted():
    assert romanize_text("لَا؟") == "la?"
    assert romanize_text("لَا، لَا") == "la, la"


def test_has_arabic():
    assert has_arabic(" إِمَّعًا") and not has_arabic("imma'ah")
