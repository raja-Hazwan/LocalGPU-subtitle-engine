import pytest

from subtitle_engine.subtitles import (
    Word,
    group_sentences,
    sentence_text,
    split_translation,
    translated_cues,
    validate_cues,
)


def w(text, start, end):
    return Word(text=text, start=start, end=end)


def test_group_sentences_breaks_after_terminal_punctuation():
    words = [w(" Hello", 0, 0.4), w(" there.", 0.4, 0.8), w(" How", 1.0, 1.2), w(" are", 1.2, 1.4),
             w(" you?", 1.4, 1.8), w(" Fine", 2.0, 2.3)]
    assert [sentence_text(s) for s in group_sentences(words)] == ["Hello there.", "How are you?", "Fine"]


def test_group_sentences_breaks_on_long_pause_and_max_duration():
    words = [w(" one", 0, 0.5), w(" two", 3.0, 3.5)]  # 2.5 s pause
    assert len(group_sentences(words, gap_split=1.5)) == 2
    words = [w(f" w{i}", i, i + 0.9) for i in range(20)]  # no punctuation, 20 s of speech
    assert all(s[-1].end - s[0].start <= 15.0 for s in group_sentences(words, max_duration=15.0))


def test_split_translation_short_sentence_is_one_cue_spanning_the_sentence():
    cues = split_translation("Apa khabar?", 1.0, 2.5)
    assert len(cues) == 1
    assert (cues[0].start, cues[0].end, cues[0].text) == (1.0, 2.5, "Apa khabar?")


def test_split_translation_long_sentence_respects_char_limit_and_covers_span():
    text = ("Jadi hari ini kita akan bercakap tentang bagaimana untuk membina "
            "perniagaan kecil dari awal tanpa modal yang besar.")
    cues = split_translation(text, 10.0, 18.0)
    assert len(cues) >= 3
    assert all(len(c.text) <= 42 for c in cues)
    assert " ".join(c.text for c in cues) == text
    assert cues[0].start == 10.0 and cues[-1].end == 18.0
    assert all(a.end == pytest.approx(b.start) for a, b in zip(cues, cues[1:]))
    assert not validate_cues(cues)


def test_split_translation_splits_long_durations_even_for_short_text():
    cues = split_translation("Baiklah kita mula sekarang", 0.0, 12.0, max_duration=5.0)
    assert len(cues) == 3
    assert " ".join(c.text for c in cues) == "Baiklah kita mula sekarang"


def test_split_translation_empty_text_gives_no_cues():
    assert split_translation("   ", 0.0, 1.0) == []


def test_translated_cues_follow_source_timing_without_overlap():
    sentences = [[w(" Hello.", 0.0, 1.0)], [w(" Thank", 0.8, 1.5), w(" you.", 1.5, 2.0)]]
    cues = translated_cues(sentences, ["Helo.", "Terima kasih."])
    assert [c.text for c in cues] == ["Helo.", "Terima kasih."]
    assert cues[0].end <= cues[1].start
    assert cues[1].end == 2.0
