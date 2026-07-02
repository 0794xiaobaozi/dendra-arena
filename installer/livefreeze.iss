#define MyAppName "LiveFreeze"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "LiveFreeze"
#define MyAppExeName "livefreeze.exe"

[Setup]
AppId={{D5FF2A68-5232-49D0-BEA5-9A49C12DA4A1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=LiveFreeze-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Files]
Source: "..\dist\livefreeze\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; 清理 0.1.0 早期安装包误带的 Conda ICU，避免其遮蔽 Windows 系统 ICU。
Type: files; Name: "{app}\_internal\icuuc.dll"
Type: files; Name: "{app}\_internal\icuuc73.dll"
Type: files; Name: "{app}\_internal\icudt73.dll"
Type: files; Name: "{app}\_internal\PySide6\icuuc.dll"
Type: files; Name: "{app}\_internal\PySide6\icuuc73.dll"
Type: files; Name: "{app}\_internal\PySide6\icudt73.dll"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
