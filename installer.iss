; Inno Setup script: packages dist\SubtitleEngine\ into installer\SubtitleEngineSetup.exe
; Build with:  build.bat   (or: ISCC.exe installer.iss, after the PyInstaller build)
;
; The speech/translation models are NOT included: the app downloads them on first use into the
; user's Hugging Face cache (or uses a "models" folder next to the exe, see tools\fetch_model.py).

#define AppName "Subtitle Engine"
#define AppVersion "1.1.0"
#define AppExe "SubtitleEngine.exe"

[Setup]
; Keep this AppId fixed forever: it is how Windows recognises upgrades and the uninstaller.
AppId={{6C1F3A52-8E4B-4D7A-9B21-3F5E7C9A1D40}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Install for all users (asks for admin) by default; the dialog also offers "only for me" without admin.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=SubtitleEngineSetup
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=no
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\SubtitleEngine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
