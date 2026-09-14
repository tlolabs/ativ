; Per-user installs keep updates independent of administrator credentials.
[Setup]
AppId=com.tlolabs.ativ{#ChannelSuffix}
AppName={#AppName}
AppVersion={#Version}
AppPublisher=TLO Labs
AppPublisherURL=https://github.com/tlolabs/ativ
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed={#Architecture}
ArchitecturesInstallIn64BitMode={#Architecture}
MinVersion=10.0.17763
OutputDir={#OutputDirectory}
OutputBaseFilename=ATIV-{#Version}-windows-{#Label}-setup
SetupIconFile=..\ATIV\Assets\ATIV.ico
UninstallDisplayIcon={app}\ATIV.exe
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
[Files]
Source: "{#PublishDirectory}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ATIV.exe"; AppUserModelID: "com.tlolabs.ativ{#ChannelSuffix}"
[Run]
Filename: "{app}\ATIV.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
