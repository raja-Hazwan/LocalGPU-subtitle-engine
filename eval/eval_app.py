"""Run the app's real Transcriber on eval/video.mp4 and score it against eval/reference.srt."""
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from subtitle_engine.engine import setup_cuda_dlls  # noqa: E402

setup_cuda_dlls()
from run_eval import EVAL, REF, norm_words, srt_text, wer  # noqa: E402

from subtitle_engine.engine import Transcriber, extract_audio  # noqa: E402
from subtitle_engine.subtitles import to_srt  # noqa: E402
from subtitle_engine.vocabulary import Vocabulary  # noqa: E402

video = sys.argv[1] if len(sys.argv) > 1 else str(EVAL / "video.mp4")
t = Transcriber()
t.load()
audio = extract_audio(video)
ref = norm_words(srt_text(REF))
for label, vocab in [("app defaults", Vocabulary()), ("+ custom word 'dahsyat'", Vocabulary(custom_words=["dahsyat"]))]:
    cues = t.transcribe(audio, vocabulary=vocab)
    srt = to_srt(cues)
    (EVAL / f"app_{label.split()[0]}.srt").write_text(srt, encoding="utf-8")
    hyp = norm_words(" ".join(c.text for c in cues))
    rate, errs = wer(ref, hyp)
    print(f"{label:26s} WER {rate*100:5.2f}% ({errs} errs)  dahsyat {hyp.count('dahsyat')}/1  amanah {hyp.count('amanah')}/1  ta'zir {hyp.count(chr(116)+chr(97)+chr(39)+'zir')}/10")
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_opcodes():
        if op != "equal":
            print(f"    {' '.join(ref[max(0,i1-2):i1])} [{' '.join(ref[i1:i2]) or '_'} -> {' '.join(hyp[j1:j2]) or '_'}] {' '.join(ref[i2:i2+2])}")
