#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

[Setup]
AppId={{B7F4D93E-6E49-4D87-A10F-9D6E8149A2B1}
AppName=ModSync
AppVersion={#MyAppVersion}
AppPublisher=Minecraft Server ModSync
DefaultDirName={localappdata}\Programs\ModSync
DefaultGroupName=ModSync
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=ModSync-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "autostart"; Description: "Launch ModSync automatically when Windows starts"; Flags: unchecked

[Files]
Source: "dist\ModSync.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ModSync"; Filename: "{app}\ModSync.exe"
Name: "{group}\Uninstall ModSync"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Classes\modsync"; ValueType: string; ValueData: "URL:ModSync Invite Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\modsync"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\modsync\shell\open\command"; ValueType: string; ValueData: """{app}\ModSync.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "ModSync"; ValueData: """{app}\ModSync.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\ModSync.exe"; Description: "Launch ModSync"; Flags: nowait postinstall skipifsilent
