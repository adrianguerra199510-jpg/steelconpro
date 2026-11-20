@echo off
REM  Ejecuta la aplicacion directamente (sin compilar el .exe): Electron con el motor en Python.
REM  Requiere Python 3.11+ con las dependencias (pip install -r requirements.txt) y Node.js 20+.
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
cd electron
if not exist node_modules call npm install --no-audit --no-fund
call npm start
if errorlevel 1 pause
