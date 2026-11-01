"""Prompt vocabulary and post-transcription auto-corrections (persisted per user)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

BASE_PROMPT = (
    "Ceramah agama dalam Bahasa Melayu. Assalamualaikum, Allah, Rasulullah, "
    "subhanallah, alhamdulillah, insyaAllah, Al-Quran, hadis, ustaz, dakwah."
)
# Generic Islamic / legal vocabulary. In testing this fixed "amanah" and "ta'zir" without
# being tuned to one video. (Passing these as faster-whisper `hotwords` instead made
# accuracy worse, so they go in the prompt.)
TERMS = [
    "amanah", "pecah amanah", "ta'zir", "hudud", "qisas", "diyat", "syariah", "fiqh", "fatwa",
    "mazhab", "zakat", "sedekah", "wakaf", "riba", "halal", "haram", "makruh", "sunat", "wajib",
    "harus", "maslahah", "mudarat", "taubat", "dosa", "pahala", "akhirat", "solat", "puasa",
    "haji", "umrah",
]
DEFAULT_CORRECTIONS = {"rasyak": "dahsyat", "takzi": "ta'zir", "taqunu": "takunu"}


def build_prompt(custom_words: list[str]) -> str:
    return f"{BASE_PROMPT} Istilah: {', '.join(TERMS + list(custom_words))}."


def parse_words(text: str) -> list[str]:
    return [w.strip() for w in re.split(r"[,\n]", text) if w.strip()]


def parse_corrections(text: str) -> dict[str, str]:
    rules = {}
    for line in text.splitlines():
        if "=" in line:
            wrong, right = (part.strip() for part in line.split("=", 1))
            if wrong and right:
                rules[wrong] = right
    return rules


def _match_case(src: str, repl: str) -> str:
    return repl[:1].upper() + repl[1:] if src[:1].isupper() else repl


def apply_corrections(text: str, corrections: dict[str, str]) -> str:
    """Replace whole words/phrases, case-insensitively, keeping a leading capital."""
    for wrong, right in corrections.items():
        pattern = re.compile(rf"(?<![\w']){re.escape(wrong)}(?![\w'])", re.IGNORECASE)
        text = pattern.sub(lambda m: _match_case(m.group(0), right), text)
    return text


def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / "SubtitleEngine" / "settings.json"


@dataclass
class Vocabulary:
    custom_words: list[str] = field(default_factory=list)
    corrections: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CORRECTIONS))

    @classmethod
    def load(cls, path: Path | None = None) -> "Vocabulary":
        try:
            data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
            return cls(custom_words=list(data.get("custom_words", [])),
                       corrections=dict(data.get("corrections", DEFAULT_CORRECTIONS)))
        except (OSError, ValueError, AttributeError):
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
