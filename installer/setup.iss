; Garra da Pantera — Script de Instalacao Inno Setup
; Gerado automaticamente pelo GitHub Actions
; Nao edite manualmente — use installer/setup.iss no repositorio

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName      "Garra da Pantera"
#define AppPublisher "RAFAELOS1997"
#define AppURL       "https://github.com/RAFAELOS1997/Garra-da-Pantera"
#define AppExe       "abrir_programa.bat"

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
; Executa setup.ps1 somente se Python estiver instalado
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup.ps1"""; \
  WorkingDir: "{app}"; \
  StatusMsg: "Configurando ambiente Python (pode demorar alguns minutos na primeira vez)..."; \
  Flags: runhidden waituntilterminated; \
  Check: PythonInstalled

; Oferecer para abrir o programa apos a instalacao
Filename: "{app}\{#AppExe}"; \
  Description: "Iniciar {#AppName} agora"; \
  Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\*.pyc"

[Messages]
brazilianportuguese.WelcomeLabel2=Este assistente vai instalar o [name/ver] no seu computador.%n%nO Garra da Pantera usa IA para segmentar malhas 3D e gerar pecas imprimiveis.%n%nRecomendamos fechar todos os outros programas antes de continuar.

[Code]
// Verifica se Python 3.10+ esta instalado
function PythonInstalled: Boolean;
var
  Path: String;
begin
  Result :=
    RegQueryStringValue(HKLM,  'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', Path) or
    RegQueryStringValue(HKLM,  'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', Path) or
    RegQueryStringValue(HKLM,  'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', Path) or
    RegQueryStringValue(HKLM,  'SOFTWARE\WOW6432Node\Python\PythonCore\3.12\InstallPath', '', Path) or
    RegQueryStringValue(HKLM,  'SOFTWARE\WOW6432Node\Python\PythonCore\3.11\InstallPath', '', Path) or
    RegQueryStringValue(HKLM,  'SOFTWARE\WOW6432Node\Python\PythonCore\3.10\InstallPath', '', Path) or
    RegQueryStringValue(HKCU,  'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', Path) or
    RegQueryStringValue(HKCU,  'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', Path) or
    RegQueryStringValue(HKCU,  'SOFTWARE\Python\PythonCore\3.10\InstallPath', '', Path);
end;

// Avisa se Python nao estiver instalado, mas permite continuar
function InitializeSetup: Boolean;
begin
  Result := True;
  if not PythonInstalled then
    MsgBox(
      'Python 3.10 ou superior nao foi encontrado no seu computador.' + #13#10#13#10 +
      'O Garra da Pantera requer Python para funcionar.' + #13#10 +
      'Baixe em: https://www.python.org/downloads/' + #13#10 +
      '(marque "Add Python to PATH" durante a instalacao)' + #13#10#13#10 +
      'A instalacao dos arquivos continuara normalmente.' + #13#10 +
      'Configure o Python e execute setup.ps1 antes de usar o programa.',
      mbInformation, MB_OK);
end;
