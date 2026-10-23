; Inno Setup — instalator SayCue (Windows, architektura §6 W3)
; Wejście: dist\saycue\ (PyInstaller onedir, zbudowane w CI na windows-latest)
; Wyjście: saycue-setup-<version>.exe — instalacja < 5 min na czystym VM.
; Autostart: HKCU\Software\Microsoft\Windows\CurrentVersion\Run.

#define MyAppName "SayCue"
#ifndef MyAppVersion
#define MyAppVersion "0.1.0-rc1"
#endif
#define MyAppPublisher "SayCue contributors"
#define MyAppExeName "saycue.exe"

[Setup]
AppId={{8F4A6C2E-3B1D-4E5A-9C77-SAYCUE000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=saycue-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
; Modeli NIE pakujemy (R10) — pierwsze uruchomienie pobiera je z manifestu.

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Uruchamiaj SayCue przy logowaniu"; Flags: unchecked

[Files]
Source: "..\dist\saycue\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Diagnostyka (doctor)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "doctor"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Uruchom SayCue (pobierze modele przy pierwszym starcie)"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeName}"; Parameters: "doctor"; Description: "Diagnostyka: mikrofon, OBS, modele"; Flags: postinstall unchecked skipifsilent runascurrentuser

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SayCue"; ValueData: """{app}\{#MyAppExeName}"" gui --no-tray"; Flags: uninsdeletevalue; Tasks: autostart

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
