@echo off
REM =====================================================================
REM  PlacaBasePro - arma la version PORTABLE lista para compartir:
REM     dist\PlacaBasePro\            (carpeta del programa)
REM     PlacaBasePro_portable.zip     (la misma carpeta comprimida)
REM  Incluye Gmsh (dentro del programa) y CalculiX (solvers\calculix).
REM  La maquina de destino no necesita instalar nada.
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

if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Creando entorno virtual...
    "%PY%" -m venv .venv || goto :err
)
set "VP=%CD%\.venv\Scripts\python.exe"

echo [2/5] Instalando dependencias (incluye Gmsh)...
"%VP%" -m pip install --upgrade pip -q || goto :err
"%VP%" -m pip install -q -r requirements.txt pyinstaller || goto :err

echo [3/5] Autoprueba del motor de calculo...
"%VP%" selftest.py || goto :err

echo [4/5] Compilando (tarda varios minutos)...
"%VP%" -m PyInstaller --noconfirm --clean placabase.spec || goto :err

echo [5/5] Copiando solvers y comprimiendo...
REM  (con Python: no depende de xcopy/powershell ni del PATH de Windows)
"%VP%" -c "import shutil; shutil.copytree('solvers', r'dist\PlacaBasePro\solvers', dirs_exist_ok=True); shutil.copy('LEEME.md', r'dist\PlacaBasePro'); shutil.make_archive('PlacaBasePro_portable', 'zip', 'dist', 'PlacaBasePro')" || goto :err

echo.
echo ==============================================================
echo  LISTO.
echo    Carpeta: %CD%\dist\PlacaBasePro\PlacaBasePro.exe
echo    Para compartir: %CD%\PlacaBasePro_portable.zip
echo  Quien lo reciba solo descomprime y abre PlacaBasePro.exe.
echo ==============================================================
pause
exit /b 0
:err
echo.
echo *** ERROR en la compilacion ***
pause
exit /b 1
