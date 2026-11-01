@echo off
REM Build the standalone Windows app into dist\SubtitleEngine\, then the installer (if Inno Setup is installed)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup first - see README.md
  exit /b 1
)
.venv\Scripts\python -m pytest -q tests || exit /b 1
.venv\Scripts\pyinstaller --noconfirm --clean subtitle_engine.spec || exit /b 1
echo.
echo Built: dist\SubtitleEngine\SubtitleEngine.exe
echo Optional (fully offline/portable): .venv\Scripts\python tools\fetch_model.py

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 not found - skipping the installer. Install it with: winget install JRSoftware.InnoSetup
  exit /b 0
)
"%ISCC%" /Q installer.iss || exit /b 1
echo Installer: installer\SubtitleEngineSetup.exe
