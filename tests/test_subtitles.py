import pytest

from subtitle_engine.subtitles import (
    Cue,
    Word,
    format_timestamp,
    group_words,
    parse_timestamp,
    to_srt,
    to_vtt,
    validate_cues,
)


def w(text, start, end):
    return Word(text=text, start=start, end=end)


def test_format_timestamp_srt_and_vtt():
    assert format_timestamp(3725.042) == "01:02:05,042"
    assert format_timestamp(3725.042, sep=".") == "01:02:05.042"
    assert format_timestamp(0) == "00:00:00,000"


def test_parse_timestamp_accepts_both_separators_and_round_trips():
    assert parse_timestamp("01:02:05,042") == pytest.approx(3725.042)
    assert parse_timestamp("00:00:01.5") == pytest.approx(1.5)
    assert parse_timestamp(format_timestamp(12.345)) == pytest.approx(12.345)


@pytest.mark.parametrize("bad", ["", "1:2", "aa:bb:cc,ddd", "00:61:00,000"])
def test_parse_timestamp_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_timestamp(bad)


def test_group_words_splits_on_pause_length_and_duration():
    words = [
        w(" Salah", 0.0, 0.4), w(" awak", 0.5, 0.8), w(" buat", 0.9, 1.2),
        # 1.0s pause -> new cue
        w(" Oh,", 2.2, 2.5), w(" awak", 2.6, 2.9),
    ]
    cues = group_words(words, max_chars=42, max_duration=5.0, gap_split=0.6)
    assert [c.text for c in cues] == ["Salah awak buat", "Oh, awak"]
    assert cues[0].start == 0.0 and cues[0].end == pytest.approx(1.2)

    long_words = [w(f" kata{i}", i * 0.3, i * 0.3 + 0.25) for i in range(20)]
    for c in group_words(long_words, max_chars=42, max_duration=5.0, gap_split=0.6):
        assert len(c.text) <= 42


def test_group_words_never_overlaps_and_has_min_length():
    words = [w(" a", 0.0, 0.05), w(" b", 0.7, 0.75)]
    cues = group_words(words, max_chars=42, max_duration=5.0, gap_split=0.6)
    assert len(cues) == 2
    assert cues[0].end <= cues[1].start
    assert cues[1].end - cues[1].start >= 0.5


def test_srt_and_vtt_output():
    cues = [Cue(0.0, 1.5, "Hai semua"), Cue(2.0, 3.25, "Apa khabar?")]
    assert to_srt(cues) == (
        "1\n00:00:00,000 --> 00:00:01,500\nHai semua\n\n"
        "2\n00:00:02,000 --> 00:00:03,250\nApa khabar?\n"
    )
    vtt = to_vtt(cues)
    assert vtt.startswith("WEBVTT\n\n")
    assert "00:00:02.000 --> 00:00:03.250\nApa khabar?" in vtt


def test_export_skips_empty_cues():
    cues = [Cue(0.0, 1.0, "  "), Cue(1.0, 2.0, "Ada")]
    assert to_srt(cues).startswith("1\n00:00:01,000")


def test_validate_cues_reports_bad_rows():
    cues = [Cue(0.0, 1.0, "ok"), Cue(2.0, 1.5, "end before start")]
    errors = validate_cues(cues)
    assert len(errors) == 1 and "2" in errors[0]
