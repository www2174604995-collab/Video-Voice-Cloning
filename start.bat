@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0server"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set PYTHONIOENCODING=utf-8
"%PY%" -m app %*
if errorlevel 1 pause
