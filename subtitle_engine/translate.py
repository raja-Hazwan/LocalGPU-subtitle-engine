"""Offline English -> Malay translation with NLLB-200 (CTranslate2): GPU (int8_float16) with CPU (int8) fallback."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .engine import Device, app_dir, cpu_device, detect_device

MODEL_REPO = "OpenNMT/nllb-200-distilled-1.3B-ct2-int8"  # CC-BY-NC-4.0 (non-commercial)
SOURCE_LANG = "eng_Latn"
TARGET_LANG = "zsm_Latn"  # Standard Malay
BATCH_SIZE = 16


def translation_model_source() -> str:
    """A local model folder next to the app wins; otherwise the Hugging Face cache (downloaded once)."""
    local = app_dir() / "models" / MODEL_REPO.split("/")[1]
    if (local / "model.bin").is_file():
        return str(local)
    from faster_whisper.utils import disabled_tqdm  # no console in the windowed exe for progress bars
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(MODEL_REPO, local_files_only=True)
    except Exception:  # not cached yet
        return snapshot_download(MODEL_REPO, tqdm_class=disabled_tqdm)


class Translator:
    """Keeps the loaded model between runs; falls back to CPU if CUDA fails to load or run."""

    def __init__(self) -> None:
        self.device: Device | None = None
        self._model = None
        self._tokenizer = None
        self._path: str | None = None

    def load(self, on_status: Callable[[str], None] = lambda s: None) -> Device:
        if self._model is not None:
            return self.device
        import ctranslate2
        from tokenizers import Tokenizer
        on_status("Preparing translation model…")
        self._path = translation_model_source()
        self._tokenizer = Tokenizer.from_file(str(Path(self._path) / "tokenizer.json"))
        device = detect_device()
        if device.is_gpu:
            try:
                on_status("Loading translation model on GPU…")
                self._model = ctranslate2.Translator(self._path, device="cuda", compute_type="int8_float16")
                self.device = device
                return device
            except Exception as exc:  # missing cuBLAS, out of memory, ...
                device = cpu_device(f"GPU failed: {str(exc).splitlines()[0][:80]}")
        on_status("Loading translation model on CPU…")
        self._model = ctranslate2.Translator(self._path, device="cpu", compute_type="int8")
        self.device = device
        return device

    def _fallback_to_cpu(self, reason: str) -> None:
        import ctranslate2
        self._model = ctranslate2.Translator(self._path, device="cpu", compute_type="int8")
        self.device = cpu_device(f"GPU failed: {reason[:80]}")

    def _encode(self, text: str) -> list[str]:
        # The bundled tokenizer.json's post-processor adds the wrong special tokens, so add them here.
        return [SOURCE_LANG] + self._tokenizer.encode(text, add_special_tokens=False).tokens + ["</s>"]

    def _decode(self, tokens: list[str]) -> str:
        ids = [self._tokenizer.token_to_id(t) for t in tokens if t != TARGET_LANG]
        return self._tokenizer.decode([i for i in ids if i is not None]).strip()

    def _batch(self, texts: list[str]) -> list[str]:
        results = self._model.translate_batch(
            [self._encode(t) for t in texts], target_prefix=[[TARGET_LANG]] * len(texts),
            beam_size=4, max_decoding_length=256)
        return [self._decode(r.hypotheses[0]) for r in results]

    def translate(self, texts: list[str], on_progress: Callable[[float], None] = lambda p: None,
                  should_stop: Callable[[], bool] = lambda: False,
                  on_status: Callable[[str], None] = lambda s: None) -> list[str]:
        out: list[str] = []
        for i in range(0, len(texts), BATCH_SIZE):
            if should_stop():
                raise InterruptedError("Cancelled")
            batch = texts[i:i + BATCH_SIZE]
            try:
                out += self._batch(batch)
            except RuntimeError as exc:
                # cuDNN/cuBLAS problems often only surface at inference time.
                if not self.device or not self.device.is_gpu:
                    raise
                on_status("GPU error, translating on CPU…")
                self._fallback_to_cpu(str(exc).splitlines()[0])
                out += self._batch(batch)
            on_progress(min((i + len(batch)) / len(texts), 1.0))
        on_progress(1.0)
        return out
