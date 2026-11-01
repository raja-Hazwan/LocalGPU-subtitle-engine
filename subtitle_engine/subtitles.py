"""Subtitle cues: grouping timed words into cues, SRT/VTT formatting and timestamp parsing."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

MIN_CUE_DURATION = 0.5


@dataclass
class Word:
    text: str  # Whisper words carry their leading space, e.g. " awak"
    start: float
    end: float


@dataclass
class Cue:
    start: float
    end: float
    text: str


def group_words(words: list[Word], max_chars: int = 42, max_duration: float = 5.0,
                gap_split: float = 0.6) -> list[Cue]:
    """Group words into cues, breaking on a long pause, line length or cue duration."""
    groups: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current:
            text = "".join(x.text for x in current + [word]).strip()
            if (len(text) > max_chars
                    or word.end - current[0].start > max_duration
                    or word.start - current[-1].end > gap_split):
                groups.append(current)
                current = []
        current.append(word)
    if current:
        groups.append(current)

    cues = []
    for i, group in enumerate(groups):
        start = group[0].start
        end = max(group[-1].end, start + MIN_CUE_DURATION)
        if i + 1 < len(groups):
            end = min(end, groups[i + 1][0].start)  # never overlap the next cue
        cues.append(Cue(start, end, "".join(x.text for x in group).strip()))
    return cues


_SENTENCE_END = (".", "?", "!")


def group_sentences(words: list[Word], max_duration: float = 15.0, gap_split: float = 1.5) -> list[list[Word]]:
    """Group words into sentences for translation: break after . ? !, on a long pause, or when too long."""
    sentences: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and (word.start - current[-1].end > gap_split
                        or word.end - current[0].start > max_duration):
            sentences.append(current)
            current = []
        current.append(word)
        if word.text.strip().endswith(_SENTENCE_END):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)
    return sentences


def sentence_text(words: list[Word]) -> str:
    return "".join(w.text for w in words).strip()


def _split_balanced(tokens: list[str], parts: int) -> list[list[str]]:
    """Split tokens into `parts` runs of roughly equal character length (by each token's midpoint)."""
    total = sum(len(t) + 1 for t in tokens)
    chunks: list[list[str]] = [[] for _ in range(parts)]
    pos = 0
    for token in tokens:
        mid = pos + (len(token) + 1) / 2
        chunks[min(int(mid / total * parts), parts - 1)].append(token)
        pos += len(token) + 1
    return [c for c in chunks if c]


def split_translation(text: str, start: float, end: float, max_chars: int = 42,
                      max_duration: float = 5.0) -> list[Cue]:
    """Split one translated sentence into cues spanning [start, end], timed by character share."""
    tokens = text.split()
    if not tokens:
        return []
    parts = max(math.ceil(len(text) / max_chars), math.ceil((end - start) / max_duration), 1)
    parts = min(parts, len(tokens))
    chunks = _split_balanced(tokens, parts)
    while parts < len(tokens) and any(len(" ".join(c)) > max_chars for c in chunks):
        parts += 1
        chunks = _split_balanced(tokens, parts)

    lines = [" ".join(c) for c in chunks]
    total = sum(len(line) for line in lines)
    cues, t = [], start
    for line in lines:
        t_end = t + (end - start) * len(line) / total
        cues.append(Cue(t, t_end, line))
        t = t_end
    cues[-1].end = end
    return cues


def translated_cues(sentences: list[list[Word]], translations: list[str], max_chars: int = 42,
                    max_duration: float = 5.0) -> list[Cue]:
    """Lay translated sentences back onto the timeline of the original (source-language) words."""
    cues: list[Cue] = []
    for i, (words, text) in enumerate(zip(sentences, translations)):
        start = words[0].start
        end = max(words[-1].end, start + MIN_CUE_DURATION)
        if i + 1 < len(sentences):
            end = min(end, sentences[i + 1][0].start)  # never overlap the next sentence
        cues += split_translation(text, start, end, max_chars, max_duration)
    return cues


def format_timestamp(seconds: float, sep: str = ",") -> str:
    ms = int(round(max(seconds, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


_TS = re.compile(r"^\s*(\d+):([0-5]?\d):([0-5]?\d)(?:[.,](\d{1,3}))?\s*$")


def parse_timestamp(value: str) -> float:
    """Parse HH:MM:SS,mmm (or with '.') back to seconds. Raises ValueError on bad input."""
    match = _TS.match(value or "")
    if not match:
        raise ValueError(f"Invalid timestamp: {value!r} (expected HH:MM:SS,mmm)")
    h, m, s, frac = match.groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + (int(frac.ljust(3, "0")) / 1000 if frac else 0)


def _non_empty(cues: list[Cue]) -> list[Cue]:
    return [c for c in cues if c.text.strip()]


def to_srt(cues: list[Cue]) -> str:
    blocks = [f"{i}\n{format_timestamp(c.start)} --> {format_timestamp(c.end)}\n{c.text.strip()}\n"
              for i, c in enumerate(_non_empty(cues), 1)]
    return "\n".join(blocks)


def to_vtt(cues: list[Cue]) -> str:
    blocks = [f"{format_timestamp(c.start, '.')} --> {format_timestamp(c.end, '.')}\n{c.text.strip()}\n"
              for c in _non_empty(cues)]
    return "WEBVTT\n\n" + "\n".join(blocks)


def validate_cues(cues: list[Cue]) -> list[str]:
    """Return human-readable problems (1-based row numbers); empty list means OK."""
    errors = []
    for i, c in enumerate(cues, 1):
        if c.end <= c.start:
            errors.append(f"Row {i}: end time must be after start time")
    return errors
