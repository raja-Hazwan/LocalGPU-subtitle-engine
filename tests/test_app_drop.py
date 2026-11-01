from subtitle_engine.app import first_video


def test_first_video_picks_first_supported_extension_case_insensitively():
    assert first_video(["C:/notes.txt", "C:/clip.MKV", "C:/b.mp4"]) == "C:/clip.MKV"


def test_first_video_none_when_no_video():
    assert first_video(["C:/a.srt", "", "C:/folder"]) is None
    assert first_video([]) is None
