# Pipeline completo de empaquetado -- Fase 7 (docs/roadmap.md).
#
# 1) Instala en .venv (la misma que usa run.bat) todo lo que hace falta para
#    correr el bot + pyinstaller.
# 2) Corre PyInstaller (packaging/pivot_x_sentinel.spec) -> dist/pivot-x-sentinel/
# 3) Si encuentra Inno Setup (ISCC.exe) instalado, compila el instalador final
#    -> packaging/dist_installer/pivot-x-sentinel-setup.exe
#    Si no lo encuentra, deja el build de PyInstaller listo y avisa como
#    instalar Inno Setup para terminar el paso 3 a mano.
#
# Uso (desde la raiz del repo o desde packaging/, da igual):
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "No se encontro $Python -- crea el venv primero (python -m venv .venv) e instala los requirements de api/ y execution/."
}

Write-Host "== 1/3: instalando dependencias en .venv ==" -ForegroundColor Cyan
& $Python -m pip install --upgrade pip | Out-Null
& $Python -m pip install -r api\requirements.txt -r execution\requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install fallo" }

Write-Host "== 2/3: PyInstaller (onedir) ==" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $Python -m PyInstaller packaging\pivot_x_sentinel.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo" }

$ExePath = "dist\pivot-x-sentinel\pivot-x-sentinel.exe"
if (-not (Test-Path $ExePath)) { throw "PyInstaller termino pero no aparecio $ExePath -- revisar el log de arriba." }
Write-Host "  OK -- $ExePath" -ForegroundColor Green

Write-Host "== 3/3: Inno Setup ==" -ForegroundColor Cyan
$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $Iscc) {
    foreach ($candidate in @(
        "$Env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
        "$Env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $candidate) { $Iscc = $candidate; break }
    }
}

if (-not $Iscc) {
    Write-Host ""
    Write-Host "Inno Setup no esta instalado -- el build de PyInstaller quedo listo en" -ForegroundColor Yellow
    Write-Host "  dist\pivot-x-sentinel\  (podes correrlo directo con pivot-x-sentinel.exe)." -ForegroundColor Yellow
    Write-Host "Para generar el instalador .exe final:" -ForegroundColor Yellow
    Write-Host "  1) Instala Inno Setup 6 (gratuito): https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    Write-Host "  2) Corre de nuevo este script, o directamente:" -ForegroundColor Yellow
    Write-Host "       ISCC packaging\installer.iss" -ForegroundColor Yellow
    exit 0
}

& $Iscc "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC (Inno Setup) fallo" }

Write-Host ""
Write-Host "Listo: packaging\dist_installer\pivot-x-sentinel-setup.exe" -ForegroundColor Green
