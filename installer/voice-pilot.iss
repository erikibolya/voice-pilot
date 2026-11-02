; Instalátor voice-pilotu.
;
; Sestavení:
;   ISCC.exe /DVersion=0.2.0 voice-pilot.iss
;
; Výsledek: dist\voice-pilot-<verze>-setup.exe

#ifndef Version
  #define Version "0.0.0"
#endif

#define AppName "voice-pilot"
#define AppPublisher "Erik Ibolya"
#define AppURL "https://github.com/erikibolya/voice-pilot"

[Setup]
AppId={{B7A3C1E2-4F5D-4A8B-9C6E-2D1F0A7B3C4D}
AppName={#AppName}
AppVersion={#Version}
AppVerName={#AppName} {#Version}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#Version}
DefaultDirName={localappdata}\VoicePilot
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=voice-pilot-{#Version}-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableWelcomePage=no
ShowLanguageDialog=no

[Languages]
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"

[Tasks]
Name: "desktopicon"; Description: "Vytvořit zástupce na ploše"; GroupDescription: "Doplňky:"

[Files]
Source: "..\pilot\*"; DestDir: "{app}\pilot"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc"
Source: "..\run.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\launch.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "bootstrap.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "vendor\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vendor\wheels\*.whl"; DestDir: "{app}\wheels"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\launch.cmd"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"
Name: "{group}\Odinstalovat {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\launch.cmd"; IconFilename: "{app}\icon.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\launch.cmd"; Description: "Spustit {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\wheels"
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\shots"
Type: filesandordirs; Name: "{app}\pilot\__pycache__"
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\install.log"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Command: String;
begin
  if CurStep = ssPostInstall then
  begin
    Command := '-NoProfile -ExecutionPolicy Bypass -File "' +
               ExpandConstant('{app}\bootstrap.ps1') +
               '" -InstallDir "' + ExpandConstant('{app}') + '"';

    WizardForm.StatusLabel.Caption := 'Připravuji Python prostředí, může to trvat několik minut…';
    WizardForm.Refresh;

    if not Exec('powershell.exe', Command, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      MsgBox('Nepodařilo se spustit přípravu prostředí.' + #13#10 +
             'Spusť ručně: ' + ExpandConstant('{app}\bootstrap.ps1'),
             mbError, MB_OK)
    else if ResultCode <> 0 then
      MsgBox('Příprava prostředí selhala (kód ' + IntToStr(ResultCode) + ').' + #13#10 + #13#10 +
             'Podrobnosti jsou v souboru:' + #13#10 +
             ExpandConstant('{app}\install.log') + #13#10 + #13#10 +
             'Zkus instalaci spustit znovu; pokud to nepomůže, nahlas chybu na GitHubu.',
             mbError, MB_OK);
  end;
end;
