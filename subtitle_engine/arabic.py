"""Romanize vowelled Arabic (as Whisper outputs it for quoted hadith / Quran) into Malay-style Latin.

Simplified Malay transliteration as used in ceramah subtitles: ش→sy, ث→s, ذ→z, ص→s, ض→d,
ط→t, ظ→z, ع→', ة→h (t before a vowel), article al-/ar-/as-... (sun letters assimilate).
Relies on the harakat Whisper emits; unvowelled text degrades to a consonant skeleton.
"""
from __future__ import annotations

import re

FATHA, DAMMA, KASRA = "َ", "ُ", "ِ"
TAN_FATH, TAN_DAMM, TAN_KASR = "ً", "ٌ", "ٍ"
SHADDA, SUKUN, DAGGER_ALIF = "ّ", "ْ", "ٰ"
MARKS = {FATHA, DAMMA, KASRA, TAN_FATH, TAN_DAMM, TAN_KASR, SHADDA, SUKUN, DAGGER_ALIF,
         "ٓ", "ٔ", "ٕ", "ـ"}  # + maddah, combining hamzas, tatweel (ignored)
VOWELS = {FATHA: "a", KASRA: "i", DAMMA: "u", TAN_FATH: "an", TAN_KASR: "in", TAN_DAMM: "un"}

ALIF, ALIF_WASLA, ALIF_MADDA = "ا", "ٱ", "آ"
HAMZAS = {"أ": "a", "إ": "i", "ؤ": "", "ئ": "", "ء": ""}  # default start vowel
WAW, YA, ALIF_MAQSURA, TA_MARBUTA, LAM = "و", "ي", "ى", "ة", "ل"

CONSONANTS = {
    "ب": "b", "ت": "t", "ث": "s", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "sy",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "'", "غ": "gh",
    "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", WAW: "w", YA: "y",
}
SUN_LETTERS = set("تثدذرزسشصضطظلن")
PUNCT = {"،": ",", "؟": "?", "؛": ";"}

_ARABIC_RUN = re.compile(r"[ء-غـ-ٰٕٱ]+")


def has_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)


def _units(word: str) -> list[tuple[str, str]]:
    """Split into (letter, marks) pairs."""
    units: list[tuple[str, str]] = []
    for ch in word:
        if ch in MARKS:
            if units:
                units[-1] = (units[-1][0], units[-1][1] + ch)
        else:
            units.append((ch, ""))
    return units


def _vowel(marks: str) -> str | None:
    for m in marks:
        if m in VOWELS:
            return VOWELS[m]
    if DAGGER_ALIF in marks:
        return "a"
    return None


def _letters(units: list[tuple[str, str]]) -> str:
    out: list[str] = []
    prev_vowel: str | None = None
    for i, (ch, marks) in enumerate(units):
        start = i == 0
        vowel = _vowel(marks)
        if ch in (ALIF, ALIF_WASLA):
            # long a after fatha / tanwin fath, silent alif after plural waw, else plain "a"
            if start:
                out.append(vowel or "")
            elif prev_vowel in ("a", "an") or (i == len(units) - 1 and units[i - 1][0] == WAW):
                pass
            else:
                out.append(vowel or "a")
        elif ch == ALIF_MADDA:
            out.append("a" if start else "'a")
        elif ch in HAMZAS:
            out.append(("" if start else "'") + (vowel if vowel is not None else (HAMZAS[ch] if start else "")))
        elif ch == ALIF_MAQSURA:
            if prev_vowel != "a":
                out.append("a")
        elif ch == TA_MARBUTA:
            out.append("t" + vowel if vowel else "h")
        elif ch == WAW and not marks and prev_vowel == "u" and not start:
            pass  # long u
        elif ch == YA and not marks and prev_vowel == "i" and not start:
            pass  # long i
        elif ch in CONSONANTS:
            cons = CONSONANTS[ch]
            if SHADDA in marks:
                cons = cons[0] + cons
            out.append(cons + (vowel or ""))
        else:
            out.append(ch)
        if vowel is not None or ch in CONSONANTS or ch in HAMZAS:
            prev_vowel = vowel
    return "".join(out)


def romanize(word: str) -> str:
    """Romanize a single Arabic word."""
    skeleton = "".join(ch for ch in word if ch not in MARKS).replace(ALIF_WASLA, ALIF)
    if skeleton == "الله":  # الله
        return "Allah"
    units = _units(word)
    if len(units) > 2 and units[0][0] in (ALIF, ALIF_WASLA) and units[1][0] == LAM:
        third, marks = units[2]
        rest = [(third, marks.replace(SHADDA, ""))] + units[3:]
        if third in SUN_LETTERS:
            return "a" + CONSONANTS[third] + "-" + _letters(rest)
        return "al-" + _letters(rest)
    return _letters(units)


def romanize_text(text: str) -> str:
    """Romanize every Arabic word in mixed Malay/Arabic text, leaving Latin text untouched."""
    for ar, latin in PUNCT.items():
        text = text.replace(ar, latin)
    return _ARABIC_RUN.sub(lambda m: romanize(m.group(0)), text)
