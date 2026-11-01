"""Entry point for Subtitle Engine (also the PyInstaller target).

    SubtitleEngine.exe                                  -> open the window
    SubtitleEngine.exe --selftest <video> <out.srt>     -> transcribe without UI (writes <out.srt>.log)
    SubtitleEngine.exe --selftest <video> <out.srt> en  -> English speech, translated to Malay
"""
import sys

from subtitle_engine.engine import setup_cuda_dlls

# Register cuBLAS/cuDNN DLL folders before faster-whisper / CTranslate2 touch CUDA.
setup_cuda_dlls()


def selftest(video: str, out: str, language: str = "ms") -> int:
    import time
    from pathlib import Path

    from subtitle_engine.engine import ENGLISH, Transcriber, english_to_malay_cues, extract_audio, find_ffmpeg
    from subtitle_engine.subtitles import sentence_text, to_srt

    log = Path(out + ".log")
    try:
        t0 = time.time()
        transcriber = Transcriber()
        transcriber.load()
        audio = extract_audio(video)
        extra = ""
        if language == ENGLISH:
            from subtitle_engine.translate import Translator
            from subtitle_engine.vocabulary import Vocabulary

            sentences = transcriber.transcribe_sentences(audio)
            translator = Translator()
            translator.load()
            texts = [sentence_text(s) for s in sentences]
            cues = english_to_malay_cues(sentences, translator.translate(texts), Vocabulary())
            extra = f" translator={translator.device.label} sentences={len(sentences)}"
        else:
            cues = transcriber.transcribe(audio)
        Path(out).write_text(to_srt(cues), encoding="utf-8")
        log.write_text(f"OK device={transcriber.device.label} ffmpeg={find_ffmpeg()} "
                       f"cues={len(cues)}{extra} seconds={time.time() - t0:.1f}\n", encoding="utf-8")
        return 0
    except Exception as exc:
        log.write_text(f"FAILED {type(exc).__name__}: {exc}\n", encoding="utf-8")
        return 1


if __name__ == "__main__":
    if len(sys.argv) in (4, 5) and sys.argv[1] == "--selftest":
        sys.exit(selftest(*sys.argv[2:]))
    from subtitle_engine.app import run

    sys.exit(run())
