; Chronos — Windows installer (Inno Setup 6).
;
; Built by packaging/windows/build.ps1, which stages everything into
; packaging/windows/stage and then runs:
;     iscc /DAppVersion=<version> packaging\windows\chronos.iss
;
; The installer copies compiled programs only. No Python source, no Docker:
;   {app}\server   chronos-server.exe (+ web UI, + migration scripts)
;   {app}\worker   chronos-worker.exe
;   {app}\pgsql    PostgreSQL binaries
;   {app}\services WinSW service wrapper
;   {app}\scripts  install / uninstall / backup / restore
; and then runs scripts\install.ps1, which sets up the database, the three
; Windows services, the firewall rule and the nightly backup.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
#define StageDir "stage"

[Setup]
; Never change AppId: it is how an upgrade finds the existing install.
AppId={{6F1B2C77-8E0B-4E0D-9B4D-4C1A7E2F9C31}
AppName=Chronos
AppVersion={#AppVersion}
AppVerName=Chronos {#AppVersion}
AppPublisher=Solis Labs
DefaultDirName={autopf}\Chronos
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=Output
OutputBaseFilename=ChronosSetup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UninstallDisplayName=Chronos
; The chronos mark (built by make_icon.py): on the installer file itself, and
; for Chronos in Settings > Apps.
SetupIconFile=chronos.ico
UninstallDisplayIcon={app}\chronos.ico
CloseApplications=no

[Files]
Source: "{#StageDir}\server\*"; DestDir: "{app}\server"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\worker\*"; DestDir: "{app}\worker"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\pgsql\*"; DestDir: "{app}\pgsql"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\winsw\WinSW-x64.exe"; DestDir: "{app}\services"; Flags: ignoreversion
Source: "install.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "uninstall.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "backup.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "restore.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "chronos.ico"; DestDir: "{app}"; Flags: ignoreversion

[INI]
; A plain internet shortcut: Chronos is used in the browser.
Filename: "{commondesktop}\Chronos.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:8080"
Filename: "{commondesktop}\Chronos.url"; Section: "InternetShortcut"; Key: "IconFile"; String: "{app}\chronos.ico"
Filename: "{commondesktop}\Chronos.url"; Section: "InternetShortcut"; Key: "IconIndex"; String: "0"

[UninstallRun]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\uninstall.ps1"" -AppDir ""{app}"" -DataDir ""{commonappdata}\Chronos"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "ChronosUninstall"

[UninstallDelete]
; Created at install time by install.ps1, so not tracked by the installer.
Type: filesandordirs; Name: "{app}\services"
Type: files; Name: "{commondesktop}\Chronos.url"

[Code]
procedure StopService(const Name: String);
var
  ResultCode: Integer;
begin
  { net stop waits for the service to finish stopping; it fails harmlessly
    when the service does not exist yet (first install). }
  Exec(ExpandConstant('{sys}\net.exe'), 'stop ' + Name, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { On an upgrade the running services hold the files about to be replaced
    (including the PostgreSQL binaries), so stop them first — worker, then
    server, then database. install.ps1 starts them again. }
  StopService('ChronosWorker');
  StopService('ChronosServer');
  StopService('ChronosPostgres');
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Params: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Setting up the database and services...';
    Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\scripts\install.ps1') + '"' +
      ' -AppDir "' + ExpandConstant('{app}') + '"' +
      ' -DataDir "' + ExpandConstant('{commonappdata}\Chronos') + '"';
    if not Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      MsgBox('Chronos was copied, but setting up the database and services did not finish.' + #13#10 + #13#10 +
        'Details are in:' + #13#10 + ExpandConstant('{commonappdata}\Chronos\logs\install.log'),
        mbError, MB_OK);
  end;
end;
