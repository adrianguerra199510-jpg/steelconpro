@echo off
REM =====================================================================
REM  SteelConPro - arma la aplicacion PORTABLE (Electron + motor de calculo):
REM     electron\dist\SteelConPro-<version>-portable.exe     (un solo archivo)
REM  Incluye Gmsh (dentro del motor) y CalculiX (solvers\calculix).
REM  La maquina de destino no necesita instalar nada.
REM  Requiere en esta maquina: Python 3.11+ y Node.js 20+.
REM =====================================================================
setlocal
cd /d "%~dp0"

set "PY="
for %%P in (py python) do if not defined PY (%%P -c "import sys" >nul 2>&1 && set "PY=%%P")
if not defined PY if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" set "PY=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
if not defined PY (
    echo No se encontro Python 3.  Instalelo desde python.org o Microsoft Store.
    goto :err
)
where node >nul 2>&1 || (
    echo No se encontro Node.js.  Instalelo desde nodejs.org.
    goto :err
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/6] Creando entorno virtual...
    "%PY%" -m venv .venv || goto :err
)
set "VP=%CD%\.venv\Scripts\python.exe"

echo [2/6] Instalando dependencias del motor (incluye Gmsh)...
"%VP%" -m pip install --upgrade pip -q || goto :err
"%VP%" -m pip install -q -r requirements.txt pyinstaller || goto :err

echo [3/6] Autoprueba del motor de calculo...
"%VP%" selftest.py || goto :err

echo [4/6] Compilando el motor (tarda varios minutos)...
"%VP%" -m PyInstaller --noconfirm --clean steelconpro.spec || goto :err

echo [5/6] Copiando solvers...
"%VP%" -c "import shutil; shutil.copytree('solvers', r'dist\engine\solvers', dirs_exist_ok=True)" || goto :err

echo [6/6] Armando la aplicacion Electron...
pushd electron
call npm install --no-audit --no-fund || (popd & goto :err)
call npx electron-builder --win portable --publish never || (popd & goto :err)
popd

echo.
echo ==============================================================
echo  LISTO.
echo    Ejecutable portable: %CD%\electron\dist\SteelConPro-1.1.0-portable.exe
echo  Quien lo reciba solo lo abre: no necesita instalar nada.
echo ==============================================================
pause
exit /b 0
:err
echo.
echo *** ERROR en la compilacion ***
pause
exit /b 1
