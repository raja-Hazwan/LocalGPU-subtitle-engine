"""Put the speech and translation models next to the app for fully offline/portable use.

Usage:  python tools\fetch_model.py [target_app_folder]
Default target: dist\SubtitleEngine. Uses the Hugging Face cache if a model is already
downloaded there, otherwise downloads it once (~3 GB speech model + ~1.4 GB translation model).
"""
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

target_app = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "dist" / "SubtitleEngine"
for repo, folder in (("Systran/faster-whisper-large-v3", "faster-whisper-large-v3"),
                     ("OpenNMT/nllb-200-distilled-1.3B-ct2-int8", "nllb-200-distilled-1.3B-ct2-int8")):
    dest = target_app / "models" / folder
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo, local_dir=dest)
    print("Model ready at", dest)
