@echo off
REM  Ejecuta la aplicacion directamente con Python (sin compilar el .exe).
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python run.py
if errorlevel 1 pause
