# PyInstaller spec for Subtitle Engine (one-folder, windowed).
# Build with:  build.bat   (or: .venv\Scripts\pyinstaller --noconfirm subtitle_engine.spec)
import shutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

import nvidia.cublas, nvidia.cudnn, nvidia.cuda_nvrtc  # noqa: E401  (pip: nvidia-*-cu12)


def nvidia_dlls(module, skip=()):
    """Bundle the CUDA DLLs under nvidia/<lib>/bin — the layout setup_cuda_dlls() looks for."""
    root = Path(list(module.__path__)[0])
    dest = "nvidia/" + root.name + "/bin"
    return [(str(p), dest) for p in (root / "bin").glob("*.dll") if p.name not in skip]


binaries = (
    collect_dynamic_libs("ctranslate2")
    + nvidia_dlls(nvidia.cublas, skip={"nvblas64_12.dll"})
    + nvidia_dlls(nvidia.cudnn)
    + nvidia_dlls(nvidia.cuda_nvrtc)
)
ffmpeg = shutil.which("ffmpeg")
if ffmpeg:
    binaries.append((ffmpeg, "."))  # bundled so the exe works without ffmpeg on PATH

a = Analysis(
    ["main.py"],
    binaries=binaries,
    datas=collect_data_files("faster_whisper")  # Silero VAD model (assets/*.onnx)
          + [("assets/app.ico", "assets")],  # window icon
    hiddenimports=["ctranslate2"],
    excludes=["torch", "tensorflow", "matplotlib", "pandas", "scipy", "cv2", "IPython",
              "tkinter", "PyQt5", "PyQt6", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SubtitleEngine",
          console=False, upx=False, icon="assets/app.ico")
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="SubtitleEngine")
