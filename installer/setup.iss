; Garra da Pantera — Script de Instalacao Inno Setup
; Gerado automaticamente pelo GitHub Actions
; Nao edite manualmente — use installer/setup.iss no repositorio

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName      "Garra da Pantera"
#define AppPublisher "RAFAELOS1997"
#define AppURL       "https://github.com/RAFAELOS1997/Garra-da-Pantera"
#define AppExe       "GarraDaPantera.exe"

[Setup]
AppId={{8F3A2B1C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=GarraDaPantera-v{#AppVersion}-Installer
OutputDir=Output
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
ChangesEnvironment=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na {%USERPROFILE}\Desktop"; GroupDescription: "Atalhos adicionais:"; Flags: checkedonce

[Files]
; Todos os arquivos do aplicativo
Source: "app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\Desinstalar {#AppName}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";        Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Oferecer para abrir o programa apos a instalacao. Nao ha mais passo de
; configuracao de Python: {app} contem a build congelada pelo PyInstaller
; (GarraDaPantera.exe + bibliotecas), que roda sozinha.
Filename: "{app}\{#AppExe}"; \
  Description: "Iniciar {#AppName} agora"; \
  Flags: nowait postinstall skipifsilent shellexec

[Messages]
brazilianportuguese.WelcomeLabel2=Este assistente vai instalar o [name/ver] no seu computador.%n%nO Garra da Pantera usa IA para segmentar malhas 3D e gerar pecas imprimiveis.%n%nRecomendamos fechar todos os outros programas antes de continuar.
