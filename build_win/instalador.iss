; Instalador do SoulFork Radar (Inno Setup)
#define AppNome "SoulFork Radar"
#define AppVersao GetEnv("RADAR_VERSAO")
#if AppVersao == ""
  #define AppVersao "1.0.0"
#endif

[Setup]
AppId={{7E2B8C11-4A0D-4B62-9C33-51F0RKRADAR01}
AppName={#AppNome}
AppVersion={#AppVersao}
AppPublisher=SoulFork
AppPublisherURL=https://soulfork.com.br
DefaultDirName={autopf}\SoulFork Radar
DefaultGroupName=SoulFork Radar
DisableProgramGroupPage=yes
OutputBaseFilename=SoulForkRadar-{#AppVersao}-instalador
OutputDir=..\dist
SetupIconFile=radar.ico
UninstallDisplayIcon={app}\SoulForkRadar.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
ShowLanguageDialog=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\dist\SoulForkRadar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SoulFork Radar"; Filename: "{app}\SoulForkRadar.exe"
Name: "{autodesktop}\SoulFork Radar"; Filename: "{app}\SoulForkRadar.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SoulForkRadar.exe"; Description: "Abrir o SoulFork Radar agora"; Flags: nowait postinstall skipifsilent
