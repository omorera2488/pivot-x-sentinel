; Instalador de pivot-x-sentinel -- Fase 7 (docs/roadmap.md) + Fase 7.1
; (versionado y releases, ver CHANGELOG.md).
;
; Requiere Inno Setup 6 (https://jrsoftware.org/isinfo.php, gratuito).
; Se compila DESPUES de generar el build de PyInstaller (ver build.ps1 o
; scripts/build_release.py, que hacen los dos pasos en orden):
;
;   ISCC packaging\installer.iss
;
; Toma como fuente dist\pivot-x-sentinel\ (carpeta onedir de PyInstaller,
; ver pivot_x_sentinel.spec) y genera un unico .exe instalador en
; packaging\dist_installer\.
;
; La version se lee de /VERSION (raiz del repo, fuente unica -- ver
; execution/src/version.py) -- NO se edita aca a mano.

#define MyAppName "pivot-x-sentinel"
#define MyAppExeName "pivot-x-sentinel.exe"
#define MyPyInstallerDist "..\dist\pivot-x-sentinel"

#define VersionFileHandle
#define MyAppVersion
#if VersionFileHandle = FileOpen("..\VERSION")
  #define MyAppVersion Trim(FileRead(VersionFileHandle))
  #expr FileClose(VersionFileHandle)
#endif
#if MyAppVersion == ""
  #error "No se pudo leer /VERSION (raiz del repo) -- necesario para compilar el instalador."
#endif

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
OutputBaseFilename=pivot-x-sentinel-setup-{#MyAppVersion}
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
; demas), recursiva. ignoreversion: siempre sobrescribe, sin comparar fecha/
; version de archivo individual -- la comparacion de version REAL (bloqueo
; de downgrade, aviso de misma version) ya se hizo antes en
; InitializeSetup() mas abajo; esto solo copia.
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
; DESINSTALACION (distinto de un upgrade, ver CurStepChanged en [Code]: ese
; solo toca _internal) se lleve TAMBIEN los datos generados en uso
; (execution\data\scores, ver execution/src/paths.py:user_data_root()) y los
; logs (control_window.py: %LOCALAPPDATA%\pivot-x-sentinel\logs -- misma
; carpeta que {app}, ya que DefaultDirName de arriba ES {localappdata}\
; pivot-x-sentinel). Documentado en README_INSTALADO.txt #5: desinstalar
; borra todo, hacer copia antes si se quiere conservar algo -- un UPGRADE en
; cambio SI preserva estos datos.
Type: filesandordirs; Name: "{app}"

[Code]
// ---- upgrade: version anterior/misma/posterior --------------------------
// AppId fijo + DefaultDirName fijo ya le alcanzan a Inno para reinstalar
// sobre la instalacion existente en vez de duplicarla (comportamiento
// nativo, no hace falta un segundo sistema de updates). Lo unico que agrega
// este bloque es la comparacion de VERSION -- Inno no la hace por si solo.
function GetInstalledVersion(var InstalledVersion: String): Boolean;
begin
  Result := RegQueryStringValue(HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1',
    'DisplayVersion', InstalledVersion);
end;

function InitializeSetup(): Boolean;
var
  InstalledVersion: String;
  VerNew, VerOld: Int64;
  Cmp: Integer;
begin
  Result := True;
  if not GetInstalledVersion(InstalledVersion) then
    exit; // no hay instalacion previa -- instalacion limpia, nada que comparar

  if not StrToVersion(InstalledVersion, VerOld) then exit;
  if not StrToVersion('{#MyAppVersion}', VerNew) then exit;
  Cmp := ComparePackedVersion(VerNew, VerOld);

  if Cmp < 0 then
  begin
    Result := (MsgBox(
      'Ya tenes instalado pivot-x-sentinel ' + InstalledVersion + ', mas nuevo que este instalador ' +
      '({#MyAppVersion}).' + #13#10#13#10 +
      'Instalar esta version ANTERIOR puede downgradear tu instalacion.' + #13#10#13#10 +
      '¿Queres continuar de todas formas?', mbConfirmation, MB_YESNO) = IDYES);
  end
  else if Cmp = 0 then
  begin
    MsgBox('pivot-x-sentinel ' + InstalledVersion + ' ya esta instalado.' + #13#10 +
      'Se va a reinstalar/reparar sobre la misma version.', mbInformation, MB_OK);
  end;
  // Cmp > 0 (upgrade normal a una version mas nueva): sigue sin avisar nada.
end;

// ---- upgrade: limpiar dependencias de la version vieja -------------------
// PyInstaller onedir guarda TODO el contenido reemplazable de la app bajo
// _internal (ver execution/src/paths.py). [Files] con /ignoreversion
// sobrescribe lo que coincide, pero NUNCA borra un archivo que existia en la
// version vieja y ya no existe en la nueva (ej. se saco una dependencia) --
// sin este paso, un upgrade podria dejar modulos huerfanos de la version
// anterior mezclados con los nuevos. Se borra ANTES de que [Files] copie
// (ssInstall), y SOLO _internal -- nunca {app} entera (ahi vive
// execution\data\scores y logs\, que tienen que sobrevivir el upgrade, ver
// execution/src/paths.py:user_data_root()).
procedure CurStepChanged(CurStep: TSetupStep);
var
  InternalDir: String;
begin
  if CurStep = ssInstall then
  begin
    InternalDir := ExpandConstant('{app}\_internal');
    if DirExists(InternalDir) then
      DelTree(InternalDir, True, True, True);
  end;
end;
