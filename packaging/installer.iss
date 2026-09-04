; Instalador de pivot-x-sentinel -- Fase 7 (docs/roadmap.md).
;
; Requiere Inno Setup 6 (https://jrsoftware.org/isinfo.php, gratuito).
; Se compila DESPUES de generar el build de PyInstaller (ver build.ps1, que
; hace los dos pasos en orden):
;
;   ISCC packaging\installer.iss
;
; Toma como fuente dist\pivot-x-sentinel\ (carpeta onedir de PyInstaller,
; ver pivot_x_sentinel.spec) y genera un unico .exe instalador en
; packaging\dist_installer\.

#define MyAppName "pivot-x-sentinel"
#define MyAppVersion "0.1.0"
#define MyAppExeName "pivot-x-sentinel.exe"
#define MyPyInstallerDist "..\dist\pivot-x-sentinel"

[Setup]
; GUID fijo -- NO regenerar: es lo que le permite a Inno Setup reconocer una
; instalacion previa y ofrecer actualizar en vez de duplicar.
AppId={{C06B5B9A-8CAE-4991-BDDE-C5B3112106A4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=pivot-x-sentinel
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Sin admin/UAC -- instala solo para el usuario actual, en una carpeta que ya
; es suya (AppData\Local). Bot personal de un solo usuario, no un servicio
; de sistema.
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=dist_installer
OutputBaseFilename=pivot-x-sentinel-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Se ve antes de elegir carpeta -- el requisito de MT5 hay que verlo SI o SI
; antes de instalar, no despues.
InfoBeforeFile=ANTES_DE_INSTALAR.txt
UninstallDisplayIcon={app}\{#MyAppExeName}
; Sin firma de codigo (cuesta dinero/año) -- SmartScreen puede avisar la
; primera vez, documentado en el Leeme post-instalacion.

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos adicionales:"

[Files]
; Toda la carpeta onedir de PyInstaller (el .exe + _internal\ con todo lo
; demas), recursiva.
Source: "{#MyPyInstallerDist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; El Leeme completo -- se copia a la carpeta de instalacion para poder
; volver a abrirlo despues (ver acceso directo "Leeme" mas abajo), ademas de
; abrirse solo una vez terminada la instalacion (ver [Run]).
Source: "README_INSTALADO.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} - Leeme"; Filename: "{app}\README_INSTALADO.txt"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Deja tildado por default abrir el bot -- pero lo que pidio el usuario es
; el Leeme, asi que ESE se abre siempre (nowait, no bloquea el wizard) y el
; bot en si queda como opcion tildable, no automatica (que un bot que manda
; ordenes reales no arranque solo sin que el usuario elija abrirlo).
Filename: "{app}\README_INSTALADO.txt"; Description: "Abrir el Leeme (configuracion, riesgo, como usarlo)"; Flags: postinstall shellexec skipifsilent nowait
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} ahora"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
; Por default Inno solo borra lo que el instalo -- esto fuerza a que la
; desinstalacion se lleve TAMBIEN los datos generados en uso (execution\
; data\scores, ver execution/src/paths.py: app_root() = carpeta de
; instalacion en build empaquetado) y los logs (control_window.py:
; %LOCALAPPDATA%\pivot-x-sentinel\logs -- misma carpeta que {app}, ya que
; DefaultDirName de arriba ES {localappdata}\pivot-x-sentinel). Documentado
; en README_INSTALADO.txt #5: desinstalar borra todo, hacer copia antes si
; se quiere conservar algo.
Type: filesandordirs; Name: "{app}"
