; Inno Setup installer script for Auger - 7 Days to Die Dedicated Server Manager
; Publisher: RobotsNeverDie
;
; PREREQUISITES:
;   1. Install Inno Setup 6+  ->  https://jrsoftware.org/isinfo.php
;   2. Run the PyInstaller build first:
;        cd 7dtd_server_tool
;        python build.py
;
; BUILD THE INSTALLER (from the repository root):
;   iscc installer\auger_setup.iss
;   -- or open this file in the Inno Setup IDE and press Ctrl+F9.
;
; OUTPUT:
;   installer\AugerSetup-1.0.0-win64.exe

#define AppName        "Auger"
#define AppFullName    "Auger - 7DTD Server Manager"
#define AppVersion     "1.0.0"
#define AppPublisher   "RobotsNeverDie"
#define AppExeName     "7DTD_Server_Manager.exe"
#define BuildOutput    "..\7dtd_server_tool\dist\7DTD_Server_Manager"

[Setup]
; *** IMPORTANT: Do NOT reuse this AppId for a different application. ***
; Generate a fresh GUID at https://www.guidgenerator.com/ if you fork or rename.
AppId={{D9E2A7B1-C4F3-4B6A-8D0E-2F3A5B7C8D9E}
AppName={#AppFullName}
AppVersion={#AppVersion}
AppVerName={#AppFullName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/RobotsNeverDie/Auger
AppSupportURL=https://github.com/RobotsNeverDie/Auger/issues
AppUpdatesURL=https://github.com/RobotsNeverDie/Auger/releases

; Installation directory — defaults to per-user AppData\Local (no UAC prompt).
; Per-user installs are trusted by Windows SmartScreen and most AV products.
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Installer output
OutputDir=.
OutputBaseFilename=AugerSetup-{#AppVersion}-win64

; High compression
Compression=lzma2/ultra64
SolidCompression=yes

; Windows 10 1809+ minimum (build 17763)
MinVersion=10.0.17763

; 64-bit only
ArchitecturesInstallIn64BitMode=x64compatible

; Install per-user by default — avoids UAC, reduces AV suspicion.
; The user can choose per-machine install via the override dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Modern wizard style
WizardStyle=modern

; Uninstaller registration
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppFullName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copy the entire --onedir output folder into the install directory.
; recursesubdirs handles all PyInstaller DLLs, .pyd files, and data folders.
Source: "{#BuildOutput}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppFullName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppFullName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppFullName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch the app immediately after install.
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppFullName}}"; Flags: nowait postinstall skipifsilent
