#define AppName "Maß-DPP Polo Simulator"
#define AppVersion "1.1.0"

[Setup]
AppId={{893AF624-F70F-47A7-A1A8-2E1A5B217E20}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\MassDPPPoloSimulator
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=PoloSimulatorSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PoloSimulator.exe

[Files]
Source: "..\dist\PoloSimulator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "deps\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not WebView2Installed

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\PoloSimulator.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PoloSimulator.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft WebView2 Runtime..."; Flags: waituntilterminated; Check: not WebView2Installed
Filename: "{app}\PoloSimulator.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Installed: Boolean;
var Version: String;
begin
  Result :=
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM64, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
end;
