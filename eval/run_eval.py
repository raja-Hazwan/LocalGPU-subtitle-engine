"""Score transcription settings against a hand-corrected reference SRT.

Usage: python eval/run_eval.py [config names...]   (run from the project root)
Writes eval/out_<config>.srt and prints WER + target-word hits per config.
"""
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from subtitle_engine.engine import SAMPLE_RATE, extract_audio, find_ffmpeg, setup_cuda_dlls  # noqa: E402

setup_cuda_dlls()
import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

from subtitle_engine.subtitles import Word, group_words, to_srt  # noqa: E402

EVAL = ROOT / "eval"
VIDEO = EVAL / "video.mp4"
REF = EVAL / "reference.srt"

BASE_PROMPT = ("Ceramah agama dalam Bahasa Melayu. Assalamualaikum, Allah, Rasulullah, "
               "subhanallah, alhamdulillah, insyaAllah, Al-Quran, hadis, ustaz, dakwah.")
# Generic Islamic / legal vocabulary — deliberately NOT tuned to this video's mistakes
# (no "dahsyat"), so the result says something about other videos too.
TERMS = ("amanah, pecah amanah, ta'zir, hudud, qisas, diyat, syariah, fiqh, fatwa, mazhab, "
         "zakat, sedekah, wakaf, riba, halal, haram, makruh, sunat, wajib, harus, maslahah, "
         "mudarat, taubat, dosa, pahala, akhirat, solat, puasa, haji, umrah")
RICH_PROMPT = ("Soal jawab dan ceramah agama Islam dalam Bahasa Melayu. Istilah: " + TERMS + ".")
HOTWORDS = TERMS
BASE_TERMS_PROMPT = BASE_PROMPT + " Istilah: " + TERMS + "."

CLEAN_FILTER = "highpass=f=80,lowpass=f=8000,afftdn=nf=-25,dynaudnorm=f=200:g=15"

CONFIGS = {
    "baseline": dict(),
    "prompt": dict(initial_prompt=RICH_PROMPT),
    "hotwords": dict(hotwords=HOTWORDS),
    "prompt+hot": dict(initial_prompt=RICH_PROMPT, hotwords=HOTWORDS),
    "beam10": dict(beam_size=10),
    "vadpad": dict(vad_parameters=dict(speech_pad_ms=600, min_silence_duration_ms=500)),
    "context": dict(condition_on_previous_text=True),
    "clean": dict(_clean=True),
    "prompt+vad": dict(initial_prompt=RICH_PROMPT,
                       vad_parameters=dict(speech_pad_ms=600, min_silence_duration_ms=500)),
    "prompt+vad+hot": dict(initial_prompt=RICH_PROMPT, hotwords=HOTWORDS,
                           vad_parameters=dict(speech_pad_ms=600, min_silence_duration_ms=500)),
    "novad": dict(vad_filter=False),
    "bt+vad": dict(initial_prompt=BASE_TERMS_PROMPT,
                   vad_parameters=dict(speech_pad_ms=600, min_silence_duration_ms=500)),
    "bt+vad+custom": dict(initial_prompt=BASE_TERMS_PROMPT[:-1] + ", dahsyat.",
                          vad_parameters=dict(speech_pad_ms=600, min_silence_duration_ms=500)),
    "bt+pad800": dict(initial_prompt=BASE_TERMS_PROMPT, vad_parameters=dict(speech_pad_ms=800)),
    "bt+vad1000": dict(initial_prompt=BASE_TERMS_PROMPT,
                       vad_parameters=dict(speech_pad_ms=600, min_silence_duration_ms=1000)),
    "best": dict(initial_prompt=RICH_PROMPT, hotwords=HOTWORDS, beam_size=10,
                 vad_parameters=dict(speech_pad_ms=600, min_silence_duration_ms=500)),
}

TARGETS = {"dahsyat": 1, "amanah": None, "ta'zir": None}  # None = count from reference


def norm_words(text: str) -> list[str]:
    text = text.lower().replace("takzir", "ta'zir").replace("’", "'")
    return [w for w in re.sub(r"[^\w'\- ]", " ", text).split() if w.strip("'-")]


def srt_text(path: Path) -> str:
    blocks = path.read_text(encoding="utf-8-sig").strip().split("\n\n")
    return " ".join(" ".join(b.split("\n")[2:]) for b in blocks)


def wer(ref: list[str], hyp: list[str]) -> tuple[float, int]:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[-1] / len(ref), d[-1]


def clean_audio(video: Path) -> np.ndarray:
    cmd = [find_ffmpeg(), "-nostdin", "-v", "error", "-i", str(video), "-vn", "-af", CLEAN_FILTER,
           "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.float32)


def main(names: list[str]) -> None:
    ref_words = norm_words(srt_text(REF))
    targets = {t: n if n else ref_words.count(t) for t, n in TARGETS.items()}
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    audio_plain = extract_audio(str(VIDEO))
    audio_clean = None
    print(f"reference: {len(ref_words)} words; targets {targets}")
    for name in names:
        cfg = dict(CONFIGS[name])
        use_clean = cfg.pop("_clean", False)
        if use_clean and audio_clean is None:
            audio_clean = clean_audio(VIDEO)
        params = dict(language="ms", word_timestamps=True, vad_filter=True, beam_size=5,
                      condition_on_previous_text=False, initial_prompt=BASE_PROMPT)
        params.update(cfg)
        t0 = time.time()
        segments, _ = model.transcribe(audio_clean if use_clean else audio_plain, **params)
        words = [Word(w.word, w.start, w.end) for s in segments for w in (s.words or [])]
        secs = time.time() - t0
        srt = to_srt(group_words(words))
        (EVAL / f"out_{name}.srt").write_text(srt, encoding="utf-8")
        hyp = norm_words("".join(w.text for w in words))  # word texts carry their own leading space
        rate, errs = wer(ref_words, hyp)
        hits = {t: f"{hyp.count(t)}/{n}" for t, n in targets.items()}
        print(f"{name:11s} WER {rate * 100:5.2f}% ({errs:3d} errs)  {hits}  {secs:5.1f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(CONFIGS))
