#define AppVersion GetEnv("ION_VERSION")
#if AppVersion == ""
  #error ION_VERSION environment variable must be set
#endif

[Setup]
AppId={{A55E5B50-2D8D-4CAC-9A50-6062F0E05880}
AppName=ION
AppVerName=ION {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=IntraStellar Logistics
AppPublisherURL=https://github.com/stellarwolf640/EliteLogistics
AppSupportURL=https://github.com/stellarwolf640/EliteLogistics/issues
DefaultDirName={localappdata}\Programs\IntraStellar Logistics\ION
DefaultGroupName=IntraStellar Logistics
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=ION-Setup-x64-{#AppVersion}
SetupIconFile=..\assets\ion.ico
UninstallDisplayIcon={app}\ION.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
ChangesEnvironment=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\ION\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ION"; Filename: "{app}\ION.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\ION"; Filename: "{app}\ION.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ION.exe"; Description: "Launch ION"; Flags: nowait postinstall skipifsilent
Filename: "{app}\ION.exe"; Flags: nowait; Check: RelaunchRequested

[Code]
const
  WebView2ClientGuid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Installed: Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid, 'pv', Version) or
    RegQueryStringValue(HKLM, 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid, 'pv', Version) or
    RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid, 'pv', Version) or
    RegQueryStringValue(HKLM64, 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientGuid, 'pv', Version);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Bootstrapper: String;
  ExitCode: Integer;
begin
  Result := '';
  if not WebView2Installed then
  begin
    try
      DownloadTemporaryFile(
        'https://go.microsoft.com/fwlink/p/?LinkId=2124703',
        'MicrosoftEdgeWebview2Setup.exe',
        '',
        nil
      );
      Bootstrapper := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');
      if not Exec(Bootstrapper, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) or (ExitCode <> 0) then
        Result := 'Microsoft Edge WebView2 could not be installed. Exit code: ' + IntToStr(ExitCode);
    except
      Result := 'Microsoft Edge WebView2 could not be downloaded. Check your internet connection and try again.';
    end;
  end;
end;

function RelaunchRequested: Boolean;
begin
  Result := Pos('/RELAUNCH=1', Uppercase(GetCmdTail)) > 0;
end;
