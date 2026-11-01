# Subtitle Engine

A small Windows desktop app that turns a video into Malay subtitles, fully offline. The speaker can talk in Malay, or in English (translated to Malay).

**Upload** a video (mp4, mkv, mov or avi), click **Generate**, review and edit the subtitles in the list, then **Export** to `.srt`, optionally with `.vtt` too.

- Speech recognition: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `large-v3`. Pick the speech language in the dropdown next to Export:
  - **Malay speech → Malay subtitles** (default, `ms`).
  - **English speech → Malay subtitles (translated)**. Whisper transcribes the English, the words are grouped into sentences, and each sentence is translated with [NLLB-200](https://huggingface.co/OpenNMT/nllb-200-distilled-1.3B-ct2-int8) (distilled 1.3B, int8, via CTranslate2 on the GPU). The Malay text is then split back into cues across the original sentence's timing. Auto-corrections apply to the Malay result. Note: the NLLB model is licensed **CC-BY-NC 4.0 (non-commercial)**.
- Runs on your NVIDIA GPU (CUDA, float16). If no GPU is available, or CUDA fails to load, it falls back to CPU (int8). The badge in the top-right corner shows which one is in use.
- Audio is extracted with ffmpeg. Long silences are skipped (VAD), and cues are split at 42 characters, 5 seconds, or a 0.6-second pause.
- Arabic quotes (hadith, Quran) are **romanized** in Malay style, for example *la takunu imma'atan* and *wattinu anfusakum*.
- **Vocabulary…** (the link at top right) holds two lists. *Custom words* are names and terms the speaker uses. *Auto-corrections* fix mistakes Whisper keeps repeating, one per line as `wrong = right`. Both are saved in `%APPDATA%\SubtitleEngine\settings.json` and apply from the next Generate.

---

## 0. Install it like a normal Windows app

Run `installer\SubtitleEngineSetup.exe` (about 1 GB). It installs to `C:\Program Files\Subtitle Engine`, or to your user folder if you pick "only for me". It adds a Start menu entry and an optional desktop icon, and lists the app under **Settings → Apps → Installed apps**, where you can uninstall it.

The models are not in the installer. They download the first time they are needed (see below). Uninstalling leaves the downloaded models in `%USERPROFILE%\.cache\huggingface\hub` and your vocabulary in `%APPDATA%\SubtitleEngine`. Delete those folders by hand if you want them gone too.

To build a new installer after changing the code, run `build.bat`. It builds the app and then the installer, using [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`). Raise `AppVersion` in `installer.iss` for each release. Installing a new version over an old one upgrades it in place.

## 1. Use the built app

`dist\SubtitleEngine\SubtitleEngine.exe` is self-contained. It bundles Python, Qt, ffmpeg and the CUDA/cuDNN libraries. Copy the entire `dist\SubtitleEngine` folder, not just the exe.

**The speech model (about 3 GB) and the translation model (about 1.4 GB, only needed for English speech) are not inside the exe.** The app looks for each one in this order:

1. `SubtitleEngine\models\faster-whisper-large-v3\` and `SubtitleEngine\models\nllb-200-distilled-1.3B-ct2-int8\`, next to the exe. This makes the app fully portable and offline. To fill this folder, run:
   ```bat
   .venv\Scripts\python tools\fetch_model.py
   ```
   It copies the models from your Hugging Face cache if it's already there, and downloads it otherwise.
2. The Hugging Face cache (`%USERPROFILE%\.cache\huggingface\hub`). On this PC the model is already there. On a new PC it downloads automatically the first time you click Generate, which needs internet once. After that it works offline.

**GPU requirements:** an NVIDIA GPU with a recent driver. Check with `nvidia-smi`. You don't need to install the CUDA Toolkit or cuDNN separately, because the needed DLLs are bundled. Large-v3 in float16 uses about 4–5 GB of VRAM. The translation model adds about 1.5 GB.

---

## 2. Run from source

Requires Python 3.10–3.12 and ffmpeg (on `PATH`, or `ffmpeg.exe` placed in this folder).

```bat
cd /d "D:\subtitle engine"
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

> On this PC, `.venv` was created with `--system-site-packages`, so it reuses the faster-whisper and CUDA packages already installed globally.

### CUDA / cuDNN setup on Windows (what faster-whisper needs)

faster-whisper runs on CTranslate2, which needs the **CUDA 12 cuBLAS** and **cuDNN 9** DLLs. The simplest way on Windows is to install the pip wheels. They're already in `requirements.txt`:

```bat
.venv\Scripts\python -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12>=9,<10" nvidia-cuda-nvrtc-cu12
```

Windows doesn't search inside those wheels for DLLs on its own. `setup_cuda_dlls()` in `subtitle_engine/engine.py` registers `site-packages\nvidia\{cublas,cudnn,cuda_nvrtc}\bin` with `os.add_dll_directory` before CTranslate2 loads, and the packaged exe does the same with its bundled copies.

Check that the GPU is being used:

```bat
.venv\Scripts\python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

This should print `1` or more. When you click Generate, the badge should turn green with your GPU's name.

If you see errors like `cublas64_12.dll not found` or `Could not load library cudnn_ops64_9.dll`, the wheels are missing or don't match. Reinstall them with the command above. The app keeps working in that case: it falls back to CPU automatically and the badge shows the reason.

To force CPU mode for testing: `set SUBTITLE_ENGINE_FORCE_CPU=1`.

---

## 3. Build the standalone exe

```bat
build.bat
```

This runs the unit tests, then runs PyInstaller with `subtitle_engine.spec` to build a one-folder windowed app in `dist\SubtitleEngine\`. The output is about 2.4 GB, mostly the CUDA DLLs. A one-folder build is used because a single-file exe would unpack 2 GB to a temp folder on every launch.

Check a build without opening the window:

```bat
dist\SubtitleEngine\SubtitleEngine.exe --selftest "C:\path\video.mp4" "C:\path\out.srt"
type "C:\path\out.srt.log"
```

The log should read `OK device=GPU · ... cues=N`. Add `en` at the end to test English speech → Malay; the log then also shows `translator=GPU · ...`.

---

## Accuracy

Settings were chosen by measuring against a hand-corrected subtitle file (`eval/`):

| Setting | Effect on the test video |
|---|---|
| Built-in Islamic-term vocabulary in the prompt (amanah, ta'zir, hudud, …) | fixed *amanah*, *ta'zir* 7/10 → 10/10 |
| Wider VAD speech padding (600 ms) + 500 ms silence split | recovered 3 phrases the default skipped entirely |
| Auto-corrections | fixes repeat mistakes (*rasyak → dahsyat*) |
| Tried and rejected: `hotwords`, beam 10, audio denoise, `condition_on_previous_text`, no VAD | all made things worse overall |

Result: all of the hand corrections on the test video are produced automatically. Still imperfect:
occasional dropped filler words (*je*, *nak buat*), *ni/ini* and *tu/itu* spelling varies, and some Arabic
verses are skipped (only the Malay translation is written).

To re-run the comparison on a new video: put it at `eval/video.mp4` and your corrected subtitles at
`eval/reference.srt`, then `.venv\Scripts\python eval\eval_app.py`.

## Editing tips

- Double-click a cell to edit it. Times use the format `HH:MM:SS,mmm`.
- Export checks every row first. Bad timestamps, or an end time before its start time, are reported by row number.
- Rows with empty text are left out of the exported file.

## Project layout

```
main.py                     entry point (+ --selftest)
subtitle_engine/engine.py   CUDA DLL setup, device detection, ffmpeg audio, transcription
subtitle_engine/subtitles.py  word grouping into cues, SRT/VTT writing, timestamp parsing
subtitle_engine/app.py      PySide6 window
tests/                      unit tests (pytest)
subtitle_engine/arabic.py   Arabic-script -> Malay-style romanization
subtitle_engine/translate.py   English -> Malay translation (NLLB-200, CTranslate2)
subtitle_engine/vocabulary.py  prompt terms, custom words, auto-corrections, settings file
eval/                       accuracy experiments (run_eval.py, eval_app.py)
tools/fetch_model.py        copy/download the models next to the exe
subtitle_engine.spec        PyInstaller build config
build.bat                   test + build exe + build installer
installer.iss               Inno Setup installer script (output: installer\SubtitleEngineSetup.exe)
assets/app.ico              app icon (redraw with tools/make_icon.py)
```
