"""Offline transcription with faster-whisper: GPU (CUDA float16) with CPU (int8) fallback.

Malay speech is transcribed directly. English speech is transcribed in English, then translated
to Malay sentence by sentence (see translate.py)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .arabic import romanize_text
from .subtitles import Cue, Word, group_sentences, group_words, translated_cues
from .vocabulary import Vocabulary, apply_corrections, build_prompt

LANGUAGE = "ms"
ENGLISH = "en"  # English speech -> Malay subtitles (translated)
MODEL_NAME = "large-v3"
SAMPLE_RATE = 16_000
# Wider speech padding + shorter silence splits: recovered phrases the default VAD dropped
# and fixed clipped words (see eval/run_eval.py, config "bt+vad").
VAD_PARAMETERS = dict(speech_pad_ms=600, min_silence_duration_ms=500)
# Hide console windows for ffmpeg / nvidia-smi when running as a windowed exe.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def app_dir() -> Path:
    """Folder of the exe when frozen, else the project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", app_dir()))


def setup_cuda_dlls() -> list[str]:
    """Make the pip-installed cuBLAS/cuDNN DLLs (nvidia-*-cu12 wheels) visible to CTranslate2.

    Must run before faster_whisper/ctranslate2 load CUDA. Looks in the PyInstaller bundle
    and in every site-packages folder.
    """
    roots = [bundle_dir()]
    if not getattr(sys, "frozen", False):
        import site
        roots += [Path(p) for p in site.getsitepackages() + [site.getusersitepackages()]]
    added = []
    for root in roots:
        for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin"):
            d = root / sub
            if d.is_dir() and str(d) not in added:
                os.add_dll_directory(str(d))
                os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
                added.append(str(d))
    return added


def find_ffmpeg() -> str:
    for candidate in (app_dir() / "ffmpeg.exe", bundle_dir() / "ffmpeg.exe"):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg")
    if not found:
        raise FileNotFoundError("ffmpeg not found. Put ffmpeg.exe next to the app or add it to PATH.")
    return found


def gpu_name() -> str | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW)
        return out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


@dataclass
class Device:
    kind: str          # "cuda" or "cpu"
    compute_type: str  # "float16" or "int8"
    label: str         # shown in the UI

    @property
    def is_gpu(self) -> bool:
        return self.kind == "cuda"


def detect_device() -> Device:
    import ctranslate2
    if os.environ.get("SUBTITLE_ENGINE_FORCE_CPU") == "1":
        return cpu_device("forced by SUBTITLE_ENGINE_FORCE_CPU")
    try:
        has_cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        has_cuda = False
    if has_cuda:
        return Device("cuda", "float16", f"GPU · {gpu_name() or 'CUDA device'} (CUDA float16)")
    return cpu_device("no CUDA GPU detected")


def cpu_device(reason: str = "") -> Device:
    return Device("cpu", "int8", "CPU (int8)" + (f" · {reason}" if reason else ""))


def model_source() -> str:
    """A local model folder next to the app wins; otherwise the Hugging Face cache (downloaded once)."""
    local = app_dir() / "models" / f"faster-whisper-{MODEL_NAME}"
    return str(local) if (local / "model.bin").is_file() else MODEL_NAME


def extract_audio(video: str, ffmpeg: str | None = None) -> np.ndarray:
    """Decode the video's audio track to 16 kHz mono float32 via ffmpeg."""
    cmd = [ffmpeg or find_ffmpeg(), "-nostdin", "-v", "error", "-i", video,
           "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg could not read the audio:\n" + proc.stderr.decode(errors="replace")[-800:])
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise RuntimeError("The video has no audio track.")
    return audio


class Transcriber:
    """Keeps the loaded model between runs; falls back to CPU if CUDA fails to load or run."""

    def __init__(self) -> None:
        self.device: Device | None = None
        self._model = None

    def load(self, on_status: Callable[[str], None] = lambda s: None) -> Device:
        if self._model is not None:
            return self.device
        from faster_whisper import WhisperModel
        device = detect_device()
        if device.is_gpu:
            try:
                on_status("Loading model on GPU…")
                self._model = WhisperModel(model_source(), device="cuda", compute_type="float16")
                self.device = device
                return device
            except Exception as exc:  # missing cuBLAS/cuDNN, out of memory, ...
                device = cpu_device(f"GPU failed: {str(exc).splitlines()[0][:80]}")
        on_status("Loading model on CPU…")
        self._model = WhisperModel(model_source(), device="cpu", compute_type="int8")
        self.device = device
        return device

    def _fallback_to_cpu(self, reason: str) -> None:
        from faster_whisper import WhisperModel
        self._model = WhisperModel(model_source(), device="cpu", compute_type="int8")
        self.device = cpu_device(f"GPU failed: {reason[:80]}")

    def transcribe(self, audio: np.ndarray, on_progress: Callable[[float], None] = lambda p: None,
                   should_stop: Callable[[], bool] = lambda: False,
                   on_status: Callable[[str], None] = lambda s: None,
                   vocabulary: Vocabulary | None = None) -> list[Cue]:
        """Malay speech -> Malay cues."""
        vocab = vocabulary or Vocabulary()
        return self._with_fallback(lambda: self._run(audio, on_progress, should_stop, vocab), on_status)

    def transcribe_sentences(self, audio: np.ndarray, on_progress: Callable[[float], None] = lambda p: None,
                             should_stop: Callable[[], bool] = lambda: False,
                             on_status: Callable[[str], None] = lambda s: None,
                             vocabulary: Vocabulary | None = None) -> list[list[Word]]:
        """English speech -> timed English sentences, ready for translation."""
        vocab = vocabulary or Vocabulary()
        return self._with_fallback(lambda: self._run_english(audio, on_progress, should_stop, vocab), on_status)

    def _with_fallback(self, run, on_status):
        try:
            return run()
        except RuntimeError as exc:
            # cuDNN/cuBLAS problems often only surface at inference time.
            if not self.device or not self.device.is_gpu:
                raise
            on_status("GPU error, retrying on CPU…")
            self._fallback_to_cpu(str(exc).splitlines()[0])
            return run()

    def _run(self, audio, on_progress, should_stop, vocab: Vocabulary) -> list[Cue]:
        duration = len(audio) / SAMPLE_RATE
        segments, _info = self._model.transcribe(
            audio, language=LANGUAGE, word_timestamps=True, vad_filter=True,
            vad_parameters=VAD_PARAMETERS, beam_size=5, condition_on_previous_text=False,
            initial_prompt=build_prompt(vocab.custom_words))
        words: list[Word] = []
        for seg in segments:  # generator: decoding happens while iterating
            if should_stop():
                raise InterruptedError("Cancelled")
            # Quoted hadith/Quran come out in Arabic script; romanize them for Malay subtitles.
            words += [Word(romanize_text(w.word), w.start, w.end) for w in (seg.words or [])]
            on_progress(min(seg.end / duration, 1.0) if duration else 1.0)
        on_progress(1.0)
        cues = group_words(words)
        for cue in cues:
            cue.text = apply_corrections(cue.text, vocab.corrections)
        return cues

    def _run_english(self, audio, on_progress, should_stop, vocab: Vocabulary) -> list[list[Word]]:
        # No Malay prompt here: it would push Whisper towards Malay. Custom words still help with names.
        duration = len(audio) / SAMPLE_RATE
        segments, _info = self._model.transcribe(
            audio, language=ENGLISH, word_timestamps=True, vad_filter=True,
            vad_parameters=VAD_PARAMETERS, beam_size=5, condition_on_previous_text=False,
            initial_prompt=", ".join(vocab.custom_words) or None)
        words: list[Word] = []
        for seg in segments:  # generator: decoding happens while iterating
            if should_stop():
                raise InterruptedError("Cancelled")
            words += [Word(w.word, w.start, w.end) for w in (seg.words or [])]
            on_progress(min(seg.end / duration, 1.0) if duration else 1.0)
        on_progress(1.0)
        return group_sentences(words)


def english_to_malay_cues(sentences: list[list[Word]], translations: list[str], vocab: Vocabulary) -> list[Cue]:
    """Translated sentences -> Malay cues, with the (Malay) auto-corrections applied."""
    cues = translated_cues(sentences, translations)
    for cue in cues:
        cue.text = apply_corrections(cue.text, vocab.corrections)
    return cues
